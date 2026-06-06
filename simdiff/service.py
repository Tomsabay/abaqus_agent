"""Reusable Simulation Diff service over supplied KPI dictionaries."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from simdiff.kpi_diff import diff_kpis
from simdiff.kpi_diff import render_markdown as render_kpi_diff_markdown

SAFE_DIFF_ID = re.compile(r"^[A-Za-z0-9_.-]{1,80}$")


def collect_kpi_diff(
    *,
    baseline_kpis: dict[str, Any],
    candidate_kpis: dict[str, Any],
    tolerances: dict[str, dict[str, float]] | None = None,
    out_dir: str | Path,
    diff_id: str = "simulation-diff",
    input_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Collect a portable KPI Simulation Diff report without invoking Abaqus."""
    safe_diff_id = validate_diff_id(diff_id)
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    report = diff_kpis(baseline_kpis, candidate_kpis, tolerances=tolerances)
    result = {
        "schema_version": "1.0",
        "project": "abaqus-agent",
        "workflow": "simulation-diff-kpi",
        "diff_id": safe_diff_id,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "real_env_verified": False,
        "real_env_required": False,
        "inputs": {
            "baseline_kpis": baseline_kpis,
            "candidate_kpis": candidate_kpis,
            "tolerances": tolerances or {},
            "metadata": input_metadata or {},
        },
        "diff": report,
        "overall_status": report["status"],
    }

    diff_json_path = out_path / "diff.json"
    diff_markdown_path = out_path / "diff.md"
    diff_json_path.write_text(
        json.dumps(result, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    diff_markdown_path.write_text(render_markdown(result), encoding="utf-8")
    return result


def render_markdown(result: dict[str, Any]) -> str:
    """Render a standalone Simulation Diff Markdown report."""
    lines = [
        "# Abaqus Agent Simulation Diff Report",
        "",
        "## Verdict Summary",
        "",
        "| Area | Status | Detail |",
        "|---|---|---|",
        f"| Overall | `{result['overall_status']}` | KPI dictionary comparison completed. |",
        f"| KPI Diff | `{result['diff']['status']}` | {result['diff']['total']} KPI rows; {result['diff']['changed_count']} changed, {result['diff']['added_count']} added, {result['diff']['removed_count']} removed. |",
        f"| Real Abaqus execution | `{'verified' if result['real_env_verified'] else 'not verified'}` | This report uses supplied KPI JSON values only. |",
        "",
        "## Run Metadata",
        "",
        f"- Project: `{result['project']}`",
        f"- Workflow: `{result['workflow']}`",
        f"- Diff ID: `{result['diff_id']}`",
        f"- Generated at: `{result['generated_at']}`",
        f"- Real environment required: `{str(result['real_env_required']).lower()}`",
        f"- Real environment verified: `{str(result['real_env_verified']).lower()}`",
        "",
        "## KPI Diff",
        "",
        render_kpi_diff_markdown(result["diff"]).strip(),
        "",
        "## Verification Boundary",
        "",
        "This Simulation Diff compares supplied KPI JSON values. It does not invoke Abaqus, read an ODB, check out a license token, or prove real solver execution.",
    ]
    return "\n".join(lines) + "\n"


def validate_diff_id(diff_id: str) -> str:
    """Return a safe diff id for local output paths and vault titles."""
    if not SAFE_DIFF_ID.match(diff_id):
        raise ValueError("diff_id must use 1-80 letters, numbers, dot, dash, or underscore")
    return diff_id
