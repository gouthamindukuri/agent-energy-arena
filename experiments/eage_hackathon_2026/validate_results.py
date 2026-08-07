"""Compare an EAGE matrix run with the published winning result."""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Any

_EXCLUDED_SUMMARY_PREFIXES = ("renewable_share_", "wall_time_seconds_")
_EXPECTED_AGENT = {
    "agent_id": "risk-aware-growth",
    "agent_name": "Risk-Aware Growth",
    "error": "",
    "mode": "module",
}
_SCORE_SUFFIXES = ("mean", "median", "min", "max")
_CASE_NUMERIC_FIELDS = (
    "days_advanced",
    "final_day",
    "happiness",
    "population",
    "raw_score",
    "score",
    "solvency",
    "treasury",
)
# The archived CSV also has housing_capacity and jobs_total; the current runner does not.


def _compare_metrics(actual: dict[str, Any], expected: dict[str, Any], path: str) -> list[str]:
    errors: list[str] = []
    for key, wanted in expected.items():
        if key.startswith(_EXCLUDED_SUMMARY_PREFIXES):
            continue
        observed = actual.get(key)
        if observed is None:
            errors.append(f"{path}.{key} is missing")
            continue
        try:
            matches = math.isclose(float(observed), float(wanted), rel_tol=0.0, abs_tol=1e-9)
        except (TypeError, ValueError):
            matches = False
        if not matches:
            errors.append(f"{path}.{key}: expected {wanted}, got {observed}")
    return errors


def _compare_raw_score_metrics(
    actual: dict[str, Any], expected: dict[str, Any], path: str
) -> list[str]:
    errors: list[str] = []
    for suffix in _SCORE_SUFFIXES:
        actual_key = f"raw_score_{suffix}"
        expected_key = f"score_{suffix}"
        wanted = expected.get(expected_key)
        observed = actual.get(actual_key)
        if observed is None:
            errors.append(f"{path}.{actual_key} is missing")
            continue
        try:
            matches = wanted is not None and math.isclose(
                float(observed), float(wanted), rel_tol=0.0, abs_tol=1e-9
            )
        except (TypeError, ValueError):
            matches = False
        if not matches:
            errors.append(f"{path}.{actual_key}: expected {wanted}, got {observed}")
    return errors


def _scenario_metrics(summary: dict[str, Any]) -> dict[str, dict[str, Any]]:
    combined = summary.get("by_agent_scenario")
    if isinstance(combined, dict):
        scenarios: dict[str, dict[str, Any]] = {}
        for key, metrics in combined.items():
            if "|" in key and isinstance(metrics, dict):
                scenarios[key.split("|", 1)[1]] = metrics
        return scenarios

    direct = summary.get("by_scenario")
    if isinstance(direct, dict):
        return direct
    return {}


def validate_summary(
    summary: dict[str, Any],
    published: dict[str, Any],
    *,
    require_current: bool = True,
) -> list[str]:
    """Compare deterministic aggregates from the current and archived runners."""
    errors: list[str] = []
    has_current_sections = "by_agent" in summary or "by_agent_scenario" in summary
    current_schema = isinstance(summary.get("by_agent"), dict) and isinstance(
        summary.get("by_agent_scenario"), dict
    )
    if require_current and not current_schema:
        errors.append("summary does not use the current finalist_eval.py schema")
    actual_overall = summary.get("overall")
    expected_overall = published.get("overall")
    if not isinstance(actual_overall, dict):
        errors.append("summary is missing an 'overall' object")
    elif not isinstance(expected_overall, dict):
        errors.append("published summary is missing an 'overall' object")
    else:
        errors.extend(_compare_metrics(actual_overall, expected_overall, "overall"))
        if has_current_sections:
            errors.extend(_compare_raw_score_metrics(actual_overall, expected_overall, "overall"))

    actual_scenarios = _scenario_metrics(summary)
    expected_scenarios = _scenario_metrics(published)
    for scenario in sorted(expected_scenarios):
        if scenario not in actual_scenarios:
            errors.append(f"scenario {scenario} is missing from summary")
            continue
        errors.extend(
            _compare_metrics(
                actual_scenarios[scenario],
                expected_scenarios[scenario],
                f"scenario {scenario}",
            )
        )
        if has_current_sections:
            errors.extend(
                _compare_raw_score_metrics(
                    actual_scenarios[scenario],
                    expected_scenarios[scenario],
                    f"scenario {scenario}",
                )
            )
    for scenario in sorted(actual_scenarios.keys() - expected_scenarios.keys()):
        errors.append(f"scenario {scenario} is unexpected in summary")

    if has_current_sections and isinstance(expected_overall, dict):
        by_agent = summary.get("by_agent")
        agent_id = _EXPECTED_AGENT["agent_id"]
        if not isinstance(by_agent, dict) or not isinstance(by_agent.get(agent_id), dict):
            errors.append(f"summary is missing by_agent.{agent_id}")
        else:
            unexpected_agents = sorted(by_agent.keys() - {agent_id})
            for unexpected in unexpected_agents:
                errors.append(f"summary has unexpected agent {unexpected}")
            agent_metrics = by_agent[agent_id]
            errors.extend(_compare_metrics(agent_metrics, expected_overall, f"agent {agent_id}"))
            errors.extend(
                _compare_raw_score_metrics(agent_metrics, expected_overall, f"agent {agent_id}")
            )

        combined = summary.get("by_agent_scenario")
        expected_keys = {f"{agent_id}|{scenario}" for scenario in expected_scenarios}
        if not isinstance(combined, dict):
            errors.append("summary is missing 'by_agent_scenario'")
        else:
            for key in sorted(expected_keys - combined.keys()):
                errors.append(f"summary is missing by_agent_scenario.{key}")
            for key in sorted(combined.keys() - expected_keys):
                errors.append(f"summary has unexpected by_agent_scenario.{key}")

    return errors


