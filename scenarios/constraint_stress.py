"""Constraint-stress scenario — transmission bottlenecks and redispatch costs.

This scenario activates the two-zone grid constraint mechanics without changing
the baseline scenarios. It represents a north/south network bottleneck:
generation can be stranded in one zone while demand in the other zone is served
by replacement energy, and renewable curtailment earns compensation costs
instead of being treated as free export revenue.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.scenario import Scenario, inject_display_marker

if TYPE_CHECKING:
    from world.sim import World


class ConstraintStress(Scenario):
    """Stress locational grid planning with limited transfer/export capacity."""

    seed: int = 42

    GRID_TRANSFER_CAPACITY_KW: float = 300.0
    GRID_EXTERNAL_EXPORT_CAPACITY_KW: float = 75.0
    TRANSMISSION_LINE_CAPACITY_KW: float = 250.0
    CURTAILMENT_COMPENSATION_PER_KWH: float = 0.06
    REPLACEMENT_ENERGY_COST_PER_KWH: float = 0.18

    def apply(self, world: World, day: int) -> None:
        state = world.state

        state.grid_transfer_capacity_kw = self.GRID_TRANSFER_CAPACITY_KW
        state.grid_external_export_capacity_kw = self.GRID_EXTERNAL_EXPORT_CAPACITY_KW
        state.transmission_line_capacity_kw = self.TRANSMISSION_LINE_CAPACITY_KW
        state.curtailment_compensation_per_kwh = self.CURTAILMENT_COMPENSATION_PER_KWH
        state.replacement_energy_cost_per_kwh = self.REPLACEMENT_ENERGY_COST_PER_KWH

        if day == 0:
            state.scenario_trace.append(
                {
                    "day": day,
                    "kind": "constraint_stress_start",
                    "grid_transfer_capacity_kw": self.GRID_TRANSFER_CAPACITY_KW,
                    "grid_external_export_capacity_kw": self.GRID_EXTERNAL_EXPORT_CAPACITY_KW,
                    "transmission_line_capacity_kw": self.TRANSMISSION_LINE_CAPACITY_KW,
                    "curtailment_compensation_per_kwh": self.CURTAILMENT_COMPENSATION_PER_KWH,
                    "replacement_energy_cost_per_kwh": self.REPLACEMENT_ENERGY_COST_PER_KWH,
                }
            )
            inject_display_marker(
                state,
                marker_type="constraint_stress",
                started_day=day,
                ends_day=world.config.game_days,
                grid_transfer_capacity_kw=self.GRID_TRANSFER_CAPACITY_KW,
                grid_external_export_capacity_kw=self.GRID_EXTERNAL_EXPORT_CAPACITY_KW,
            )
