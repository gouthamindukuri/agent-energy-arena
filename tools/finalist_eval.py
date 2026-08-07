"""Run finalist agents on a fixed seed/scenario matrix.

Examples:

    uv run python tools/finalist_eval.py --list-agents

    uv run python tools/finalist_eval.py \
      --agents all \
      --seeds 112 \
      --scenarios baseline \
      --days 730 \
      --no-time-budget \
      --workers 6

    uv run python tools/finalist_eval.py \
      --agents all \
      --seeds 112 \
      --scenarios baseline \
      --workers 6 \
      --time-budget 600

    uv run python tools/finalist_eval.py \
      --agents risk-aware-growth,oil-exploration \
      --seeds 1,42,101,112,777 \
      --scenarios baseline,economy_stress,grid_stress \
      --workers 10
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import statistics
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from agents.finalists.cem_action_space import ACTIONS as CEM_ACTIONS
from agents.finalists.cem_action_space import apply_action, legal_action_mask
from agents.finalists.registry import FINALISTS, RUNNABLE_IDS
from world.scenario import load_scenario
from world.scoring import compute_score
from world.sim import World

DEFAULT_SEEDS = (1, 42, 101, 112, 777)
DEFAULT_SCENARIOS = ("scenarios.baseline", "scenarios.economy_stress", "scenarios.grid_stress")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _csv_ints(raw: str) -> tuple[int, ...]:
    return tuple(int(item.strip()) for item in raw.split(",") if item.strip())


def _scenario_name(raw: str) -> str:
    value = raw.strip()
    if not value:
        raise ValueError("empty scenario")
    return value if value.startswith("scenarios.") else f"scenarios.{value}"


def _csv_scenarios(raw: str) -> tuple[str, ...]:
    return tuple(_scenario_name(item) for item in raw.split(",") if item.strip())


def _select_agents(raw: str, *, include_archived: bool) -> tuple[str, ...]:
    if raw.strip() == "all":
        return tuple(FINALISTS) if include_archived else RUNNABLE_IDS
    selected = tuple(item.strip() for item in raw.split(",") if item.strip())
    unknown = [agent_id for agent_id in selected if agent_id not in FINALISTS]
    if unknown:
        raise ValueError(f"unknown agents: {unknown}; choices: {sorted(FINALISTS)}")
    if not include_archived:
        selected = tuple(
            agent_id for agent_id in selected if FINALISTS[agent_id].mode != "archived"
        )
    return selected


def _json_line(stdout: str) -> dict[str, Any]:
    for line in reversed(stdout.splitlines()):
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            return json.loads(line)
    raise RuntimeError(f"no JSON result line found:\n{stdout[-2000:]}")


def _component(payload: dict[str, Any], name: str) -> float | None:
    value = payload.get("score", {}).get("components", {}).get(name)
    return None if value is None else float(value)


def _run_module_agent(job: dict[str, Any]) -> dict[str, Any]:
    root = Path(job["root"])
    finalist = FINALISTS[str(job["agent_id"])]
    assert finalist.module is not None
    scenario = str(job["scenario"])
    seed = int(job["seed"])
    with tempfile.TemporaryDirectory(
        prefix=f"{finalist.agent_id}-{scenario.rsplit('.', 1)[-1]}-{seed}-"
    ) as temp:
        env = os.environ.copy()
        env["PYTHONPATH"] = str(root)
        command = [
            sys.executable,
            str(root / "evaluate.py"),
            "--agent",
            finalist.module,
            "--scenario",
            scenario,
            "--seed",
            str(seed),
        ]
        if job.get("time_budget") is not None:
            command.extend(["--time-budget", str(int(job["time_budget"]))])
        if job.get("days") is not None:
            command.extend(["--days", str(int(job["days"]))])
        started = time.monotonic()
        proc = subprocess.run(
            command,
            cwd=temp,
            text=True,
            capture_output=True,
            timeout=int(job["timeout"]),
            check=False,
            env=env,
        )
        elapsed = time.monotonic() - started
        if proc.returncode != 0:
            return _failed_row(job, elapsed, proc.stderr[-4000:] + "\n" + proc.stdout[-4000:])
        payload = _json_line(proc.stdout)
        final_state: dict[str, Any] = {}
        run_id = payload.get("run_id")
        if run_id:
            final_path = Path(temp) / "runs" / str(run_id) / "final_state.json"
            if final_path.exists():
                final_state = json.loads(final_path.read_text())
        score = payload.get("time_scaled_score")
        if score is None:
            score = payload.get("score", {}).get("score", 0.0)
        return {
            **_base_row(job),
            "ok": True,
            "score": float(score),
            "raw_score": float(payload.get("score", {}).get("score", score)),
            "treasury": float(final_state.get("treasury", payload.get("treasury", 0.0))),
            "population": int(final_state.get("population", payload.get("population", 0))),
            "happiness": float(final_state.get("happiness", payload.get("happiness", 0.0))),
            "solvency": _component(payload, "solvency"),
            "renewable_share": _component(payload, "renewable_share"),
            "days_advanced": int(payload.get("days_advanced", final_state.get("day", 0))),
            "final_day": int(final_state.get("day", payload.get("days_advanced", 0))),
            "wall_time_seconds": float(payload.get("wall_time_seconds", elapsed)),
            "runtime_seconds": elapsed,
            "run_id": run_id,
            "error": "",
        }


def _run_cem_policy(job: dict[str, Any]) -> dict[str, Any]:
    root = Path(job["root"])
    finalist = FINALISTS[str(job["agent_id"])]
    assert finalist.policy is not None
    started = time.monotonic()
    try:
        row = _cem_run_one(
            policy_path=root / finalist.policy,
            seed=int(job["seed"]),
            scenario_name=str(job["scenario"]),
            max_days=int(job.get("days") or 3650),
        )
    except Exception as exc:  # noqa: BLE001 - preserve failed row context.
        return _failed_row(job, time.monotonic() - started, repr(exc))
    return {
        **_base_row(job),
        "ok": True,
        "score": float(row["score"]),
        "raw_score": float(row["score"]),
        "treasury": float(row["treasury"]),
        "population": int(row["population"]),
        "happiness": float(row["happiness"]),
        "solvency": float(row["solvency"]),
        "renewable_share": float(row["renewable_share"]),
        "days_advanced": int(row["days"]),
        "final_day": int(row["days"]),
        "wall_time_seconds": time.monotonic() - started,
        "runtime_seconds": time.monotonic() - started,
        "run_id": "",
        "error": "",
    }


def _failed_row(job: dict[str, Any], elapsed: float, error: str) -> dict[str, Any]:
    return {
        **_base_row(job),
        "ok": False,
        "score": None,
        "raw_score": None,
        "treasury": None,
        "population": None,
        "happiness": None,
        "solvency": None,
        "renewable_share": None,
        "days_advanced": None,
        "final_day": None,
        "wall_time_seconds": elapsed,
        "runtime_seconds": elapsed,
        "run_id": "",
        "error": error,
    }


def _base_row(job: dict[str, Any]) -> dict[str, Any]:
    finalist = FINALISTS[str(job["agent_id"])]
    return {
        "agent_id": finalist.agent_id,
        "agent_name": finalist.name,
        "mode": finalist.mode,
        "scenario": str(job["scenario"]),
        "seed": int(job["seed"]),
    }


def _sigmoid(value: float) -> float:
    if value >= 0:
        z = np.exp(-value)
        return float(1.0 / (1.0 + z))
    z = np.exp(value)
    return float(z / (1.0 + z))


def _load_cem_policy(path: Path) -> tuple[np.ndarray, list[str], list[str], float]:
    with np.load(path, allow_pickle=False) as data:
        params = np.asarray(data["params"], dtype=np.float32)
        actions = [str(item) for item in data["actions"].tolist()]
        features = [str(item) for item in data["features"].tolist()]
    cash_floor = 25_000.0 + 325_000.0 * _sigmoid(float(params[-1]))
    weights = params[:-1].reshape(len(actions), len(features))
    return weights, actions, features, cash_floor


def _cem_run_one(
    *,
    policy_path: Path,
    seed: int,
    scenario_name: str,
    max_days: int,
) -> dict[str, Any]:
    weights, actions, features, cash_floor = _load_cem_policy(policy_path)
    world = World(runs_root=None, seed_starter_grid=True)
    world.reset(
        seed=seed,
        scenario=load_scenario(scenario_name),
        scenario_dotted_path=scenario_name,
    )
    current_index = {name: idx for idx, name in enumerate(CEM_ACTIONS)}
    snapshots: list[dict[str, float]] = []
    while world.state.day < max_days:
        feature_vec = np.asarray(
            [_cem_feature_map(world, features).get(name, 0.0) for name in features],
            dtype=np.float32,
        )
        current_mask = legal_action_mask(world, min_cash_after=cash_floor)
        saved_mask = np.asarray(
            [
                bool(current_mask[current_index[name]]) if name in current_index else False
                for name in actions
            ],
            dtype=np.bool_,
        )
        scores = np.where(saved_mask, weights @ feature_vec, -1.0e9)
        action_name = actions[int(np.argmax(scores))]
        if action_name in current_index:
            apply_action(world, current_index[action_name])
        world.step(days=1)
        snapshots.append(_cem_snapshot(world))
        if world.state.treasury < -1_000_000.0:
            break
        if world.state.day > 90 and world.state.population <= 1.0:
            break
    score = compute_score(snapshots, world.config.starting_cash) if snapshots else {}
    components = score.get("components", {})
    if not isinstance(components, dict):
        components = {}
    return {
        "days": int(world.state.day),
        "score": float(score.get("score", 0.0)),
        "treasury": float(world.state.treasury),
        "population": int(world.state.population),
        "happiness": float(world.state.happiness),
        "solvency": float(components.get("solvency", 0.0)),
        "renewable_share": float(components.get("renewable_share", 0.0)),
    }


def _cem_feature_map(world: World, feature_names: list[str]) -> dict[str, float]:
    state = world.state
    counts: dict[str, int] = {}
    for tile in state.tiles:
        counts[tile.type] = counts.get(tile.type, 0) + 1
    population = float(state.population)
    housing = float(sum(tile.housing_capacity for tile in state.tiles))
    jobs = float(sum(tile.jobs for tile in state.tiles))
    renewable_share = state.cumulative_renewable_served_kwh / max(
        1.0, state.cumulative_total_served_kwh
    )
    event_types = {str(event.get("type")) for event in state.active_events}
    values = {
        "bias": 1.0,
        "day_3650": min(1.0, state.day / 3650.0),
        "treasury_300k": state.treasury / 300_000.0,
        "treasury_delta_1m": (state.treasury - 300_000.0) / 1_000_000.0,
        "population_400": population / 400.0,
        "happiness_1p2": state.happiness / 1.2,
        "housing_gap_120": (housing - population) / 120.0,
        "jobs_gap_120": (jobs - population) / 120.0,
        "renewable_deficit": max(0.0, 0.5 - renewable_share) / 0.5,
        "last_blackout_24": float(state.yesterday_blackout_hours) / 24.0,
        "last_brownout_24": float(state.yesterday_brownout_hours) / 24.0,
        "carbon_price_100": float(state.carbon_price) / 100.0,
        "road_160": counts.get("road", 0) / 160.0,
        "house_50": counts.get("house", 0) / 50.0,
        "commercial_40": counts.get("commercial", 0) / 40.0,
        "industrial_12": counts.get("industrial", 0) / 12.0,
        "park_20": counts.get("park", 0) / 20.0,
        "solar_24": counts.get("solar_farm", 0) / 24.0,
        "wind_16": counts.get("wind_turbine", 0) / 16.0,
        "battery_8": counts.get("battery", 0) / 8.0,
        "coal_2": counts.get("coal_plant", 0) / 2.0,
        "wells_6": len(state.wells) / 6.0,
        "revealed_oil_100k": 0.0,
        "heatwave": 1.0 if "heatwave" in event_types else 0.0,
        "fuel_price_shock": 1.0 if "fuel_price_shock" in event_types else 0.0,
        "demand_surprise": 1.0 if "demand_surprise" in event_types else 0.0,
        "plant_failure": 1.0 if "plant_failure" in event_types else 0.0,
    }
    if "revealed_oil_100k" in feature_names:
        state_view = world.state_dict()
        values["revealed_oil_100k"] = (
            float(
                state_view.get("reservoirs_revealed", {}).get(
                    "total_estimated_oil_remaining_bbl", 0.0
                )
            )
            / 100_000.0
        )
    return values


def _cem_snapshot(world: World) -> dict[str, float]:
    state = world.state
    return {
        "treasury": float(state.treasury),
        "population": float(state.population),
        "happiness": float(state.happiness),
        "cumulative_renewable_served_kwh": float(state.cumulative_renewable_served_kwh),
        "cumulative_total_served_kwh": float(state.cumulative_total_served_kwh),
    }


def _run_job(job: dict[str, Any]) -> dict[str, Any]:
    finalist = FINALISTS[str(job["agent_id"])]
    if finalist.mode == "module":
        return _run_module_agent(job)
    if finalist.mode == "cem":
        return _run_cem_policy(job)
    return _failed_row(job, 0.0, f"{finalist.agent_id} is archived and not runnable")


def _stats(rows: list[dict[str, Any]]) -> dict[str, Any]:
    good = [row for row in rows if row.get("ok")]
    out: dict[str, Any] = {"n": len(rows), "ok": len(good), "failed": len(rows) - len(good)}
    for metric in (
        "score",
        "raw_score",
        "treasury",
        "population",
        "happiness",
        "solvency",
        "renewable_share",
        "days_advanced",
        "wall_time_seconds",
    ):
        values = [float(row[metric]) for row in good if row.get(metric) is not None]
        if values:
            out[f"{metric}_mean"] = statistics.fmean(values)
            out[f"{metric}_median"] = statistics.median(values)
            out[f"{metric}_min"] = min(values)
            out[f"{metric}_max"] = max(values)
    return out


def _write_outputs(out_dir: Path, rows: list[dict[str, Any]], started_at: float) -> None:
    rows.sort(key=lambda row: (row["agent_id"], row["scenario"], int(row["seed"])))
    out_dir.mkdir(parents=True, exist_ok=True)
    with (out_dir / "results.jsonl").open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, sort_keys=True) + "\n")
    keys = sorted({key for row in rows for key in row})
    with (out_dir / "results.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=keys)
        writer.writeheader()
        writer.writerows(rows)
    summary = {
        "created_at": datetime.now(UTC).isoformat(),
        "elapsed_seconds": time.monotonic() - started_at,
        "overall": _stats(rows),
        "by_agent": {
            agent_id: _stats([row for row in rows if row["agent_id"] == agent_id])
            for agent_id in sorted({row["agent_id"] for row in rows})
        },
        "by_agent_scenario": {
            f"{agent_id}|{scenario}": _stats(
                [row for row in rows if row["agent_id"] == agent_id and row["scenario"] == scenario]
            )
            for agent_id in sorted({row["agent_id"] for row in rows})
            for scenario in sorted({row["scenario"] for row in rows})
        },
    }
    (out_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _print_agent_list() -> None:
    for agent_id, finalist in FINALISTS.items():
        runnable = "yes" if finalist.mode != "archived" else "no"
        module = finalist.module or finalist.policy or ""
        print(
            f"{agent_id:20s} {finalist.name:22s} mode={finalist.mode:8s} "
            f"runnable={runnable:3s} {module}"
        )
        if finalist.note:
            print(f"{'':20s} note: {finalist.note}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list-agents", action="store_true")
    parser.add_argument("--agents", default="all", help="Comma-separated agent ids, or all.")
    parser.add_argument("--seeds", default=",".join(str(seed) for seed in DEFAULT_SEEDS))
    parser.add_argument("--scenarios", default=",".join(DEFAULT_SCENARIOS))
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--time-budget", type=int, default=600)
    parser.add_argument(
        "--no-time-budget",
        action="store_true",
        help="Do not pass --time-budget to evaluate.py. Use with --days 730 for fixed-horizon runs.",
    )
    parser.add_argument("--timeout", type=int, default=720)
    parser.add_argument("--days", type=int, default=None)
    parser.add_argument("--include-archived", action="store_true")
    parser.add_argument("--out-dir", type=Path, default=None)
    args = parser.parse_args()

    if args.list_agents:
        _print_agent_list()
        return 0

    root = _repo_root()
    agent_ids = _select_agents(str(args.agents), include_archived=bool(args.include_archived))
    seeds = _csv_ints(str(args.seeds))
    scenarios = _csv_scenarios(str(args.scenarios))
    time_budget = None if args.no_time_budget else int(args.time_budget)
    stamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    out_dir = args.out_dir or (root / "runs" / "finalist_eval" / stamp)
    jobs = [
        {
            "root": str(root),
            "agent_id": agent_id,
            "seed": seed,
            "scenario": scenario,
            "time_budget": time_budget,
            "timeout": int(args.timeout),
            "days": args.days,
        }
        for agent_id in agent_ids
        for scenario in scenarios
        for seed in seeds
    ]
    print(
        json.dumps(
            {
                "jobs": len(jobs),
                "workers": int(args.workers),
                "agents": list(agent_ids),
                "seeds": list(seeds),
                "scenarios": list(scenarios),
                "out_dir": str(out_dir),
            },
            sort_keys=True,
        ),
        flush=True,
    )
    started_at = time.monotonic()
    rows: list[dict[str, Any]] = []
    with ProcessPoolExecutor(max_workers=int(args.workers)) as pool:
        futures = {pool.submit(_run_job, job): job for job in jobs}
        for future in as_completed(futures):
            row = future.result()
            rows.append(row)
            print(
                f"{'ok' if row.get('ok') else 'fail'} {row['agent_id']} "
                f"{row['scenario']} seed={row['seed']} score={row.get('score')} "
                f"pop={row.get('population')} treasury={row.get('treasury')}",
                flush=True,
            )
    _write_outputs(out_dir, rows, started_at)
    failed = sum(1 for row in rows if not row.get("ok"))
    print(json.dumps({"out_dir": str(out_dir), "failed": failed}, sort_keys=True), flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
