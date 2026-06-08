"""Smarter prompt/memory wrapper for the shipped LLM ReAct agent.

This is intentionally still an LLM-controlled agent. It does not encode a
city plan or preselected coordinates. The changes are model-facing:

- clearer operating doctrine for the 720/730-day score;
- compact map occupancy so the model can avoid already-used tiles;
- recent tool-outcome memory so rejected actions are not invisible.
"""

from __future__ import annotations

from collections import Counter, deque
from contextlib import suppress
from copy import deepcopy
from typing import Any

from agents.llm import ToolCall
from agents.llm_react.agent import (
    DEFAULT_STEP_DAYS_FALLBACK,
    MAX_TOKENS_PER_TURN,
    LLMReactAgent,
)
from agents.prompts import ACTION_TOOLS
from agents.state_summary import summarize_state
from agents.tool_dispatch import dispatch_tool_call

SMART_SYSTEM_PROMPT = """\
You are controlling an autonomous city-energy simulation for a 720/730-day
score. Your job is to make operational decisions through tool calls.

Primary objective:
- Preserve solvency and keep treasury positive.
- Grow population by balancing housing capacity, jobs, happiness, and power.
- Add renewable served energy when the city can afford it.
- Avoid peak-and-collapse behavior. A stable, cash-positive, growing city
  scores far better than speculative spending.

How to think each turn:
1. Read the current state, visible map, and recent tool outcomes.
2. Diagnose the current bottleneck: power, housing, jobs, happiness, cash,
   renewable share, or wasted actions.
3. Make a small number of high-confidence tool calls.
4. End with exactly one step(days=N) call.

Critical behavior requirements:
- Do not repeat an exact failed tool call from RECENT TOOL OUTCOMES.
- Do not build on occupied coordinates from VISIBLE_SURFACE.
- Requires-road tiles need direct orthogonal adjacency to connected road or
  town_hall. A house or commercial tile does not extend road adjacency.
- If a build is rejected as tile_occupied or no_road_adjacency, choose a
  different empty location next turn instead of retrying it.
- Population growth needs both free housing and enough jobs. If jobs_gap is
  negative, add jobs before adding more houses.
- If housing_gap is already large, more houses do not fix growth.
- Jobs far above population are not useful by themselves. Avoid adding many
  industrial/commercial tiles when jobs_gap is already strongly positive.
- Renewable share is a direct score component. If renewable served energy is
  low and cash is healthy, add solar/wind/battery before more fossil-heavy
  industrial growth.
- Renewables improve power and score but are not the main cash engine.
  Houses also do not create jobs or revenue by themselves.
- Industrial is the reliable early cashflow tile when it is staffed and
  powered; commercial is modest and depends on nearby occupied housing.
- Before planning builds, mentally subtract their CAPEX. In the first
  180 days, try to preserve about $100k treasury reserve instead of spending
  down to near zero.
- If you build a road, that coordinate becomes occupied. Do not also build a
  house/commercial/industrial on the same coordinate in the same turn.
- MAP_BUILD_CONTEXT road-required coordinates are already valid for buildings
  right now; do not build a road on them first.
- If you choose to extend roads, make the road extension the only build action
  and step afterward so the next state summary shows newly valid tiles.
- Solar farms and batteries do not need roads. Use open non-road candidates
  for them when renewable share is low.
- Survey/drill/oil are optional and risky. Use them only when you have a
  funded, concrete oil plan; otherwise grow the surface city.
- Do not demolish unless a tile is clearly harmful or blocking a better plan.
- If cash is low or negative, stop spending and step several days to recover.
- Treat treasury below about $100k as low cash. Do not keep attempting
  expensive builds after insufficient_funds.
- If population is falling, fix jobs/housing/happiness and power reliability.
- If there is enough cash and the city is stable, invest in renewables,
  batteries, and balanced housing/jobs growth.

Tool discipline:
- Emit tool calls only. No prose.
- The final tool call must be step with days in [1, 7].
- Use step(days=7) when waiting, cash-recovering, or monitoring a stable city.
  Use shorter steps only when you need a fast follow-up after new builds/events.
- Use at most 1-3 non-step tool calls per turn. More is usually reckless.
"""


