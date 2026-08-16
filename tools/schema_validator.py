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
    """Minimal validation without jsonschema dependency.

    Mirrors the dialect split in the schema's top-level ``allOf``. Without that
    mirroring this fallback rejects every v2 spec for "missing geometry" on a
    machine where jsonschema happens not to be installed — a validator that
    disagrees with its own schema is worse than no validator, because the
    disagreement only shows up on someone else's machine.
    """
    errors = []
    is_deck = "deck" in spec
    is_v2 = "parts" in spec
    if is_deck:
        # A deck describes nothing: it hands over a finished .inp that already
        # carries its own parts, steps, boundary conditions and loads.
        required_top = ["meta", "material", "outputs"]
    elif is_v2:
        required_top = ["meta", "material", "outputs", "assembly", "steps"]
    else:
        # Neither dialect names itself. v1 -- `geometry` + `analysis.step_type`
        # + `bc_load` -- was removed 2026-08-16, so there is no third shape to
        # fall back to. Say the spec declares no model, rather than demanding
        # v1's keys and letting a v1 spec pass here while the real schema
        # refuses it: that divergence would only surface on a machine without
        # jsonschema installed, which is the whole hazard this function has.
        required_top = ["meta", "material", "outputs"]
        errors.append(
            "spec declares no model: expected 'parts' (describe one) or "
            "'deck' (hand over a finished .inp)")
    for key in required_top:
        if key not in spec:
            errors.append(f"Missing required field: '{key}'")
    if is_deck:
        if not (spec.get("deck") or {}).get("file"):
            errors.append("deck.file is required")
        for key in ("geometry", "parts", "assembly", "steps", "conditions",
                    "interactions", "bc_load"):
            if key in spec:
                errors.append(
                    f"'{key}' describes a model, and 'deck' hands over one "
                    f"that is already complete — the two cannot be combined")
    elif is_v2:
        for key in ("geometry", "bc_load"):
            if key in spec:
                errors.append(
                    f"'{key}' belongs to the v1 dialect and cannot be combined "
                    f"with 'parts'")

    meta = spec.get("meta", {})
    if "abaqus_release" not in meta:
        errors.append("meta.abaqus_release is required")
    if "model_name" not in meta:
        errors.append("meta.model_name is required")

    mat = spec.get("material", {})
    for f in ["name", "E", "nu"]:
        if f not in mat:
            errors.append(f"material.{f} is required")

    out = spec.get("outputs", {})
    if "kpis" not in out or not out["kpis"]:
        errors.append("outputs.kpis must have at least one entry")

    return len(errors) == 0, errors
