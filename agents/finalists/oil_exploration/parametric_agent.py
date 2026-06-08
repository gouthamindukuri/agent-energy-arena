"""Parametric deterministic agents for rapid policy search.

Select a policy with EAGE_POLICY_ID. The default is a conservative
house-heavy coal-backed growth plan, not the saved best checkpoint.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from .high_growth import (
    BATTERY_STAGE_1_PLAN,
    BATTERY_STAGE_2_PLAN,
    BATTERY_STAGE_3_PLAN,
    BATTERY_STAGE_4_PLAN,
    COAL_BACKUP_PLAN,
    HOUSE_SURPLUS_PLAN,
    ROAD_GRID_PLAN,
    SOLAR_STAGE_1_PLAN,
    SOLAR_STAGE_2_PLAN,
    SOLAR_STAGE_3_PLAN,
    HighGrowthAdaptiveShedAgent,
    OilFundedGrowthAgent,
)

Plan = tuple[tuple[str, int, int], ...]
Stage = tuple[float, Plan]


def _support_row(
    house_y: int,
    support_y: int,
    *,
    commercial_xs: tuple[int, ...],
    park_xs: tuple[int, ...],
) -> Plan:
    used = set(commercial_xs) & set(park_xs)
    if used:
        raise ValueError(f"duplicate support cells: {sorted(used)}")
    return (
        *(("house", x, house_y) for x in range(23, 32)),
        *(("commercial", x, support_y) for x in commercial_xs),
        *(("park", x, support_y) for x in park_xs),
    )


ROW_20_GARDEN_4C = _support_row(
    20,
    21,
    commercial_xs=(23, 25, 27, 29),
    park_xs=(24, 26, 28, 30, 31),
)
ROW_23_GARDEN_4C = _support_row(
    23,
    24,
    commercial_xs=(23, 25, 27, 29),
    park_xs=(24, 26, 28, 30, 31),
)
ROW_26_GARDEN_4C = _support_row(
    26,
    27,
    commercial_xs=(23, 25, 27, 29),
    park_xs=(24, 26, 28, 30, 31),
)

ROW_20_GARDEN_5C = _support_row(
    20,
    21,
    commercial_xs=(23, 25, 27, 29, 31),
    park_xs=(24, 26, 28, 30),
)
ROW_23_GARDEN_5C = _support_row(
    23,
    24,
    commercial_xs=(23, 25, 27, 29, 31),
    park_xs=(24, 26, 28, 30),
)
ROW_26_GARDEN_5C = _support_row(
    26,
    27,
    commercial_xs=(23, 25, 27, 29, 31),
    park_xs=(24, 26, 28, 30),
)

ROW_29_EDGE_3C = (
    *(("house", x, 29) for x in range(23, 32)),
    ("park", 25, 30),
    ("park", 28, 30),
    ("park", 31, 30),
    ("commercial", 25, 18),
    ("commercial", 28, 18),
    ("commercial", 31, 18),
)

ROW_29_EDGE_4C = (
    *(("house", x, 29) for x in range(23, 32)),
    ("park", 24, 30),
    ("park", 27, 30),
    ("park", 30, 30),
    ("commercial", 24, 18),
    ("commercial", 25, 18),
    ("commercial", 28, 18),
    ("commercial", 31, 18),
)

WIND_NORTH_PLAN = (
    ("wind_turbine", 18, 3),
    ("wind_turbine", 18, 6),
    ("wind_turbine", 18, 9),
    ("wind_turbine", 21, 6),
)

BATTERY_STAGE_5_PLAN = (
    ("battery", 30, 7),
    ("battery", 31, 7),
)

SOLAR_STAGE_4_PLAN = (
    ("solar_farm", 26, 6),
    ("solar_farm", 27, 6),
    ("solar_farm", 28, 6),
    ("solar_farm", 29, 6),
)

ENERGY_1 = SOLAR_STAGE_1_PLAN + BATTERY_STAGE_1_PLAN
ENERGY_2 = SOLAR_STAGE_2_PLAN + BATTERY_STAGE_2_PLAN
ENERGY_3 = SOLAR_STAGE_3_PLAN
ENERGY_3B = SOLAR_STAGE_3_PLAN + BATTERY_STAGE_3_PLAN
ENERGY_4B = SOLAR_STAGE_4_PLAN + BATTERY_STAGE_4_PLAN


@dataclass(frozen=True)
class Policy:
    plans: tuple[Stage, ...]
    use_oil: bool = True
    oil_after_growth_index: int = 1
    max_shed_sites: int = 0
    permanent_shed: bool = True
    restore_floor: float = 150_000.0
    oil_floor: float = 300_000.0
    min_post_oil_treasury: float = 70_000.0
    min_crude_price: float = 35.0
    min_rate_bbl_day: float = 35.0
    min_net_value: float = 150_000.0


COAL18_PLANS: tuple[Stage, ...] = (
    (40_000.0, HOUSE_SURPLUS_PLAN),
    (380_000.0, COAL_BACKUP_PLAN + ROAD_GRID_PLAN),
    (180_000.0, ROW_20_GARDEN_5C),
    (290_000.0, ENERGY_1),
    (250_000.0, ROW_23_GARDEN_5C),
    (360_000.0, ENERGY_2),
    (330_000.0, ROW_26_GARDEN_5C),
    (460_000.0, ENERGY_3),
    (530_000.0, ROW_29_EDGE_3C),
    (680_000.0, BATTERY_STAGE_3_PLAN),
    (840_000.0, BATTERY_STAGE_4_PLAN),
)

COAL18_FAST_PLANS: tuple[Stage, ...] = (
    (40_000.0, HOUSE_SURPLUS_PLAN),
    (330_000.0, COAL_BACKUP_PLAN + ROAD_GRID_PLAN),
    (140_000.0, ROW_20_GARDEN_5C),
    (235_000.0, ENERGY_1),
    (195_000.0, ROW_23_GARDEN_5C),
    (300_000.0, ENERGY_2),
    (255_000.0, ROW_26_GARDEN_5C),
    (390_000.0, ENERGY_3),
    (450_000.0, ROW_29_EDGE_3C),
    (610_000.0, BATTERY_STAGE_3_PLAN),
    (780_000.0, BATTERY_STAGE_4_PLAN),
)

COAL19_FAST_PLANS: tuple[Stage, ...] = (
    (40_000.0, HOUSE_SURPLUS_PLAN),
    (330_000.0, COAL_BACKUP_PLAN + ROAD_GRID_PLAN),
    (140_000.0, ROW_20_GARDEN_5C),
    (235_000.0, ENERGY_1),
    (195_000.0, ROW_23_GARDEN_5C),
    (300_000.0, ENERGY_2),
    (255_000.0, ROW_26_GARDEN_5C),
    (390_000.0, ENERGY_3),
    (470_000.0, ROW_29_EDGE_4C),
    (630_000.0, BATTERY_STAGE_3_PLAN),
    (800_000.0, BATTERY_STAGE_4_PLAN),
)

COAL18_PREOIL_CITY_PLANS: tuple[Stage, ...] = (
    (40_000.0, HOUSE_SURPLUS_PLAN),
    (365_000.0, COAL_BACKUP_PLAN + ROAD_GRID_PLAN + ROW_20_GARDEN_5C),
    (245_000.0, ENERGY_1),
    (220_000.0, ROW_23_GARDEN_5C),
    (310_000.0, ENERGY_2),
    (280_000.0, ROW_26_GARDEN_5C),
    (400_000.0, ENERGY_3),
    (470_000.0, ROW_29_EDGE_3C),
    (630_000.0, BATTERY_STAGE_3_PLAN),
    (800_000.0, BATTERY_STAGE_4_PLAN),
)


POLICIES: dict[str, Policy] = {
    "coal15_oil_noshed": Policy(
        plans=(
            (40_000.0, HOUSE_SURPLUS_PLAN),
            (380_000.0, COAL_BACKUP_PLAN + ROAD_GRID_PLAN),
            (170_000.0, ROW_20_GARDEN_4C),
            (270_000.0, ENERGY_1),
            (230_000.0, ROW_23_GARDEN_4C),
            (340_000.0, ENERGY_2),
            (300_000.0, ROW_26_GARDEN_4C),
            (430_000.0, ENERGY_3),
            (500_000.0, ROW_29_EDGE_3C),
            (650_000.0, BATTERY_STAGE_3_PLAN),
            (800_000.0, BATTERY_STAGE_4_PLAN),
        ),
        max_shed_sites=0,
    ),
    "coal15_oil_shed2": Policy(
        plans=(
            (40_000.0, HOUSE_SURPLUS_PLAN),
            (380_000.0, COAL_BACKUP_PLAN + ROAD_GRID_PLAN),
            (170_000.0, ROW_20_GARDEN_4C),
            (270_000.0, ENERGY_1),
            (230_000.0, ROW_23_GARDEN_4C),
            (340_000.0, ENERGY_2),
            (300_000.0, ROW_26_GARDEN_4C),
            (430_000.0, ENERGY_3),
            (500_000.0, ROW_29_EDGE_3C),
            (650_000.0, BATTERY_STAGE_3_PLAN),
            (800_000.0, BATTERY_STAGE_4_PLAN),
        ),
        max_shed_sites=2,
    ),
    "coal15_oil_shed4": Policy(
        plans=(
            (40_000.0, HOUSE_SURPLUS_PLAN),
            (380_000.0, COAL_BACKUP_PLAN + ROAD_GRID_PLAN),
            (170_000.0, ROW_20_GARDEN_4C),
            (270_000.0, ENERGY_1),
            (230_000.0, ROW_23_GARDEN_4C),
            (340_000.0, ENERGY_2),
            (300_000.0, ROW_26_GARDEN_4C),
            (430_000.0, ENERGY_3),
            (500_000.0, ROW_29_EDGE_3C),
            (650_000.0, BATTERY_STAGE_3_PLAN),
            (800_000.0, BATTERY_STAGE_4_PLAN),
        ),
        max_shed_sites=4,
    ),
    "coal18_oil_shed2": Policy(
        plans=COAL18_PLANS,
        max_shed_sites=2,
    ),
    "coal18_oil_noshed": Policy(
        plans=COAL18_PLANS,
        max_shed_sites=0,
    ),
    "coal18_oil_restore2": Policy(
        plans=COAL18_PLANS,
        max_shed_sites=2,
        permanent_shed=False,
        restore_floor=300_000.0,
    ),
    "coal18_earlyoil_shed2": Policy(
        plans=COAL18_PLANS,
        max_shed_sites=2,
        oil_floor=240_000.0,
        min_post_oil_treasury=55_000.0,
    ),
    "coal18_fast_earlyoil_shed2": Policy(
        plans=COAL18_FAST_PLANS,
        max_shed_sites=2,
        oil_floor=240_000.0,
        min_post_oil_treasury=55_000.0,
    ),
    "coal18_fast_earlyoil_noshed": Policy(
        plans=COAL18_FAST_PLANS,
        max_shed_sites=0,
        oil_floor=240_000.0,
        min_post_oil_treasury=55_000.0,
    ),
    "coal18_fast_earlyoil_restore2": Policy(
        plans=COAL18_FAST_PLANS,
        max_shed_sites=2,
        permanent_shed=False,
        restore_floor=250_000.0,
        oil_floor=240_000.0,
        min_post_oil_treasury=55_000.0,
    ),
    "coal18_preoil_city_noshed": Policy(
        plans=COAL18_PREOIL_CITY_PLANS,
        oil_after_growth_index=2,
        max_shed_sites=0,
        oil_floor=260_000.0,
        min_post_oil_treasury=50_000.0,
    ),
    "coal18_preoil_city_restore2": Policy(
        plans=COAL18_PREOIL_CITY_PLANS,
        oil_after_growth_index=2,
        max_shed_sites=2,
        permanent_shed=False,
        restore_floor=250_000.0,
        oil_floor=260_000.0,
        min_post_oil_treasury=50_000.0,
    ),
    "coal18_nooil_noshed": Policy(
        plans=COAL18_PLANS,
        use_oil=False,
        max_shed_sites=0,
    ),
    "coal19_fast_earlyoil_restore2": Policy(
        plans=COAL19_FAST_PLANS,
        max_shed_sites=2,
        permanent_shed=False,
        restore_floor=300_000.0,
        oil_floor=240_000.0,
        min_post_oil_treasury=55_000.0,
    ),
    "coal19_oil_noshed": Policy(
        plans=(
            (40_000.0, HOUSE_SURPLUS_PLAN),
            (380_000.0, COAL_BACKUP_PLAN + ROAD_GRID_PLAN),
            (180_000.0, ROW_20_GARDEN_5C),
            (290_000.0, ENERGY_1),
            (250_000.0, ROW_23_GARDEN_5C),
            (360_000.0, ENERGY_2),
            (330_000.0, ROW_26_GARDEN_5C),
            (460_000.0, ENERGY_3),
            (550_000.0, ROW_29_EDGE_4C),
            (700_000.0, BATTERY_STAGE_3_PLAN),
            (860_000.0, BATTERY_STAGE_4_PLAN),
        ),
        max_shed_sites=0,
    ),
    "coal15_wind_oil_shed2": Policy(
        plans=(
            (40_000.0, HOUSE_SURPLUS_PLAN),
            (420_000.0, COAL_BACKUP_PLAN + ROAD_GRID_PLAN + WIND_NORTH_PLAN),
            (180_000.0, ROW_20_GARDEN_4C),
            (300_000.0, ENERGY_1),
            (250_000.0, ROW_23_GARDEN_4C),
            (370_000.0, ENERGY_2),
            (330_000.0, ROW_26_GARDEN_4C),
            (470_000.0, ENERGY_3),
            (540_000.0, ROW_29_EDGE_3C),
            (700_000.0, BATTERY_STAGE_3_PLAN),
            (860_000.0, BATTERY_STAGE_4_PLAN),
        ),
        max_shed_sites=2,
    ),
    "coal15_nooil_shed2": Policy(
        plans=(
            (40_000.0, HOUSE_SURPLUS_PLAN),
            (380_000.0, COAL_BACKUP_PLAN + ROAD_GRID_PLAN),
            (170_000.0, ROW_20_GARDEN_4C),
            (270_000.0, ENERGY_1),
            (230_000.0, ROW_23_GARDEN_4C),
            (340_000.0, ENERGY_2),
            (300_000.0, ROW_26_GARDEN_4C),
            (430_000.0, ENERGY_3),
            (500_000.0, ROW_29_EDGE_3C),
            (650_000.0, BATTERY_STAGE_3_PLAN),
            (800_000.0, BATTERY_STAGE_4_PLAN),
        ),
        use_oil=False,
        max_shed_sites=2,
    ),
    "renewable15_oil_shed4": Policy(
        plans=(
            (40_000.0, HOUSE_SURPLUS_PLAN),
            (240_000.0, ROAD_GRID_PLAN),
            (180_000.0, ROW_20_GARDEN_4C),
            (270_000.0, ENERGY_1),
            (240_000.0, ROW_23_GARDEN_4C),
            (340_000.0, ENERGY_2),
            (310_000.0, ROW_26_GARDEN_4C),
            (440_000.0, ENERGY_3B),
            (560_000.0, ROW_29_EDGE_3C),
            (720_000.0, ENERGY_4B),
            (900_000.0, BATTERY_STAGE_5_PLAN),
        ),
        max_shed_sites=4,
    ),
    "coal15_fast_oil_shed2": Policy(
        plans=(
            (40_000.0, HOUSE_SURPLUS_PLAN),
            (330_000.0, COAL_BACKUP_PLAN + ROAD_GRID_PLAN),
            (130_000.0, ROW_20_GARDEN_4C),
            (230_000.0, ENERGY_1),
            (180_000.0, ROW_23_GARDEN_4C),
            (300_000.0, ENERGY_2),
            (240_000.0, ROW_26_GARDEN_4C),
            (390_000.0, ENERGY_3),
            (430_000.0, ROW_29_EDGE_3C),
            (600_000.0, BATTERY_STAGE_3_PLAN),
            (760_000.0, BATTERY_STAGE_4_PLAN),
        ),
        max_shed_sites=2,
    ),
    "coal15_slow_oil_shed2": Policy(
        plans=(
            (40_000.0, HOUSE_SURPLUS_PLAN),
            (460_000.0, COAL_BACKUP_PLAN + ROAD_GRID_PLAN),
            (240_000.0, ROW_20_GARDEN_4C),
            (360_000.0, ENERGY_1),
            (330_000.0, ROW_23_GARDEN_4C),
            (460_000.0, ENERGY_2),
            (430_000.0, ROW_26_GARDEN_4C),
            (580_000.0, ENERGY_3),
            (660_000.0, ROW_29_EDGE_3C),
            (820_000.0, BATTERY_STAGE_3_PLAN),
            (980_000.0, BATTERY_STAGE_4_PLAN),
        ),
        max_shed_sites=2,
    ),
}

DEFAULT_POLICY_ID = "coal15_oil_shed2"


class ParametricAgent(OilFundedGrowthAgent):
    """One agent class whose behavior is selected by EAGE_POLICY_ID."""

    POLICY_ID: str | None = None

    def __init__(self, api, *, seed: int | None = None) -> None:
        policy_id = self.POLICY_ID or os.environ.get("EAGE_POLICY_ID", DEFAULT_POLICY_ID)
        if policy_id not in POLICIES:
            raise ValueError(f"unknown EAGE_POLICY_ID={policy_id!r}; choices={sorted(POLICIES)}")
        self.policy_id = policy_id
        self.policy = POLICIES[policy_id]
        super().__init__(api, seed=seed)
        self.PLANS = self.policy.plans
        self.MAX_SHED_SITES = self.policy.max_shed_sites
        self.RESTORE_TREASURY_FLOOR = self.policy.restore_floor
        self.OIL_TREASURY_FLOOR = self.policy.oil_floor
        self.MIN_POST_OIL_TREASURY = self.policy.min_post_oil_treasury
        self.MIN_CRUDE_PRICE = self.policy.min_crude_price
        self.MIN_RATE_BBL_DAY = self.policy.min_rate_bbl_day
        self.MIN_NET_VALUE = self.policy.min_net_value

    def _act_after_v1(self, state: dict[str, Any]) -> None:
        if not self.policy.use_oil:
            HighGrowthAdaptiveShedAgent._act_after_v1(self, state)
            return
        if not self._second_growth_built:
            return
        if self._growth_index < self.policy.oil_after_growth_index:
            HighGrowthAdaptiveShedAgent._act_after_v1(self, state)
            return
        if self._growth_index == self.policy.oil_after_growth_index and not self._oil_attempted:
            if not self._oil_window_is_favorable(state):
                return
            self._oil_attempted = True
            self._run_oil_surveys()
            self._drill_best_oil_target(self.api.state())
            return
        HighGrowthAdaptiveShedAgent._act_after_v1(self, state)

    def _restore_one_if_safe(self, state: dict[str, Any]) -> None:
        if self.policy.permanent_shed:
            return
        super()._restore_one_if_safe(state)


Agent = ParametricAgent
