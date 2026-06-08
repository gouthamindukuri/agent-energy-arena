# Reproduce Finalist Results

This file is the single reproduction guide for the finalist agents and
comparison runs.

## Repository

```text
fork:   https://github.com/gouthamindukuri/agent-energy-arena
parent: https://github.com/ovcharenkoo/agent-energy-arena
branch: main
```

The consolidated finalist code lives in:

```text
agents/finalists/
tools/finalist_eval.py
FINALISTS.md
```

## Environment

Use the repo dependency manager:

```bash
uv sync --all-extras
```

If the environment already exists, this is enough:

```bash
uv run python tools/finalist_eval.py --list-agents
```

## Finalist Agents

| Agent ID | Name | Mode | Notes |
| --- | --- | --- | --- |
| `risk-aware-growth` | Risk-Aware Growth | `evaluate.py` module | Default final submission candidate |
| `safe-adaptive` | Safe Adaptive | `evaluate.py` module | Robust deterministic fallback |
| `renewables-mix` | Renewables Mix | `evaluate.py` module | Conservative renewable/economy mix |
| `oil-exploration` | Oil Exploration | `evaluate.py` module | Oil exploration variant, high upside but less stable |
| `safety-first` | Safety First | `evaluate.py` module | Aggressive safety-envelope policy |
| `cem-rl-survival` | CEM RL Survival | saved CEM policy | Runnable through `tools/finalist_eval.py` |
| `cem-rl-population` | CEM RL Population | saved CEM policy | Runnable through `tools/finalist_eval.py` |
| `ppo-rl` | PPO RL | archived only | Historical result only; no runnable checkpoint preserved |

The direct submission module for the best agent is:

```text
agents.finalists.risk_aware_growth
```

Run it directly:

```bash
uv run python evaluate.py \
  --agent agents.finalists.risk_aware_growth \
  --scenario scenarios.baseline \
  --seed 112 \
  --time-budget 600
```

## Evaluation Matrix

The standard comparison matrix uses five fixed seeds and three scenarios:

```text
seeds:     1, 42, 101, 112, 777
scenarios: baseline, economy_stress, grid_stress
jobs:      5 * 3 = 15 per agent
```

Scenario names can be passed either as short names or dotted module names:

```text
baseline
economy_stress
grid_stress

scenarios.baseline
scenarios.economy_stress
scenarios.grid_stress
```

## Reproduce Full 10-Minute Results

This is the main hackathon-style evaluation mode. It gives each agent a
600-second wall-clock budget and lets it advance as many simulated days as it
can.

```bash
uv run python tools/finalist_eval.py \
  --agents all \
  --seeds 1,42,101,112,777 \
  --scenarios baseline,economy_stress,grid_stress \
  --time-budget 600 \
  --workers 10
```

For only the strongest practical candidates:

```bash
uv run python tools/finalist_eval.py \
  --agents risk-aware-growth,safe-adaptive,oil-exploration \
  --seeds 1,42,101,112,777 \
  --scenarios baseline,economy_stress,grid_stress \
  --time-budget 600 \
  --workers 10
```

## Reproduce Fixed 730-Day Results

The organizers also suggested checking a fixed 730-day horizon. In this mode,
use `--days 730` and disable the wall-time budget passed to `evaluate.py`.

```bash
uv run python tools/finalist_eval.py \
  --agents all \
  --seeds 1,42,101,112,777 \
  --scenarios baseline,economy_stress,grid_stress \
  --days 730 \
  --no-time-budget \
  --workers 10
```

For a single revealed seed/scenario:

```bash
uv run python tools/finalist_eval.py \
  --agents all \
  --seeds <SEED> \
  --scenarios <SCENARIO> \
  --days 730 \
  --no-time-budget \
  --workers 7
```

And for the 10-minute revealed case:

```bash
uv run python tools/finalist_eval.py \
  --agents all \
  --seeds <SEED> \
  --scenarios <SCENARIO> \
  --time-budget 600 \
  --workers 7
```

## Output Files

Each `tools/finalist_eval.py` run writes:

```text
runs/finalist_eval/<timestamp>/results.csv
runs/finalist_eval/<timestamp>/results.jsonl
runs/finalist_eval/<timestamp>/summary.json
```

The `runs/` directory is intentionally ignored by git.

## Known 15-Run 10-Minute Comparison

These are the final comparison results from the 15-case
seed/scenario matrix under the 600-second wall-time evaluation setup.

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

Best individual observed Risk-Aware Growth run:

```text
scenario:   baseline
seed:       112
score:      89.8788813651468
population: 434
happiness:  1.2227700110975839
treasury:   $3,648,411.87
solvency:   1.0
days:       3650
```

## Interpretation

`risk-aware-growth` is the default final agent because it had the strongest
overall score profile, full solvency across the tested 15-run matrix, and the
best balance between population growth and treasury safety.

It is a deterministic state-based controller. It starts from a stable
renewable/coal-backed city shape, grows housing and jobs in stages, and gates
each growth phase on treasury floor, reserve, supply/demand forecast, active
events, and outage risk. It avoids oil in the default version because oil
provided high upside on favorable seeds but created severe downside on dry or
badly timed seeds.

`oil-exploration` is preserved because it can be excellent on favorable oil
layouts. It is not the default because the oil search can still fail badly on
some seed/scenario combinations.

The CEM policies are saved learned-policy artifacts. They are useful for
comparison but are not direct `evaluate.py` module submissions.

## Validation Commands

Before committing, this repo was checked with:

```bash
uv lock --check
uv run ruff check agents/finalists tools/finalist_eval.py
uv run python -m py_compile $(find agents/finalists -name '*.py' -print) tools/finalist_eval.py
uv run python tools/finalist_eval.py --list-agents
uv run pytest
```

Observed test result:

```text
973 passed, 3 deselected, 1 warning
```

Functional smoke command:

```bash
uv run python tools/finalist_eval.py \
  --agents all \
  --seeds 1 \
  --scenarios baseline \
  --days 10 \
  --no-time-budget \
  --workers 4 \
  --out-dir /tmp/eage_finalist_smoke_all
```

Observed smoke result:

```text
7 runnable finalists completed
failed: 0
```

Fixed-horizon sanity check for the final candidate:

```bash
uv run python tools/finalist_eval.py \
  --agents risk-aware-growth \
  --seeds 112 \
  --scenarios baseline \
  --days 730 \
  --no-time-budget \
  --workers 1 \
  --out-dir /tmp/eage_rag_730
```

Observed result:

```text
risk-aware-growth scenarios.baseline seed=112
score:      70.80873300492024
population: 308
treasury:   $166,599.48
failed:     0
```
