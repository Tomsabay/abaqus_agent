"""
feature_registry.py
-------------------
Central registry that maps premium features to their implementations.

This module is the single integration point between the base pipeline
and premium feature modules. It provides dispatch functions that
build_model.py, orchestrator.py, and extract_kpis.py call into.
"""

from __future__ import annotations

from typing import Callable

from premium.licensing import feature_gate, PREMIUM_FEATURES


# -----------------------------------------------------------------
# Geometry dispatch registry
# -----------------------------------------------------------------

# Maps geometry type string -> (feature_name, generator_function)
_GEOMETRY_REGISTRY: dict[str, tuple[str, Callable]] = {}

# Maps step type string -> (feature_name, generator_function)
_STEP_REGISTRY: dict[str, tuple[str, Callable]] = {}

# Maps KPI type string -> (feature_name, extractor_function)
_KPI_REGISTRY: dict[str, tuple[str, Callable]] = {}

# Pipeline hooks: stage_name -> list of (feature_name, hook_function)
_PIPELINE_HOOKS: dict[str, list[tuple[str, Callable]]] = {
    "pre_build": [],
    "post_build": [],
    "pre_submit": [],
    "post_submit_failure": [],   # autorepair hooks here
    "post_extract": [],
}


def register_geometry(geo_type: str, feature: str, generator: Callable) -> None:
    """Register a premium geometry code generator."""
    _GEOMETRY_REGISTRY[geo_type] = (feature, generator)


def register_step(step_type: str, feature: str, generator: Callable) -> None:
    """Register a premium step code generator."""
    _STEP_REGISTRY[step_type] = (feature, generator)


def register_kpi(kpi_type: str, feature: str, extractor: Callable) -> None:
    """Register a premium KPI extractor."""
    _KPI_REGISTRY[kpi_type] = (feature, extractor)


def register_hook(stage: str, feature: str, hook: Callable) -> None:
    """Register a pipeline hook for a premium feature."""
    if stage in _PIPELINE_HOOKS:
        _PIPELINE_HOOKS[stage].append((feature, hook))


# -----------------------------------------------------------------
# Dispatch functions (called by base pipeline)
# -----------------------------------------------------------------

def get_premium_geometry(geo_type: str) -> Callable | None:
    """Get geometry generator for a premium geometry type, or None."""
    if geo_type in _GEOMETRY_REGISTRY:
        feat, gen = _GEOMETRY_REGISTRY[geo_type]
        feature_gate.require(feat)
        return gen
    return None


def get_premium_step(step_type: str) -> Callable | None:
    """Get step generator for a premium step type, or None."""
    if step_type in _STEP_REGISTRY:
        feat, gen = _STEP_REGISTRY[step_type]
        feature_gate.require(feat)
        return gen
    return None


def get_premium_kpi(kpi_type: str) -> Callable | None:
    """Get KPI extractor for a premium KPI type, or None."""
    if kpi_type in _KPI_REGISTRY:
        feat, ext = _KPI_REGISTRY[kpi_type]
        feature_gate.require(feat)
        return ext
    return None


def run_hooks(stage: str, context: dict) -> dict:
    """Run all registered hooks for a pipeline stage."""
    for feat, hook in _PIPELINE_HOOKS.get(stage, []):
        if feature_gate.is_enabled(feat):
            context = hook(context) or context
    return context


def is_premium_geometry(geo_type: str) -> bool:
    """Check if a geometry type requires premium."""
    return geo_type in _GEOMETRY_REGISTRY


def is_premium_step(step_type: str) -> bool:
    """Check if a step type requires premium."""
    return step_type in _STEP_REGISTRY


def is_premium_kpi(kpi_type: str) -> bool:
    """Check if a KPI type requires premium."""
    return kpi_type in _KPI_REGISTRY


def list_premium_capabilities() -> dict:
    """Return a summary of all registered premium capabilities."""
    return {
        "geometry_types": list(_GEOMETRY_REGISTRY.keys()),
        "step_types": list(_STEP_REGISTRY.keys()),
        "kpi_types": list(_KPI_REGISTRY.keys()),
        "hooks": {k: len(v) for k, v in _PIPELINE_HOOKS.items() if v},
        "features": {
            name: {
                "display_name": PREMIUM_FEATURES[name],
                "enabled": feature_gate.is_enabled(name),
            }
            for name in PREMIUM_FEATURES
        },
    }
