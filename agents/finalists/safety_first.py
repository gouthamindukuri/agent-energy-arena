"""Submission agent: adaptive safety-envelope controller.

The default policy is a deterministic state-feedback controller. It uses
the public 24h dispatch preview as a safety signal, keeps cash buffers
before capital work, sheds low-value commercial load during grid stress,
and rebuilds it once the preview is clean again.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from agents.api_client import ApiClient
from agents.base import BaseAgent

Plan = tuple[tuple[str, int, int], ...]


@dataclass(frozen=True)
class Stage:
    name: str
    plan: Plan
    reserve: float
    min_day: int = 0


@dataclass(frozen=True)
class PolicyConfig:
    name: str
    bootstrap: Plan
    stages: tuple[Stage, ...]
    bootstrap_buffer: float
    restore_buffer: float


BOOTSTRAP_CORE: Plan = (
    ("solar_farm", 24, 15),
    ("solar_farm", 24, 16),
    ("solar_farm", 24, 17),
    ("solar_farm", 24, 18),
    ("battery", 23, 15),
    ("commercial", 16, 15),
    ("commercial", 16, 17),
    ("commercial", 15, 15),
    ("park", 15, 14),
    ("park", 15, 18),
    ("house", 14, 15),
    ("house", 14, 17),
)

BOOTSTRAP_AGGRESSIVE: Plan = (
    ("solar_farm", 24, 15),
    ("solar_farm", 24, 16),
    ("solar_farm", 24, 17),
    ("solar_farm", 24, 18),
    ("battery", 23, 15),
    ("battery", 23, 16),
    ("commercial", 16, 15),
    ("commercial", 16, 17),
    ("commercial", 15, 15),
    ("park", 15, 14),
    ("park", 15, 18),
    ("house", 14, 15),
    ("house", 14, 17),
)

FLEX_CORE: Plan = (
    ("battery", 23, 16),
    ("commercial", 15, 17),
)

FLEX_CORE_AGGRESSIVE: Plan = (
    ("commercial", 15, 17),
)

CORE_A: Plan = (
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

CORE_B: Plan = (
    ("road", 20, 16),
    ("road", 21, 16),
    ("road", 22, 16),
    ("road", 22, 17),
    ("house", 20, 15),
    ("house", 21, 15),
    ("house", 22, 15),
    ("commercial", 20, 17),
    ("commercial", 21, 17),
    ("park", 20, 14),
    ("park", 22, 14),
)

BACKUP_COAL: Plan = (
    ("road", 9, 15),
    ("road", 8, 15),
    ("coal_plant", 8, 14),
)

ROAD_GRID: Plan = (
    *(("road", 22, y) for y in range(18, 29)),
    *(("road", x, y) for y in (19, 22, 25, 28) for x in range(23, 32)),
)

ENERGY_A: Plan = (
    ("solar_farm", 26, 3),
    ("solar_farm", 27, 3),
    ("solar_farm", 28, 3),
    ("solar_farm", 29, 3),
    ("battery", 30, 3),
    ("battery", 31, 3),
)

ENERGY_B: Plan = (
    ("solar_farm", 26, 4),
    ("solar_farm", 27, 4),
    ("solar_farm", 28, 4),
    ("solar_farm", 29, 4),
    ("battery", 30, 4),
    ("battery", 31, 4),
)

ENERGY_C: Plan = (
    ("solar_farm", 26, 5),
    ("solar_farm", 27, 5),
    ("solar_farm", 28, 5),
    ("solar_farm", 29, 5),
)

ENERGY_D: Plan = (
    ("solar_farm", 26, 6),
    ("solar_farm", 27, 6),
    ("solar_farm", 28, 6),
    ("solar_farm", 29, 6),
    ("battery", 30, 5),
    ("battery", 31, 5),
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


ROW_20: Plan = _support_row(20, 21, commercial_xs=(23, 25, 27, 29, 31), park_xs=(24, 26, 28, 30))
ROW_23: Plan = _support_row(23, 24, commercial_xs=(23, 25, 27, 29, 31), park_xs=(24, 26, 28, 30))
ROW_26: Plan = _support_row(26, 27, commercial_xs=(23, 25, 27, 29, 31), park_xs=(24, 26, 28, 30))

ROW_29: Plan = (
    *(("house", x, 29) for x in range(23, 32)),
    ("park", 25, 30),
    ("park", 28, 30),
    ("park", 31, 30),
    ("commercial", 25, 18),
    ("commercial", 28, 18),
    ("commercial", 31, 18),
)

SAFETY_STAGES: tuple[Stage, ...] = (
    Stage("flex core", FLEX_CORE, reserve=85_000, min_day=7),
    Stage("core a", CORE_A, reserve=95_000, min_day=25),
    Stage("core b", CORE_B, reserve=115_000, min_day=70),
    Stage("energy a", ENERGY_A, reserve=120_000, min_day=120),
    Stage("road grid", ROAD_GRID, reserve=140_000, min_day=150),
    Stage("row 20", ROW_20, reserve=150_000, min_day=170),
    Stage("energy b", ENERGY_B, reserve=170_000, min_day=240),
    Stage("row 23", ROW_23, reserve=190_000, min_day=280),
    Stage("row 26", ROW_26, reserve=220_000, min_day=430),
    Stage("energy c", ENERGY_C, reserve=230_000, min_day=500),
    Stage("row 29", ROW_29, reserve=260_000, min_day=650),
    Stage("energy d", ENERGY_D, reserve=300_000, min_day=720),
)

AGGRESSIVE_STAGES: tuple[Stage, ...] = (
    Stage("flex core", FLEX_CORE_AGGRESSIVE, reserve=35_000, min_day=7),
    Stage("core a", CORE_A, reserve=45_000, min_day=20),
    Stage("core b", CORE_B, reserve=55_000, min_day=55),
    Stage("energy a", ENERGY_A, reserve=80_000, min_day=95),
    Stage("road grid", ROAD_GRID, reserve=75_000, min_day=120),
    Stage("row 20", ROW_20, reserve=80_000, min_day=150),
    Stage("energy b", ENERGY_B, reserve=95_000, min_day=210),
    Stage("row 23", ROW_23, reserve=100_000, min_day=240),
    Stage("row 26", ROW_26, reserve=115_000, min_day=330),
    Stage("energy c", ENERGY_C, reserve=130_000, min_day=390),
    Stage("row 29", ROW_29, reserve=115_000, min_day=520),
    Stage("energy d", ENERGY_D, reserve=140_000, min_day=720),
)

POLICIES: dict[str, PolicyConfig] = {
    "safety_envelope": PolicyConfig(
        name="safety_envelope",
        bootstrap=BOOTSTRAP_CORE,
        stages=SAFETY_STAGES,
        bootstrap_buffer=35_000.0,
        restore_buffer=12_000.0,
    ),
    "aggressive_safety": PolicyConfig(
        name="aggressive_safety",
        bootstrap=BOOTSTRAP_AGGRESSIVE,
        stages=AGGRESSIVE_STAGES,
        bootstrap_buffer=35_000.0,
        restore_buffer=12_000.0,
    ),
}


class SafetyEnvelopeAgent(BaseAgent):
    """State-feedback policy for solvency-first population growth."""

    MAX_SHED_SITES = 10
    MIN_COMMERCIAL_TO_KEEP = 4
    OIL_SURVEY_SIZE = 8
    MAX_OIL_SURVEYS = 2

    def __init__(self, api: ApiClient, *, seed: int | None = None) -> None:
        super().__init__(api, seed=seed)
        policy_id = os.environ.get("EAGE_POLICY_ID", "aggressive_safety")
        self.policy = POLICIES.get(policy_id, POLICIES["aggressive_safety"])
        self._bootstrapped = False
        self._stage_index = 0
        self._backup_built = False
        self._oil_attempted = False
        self._shed_sites: list[tuple[int, int]] = []
        self._catalog_by_type: dict[str, dict[str, Any]] | None = None
        self._oil_estimates: dict[tuple[int, int, int], tuple[float, float]] = {}

    def next_step_days(self, state: dict[str, Any]) -> int:
        return 1

    def act(self, state: dict[str, Any]) -> None:
        if not self._bootstrapped:
            self._build_plan(self.policy.bootstrap, min_buffer=self.policy.bootstrap_buffer)
            self._bootstrapped = True
            return

        if self._has_outage_risk(state):
            if self._shed_until_safe(state):
                return
            if self._build_emergency_power(state):
                return

        if self._shed_sites and self._restore_one_if_safe(state):
            return

        if self._should_build_backup_coal(state) and self._build_plan(
            BACKUP_COAL,
            min_buffer=self._cash_reserve(state) + 80_000,
        ):
            self._backup_built = True
            return

        if self._build_next_stage_if_safe(state):
            return

        if self._try_late_oil(state):
            return

    def _build_next_stage_if_safe(self, state: dict[str, Any]) -> bool:
        while self._stage_index < len(self.policy.stages):
            stage = self.policy.stages[self._stage_index]
            if self._plan_already_done(stage.plan, state):
                self._stage_index += 1
                continue
            break
        if self._stage_index >= len(self.policy.stages):
            return False

        stage = self.policy.stages[self._stage_index]
        day = int(state["day"])
        if day < stage.min_day:
            return False
        if self._has_hard_event_risk(state):
            return False
        if self._has_outage_risk(state):
            return False

        reserve = max(stage.reserve, self._cash_reserve(state))
        if not self._build_plan(stage.plan, min_buffer=reserve):
            return False
        self._stage_index += 1
        return True

    def _should_build_backup_coal(self, state: dict[str, Any]) -> bool:
        if self._backup_built or self._has_hard_event_risk(state):
            return False
        if int(state["day"]) < 180:
            return False
        if self._has_outage_risk(state):
            return False
        coal_count = self._count_tiles(state, "coal_plant")
        if coal_count >= 2:
            self._backup_built = True
            return False
        pop = int(state["population"])
        commercial_count = self._count_tiles(state, "commercial")
        return pop >= 150 or commercial_count >= 9

    def _build_emergency_power(self, state: dict[str, Any]) -> bool:
        if float(state["treasury"]) < self._cash_reserve(state) + 85_000:
            return False
        solar_count = self._count_tiles(state, "solar_farm")
        battery_count = self._count_tiles(state, "battery")
        if battery_count < max(2, solar_count // 4):
            emergency: Plan = (("battery", 23, 16 + battery_count),)
        elif solar_count < 12:
            row = 3 + max(0, (solar_count - 4) // 4)
            emergency = tuple(("solar_farm", x, row) for x in range(26, 30))
        else:
            return False
        return self._build_plan(emergency, min_buffer=self._cash_reserve(state))

    def _build_plan(self, plan: Plan, *, min_buffer: float) -> bool:
        for tile_type, x, y in plan:
            latest = self.api.state()
            if self._tile_at(latest, x, y) is not None:
                continue
            capex = self._tile_capex(tile_type)
            if float(latest["treasury"]) < capex + min_buffer:
                return False
            result = self.api.build(tile_type, x, y)
            if result.get("ok"):
                continue
            if result.get("error") == "tile_occupied":
                continue
            return False
        return True

    def _shed_until_safe(self, state: dict[str, Any]) -> bool:
        did_shed = False
        latest = state
        while self._has_outage_risk(latest) and len(self._shed_sites) < self.MAX_SHED_SITES:
            tile = self._lowest_value_commercial(latest)
            if tile is None:
                break
            x, y = int(tile["x"]), int(tile["y"])
            result = self.api.demolish(x, y)
            if not result.get("ok"):
                break
            if (x, y) not in self._shed_sites:
                self._shed_sites.append((x, y))
            did_shed = True
            latest = self.api.state()
        return did_shed

    def _restore_one_if_safe(self, state: dict[str, Any]) -> bool:
        if self._has_hard_event_risk(state):
            return False
        if self._has_outage_risk(state):
            return False
        capex = self._tile_capex("commercial")
        if float(state["treasury"]) < self.policy.restore_buffer + capex:
            return False
        x, y = self._shed_sites[0]
        if self._tile_at(state, x, y) is not None:
            self._shed_sites.pop(0)
            return True
        result = self.api.build("commercial", x, y)
        if not result.get("ok"):
            return False
        latest = self.api.state()
        if self._has_outage_risk(latest):
            undo = self.api.demolish(x, y)
            if undo.get("ok") and (x, y) not in self._shed_sites:
                self._shed_sites.insert(0, (x, y))
            return bool(undo.get("ok"))
        self._shed_sites.pop(0)
        return True

    def _try_late_oil(self, state: dict[str, Any]) -> bool:
        if self._oil_attempted:
            return False
        if int(state["day"]) < 730:
            return False
        if float(state.get("crude_price_usd_per_bbl", 40.0)) < 35.0:
            return False
        if any(e.get("type") == "crude_collapse" for e in state.get("active_events", [])):
            return False
        if float(state["treasury"]) < max(650_000.0, self._cash_reserve(state) + 300_000.0):
            return False

        self._oil_attempted = True
        surveyed = 0
        latest = state
        for x, y, size in self._oil_survey_windows(latest):
            if surveyed >= self.MAX_OIL_SURVEYS:
                break
            if float(latest["treasury"]) < self.api.survey_cost_preview(size) + self._cash_reserve(latest):
                break
            result = self.api.survey(x, y, size)
            if not result.get("ok"):
                break
            surveyed += 1
            for voxel in result["result"]["voxels"]:
                key = (int(voxel["x"]), int(voxel["y"]), int(voxel["z"]))
                self._oil_estimates[key] = (
                    float(voxel["oil_estimate_bbl"]),
                    float(voxel["perm_estimate_md"]),
                )
            latest = self.api.state()

        target = self._best_oil_target(self.api.state())
        if target is None:
            return surveyed > 0
        _value, rate, x, y, z = target
        capex = 50_000.0 * (1.0 + (z / int(state["config"]["world_d"])) ** 2)
        latest = self.api.state()
        if float(latest["treasury"]) < capex + self._cash_reserve(latest) + 100_000:
            return surveyed > 0
        result = self.api.drill(x, y, z, "production")
        if result.get("ok"):
            self.api.control_well(str(result["result"]["id"]), min(200.0, rate))
        return True

    def _oil_survey_windows(self, state: dict[str, Any]) -> tuple[tuple[int, int, int], ...]:
        size = self.OIL_SURVEY_SIZE
        half = size // 2
        world_w = int(state["config"]["world_w"])
        world_h = int(state["config"]["world_h"])
        occupied = {(int(t["x"]), int(t["y"])) for t in state["tiles"]}
        scored: list[tuple[int, int, int, int]] = []
        for y in range(half, world_h, size):
            for x in range(half, world_w, size):
                x0 = max(0, x - half)
                y0 = max(0, y - half)
                x1 = min(world_w, x0 + size)
                y1 = min(world_h, y0 + size)
                cells = {(vx, vy) for vx in range(x0, x1) for vy in range(y0, y1)}
                overlap = len(cells & occupied)
                distance = max(abs(x - 16), abs(y - 16))
                scored.append((overlap, -distance, x, y))
        scored.sort()
        return tuple((x, y, size) for _overlap, _dist, x, y in scored)

    def _best_oil_target(self, state: dict[str, Any]) -> tuple[float, float, int, int, int] | None:
        world_w = int(state["config"]["world_w"])
        world_h = int(state["config"]["world_h"])
        world_d = int(state["config"]["world_d"])
        remaining_days = max(0, int(state["config"]["active_game_days"]) - int(state["day"]))
        crude_price = float(state.get("crude_price_usd_per_bbl", 40.0))
        occupied = {
            (int(tile["x"]), int(tile["y"]))
            for tile in state["tiles"]
        } | {
            (int(well["x"]), int(well["y"]))
            for well in state.get("wells", [])
        }
        best: tuple[float, float, int, int, int] | None = None
        for (x, y, z), (_oil_est, _perm_est) in self._oil_estimates.items():
            if (x, y) in occupied:
                continue
            pool = self._known_pool(x, y, z, world_w, world_h, world_d)
            if pool is None:
                continue
            pool_oil, mean_perm = pool
            if pool_oil <= 0.0 or mean_perm <= 0.0:
                continue
            rate = min(200.0, 200.0 * mean_perm / 500.0)
            if rate < 35.0:
                continue
            capex = 50_000.0 * (1.0 + (z / world_d) ** 2)
            net_value = min(pool_oil, rate * remaining_days) * crude_price - capex
            if net_value < 120_000.0:
                continue
            candidate = (net_value, rate, x, y, z)
            if best is None or candidate > best:
                best = candidate
        return best

    def _known_pool(
        self,
        x: int,
        y: int,
        z: int,
        world_w: int,
        world_h: int,
        world_d: int,
    ) -> tuple[float, float] | None:
        oil_total = 0.0
        perm_total = 0.0
        n = 0
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    vx, vy, vz = x + dx, y + dy, z + dz
                    if not (0 <= vx < world_w and 0 <= vy < world_h and 0 <= vz < world_d):
                        continue
                    key = (vx, vy, vz)
                    if key not in self._oil_estimates:
                        return None
                    oil, perm = self._oil_estimates[key]
                    oil_total += oil
                    perm_total += perm
                    n += 1
        if n == 0:
            return None
        return oil_total, perm_total / n

    def _has_outage_risk(self, state: dict[str, Any]) -> bool:
        preview = state.get("next_24h_preview") or {}
        states = [str(s) for s in preview.get("balance_state_by_hour", [])]
        return any(s in {"brownout", "blackout"} for s in states)

    def _has_hard_event_risk(self, state: dict[str, Any]) -> bool:
        active = state.get("active_events", [])
        risky = {"plant_failure", "fuel_price_shock", "demand_surprise", "heatwave"}
        return any(event.get("type") in risky for event in active)

    def _cash_reserve(self, state: dict[str, Any]) -> float:
        day = int(state["day"])
        if day < 120:
            reserve = 90_000.0
        elif day < 365:
            reserve = 120_000.0
        elif day < 730:
            reserve = 160_000.0
        else:
            reserve = 220_000.0
        if self._has_hard_event_risk(state):
            reserve += 80_000.0
        if self._has_outage_risk(state):
            reserve += 60_000.0
        return reserve

    def _lowest_value_commercial(self, state: dict[str, Any]) -> dict[str, Any] | None:
        candidates = [
            tile
            for tile in state["tiles"]
            if tile["type"] == "commercial"
            and int(tile.get("staffed_jobs", 0)) > 0
            and (int(tile["x"]), int(tile["y"])) not in self._shed_sites
        ]
        if len(candidates) <= self._min_commercial_to_keep(state):
            return None
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

    def _plan_already_done(self, plan: Plan, state: dict[str, Any]) -> bool:
        occupied = {(int(t["x"]), int(t["y"])): t["type"] for t in state["tiles"]}
        return all(occupied.get((x, y)) == tile_type for tile_type, x, y in plan)

    def _tile_at(self, state: dict[str, Any], x: int, y: int) -> dict[str, Any] | None:
        return next(
            (tile for tile in state["tiles"] if int(tile["x"]) == x and int(tile["y"]) == y),
            None,
        )

    def _count_tiles(self, state: dict[str, Any], tile_type: str) -> int:
        return sum(1 for tile in state["tiles"] if tile["type"] == tile_type)

    def _min_commercial_to_keep(self, state: dict[str, Any]) -> int:
        if any(event.get("type") == "plant_failure" for event in state.get("active_events", [])):
            return 2
        return self.MIN_COMMERCIAL_TO_KEEP

    def _tile_capex(self, tile_type: str) -> float:
        if self._catalog_by_type is None:
            catalog = self.api.catalog()
            self._catalog_by_type = {entry["tile_type"]: entry for entry in catalog["tiles"]}
        return float(self._catalog_by_type[tile_type]["capex"])


Agent = SafetyEnvelopeAgent
