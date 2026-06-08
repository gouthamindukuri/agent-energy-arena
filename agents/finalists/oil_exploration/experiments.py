"""Research agents layered on top of the V1 deterministic policy.

The oil variants intentionally use only legal API information:

* pay for `/survey`;
* rank only voxels returned by survey results;
* drill through `/drill`;
* control wells through `/control/well`.

No hidden reservoir access is used here.
"""

from __future__ import annotations

from typing import Any

from .v1_core import V1Agent


class PostV1Agent(V1Agent):
    """Run V1 first, then allow a subclass experiment when V1 is idle."""

    def act(self, state: dict[str, Any]) -> None:
        before = (
            self._bootstrapped,
            self._first_growth_built,
            self._second_growth_built,
            len(self._shed_sites),
        )
        super().act(state)
        after = (
            self._bootstrapped,
            self._first_growth_built,
            self._second_growth_built,
            len(self._shed_sites),
        )
        if after != before:
            return
        latest = self.api.state()
        self._act_after_v1(latest)

    def _act_after_v1(self, state: dict[str, Any]) -> None:
        return


class LegalOilAgent(PostV1Agent):
    """Survey a fixed legal pattern and drill the best revealed raw-oil well."""

    SURVEY_PLAN: tuple[tuple[int, int, int], ...] = ()
    TREASURY_FLOOR: float = 450_000.0
    MIN_RATE_BBL_DAY: float = 50.0
    MIN_NET_VALUE: float = 50_000.0
    ASSUMED_CRUDE_PRICE: float = 40.0
    MAX_VALUE_DAYS: int = 365
    WAIT_FOR_SECOND_GROWTH: bool = True

    def __init__(self, api, *, seed: int | None = None) -> None:
        super().__init__(api, seed=seed)
        self._oil_attempted = False
        self._estimates: dict[tuple[int, int, int], tuple[float, float]] = {}

    def _act_after_v1(self, state: dict[str, Any]) -> None:
        if self._oil_attempted:
            return
        if self.WAIT_FOR_SECOND_GROWTH and not self._second_growth_built:
            return
        if self._crude_collapse_active(state):
            return
        if float(state["treasury"]) < self.TREASURY_FLOOR:
            return
        self._oil_attempted = True
        self._run_surveys()
        self._drill_best_revealed_target(state)

    def _run_surveys(self) -> None:
        for x, y, size in self.SURVEY_PLAN:
            result = self.api.survey(x, y, size)
            if not result.get("ok"):
                return
            for voxel in result["result"]["voxels"]:
                key = (int(voxel["x"]), int(voxel["y"]), int(voxel["z"]))
                self._estimates[key] = (
                    float(voxel["oil_estimate_bbl"]),
                    float(voxel["perm_estimate_md"]),
                )

    def _drill_best_revealed_target(self, state: dict[str, Any]) -> None:
        target = self._best_target(state)
        if target is None:
            return
        _value, rate, x, y, z = target
        if rate < self.MIN_RATE_BBL_DAY:
            return
        result = self.api.drill(x, y, z, "production")
        if result.get("ok"):
            self.api.control_well(str(result["result"]["id"]), 200.0)

    def _best_target(self, state: dict[str, Any]) -> tuple[float, float, int, int, int] | None:
        world_w = int(state["config"]["world_w"])
        world_h = int(state["config"]["world_h"])
        world_d = int(state["config"]["world_d"])
        occupied = {
            (int(tile["x"]), int(tile["y"]))
            for tile in state["tiles"]
        } | {
            (int(well["x"]), int(well["y"]))
            for well in state.get("wells", [])
        }
        best: tuple[float, float, int, int, int] | None = None
        remaining_days = max(0, 730 - int(state["day"]))
        value_days = min(self.MAX_VALUE_DAYS, remaining_days)

        for (x, y, z), (oil_est, _perm_est) in self._estimates.items():
            if oil_est <= 0.0:
                continue
            if (x, y) in occupied:
                continue
            pool = self._known_pool(x, y, z, world_w, world_h, world_d)
            if pool is None:
                continue
            pool_oil, mean_perm = pool
            if pool_oil <= 0.0 or mean_perm <= 0.0:
                continue
            rate = min(200.0, 200.0 * mean_perm / 500.0)
            capex = 50_000.0 * (1.0 + (z / world_d) ** 2)
            net_value = rate * self.ASSUMED_CRUDE_PRICE * value_days - capex
            if net_value < self.MIN_NET_VALUE:
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
        n_positions = 0
        oil_total = 0.0
        perm_total = 0.0
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    vx, vy, vz = x + dx, y + dy, z + dz
                    if not (0 <= vx < world_w and 0 <= vy < world_h and 0 <= vz < world_d):
                        continue
                    key = (vx, vy, vz)
                    if key not in self._estimates:
                        return None
                    oil_est, perm_est = self._estimates[key]
                    oil_total += oil_est
                    perm_total += perm_est
                    n_positions += 1
        if n_positions == 0:
            return None
        return oil_total, perm_total / n_positions

    def _crude_collapse_active(self, state: dict[str, Any]) -> bool:
        return any(event.get("type") == "crude_collapse" for event in state.get("active_events", []))


