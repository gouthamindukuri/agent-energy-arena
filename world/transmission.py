"""Two-zone transmission constraints layered on top of dispatch.

The base arena dispatch is a copper-plate grid: every generated kWh can serve
every load. This module keeps that default behavior when transfer/export limits
are high, while allowing scenarios to model a common real-world failure mode:
cheap renewable generation stranded behind a network bottleneck while demand in
another zone is met by replacement energy.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from world import workforce
from world.event_effects import demand_surprise_ic_mult, heatwave_residential_mult
from world.power import (
    PLANT_TYPES,
    R_BALANCED,
    R_BROWNOUT,
    R_CURTAILMENT,
    RENEWABLE_TYPES,
    commercial_factor,
    residential_kw,
)
from world.snapshots import BalanceState

if TYPE_CHECKING:
    from world.state import Tile, WorldState

NORTH = "north"
SOUTH = "south"
ZONES: tuple[str, str] = (NORTH, SOUTH)


@dataclass(frozen=True)
class TransmissionResult:
    supply_kw: float
    balance: BalanceState
    served_kw: float
    excess_kw: float
    exported_kw: float
    curtailed_renewable_kw: float
    replacement_energy_kw: float
    constraint_payment: float
    replacement_energy_cost: float
    transfer_north_to_south_kw: float
    transfer_south_to_north_kw: float
    demand_by_zone: dict[str, float]
    supply_by_zone: dict[str, float]


def empty_zone_split() -> dict[str, float]:
    return {NORTH: 0.0, SOUTH: 0.0}


def zone_split_y(state: WorldState) -> int:
    """Return the north/south boundary row.

    The town hall is placed at ``world_h // 2`` during reset. Using it as the
    split anchor avoids threading config through pure tick helpers and keeps
    tests with hand-built states deterministic.
    """

    town_hall_y = [t.y for t in state.tiles if t.type == "town_hall"]
    return min(town_hall_y) if town_hall_y else 16


def zone_for_xy(state: WorldState, _x: int, y: int) -> str:
    return NORTH if y < zone_split_y(state) else SOUTH


def zonal_civilian_demand_kw(state: WorldState, hour: int) -> dict[str, float]:
    """Split residential/commercial/industrial demand across two zones."""

    demand = empty_zone_split()

    residential = residential_kw(hour, int(state.population)) * heatwave_residential_mult(state)
    housing_by_zone = empty_zone_split()
    for tile in state.tiles:
        if tile.housing_capacity <= 0:
            continue
        housing_by_zone[zone_for_xy(state, tile.x, tile.y)] += tile.housing_capacity
    total_housing = sum(housing_by_zone.values())
    if total_housing > 0.0:
        for zone in ZONES:
            demand[zone] += residential * housing_by_zone[zone] / total_housing
    else:
        demand[SOUTH] += residential

    ic_mult = demand_surprise_ic_mult(state)
    for tile in state.tiles:
        if not tile.operational:
            continue
        zone = zone_for_xy(state, tile.x, tile.y)
        if tile.type == "industrial":
            demand[zone] += tile.demand_kw * workforce.efficiency(tile) * ic_mult
        elif tile.type == "commercial":
            demand[zone] += (
                tile.demand_kw * commercial_factor(hour) * workforce.efficiency(tile) * ic_mult
            )

    return demand


def transfer_capacity_kw(state: WorldState) -> float:
    line_count = sum(
        1 for tile in state.tiles if tile.type == "transmission_line" and tile.operational
    )
    return max(0.0, state.grid_transfer_capacity_kw) + (
        line_count * max(0.0, state.transmission_line_capacity_kw)
    )


def zonal_supply_kw(
    state: WorldState,
    plants: list[Tile],
    outputs: dict[str, float],
    charge_kw_by_battery: dict[str, float],
    discharge_kw_by_battery: dict[str, float],
) -> dict[str, float]:
    supply = empty_zone_split()
    for plant in plants:
        if plant.type not in PLANT_TYPES:
            continue
        supply[zone_for_xy(state, plant.x, plant.y)] += outputs.get(plant.id, 0.0)
    for tile in state.tiles:
        if tile.type != "battery":
            continue
        zone = zone_for_xy(state, tile.x, tile.y)
        supply[zone] -= charge_kw_by_battery.get(tile.id, 0.0)
        supply[zone] += discharge_kw_by_battery.get(tile.id, 0.0)
    return supply


def zonal_renewable_supply_kw(
    state: WorldState,
    plants: list[Tile],
    outputs: dict[str, float],
    charge_kw_by_battery: dict[str, float],
    discharge_kw_by_battery: dict[str, float],
) -> dict[str, float]:
    renewable = empty_zone_split()
    for plant in plants:
        if plant.type not in RENEWABLE_TYPES:
            continue
        renewable[zone_for_xy(state, plant.x, plant.y)] += outputs.get(plant.id, 0.0)
    for tile in state.tiles:
        if tile.type != "battery":
            continue
        zone = zone_for_xy(state, tile.x, tile.y)
        renewable[zone] -= charge_kw_by_battery.get(tile.id, 0.0)
        renewable[zone] += discharge_kw_by_battery.get(tile.id, 0.0)
    return renewable


def apply_transmission_constraints(
    state: WorldState,
    *,
    demand_by_zone: dict[str, float],
    supply_by_zone: dict[str, float],
    renewable_supply_by_zone: dict[str, float],
) -> TransmissionResult:
    """Resolve two-zone flows, constrained curtailment, and replacement energy."""

    north_supply = max(0.0, supply_by_zone.get(NORTH, 0.0))
    south_supply = max(0.0, supply_by_zone.get(SOUTH, 0.0))
    north_demand = max(0.0, demand_by_zone.get(NORTH, 0.0))
    south_demand = max(0.0, demand_by_zone.get(SOUTH, 0.0))
    total_demand = north_demand + south_demand
    if total_demand <= 0.0:
        return TransmissionResult(
            supply_kw=0.0,
            balance=BalanceState.BALANCED,
            served_kw=0.0,
            excess_kw=0.0,
            exported_kw=0.0,
            curtailed_renewable_kw=0.0,
            replacement_energy_kw=0.0,
            constraint_payment=0.0,
            replacement_energy_cost=0.0,
            transfer_north_to_south_kw=0.0,
            transfer_south_to_north_kw=0.0,
            demand_by_zone={NORTH: north_demand, SOUTH: south_demand},
            supply_by_zone={NORTH: north_supply, SOUTH: south_supply},
        )

    north_surplus = max(0.0, north_supply - north_demand)
    south_surplus = max(0.0, south_supply - south_demand)
    north_deficit = max(0.0, north_demand - north_supply)
    south_deficit = max(0.0, south_demand - south_supply)

    transfer_capacity = transfer_capacity_kw(state)
    north_to_south = 0.0
    south_to_north = 0.0
    if north_surplus > 0.0 and south_deficit > 0.0:
        north_to_south = min(north_surplus, south_deficit, transfer_capacity)
        north_surplus -= north_to_south
        south_deficit -= north_to_south
    elif south_surplus > 0.0 and north_deficit > 0.0:
        south_to_north = min(south_surplus, north_deficit, transfer_capacity)
        south_surplus -= south_to_north
        north_deficit -= south_to_north

    stranded_surplus = north_surplus + south_surplus
    unresolved_deficit_before_replacement = north_deficit + south_deficit

    # Replacement energy models redispatch: another unit must generate where
    # the demand is because low-cost energy is stranded behind the bottleneck.
    # It only covers a deficit that coexists with stranded local surplus, so a
    # true generation shortage still becomes brownout/blackout.
    replacement_energy_kw = min(unresolved_deficit_before_replacement, stranded_surplus)
    unresolved_deficit = max(0.0, unresolved_deficit_before_replacement - replacement_energy_kw)
    served_kw = max(0.0, total_demand - unresolved_deficit)

    if served_kw / total_demand < R_BALANCED:
        if served_kw / total_demand >= R_BROWNOUT:
            balance = BalanceState.BROWNOUT
        else:
            balance = BalanceState.BLACKOUT
        exported_kw = 0.0
        curtailed_renewable_kw = _curtailed_renewable_from_surplus(
            stranded_surplus,
            north_surplus,
            south_surplus,
            renewable_supply_by_zone,
            {NORTH: north_demand, SOUTH: south_demand},
            economic_excess_kw=stranded_surplus,
        )
        excess_kw = 0.0
    else:
        if (served_kw + stranded_surplus) / total_demand >= R_CURTAILMENT:
            balance = BalanceState.CURTAILMENT
            excess_kw = stranded_surplus
            exported_kw = min(excess_kw, max(0.0, state.grid_external_export_capacity_kw))
            physical_curtailed_kw = max(0.0, excess_kw - exported_kw)
            curtailed_renewable_kw = _curtailed_renewable_from_surplus(
                physical_curtailed_kw,
                north_surplus,
                south_surplus,
                renewable_supply_by_zone,
                {NORTH: north_demand, SOUTH: south_demand},
                economic_excess_kw=excess_kw,
            )
        else:
            balance = BalanceState.BALANCED
            excess_kw = 0.0
            exported_kw = 0.0
            curtailed_renewable_kw = 0.0

    # For the supply/demand chart, keep the original single-bus convention when
    # the grid is effectively serving load: visible supply includes reserve or
    # curtailed surplus even if it is not paid as export. During outage states,
    # show delivered supply so stranded generation cannot hide a brownout.
    if served_kw / total_demand >= R_BALANCED:
        supply_kw = served_kw + stranded_surplus
    else:
        supply_kw = served_kw
    constraint_payment = curtailed_renewable_kw * max(0.0, state.curtailment_compensation_per_kwh)
    replacement_energy_cost = replacement_energy_kw * max(
        0.0, state.replacement_energy_cost_per_kwh
    )

    return TransmissionResult(
        supply_kw=supply_kw,
        balance=balance,
        served_kw=served_kw,
        excess_kw=excess_kw,
        exported_kw=exported_kw,
        curtailed_renewable_kw=curtailed_renewable_kw,
        replacement_energy_kw=replacement_energy_kw,
        constraint_payment=constraint_payment,
        replacement_energy_cost=replacement_energy_cost,
        transfer_north_to_south_kw=north_to_south,
        transfer_south_to_north_kw=south_to_north,
        demand_by_zone={NORTH: north_demand, SOUTH: south_demand},
        supply_by_zone={NORTH: north_supply, SOUTH: south_supply},
    )


def _curtailed_renewable_from_surplus(
    curtailed_kw: float,
    north_surplus: float,
    south_surplus: float,
    renewable_supply_by_zone: dict[str, float],
    demand_by_zone: dict[str, float],
    *,
    economic_excess_kw: float,
) -> float:
    if curtailed_kw <= 0.0 or economic_excess_kw <= 0.0:
        return 0.0

    renewable_surplus_by_zone = empty_zone_split()
    for zone in ZONES:
        renewable_surplus_by_zone[zone] = max(
            0.0,
            renewable_supply_by_zone.get(zone, 0.0) - demand_by_zone.get(zone, 0.0),
        )

    north_weight = north_surplus / economic_excess_kw if economic_excess_kw > 0 else 0.0
    south_weight = south_surplus / economic_excess_kw if economic_excess_kw > 0 else 0.0
    renewable_fraction = 0.0
    if north_surplus > 0.0:
        renewable_fraction += north_weight * min(
            1.0, renewable_surplus_by_zone[NORTH] / north_surplus
        )
    if south_surplus > 0.0:
        renewable_fraction += south_weight * min(
            1.0, renewable_surplus_by_zone[SOUTH] / south_surplus
        )
    renewable_fraction = max(0.0, min(1.0, renewable_fraction))
    return curtailed_kw * renewable_fraction
