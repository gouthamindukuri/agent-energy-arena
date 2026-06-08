"""Agent_oil_2 — patient, oil-conditional growth on the coal18 backbone.

Motivation
----------
The V3 winner ``coal18_oil_noshed`` scores 86-90 when its single hard-coded
survey at ``(8, 28)`` strikes oil, but **collapses to ~55** when that one
spot is dry (e.g. seed 42): it surveys once, finds nothing, then commits to
the expensive ENERGY_1 + growth stages *anyway* and bleeds out. The whole
plan silently assumes oil revenue exists.

Agent_oil_2 removes that assumption with three changes, all built to stay
robust across scenarios (static-price ``grid_stress`` and the
``economy_stress`` crude collapse alike):

A. **Search during the cash plateau.** After the first matched district,
   the city idles at ~pop 132 while treasury climbs toward the 350k
   second-growth trigger. That idle buffer funds surveying for free —
   discovery happens *before* the ENERGY_1 drain, not after.

B. **Patient multi-region search behind a reserve floor.** Instead of one
   fixed spot, sweep a priority list of regions. Survey the next region
   only while ``treasury - survey_cost >= SURVEY_RESERVE_FLOOR``; if the
   floor blocks it, *wait for the commercial economy to refill* and try
   again. Surveying can therefore never threaten solvency, and the drill
   targeter (inherited) automatically picks the richest pool found across
   *all* surveyed regions.

C. **Oil-conditional expensive stages.** Stages at/after ``ENERGY_1``
   (index 3 of the coal18 plan) are gated on oil actually being secured.
   If the search is exhausted with no profitable well, growth halts at the
   capped fallback city (``FALLBACK_MAX_GROWTH_INDEX``) and hoards cash on
   the commercial economy — a guaranteed-solvent ~71 floor instead of the
   ~55 collapse. When oil *is* secured, the full coal18 path runs and lands
   the usual 86-90.

Price handling (cross-scenario robustness)
------------------------------------------
Drill and sell are separate decisions. We drill as soon as a profitable
target is revealed *and* the price window is favorable (the inherited
``_oil_window_is_favorable`` refuses to drill into a crude collapse, so on
``economy_stress`` the drill simply waits for recovery while the city sits
safely at the fallback size). Once producing, ``_manage_wells`` shuts wells
in (setpoint 0) during a crude collapse or sub-threshold price and reopens
them on recovery. On ``grid_stress`` (static $40) this never triggers, so
the well just produces continuously — which is optimal there.
"""

from __future__ import annotations

from typing import Any

from .parametric_agent import ParametricAgent


def _survey_cost(size: int) -> float:
    # Mirrors world.subsurface.survey_cost: 15_000 * (size / 4) ** 2.
    return 15_000.0 * (size / 4.0) ** 2


