from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

from agents.finalists.registry import FINALISTS, RUNNABLE_IDS

REPO_ROOT = Path(__file__).resolve().parents[3]
MANIFEST_PATH = REPO_ROOT / "experiments/eage_hackathon_2026/manifest.json"
EXPECTED_SUBMISSION_HASH = "2e884ec93b60176f49d00a3d485321d3c772a9b413b3aff3ce06b3d921991676"
EXPECTED_SUBMISSION_FILES = {
    "experiments/eage_hackathon_2026/final_submission/submit/__init__.py": (
        "01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b"
    ),
    "experiments/eage_hackathon_2026/final_submission/submit/agent.py": (
        "834efd0d9e3dc5fad2fc909922051c769e03b7dc5a83918730899a9ac5f31112"
    ),
    "experiments/eage_hackathon_2026/final_submission/submit/safe_adaptive_growth_agent.py": (
        EXPECTED_SUBMISSION_HASH
    ),
}
EXPECTED_APPROACHES = {
    "risk-aware-growth",
    "safe-adaptive",
    "renewables-mix",
    "oil-exploration",
    "safety-first",
    "cem-rl-survival",
    "cem-rl-population",
    "ppo-rl",
}


def _manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text())


def test_manifest_identifies_event_team_and_repositories() -> None:
    manifest = _manifest()

    assert manifest["event"] == "EAGE Hackthon 2026"
    assert manifest["team"] == "Prometheus"
    assert manifest["repository"]["upstream"] == (
        "https://github.com/ovcharenkoo/agent-energy-arena"
    )
    assert manifest["repository"]["fork"] == (
        "https://github.com/gouthamindukuri/agent-energy-arena"
    )


def test_manifest_records_fork_commits_without_rewriting_upstream() -> None:
    repository = _manifest()["repository"]

    assert repository["upstream_base"] == "397ecb991f644a2631293b8a6db9d4d44960f826"
    assert [commit["sha"] for commit in repository["fork_main_commits"]] == [
        "c781a78a43942ceba5ea785959311c06db82b06e",
        "a86045d0e26979e03cd35a07c410b22dfe4034fe",
        "6f0b38b0fa75ce9ebfd686cfae065cdeed494da2",
    ]
    assert {commit["sha"] for commit in repository["research_commits"]} == {
        "cf41dda598d0269aa94c343f6bccce7c540bbba7",
        "e7cf0cbe873ed1970124505301fcf0d871ee5879",
        "e39be8088c905f83a5ca23e47f8621079c2388f1",
        "8e51d5dbd1df9568e119093cb60a6b335ff7fc71",
    }
    dispositions = {
        commit["sha"]: commit["integration"] for commit in repository["research_commits"]
    }
    assert "superseded" in dispositions["cf41dda598d0269aa94c343f6bccce7c540bbba7"]
    assert "superseded" in dispositions["e7cf0cbe873ed1970124505301fcf0d871ee5879"]
    assert "blocked" in dispositions["e39be8088c905f83a5ca23e47f8621079c2388f1"]
    assert "requires" in dispositions["8e51d5dbd1df9568e119093cb60a6b335ff7fc71"]


def test_recorded_main_commit_topology_matches_git_history() -> None:
    commits = [commit["sha"] for commit in _manifest()["repository"]["fork_main_commits"]]

    parents = subprocess.run(
        ["git", "show", "-s", "--format=%P", *commits],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()

    assert parents == [
        "9262bcc22534e5a8cb1a70fd6d9ad773a7cfbd45",
        ("c781a78a43942ceba5ea785959311c06db82b06e 397ecb991f644a2631293b8a6db9d4d44960f826"),
        "a86045d0e26979e03cd35a07c410b22dfe4034fe",
    ]


def test_recorded_commit_subjects_and_sources_match_git_history() -> None:
    manifest = _manifest()
    records = [
        *manifest["repository"]["fork_main_commits"],
        *manifest["repository"]["research_commits"],
    ]

    for record in records:
        subject = subprocess.run(
            ["git", "show", "-s", "--format=%s", record["sha"]],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        assert subject == record["subject"]

    for approach in manifest["approaches"]:
        if approach["source"] is None:
            continue
        subprocess.run(
            [
                "git",
                "cat-file",
                "-e",
                f"{approach['provenance_commit']}:{approach['source']}",
            ],
            cwd=REPO_ROOT,
            check=True,
        )


def test_manifest_pins_exact_submission() -> None:
    submission = _manifest()["winning_submission"]

    assert submission["entrypoint_module"] == "submit.agent"
    assert submission["exported_name"] == "Agent"
    assert submission["implementation_class"] == "SafeAdaptiveGrowthAgent"
    assert submission["sha256"] == EXPECTED_SUBMISSION_HASH
    assert submission["submitted_files"] == EXPECTED_SUBMISSION_FILES
    for relative_path, expected_hash in EXPECTED_SUBMISSION_FILES.items():
        with (REPO_ROOT / relative_path).open("rb") as handle:
            assert hashlib.file_digest(handle, "sha256").hexdigest() == expected_hash

    package_root = REPO_ROOT / "experiments/eage_hackathon_2026/final_submission"
    environment = {**os.environ, "PYTHONPATH": str(package_root)}
    subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from submit.agent import Agent; "
                "from submit.safe_adaptive_growth_agent import SafeAdaptiveGrowthAgent; "
                "assert Agent is SafeAdaptiveGrowthAgent"
            ),
        ],
        cwd=REPO_ROOT,
        env=environment,
        check=True,
    )


