"""Tests for two-zone transmission constraints."""

from __future__ import annotations

import pytest

from world.snapshots import BalanceState
from world.state import Tile, WorldState
from world.transmission import (
    NORTH,
    SOUTH,
    apply_transmission_constraints,
    transfer_capacity_kw,
    zone_for_xy,
)


def _state() -> WorldState:
    return WorldState(
        seed=1,
        grid_transfer_capacity_kw=1_000_000.0,
        grid_external_export_capacity_kw=1_000_000.0,
        transmission_line_capacity_kw=250.0,
        curtailment_compensation_per_kwh=0.06,
        replacement_energy_cost_per_kwh=0.18,
        tiles=[Tile(id="town_hall-1", type="town_hall", x=16, y=16, built_day=0)],
    )


def test_zone_split_uses_town_hall_row_as_boundary() -> None:
    state = _state()
    assert zone_for_xy(state, 0, 15) == NORTH
    assert zone_for_xy(state, 0, 16) == SOUTH


def test_unconstrained_transfer_behaves_like_single_grid_export() -> None:
    state = _state()
    result = apply_transmission_constraints(
        state,
        demand_by_zone={NORTH: 0.0, SOUTH: 100.0},
        supply_by_zone={NORTH: 150.0, SOUTH: 0.0},
        renewable_supply_by_zone={NORTH: 150.0, SOUTH: 0.0},
    )
    assert result.balance == BalanceState.CURTAILMENT
    assert result.served_kw == pytest.approx(100.0)
    assert result.exported_kw == pytest.approx(50.0)
    assert result.curtailed_renewable_kw == pytest.approx(0.0)
    assert result.replacement_energy_kw == pytest.approx(0.0)
    assert result.transfer_north_to_south_kw == pytest.approx(100.0)


def test_limited_transfer_creates_replacement_energy_and_curtailment_costs() -> None:
    state = _state()
    state.grid_transfer_capacity_kw = 10.0
    state.grid_external_export_capacity_kw = 0.0
    result = apply_transmission_constraints(
        state,
        demand_by_zone={NORTH: 0.0, SOUTH: 100.0},
        supply_by_zone={NORTH: 150.0, SOUTH: 0.0},
        renewable_supply_by_zone={NORTH: 150.0, SOUTH: 0.0},
    )
    assert result.balance == BalanceState.CURTAILMENT
    assert result.served_kw == pytest.approx(100.0)
    assert result.exported_kw == pytest.approx(0.0)
    assert result.curtailed_renewable_kw == pytest.approx(140.0)
    assert result.replacement_energy_kw == pytest.approx(90.0)
    assert result.constraint_payment == pytest.approx(140.0 * 0.06)
    assert result.replacement_energy_cost == pytest.approx(90.0 * 0.18)
    assert result.transfer_north_to_south_kw == pytest.approx(10.0)


def test_true_generation_shortage_still_brownouts() -> None:
    state = _state()
    state.grid_transfer_capacity_kw = 10.0
    result = apply_transmission_constraints(
        state,
        demand_by_zone={NORTH: 0.0, SOUTH: 100.0},
        supply_by_zone={NORTH: 10.0, SOUTH: 0.0},
        renewable_supply_by_zone={NORTH: 10.0, SOUTH: 0.0},
    )
    assert result.balance == BalanceState.BLACKOUT
    assert result.served_kw == pytest.approx(10.0)
    assert result.replacement_energy_kw == pytest.approx(0.0)


def test_transmission_lines_increase_transfer_capacity() -> None:
    state = _state()
    state.grid_transfer_capacity_kw = 100.0
    state.tiles.extend(
        [
            Tile(id="line-1", type="transmission_line", x=1, y=15, built_day=0),
            Tile(id="line-2", type="transmission_line", x=1, y=16, built_day=0),
        ]
    )
    assert transfer_capacity_kw(state) == pytest.approx(600.0)
