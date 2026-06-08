"""State-based deterministic growth policy.

The policy is intentionally no-oil for its first version. It takes the stable
opening from the robust baseline and the high-population city shape from the
old V3 runs, but gates growth on cash reserve and forecast health.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agents.api_client import ApiClient
from agents.base import BaseAgent

Plan = tuple[tuple[str, int, int], ...]


CAPEX: dict[str, float] = {
    "road": 500.0,
    "house": 3_000.0,
    "commercial": 8_000.0,
    "park": 5_000.0,
    "solar_farm": 25_000.0,
    "wind_turbine": 40_000.0,
    "battery": 60_000.0,
    "coal_plant": 200_000.0,
}


BOOTSTRAP_PLAN: Plan = (
    ("solar_farm", 24, 15),
    ("solar_farm", 24, 16),
    ("solar_farm", 24, 17),
    ("battery", 23, 15),
    ("wind_turbine", 30, 10),
    ("commercial", 16, 15),
    ("commercial", 16, 17),
    ("commercial", 15, 15),
    ("commercial", 15, 17),
    ("park", 15, 14),
    ("house", 14, 15),
)


FIRST_GROWTH_PLAN: Plan = (
    ("road", 17, 16),
    ("road", 18, 16),
    ("road", 19, 16),
    ("house", 17, 15),
    ("house", 18, 15),
    ("house", 19, 15),
    ("commercial", 17, 17),
    ("commercial", 18, 17),
    ("park", 18, 14),
    ("park", 19, 14),
)


SECOND_GROWTH_PLAN: Plan = (
    ("road", 20, 16),
    ("road", 21, 16),
    ("road", 22, 16),
    ("house", 20, 15),
    ("house", 21, 15),
    ("house", 22, 15),
    ("commercial", 20, 17),
    ("commercial", 21, 17),
    ("park", 22, 14),
)


HOUSE_SURPLUS_PLAN: Plan = (
    ("road", 22, 17),
    ("house", 23, 17),
    ("park", 23, 18),
)


ROAD_GRID_PLAN: Plan = (
    ("road", 22, 18),
    ("road", 22, 19),
    ("road", 22, 20),
    ("road", 22, 21),
    ("road", 22, 22),
    ("road", 22, 23),
    ("road", 22, 24),
    ("road", 22, 25),
    ("road", 22, 26),
    ("road", 22, 27),
    ("road", 22, 28),
    *(("road", x, y) for y in (19, 22, 25, 28) for x in range(23, 32)),
)


COAL_BACKUP_PLAN: Plan = (
    ("road", 9, 15),
    ("road", 8, 15),
    ("coal_plant", 8, 14),
)


def _support_row(
    house_y: int,
    support_y: int,
    *,
    commercial_xs: tuple[int, ...],
    park_xs: tuple[int, ...],
) -> Plan:
    return (
        *(("house", x, house_y) for x in range(23, 32)),
        *(("commercial", x, support_y) for x in commercial_xs),
        *(("park", x, support_y) for x in park_xs),
    )


ROW_20_GARDEN_5C: Plan = _support_row(
    20,
    21,
    commercial_xs=(23, 25, 27, 29, 31),
    park_xs=(24, 26, 28, 30),
)


ROW_23_GARDEN_5C: Plan = _support_row(
    23,
    24,
    commercial_xs=(23, 25, 27, 29, 31),
    park_xs=(24, 26, 28, 30),
)


ROW_26_GARDEN_5C: Plan = _support_row(
    26,
    27,
    commercial_xs=(23, 25, 27, 29, 31),
    park_xs=(24, 26, 28, 30),
)


ROW_29_EDGE_3C: Plan = (
    *(("house", x, 29) for x in range(23, 32)),
    ("park", 25, 30),
    ("park", 28, 30),
    ("park", 31, 30),
    ("commercial", 25, 18),
    ("commercial", 28, 18),
    ("commercial", 31, 18),
)


SOLAR_STAGE_1_PLAN: Plan = (
    ("solar_farm", 26, 3),
    ("solar_farm", 27, 3),
    ("solar_farm", 28, 3),
    ("solar_farm", 29, 3),
)


SOLAR_STAGE_2_PLAN: Plan = (
    ("solar_farm", 26, 4),
    ("solar_farm", 27, 4),
    ("solar_farm", 28, 4),
    ("solar_farm", 29, 4),
)


SOLAR_STAGE_3_PLAN: Plan = (
    ("solar_farm", 26, 5),
    ("solar_farm", 27, 5),
    ("solar_farm", 28, 5),
    ("solar_farm", 29, 5),
)


BATTERY_STAGE_1_PLAN: Plan = (
    ("battery", 30, 3),
    ("battery", 31, 3),
)


BATTERY_STAGE_2_PLAN: Plan = (
    ("battery", 30, 4),
    ("battery", 31, 4),
)


BATTERY_STAGE_3_PLAN: Plan = (
    ("battery", 30, 5),
    ("battery", 31, 5),
)


BATTERY_STAGE_4_PLAN: Plan = (
    ("battery", 30, 6),
    ("battery", 31, 6),
)


@dataclass(frozen=True)
class Stage:
    name: str
    floor: float
    reserve: float
    plan: Plan
    kind: str


STAGES: tuple[Stage, ...] = (
    Stage("first growth", 50_000.0, 25_000.0, FIRST_GROWTH_PLAN, "demand"),
    Stage("second growth", 100_000.0, 50_000.0, SECOND_GROWTH_PLAN, "demand"),
    Stage("house surplus", 40_000.0, 25_000.0, HOUSE_SURPLUS_PLAN, "demand"),
    Stage("coal/grid backbone", 380_000.0, 150_000.0, COAL_BACKUP_PLAN + ROAD_GRID_PLAN, "security"),
    Stage("row 20", 180_000.0, 80_000.0, ROW_20_GARDEN_5C, "demand"),
    Stage("row 23", 250_000.0, 120_000.0, ROW_23_GARDEN_5C, "demand"),
    Stage("energy 1", 290_000.0, 70_000.0, SOLAR_STAGE_1_PLAN + BATTERY_STAGE_1_PLAN, "energy"),
    Stage("row 26", 240_000.0, 80_000.0, ROW_26_GARDEN_5C, "demand"),
    Stage("energy 2", 360_000.0, 120_000.0, SOLAR_STAGE_2_PLAN + BATTERY_STAGE_2_PLAN, "energy"),
    Stage("row 29", 330_000.0, 140_000.0, ROW_29_EDGE_3C, "demand"),
    Stage("energy 3", 460_000.0, 260_000.0, SOLAR_STAGE_3_PLAN, "energy"),
    Stage("battery 3", 680_000.0, 430_000.0, BATTERY_STAGE_3_PLAN, "energy"),
    Stage("battery 4", 840_000.0, 560_000.0, BATTERY_STAGE_4_PLAN, "energy"),
)


ECONOMY_STRESS_MARKERS: frozenset[str] = frozenset({"fuel_cost_shock", "crude_collapse"})
ECONOMY_SAFE_STAGES: frozenset[str] = frozenset(
    {"first growth", "second growth", "house surplus"}
)
LATE_POPULATION_STAGES: frozenset[str] = frozenset({"row 26", "row 29"})


class SafeAdaptiveGrowthAgent(BaseAgent):
    """Fast deterministic controller with no seed/scenario routing."""

    RESTORE_TREASURY_FLOOR = 120_000.0
    SMALL_CITY_RESTORE_TREASURY_FLOOR = 8_000.0
    GROWTH_MAX_SHED_SITES = 3
    SMALL_CITY_MAX_SHED_SITES = 8

    def __init__(self, api: ApiClient, *, seed: int | None = None) -> None:
        super().__init__(api, seed=seed)
        self._bootstrapped = False
        self._stage_index = 0
        self._shed_sites: list[tuple[int, int]] = []
        self._economy_stress_seen = False

    def next_step_days(self, state: dict[str, Any]) -> int:
        return 1

    def act(self, state: dict[str, Any]) -> None:
        if not self._bootstrapped:
            self._build_plan(BOOTSTRAP_PLAN, "bootstrap")
            self._bootstrapped = True
            return

        latest = self.api.state()
        if self._deterministic_economy_stress_active(latest):
            self._economy_stress_seen = True

        if self._live_plant_failure(latest):
            self._shed_for_plant_failure(latest)
            return

        if self._preview_has_outage(latest) and self._shed_until_preview_ok(
            latest, max_sites=self._shed_limit(latest)
        ):
            return

        if self._shed_sites and self._safe_to_restore(latest):
            self._restore_one_if_safe(latest)
            return

        self._build_next_safe_stage(latest)

    def _build_next_safe_stage(self, state: dict[str, Any]) -> None:
        if self._stage_index >= len(STAGES):
            return
        stage = STAGES[self._stage_index]
        treasury = float(state["treasury"])
        if self._economy_stress_seen and stage.name not in ECONOMY_SAFE_STAGES:
            return
        if treasury < stage.floor:
            return
        if treasury - _plan_cost(stage.plan) < self._dynamic_reserve(state, stage):
            return
        if stage.kind == "demand" and self._preview_margin(state) < self._stage_margin_floor(state, stage):
            return
        if stage.kind == "demand" and self._weather_or_load_risk_active(state):
            return

        self._build_plan(stage.plan, stage.name)
        self._stage_index += 1

        latest = self.api.state()
        if self._preview_has_outage(latest):
            self._shed_until_preview_ok(latest, max_sites=self._shed_limit(latest))

    def _dynamic_reserve(self, state: dict[str, Any], stage: Stage) -> float:
        reserve = stage.reserve
        day = int(state["day"])
        if day < 120:
            reserve += 40_000.0
        if self._weather_or_load_risk_active(state):
            reserve += 120_000.0
        if float(state.get("happiness", 1.0)) < 1.05:
            reserve += 50_000.0
        return reserve

    def _is_emergency(self, state: dict[str, Any]) -> bool:
        return self._live_plant_failure(state) or self._preview_has_outage(state)

    def _live_plant_failure(self, state: dict[str, Any]) -> bool:
        day = int(state["day"])
        return any(
            event.get("type") == "plant_failure" and int(event.get("ends_day", day + 1)) > day
            for event in state.get("active_events", [])
        )

    def _weather_or_load_risk_active(self, state: dict[str, Any]) -> bool:
        return any(
            event.get("type") in {"heatwave", "demand_surprise", "fuel_price_shock"}
            for event in state.get("active_events", [])
        )

    def _deterministic_economy_stress_active(self, state: dict[str, Any]) -> bool:
        if float(state.get("crude_price_usd_per_bbl", 40.0)) <= 20.0:
            return True
        return any(
            event.get("type") in ECONOMY_STRESS_MARKERS
            for event in state.get("active_events", [])
        )

    def _preview_has_outage(self, state: dict[str, Any]) -> bool:
        preview = state.get("next_24h_preview") or {}
        return any(
            str(mode) in {"brownout", "blackout", "BalanceState.BROWNOUT", "BalanceState.BLACKOUT"}
            for mode in preview.get("balance_state_by_hour", [])
        )

    def _preview_margin(self, state: dict[str, Any]) -> float:
        preview = state.get("next_24h_preview") or {}
        return float(preview.get("min_reserve_margin", 0.0))

    def _stage_margin_floor(self, state: dict[str, Any], stage: Stage) -> float:
        if stage.name in LATE_POPULATION_STAGES and self._has_hardened_grid(state):
            return 0.0
        return 0.05

    def _has_hardened_grid(self, state: dict[str, Any]) -> bool:
        counts: dict[str, int] = {}
        for tile in state.get("tiles", []):
            tile_type = str(tile.get("type"))
            counts[tile_type] = counts.get(tile_type, 0) + 1
        return (
            counts.get("coal_plant", 0) >= 2
            and counts.get("solar_farm", 0) >= 7
            and counts.get("battery", 0) >= 3
        )

    def _shed_until_preview_ok(
        self,
        state: dict[str, Any],
        *,
        max_sites: int | None = None,
    ) -> bool:
        did_shed = False
        latest = state
        limit = self.SMALL_CITY_MAX_SHED_SITES if max_sites is None else max_sites
        while self._preview_has_outage(latest) and len(self._shed_sites) < limit:
            tile = self._lowest_value_staffed_commercial(latest)
            if tile is None:
                break
            x, y = int(tile["x"]), int(tile["y"])
            result = self.api.demolish(x, y)
            if not result.get("ok"):
                break
            self._shed_sites.append((x, y))
            did_shed = True
            latest = self.api.state()
        return did_shed

    def _shed_for_plant_failure(self, state: dict[str, Any]) -> bool:
        return self._shed_until_preview_ok(
            state,
            max_sites=self._shed_limit(state),
        )

    def _lowest_value_staffed_commercial(self, state: dict[str, Any]) -> dict[str, Any] | None:
        candidates = [
            tile
            for tile in state["tiles"]
            if tile["type"] == "commercial"
            and int(tile.get("staffed_jobs", 0)) > 0
            and (int(tile["x"]), int(tile["y"])) not in self._shed_sites
        ]
        if not candidates:
            return None
        candidates.sort(
            key=lambda tile: (
                float(tile.get("estimated_net_per_day", 0.0)),
                float(tile.get("residents_in_radius", 0.0)),
                -int(tile["x"]),
                -int(tile["y"]),
            )
        )
        return candidates[0]

    def _safe_to_restore(self, state: dict[str, Any]) -> bool:
        floor = (
            self.SMALL_CITY_RESTORE_TREASURY_FLOOR
            if self._small_city_or_economy_mode(state)
            else self.RESTORE_TREASURY_FLOOR
        )
        if float(state["treasury"]) < floor:
            return False
        if (
            self._weather_or_load_risk_active(state)
            or self._live_plant_failure(state)
        ):
            return False
        return not self._preview_has_outage(state)

    def _small_city_or_economy_mode(self, state: dict[str, Any]) -> bool:
        return self._economy_stress_seen or int(state["population"]) < 220

    def _shed_limit(self, state: dict[str, Any]) -> int:
        if self._small_city_or_economy_mode(state):
            return self.SMALL_CITY_MAX_SHED_SITES
        return self.GROWTH_MAX_SHED_SITES

    def _restore_one_if_safe(self, state: dict[str, Any]) -> None:
        if not self._shed_sites:
            return
        x, y = self._shed_sites[0]
        result = self.api.build("commercial", x, y)
        if result.get("ok"):
            self._shed_sites.pop(0)

    def _build_plan(self, plan: Plan, label: str) -> None:
        for tile_type, x, y in plan:
            result = self.api.build(tile_type, x, y)
            if not result.get("ok"):
                raise RuntimeError(f"{label} failed: {tile_type}@({x},{y}): {result.get('error')}")


def _plan_cost(plan: Plan) -> float:
    return sum(CAPEX[tile_type] for tile_type, _x, _y in plan)


Agent = SafeAdaptiveGrowthAgent