class SmartLLMReactAgent(LLMReactAgent):
    """LLM agent with model-visible action feedback and map context."""

    MEMORY_SIZE = 24

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        kwargs.setdefault("system_prompt", SMART_SYSTEM_PROMPT)
        kwargs.setdefault("action_tools", _smart_action_tools())
        kwargs.setdefault("max_tokens_per_turn", MAX_TOKENS_PER_TURN)
        super().__init__(*args, **kwargs)
        self._recent_outcomes: deque[str] = deque(maxlen=self.MEMORY_SIZE)
        self._recent_failures: deque[str] = deque(maxlen=self.MEMORY_SIZE)
        self._catalog_digest: str | None = None

    def decide(
        self,
        state: dict[str, Any],
        forecast: list[dict[str, Any]] | None,
        *,
        game_days: int,
    ) -> int:
        user_msg = self._smart_summary(state, forecast)
        response = self.llm.chat(
            system=self.system_prompt,
            user=user_msg,
            tools=self.action_tools,
            max_tokens=self.max_tokens_per_turn,
        )
        self._record_usage(response.usage.total)

        if not response.tool_calls:
            self._remember("model returned no tool calls")

        remaining_days = game_days - int(state["day"])
        for call in response.tool_calls:
            if call.name == "step":
                days = self._step_days(call, remaining_days)
                try:
                    self.api.step(days=days)
                    self._remember(f"step(days={days}) ok")
                    return days
                except RuntimeError as exc:
                    self._remember(f"step(days={days}) rejected: {exc}")
                    return 0

            before_cash = float(state.get("treasury", 0.0))
            try:
                result = dispatch_tool_call(self.api, call)
            except (RuntimeError, KeyError, TypeError, ValueError) as exc:
                self._remember_failure(
                    f"{_call_sig(call)} rejected: {type(exc).__name__}: {exc}"
                )
                continue

            if result is None:
                self._remember_failure(f"{_call_sig(call)} ignored: unknown tool")
                continue

            ok = bool(result.get("ok"))
            error = result.get("error")
            treasury_after = result.get("treasury_after")
            cash_text = ""
            if isinstance(treasury_after, int | float):
                cash_text = f" treasury_after=${treasury_after:,.0f}"
            elif before_cash:
                cash_text = f" treasury_before=${before_cash:,.0f}"
            if ok:
                self._remember(f"{_call_sig(call)} ok{cash_text}")
            else:
                self._remember_failure(f"{_call_sig(call)} failed error={error}{cash_text}")

            # Refresh state after mutations so later summaries are accurate next turn.
            with suppress(RuntimeError):
                state = self.api.state()

        return 0

    def _step_days(self, call: ToolCall, remaining_days: int) -> int:
        try:
            days = int(call.arguments.get("days", DEFAULT_STEP_DAYS_FALLBACK))
        except (TypeError, ValueError):
            days = DEFAULT_STEP_DAYS_FALLBACK
        days = max(1, min(7, days))
        return min(days, max(1, remaining_days))

    def _smart_summary(
        self,
        state: dict[str, Any],
        forecast: list[dict[str, Any]] | None,
    ) -> str:
        parts = [summarize_state(state, forecast)]
        parts.append(self._catalog_context())
        parts.append(_city_diagnosis(state))
        parts.append(_visible_surface(state))
        parts.append(_build_context(state))
        if self._recent_outcomes:
            parts.append("RECENT_TOOL_OUTCOMES:\n" + "\n".join(f"- {x}" for x in self._recent_outcomes))
        else:
            parts.append("RECENT_TOOL_OUTCOMES: none yet")
        if self._recent_failures:
            parts.append("RECENT_FAILED_CALLS:\n" + "\n".join(f"- {x}" for x in self._recent_failures))
        else:
            parts.append("RECENT_FAILED_CALLS: none yet")
        parts.append(
            "TURN_INSTRUCTIONS:\n"
            "- Choose actions based on the bottleneck and visible map.\n"
            "- Use MAP_BUILD_CONTEXT when selecting coordinates.\n"
            "- road_required candidates are valid right now; do not turn those same coordinates into roads first.\n"
            "- Avoid exact repeats of failed calls.\n"
            "- Prefer fewer, higher-confidence actions over many speculative actions.\n"
            "- End with one step(days=N)."
        )
        return "\n\n".join(parts)

    def _remember(self, text: str) -> None:
        self._recent_outcomes.append(text)

    def _remember_failure(self, text: str) -> None:
        self._recent_outcomes.append(text)
        self._recent_failures.append(text)

    def _catalog_context(self) -> str:
        if self._catalog_digest is not None:
            return self._catalog_digest
        try:
            catalog = self.api.catalog()
        except RuntimeError as exc:
            self._catalog_digest = f"CATALOG_CONTEXT unavailable: {exc}"
            return self._catalog_digest
        self._catalog_digest = _catalog_digest(catalog)
        return self._catalog_digest


def _smart_action_tools() -> list[dict[str, Any]]:
    tools = deepcopy(ACTION_TOOLS)
    for tool in tools:
        if tool.get("name") != "survey":
            continue
        params = tool.get("parameters", {})
        required = list(params.get("required", []))
        if "size" not in required:
            required.append("size")
        params["required"] = required
        tool["description"] = (
            "Reveal a size×size column of subsurface voxels centered at (x, y). "
            "Always specify size explicitly. Cost = 15_000·(size/4)^2, so "
            "size=4 costs $15k and is the cheapest focused survey; size=16 "
            "costs $240k and should only be used when the treasury can absorb it."
        )
    return tools


