"""Agent_oil_4 — Agent_oil_2 + an early probe at the proven oil spot.

Agent_oil_2's safe-city-first reorder protects (8,28)-miss seeds from the V3
collapse, but it costs the (8,28)-HIT seeds: the oil search only begins once
the fallback city is built (~day 600) and is then paced behind a reserve
floor, so even on a seed whose (8,28) reservoir is rich, oil comes online
late — too late to fund the climb to 437 in time. The whole score gap to 90
is the early game (the `level`/`trough` of the treasury and population axes
are dragged by every day spent below pop-400 / below treasury-surplus), so
late oil leaves points on the table (seed 112 fell 90.05 -> 88.69; seed 302,
which V3 scored 89.17, stalls at pop 236 under oil_2).

Agent_oil_4 restores V3's early-oil ramp WITHOUT reintroducing the collapse:
it probes the proven spot ONCE, early, during the bootstrap cash plateau
(treasury is $277k+ there — ample for one $60k survey plus a ~$70k drill).

  * HIT  -> drill immediately, oil online ~day 300, the expensive growth
            stages unlock (oil secured) and the city ramps to 437 early,
            lifting level_pop/level_treasury and the troughs back toward V3.
  * MISS -> fall straight through to Agent_oil_2's safe-city-first +
            bounded adaptive search + hoard fallback. The probe's survey is
            recorded (so the later search skips (8,28) and counts it against
            the survey budget), and no expensive growth was committed, so a
            dry probe cannot trigger the V3 insolvency spiral.

This is the best-of-both: early oil on the easy hit seeds, the robust ~71
fallback on the miss seeds.
"""

from __future__ import annotations

from typing import Any

from .agent_oil_2 import Agent_oil_2


class Agent_oil_4(Agent_oil_2):
    """Agent_oil_2 with an early single probe at the proven oil spot."""

    # The proven spot (productive on seeds 112/1342/2232/302), widest column.
    EARLY_PROBE_SITE: tuple[int, int, int] = (8, 28, 8)
    # Fire the probe once the bootstrap plateau holds at least this much —
    # enough for the $60k survey, a ~$70k drill, and a safe post-drill
    # balance — while staying below the $350k second-growth trigger so the
    # probe lands during the plateau, not after the city has already moved on.
    EARLY_PROBE_MIN_CASH: float = 260_000.0

    def __init__(self, api, *, seed: int | None = None) -> None:
        super().__init__(api, seed=seed)
        self._early_probe_done = False

    def _act_after_v1(self, state: dict[str, Any]) -> None:
        # Early probe BEFORE the safe-city-first gate: a hit puts oil online
        # ~day 300 (V3-style) and unlocks fast growth; a miss falls straight
        # through to Agent_oil_2's robust fallback path below.
        self._maybe_early_probe(state)
        super()._act_after_v1(state)

    def _maybe_early_probe(self, state: dict[str, Any]) -> None:
        if self._early_probe_done or self._oil_secured:
            return
        # Wait for the bootstrap + first matched district, then for the
        # plateau to hold enough cash to survey-and-drill in one shot.
        if not self._first_growth_built:
            return
        if float(state["treasury"]) < self.EARLY_PROBE_MIN_CASH:
            return
        self._early_probe_done = True
        x, y, size = self.EARLY_PROBE_SITE
        self._do_survey(x, y, size)  # records the spot; counts vs MAX_SURVEYS
        self._try_drill(self.api.state())  # drills + sets _oil_secured on a hit


# evaluate.py / Agent Play attach both look for a top-level ``Agent``.
Agent = Agent_oil_4