def _index_rows(
    rows: list[dict[str, str]], label: str
) -> tuple[dict[tuple[str, int], dict[str, str]], list[str]]:
    indexed: dict[tuple[str, int], dict[str, str]] = {}
    errors: list[str] = []
    for row_number, row in enumerate(rows, start=2):
        scenario = row.get("scenario")
        seed_text = row.get("seed")
        try:
            case = (str(scenario), int(seed_text or ""))
        except ValueError:
            errors.append(f"{label} row {row_number} has an invalid seed: {seed_text}")
            continue
        if not scenario:
            errors.append(f"{label} row {row_number} is missing scenario")
            continue
        if case in indexed:
            errors.append(f"{label} has duplicate case {case[0]} seed={case[1]}")
            continue
        indexed[case] = row
    return indexed, errors


def validate_case_rows(
    rows: list[dict[str, str]],
    published_rows: list[dict[str, str]],
    *,
    require_current: bool = True,
) -> list[str]:
    """Compare deterministic fields for every published scenario and seed."""
    actual, errors = _index_rows(rows, "results")
    expected, published_errors = _index_rows(published_rows, "published results")
    errors.extend(published_errors)

    for case in sorted(expected):
        scenario, seed = case
        if case not in actual:
            errors.append(f"{scenario} seed={seed}: missing result")
            continue

        actual_row = actual[case]
        expected_row = expected[case]
        if actual_row.get("ok") != expected_row.get("ok"):
            errors.append(
                f"{scenario} seed={seed} ok: expected {expected_row.get('ok')}, "
                f"got {actual_row.get('ok')}"
            )

        if require_current or any(field in actual_row for field in _EXPECTED_AGENT):
            for field, expected_text in _EXPECTED_AGENT.items():
                observed_text = actual_row.get(field)
                if observed_text != expected_text:
                    errors.append(
                        f"{scenario} seed={seed} {field}: expected {expected_text!r}, "
                        f"got {observed_text!r}"
                    )

        for field in _CASE_NUMERIC_FIELDS:
            wanted = expected_row.get(field)
            observed = actual_row.get(field)
            try:
                matches = (
                    wanted is not None
                    and observed is not None
                    and math.isclose(float(observed), float(wanted), rel_tol=0.0, abs_tol=1e-9)
                )
            except ValueError:
                matches = False
            if not matches:
                errors.append(f"{scenario} seed={seed} {field}: expected {wanted}, got {observed}")

    for scenario, seed in sorted(actual.keys() - expected.keys()):
        errors.append(f"{scenario} seed={seed}: unexpected result")

    return errors


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def main(argv: list[str] | None = None) -> int:
    root = Path(__file__).parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("summary", type=Path, help="summary.json from finalist_eval.py")
    parser.add_argument("results_csv", type=Path, help="results.csv from finalist_eval.py")
    parser.add_argument(
        "--published-summary",
        type=Path,
        default=root / "results" / "score90_best_summary.json",
        help="published summary used for comparison",
    )
    parser.add_argument(
        "--published-csv",
        type=Path,
        default=root / "results" / "score90_best_results.csv",
        help="published per-case CSV used for comparison",
    )
    args = parser.parse_args(argv)

    try:
        summary = json.loads(args.summary.read_text())
        published_summary = json.loads(args.published_summary.read_text())
        rows = _read_csv(args.results_csv)
        published_rows = _read_csv(args.published_csv)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: could not read validation input: {exc}")
        return 2

    errors = validate_summary(summary, published_summary)
    errors.extend(validate_case_rows(rows, published_rows))

    if errors:
        print("FAIL: generated results do not match the published result")
        for error in errors:
            print(f"- {error}")
        return 1

    print(f"PASS: {len(published_rows)} cases match the published winning result")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