def _catalog_digest(catalog: dict[str, Any]) -> str:
    lines = ["CATALOG_CONTEXT:"]
    tiles = {str(t.get("tile_type")): t for t in catalog.get("tiles", [])}
    wanted = [
        "road",
        "house",
        "commercial",
        "industrial",
        "park",
        "solar_farm",
        "wind_turbine",
        "battery",
        "coal_plant",
        "gas_peaker",
        "refinery",
        "pipeline",
    ]
    for name in wanted:
        spec = tiles.get(name)
        if not spec:
            continue
        attrs = [
            f"capex=${float(spec.get('capex', 0)):,.0f}",
            f"opex=${float(spec.get('opex_per_day', 0)):,.0f}/d",
        ]
        if spec.get("housing_capacity"):
            attrs.append(f"housing={spec['housing_capacity']}")
        if spec.get("jobs"):
            attrs.append(f"jobs={spec['jobs']}")
        if spec.get("demand_kw"):
            attrs.append(f"demand={spec['demand_kw']}kW")
        if spec.get("capacity_kw"):
            attrs.append(f"capacity={spec['capacity_kw']}kW")
        if spec.get("storage_kwh"):
            attrs.append(f"storage={spec['storage_kwh']}kWh")
        if spec.get("requires_road"):
            attrs.append("road_required")
        lines.append(f"- {name}: " + " ".join(attrs))

    economics = catalog.get("economics", {})
    if economics:
        lines.append(
            "- economics: "
            f"industrial_revenue=${float(economics.get('industrial_revenue_per_day', 0)):,.0f}/staffed_industrial_day "
            f"commercial_revenue=${float(economics.get('commercial_revenue_per_resident_per_day', 0)):,.0f}/nearby_resident_day "
            f"retail_power=${float(economics.get('grid_price_retail', 0)):.2f}/kWh "
            f"export_power=${float(economics.get('grid_price_export', 0)):.2f}/kWh"
        )
        lines.append(
            "- cashflow_note: industrial is the reliable early revenue tile if staffed and powered; "
            "commercial is modest and location-dependent; solar/wind improve score and supply but do not replace revenue."
        )

    subsurface = catalog.get("subsurface", {})
    survey = subsurface.get("survey", {})
    if survey:
        lines.append(
            "- survey: "
            f"min_size={survey.get('min_size')} default_size={survey.get('default_size')} "
            f"base_cost=${float(survey.get('base_cost', 0)):,.0f} "
            f"formula={survey.get('cost_formula')}"
        )
    drill = subsurface.get("drill", {})
    production = drill.get("production", {})
    injection = drill.get("injection", {})
    if production or injection:
        lines.append(
            "- oil_tools: "
            f"producer_base=${float(production.get('capex', 0)):,.0f} "
            f"injector_base=${float(injection.get('capex', 0)):,.0f} "
            f"max_rate={production.get('max_rate_bbl_day')}bbl/d "
            f"crude=${float(production.get('crude_price_usd_per_bbl', 0)):,.0f}/bbl"
        )
    return "\n".join(lines)


def _city_diagnosis(state: dict[str, Any]) -> str:
    tiles = state.get("tiles") or []
    population = float(state.get("population", 0.0))
    treasury = float(state.get("treasury", 0.0))
    happiness = float(state.get("happiness", 0.0))
    housing = sum(float(t.get("housing_capacity", 0.0)) for t in tiles)
    jobs = sum(float(t.get("jobs", 0.0)) for t in tiles)
    counts = Counter(str(t.get("type", "?")) for t in tiles)
    preview = state.get("next_24h_preview") or {}
    worst_reserve = preview.get("worst_hour_reserve_margin_pct")
    balance = state.get("balance_state") or (state.get("power_now") or {}).get("balance_state")
    active_events = [str(e.get("type")) for e in state.get("active_events", [])]
    return "\n".join(
        [
            "CITY_DIAGNOSIS:",
            f"- treasury=${treasury:,.0f} population={population:.0f} happiness={happiness:.2f}",
            f"- housing_capacity={housing:.0f} jobs={jobs:.0f} housing_gap={housing - population:.0f} jobs_gap={jobs - population:.0f}",
            "- tile_counts="
            + " ".join(f"{name}={count}" for name, count in sorted(counts.items())),
            f"- current_balance={balance} forecast_worst_reserve_pct={worst_reserve}",
            "- active_events=" + (",".join(active_events) if active_events else "none"),
        ]
    )


