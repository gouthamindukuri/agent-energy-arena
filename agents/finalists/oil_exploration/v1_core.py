"""Deterministic V1 submission.

Strategy:
* bootstrap enough renewable generation and storage to survive starter-coal
  failures;
* observe daily so a new failure cannot hide inside a seven-day step;
* shed staffed commercial loads during failures, then restore them;
* add matched housing/jobs/parks at $50k;
* add a second matched district only from a $350k surplus.
"""

from __future__ import annotations

from typing import Any

from agents.api_client import ApiClient
from agents.base import BaseAgent


class V1Agent(BaseAgent):
    BOOTSTRAP_PLAN = (
        ("solar_farm", 24, 15),
        ("solar_farm", 24, 16),
        ("solar_farm", 24, 17),
        ("solar_farm", 24, 18),
        ("battery", 23, 15),
        ("battery", 23, 16),
        ("commercial", 16, 15),
        ("commercial", 16, 17),
        ("commercial", 15, 15),
        ("commercial", 15, 17),
        ("park", 15, 14),
        ("house", 14, 15),
    )
    FIRST_GROWTH_PLAN = (
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
    SECOND_GROWTH_PLAN = (
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

    def __init__(self, api: ApiClient, *, seed: int | None = None) -> None:
        super().__init__(api, seed=seed)
        self._bootstrapped = False
        self._first_growth_built = False
        self._second_growth_built = False
        self._shed_sites: list[tuple[int, int]] = []

    def next_step_days(self, state: dict[str, Any]) -> int:
        return 1

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
            if float(latest["treasury"]) >= 350_000.0:
                self._build_plan(self.SECOND_GROWTH_PLAN, "second growth")
                self._second_growth_built = True

    def _build_plan(self, plan: tuple[tuple[str, int, int], ...], label: str) -> None:
        for tile_type, x, y in plan:
            result = self.api.build(tile_type, x, y)
            if not result.get("ok"):
                raise RuntimeError(f"{label} failed: {tile_type}@({x},{y}): {result.get('error')}")

    def _shed_commercial_load(self, state: dict[str, Any]) -> None:
        staffed = [
            tile
            for tile in state["tiles"]
            if tile["type"] == "commercial" and int(tile.get("staffed_jobs", 0)) > 0
        ]
        # Two staffed commercial loads are supportable by the solar/storage
        # package even during a multi-day coal outage.
        count_to_shed = max(0, len(staffed) - 2) - len(self._shed_sites)
        staffed.sort(key=lambda tile: (-int(tile["staffed_jobs"]), str(tile["id"])))
        for tile in staffed[:count_to_shed]:
            result = self.api.demolish(int(tile["x"]), int(tile["y"]))
            if result.get("ok"):
                self._shed_sites.append((int(tile["x"]), int(tile["y"])))

    def _restore_commercial_load(self) -> None:
        while self._shed_sites:
            state = self.api.state()
            if float(state["treasury"]) < 8_000.0:
                return
            x, y = self._shed_sites[0]
            result = self.api.build("commercial", x, y)
            if not result.get("ok"):
                return
            self._shed_sites.pop(0)


Agent = V1Agent
