"""
offline.py
----------
Reusable offline Simulation QA evidence workflow.

This module evaluates already-available KPI dictionaries. It does not invoke
Abaqus, read ODB files, check out a license token, or prove solver execution.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from html import escape as escape_html
from pathlib import Path
from typing import Any

from capsule.metadata import evidence_metadata
from capsule.store import MANIFEST_NAME, create_capsule
from contracts.evaluator import evaluate_contracts
from contracts.io import load_contracts
from simdiff.kpi_diff import diff_kpis
from simdiff.kpi_diff import render_markdown as render_diff_markdown

SAFE_RUN_ID = re.compile(r"^[A-Za-z0-9_.-]{1,80}$")


def collect_evidence_from_files(
    *,
    baseline_kpis_path: str | Path,
    candidate_kpis_path: str | Path,
    contracts_path: str | Path,
    out_dir: str | Path,
    run_id: str = "offline-evidence",
    extra_inputs: list[str | Path] | None = None,
) -> dict:
    """Collect offline evidence from local KPI/contract files."""
    safe_run_id = validate_run_id(run_id)
    baseline_kpis = load_kpis(baseline_kpis_path)
    candidate_kpis = load_kpis(candidate_kpis_path)
    contracts = load_contracts(contracts_path)
    input_refs = {
        "baseline_kpis": str(Path(baseline_kpis_path)),
        "candidate_kpis": str(Path(candidate_kpis_path)),
        "contracts": str(Path(contracts_path)),
    }
    capsule_inputs = [
        baseline_kpis_path,
        candidate_kpis_path,
        contracts_path,
        *(extra_inputs or []),
    ]
    return _collect_evidence(
        baseline_kpis=baseline_kpis,
        candidate_kpis=candidate_kpis,
        contracts=contracts,
        out_dir=out_dir,
        run_id=safe_run_id,
        input_refs=input_refs,
        capsule_inputs=capsule_inputs,
    )


def collect_evidence_from_values(
    *,
    baseline_kpis: dict[str, Any],
    candidate_kpis: dict[str, Any],
    contracts: list[dict[str, Any]],
    out_dir: str | Path,
    run_id: str = "offline-evidence",
    input_paths: list[str | Path] | None = None,
    input_metadata: dict[str, Any] | None = None,
) -> dict:
    """Collect offline evidence from API/in-memory values."""
    safe_run_id = validate_run_id(run_id)
    out_path = Path(out_dir)
    request_dir = out_path / "request_inputs"
    request_dir.mkdir(parents=True, exist_ok=True)

    baseline_path = request_dir / "baseline_kpis.json"
    candidate_path = request_dir / "candidate_kpis.json"
    contracts_path = request_dir / "contracts.json"
    baseline_path.write_text(_json_dump(baseline_kpis), encoding="utf-8")
    candidate_path.write_text(_json_dump(candidate_kpis), encoding="utf-8")
    contracts_path.write_text(_json_dump({"contracts": contracts}), encoding="utf-8")

    capsule_inputs: list[str | Path] = [baseline_path, candidate_path, contracts_path]
    input_refs: dict[str, Any] = {
        "baseline_kpis": str(baseline_path),
        "candidate_kpis": str(candidate_path),
        "contracts": str(contracts_path),
    }
    if input_metadata:
        metadata_path = request_dir / "input_metadata.json"
        metadata_path.write_text(_json_dump(input_metadata), encoding="utf-8")
        capsule_inputs.append(metadata_path)
        input_refs["metadata"] = input_metadata

    for path in input_paths or []:
        if path:
            capsule_inputs.append(path)

    return _collect_evidence(
        baseline_kpis=baseline_kpis,
        candidate_kpis=candidate_kpis,
        contracts=contracts,
        out_dir=out_path,
        run_id=safe_run_id,
        input_refs=input_refs,
        capsule_inputs=capsule_inputs,
    )


def load_kpis(path: str | Path) -> dict[str, Any]:
    """Load a KPI JSON object, accepting either a direct object or `{"kpis": ...}`."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, dict) and isinstance(data.get("kpis"), dict):
        return data["kpis"]
    if isinstance(data, dict):
        return data
    raise ValueError(f"KPI file must be a JSON object: {path}")


