from __future__ import annotations

import importlib
from pathlib import Path

import numpy as np
import pytest

from agents.finalists.registry import FINALISTS, RUNNABLE_IDS

REPO_ROOT = Path(__file__).resolve().parents[2]
EXPECTED_MODES = {
    "risk-aware-growth": "module",
    "safe-adaptive": "module",
    "renewables-mix": "module",
    "oil-exploration": "module",
    "safety-first": "module",
    "cem-rl-survival": "cem",
    "cem-rl-population": "cem",
    "ppo-rl": "archived",
}


def test_registry_has_stable_ids_and_modes() -> None:
    assert {agent_id: finalist.mode for agent_id, finalist in FINALISTS.items()} == EXPECTED_MODES


def test_module_finalists_export_agent() -> None:
    for finalist in FINALISTS.values():
        if finalist.mode != "module":
            continue
        assert finalist.module is not None
        module = importlib.import_module(finalist.module)
        assert hasattr(module, "Agent"), finalist.agent_id


def test_cem_finalists_reference_loadable_policy_files() -> None:
    for finalist in FINALISTS.values():
        if finalist.mode != "cem":
            continue
        assert finalist.policy is not None
        policy_path = REPO_ROOT / finalist.policy
        assert policy_path.is_file(), finalist.agent_id
        with np.load(policy_path) as policy:
            assert policy.files, finalist.agent_id


def test_archived_finalists_are_not_runnable() -> None:
    assert "ppo-rl" not in RUNNABLE_IDS
    assert all(FINALISTS[agent_id].mode != "archived" for agent_id in RUNNABLE_IDS)


def test_registry_key_matches_agent_id() -> None:
    assert all(key == finalist.agent_id for key, finalist in FINALISTS.items())


def test_registry_is_immutable() -> None:
    with pytest.raises(TypeError):
        FINALISTS["unexpected"] = FINALISTS["risk-aware-growth"]  # type: ignore[index]
