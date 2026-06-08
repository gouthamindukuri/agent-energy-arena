"""Generic 3-solar/1-battery/1-wind survival opening."""

from __future__ import annotations

from typing import Any

from .v1_core import V1Agent


class EconomyMix3S1B1WAgent(V1Agent):
    """V1-style city with a cheaper, more resilient renewable mix.

    Compared with the V1 opening, this swaps one battery and one solar farm for
    one wind turbine. The result keeps enough renewable diversity for night and
    coal-failure windows while preserving more cash for early shocks.
    """

    BOOTSTRAP_PLAN = (
        ("solar_farm", 24, 15),
        ("solar_farm", 24, 16),
        ("solar_farm", 24, 17),
        ("battery", 23, 15),
        ("wind_turbine", 30, 10),
        ("commercial", 16, 15),
        ("commercial", 16, 17),
        ("commercial", 15, 15),
        ("commercial", 15, 17),
        ("park", 15, 14),
        ("house", 14, 15),
    )

    def _shed_commercial_load(self, state: dict[str, Any]) -> None:
        staffed = [
            tile
            for tile in state["tiles"]
            if tile["type"] == "commercial" and int(tile.get("staffed_jobs", 0)) > 0
        ]
        count_to_shed = len(staffed) - len(self._shed_sites)
        staffed.sort(key=lambda tile: (-int(tile["staffed_jobs"]), str(tile["id"])))
        for tile in staffed[:count_to_shed]:
            result = self.api.demolish(int(tile["x"]), int(tile["y"]))
            if result.get("ok"):
                self._shed_sites.append((int(tile["x"]), int(tile["y"])))


Agent = EconomyMix3S1B1WAgent