class OilOneS8Agent(LegalOilAgent):
    SURVEY_PLAN = ((8, 28, 8),)
    TREASURY_FLOOR = 450_000.0
    MIN_RATE_BBL_DAY = 45.0
    MIN_NET_VALUE = 40_000.0


class OilCheapS4Agent(LegalOilAgent):
    SURVEY_PLAN = (
        (10, 26, 4),
        (30, 26, 4),
        (10, 30, 4),
        (6, 30, 4),
        (30, 14, 4),
        (30, 6, 4),
        (10, 22, 4),
        (6, 22, 4),
    )
    TREASURY_FLOOR = 450_000.0
    MIN_RATE_BBL_DAY = 45.0
    MIN_NET_VALUE = 40_000.0


class OilQuadS8Agent(LegalOilAgent):
    SURVEY_PLAN = (
        (8, 8, 8),
        (24, 8, 8),
        (8, 24, 8),
        (24, 24, 8),
    )
    TREASURY_FLOOR = 600_000.0
    MIN_RATE_BBL_DAY = 45.0
    MIN_NET_VALUE = 80_000.0


class OilS16Agent(LegalOilAgent):
    SURVEY_PLAN = ((8, 24, 16),)
    TREASURY_FLOOR = 650_000.0
    MIN_RATE_BBL_DAY = 55.0
    MIN_NET_VALUE = 100_000.0


class GasBackupAgent(PostV1Agent):
    """Add a refinery-supplied gas peaker after V1 is cash-rich."""

    TREASURY_FLOOR: float = 650_000.0
    BACKUP_PLAN = (
        ("refinery", 10, 17),
        ("pipeline", 10, 18),
        ("pipeline", 10, 19),
        ("pipeline", 10, 20),
        ("pipeline", 10, 21),
        ("gas_peaker", 10, 22),
    )

    def __init__(self, api, *, seed: int | None = None) -> None:
        super().__init__(api, seed=seed)
        self._gas_backup_built = False

    def _act_after_v1(self, state: dict[str, Any]) -> None:
        if self._gas_backup_built:
            return
        if not self._second_growth_built:
            return
        if float(state["treasury"]) < self.TREASURY_FLOOR:
            return
        self._build_plan(self.BACKUP_PLAN, "gas backup")
        self._gas_backup_built = True

    def _shed_commercial_load(self, state: dict[str, Any]) -> None:
        staffed = [
            tile
            for tile in state["tiles"]
            if tile["type"] == "commercial" and int(tile.get("staffed_jobs", 0)) > 0
        ]
        target = 4 if self._gas_backup_built else 2
        count_to_shed = max(0, len(staffed) - target) - len(self._shed_sites)
        staffed.sort(key=lambda tile: (-int(tile["staffed_jobs"]), str(tile["id"])))
        for tile in staffed[:count_to_shed]:
            result = self.api.demolish(int(tile["x"]), int(tile["y"]))
            if result.get("ok"):
                self._shed_sites.append((int(tile["x"]), int(tile["y"])))


