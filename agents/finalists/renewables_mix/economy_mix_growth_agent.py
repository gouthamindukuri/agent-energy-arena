"""Generic stable deterministic policy.

This is the current robust baseline: 3 solar + 1 battery + 1 wind opening,
full commercial shedding during live plant failures, and an earlier second
growth threshold so the city does not stall at the first expansion.
"""

from __future__ import annotations

from typing import Any

from .economy_mix_3s1b1w_agent import EconomyMix3S1B1WAgent


class EconomyMixGrowthAgent(EconomyMix3S1B1WAgent):
    SECOND_GROWTH_FLOOR = 100_000.0

    def act(self, state: dict[str, Any]) -> None:
        if not self._bootstrapped:
            self._build_plan(self.BOOTSTRAP_PLAN, "bootstrap")
            self._bootstrapped = True
            return

        day = int(state["day"])
        live_failure = any(
            event.get("type") == "plant_failure" and int(event.get("ends_day", day + 1)) > day
            for event in state.get("active_events", [])
        )
        if live_failure:
            self._shed_commercial_load(state)
            return

        if self._shed_sites:
            self._restore_commercial_load()
            return

        if not self._first_growth_built and float(state["treasury"]) >= 50_000.0:
            self._build_plan(self.FIRST_GROWTH_PLAN, "first growth")
            self._first_growth_built = True
            return

        if self._first_growth_built and not self._second_growth_built:
            latest = self.api.state()
            if float(latest["treasury"]) >= self.SECOND_GROWTH_FLOOR:
                self._build_plan(self.SECOND_GROWTH_PLAN, "second growth")
                self._second_growth_built = True


Agent = EconomyMixGrowthAgent
