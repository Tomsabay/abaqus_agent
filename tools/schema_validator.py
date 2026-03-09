"""
schema_validator.py
-------------------
Validates a Problem Spec dict/YAML against spec_schema.json.
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

SCHEMA_PATH = Path(__file__).parent.parent / "schema" / "spec_schema.json"


def validate_spec(spec: dict | str | Path) -> tuple[bool, list[str]]:
    """
    Validate a spec against the JSON Schema.

    Parameters
    ----------
    spec : dict, str (YAML text), or Path (to .yaml/.json file)

    Returns
    -------
    (valid: bool, errors: list[str])
    """
    if isinstance(spec, (str, Path)):
        p = Path(spec)
        if p.exists():
            with open(p, encoding="utf-8") as f:
                spec = yaml.safe_load(f)
        else:
            spec = yaml.safe_load(str(spec))

    try:
        import jsonschema
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        validator = jsonschema.Draft7Validator(schema)
        errors = [e.message for e in validator.iter_errors(spec)]
        return len(errors) == 0, errors
    except ImportError:
        # jsonschema not installed - do minimal manual checks
        return _manual_validate(spec)


def _manual_validate(spec: dict) -> tuple[bool, list[str]]:
    """Minimal validation without jsonschema dependency."""
    errors = []
    required_top = ["meta", "geometry", "material", "analysis", "bc_load", "outputs"]
    for key in required_top:
        if key not in spec:
            errors.append(f"Missing required field: '{key}'")

    meta = spec.get("meta", {})
    if "abaqus_release" not in meta:
        errors.append("meta.abaqus_release is required")
    if "model_name" not in meta:
        errors.append("meta.model_name is required")

    mat = spec.get("material", {})
    for f in ["name", "E", "nu"]:
        if f not in mat:
            errors.append(f"material.{f} is required")

    ana = spec.get("analysis", {})
    for f in ["solver", "step_type"]:
        if f not in ana:
            errors.append(f"analysis.{f} is required")

    out = spec.get("outputs", {})
    if "kpis" not in out or not out["kpis"]:
        errors.append("outputs.kpis must have at least one entry")

    return len(errors) == 0, errors