class Agent_oil_2(ParametricAgent):
    """Coal18 backbone + patient oil search + oil-conditional growth."""

    # Inherit the exact winning configuration (COAL18_PLANS, no-shed, oil
    # params) and then override the oil/growth control flow below.
    POLICY_ID = "coal18_oil_noshed"

    # -- Oil search knobs ------------------------------------------------
    # The geology places 3-7 reservoir blobs at *uniformly random* (x, y)
    # across the whole 32x32 map (radius 3-6, depth 4-14), so no spot is
    # privileged a priori. The search is therefore ADAPTIVE and BOUNDED:
    #
    #   * Coarse-detect: survey a spread of anchors (the proven (8,28) spot
    #     leads, then an ~8-spaced grid). A survey reveals oil estimates for
    #     the whole column, so even clipping a blob's edge shows elevated
    #     oil pointing at it.
    #   * Densify: once any anchor shows an oil signal, the next survey
    #     re-centers on that signal to reveal a complete 3x3x3 drillable
    #     pool (a single off-centre coarse survey usually exposes oil but
    #     not a full pool — which is why blind grids often map oil yet never
    #     drill).
    #   * Bounded: give up after MAX_SURVEYS attempts and commit to the
    #     no-oil fallback. Late oil cannot grow the city anyway, and a
    #     bounded search caps the survey spend + R drag on dry seeds.
    COARSE_ANCHORS: tuple[tuple[int, int, int], ...] = (
        (8, 28, 8),    # proven productive spot, widest column first
        (16, 16, 6),   # center
        (8, 8, 6),     # NW
        (24, 8, 6),    # NE
        (24, 24, 6),   # SE
        (16, 28, 6),   # S
        (8, 16, 6),    # W
        (24, 16, 6),   # E
        (16, 8, 6),    # N
    )
    # Stop after this many surveys with no drillable pool → abandon oil.
    # Kept low: on (8,28)-miss seeds, oil found this late/small cannot fund
    # the climb to 437 anyway, so extra surveys only burn cash and drag the
    # renewable share. The proven spot + a few adaptive follow-ups is enough
    # to catch seeds whose reservoir is reachable early.
    MAX_SURVEYS: int = 4
    # A revealed voxel this rich (bbl) is a "signal" worth densifying around.
    DENSIFY_OIL_MIN: float = 2_000.0
    DENSIFY_SIZE: int = 6
    WORLD_W: int = 32
    WORLD_H: int = 32

    # Survey (map-the-field) floor — kept BELOW the drill floor on purpose.
    # Surveying only accumulates estimates; the drill-first logic stops
    # surveying the moment a profitable pool is revealed and then waits for
    # treasury to recover to the (higher) drill floor before committing the
    # well. Decoupling the two lets the mapping phase proceed from the safe
    # city's thin-ish surplus without the drill threshold throttling survey
    # frequency. Still far above $0, so solvency is never at risk.
    SURVEY_RESERVE_FLOOR: float = 150_000.0

    # Expensive, oil-funded stages begin at this coal18 plan index
    # (index 3 == ENERGY_1, the $220k drain).
    #
    # NOTE (verified, seed 42): folding ENERGY_1 into the unconditional
    # fallback (gating from index 4) to lift the renewable share BACKFIRED
    # — it forced the thin economy to spend its hoarded cash buffer to the
    # $290k floor and down to ~$70k, leaving no cushion for the next
    # coal-failure outage (≈58% chance over the game). The city then went
    # insolvent (treasury −$650k, pop 232→137). The buffer is load-bearing
    # for solvency, so the fallback stops at index 2 and HOARDS. The R~0.39
    # drag is the deliberate price of that outage-absorbing cushion.
    OIL_GATED_FROM_INDEX: int = 3
    # When oil is dry, build no further than this index, then hoard. Index
    # 2 == one garden row past the 2nd coal → a solvent ~pop 230 city.
    FALLBACK_MAX_GROWTH_INDEX: int = 2

    # Shut wells in below this crude price (or during a crude collapse).
    # Default is below grid_stress's static $40, so it is inert there and
    # only engages on economy_stress.
    MIN_CRUDE_PRICE_PRODUCE: float = 30.0

    def __init__(self, api, *, seed: int | None = None) -> None:
        super().__init__(api, seed=seed)
        # Drill floor low enough that the thin ~236 fallback economy (which
        # hovers ~160-190k while surveying) can actually commit a well the
        # moment a profitable pool is revealed; MIN_POST_OIL_TREASURY still
        # guards the post-drill balance against insolvency.
        self.OIL_TREASURY_FLOOR = 160_000.0
        self.MIN_POST_OIL_TREASURY = 50_000.0
        self._anchors: list[tuple[int, int, int]] = list(self.COARSE_ANCHORS)
        self._surveyed_centers: set[tuple[int, int]] = set()
        self._surveys_done = 0
        self._oil_secured = False
        self._oil_search_exhausted = False

    # -- Control flow ----------------------------------------------------

    def _act_after_v1(self, state: dict[str, Any]) -> None:
        # Stage machine (coal18 plans), with the expensive tail gated on oil.
        if not self._second_growth_built:
            return

        # (A) Safe-city-first: build the un-gated stages (through the
        #     fallback index, ~pop 236) BEFORE searching for oil, so the
        #     search is funded by that city's ~$2k/day surplus — which
        #     refills surveys fast and stays above the drill threshold —
        #     rather than the thin pre-growth economy that starved the
        #     drill in the early-search prototype.
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
        if float(state["treasury"]) < floor:
            return
        self._build_plan(plan, f"growth {self._growth_index + 1}")
        self._growth_index += 1

    # -- Oil search ------------------------------------------------------

    def _producers(self, state: dict[str, Any]) -> list[dict[str, Any]]:
        return [w for w in state.get("wells", []) if w["type"] == "production"]

    def _tick_oil_search(self, state: dict[str, Any]) -> None:
        if self._oil_secured:
            self._manage_wells(state)
            return
        if self._oil_search_exhausted:
            return

        # Drill immediately when a profitable target is revealed and the
        # price window is favorable (waits out a crude collapse on its own).
        if self._try_drill(state):
            return

        # Bounded search: abandon oil after MAX_SURVEYS fruitless attempts.
        if self._surveys_done >= self.MAX_SURVEYS:
            self._oil_search_exhausted = True
            return

        target = self._next_survey_target()
        if target is None:
            self._oil_search_exhausted = True
            return
        x, y, size = target
        # Survey only above the reserve floor; otherwise wait for refill.
        if float(state["treasury"]) - _survey_cost(size) < self.SURVEY_RESERVE_FLOOR:
            return
        self._do_survey(x, y, size)
        # New info may have revealed a drillable pool — try at once.
        self._try_drill(self.api.state())

    def _try_drill(self, state: dict[str, Any]) -> bool:
        """Drill the best revealed pool if favorable; return True if it fired."""
        if not (self._oil_window_is_favorable(state) and self._best_oil_target(state) is not None):
            return False
        self._drill_best_oil_target(state)
        if self._producers(self.api.state()):
            self._oil_secured = True
        return True

    def _next_survey_target(self) -> tuple[int, int, int] | None:
        """Adaptive: densify on the richest revealed signal if one exists,
        else advance to the next coarse anchor. Returns None when both the
        densify options and the anchor list are exhausted."""
        # Densify around the richest revealed voxel if it is a real signal
        # and a nearby un-surveyed center is available — this converts an
        # edge-clip detection into a full drillable pool.
        if self._estimates:
            (bx, by, _bz), (boil, _bperm) = max(
                self._estimates.items(), key=lambda kv: kv[1][0] * kv[1][1]
            )
            if boil >= self.DENSIFY_OIL_MIN:
                for dx, dy in ((0, 0), (3, 0), (-3, 0), (0, 3), (0, -3)):
                    cx = max(2, min(self.WORLD_W - 3, bx + dx))
                    cy = max(2, min(self.WORLD_H - 3, by + dy))
                    if (cx, cy) not in self._surveyed_centers:
                        return (cx, cy, self.DENSIFY_SIZE)
        # Otherwise the next coarse anchor we have not surveyed yet. PEEK
        # (do not pop) — an anchor is only consumed once it is actually
        # surveyed (via `_surveyed_centers`). Popping here would silently
        # discard anchors on the ticks where treasury is below the survey
        # floor, exhausting the search before a single survey fires.
        for ax, ay, asize in self._anchors:
            if (ax, ay) not in self._surveyed_centers:
                return (ax, ay, asize)
        return None

    def _do_survey(self, x: int, y: int, size: int) -> bool:
        result = self.api.survey(x, y, size)
        self._surveyed_centers.add((x, y))
        self._surveys_done += 1
        if not result.get("ok"):
            return False
        for voxel in result["result"]["voxels"]:
            key = (int(voxel["x"]), int(voxel["y"]), int(voxel["z"]))
            self._estimates[key] = (
                float(voxel["oil_estimate_bbl"]),
                float(voxel["perm_estimate_md"]),
            )
        return True

    def _manage_wells(self, state: dict[str, Any]) -> None:
        # Price-aware production. Inert on static-$40 grid_stress; shuts in
        # during an economy_stress crude collapse, reopens on recovery.
        price = float(state.get("crude_price_usd_per_bbl", 40.0))
        collapse = any(
            e.get("type") == "crude_collapse" for e in state.get("active_events", [])
        )
        target = 0.0 if (collapse or price < self.MIN_CRUDE_PRICE_PRODUCE) else 200.0
        for w in self._producers(state):
            if abs(float(w.get("setpoint_rate_bbl_day", 0.0)) - target) > 1.0:
                self.api.control_well(str(w["id"]), target)


# evaluate.py / Agent Play attach both look for a top-level ``Agent``.
Agent = Agent_oil_2
