from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from experiments.eage_hackathon_2026.validate_results import (  # noqa: E402
    main,
    validate_case_rows,
    validate_summary,
)

ROOT = Path(__file__).resolve().parents[1]
SUMMARY = ROOT / "results/score90_best_summary.json"
RESULTS = ROOT / "results/score90_best_results.csv"


def _load_json(path: Path = SUMMARY) -> dict:
    return json.loads(path.read_text())


def _load_csv(path: Path = RESULTS) -> list[dict[str, str]]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def _with_raw_score(metrics: dict) -> dict:
    current = metrics.copy()
    for suffix in ("mean", "median", "min", "max"):
        current[f"raw_score_{suffix}"] = current[f"score_{suffix}"]
    return current


def _current_summary() -> dict:
    published = _load_json()
    overall = _with_raw_score(published["overall"])
    scenarios = {
        name: _with_raw_score(metrics) for name, metrics in published["by_scenario"].items()
    }
    return {
        "overall": overall.copy(),
        "by_agent": {"risk-aware-growth": overall.copy()},
        "by_agent_scenario": {
            f"risk-aware-growth|{name}": metrics for name, metrics in scenarios.items()
        },
    }


def _current_rows() -> list[dict[str, str]]:
    rows = [row.copy() for row in _load_csv()]
    for row in rows:
        row.update(
            {
                "agent_id": "risk-aware-growth",
                "agent_name": "Risk-Aware Growth",
                "error": "",
                "mode": "module",
            }
        )
    return rows


def _write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def test_published_summary_matches_itself() -> None:
    summary = _load_json()

    assert validate_summary(summary, summary, require_current=False) == []


def test_current_summary_matches_published_metrics() -> None:
    assert validate_summary(_current_summary(), _load_json()) == []


def test_current_summary_schema_is_required() -> None:
    published = _load_json()

    assert validate_summary(published, published) == [
        "summary does not use the current finalist_eval.py schema"
    ]


def test_current_agent_scenario_keys_are_required() -> None:
    actual = _current_summary()
    metrics = actual["by_agent_scenario"].pop("risk-aware-growth|scenarios.baseline")
    actual["by_agent_scenario"]["wrong-agent|scenarios.baseline"] = metrics

    assert validate_summary(actual, _load_json()) == [
        "summary is missing by_agent_scenario.risk-aware-growth|scenarios.baseline",
        "summary has unexpected by_agent_scenario.wrong-agent|scenarios.baseline",
    ]


def test_legacy_scenario_metrics_cannot_shadow_current_metrics() -> None:
    actual = _current_summary()
    actual["by_scenario"] = _load_json()["by_scenario"]
    for key in actual["by_agent_scenario"]:
        actual["by_agent_scenario"][key] = {}

    errors = validate_summary(actual, _load_json())

    assert "scenario scenarios.baseline.days_advanced_max is missing" in errors


def test_current_raw_score_aggregate_mismatch_is_reported() -> None:
    actual = _current_summary()
    actual["overall"]["raw_score_mean"] = -1

    assert validate_summary(actual, _load_json()) == [
        "overall.raw_score_mean: expected 85.5162236145003, got -1"
    ]


def test_overall_summary_mismatches_are_reported() -> None:
    published = _load_json()
    actual = _load_json()
    actual["overall"]["population_mean"] = -1

    assert validate_summary(actual, published, require_current=False) == [
        "overall.population_mean: expected 343.93333333333334, got -1"
    ]


def test_scenario_summary_mismatches_are_reported() -> None:
    published = _load_json()
    actual = _load_json()
    actual["by_scenario"]["scenarios.grid_stress"]["treasury_min"] = -1

    assert validate_summary(actual, published, require_current=False) == [
        "scenario scenarios.grid_stress.treasury_min: expected 2116846.3478508047, got -1"
    ]


def test_every_published_case_matches_itself() -> None:
    rows = _load_csv()

    assert validate_case_rows(rows, rows, require_current=False) == []


def test_case_mismatch_is_reported() -> None:
    published = _load_csv()
    actual = [row.copy() for row in published]
    actual[0]["treasury"] = "1.0"

    assert validate_case_rows(actual, published, require_current=False) == [
        "scenarios.baseline seed=1 treasury: expected 3096135.2442496275, got 1.0"
    ]


def test_current_agent_metadata_mismatch_is_reported() -> None:
    actual = _current_rows()
    actual[0]["mode"] = "wrong"

    assert validate_case_rows(actual, _load_csv()) == [
        "scenarios.baseline seed=1 mode: expected 'module', got 'wrong'"
    ]


def test_current_agent_metadata_cannot_be_omitted() -> None:
    actual = _current_rows()
    for field in ("agent_id", "agent_name", "error", "mode"):
        actual[0].pop(field)

    assert validate_case_rows(actual, _load_csv()) == [
        "scenarios.baseline seed=1 agent_id: expected 'risk-aware-growth', got None",
        "scenarios.baseline seed=1 agent_name: expected 'Risk-Aware Growth', got None",
        "scenarios.baseline seed=1 error: expected '', got None",
        "scenarios.baseline seed=1 mode: expected 'module', got None",
    ]


def test_duplicate_row_cannot_hide_a_missing_case() -> None:
    published = _load_csv()
    actual = [row.copy() for row in published[:-1]]
    actual.append(published[0].copy())

    assert validate_case_rows(actual, published, require_current=False) == [
        "results has duplicate case scenarios.baseline seed=1",
        "scenarios.grid_stress seed=777: missing result",
    ]


def test_cli_prints_pass_for_current_results(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    summary = tmp_path / "summary.json"
    results = tmp_path / "results.csv"
    summary.write_text(json.dumps(_current_summary()))
    _write_csv(results, _current_rows())

    exit_code = main([str(summary), str(results)])

    assert exit_code == 0
    assert capsys.readouterr().out == "PASS: 15 cases match the published winning result\n"


def test_cli_requires_per_case_results() -> None:
    with pytest.raises(SystemExit) as exc_info:
        main([str(SUMMARY)])

    assert exc_info.value.code == 2


def test_cli_reports_unreadable_input(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    bad_summary = tmp_path / "summary.json"
    bad_summary.write_text("not json")

    exit_code = main([str(bad_summary), str(RESULTS)])

    assert exit_code == 2
    assert capsys.readouterr().out.startswith("ERROR: could not read validation input:")
