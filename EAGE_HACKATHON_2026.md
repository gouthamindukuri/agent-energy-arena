# Prometheus: EAGE Hackthon 2026 winning solution

Prometheus won EAGE Hackthon 2026 with a deterministic city controller called Risk-Aware Growth. The controller builds a fixed city layout in stages, but it only moves to the next stage when the treasury and power grid can support it.

This repository is a fork of [ovcharenkoo/agent-energy-arena](https://github.com/ovcharenkoo/agent-energy-arena). The upstream project provides the simulator, API, scenarios, scoring code, and evaluation harness. This document covers our agent work, the experiments that led to the final policy, and the commands needed to reproduce the published result.

## What we submitted

The original submission entrypoint was `submit.agent`. An exact copy is kept here:

- [submission entrypoint](experiments/eage_hackathon_2026/final_submission/submit/agent.py)
- [submitted controller](experiments/eage_hackathon_2026/final_submission/submit/safe_adaptive_growth_agent.py)

The submitted controller has this SHA-256 hash:

```text
2e884ec93b60176f49d00a3d485321d3c772a9b413b3aff3ce06b3d921991676
```

The same policy is available in the main agent tree as [`agents.finalists.risk_aware_growth`](agents/finalists/risk_aware_growth.py). That is the version used by the current matrix runner.

The name is slightly confusing. The submitted Python class is named `SafeAdaptiveGrowthAgent`, while the final policy was presented as Risk-Aware Growth or Score90. It is different from the older `safe-adaptive` finalist.

## How the game is scored

The simulator starts with $300,000, a population of 100, a town hall, seven roads, and one coal plant. An agent has to grow the city without running out of money or losing power.

The score uses the full daily history. A strong final day cannot hide a collapse earlier in the run.

| Part of the score | Weight inside the base score | Full-credit target |
| --- | ---: | ---: |
| Treasury | 30% | Profit relative to starting cash |
| Population | 30% | 400 people |
| Happiness | 10% | 1.20 |
| Renewable electricity served | 20% | 50% |
| Solvency | 10% | Positive treasury every day |

Treasury, population, and happiness each include average level, trend, and the worst 5% of days. The base score contributes 85% of the final number. Surviving for 730 days contributes the remaining 15%.

This shaped our work. We did not need a city with the highest possible population or a fully renewable grid. We needed to reach roughly 400 people early enough, keep happiness near 1.20, serve at least half of local demand with renewables, and avoid a bad cash or outage period.

## Evaluation setup

The preserved final validation used this 15-case matrix:

```text
Scenarios: baseline, economy_stress, grid_stress
Seeds:     1, 42, 101, 112, 777
Budget:    600 seconds per case
```

The policy does not read the seed or scenario name. It reacts to state returned by the simulator: treasury, population, active events, plant failures, and the next-day power preview.

There are two different horizons in the repository:

- A fixed evaluation can stop after 730 simulated days.
- A wall-time evaluation without `--days` uses the simulator default of 3650 days.

Our published near-90 result is from the 600-second wall-time evaluation. The deterministic agent completed all 3650 days in every case. A separate 730-day baseline check scored 70.81 because the city had less time to finish its growth stages. The two results should not be compared as if they used the same horizon.

## Experiment path

We kept the useful finalists in [`agents/finalists`](agents/finalists). The full development process used separate worktrees, but copying every worktree here would make the repository harder to understand and harder to run. Early figures in this section come from development notes; the final 15-case result is the archived and reproducible benchmark.

### Stable renewable city

The first reliable policies built solar, a battery, wind power, commercial jobs, housing, and parks around the starter grid. In development runs, they stayed solvent and usually reached 150 to 164 people.

They taught us four basic rules:

1. Housing without jobs does not grow the population.
2. Jobs without nearby residents do not produce enough income.
3. Parks matter because happiness controls population growth.
4. Energy equipment bought too early ties up cash before the city can use it.

This approach was safe, but it left most of the population score unused.

### Staged growth plans

We then built exact city layouts and tested different stage orders, cash floors, housing rows, commercial counts, parks, and energy additions.

House-heavy rows worked better than commercial-heavy rows. Commercial buildings add jobs and revenue, but they also add load. Too many shops made the grid fragile. The better layouts added only enough commercial capacity to support the next housing block.

Dense park placement kept happiness near the 1.20 scoring limit. A second coal plant, built before the large housing rows, removed the worst late-game failure mode. Solar and batteries were added after the city had enough income to pay for them.

One recorded development run reached 89.17. It showed that a score near 90 was possible, but that policy used oil and had only been strong on a favourable case.

### Oil-funded growth

Oil was our high-upside experiment. A good reservoir could pay for a large city, and the strongest individual oil runs were close to 90.

The downside was too large for the final submission. Surveying and drilling consumed cash before returning revenue. Poor reservoirs, badly timed wells, or an oil-price collapse could leave the city with more operating cost and power demand than it could support. Adding more wells usually made the problem worse.

The final oil finalist could still produce a high score, but its broader matrix had a much lower floor and did not stay solvent in every case. We kept it for comparison and removed oil from the submitted policy.

### Adaptive safety controls

The next step was to make growth conditional on the live state rather than a fixed day number.

We added:

- minimum treasury before each build stage;
- minimum cash left after construction;
- a reserve-margin check from the next 24-hour preview;
- a pause during heatwaves, demand surprises, and fuel shocks;
- commercial load shedding during a plant failure or predicted outage;
- one-at-a-time restoration after the grid recovered.

In development runs, removing the second coal plant dropped focused scores into the 50s and 60s. Trying to restart large growth after an economy shock caused debt on several seeds. The safer choice was to stop at a small, profitable city under economy stress.

### Learned policies

We tested learned growth rules, a linear macro policy, Cross-Entropy Method policy search, and PPO.

The learned policies did not beat the hand-built controller. Population-focused training spent too much and stayed in debt. Survival-focused training learned to avoid failure but barely grew the city. Adding oil actions made the search space harder and produced early collapses. The final comparison recorded a PPO median of about 29.8, well below the deterministic finalists.

The useful part of these experiments was the failure data. They confirmed that solvency had to behave like a hard constraint and that a small action space was easier to validate across scenarios.

## Final policy

Risk-Aware Growth is a daily state machine. It acts once per simulated day and attempts one stage at a time.

### Opening

The opening spends $215,000 on:

```text
3 solar farms
1 battery
1 wind turbine
4 commercial buildings
1 park
1 house
```

This gives the starter population jobs, adds renewable generation and storage, and starts the cash flow needed for later construction.

### Build stages

The complete plan adds the following assets beyond the free starter grid:

| Asset | Count |
| --- | ---: |
| Houses | 44 |
| Commercial buildings | 26 |
| Parks | 20 |
| Roads | 56 |
| Solar farms | 15 |
| Batteries | 9 |
| Wind turbines | 1 |
| Coal plants | 1 |

The scripted capital cost is $1,623,000, but the controller does not spend that money at once. It builds two small districts, adds a housing buffer, installs the second coal plant and road backbone, then alternates larger housing rows with solar and battery blocks.

Each stage has a treasury floor and a required post-build reserve. The reserve rises early in the game, during weather or load events, and when happiness is low. Demand stages also require a safe next-day power preview.

The later housing rows are allowed only after the grid has two coal plants, at least seven solar farms, and at least three batteries.

### Failure handling

The action order is simple:

1. Detect economy stress.
2. Shed commercial load if a plant has failed.
3. Shed commercial load if the next-day preview contains a brownout or blackout.
4. Restore one shed site when cash and the power preview are safe.
5. Otherwise try the next build stage.

When it has to shed load, the controller removes the staffed commercial site with the lowest estimated value and checks the grid again. It removes at most three sites in the large city and at most eight in the small economy-stress city.

### Economy stress

A fuel-cost shock, crude-price collapse, or crude price at or below $20 switches the policy into economy mode. It completes only the three early growth stages and then stops expanding.

That is why the final matrix has two clear outcomes:

- baseline and grid stress finish with 434 people;
- economy stress finishes with 163 or 164 people.

The lower population is intentional. Attempts to resume growth after the shock produced insolvency. The small city preserved a positive treasury on all five economy-stress seeds.

## Published result

The original June 8 result files are committed unchanged:

- [aggregate summary](experiments/eage_hackathon_2026/results/score90_best_summary.json)
- [15 per-case rows](experiments/eage_hackathon_2026/results/score90_best_results.csv)

### Overall

| Metric | Result |
| --- | ---: |
| Cases completed | 15 / 15 |
| Failed cases | 0 |
| Median score | 89.2186 |
| Mean score | 85.5162 |
| Best score | 89.8789 |
| Worst score | 72.5258 |
| Median population | 434 |
| Mean population | 343.9 |
| Mean final treasury | $2,648,441 |
| Minimum solvency | 1.000 |
| Days completed in every case | 3650 |

### By scenario

| Scenario | Mean | Median | Worst | Best | Final population |
| --- | ---: | ---: | ---: | ---: | ---: |
| Baseline | 89.65 | 89.65 | 89.35 | 89.88 | 434 |
| Economy stress | 78.13 | 79.30 | 72.53 | 80.48 | 163–164 |
| Grid stress | 88.78 | 89.22 | 86.50 | 89.73 | 434 |

The best case was baseline seed 112:

```text
Score:      89.8788813651468
Population: 434
Housing:    452
Jobs:       434
Happiness:  1.2227700110975839
Treasury:   $3,648,411.87
Solvency:   1.0
Days:       3650
```

### Final comparison

| Approach | Median | Mean | Worst | Best | Decision |
| --- | ---: | ---: | ---: | ---: | --- |
| Risk-Aware Growth | 89.22 | 85.52 | 72.53 | 89.88 | Submitted |
| Safe Adaptive fallback | 79.96 | 81.87 | 72.53 | 88.53 | Safe, less growth |
| Stable renewable mix | 80.56 | 79.75 | 72.48 | 80.86 | Too little population |
| Oil exploration | 79.93 | 75.78 | 48.14 | 89.69 | High upside, weak floor |
| Adaptive safety aggressive | 77.65 | 73.84 | 45.75 | 88.34 | Insolvency risk |
| CEM survival | 66.73 | 60.79 | 44.28 | 66.73 | Survived, little growth |
| CEM population | 60.50 | 60.60 | 57.83 | 64.62 | Persistent debt |
| PPO artifact | 29.80 | n/a | 21.23 | n/a | Not competitive |

## Reproduce the result

### 1. Clone and install

```bash
git clone https://github.com/gouthamindukuri/agent-energy-arena.git
cd agent-energy-arena
uv sync --extra dev
```

All commands below run in process through FastAPI's test client. They do not need Docker or a separate web server.

### 2. Smoke test

This checks imports, agent construction, simulation, scoring, and result export without waiting for a full game.

```bash
uv run python tools/finalist_eval.py \
  --agents risk-aware-growth \
  --seeds 112 \
  --scenarios baseline \
  --days 30 \
  --no-time-budget \
  --workers 1 \
  --out-dir /tmp/eage-smoke
```

Expected: one successful case and zero failures.

### 3. Fixed 730-day check

```bash
uv run python tools/finalist_eval.py \
  --agents risk-aware-growth \
  --seeds 112 \
  --scenarios baseline \
  --days 730 \
  --no-time-budget \
  --workers 1 \
  --out-dir /tmp/eage-730
```

Expected values:

```text
Score:      70.8087330049202
Population: 308
Treasury:   $166,599.48
Failures:   0
```

### 4. Full winning matrix

```bash
uv run python tools/finalist_eval.py \
  --agents risk-aware-growth \
  --seeds 1,42,101,112,777 \
  --scenarios baseline,economy_stress,grid_stress \
  --time-budget 600 \
  --workers 10 \
  --out-dir /tmp/eage-winning-matrix
```

The wall time depends on the machine. The score does not. All 15 cases must reach 3650 days before the 600-second limit.

### 5. Validate the output

```bash
uv run python experiments/eage_hackathon_2026/validate_results.py \
  /tmp/eage-winning-matrix/summary.json \
  /tmp/eage-winning-matrix/results.csv
```

Expected output:

```text
PASS: 15 cases match the published winning result
```

To verify the exact archived submission instead of the maintained finalist module:

```bash
PYTHONPATH=experiments/eage_hackathon_2026/final_submission \
uv run python evaluate.py \
  --agent submit.agent \
  --scenario scenarios.baseline \
  --seed 112 \
  --days 30
```

## Result provenance and known reporting issue

The official summary and CSV came from the final June 8 matrix. Each case ran in its own temporary directory, so the exported run IDs are not unique and the temporary daily traces no longer exist. The per-case scores, final states, and aggregate metrics were retained.

The old matrix exporter wrote `renewable_share=0.0` because it looked for a field that was not present in `final_state.json`. This did not change the score. The evaluator calculated renewable share from the recorded state history before returning the score. The current `tools/finalist_eval.py` reads the scored component correctly. For that reason, the validation script does not compare the stale renewable-share column.

The old CSV also contains `housing_capacity` and `jobs_total`, which the current runner does not export. Those two archive-only columns are kept for provenance but are not part of the automated comparison. The validator requires both generated files and compares every deterministic aggregate plus every per-case field emitted by the current runner. It ignores run IDs and wall-clock timings.

## Repository map

| Path | Purpose |
| --- | --- |
| [`agents/finalists/risk_aware_growth.py`](agents/finalists/risk_aware_growth.py) | Maintained winning policy |
| [`tools/finalist_eval.py`](tools/finalist_eval.py) | Current matrix runner |
| [`experiments/eage_hackathon_2026/final_submission`](experiments/eage_hackathon_2026/final_submission) | Exact submitted source snapshot |
| [`experiments/eage_hackathon_2026/results`](experiments/eage_hackathon_2026/results) | Original compact result files |
| [`experiments/eage_hackathon_2026/validate_results.py`](experiments/eage_hackathon_2026/validate_results.py) | Result checker |
| [`agents/finalists`](agents/finalists) | Other preserved finalists |

## License and credit

The arena is based on [ovcharenkoo/agent-energy-arena](https://github.com/ovcharenkoo/agent-energy-arena) and is distributed under the repository's MIT license. Prometheus developed and evaluated the winning agent described here for EAGE Hackthon 2026.
