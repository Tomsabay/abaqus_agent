"""
premium.parametric
------------------
Batch parametric sweep engine for Abaqus Agent (premium).

Supports DOE strategies: full factorial, Latin Hypercube, Sobol.
"""

from premium.feature_registry import register_hook
from premium.parametric.sweep_engine import parametric_pre_build_hook

register_hook("pre_build", "parametric", parametric_pre_build_hook)
