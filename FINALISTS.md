# Finalist Agent Evaluation Guide

This repo now contains the finished agents in one place, under:

```text
agents/finalists/
```

Use this repo as the single core evaluation workspace when a seed and scenario
are revealed.

## Agent IDs

| Agent ID | Presentation Name | Runner Mode | Notes |
| --- | --- | --- | --- |
| `risk-aware-growth` | Risk-Aware Growth | `evaluate.py` module | Final submission candidate |
| `safe-adaptive` | Safe Adaptive | `evaluate.py` module | Robust deterministic fallback |
| `renewables-mix` | Renewables Mix | `evaluate.py` module | Conservative renewable/economy mix |
| `oil-exploration` | Oil Exploration | `evaluate.py` module | Oil_6 fixed bundle |
| `safety-first` | Safety First | `evaluate.py` module | Defaults to aggressive safety policy |
| `cem-rl-survival` | CEM RL Survival | saved CEM policy | Runs through `tools/finalist_eval.py` |
| `cem-rl-population` | CEM RL Population | saved CEM policy | Runs through `tools/finalist_eval.py` |
| `ppo-rl` | PPO RL | archived only | Not runnable as a finalist; checkpoint was not preserved |

List agents:

```bash
uv run python tools/finalist_eval.py --list-agents
```

## Run One Agent Directly

For standard `evaluate.py` agents:

```bash
uv run python evaluate.py \
  --agent agents.finalists.risk_aware_growth \
  --scenario scenarios.baseline \
  --seed 112 \
  --time-budget 600
```

Other direct module paths:

```text
agents.finalists.safe_adaptive
agents.finalists.renewables_mix.agent
agents.finalists.oil_exploration.agent_oil_6
agents.finalists.safety_first
```

The CEM policies are not `BaseAgent` modules. Use the unified finalist runner
for them.

## Run All Finalists On A Revealed Case

When the organizers reveal one scenario and one seed, run both evaluation modes.

### Mode 1: Fixed 730-Day Evaluation

This evaluates the same seed/scenario for exactly 730 simulated days.

```bash
uv run python tools/finalist_eval.py \
  --agents all \
  --seeds <SEED> \
  --scenarios <SCENARIO> \
  --days 730 \
  --no-time-budget \
  --workers 7
```

### Mode 2: Full 10-Minute Wall-Time Evaluation

This evaluates under the 600-second wall-clock budget. Do not pass `--days` in
this mode; let the agent advance as far as it can within the time budget.

```bash
uv run python tools/finalist_eval.py \
  --agents all \
  --seeds <SEED> \
  --scenarios <SCENARIO> \
  --time-budget 600 \
  --workers 7
```

Examples:

```bash
uv run python tools/finalist_eval.py \
  --agents all \
  --seeds 112 \
  --scenarios baseline \
  --days 730 \
  --no-time-budget \
  --workers 7

uv run python tools/finalist_eval.py \
  --agents all \
  --seeds 112 \
  --scenarios baseline \
  --time-budget 600 \
  --workers 7

uv run python tools/finalist_eval.py \
  --agents all \
  --seeds 42 \
  --scenarios economy_stress \
  --days 730 \
  --no-time-budget \
  --workers 7

uv run python tools/finalist_eval.py \
  --agents all \
  --seeds 42 \
  --scenarios economy_stress \
  --time-budget 600 \
  --workers 7
```

Scenario names can be either short or dotted:

```text
baseline
economy_stress
grid_stress

scenarios.baseline
scenarios.economy_stress
scenarios.grid_stress
```

## Run A Full Matrix

Fixed 730-day matrix:

```bash
uv run python tools/finalist_eval.py \
  --agents all \
  --seeds 1,42,101,112,777 \
  --scenarios baseline,economy_stress,grid_stress \
  --days 730 \
  --no-time-budget \
  --workers 10
```

Full 10-minute matrix:

```bash
uv run python tools/finalist_eval.py \
  --agents all \
  --seeds 1,42,101,112,777 \
  --scenarios baseline,economy_stress,grid_stress \
  --time-budget 600 \
  --workers 10
```

To compare only the strongest finalists:

```bash
uv run python tools/finalist_eval.py \
  --agents risk-aware-growth,oil-exploration,safe-adaptive \
  --seeds 1,42,101,112,777 \
  --scenarios baseline,economy_stress,grid_stress \
  --time-budget 600 \
  --workers 10
```

## Output Files

Each run creates:

```text
runs/finalist_eval/<timestamp>/results.csv
runs/finalist_eval/<timestamp>/results.jsonl
runs/finalist_eval/<timestamp>/summary.json
```

The runner prints the output directory at the end:

```text
{"failed": 0, "out_dir": "runs/finalist_eval/<timestamp>"}
```

## Known 15-Run Results

These are the final comparison results from the fixed matrix:

| Approach | Median Score | Mean Score | Best | Worst | Median Pop | Mean Pop | Mean Treasury | Mean Solvency |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Risk-Aware Growth | 89.22 | 85.52 | 89.88 | 72.53 | 434 | 343.9 | $2,648,441 | 1.000 |
| Safe Adaptive | 79.96 | 81.87 | 88.53 | 72.53 | 308 | 315.1 | $1,936,851 | 1.000 |
| Renewables Mix | 80.56 | 79.75 | 80.86 | 72.48 | 156 | 156.0 | $2,747,149 | 1.000 |
| Oil Exploration | 79.93 | 75.78 | 89.69 | 48.14 | 437 | 298.8 | $157,623 | 0.816 |
| Safety First | 77.65 | 73.84 | 88.34 | 45.75 | 400 | 309.3 | $785,606 | 0.784 |
| CEM RL Survival | 66.73 | 60.79 | 66.73 | 44.28 | 36 | 39.7 | -$171,827 | 0.970 |
| CEM RL Population | 60.50 | 60.60 | 64.62 | 57.83 | 90 | 87.2 | -$833,020 | 0.531 |
| PPO RL | 29.80 | n/a | n/a | 21.23 | 17.5 | n/a | n/a | low |

## Final Recommendation

Use `risk-aware-growth` as the default submission.

Why:

```text
highest median score
highest mean score
full solvency across the 15-run matrix
3650 days reached in every tested run
near-90 baseline/grid performance
economy stress remains solvent instead of collapsing
```

If the revealed scenario/seed strongly favors oil, `oil-exploration` can show
very high population and near-90 scores. It is not the default because its
seed-42 failure mode is severe.

## Smoke Check

This repo was smoke-tested with:

```bash
uv run python tools/finalist_eval.py \
  --agents all \
  --seeds 1 \
  --scenarios baseline \
  --days 30 \
  --no-time-budget \
  --workers 4 \
  --out-dir /tmp/eage_finalist_smoke_all
```

All runnable finalists completed the smoke run.
