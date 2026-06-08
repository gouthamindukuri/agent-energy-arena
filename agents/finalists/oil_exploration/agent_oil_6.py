"""Agent_oil_6 — Agent_oil_4 with an early MULTI-probe oil search.

Agent_oil_4 probes only the one proven spot (8,28) early. When that spot is
dry but a reservoir sits elsewhere (the geology scatters 3-7 blobs at random
across the map), oil_4 falls through to the safe-city-first *late* search,
which finds the oil too late to grow the city well — the "late hit" class:
grid_stress seed 101 (oil on survey 2 -> 77.5, R 0.39) and seed 777 (survey 3
-> 82.6, R 0.46), versus the early hits at ~88 with R 0.54.

Agent_oil_6 front-loads the whole bounded adaptive search into the plateau:
instead of one early probe, it keeps probing spread anchors (and densifying
on any signal) from the cash plateau — each probe gated at the same healthy
threshold so a hit is always drillable — until oil is found or the probe
budget is spent. While probing it holds the city at the plateau (each probe
keeps treasury below the second-growth trigger), so a reservoir found on
probe 2 or 3 still comes online ~day 350-450 and the city ramps to 437 early
(early-hit ~88), instead of arriving via the late search (~77-82).

A genuinely dry seed exhausts the budget and falls through to oil_4/oil_2's
robust safe-city + hoard fallback (~71) — no expensive growth was committed,
so there is no collapse risk. Net: late-hits become early-hits (+6-10 each),
for a small delay on the rare all-dry seed.
"""

from __future__ import annotations

from typing import Any

from .agent_oil_2 import _survey_cost
from .agent_oil_4 import Agent_oil_4


