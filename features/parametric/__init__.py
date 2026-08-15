"""
features.parametric
-------------------
Batch parametric sweep engine for Abaqus Agent.

Supports DOE strategies: full factorial, Latin Hypercube, Sobol.
"""

from features.feature_registry import register_hook
from features.parametric.sweep_engine import parametric_pre_build_hook

register_hook("pre_build", parametric_pre_build_hook)
