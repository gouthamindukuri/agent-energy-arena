"""Default submission entrypoint.

This points at the current best generic deterministic policy. Historical
and experimental variants remain in sibling modules.
"""

from .economy_mix_growth_agent import EconomyMixGrowthAgent

Agent = EconomyMixGrowthAgent