def render_markdown(evidence: dict) -> str:
    """Render offline evidence as a portable Markdown report."""
    contract = evidence["contracts"]
    diff = evidence["diff"]
    lines = [
        "# Abaqus Agent Offline Evidence Slice Report",
        "",
        "## Verdict Summary",
        "",
        "| Area | Status | Detail |",
        "|---|---|---|",
        f"| Overall | `{evidence['overall_status']}` | Offline KPI evidence bundle generated. |",
        f"| Physics Contracts | `{contract['status']}` | {contract['passed_count']} pass / {contract['warning_count']} warning / {contract['failed_count']} fail. |",
        f"| Simulation Diff | `{diff['status']}` | {diff['total']} KPI rows; {diff['changed_count']} changed, {diff['added_count']} added, {diff['removed_count']} removed. |",
        f"| Real Abaqus execution | `{'verified' if evidence['real_env_verified'] else 'not verified'}` | This report uses supplied KPI JSON values only. |",
        "",
        "## Run Metadata",
        "",
        f"- Project: `{evidence['project']}`",
        f"- Workflow: `{evidence['workflow']}`",
        f"- Run ID: `{evidence['run_id']}`",
        f"- Generated at: `{evidence['generated_at']}`",
        f"- Real environment required: `{str(evidence['real_env_required']).lower()}`",
        f"- Real environment verified: `{str(evidence['real_env_verified']).lower()}`",
        "",
        "## Inputs",
        "",
        f"- Baseline KPIs: `{evidence['inputs']['baseline_kpis']}`",
        f"- Candidate KPIs: `{evidence['inputs']['candidate_kpis']}`",
        f"- Contracts: `{evidence['inputs']['contracts']}`",
    ]
    if evidence["inputs"].get("metadata"):
        metadata = json.dumps(evidence["inputs"]["metadata"], sort_keys=True)
        lines.append(f"- Metadata: `{_escape_md(metadata)}`")

    lines.extend(
        [
            "",
            "## Physics Contracts",
            "",
            f"Status: `{contract['status']}`",
            "",
            "| Contract | Status | Message |",
            "|---|---|---|",
        ]
    )

    checks = contract.get("checks", [])
    if not checks:
        lines.append("| - | INFO | No contract checks supplied. |")
    for check in checks:
        lines.append(
            "| {name} | {status} | {message} |".format(
                name=_escape_md(check.get("name", "-")),
                status=_escape_md(check.get("status", "-")),
                message=_escape_md(check.get("message", "-")),
            )
        )

    lines.extend(["", "## Simulation Diff", ""])
    lines.append(render_diff_markdown(diff).strip())

    capsule = evidence.get("capsule")
    if capsule:
        lines.extend(
            [
                "",
                "## Capsule Provenance",
                "",
                f"- Manifest: `{capsule['manifest_path']}`",
                f"- Capsule hash: `{capsule['capsule_hash']}`",
                f"- Inputs: `{capsule['input_count']}`",
                f"- Artifacts: `{capsule['artifact_count']}`",
            ]
        )

    lines.extend(
        [
            "",
            "## Verification Boundary",
            "",
            "This offline slice evaluates supplied KPI JSON values. It does not invoke Abaqus, read an ODB, check out a license token, or prove real solver execution.",
        ]
    )
    return "\n".join(lines) + "\n"


def render_html(evidence: dict) -> str:
    """Render offline evidence as a self-contained browser-readable report."""
    markdown = render_markdown(evidence)
    return "\n".join(
        [
            "<!doctype html>",
            '<html lang="en">',
            "<head>",
            '  <meta charset="utf-8">',
            "  <title>Abaqus Agent Offline Evidence Slice Report</title>",
            "  <style>",
            "    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; margin: 0; background: #f6f7f9; color: #17191c; }",
            "    main { max-width: 1080px; margin: 0 auto; padding: 32px 24px 48px; }",
            "    h1 { font-size: 28px; margin: 0 0 8px; }",
            "    .meta { color: #5d6673; margin-bottom: 24px; }",
            "    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 12px; margin: 20px 0; }",
            "    .card { background: #fff; border: 1px solid #dfe3e8; border-radius: 8px; padding: 14px; }",
            "    .label { color: #687385; font-size: 12px; text-transform: uppercase; }",
            "    .value { margin-top: 6px; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 18px; }",
            "    pre { white-space: pre-wrap; word-break: break-word; background: #fff; border: 1px solid #dfe3e8; border-radius: 8px; padding: 18px; line-height: 1.55; }",
            "    .boundary { background: #fff7e6; border: 1px solid #ffd27a; border-radius: 8px; padding: 14px; }",
            "  </style>",
            "</head>",
            "<body>",
            "  <main>",
            "    <h1>Abaqus Agent Offline Evidence Slice Report</h1>",
            f"    <div class=\"meta\">Run ID: <code>{escape_html(str(evidence['run_id']))}</code> · Generated: <code>{escape_html(str(evidence['generated_at']))}</code></div>",
            "    <section class=\"grid\">",
            _html_card("Overall", evidence.get("overall_status")),
            _html_card("Contracts", evidence.get("contracts", {}).get("status")),
            _html_card("Diff", evidence.get("diff", {}).get("status")),
            _html_card("Real Abaqus", "verified" if evidence.get("real_env_verified") else "not verified"),
            "    </section>",
            "    <section class=\"boundary\">This report uses supplied KPI JSON values only. It does not invoke Abaqus, read an ODB, check out a license token, or prove real solver execution.</section>",
            "    <h2>Markdown Report</h2>",
            f"    <pre>{escape_html(markdown)}</pre>",
            "  </main>",
            "</body>",
            "</html>",
            "",
        ]
    )