def _build_context(state: dict[str, Any]) -> str:
    tiles = state.get("tiles") or []
    cfg = state.get("config") or {}
    width = int(cfg.get("world_w", 32))
    height = int(cfg.get("world_h", 32))
    occupied = {
        (int(t.get("x", -1)), int(t.get("y", -1))): str(t.get("type", "?"))
        for t in tiles
    }
    road_network = _road_network(occupied, width, height)
    road_required = _empty_neighbors(road_network, occupied, width, height)
    open_nonroad = [
        (x, y)
        for y in range(height)
        for x in range(width)
        if (x, y) not in occupied
    ]
    halo_safe = _halo_safe_empty(occupied, width, height)
    return "\n".join(
        [
            "MAP_BUILD_CONTEXT:",
            "- valid_now_road_required for house/commercial/industrial/refinery: "
            + _fmt_coords(_near_town_hall(road_required, occupied), limit=36),
            "- open_nonroad_candidates for solar_farm/battery/park/pipeline: "
            + _fmt_coords(_near_town_hall(open_nonroad, occupied), limit=36),
            "- halo_safe_candidates for wind/gas/coal plants: "
            + _fmt_coords(_near_town_hall(halo_safe, occupied), limit=36),
        ]
    )


def _road_network(
    occupied: dict[tuple[int, int], str],
    width: int,
    height: int,
) -> set[tuple[int, int]]:
    start = next((pos for pos, tile_type in occupied.items() if tile_type == "town_hall"), None)
    if start is None:
        return set()
    seen = {start}
    stack = [start]
    while stack:
        x, y = stack.pop()
        for nx, ny in _neighbors4(x, y):
            if not (0 <= nx < width and 0 <= ny < height):
                continue
            if (nx, ny) in seen:
                continue
            if occupied.get((nx, ny)) not in {"road", "town_hall"}:
                continue
            seen.add((nx, ny))
            stack.append((nx, ny))
    return seen


def _empty_neighbors(
    positions: set[tuple[int, int]],
    occupied: dict[tuple[int, int], str],
    width: int,
    height: int,
    *,
    include_diagonal: bool = False,
) -> list[tuple[int, int]]:
    candidates: set[tuple[int, int]] = set()
    offsets = _NEIGHBORS8 if include_diagonal else _NEIGHBORS4
    for x, y in positions:
        for dx, dy in offsets:
            nx, ny = x + dx, y + dy
            if 0 <= nx < width and 0 <= ny < height and (nx, ny) not in occupied:
                candidates.add((nx, ny))
    return sorted(candidates)


def _halo_safe_empty(
    occupied: dict[tuple[int, int], str],
    width: int,
    height: int,
) -> list[tuple[int, int]]:
    admitted = {"road", "battery", "town_hall", "pipeline"}
    candidates = []
    for y in range(height):
        for x in range(width):
            if (x, y) in occupied:
                continue
            unsafe = False
            for dx, dy in _NEIGHBORS8:
                tile_type = occupied.get((x + dx, y + dy))
                if tile_type is not None and tile_type not in admitted:
                    unsafe = True
                    break
            if not unsafe:
                candidates.append((x, y))
    return candidates


def _near_town_hall(
    coords: list[tuple[int, int]],
    occupied: dict[tuple[int, int], str],
) -> list[tuple[int, int]]:
    town_hall = next((pos for pos, tile_type in occupied.items() if tile_type == "town_hall"), (16, 16))
    tx, ty = town_hall
    return sorted(coords, key=lambda pos: (abs(pos[0] - tx) + abs(pos[1] - ty), pos[1], pos[0]))


def _fmt_coords(coords: list[tuple[int, int]], *, limit: int) -> str:
    if not coords:
        return "none"
    return " ".join(f"({x},{y})" for x, y in coords[:limit])


def _neighbors4(x: int, y: int) -> tuple[tuple[int, int], ...]:
    return ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1))


def _visible_surface(state: dict[str, Any]) -> str:
    tiles = state.get("tiles") or []
    if not tiles:
        return "VISIBLE_SURFACE: no tiles"
    compact = [
        f"{t.get('type')}@({int(t.get('x', -1))},{int(t.get('y', -1))})"
        for t in sorted(tiles, key=lambda x: (str(x.get("type")), int(x.get("y", 0)), int(x.get("x", 0))))
    ]
    return "VISIBLE_SURFACE occupied coordinates:\n" + " ".join(compact[:180])


def _call_sig(call: ToolCall) -> str:
    args = ",".join(f"{key}={value!r}" for key, value in sorted(call.arguments.items()))
    return f"{call.name}({args})"


Agent = SmartLLMReactAgent


_NEIGHBORS4: tuple[tuple[int, int], ...] = ((1, 0), (-1, 0), (0, 1), (0, -1))
_NEIGHBORS8: tuple[tuple[int, int], ...] = (
    (-1, -1),
    (0, -1),
    (1, -1),
    (-1, 0),
    (1, 0),
    (-1, 1),
    (0, 1),
    (1, 1),
)