class ExtraGrowthAgent(PostV1Agent):
    """Add compact matched housing/jobs/park bundles after V1 expansion."""

    PLANS: tuple[tuple[float, tuple[tuple[str, int, int], ...]], ...] = ()

    def __init__(self, api, *, seed: int | None = None) -> None:
        super().__init__(api, seed=seed)
        self._growth_index = 0

    def _act_after_v1(self, state: dict[str, Any]) -> None:
        if not self._second_growth_built:
            return
        if self._growth_index >= len(self.PLANS):
            return
        floor, plan = self.PLANS[self._growth_index]
        if float(state["treasury"]) < floor:
            return
        self._build_plan(plan, f"extra growth {self._growth_index + 1}")
        self._growth_index += 1


MICRO_BALANCED_PLAN = (
    ("road", 22, 17),
    ("house", 23, 17),
    ("commercial", 22, 18),
    ("park", 23, 18),
)

HOUSE_SURPLUS_PLAN = (
    ("road", 22, 17),
    ("house", 23, 17),
    ("park", 23, 18),
)

SOUTH_SMALL_PLAN = (
    ("road", 22, 17),
    ("road", 22, 18),
    ("road", 22, 19),
    ("road", 23, 19),
    ("road", 24, 19),
    ("road", 25, 19),
    ("house", 22, 20),
    ("house", 23, 20),
    ("house", 24, 20),
    ("house", 25, 20),
    ("commercial", 23, 18),
    ("commercial", 25, 18),
    ("commercial", 26, 19),
    ("park", 22, 21),
    ("park", 25, 21),
)

SOUTH_SECOND_SMALL_PLAN = (
    ("road", 26, 19),
    ("road", 27, 19),
    ("road", 28, 19),
    ("road", 29, 19),
    ("house", 26, 20),
    ("house", 27, 20),
    ("house", 28, 20),
    ("house", 29, 20),
    ("commercial", 27, 18),
    ("commercial", 29, 18),
    ("park", 27, 21),
)


class GrowthMicroAgent(ExtraGrowthAgent):
    PLANS = ((40_000.0, MICRO_BALANCED_PLAN),)


class GrowthMicro500Agent(ExtraGrowthAgent):
    PLANS = ((500_000.0, MICRO_BALANCED_PLAN),)


class GrowthMicro650Agent(ExtraGrowthAgent):
    PLANS = ((650_000.0, MICRO_BALANCED_PLAN),)


class GrowthHouseAgent(ExtraGrowthAgent):
    PLANS = ((40_000.0, HOUSE_SURPLUS_PLAN),)


class GrowthHouse500Agent(ExtraGrowthAgent):
    PLANS = ((500_000.0, HOUSE_SURPLUS_PLAN),)


class GrowthHouse650Agent(ExtraGrowthAgent):
    PLANS = ((650_000.0, HOUSE_SURPLUS_PLAN),)


class GrowthSmall500Agent(ExtraGrowthAgent):
    PLANS = ((500_000.0, SOUTH_SMALL_PLAN),)


class GrowthSmall650Agent(ExtraGrowthAgent):
    PLANS = ((650_000.0, SOUTH_SMALL_PLAN),)


class GrowthStagedAgent(ExtraGrowthAgent):
    PLANS = (
        (40_000.0, MICRO_BALANCED_PLAN),
        (650_000.0, SOUTH_SECOND_SMALL_PLAN),
    )
