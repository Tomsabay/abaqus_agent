"""Schema helpers for Abaqus Agent experiment capsules."""

from __future__ import annotations

CAPSULE_SCHEMA_VERSION = "0.2.0-dev"

REQUIRED_CAPSULE_KEYS = {
    "schema_version",
    "run_id",
    "created_at",
    "inputs",
    "artifacts",
    "provenance",
}


def validate_capsule(capsule: dict) -> tuple[bool, list[str]]:
    """Validate the minimal capsule shape used by the v0.2 kernel."""
    errors = []
    missing = REQUIRED_CAPSULE_KEYS - set(capsule)
    if missing:
        errors.append("Missing capsule keys: " + ", ".join(sorted(missing)))

    if not isinstance(capsule.get("inputs", {}), dict):
        errors.append("inputs must be an object")
    if not isinstance(capsule.get("artifacts", {}), dict):
        errors.append("artifacts must be an object")
    if not isinstance(capsule.get("provenance", {}), dict):
        errors.append("provenance must be an object")

    return not errors, errors