def test_manifest_approach_ids_are_complete_and_unique() -> None:
    approaches = _manifest()["approaches"]
    ids = [approach["id"] for approach in approaches]

    assert len(ids) == len(set(ids))
    assert set(ids) == EXPECTED_APPROACHES


def test_manifest_runnable_sources_and_artifacts_exist() -> None:
    manifest = _manifest()

    for approach in manifest["approaches"]:
        if approach["runnable"]:
            assert (REPO_ROOT / approach["source"]).exists(), approach["id"]
        else:
            assert approach["evidence_gap"], approach["id"]

    for relative_path in manifest["winning_submission"]["artifacts"]:
        assert (REPO_ROOT / relative_path).is_file(), relative_path


def test_manifest_approaches_match_runtime_registry() -> None:
    approaches = {approach["id"]: approach for approach in _manifest()["approaches"]}

    assert approaches.keys() == FINALISTS.keys()
    for agent_id, finalist in FINALISTS.items():
        assert approaches[agent_id]["mode"] == finalist.mode
        assert approaches[agent_id]["runnable"] is (agent_id in RUNNABLE_IDS)


def test_manifest_records_exact_evaluation_matrix() -> None:
    evaluation = _manifest()["winning_submission"]["evaluation"]

    assert evaluation["matrix"] == {
        "seeds": [1, 42, 101, 112, 777],
        "scenarios": ["baseline", "economy_stress", "grid_stress"],
        "horizon_days": 3650,
        "time_budget_seconds": 600,
        "cases": 15,
    }
    assert evaluation["archived_run"] == {
        "agent": "submit.agent",
        "workers": 15,
        "evidence": "experiments/eage_hackathon_2026/results/score90_best_summary.json",
    }
    assert evaluation["maintained_reproduction"] == {
        "agent": "risk-aware-growth",
        "workers": 10,
        "validator": "experiments/eage_hackathon_2026/validate_results.py",
    }


def test_publication_has_one_discoverable_canonical_document() -> None:
    publication = (REPO_ROOT / "EAGE_HACKATHON_2026.md").read_text()
    readme = (REPO_ROOT / "README.md").read_text()

    assert "[Prometheus winning solution](EAGE_HACKATHON_2026.md)" in readme
    assert "experiments/eage_hackathon_2026/manifest.json" in publication
    assert "agents/finalists/registry.py" in publication
    assert "--list-agents" in publication
    assert "--agents all" in publication
    assert "agents.finalists.safe_adaptive" in publication
    assert "--agents risk-aware-growth,safe-adaptive,oil-exploration" in publication
    assert "--seeds <SEED>" in publication
    assert "uv lock --check" in publication
    expected_comparison_rows = (
        "| Risk-Aware Growth | 434 | 343.9 | $2,648,441 | 1.000 |",
        "| Safe Adaptive fallback | 308 | 315.1 | $1,936,851 | 1.000 |",
        "| Stable renewable mix | 156 | 156.0 | $2,747,149 | 1.000 |",
        "| Oil exploration | 437 | 298.8 | $157,623 | 0.816 |",
        "| Adaptive safety aggressive | 400 | 309.3 | $785,606 | 0.784 |",
        "| CEM survival | 36 | 39.7 | -$171,827 | 0.970 |",
        "| CEM population | 90 | 87.2 | -$833,020 | 0.531 |",
    )
    for row in expected_comparison_rows:
        assert row in publication
    assert (
        "worker contention can affect\nwhether a constrained machine reaches the "
        "3650-day horizon before the wall-time\nlimit."
    ) in publication
    assert not (REPO_ROOT / "FINALISTS.md").exists()
    assert not (REPO_ROOT / "REPRODUCE.md").exists()
