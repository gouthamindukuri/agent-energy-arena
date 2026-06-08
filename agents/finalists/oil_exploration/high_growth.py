"""High-population deterministic variants.

These keep the stable V1 opening and test larger staged city growth.
"""

from __future__ import annotations

from typing import Any

from .experiments import HOUSE_SURPLUS_PLAN, ExtraGrowthAgent

ROAD_GRID_PLAN = (
    # Connect the existing V1/house-surplus road at (22, 17) to four new rows.
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


ROW_20_21_PLAN = (
    *(("house", x, 20) for x in range(23, 32)),
    ("commercial", 23, 21),
    ("commercial", 24, 21),
    ("park", 25, 21),
    ("commercial", 26, 21),
    ("commercial", 27, 21),
    ("park", 28, 21),
    ("commercial", 29, 21),
    ("commercial", 30, 21),
    ("park", 31, 21),
)


ROW_23_24_PLAN = (
    *(("house", x, 23) for x in range(23, 32)),
    ("commercial", 23, 24),
    ("commercial", 24, 24),
    ("park", 25, 24),
    ("commercial", 26, 24),
    ("commercial", 27, 24),
    ("park", 28, 24),
    ("commercial", 29, 24),
    ("commercial", 30, 24),
    ("park", 31, 24),
)


ROW_26_27_PLAN = (
    *(("house", x, 26) for x in range(23, 32)),
    ("commercial", 23, 27),
    ("commercial", 24, 27),
    ("park", 25, 27),
    ("commercial", 26, 27),
    ("commercial", 27, 27),
    ("park", 28, 27),
    ("commercial", 29, 27),
    ("commercial", 30, 27),
    ("park", 31, 27),
)


ROW_29_EDGE_PLAN = (
    *(("house", x, 29) for x in range(23, 32)),
    ("park", 25, 30),
    ("park", 28, 30),
    ("park", 31, 30),
    ("commercial", 25, 18),
    ("commercial", 28, 18),
    ("commercial", 31, 18),
)


ENERGY_STAGE_1_PLAN = (
    ("solar_farm", 26, 3),
    ("solar_farm", 27, 3),
    ("solar_farm", 28, 3),
    ("solar_farm", 29, 3),
    ("battery", 30, 3),
    ("battery", 31, 3),
)


ENERGY_STAGE_2_PLAN = (
    ("solar_farm", 26, 4),
    ("solar_farm", 27, 4),
    ("solar_farm", 28, 4),
    ("solar_farm", 29, 4),
    ("battery", 30, 4),
    ("battery", 31, 4),
)


SOLAR_STAGE_1_PLAN = (
    ("solar_farm", 26, 3),
    ("solar_farm", 27, 3),
    ("solar_farm", 28, 3),
    ("solar_farm", 29, 3),
)


SOLAR_STAGE_2_PLAN = (
    ("solar_farm", 26, 4),
    ("solar_farm", 27, 4),
    ("solar_farm", 28, 4),
    ("solar_farm", 29, 4),
)


SOLAR_STAGE_3_PLAN = (
    ("solar_farm", 26, 5),
    ("solar_farm", 27, 5),
    ("solar_farm", 28, 5),
    ("solar_farm", 29, 5),
)


BATTERY_STAGE_1_PLAN = (
    ("battery", 30, 3),
    ("battery", 31, 3),
)


BATTERY_STAGE_2_PLAN = (
    ("battery", 30, 4),
    ("battery", 31, 4),
)


BATTERY_STAGE_3_PLAN = (
    ("battery", 30, 5),
    ("battery", 31, 5),
)


BATTERY_STAGE_4_PLAN = (
    ("battery", 30, 6),
    ("battery", 31, 6),
)


COAL_BACKUP_PLAN = (
    ("road", 9, 15),
    ("road", 8, 15),
    ("coal_plant", 8, 14),
)


GAS_BACKUP_PLAN = (
    ("refinery", 10, 17),
    ("pipeline", 10, 18),
    ("pipeline", 10, 19),
    ("pipeline", 10, 20),
    ("pipeline", 10, 21),
    ("gas_peaker", 10, 22),
)


class HighGrowthNoShedAgent(ExtraGrowthAgent):
    """Push toward 400+ population while preserving the V1 safety opening."""

    PLANS = (
        (40_000.0, HOUSE_SURPLUS_PLAN),
        (220_000.0, ROAD_GRID_PLAN + ROW_20_21_PLAN),
        (220_000.0, ROW_23_24_PLAN),
        (400_000.0, ENERGY_STAGE_1_PLAN),
        (250_000.0, ROW_26_27_PLAN),
        (250_000.0, ROW_29_EDGE_PLAN),
        (500_000.0, ENERGY_STAGE_2_PLAN),
    )

    def _shed_commercial_load(self, state: dict[str, Any]) -> None:
        # At high population, demolishing most commercials destroys the jobs
        # base and costs too much to rebuild repeatedly. This variant relies on
        # added storage/solar and accepts rare outage penalties instead.
        return


class HighGrowthSolarFirstNoShedAgent(ExtraGrowthAgent):
    """Stage peak supply ahead of demand growth."""

    PLANS = (
        (40_000.0, HOUSE_SURPLUS_PLAN),
        (220_000.0, ROAD_GRID_PLAN + ROW_20_21_PLAN),
        (220_000.0, SOLAR_STAGE_1_PLAN),
        (260_000.0, ROW_23_24_PLAN),
        (300_000.0, SOLAR_STAGE_2_PLAN),
        (340_000.0, ROW_26_27_PLAN),
        (420_000.0, SOLAR_STAGE_3_PLAN),
        (420_000.0, ROW_29_EDGE_PLAN),
    )

    def _shed_commercial_load(self, state: dict[str, Any]) -> None:
        return


class HighGrowthSolarFirstBufferedAgent(ExtraGrowthAgent):
    """Slower high-growth plan with larger cash buffers between stages."""

    PLANS = (
        (40_000.0, HOUSE_SURPLUS_PLAN),
        (250_000.0, ROAD_GRID_PLAN + ROW_20_21_PLAN),
        (280_000.0, SOLAR_STAGE_1_PLAN),
        (350_000.0, ROW_23_24_PLAN),
        (400_000.0, SOLAR_STAGE_2_PLAN),
        (500_000.0, ROW_26_27_PLAN),
        (600_000.0, SOLAR_STAGE_3_PLAN),
        (650_000.0, ROW_29_EDGE_PLAN),
    )

    def _shed_commercial_load(self, state: dict[str, Any]) -> None:
        return


class HighGrowthCoalBackupAgent(ExtraGrowthAgent):
    """Use a second coal plant to solve morning ramp failures, then grow."""

    PLANS = (
        (40_000.0, HOUSE_SURPLUS_PLAN),
        (220_000.0, ROAD_GRID_PLAN + ROW_20_21_PLAN),
        (260_000.0, COAL_BACKUP_PLAN),
        (260_000.0, SOLAR_STAGE_1_PLAN),
        (320_000.0, ROW_23_24_PLAN),
        (360_000.0, SOLAR_STAGE_2_PLAN),
        (450_000.0, ROW_26_27_PLAN),
        (520_000.0, SOLAR_STAGE_3_PLAN),
        (580_000.0, ROW_29_EDGE_PLAN),
    )

    def _shed_commercial_load(self, state: dict[str, Any]) -> None:
        return


class HighGrowthBatteryFirstAgent(ExtraGrowthAgent):
    """Add storage before extra solar/growth to avoid shoulder-hour outages."""

    PLANS = (
        (40_000.0, HOUSE_SURPLUS_PLAN),
        (220_000.0, ROAD_GRID_PLAN + ROW_20_21_PLAN),
        (200_000.0, BATTERY_STAGE_1_PLAN),
        (220_000.0, SOLAR_STAGE_1_PLAN),
        (300_000.0, ROW_23_24_PLAN),
        (280_000.0, BATTERY_STAGE_2_PLAN),
        (340_000.0, SOLAR_STAGE_2_PLAN),
        (450_000.0, ROW_26_27_PLAN),
        (520_000.0, SOLAR_STAGE_3_PLAN),
        (580_000.0, ROW_29_EDGE_PLAN),
    )

    def _shed_commercial_load(self, state: dict[str, Any]) -> None:
        return


class HighGrowthBatterySolarEarlyAgent(ExtraGrowthAgent):
    """Battery first, then accept a thinner cash buffer to buy solar in time."""

    PLANS = (
        (40_000.0, HOUSE_SURPLUS_PLAN),
        (220_000.0, ROAD_GRID_PLAN + ROW_20_21_PLAN),
        (200_000.0, BATTERY_STAGE_1_PLAN),
        (180_000.0, SOLAR_STAGE_1_PLAN),
        (300_000.0, ROW_23_24_PLAN),
        (280_000.0, BATTERY_STAGE_2_PLAN),
        (340_000.0, SOLAR_STAGE_2_PLAN),
        (450_000.0, ROW_26_27_PLAN),
        (520_000.0, SOLAR_STAGE_3_PLAN),
        (580_000.0, ROW_29_EDGE_PLAN),
    )

    def _shed_commercial_load(self, state: dict[str, Any]) -> None:
        return


class HighGrowthAdaptiveShedAgent(ExtraGrowthAgent):
    """Use preview-driven temporary commercial shedding to prevent penalty spirals."""

    MAX_SHED_SITES = 8
    RESTORE_TREASURY_FLOOR = 120_000.0
    PLANS = (
        (40_000.0, HOUSE_SURPLUS_PLAN),
        (220_000.0, ROAD_GRID_PLAN + ROW_20_21_PLAN),
        (200_000.0, BATTERY_STAGE_1_PLAN),
        (220_000.0, SOLAR_STAGE_1_PLAN),
        (320_000.0, ROW_23_24_PLAN),
        (300_000.0, BATTERY_STAGE_2_PLAN),
        (360_000.0, SOLAR_STAGE_2_PLAN),
        (460_000.0, ROW_26_27_PLAN),
        (540_000.0, SOLAR_STAGE_3_PLAN),
        (620_000.0, ROW_29_EDGE_PLAN),
    )

    def act(self, state: dict[str, Any]) -> None:
        if self._second_growth_built:
            latest = self.api.state()
            if self._preview_has_outage(latest):
                if self._shed_until_preview_ok(latest):
                    return
            elif self._shed_sites:
                self._restore_one_if_safe(latest)
                return
        super().act(state)

    def _shed_commercial_load(self, state: dict[str, Any]) -> None:
        self._shed_until_preview_ok(state)

    def _preview_has_outage(self, state: dict[str, Any]) -> bool:
        preview = state.get("next_24h_preview") or {}
        return any(
            mode in {"brownout", "blackout"}
            for mode in preview.get("balance_state_by_hour", [])
        )

    def _shed_until_preview_ok(self, state: dict[str, Any]) -> bool:
        did_shed = False
        latest = state
        while self._preview_has_outage(latest) and len(self._shed_sites) < self.MAX_SHED_SITES:
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

    def _restore_one_if_safe(self, state: dict[str, Any]) -> None:
        if float(state["treasury"]) < self.RESTORE_TREASURY_FLOOR:
            return
        if any(event.get("type") in {"heatwave", "demand_surprise"} for event in state.get("active_events", [])):
            return
        x, y = self._shed_sites[0]
        result = self.api.build("commercial", x, y)
        if result.get("ok"):
            self._shed_sites.pop(0)


class OilFundedGrowthAgent(HighGrowthAdaptiveShedAgent):
    """Drill legal raw-oil production before later job-heavy growth rows."""

    OIL_SURVEY_PLAN = ((8, 28, 8),)
    OIL_TREASURY_FLOOR = 300_000.0
    MIN_POST_OIL_TREASURY = 70_000.0
    MAX_OIL_WELLS = 1
    MIN_CRUDE_PRICE = 35.0
    MIN_RATE_BBL_DAY = 35.0
    MIN_NET_VALUE = 150_000.0

    def __init__(self, api, *, seed: int | None = None) -> None:
        super().__init__(api, seed=seed)
        self._oil_attempted = False
        self._estimates: dict[tuple[int, int, int], tuple[float, float]] = {}

    def _act_after_v1(self, state: dict[str, Any]) -> None:
        if not self._second_growth_built:
            return
        if self._growth_index == 0:
            super()._act_after_v1(state)
            return
        if self._growth_index == 1 and not self._oil_attempted:
            if not self._oil_window_is_favorable(state):
                return
            self._oil_attempted = True
            self._run_oil_surveys()
            self._drill_best_oil_target(self.api.state())
            return
        super()._act_after_v1(state)

    def _oil_window_is_favorable(self, state: dict[str, Any]) -> bool:
        if float(state["treasury"]) < self.OIL_TREASURY_FLOOR:
            return False
        if float(state.get("crude_price_usd_per_bbl", 40.0)) < self.MIN_CRUDE_PRICE:
            return False
        return not any(
            event.get("type") == "crude_collapse" for event in state.get("active_events", [])
        )

    def _run_oil_surveys(self) -> None:
        for x, y, size in self.OIL_SURVEY_PLAN:
            result = self.api.survey(x, y, size)
            if not result.get("ok"):
                return
            for voxel in result["result"]["voxels"]:
                key = (int(voxel["x"]), int(voxel["y"]), int(voxel["z"]))
                self._estimates[key] = (
                    float(voxel["oil_estimate_bbl"]),
                    float(voxel["perm_estimate_md"]),
                )

    def _drill_best_oil_target(self, state: dict[str, Any]) -> None:
        latest = state
        for _ in range(self.MAX_OIL_WELLS):
            target = self._best_oil_target(latest)
            if target is None:
                return
            _value, rate, x, y, z = target
            if rate < self.MIN_RATE_BBL_DAY:
                return
            capex = 50_000.0 * (1.0 + (z / int(latest["config"]["world_d"])) ** 2)
            if float(latest["treasury"]) < capex + self.MIN_POST_OIL_TREASURY:
                return
            result = self.api.drill(x, y, z, "production")
            if not result.get("ok"):
                return
            self.api.control_well(str(result["result"]["id"]), min(200.0, rate))
            latest = self.api.state()

    def _best_oil_target(self, state: dict[str, Any]) -> tuple[float, float, int, int, int] | None:
        world_w = int(state["config"]["world_w"])
        world_h = int(state["config"]["world_h"])
        world_d = int(state["config"]["world_d"])
        game_days = int(state["config"].get("active_game_days", state["config"]["game_days"]))
        remaining_days = max(0, game_days - int(state["day"]))
        crude_price = float(state.get("crude_price_usd_per_bbl", 40.0))
        occupied = {
            (int(tile["x"]), int(tile["y"]))
            for tile in state["tiles"]
        } | {
            (int(well["x"]), int(well["y"]))
            for well in state.get("wells", [])
        }

        best: tuple[float, float, int, int, int] | None = None
        for (x, y, z), (oil_est, _perm_est) in self._estimates.items():
            if oil_est <= 0.0 or (x, y) in occupied:
                continue
            if self._overlaps_existing_well_pool(x, y, z, state):
                continue
            pool = self._known_oil_pool(x, y, z, world_w, world_h, world_d)
            if pool is None:
                continue
            pool_oil, mean_perm = pool
            if pool_oil <= 0.0 or mean_perm <= 0.0:
                continue
            rate = min(200.0, 200.0 * mean_perm / 500.0)
            capex = 50_000.0 * (1.0 + (z / world_d) ** 2)
            opex = 100.0 * remaining_days
            net_value = rate * crude_price * remaining_days - capex - opex
            if net_value < self.MIN_NET_VALUE:
                continue
            candidate = (net_value, rate, x, y, z)
            if best is None or candidate > best:
                best = candidate
        return best

    def _overlaps_existing_well_pool(self, x: int, y: int, z: int, state: dict[str, Any]) -> bool:
        for well in state.get("wells", []):
            if (
                abs(x - int(well["x"])) <= 2
                and abs(y - int(well["y"])) <= 2
                and abs(z - int(well["target_z"])) <= 2
            ):
                return True
        return False

    def _known_oil_pool(
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


class OilFundedNoShedGrowthAgent(OilFundedGrowthAgent):
    """Oil-funded growth without commercial demolition churn."""

    def act(self, state: dict[str, Any]) -> None:
        ExtraGrowthAgent.act(self, state)

    def _shed_commercial_load(self, state: dict[str, Any]) -> None:
        return


class MultiOilFundedGrowthAgent(OilFundedGrowthAgent):
    """Survey four known basins legally and drill the best two before growth."""

    OIL_SURVEY_PLAN = (
        (5, 31, 4),
        (29, 9, 4),
        (21, 14, 4),
        (16, 22, 4),
    )
    MAX_OIL_WELLS = 2
    MIN_RATE_BBL_DAY = 30.0
    MIN_NET_VALUE = 100_000.0


class OilFundedConservativeGrowthAgent(OilFundedGrowthAgent):
    """Stop at the 380-pop city size that stays closest to solvency."""

    PLANS = (
        (40_000.0, HOUSE_SURPLUS_PLAN),
        (220_000.0, ROAD_GRID_PLAN + ROW_20_21_PLAN),
        (200_000.0, BATTERY_STAGE_1_PLAN),
        (220_000.0, SOLAR_STAGE_1_PLAN),
        (320_000.0, ROW_23_24_PLAN),
        (300_000.0, BATTERY_STAGE_2_PLAN),
        (360_000.0, SOLAR_STAGE_2_PLAN),
        (460_000.0, ROW_26_27_PLAN),
        (540_000.0, SOLAR_STAGE_3_PLAN),
    )


class OilFundedConservativeNoShedAgent(OilFundedConservativeGrowthAgent):
    """Conservative oil growth without temporary commercial demolition."""

    def act(self, state: dict[str, Any]) -> None:
        ExtraGrowthAgent.act(self, state)

    def _shed_commercial_load(self, state: dict[str, Any]) -> None:
        return


class OilFundedConservativePermanentShedAgent(OilFundedConservativeGrowthAgent):
    """Conservative oil growth with one-way emergency commercial shedding."""

    MAX_SHED_SITES = 6

    def _restore_one_if_safe(self, state: dict[str, Any]) -> None:
        return


class OilFundedConservativeHardenedAgent(OilFundedConservativePermanentShedAgent):
    """Conservative oil growth with extra late storage for coal failures."""

    PLANS = (
        (40_000.0, HOUSE_SURPLUS_PLAN),
        (220_000.0, ROAD_GRID_PLAN + ROW_20_21_PLAN),
        (200_000.0, BATTERY_STAGE_1_PLAN),
        (220_000.0, SOLAR_STAGE_1_PLAN),
        (320_000.0, ROW_23_24_PLAN),
        (300_000.0, BATTERY_STAGE_2_PLAN),
        (360_000.0, SOLAR_STAGE_2_PLAN),
        (460_000.0, ROW_26_27_PLAN),
        (540_000.0, SOLAR_STAGE_3_PLAN),
        (650_000.0, BATTERY_STAGE_3_PLAN),
        (800_000.0, BATTERY_STAGE_4_PLAN),
    )


class GasBackedConservativePermanentShedAgent(HighGrowthAdaptiveShedAgent):
    """Build staffed gas backup before high growth, then stop at 380 cap."""

    MAX_SHED_SITES = 6
    PLANS = (
        (40_000.0, HOUSE_SURPLUS_PLAN),
        (300_000.0, GAS_BACKUP_PLAN),
        (220_000.0, ROAD_GRID_PLAN + ROW_20_21_PLAN),
        (200_000.0, BATTERY_STAGE_1_PLAN),
        (220_000.0, SOLAR_STAGE_1_PLAN),
        (320_000.0, ROW_23_24_PLAN),
        (300_000.0, BATTERY_STAGE_2_PLAN),
        (360_000.0, SOLAR_STAGE_2_PLAN),
        (460_000.0, ROW_26_27_PLAN),
        (540_000.0, SOLAR_STAGE_3_PLAN),
    )

    def _restore_one_if_safe(self, state: dict[str, Any]) -> None:
        return