def validate_run_id(run_id: str) -> str:
    """Return a safe run id for local output paths."""
    if not SAFE_RUN_ID.match(run_id):
        raise ValueError("run_id must use 1-80 letters, numbers, dot, dash, or underscore")
    return run_id


def _collect_evidence(
    *,
    baseline_kpis: dict[str, Any],
    candidate_kpis: dict[str, Any],
    contracts: list[dict[str, Any]],
    out_dir: str | Path,
    run_id: str,
    input_refs: dict[str, Any],
    capsule_inputs: list[str | Path],
) -> dict:
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    contract_report = evaluate_contracts(candidate_kpis, contracts)
    diff_report = diff_kpis(
        baseline_kpis,
        candidate_kpis,
        tolerances=_tolerances_from_contracts(contracts),
    )
    evidence = {
        "schema_version": "1.0",
        "project": "abaqus-agent",
        "workflow": "offline-evidence-slice",
        "generated_at": _utc_now(),
        "run_id": run_id,
        "real_env_verified": False,
        "real_env_required": False,
        "inputs": input_refs,
        "baseline_kpis": baseline_kpis,
        "candidate_kpis": candidate_kpis,
        "contracts": contract_report,
        "diff": diff_report,
        "overall_status": _overall_status(contract_report, diff_report),
    }

    evidence_path = out_path / "evidence.json"
    report_path = out_path / "evidence.md"
    html_path = out_path / "evidence.html"
    evidence["html_path"] = str(html_path)
    _write_evidence_files(evidence, evidence_path, report_path, html_path)

    capsule_manifest = create_capsule(
        out_path / "capsule",
        run_id,
        inputs=capsule_inputs,
        artifacts=[evidence_path, report_path, html_path],
        metadata=evidence_metadata(
            workflow="offline-evidence-slice",
            evidence_source="supplied-kpi-json",
            evidence_level="offline",
            overall_status=evidence["overall_status"],
            real_env_required=False,
            real_env_verified=False,
        ),
    )
    manifest_path = out_path / "capsule" / run_id / MANIFEST_NAME
    evidence["capsule"] = {
        "run_id": run_id,
        "manifest_path": str(manifest_path),
        "capsule_hash": capsule_manifest["capsule_hash"],
        "input_count": len(capsule_manifest["inputs"]),
        "artifact_count": len(capsule_manifest["artifacts"]),
    }
    _write_evidence_files(evidence, evidence_path, report_path, html_path)
    return evidence


def _write_evidence_files(
    evidence: dict,
    evidence_path: Path,
    report_path: Path,
    html_path: Path,
) -> None:
    evidence_path.write_text(_json_dump(evidence), encoding="utf-8")
    report_path.write_text(render_markdown(evidence), encoding="utf-8")
    html_path.write_text(render_html(evidence), encoding="utf-8")


def _html_card(label: str, value: Any) -> str:
    return (
        '      <div class="card">'
        f'<div class="label">{escape_html(label)}</div>'
        f'<div class="value">{escape_html(str(value or "-"))}</div>'
        "</div>"
    )


def _tolerances_from_contracts(contracts: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    tolerances: dict[str, dict[str, float]] = {}
    for contract in contracts:
        if contract.get("type") != "relative_error":
            continue
        kpi = contract.get("kpi")
        if not isinstance(kpi, str) or not kpi:
            continue
        tolerances[kpi] = {
            "rtol": float(contract.get("rtol", 0.0)),
            "atol": float(contract.get("atol", 0.0)),
        }
    return tolerances


def _overall_status(contract_report: dict, diff_report: dict) -> str:
    if contract_report["status"] == "FAIL" or diff_report["status"] == "FAIL":
        return "FAIL"
    if contract_report["status"] == "WARNING":
        return "WARNING"
    if contract_report["status"] == "PASS" and diff_report["status"] in {"PASS", "INFO"}:
        return "PASS"
    return "INFO"


def _escape_md(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def _json_dump(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True) + "\n"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
