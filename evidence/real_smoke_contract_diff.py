"""Contract and Simulation Diff evidence over a captured real Abaqus smoke run."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from html import escape as escape_html
from pathlib import Path, PureWindowsPath
from typing import Any

from capsule.metadata import evidence_metadata
from capsule.store import MANIFEST_NAME, create_capsule
from contracts.evaluator import evaluate_contracts
from contracts.io import load_contracts
from simdiff.kpi_diff import diff_kpis
from simdiff.kpi_diff import render_markdown as render_diff_markdown

ROOT = Path(__file__).resolve().parents[1]
SAFE_RUN_ID = re.compile(r"^[A-Za-z0-9_.-]{1,80}$")


def collect_real_smoke_contract_diff(
    *,
    smoke_dir: str | Path,
    out_dir: str | Path,
    contracts_path: str | Path | None = None,
    run_id: str | None = None,
    require_verified: bool = True,
) -> dict[str, Any]:
    """Generate contract/diff/report evidence from an existing real smoke bundle."""
    smoke_path = Path(smoke_dir)
    smoke_evidence_path = smoke_path / "smoke_evidence.json"
    kpi_result_path = smoke_path / "run" / "_kpi_result.json"
    expected_path = smoke_path / "case" / "expected.json"
    spec_path = smoke_path / "case" / "spec.yaml"

    smoke_evidence = _load_json(smoke_evidence_path)
    kpi_result = _load_json(kpi_result_path)
    case_name = str(smoke_evidence.get("case") or smoke_path.name)
    contract_path = Path(contracts_path) if contracts_path else ROOT / "examples" / "contracts" / f"{case_name}.yaml"

    baseline_kpis = _load_expected_kpis(expected_path)
    candidate_kpis = _extract_candidate_kpis(kpi_result)
    contracts = load_contracts(contract_path)
    verified = _is_verified_real_smoke(smoke_evidence, kpi_result)
    if require_verified and not verified:
        raise ValueError("source smoke evidence is not a verified require-real Abaqus smoke run")

    safe_run_id = validate_run_id(run_id or f"{case_name}-real-smoke-contract-diff")
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    contract_report = evaluate_contracts(candidate_kpis, contracts)
    diff_report = diff_kpis(
        baseline_kpis,
        candidate_kpis,
        tolerances=_tolerances_from_contracts(contracts),
    )
    overall_status = _overall_status(contract_report, diff_report)
    local_odb_path = _resolve_local_odb_path(smoke_path, kpi_result)
    stage_summary = _stage_summary(smoke_evidence)

    evidence = {
        "schema_version": "1.0",
        "project": "abaqus-agent",
        "workflow": "real-smoke-contract-diff",
        "generated_at": _utc_now(),
        "run_id": safe_run_id,
        "case": case_name,
        "overall_status": overall_status,
        "real_env_required": True,
        "real_env_verified": verified,
        "inputs": {
            "smoke_evidence": str(smoke_evidence_path),
            "kpi_result": str(kpi_result_path),
            "expected": str(expected_path),
            "contracts": str(contract_path),
            "spec": str(spec_path) if spec_path.exists() else None,
            "odb": str(local_odb_path) if local_odb_path else kpi_result.get("odb_path"),
        },
        "baseline_kpis": baseline_kpis,
        "candidate_kpis": candidate_kpis,
        "contracts": contract_report,
        "diff": diff_report,
        "source_smoke": {
            "mode": smoke_evidence.get("mode"),
            "overall_status": smoke_evidence.get("overall_status"),
            "real_env_verified": smoke_evidence.get("real_env_verified"),
            "out_dir": smoke_evidence.get("out_dir"),
            "kpi_errors": kpi_result.get("errors", []),
            "odb_path": kpi_result.get("odb_path"),
            "local_odb_path": str(local_odb_path) if local_odb_path else None,
            "stages": stage_summary,
        },
    }

    evidence_path = out_path / "real_smoke_contract_diff.json"
    report_path = out_path / "real_smoke_contract_diff.md"
    html_path = out_path / "real_smoke_contract_diff.html"
    evidence["report_path"] = str(report_path)
    evidence["html_path"] = str(html_path)
    _write_evidence_files(evidence, evidence_path, report_path, html_path)

    capsule_inputs = [
        smoke_evidence_path,
        kpi_result_path,
        expected_path,
        contract_path,
        *(path for path in [spec_path] if path.exists()),
    ]
    capsule_artifacts = [
        evidence_path,
        report_path,
        html_path,
        *[
            path
            for path in _smoke_artifact_paths(smoke_path, local_odb_path)
            if path.exists()
        ],
    ]
    capsule_manifest = create_capsule(
        out_path / "capsule",
        safe_run_id,
        inputs=capsule_inputs,
        artifacts=capsule_artifacts,
        metadata=evidence_metadata(
            workflow="real-smoke-contract-diff",
            evidence_source="real-abaqus-smoke",
            evidence_level="real",
            overall_status=overall_status,
            real_env_required=True,
            real_env_verified=verified,
            extra={
                "case": case_name,
                "source_smoke_status": str(smoke_evidence.get("overall_status")),
            },
        ),
    )
    manifest_path = out_path / "capsule" / safe_run_id / MANIFEST_NAME
    evidence["capsule"] = {
        "run_id": safe_run_id,
        "manifest_path": str(manifest_path),
        "capsule_hash": capsule_manifest["capsule_hash"],
        "input_count": len(capsule_manifest["inputs"]),
        "artifact_count": len(capsule_manifest["artifacts"]),
    }
    _write_evidence_files(evidence, evidence_path, report_path, html_path)
    return evidence


def render_markdown(evidence: dict[str, Any]) -> str:
    """Render a real smoke contract/diff report as Markdown."""
    contract = evidence["contracts"]
    diff = evidence["diff"]
    lines = [
        "# Abaqus Agent Real Smoke Contract/Diff Report",
        "",
        "## Verdict Summary",
        "",
        "| Area | Status | Detail |",
        "|---|---|---|",
        f"| Overall | `{evidence['overall_status']}` | Real smoke KPI values were checked against contracts and expected KPI baselines. |",
        f"| Physics Contracts | `{contract['status']}` | {contract['passed_count']} pass / {contract['warning_count']} warning / {contract['failed_count']} fail. |",
        f"| Simulation Diff | `{diff['status']}` | {diff['total']} KPI rows; {diff['changed_count']} changed, {diff['added_count']} added, {diff['removed_count']} removed. |",
        f"| Real Abaqus smoke | `{'verified' if evidence['real_env_verified'] else 'not verified'}` | Source smoke status: `{evidence['source_smoke']['overall_status']}`. |",
        "",
        "## Run Metadata",
        "",
        f"- Project: `{evidence['project']}`",
        f"- Workflow: `{evidence['workflow']}`",
        f"- Case: `{evidence['case']}`",
        f"- Run ID: `{evidence['run_id']}`",
        f"- Generated at: `{evidence['generated_at']}`",
        f"- Real environment required: `{str(evidence['real_env_required']).lower()}`",
        f"- Real environment verified: `{str(evidence['real_env_verified']).lower()}`",
        "",
        "## Real Smoke Source",
        "",
        f"- Smoke evidence: `{evidence['inputs']['smoke_evidence']}`",
        f"- KPI result: `{evidence['inputs']['kpi_result']}`",
        f"- ODB artifact: `{evidence['inputs']['odb']}`",
        f"- Source mode: `{evidence['source_smoke']['mode']}`",
        "",
        "| Stage | Status | Real Verified |",
        "|---|---|---|",
    ]
    for stage in evidence["source_smoke"].get("stages", []):
        lines.append(
            "| {name} | {status} | {verified} |".format(
                name=_escape_md(stage.get("name", "-")),
                status=_escape_md(stage.get("status", "-")),
                verified=str(stage.get("real_env_verified", False)).lower(),
            )
        )

    lines.extend(
        [
            "",
            "## KPI Values",
            "",
            "| KPI | Expected Baseline | Real ODB Candidate |",
            "|---|---:|---:|",
        ]
    )
    for name in sorted(set(evidence["baseline_kpis"]) | set(evidence["candidate_kpis"])):
        lines.append(
            f"| {_escape_md(name)} | {_format_value(evidence['baseline_kpis'].get(name))} | {_format_value(evidence['candidate_kpis'].get(name))} |"
        )

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
    for check in contract.get("checks", []):
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
            "This report does not rerun Abaqus. It extends an already captured `require-real` smoke bundle by checking its extracted ODB KPI values against Physics Contracts and expected KPI baselines.",
        ]
    )
    return "\n".join(lines) + "\n"


def render_html(evidence: dict[str, Any]) -> str:
    """Render a self-contained browser-readable real smoke report."""
    markdown = render_markdown(evidence)
    return "\n".join(
        [
            "<!doctype html>",
            '<html lang="en">',
            "<head>",
            '  <meta charset="utf-8">',
            "  <title>Abaqus Agent Real Smoke Contract/Diff Report</title>",
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
            "    <h1>Abaqus Agent Real Smoke Contract/Diff Report</h1>",
            f"    <div class=\"meta\">Case: <code>{escape_html(str(evidence['case']))}</code> · Run ID: <code>{escape_html(str(evidence['run_id']))}</code></div>",
            "    <section class=\"grid\">",
            _html_card("Overall", evidence.get("overall_status")),
            _html_card("Contracts", evidence.get("contracts", {}).get("status")),
            _html_card("Diff", evidence.get("diff", {}).get("status")),
            _html_card("Real Abaqus", "verified" if evidence.get("real_env_verified") else "not verified"),
            "    </section>",
            "    <section class=\"boundary\">This report extends an already captured real Abaqus smoke bundle; it does not rerun Abaqus.</section>",
            "    <h2>Markdown Report</h2>",
            f"    <pre>{escape_html(markdown)}</pre>",
            "  </main>",
            "</body>",
            "</html>",
            "",
        ]
    )


def validate_run_id(run_id: str) -> str:
    if not SAFE_RUN_ID.match(run_id):
        raise ValueError("run_id must use 1-80 letters, numbers, dot, dash, or underscore")
    return run_id


def _write_evidence_files(
    evidence: dict[str, Any],
    evidence_path: Path,
    report_path: Path,
    html_path: Path,
) -> None:
    evidence_path.write_text(_json_dump(evidence), encoding="utf-8")
    report_path.write_text(render_markdown(evidence), encoding="utf-8")
    html_path.write_text(render_html(evidence), encoding="utf-8")


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"required evidence file not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"expected JSON object: {path}")
    return data


def _load_expected_kpis(path: Path) -> dict[str, Any]:
    data = _load_json(path)
    kpis = data.get("kpis", data)
    if not isinstance(kpis, dict):
        raise ValueError(f"expected KPI object: {path}")
    result: dict[str, Any] = {}
    for name, value in kpis.items():
        if isinstance(value, dict) and "value" in value:
            result[str(name)] = value["value"]
        else:
            result[str(name)] = value
    return result


def _extract_candidate_kpis(kpi_result: dict[str, Any]) -> dict[str, Any]:
    kpis = kpi_result.get("kpis")
    if not isinstance(kpis, dict) or not kpis:
        raise ValueError("KPI result does not contain extracted KPI values")
    return {str(name): value for name, value in kpis.items()}


def _is_verified_real_smoke(smoke_evidence: dict[str, Any], kpi_result: dict[str, Any]) -> bool:
    if smoke_evidence.get("mode") != "require-real":
        return False
    if smoke_evidence.get("overall_status") != "real-env-verified":
        return False
    if smoke_evidence.get("real_env_verified") is not True:
        return False
    if kpi_result.get("errors"):
        return False
    return any(
        stage.get("name") == "odb_kpi_adapter_probe"
        and stage.get("status") == "completed"
        and stage.get("real_env_verified") is True
        for stage in smoke_evidence.get("stages", [])
        if isinstance(stage, dict)
    )


def _resolve_local_odb_path(smoke_dir: Path, kpi_result: dict[str, Any]) -> Path | None:
    raw_path = kpi_result.get("odb_path")
    if not raw_path:
        return None
    direct = Path(str(raw_path))
    if direct.exists():
        return direct
    filename = PureWindowsPath(str(raw_path)).name or direct.name
    candidate = smoke_dir / "run" / filename
    return candidate if candidate.exists() else None


def _smoke_artifact_paths(smoke_dir: Path, local_odb_path: Path | None) -> list[Path]:
    run_dir = smoke_dir / "run"
    job_stem = local_odb_path.stem if local_odb_path else "Cantilever"
    artifacts = [
        smoke_dir / "stage_syntaxcheck.json",
        smoke_dir / "stage_submit_job.json",
        smoke_dir / "stage_monitor_status_collection.json",
        smoke_dir / "stage_odb_kpi_adapter_probe.json",
        run_dir / "_kpi_spec.json",
        run_dir / f"{job_stem}.log",
        run_dir / f"{job_stem}.sta",
        run_dir / f"{job_stem}.dat",
    ]
    if local_odb_path:
        artifacts.append(local_odb_path)
    return artifacts


def _stage_summary(smoke_evidence: dict[str, Any]) -> list[dict[str, Any]]:
    stages = smoke_evidence.get("stages", [])
    if not isinstance(stages, list):
        return []
    return [
        {
            "name": stage.get("name"),
            "status": stage.get("status"),
            "real_env_verified": bool(stage.get("real_env_verified")),
        }
        for stage in stages
        if isinstance(stage, dict)
    ]


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


def _overall_status(contract_report: dict[str, Any], diff_report: dict[str, Any]) -> str:
    if contract_report["status"] == "FAIL" or diff_report["status"] == "FAIL":
        return "FAIL"
    if contract_report["status"] == "WARNING":
        return "WARNING"
    if contract_report["status"] == "PASS" and diff_report["status"] in {"PASS", "INFO"}:
        return "PASS"
    return "INFO"


def _html_card(label: str, value: Any) -> str:
    return (
        '      <div class="card">'
        f'<div class="label">{escape_html(label)}</div>'
        f'<div class="value">{escape_html(str(value or "-"))}</div>'
        "</div>"
    )


def _format_value(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.6g}"
    return _escape_md(value)


def _escape_md(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def _json_dump(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True) + "\n"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
