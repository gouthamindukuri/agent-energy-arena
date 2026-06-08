"""Per-scenario tests for `scenarios.constraint_stress`."""

from __future__ import annotations

from scenarios.constraint_stress import ConstraintStress
from world.scenario import Scenario, load_scenario
from world.sim import World


def _fresh_world() -> World:
    w = World(scenario=ConstraintStress())
    w.reset(seed=42, scenario=ConstraintStress())
    return w


def test_constraint_stress_loads_via_dotted_path() -> None:
    instance = load_scenario("scenarios.constraint_stress")
    assert isinstance(instance, ConstraintStress)
    assert isinstance(instance, Scenario)
    assert instance.seed == 42


def test_constraint_stress_consumes_no_random_numbers() -> None:
    w = _fresh_world()
    s = ConstraintStress()
    sim_before = w.sim_rng.bit_generator.state
    event_before = w.event_rng.bit_generator.state
    forecast_before = w.forecast_rng.bit_generator.state
    s.apply(w, 0)
    s.apply(w, 1)
    assert w.sim_rng.bit_generator.state == sim_before
    assert w.event_rng.bit_generator.state == event_before
    assert w.forecast_rng.bit_generator.state == forecast_before


def test_constraint_stress_writes_grid_values_and_marker() -> None:
    w = _fresh_world()
    w.scenario.apply(w, 0)
    state = w.state
    assert state.grid_transfer_capacity_kw == ConstraintStress.GRID_TRANSFER_CAPACITY_KW
    assert (
        state.grid_external_export_capacity_kw == ConstraintStress.GRID_EXTERNAL_EXPORT_CAPACITY_KW
    )
    assert state.transmission_line_capacity_kw == ConstraintStress.TRANSMISSION_LINE_CAPACITY_KW
    assert (
        state.curtailment_compensation_per_kwh == ConstraintStress.CURTAILMENT_COMPENSATION_PER_KWH
    )
    assert state.replacement_energy_cost_per_kwh == ConstraintStress.REPLACEMENT_ENERGY_COST_PER_KWH
    assert any(e.get("type") == "constraint_stress" for e in state.active_events)
    assert any(t.get("kind") == "constraint_stress_start" for t in state.scenario_trace)
