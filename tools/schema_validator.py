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
        # The path is half the message. Measured (round 4, 2026-08-18): a
        # planner-written spec came back as just "2 is not of type 'array'" —
        # one scalar, somewhere in a 200-line file, and neither the user nor
        # the model that wrote it could tell which key to fix.
        errors = []
        for e in validator.iter_errors(spec):
            errors.extend(_flatten(e))
        errors.extend(_recipe_errors(spec))
        return len(errors) == 0, errors
    except ImportError:
        # jsonschema not installed - do minimal manual checks
        return _manual_validate(spec)


def _flatten(error) -> list[str]:
    """One `oneOf` failure, reported as the thing that is actually wrong.

    A schema built out of `oneOf` says "is not valid under any of the given
    schemas" and prints the whole value back. Measured (round 5, 2026-08-18):
    a contact interaction that spelled its friction `friction_coefficient:
    0.15` instead of `property: {friction: 0.15}` came back as a 4-line dump
    of the object with no mention of the key -- and the planner that wrote it
    got that dump as its only feedback.

    So each branch's own errors are counted, and the branch with the fewest is
    taken as the one the value came closest to matching -- for that
    interaction, the sugar branch, whose complaint is
    "Additional properties are not allowed ('friction_coefficient' was
    unexpected)". Recursive, because a branch can itself be a `oneOf`.

    `absolute_path` is read off each sub-error rather than accumulated: a
    context error is chained to its parent, so it already carries the whole
    path. Adding the parent's on top reported the key twice
    ("interactions.1.interactions.1"), which reads as a second, deeper item
    that does not exist.

    Fewest-errors is the right pick only when something in the value says
    which branch was meant. When the closest branch's only complaint is that
    keys are MISSING, nothing does -- `material: {name: Nameless}` is one key
    short of the library shape and two short of the E/nu shape, and reporting
    only "'library' is a required property" hides that giving E and nu is
    equally correct. So in that case every shape's requirements are reported.

    At most three messages per branch. A branch that disagrees in more places
    than that is not the branch the author meant, and printing all of them
    buries the one that matters.
    """
    if not error.context:
        text = ".".join(str(p) for p in error.absolute_path)
        return [f"{text}: {error.message}" if text else error.message]
    branches: dict = {}
    for sub in error.context:
        key = sub.schema_path[0] if sub.schema_path else 0
        branches.setdefault(key, []).append(sub)

    def only_missing_keys(branch: list) -> bool:
        return all(sub.validator == "required" for sub in branch)

    closest = min(branches.values(), key=len)
    chosen = [closest]
    if only_missing_keys(closest):
        chosen = [b for b in branches.values() if only_missing_keys(b)]
    out: list[str] = []
    for branch in chosen:
        for sub in branch[:3]:
            for message in _flatten(sub):
                if message not in out:
                    out.append(message)
    return out


def _recipe_errors(spec) -> list[str]:
    """The KPI reader's refusals, delivered at validation time.

    The schema knows the KPI types but not the component names, so
    `component: Mises` — the plausible spelling, measured from deepseek-v4-pro
    on its first probe (2026-08-18) — passed validation and the dry build,
    and nothing before post/extract_kpis.py would have refused it: a refusal
    priced at one real solve (~26 min on this model's round-3 twin). Every
    caller of validate_spec gets the refusal here instead, in the extractor's
    own words, because odb_lens reuses the extractor's tables rather than
    keeping a copy.

    Presence checks stay the schema's job: an absent or empty kpis list is
    already reported by it, and reporting it twice would say the file
    disagrees with itself.
    """
    if not isinstance(spec, dict):
        return []
    outputs = spec.get("outputs")
    if not isinstance(outputs, dict):
        return []
    kpis = outputs.get("kpis")
    if not isinstance(kpis, list) or not kpis:
        return []
    from odb_lens.recipe import normalize_recipe
    try:
        normalize_recipe(kpis)
    except ValueError as e:
        return [f"outputs.kpis: {e}"]
    return []


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

    errors.extend(_recipe_errors(spec))
    return len(errors) == 0, errors
