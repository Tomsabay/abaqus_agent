"""
metadata.py
-----------
Shared Experiment Capsule metadata helpers for evidence-producing workflows.
"""

from __future__ import annotations

from typing import Any

METADATA_SCHEMA_VERSION = "1.0"
PROJECT_NAME = "abaqus-agent"


def evidence_metadata(
    *,
    workflow: str,
    evidence_source: str,
    evidence_level: str,
    overall_status: str,
    real_env_required: bool,
    real_env_verified: bool,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return standard metadata for a capsule created from evidence artifacts."""
    metadata: dict[str, Any] = {
        "metadata_schema_version": METADATA_SCHEMA_VERSION,
        "project": PROJECT_NAME,
        "workflow": workflow,
        "evidence_source": evidence_source,
        "evidence_level": evidence_level,
        "overall_status": overall_status,
        "real_env_required": real_env_required,
        "real_env_verified": real_env_verified,
    }
    if extra:
        metadata.update(extra)
    return metadata
