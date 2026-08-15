"""
feature_registry.py
-------------------
Central registry that maps optional feature modules to their implementations.

This module is the single integration point between the base pipeline
and the feature modules under ``features/``. It provides dispatch
functions that build_model.py, orchestrator.py, and extract_kpis.py
call into.

Registration happens as an import side effect of each sub-package. Relying on
somebody happening to import them made the answer to "is this supported?"
depend on what else the process had done first, so every lookup below now
loads them first (see ``_ensure_loaded``).
"""

from __future__ import annotations

import importlib
from typing import Callable

# Human-readable names of the optional feature modules shipped in this tree.
FEATURE_MODULES: dict[str, str] = {
    "coupling":     "Multi-Physics Coupling",
    "adaptivity":   "Automatic Mesh Adaptivity",
    "parametric":   "Batch Parametric Sweeps",
    "geometry_ext": "Extended Geometry Types",
    "autorepair":   "Failure Auto-Repair",
}

# -----------------------------------------------------------------
# Geometry dispatch registry
# -----------------------------------------------------------------

# Maps geometry type string -> generator function
_GEOMETRY_REGISTRY: dict[str, Callable] = {}

# Maps step type string -> generator function
_STEP_REGISTRY: dict[str, Callable] = {}

# Maps KPI type string -> extractor function
_KPI_REGISTRY: dict[str, Callable] = {}

# Pipeline hooks: stage_name -> list of hook functions
_PIPELINE_HOOKS: dict[str, list[Callable]] = {
    "pre_build": [],
    "post_build": [],
    "pre_submit": [],
    "post_submit_failure": [],   # autorepair hooks here
    "post_extract": [],
}


def register_geometry(geo_type: str, generator: Callable) -> None:
    """Register a geometry code generator."""
    _GEOMETRY_REGISTRY[geo_type] = generator


def register_step(step_type: str, generator: Callable) -> None:
    """Register a step code generator."""
    _STEP_REGISTRY[step_type] = generator


def register_kpi(kpi_type: str, extractor: Callable) -> None:
    """Register a KPI extractor."""
    _KPI_REGISTRY[kpi_type] = extractor


def register_hook(stage: str, hook: Callable) -> None:
    """Register a pipeline hook."""
    if stage in _PIPELINE_HOOKS:
        _PIPELINE_HOOKS[stage].append(hook)


# -----------------------------------------------------------------
# Deterministic loading
# -----------------------------------------------------------------

# Sub-packages whose import populates the registries above. Import order is
# irrelevant; each registers only its own entries.
_REGISTERING_PACKAGES = (
    "features.geometry",
    "features.coupling",
    "features.adaptivity",
    "features.parametric",
    "features.autorepair",
)

_loaded = False
_load_failures: dict[str, str] = {}


def _ensure_loaded() -> None:
    """Import every feature sub-package exactly once, before any lookup.

    Without this the registries were populated only as a side effect of some
    unrelated import. Two things followed, both measured on this tree:
    ``shell_plate`` / ``beam_frame`` / ``composite_plate`` / ``cohesive_layer``
    were listed in schema/spec_schema.json but nothing ever imported
    ``features.geometry``, so they returned "Unsupported geometry type" every
    time; and ``Coupled_Temperature_Displacement`` worked or not depending on
    whether the same process had already built an ordinary model (which
    imports ``features.coupling.coupled_materials`` further down
    runner/build_model.py, i.e. *after* the step dispatch that needed it).

    A module that fails to import is recorded rather than swallowed, so
    "unsupported" and "broken install" stay distinguishable.
    """
    global _loaded
    if _loaded:
        return
    _loaded = True
    for name in _REGISTERING_PACKAGES:
        try:
            importlib.import_module(name)
        except Exception as exc:
            _load_failures[name] = "%s: %s" % (type(exc).__name__, exc)


def load_failures() -> dict:
    """Feature modules that are present but failed to import, with the reason."""
    _ensure_loaded()
    return dict(_load_failures)


# -----------------------------------------------------------------
# Dispatch functions (called by base pipeline)
# -----------------------------------------------------------------

def get_geometry_generator(geo_type: str) -> Callable | None:
    """Get the generator for a registered geometry type, or None."""
    _ensure_loaded()
    return _GEOMETRY_REGISTRY.get(geo_type)


def get_step_generator(step_type: str) -> Callable | None:
    """Get the generator for a registered step type, or None."""
    _ensure_loaded()
    return _STEP_REGISTRY.get(step_type)


def get_kpi_extractor(kpi_type: str) -> Callable | None:
    """Get the extractor for a registered KPI type, or None."""
    _ensure_loaded()
    return _KPI_REGISTRY.get(kpi_type)


def run_hooks(stage: str, context: dict) -> dict:
    """Run all registered hooks for a pipeline stage."""
    _ensure_loaded()
    for hook in _PIPELINE_HOOKS.get(stage, []):
        context = hook(context) or context
    return context


def is_registered_geometry(geo_type: str) -> bool:
    """Check if a geometry type is provided by a feature module."""
    _ensure_loaded()
    return geo_type in _GEOMETRY_REGISTRY


def is_registered_step(step_type: str) -> bool:
    """Check if a step type is provided by a feature module."""
    _ensure_loaded()
    return step_type in _STEP_REGISTRY


def is_registered_kpi(kpi_type: str) -> bool:
    """Check if a KPI type is provided by a feature module."""
    _ensure_loaded()
    return kpi_type in _KPI_REGISTRY


def list_feature_modules() -> dict:
    """Return the optional feature modules shipped in this tree."""
    return {
        name: {"display_name": display}
        for name, display in FEATURE_MODULES.items()
    }


def list_capabilities() -> dict:
    """Return a summary of everything registered.

    Reported after loading, so this answers "what can this build do" rather
    than "what happened to be imported by the time you asked".
    """
    _ensure_loaded()
    caps = {
        "geometry_types": sorted(_GEOMETRY_REGISTRY.keys()),
        "step_types": sorted(_STEP_REGISTRY.keys()),
        "kpi_types": sorted(_KPI_REGISTRY.keys()),
        "hooks": {k: len(v) for k, v in _PIPELINE_HOOKS.items() if v},
    }
    if _load_failures:
        caps["unavailable_modules"] = dict(_load_failures)
    return caps
