"""
features.adaptivity
-------------------
Automatic mesh adaptivity for Abaqus Agent.

Provides ALE adaptive meshing and h-refinement remeshing.
"""

from features.adaptivity.ale_mesh import inject_ale_adaptive_mesh
from features.adaptivity.error_indicators import recommend_adaptivity_strategy
from features.adaptivity.remesh import inject_remesh_controls
from features.feature_registry import register_hook

__all__ = [
    "inject_ale_adaptive_mesh",
    "recommend_adaptivity_strategy",
    "inject_remesh_controls",
]

register_hook("pre_build", inject_ale_adaptive_mesh)
