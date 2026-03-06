"""
premium.adaptivity
------------------
Automatic mesh adaptivity for Abaqus Agent (premium).

Provides ALE adaptive meshing and h-refinement remeshing.
"""

from premium.feature_registry import register_hook
from premium.adaptivity.ale_mesh import inject_ale_adaptive_mesh
from premium.adaptivity.remesh import inject_remesh_controls
from premium.adaptivity.error_indicators import recommend_adaptivity_strategy

register_hook("pre_build", "adaptivity", inject_ale_adaptive_mesh)
