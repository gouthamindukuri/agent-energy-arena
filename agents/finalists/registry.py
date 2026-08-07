"""Stable registry for the preserved EAGE Hackthon 2026 finalists."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal

Mode = Literal["module", "cem", "archived"]


@dataclass(frozen=True)
class Finalist:
    agent_id: str
    name: str
    mode: Mode
    module: str | None = None
    policy: str | None = None
    note: str = ""


_FINALISTS = {
    "risk-aware-growth": Finalist(
        agent_id="risk-aware-growth",
        name="Risk-Aware Growth",
        mode="module",
        module="agents.finalists.risk_aware_growth",
        note="Maintained equivalent of the final submitted policy.",
    ),
    "safe-adaptive": Finalist(
        agent_id="safe-adaptive",
        name="Safe Adaptive",
        mode="module",
        module="agents.finalists.safe_adaptive",
    ),
    "renewables-mix": Finalist(
        agent_id="renewables-mix",
        name="Renewables Mix",
        mode="module",
        module="agents.finalists.renewables_mix.agent",
    ),
    "oil-exploration": Finalist(
        agent_id="oil-exploration",
        name="Oil Exploration",
        mode="module",
        module="agents.finalists.oil_exploration.agent_oil_6",
    ),
    "safety-first": Finalist(
        agent_id="safety-first",
        name="Safety First",
        mode="module",
        module="agents.finalists.safety_first",
        note="Defaults to the aggressive_safety policy.",
    ),
    "cem-rl-survival": Finalist(
        agent_id="cem-rl-survival",
        name="CEM RL Survival",
        mode="cem",
        policy="agents/finalists/cem_policies/cem_full_survival.npz",
    ),
    "cem-rl-population": Finalist(
        agent_id="cem-rl-population",
        name="CEM RL Population",
        mode="cem",
        policy="agents/finalists/cem_policies/cem_population_weighted.npz",
    ),
    "ppo-rl": Finalist(
        agent_id="ppo-rl",
        name="PPO RL",
        mode="archived",
        note="Historical only: the competitive checkpoint was not preserved as a runnable finalist.",
    ),
}

FINALISTS: Mapping[str, Finalist] = MappingProxyType(_FINALISTS)
RUNNABLE_IDS = tuple(
    agent_id for agent_id, finalist in FINALISTS.items() if finalist.mode != "archived"
)