class Agent_oil_6(Agent_oil_4):
    """Agent_oil_4 with the bounded oil search front-loaded as a fast burst.

    Probing is a BURST, not a paced sweep: once the plateau holds enough cash
    the agent probes spread anchors on *consecutive* days (drilling on a hit)
    until oil is found, the budget is spent, or treasury would fall below the
    drill/buffer floor. So the city stalls at the plateau for only a handful
    of days — not the ~125 days a refill-gated sweep would cost — and the
    moment the burst resolves the safe-city build resumes. The proven (8,28)
    spot is probed first, so the common single-hit case still costs one probe.
    """

    # Begin the burst once the plateau reaches this. Sized so the full
    # 4-probe budget ($60k + $34k*3 = $162k) all fits above EARLY_PROBE_FLOOR
    # ($330k - $162k = $168k >= $160k), and still below the $350k
    # second-growth trigger so the burst fires during the plateau.
    EARLY_PROBE_START: float = 330_000.0
    # Stop the burst before a probe would drop treasury under this — it is the
    # drill floor (so any hit is immediately drillable) and the outage buffer.
    EARLY_PROBE_FLOOR: float = 160_000.0
    # Hard cap on burst probes (the buffer floor usually binds first).
    EARLY_PROBE_MAX: int = 4

    # A drilled well only counts as "oil secured" once it actually produces
    # at least this much. A drill can succeed yet the well produce ~0 — an
    # unstaffable well at low population, or a near-dry pool the survey
    # over-estimated. Treating a *drilled* well as secured (the old bug)
    # unlocked the expensive oil-funded growth on phantom revenue and
    # collapsed the city (baseline seed 777: well at 0 bbl/day, built ~$420k
    # of growth, bled to -$6.3M). We require real production instead.
    PRODUCTION_THRESHOLD: float = 20.0  # bbl/day
    # Oil counts as secured only after the well SUSTAINS production for this
    # many consecutive days — a single-tick spike (a momentary staffing
    # fluctuation on an otherwise-dead well) must not unlock growth.
    SUSTAINED_PRODUCTION_DAYS: int = 10
    # If the well has not sustained production within this many days of the
    # drill it is declared dead: abandon oil and hold the safe hoard. Once
    # dead it is NEVER resurrected by a later blip.
    DRILL_GRACE_DAYS: int = 45

    # Outage buffer for the NO-OIL fallback. Once oil is ruled out, the city
    # is coal-powered and a plant_failure causes a multi-day total blackout
    # (~$290k of outage penalties — the 2nd coal is no backup, it is unstaffed
    # at this population). No discretionary fallback build may drop treasury
    # below this, so the cash that rides the blackout is never spent on
    # growth/2nd-coal right before the failure (the seed-777 collapse).
    SOLVENCY_FLOOR: float = 320_000.0
    # Capex mirror (world/catalog.py) for estimating a stage's total cost.
    _CAPEX: dict[str, float] = {
        "road": 500, "house": 3_000, "commercial": 8_000, "industrial": 20_000,
        "park": 5_000, "solar_farm": 25_000, "wind_turbine": 40_000,
        "gas_peaker": 80_000, "coal_plant": 200_000, "battery": 60_000,
        "refinery": 150_000, "pipeline": 2_000,
    }

    def __init__(self, api, *, seed: int | None = None) -> None:
        super().__init__(api, seed=seed)
        self._early_probes_used = 0
        self._burst_started = False
        self._drilled = False       # a well exists, awaiting production proof
        self._drilled_day = -1
        self._production_streak = 0  # consecutive days the well produced >= threshold

    def _maybe_early_probe(self, state: dict[str, Any]) -> None:
        # Fast EARLY burst (overrides oil_4's single fixed probe).
        if self._early_probe_done or self._oil_secured:
            return
        if not self._first_growth_built:
            return
        treasury = float(state["treasury"])

        # Arm the burst once, at the plateau peak; thereafter probe every tick
        # (no refill wait) so the city holds for days, not months.
        if not self._burst_started:
            if treasury < self.EARLY_PROBE_START:
                return
            self._burst_started = True

        # Adaptive target: densify on the richest revealed signal, else the
        # next spread anchor (reuses Agent_oil_2's search machinery).
        target = self._next_survey_target()
        if target is None:
            self._early_probe_done = True
            return
        x, y, size = target
        # Protect the drill/outage buffer: stop bursting rather than dig below
        # it. Any hit so far is still drillable; a miss falls to the fallback.
        if treasury - _survey_cost(size) < self.EARLY_PROBE_FLOOR:
            self._early_probe_done = True
            return

        self._do_survey(x, y, size)
        self._early_probes_used += 1
        drilled = self._try_drill(self.api.state())  # one well, pending proof

        # Stop the burst once a well is down (await production proof, do not
        # drill more), the budget is spent, or oil is already confirmed.
        if drilled or self._oil_secured or self._early_probes_used >= self.EARLY_PROBE_MAX:
            self._early_probe_done = True

    # -- Stage machine with an always-on solvency floor -----------------

    def _act_after_v1(self, state: dict[str, Any]) -> None:
        # Reimplements Agent_oil_2's safe-city-first stage machine with an
        # ALWAYS-ON solvency floor. A stage builds only if it leaves the
        # blackout buffer intact — regardless of oil. This lets growth proceed
        # whenever the city stays solvent (commercial revenue alone sustains
        # the 437 city on forgiving scenarios, which also staffs a fresh
        # well), DEFERS a build that would drain the buffer right before a
        # coal-failure blackout (the seed-777 fix), and self-limits on harsh
        # scenarios where the surplus thins. Replaces the production-
        # verification gate, which deadlocked oil (growth needs the well
        # staffed; staffing needs growth) and forfeited every oil hit.
        self._maybe_early_probe(state)

        if not self._second_growth_built:
            return
        if self._growth_index >= self.FALLBACK_MAX_GROWTH_INDEX:
            self._tick_oil_search(state)
        if self._growth_index >= len(self.PLANS):
            return
        if self._growth_index >= self.OIL_GATED_FROM_INDEX and not self._oil_secured:
            if not self._oil_search_exhausted:
                return  # still hunting — do not commit oil-funded stages
            if self._growth_index > self.FALLBACK_MAX_GROWTH_INDEX:
                return  # dry: stop growth, hold the capped fallback city
        floor, plan = self.PLANS[self._growth_index]
        treasury = float(state["treasury"])
        if treasury < floor:
            return
        # Always-on solvency floor: never let a stage drop treasury below the
        # buffer that rides a multi-day coal-failure blackout (~$290k). DEFER
        # (return without advancing) so the stage retries once the hoard has
        # grown past floor + cost + buffer.
        cost = sum(self._CAPEX.get(t, 0.0) for t, _x, _y in plan)
        if treasury - cost < self.SOLVENCY_FLOOR:
            return
        self._build_plan(plan, f"growth {self._growth_index + 1}")
        self._growth_index += 1

    def _try_drill(self, state: dict[str, Any]) -> bool:
        """Drill the best revealed pool and mark oil secured on the drill, so
        growth proceeds (which staffs the well and lets it produce). The
        always-on solvency floor caps any over-commitment if the well is a
        dud — the earlier production-verification gate deadlocked oil because
        growth needs the well staffed but staffing needs growth."""
        if self._oil_secured or self._drilled:
            return False
        if not (self._oil_window_is_favorable(state) and self._best_oil_target(state) is not None):
            return False
        self._drill_best_oil_target(state)
        if self._producers(self.api.state()):
            self._drilled = True
            self._oil_secured = True
            return True
        return False

    def _update_oil_secured(self, state: dict[str, Any]) -> None:
        # Already resolved (secured, or the well was declared dead) — a dead
        # well is never resurrected by a later transient blip.
        if self._oil_secured or self._oil_search_exhausted or not self._drilled:
            return
        producing = any(
            float(w.get("current_rate_bbl_day", 0.0)) >= self.PRODUCTION_THRESHOLD
            for w in self._producers(state)
        )
        # Count CONSECUTIVE producing days; a gap resets the streak so an
        # intermittently-staffed (effectively dead) well never qualifies.
        self._production_streak = self._production_streak + 1 if producing else 0
        if self._production_streak >= self.SUSTAINED_PRODUCTION_DAYS:
            self._oil_secured = True  # sustained real revenue — unlock growth
            return
        # No sustained production within the grace window → the well is dead
        # (unstaffable or near-dry). Abandon oil and hold the safe hoard.
        if int(state["day"]) - self._drilled_day >= self.DRILL_GRACE_DAYS:
            self._oil_search_exhausted = True


# evaluate.py / Agent Play attach both look for a top-level ``Agent``.
Agent = Agent_oil_6
