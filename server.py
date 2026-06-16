"""
server.py
---------
FastAPI server for Abaqus Agent.

Endpoints:
  POST /api/spec/generate     - NL text → spec YAML
  POST /api/spec/validate     - validate spec YAML
  POST /api/run/start         - start pipeline run (async)
  GET  /api/run/{run_id}      - get run status
  GET  /api/run/{run_id}/stream  - SSE stream for real-time stage updates
  GET  /api/benchmark         - get all benchmark case definitions
  POST /api/benchmark/run     - trigger a benchmark dry-run

Run:
  python server.py
  # or: uvicorn server:app --reload --port 8000
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import io
import json
import mimetypes

# ── Project imports ──────────────────────────────────────────────
import sys
import tempfile
import time
import uuid
import zipfile
from pathlib import Path
from typing import Any, AsyncGenerator

import yaml
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

sys.path.insert(0, str(Path(__file__).parent))

from case_memory import (
    CaseMemoryQuery,
    render_memory_markdown,
)
from case_memory import (
    search_case_memory as search_run_case_memory,
)
from copilot.models import CopilotPlan
from copilot.planner import CodexUnavailable, build_copilot_plan, execute_plan
from core.helpers import CASES_DIR, check_abaqus, list_cases, make_run_id
from core.pipeline import (
    run_benchmark_async,
    run_pipeline,
)
from core.spec_generator import generate_spec_async
from doctor.solver_doctor import diagnose_log_texts, list_doctor_patterns, render_markdown
from evidence.case_memory import search_case_memory
from evidence.case_memory_diff import collect_case_memory_diff
from evidence.demo_gallery import collect_demo_gallery
from evidence.examples import get_example, list_examples
from evidence.offline import collect_evidence_from_values, validate_run_id
from evidence.vault import (
    create_vault_entry,
    default_vault_root,
    get_vault_file_path,
    get_vault_record,
    list_vault_entries,
)
from post.kpi_recipes import get_kpi_recipe, list_kpi_recipes
from reporting import (
    build_offline_report_bundle,
    build_offline_report_pdf,
    build_offline_run_report,
    render_html_to_pdf,
    render_run_report_html,
    render_run_report_markdown,
)
from scripts.package_copilot_alpha import build_copilot_alpha_package
from scripts.run_local_cli_smoke import collect_local_cli_smoke
from scripts.run_local_demo_pack import collect_demo_pack_vault_files, create_local_demo_pack
from scripts.verify_copilot_alpha_package import verify_copilot_alpha_package
from scripts.verify_copilot_alpha_release import collect_release_gate
from scripts.verify_local_cli_smoke_bundle import verify_smoke_bundle
from scripts.verify_local_demo_pack_bundle import verify_demo_pack_bundle
from simdiff import diff_runs, render_run_markdown
from simdiff.service import collect_kpi_diff, validate_diff_id
from tools.schema_validator import validate_spec
from validation import render_preflight_markdown, run_environment_preflight

FRONTEND_DIR = Path(__file__).parent / "frontend"

# ── In-memory run store ───────────────────────────────────────────
# {run_id: {status, stages, kpis, spec, ...}}
RUNS: dict[str, dict] = {}
EVIDENCE_ARTIFACTS: dict[str, dict[str, Any]] = {}
EVIDENCE_ARTIFACT_SEQUENCE = 0
DEMO_GALLERY_ARTIFACTS: dict[str, dict[str, Any]] = {}
COPILOT_SESSIONS: dict[str, dict[str, Any]] = {}
COPILOT_SESSION_FILE = Path.home() / ".abaqus_agent_session"

# ── FastAPI app ───────────────────────────────────────────────────
app = FastAPI(
    title="Abaqus Agent API",
    version="0.1.0",
    description=(
        "Local Simulation QA and regression framework for Abaqus FEA: "
        "validate specs, run local evidence workflows, inspect benchmark cases, "
        "and expose dry-run/mock-real/real-runtime boundaries."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve frontend
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


# ── Request / Response models ─────────────────────────────────────

class GenerateSpecRequest(BaseModel):
    text: str
    abaqus_release: str = "2024"
    llm_backend: str = "template"
    anthropic_key: str = ""   # Optional: override ANTHROPIC_API_KEY env var
    openai_key: str = ""      # Optional: override OPENAI_API_KEY env var

class ValidateSpecRequest(BaseModel):
    spec_yaml: str

class StartRunRequest(BaseModel):
    spec_yaml: str
    runner_cfg: dict = Field(default_factory=dict)

class DiffRequest(BaseModel):
    baseline: str
    candidate: str
    rtol: float = 0.05
    tolerances: dict = Field(default_factory=dict)

class MemorySearchRequest(BaseModel):
    roots: list[str]
    query: str = ""
    match_mode: str = "any"
    similar_to: str = ""
    status: str = ""
    model_name: str = ""
    geometry_type: str = ""
    solver: str = ""
    material_name: str = ""
    contract: str = ""
    contracts_passed: str = ""
    diagnosis_id: str = ""
    kpi: str = ""
    artifact: str = ""
    limit: int = 10
    include_artifacts: bool = False
    sort_by: str = "score"
    sort_order: str = "desc"
    min_score: float = 0.0

class EnvironmentPreflightRequest(BaseModel):
    abaqus_cmd: str = ""
    timeout_seconds: float = 15.0
    check_release: bool = True
    expected_release: str = ""
    workdir: str = ""
    runner_cfg: dict = Field(default_factory=dict)

class OfflineReportRequest(BaseModel):
    source: str
    template: str = "standard"
    max_artifact_bytes: int = 25_000_000

class OfflineEvidenceRequest(BaseModel):
    baseline_kpis: dict[str, Any]
    candidate_kpis: dict[str, Any]
    contracts: list[dict[str, Any]]
    run_id: str = "offline-evidence"
    input_path: str = ""
    input_metadata: dict[str, Any] = Field(default_factory=dict)

class SimulationDiffRequest(BaseModel):
    baseline_kpis: dict[str, Any]
    candidate_kpis: dict[str, Any]
    tolerances: dict[str, dict[str, float]] = Field(default_factory=dict)
    diff_id: str = "simulation-diff"
    input_metadata: dict[str, Any] = Field(default_factory=dict)

class DoctorDiagnoseRequest(BaseModel):
    job_name: str = "Job-1"
    msg_text: str = ""
    dat_text: str = ""
    sta_text: str = ""
    log_text: str = ""

class CaseMemoryDiffRequest(BaseModel):
    baseline_vault_id: str
    candidate_vault_id: str
    diff_id: str = "case-memory-diff"
    baseline_filename: str | None = None
    candidate_filename: str | None = None

class CopilotPlanRequest(BaseModel):
    text: str
    backend: str = "codex"

class CopilotExecuteRequest(BaseModel):
    session_id: str
    bridge_mode: str = "mock"

class CopilotActionResultRequest(BaseModel):
    action_index: int
    status: str
    message: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)


def _artifact_id(run_id: str) -> str:
    return f"{run_id}-{uuid.uuid4().hex[:8]}"


def _register_evidence_artifacts(
    *,
    run_id: str,
    evidence: dict[str, Any],
    evidence_path: Path,
    report_path: Path,
    html_path: Path,
    capsule_manifest_path: Path,
    url_prefix: str = "/api/evidence/artifacts",
) -> dict[str, Any]:
    global EVIDENCE_ARTIFACT_SEQUENCE
    EVIDENCE_ARTIFACT_SEQUENCE += 1
    artifact_id = _artifact_id(run_id)
    generated_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    bundle_path = report_path.parent / f"{artifact_id}.zip"
    _write_evidence_bundle_zip(
        bundle_path=bundle_path,
        artifact_id=artifact_id,
        run_id=run_id,
        generated_at=generated_at,
        evidence_path=evidence_path,
        report_path=report_path,
        html_path=html_path,
        capsule_manifest_path=capsule_manifest_path,
    )
    artifact_urls = {
        "evidence_json": f"{url_prefix}/{artifact_id}/evidence.json",
        "report_markdown": f"{url_prefix}/{artifact_id}/evidence.md",
        "report_html": f"{url_prefix}/{artifact_id}/evidence.html",
        "capsule_manifest": f"{url_prefix}/{artifact_id}/capsule.json",
        "bundle_zip": f"{url_prefix}/{artifact_id}/bundle.zip",
    }
    record = _evidence_artifact_record(
        artifact_id=artifact_id,
        run_id=run_id,
        generated_at=generated_at,
        sequence=EVIDENCE_ARTIFACT_SEQUENCE,
        artifact_urls=artifact_urls,
        evidence=evidence,
    )
    EVIDENCE_ARTIFACTS[artifact_id] = {
        "files": {
            "evidence.json": evidence_path,
            "evidence.md": report_path,
            "evidence.html": html_path,
            "capsule.json": capsule_manifest_path,
            "bundle.zip": bundle_path,
        },
        "record": record,
    }
    return {"artifact_id": artifact_id, "artifact_urls": artifact_urls}


def _evidence_artifact_record(
    *,
    artifact_id: str,
    run_id: str,
    generated_at: str,
    sequence: int,
    artifact_urls: dict[str, str],
    evidence: dict[str, Any],
) -> dict[str, Any]:
    contracts = evidence.get("contracts", {})
    diff = evidence.get("diff", {})
    capsule = evidence.get("capsule", {})
    return {
        "artifact_id": artifact_id,
        "run_id": run_id,
        "generated_at": generated_at,
        "sequence": sequence,
        "overall_status": evidence.get("overall_status"),
        "real_env_verified": evidence.get("real_env_verified"),
        "contracts": {
            "status": contracts.get("status"),
            "total": contracts.get("total"),
            "failed_count": contracts.get("failed_count"),
            "warning_count": contracts.get("warning_count"),
        },
        "diff": {
            "status": diff.get("status"),
            "total": diff.get("total"),
            "changed_count": diff.get("changed_count"),
            "added_count": diff.get("added_count"),
            "removed_count": diff.get("removed_count"),
        },
        "capsule": {
            "run_id": capsule.get("run_id"),
            "capsule_hash": capsule.get("capsule_hash"),
            "input_count": capsule.get("input_count"),
            "artifact_count": capsule.get("artifact_count"),
        },
        "artifact_urls": artifact_urls,
    }


def _write_evidence_bundle_zip(
    *,
    bundle_path: Path,
    artifact_id: str,
    run_id: str,
    generated_at: str,
    evidence_path: Path,
    report_path: Path,
    html_path: Path,
    capsule_manifest_path: Path,
) -> None:
    manifest = {
        "schema_version": "1.0",
        "artifact_id": artifact_id,
        "run_id": run_id,
        "generated_at": generated_at,
        "files": ["evidence.json", "evidence.md", "evidence.html", "capsule.json"],
    }
    with zipfile.ZipFile(bundle_path, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        bundle.write(evidence_path, "evidence.json")
        bundle.write(report_path, "evidence.md")
        bundle.write(html_path, "evidence.html")
        bundle.write(capsule_manifest_path, "capsule.json")
        bundle.writestr("bundle_manifest.json", json.dumps(manifest, indent=2, sort_keys=True))


def _get_evidence_artifact_path(artifact_id: str, filename: str) -> Path:
    artifact = EVIDENCE_ARTIFACTS.get(artifact_id)
    files = artifact.get("files", {}) if artifact else {}
    if filename not in files:
        raise HTTPException(status_code=404, detail="Evidence artifact not found")
    path = files[filename]
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Evidence artifact file missing")
    return path


def _list_evidence_artifact_records(limit: int = 20) -> dict[str, Any]:
    safe_limit = max(1, min(limit, 100))
    items = [
        artifact["record"]
        for artifact in EVIDENCE_ARTIFACTS.values()
        if "record" in artifact
    ]
    items.sort(key=lambda item: item["sequence"], reverse=True)
    return {"items": items[:safe_limit], "total": len(items)}


def _create_vault_entry(
    *,
    kind: str,
    title: str,
    files: dict[str, Path],
    summary: dict[str, Any],
    url_prefix: str = "/api/evidence/vault",
) -> dict[str, Any]:
    record = create_vault_entry(kind=kind, title=title, files=files, summary=summary)
    vault_urls = {
        filename: f"{url_prefix}/{record['vault_id']}/{filename}"
        for filename in record["files"]
    }
    return {"vault_id": record["vault_id"], "vault_urls": vault_urls}


def _register_demo_gallery_artifacts(
    *,
    index: dict[str, Any],
    out_dir: Path,
    url_prefix: str = "/api/evidence/demo-gallery",
) -> dict[str, Any]:
    artifact_id = _artifact_id("demo-gallery")
    artifact_urls = {
        "index_json": f"{url_prefix}/{artifact_id}/index.json",
        "index_markdown": f"{url_prefix}/{artifact_id}/index.md",
        "index_html": f"{url_prefix}/{artifact_id}/index.html",
        "gallery_zip": f"{url_prefix}/{artifact_id}/offline-demo-gallery.zip",
    }
    record = {
        "artifact_id": artifact_id,
        "generated_at": index["generated_at"],
        "overall_status": index["overall_status"],
        "case_count": index["case_count"],
        "cases": [
            {
                "case": case["case"],
                "overall_status": case["overall_status"],
                "contracts_status": case["contracts_status"],
                "diff_status": case["diff_status"],
                "capsule_hash": case["capsule_hash"],
            }
            for case in index["cases"]
        ],
        "artifact_urls": artifact_urls,
    }
    DEMO_GALLERY_ARTIFACTS[artifact_id] = {
        "files": {
            "index.json": out_dir / "index.json",
            "index.md": out_dir / "index.md",
            "index.html": out_dir / "index.html",
            "offline-demo-gallery.zip": Path(index["gallery_zip_path"]),
        },
        "record": record,
    }
    return {"artifact_id": artifact_id, "artifact_urls": artifact_urls, "record": record}


def _get_demo_gallery_artifact_path(artifact_id: str, filename: str) -> Path:
    artifact = DEMO_GALLERY_ARTIFACTS.get(artifact_id)
    files = artifact.get("files", {}) if artifact else {}
    if filename not in files:
        raise HTTPException(status_code=404, detail="Demo gallery artifact not found")
    path = files[filename]
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Demo gallery artifact file missing")
    return path


# ── Routes ───────────────────────────────────────────────────────

@app.get("/")
def root():
    index = FRONTEND_DIR / "index.html"
    if index.exists():
        return FileResponse(str(index))
    return {"status": "ok", "message": "Abaqus Agent API running"}


@app.get("/health")
def health():
    return {
        "status": "ok",
        "abaqus_available": check_abaqus(),
        "cases": list_cases(),
        "version": "0.1.0",
    }


# ── Copilot endpoints ─────────────────────────────────────────────

@app.get("/api/copilot/status")
def get_copilot_status():
    """Expose the user-facing Copilot runtime status."""
    return {
        "status": "ok",
        "codex_app_server": "available",
        "auth_mode": "local_codex_app_server",
        "abaqus_available": check_abaqus(),
        "supported_actions": [
            "create_cantilever_model",
            "apply_boundary_condition",
            "submit_job_or_prepare_run",
        ],
        "sessions": len(COPILOT_SESSIONS),
    }


@app.get("/api/copilot/plugin-guide")
def get_copilot_plugin_guide(request: Request):
    """Return copy-paste setup details for the Abaqus/CAE Copilot plug-in."""
    server_url = str(request.base_url).rstrip("/")
    return {
        "server_url": server_url,
        "install_command": "abaqus-agent-copilot-install-plugin --plugin-dir <ABAQUS_PLUGIN_DIR>",
        "remote_server_env": f"ABAQUS_AGENT_SERVER_URL={server_url}",
        "session_file": str(COPILOT_SESSION_FILE),
        "open_sidecar_action": "AbaqusAgent Copilot: Open Sidecar",
        "run_plan_action": "AbaqusAgent Copilot: Run Current Plan",
        "execute_next_action": "AbaqusAgent Copilot: Execute Next Action",
        "status_action": "AbaqusAgent Copilot: Check Session Status",
        "execution_loop": "优先点击 Run Current Plan 一键执行完整队列；需要调试时再用 Execute Next Action 单步执行。",
    }


@app.get("/api/copilot/release-gate")
def get_copilot_release_gate(strict_gui: bool = False):
    """Return current Copilot Alpha/release evidence status."""
    return collect_release_gate(root=Path(__file__).parent, strict_gui=strict_gui)


@app.get("/api/copilot/alpha-package.zip")
def get_copilot_alpha_package(request: Request):
    """Build and download the current Copilot Alpha package."""
    server_url = str(request.base_url).rstrip("/")
    result = build_copilot_alpha_package(root=Path(__file__).parent, server_url=server_url)
    package_path = Path(result["package_path"])
    if not package_path.exists():
        raise HTTPException(status_code=404, detail="Copilot Alpha package not found")
    return FileResponse(
        package_path,
        media_type="application/zip",
        filename=result["package_name"],
    )


@app.get("/api/copilot/alpha-package/verify")
def verify_copilot_alpha_package_endpoint(request: Request):
    """Build and verify the current Copilot Alpha package."""
    server_url = str(request.base_url).rstrip("/")
    package = build_copilot_alpha_package(root=Path(__file__).parent, server_url=server_url)
    verification = verify_copilot_alpha_package(package["package_path"])
    return {
        "package": package,
        "verification": verification,
    }


@app.post("/api/copilot/plan")
def create_copilot_plan(req: CopilotPlanRequest):
    """Convert a beginner-friendly Abaqus request into safe CAE actions."""
    try:
        plan = build_copilot_plan(req.text, backend=req.backend)
    except CodexUnavailable as e:
        raise HTTPException(status_code=503, detail=f"Codex app-server unavailable: {e}")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    plan_data = plan.model_dump()
    COPILOT_SESSIONS[plan.session_id] = {
        "plan": plan_data,
        "pending_actions": plan_data["actions"].copy(),
        "results": [],
        "created_at": time.time(),
    }
    return plan_data


@app.post("/api/copilot/execute")
def execute_copilot_plan(req: CopilotExecuteRequest):
    """Prepare or execute a Copilot action plan through the local bridge."""
    record = COPILOT_SESSIONS.get(req.session_id)
    if not record:
        raise HTTPException(status_code=404, detail="Copilot session not found")
    plan = CopilotPlan.model_validate(record["plan"])
    result = execute_plan(plan, bridge_mode=req.bridge_mode)
    result_data = result.model_dump()
    record["execution"] = result_data
    return result_data


@app.get("/api/copilot/sessions/{session_id}")
def get_copilot_session(session_id: str):
    """Return a Copilot session summary for sidecar/plugin progress UI."""
    record = COPILOT_SESSIONS.get(session_id)
    if not record:
        raise HTTPException(status_code=404, detail="Copilot session not found")
    plan = record.get("plan") or {}
    pending_actions = record.get("pending_actions") or []
    results = record.get("results") or []
    return {
        "session_id": session_id,
        "backend": plan.get("backend"),
        "user_summary": plan.get("user_summary"),
        "action_count": len(plan.get("actions") or []),
        "pending_count": len(pending_actions),
        "completed_count": len(results),
        "results": results,
        "execution": record.get("execution"),
        "created_at": record.get("created_at"),
    }


@app.get("/api/copilot/sessions/{session_id}/next-action")
def get_copilot_next_action(session_id: str):
    """Endpoint polled by the Abaqus/CAE plugin bridge."""
    record = COPILOT_SESSIONS.get(session_id)
    if not record:
        raise HTTPException(status_code=404, detail="Copilot session not found")
    pending = record.get("pending_actions") or []
    if not pending:
        return {"session_id": session_id, "action": None}
    return {
        "session_id": session_id,
        "action_index": len(record.get("results", [])),
        "action": pending[0],
    }


@app.post("/api/copilot/sessions/{session_id}/activate")
def activate_copilot_session(session_id: str):
    """Make a Copilot session the default session for the local CAE plug-in."""
    if session_id not in COPILOT_SESSIONS:
        raise HTTPException(status_code=404, detail="Copilot session not found")
    COPILOT_SESSION_FILE.write_text(session_id, encoding="utf-8")
    return {
        "session_id": session_id,
        "session_file": str(COPILOT_SESSION_FILE),
        "plugin_action": "AbaqusAgent Copilot: Run Current Plan",
        "debug_plugin_action": "AbaqusAgent Copilot: Execute Next Action",
        "message": "Copilot session activated for the local Abaqus/CAE plug-in.",
    }


@app.post("/api/copilot/sessions/{session_id}/action-result")
def post_copilot_action_result(session_id: str, req: CopilotActionResultRequest):
    """Record a result from the Abaqus/CAE plugin bridge."""
    record = COPILOT_SESSIONS.get(session_id)
    if not record:
        raise HTTPException(status_code=404, detail="Copilot session not found")
    pending = record.get("pending_actions") or []
    if pending:
        pending.pop(0)
    result = {
        "action_index": req.action_index,
        "status": req.status,
        "message": req.message,
        "payload": req.payload,
        "received_at": time.time(),
    }
    record.setdefault("results", []).append(result)
    return {
        "session_id": session_id,
        "remaining_actions": len(record.get("pending_actions") or []),
        "result": result,
    }


@app.post("/api/validate/env")
def post_environment_preflight(req: EnvironmentPreflightRequest):
    try:
        result = run_environment_preflight(
            abaqus_cmd=req.abaqus_cmd or None,
            timeout_seconds=req.timeout_seconds,
            check_release=req.check_release,
            expected_release=req.expected_release,
            workdir=req.workdir or None,
            runner_cfg=req.runner_cfg,
        )
    except (OSError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    result["markdown"] = render_preflight_markdown(result)
    return result


@app.post("/api/report/export")
def post_offline_report_export(req: OfflineReportRequest):
    try:
        report = build_offline_run_report(req.source, template=req.template, embed_images=True)
    except (FileNotFoundError, OSError, json.JSONDecodeError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    report["offline_source"] = req.source
    return report


@app.post("/api/report/export.zip")
def post_offline_report_export_bundle(req: OfflineReportRequest):
    try:
        report = build_offline_run_report(req.source, template=req.template, embed_images=False)
        content = build_offline_report_bundle(
            req.source,
            template=req.template,
            max_artifact_bytes=req.max_artifact_bytes,
        )
    except (FileNotFoundError, OSError, json.JSONDecodeError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    run_id = report.get("summary", {}).get("run_id") or "offline"
    return Response(
        content=content,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="abaqus-report-{run_id}.zip"'},
    )


@app.post("/api/report/export.pdf")
def post_offline_report_export_pdf(req: OfflineReportRequest):
    try:
        content = build_offline_report_pdf(req.source, template=req.template)
        report = build_offline_run_report(req.source, template=req.template, embed_images=False)
    except (FileNotFoundError, OSError, json.JSONDecodeError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=501, detail=str(e))
    run_id = report.get("summary", {}).get("run_id") or "offline"
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="abaqus-report-{run_id}.pdf"'},
    )


# ── Spec endpoints ────────────────────────────────────────────────

@app.post("/api/spec/generate")
async def generate_spec(req: GenerateSpecRequest):
    """Convert natural language to Problem Spec YAML."""
    try:
        spec_dict, missing = await generate_spec_async(
            req.text, req.abaqus_release, req.llm_backend,
            anthropic_key=req.anthropic_key,
            openai_key=req.openai_key,
        )
        spec_yaml = yaml.dump(spec_dict, allow_unicode=True, default_flow_style=False)
        valid, errors = validate_spec(spec_dict)
        return {
            "spec_yaml": spec_yaml,
            "spec_dict": spec_dict,
            "valid": valid,
            "errors": errors,
            "missing_questions": missing,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/spec/validate")
def validate_spec_endpoint(req: ValidateSpecRequest):
    """Validate a spec YAML string."""
    try:
        spec_dict = yaml.safe_load(req.spec_yaml)
        valid, errors = validate_spec(spec_dict)
        return {"valid": valid, "errors": errors}
    except yaml.YAMLError as e:
        return {"valid": False, "errors": [f"YAML parse error: {e}"]}


# ── Evidence endpoints ────────────────────────────────────────────

@app.get("/api/evidence/examples")
def list_offline_evidence_examples():
    """List built-in offline evidence example cases."""
    return list_examples()


@app.get("/api/evidence/examples/{case_name}")
def get_offline_evidence_example(case_name: str):
    """Return one built-in offline evidence example payload."""
    try:
        return get_example(case_name)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/evidence/offline")
def create_offline_evidence(req: OfflineEvidenceRequest):
    """Run the offline KPI contract/diff/capsule evidence workflow."""
    try:
        run_id = validate_run_id(req.run_id)
        out_dir = Path(tempfile.mkdtemp(prefix=f"abaqus-agent-offline-{run_id}."))
        input_paths = []
        if req.input_path:
            input_path = Path(req.input_path).expanduser()
            if not input_path.exists() or not input_path.is_file():
                raise HTTPException(status_code=400, detail=f"Input path not found: {req.input_path}")
            input_paths.append(input_path)

        evidence = collect_evidence_from_values(
            baseline_kpis=req.baseline_kpis,
            candidate_kpis=req.candidate_kpis,
            contracts=req.contracts,
            out_dir=out_dir,
            run_id=run_id,
            input_paths=input_paths,
            input_metadata=req.input_metadata,
        )
        evidence_path = out_dir / "evidence.json"
        report_path = out_dir / "evidence.md"
        html_path = out_dir / "evidence.html"
        artifacts = _register_evidence_artifacts(
            run_id=run_id,
            evidence=evidence,
            evidence_path=evidence_path,
            report_path=report_path,
            html_path=html_path,
            capsule_manifest_path=Path(evidence["capsule"]["manifest_path"]),
        )
        artifact_files = EVIDENCE_ARTIFACTS[artifacts["artifact_id"]]["files"]
        vault = _create_vault_entry(
            kind="offline-evidence",
            title=run_id,
            files={
                "evidence.json": artifact_files["evidence.json"],
                "evidence.md": artifact_files["evidence.md"],
                "evidence.html": artifact_files["evidence.html"],
                "capsule.json": artifact_files["capsule.json"],
                "bundle.zip": artifact_files["bundle.zip"],
            },
            summary={
                "overall_status": evidence["overall_status"],
                "real_env_verified": evidence["real_env_verified"],
                "contracts_status": evidence["contracts"]["status"],
                "diff_status": evidence["diff"]["status"],
            },
        )
        return {
            "run_id": evidence["run_id"],
            **artifacts,
            **vault,
            "overall_status": evidence["overall_status"],
            "real_env_verified": evidence["real_env_verified"],
            "contracts": {
                "status": evidence["contracts"]["status"],
                "total": evidence["contracts"]["total"],
                "failed_count": evidence["contracts"]["failed_count"],
                "warning_count": evidence["contracts"]["warning_count"],
            },
            "diff": {
                "status": evidence["diff"]["status"],
                "total": evidence["diff"]["total"],
                "changed_count": evidence["diff"]["changed_count"],
                "added_count": evidence["diff"]["added_count"],
                "removed_count": evidence["diff"]["removed_count"],
            },
            "capsule": evidence["capsule"],
            "evidence_path": str(evidence_path),
            "report_path": str(report_path),
            "html_path": str(html_path),
            "report_markdown": report_path.read_text(encoding="utf-8"),
        }
    except HTTPException:
        raise
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/evidence/demo-gallery")
def create_offline_demo_gallery():
    """Generate a downloadable offline evidence demo gallery for all examples."""
    out_dir = Path(tempfile.mkdtemp(prefix="abaqus-agent-demo-gallery."))
    index = collect_demo_gallery(out_dir)
    artifacts = _register_demo_gallery_artifacts(index=index, out_dir=out_dir)
    vault = _create_vault_entry(
        kind="demo-gallery",
        title="offline-demo-gallery",
        files={
            "index.json": out_dir / "index.json",
            "index.md": out_dir / "index.md",
            "index.html": out_dir / "index.html",
            "offline-demo-gallery.zip": Path(index["gallery_zip_path"]),
        },
        summary={
            "overall_status": index["overall_status"],
            "case_count": index["case_count"],
        },
    )
    return {
        **artifacts["record"],
        **vault,
        "index": index,
        "index_markdown": (out_dir / "index.md").read_text(encoding="utf-8"),
        "index_html": (out_dir / "index.html").read_text(encoding="utf-8"),
        "index_html_url": vault["vault_urls"]["index.html"],
    }


@app.get("/api/evidence/demo-gallery/{artifact_id}/{filename}")
def get_offline_demo_gallery_artifact(artifact_id: str, filename: str):
    """Return a generated offline demo gallery artifact from this server process."""
    media_types = {
        "index.json": "application/json",
        "index.md": "text/markdown; charset=utf-8",
        "index.html": "text/html; charset=utf-8",
        "offline-demo-gallery.zip": "application/zip",
    }
    if filename not in media_types:
        raise HTTPException(status_code=404, detail="Demo gallery artifact not found")
    return FileResponse(
        _get_demo_gallery_artifact_path(artifact_id, filename),
        media_type=media_types[filename],
        filename=filename,
    )


@app.post("/api/evidence/demo-pack")
def create_local_demo_pack_endpoint():
    """Generate a downloadable local product demo pack."""
    out_dir = Path(tempfile.mkdtemp(prefix="abaqus-agent-local-demo-pack."))
    index = create_local_demo_pack(out_dir)
    vault = _create_vault_entry(
        kind="local-demo-pack",
        title="local-demo-pack",
        files=collect_demo_pack_vault_files(index),
        summary={
            "overall_status": index["overall_status"],
            "real_env_verified": index["real_env_verified"],
            "gallery_case_count": index["offline_demo_gallery"]["case_count"],
            "doctor_status": index["solver_doctor"]["status"],
            "simulation_diff_status": index["simulation_diff"]["status"],
        },
    )
    return {
        **vault,
        "overall_status": index["overall_status"],
        "real_env_verified": index["real_env_verified"],
        "index": index,
        "index_markdown": (out_dir / "index.md").read_text(encoding="utf-8"),
        "index_html": (out_dir / "index.html").read_text(encoding="utf-8"),
        "index_html_url": vault["vault_urls"]["index.html"],
        "pack_zip_url": vault["vault_urls"]["local-demo-pack.zip"],
    }


@app.post("/api/evidence/local-cli-smoke")
def run_local_cli_smoke_endpoint():
    """Run local no-server CLI smoke and return reviewable evidence report paths."""
    out_dir = Path(tempfile.mkdtemp(prefix="abaqus-agent-api-cli-smoke."))
    report = collect_local_cli_smoke(out_dir, vault_root=default_vault_root())
    markdown_path = Path(report["markdown_path"])
    html_path = Path(report["html_path"])
    smoke_vault_urls = {
        filename: f"/api/evidence/vault/{report['smoke_vault_id']}/{filename}"
        for filename in report.get("smoke_vault_files", [])
    }
    return {
        "overall_status": report["overall_status"],
        "real_env_verified": report["real_env_verified"],
        "workflow": report["workflow"],
        "step_count": len(report["steps"]),
        "steps": report["steps"],
        "vault_id": report["vault_id"],
        "smoke_vault_id": report["smoke_vault_id"],
        "vault_root": report["vault_root"],
        "json_path": report["json_path"],
        "markdown_path": report["markdown_path"],
        "html_path": report["html_path"],
        "smoke_vault_urls": smoke_vault_urls,
        "report_markdown": markdown_path.read_text(encoding="utf-8"),
        "report_html": html_path.read_text(encoding="utf-8"),
    }


@app.get("/api/evidence/artifacts/{artifact_id}/{filename}")
def get_offline_evidence_artifact(artifact_id: str, filename: str):
    """Return a generated offline evidence artifact from the in-process registry."""
    media_types = {
        "evidence.json": "application/json",
        "capsule.json": "application/json",
        "evidence.md": "text/markdown; charset=utf-8",
        "evidence.html": "text/html; charset=utf-8",
        "bundle.zip": "application/zip",
    }
    if filename not in media_types:
        raise HTTPException(status_code=404, detail="Evidence artifact not found")
    return FileResponse(
        _get_evidence_artifact_path(artifact_id, filename),
        media_type=media_types[filename],
        filename=filename,
    )


@app.get("/api/evidence/artifacts")
def list_offline_evidence_artifacts(limit: int = 20):
    """List recent offline evidence artifacts registered in this server process."""
    return _list_evidence_artifact_records(limit)


@app.get("/api/evidence/vault")
def list_evidence_vault(limit: int = 50, query: str = "", kind: str = "", status: str = ""):
    """List persisted local evidence vault entries."""
    data = list_vault_entries(limit=limit, query=query, kind=kind, status=status)
    for item in data["items"]:
        _attach_vault_urls(item, url_prefix="/api/evidence/vault")
    return data


@app.post("/api/evidence/vault/{vault_id}/verify-smoke")
def verify_evidence_vault_smoke_bundle(vault_id: str, filename: str = "local_cli_smoke.zip"):
    """Verify a stored local CLI smoke ZIP bundle against its embedded manifest."""
    try:
        path = get_vault_file_path(vault_id, filename)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    data = verify_smoke_bundle(path)
    data["vault_id"] = vault_id
    data["filename"] = filename
    data["source_path"] = str(path)
    return data


@app.post("/api/evidence/vault/{vault_id}/verify-demo-pack")
def verify_evidence_vault_demo_pack_bundle(vault_id: str, filename: str = "local-demo-pack.zip"):
    """Verify a stored local demo pack ZIP bundle against its embedded manifest."""
    try:
        path = get_vault_file_path(vault_id, filename)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    data = verify_demo_pack_bundle(path)
    data["vault_id"] = vault_id
    data["filename"] = filename
    data["source_path"] = str(path)
    return data


@app.get("/api/evidence/vault/{vault_id}/{filename:path}")
def get_evidence_vault_file(vault_id: str, filename: str):
    """Return a persisted local evidence vault file."""
    media_types = {
        ".json": "application/json",
        ".md": "text/markdown; charset=utf-8",
        ".html": "text/html; charset=utf-8",
        ".zip": "application/zip",
    }
    try:
        path = get_vault_file_path(vault_id, filename)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return FileResponse(
        path,
        media_type=media_types.get(path.suffix, "application/octet-stream"),
        filename=filename,
    )


@app.get("/api/evidence/vault/{vault_id}")
def get_evidence_vault_record(vault_id: str):
    """Return one persisted local evidence vault record."""
    if Path(vault_id).suffix in {".json", ".md", ".html", ".zip"}:
        raise HTTPException(status_code=400, detail=f"Vault id is invalid: {vault_id}")
    try:
        record = get_vault_record(vault_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    _attach_vault_urls(record, url_prefix="/api/evidence/vault")
    return record


def _attach_vault_urls(record: dict[str, Any], *, url_prefix: str) -> None:
    record["vault_urls"] = {
        filename: f"{url_prefix}/{record['vault_id']}/{filename}"
        for filename in record.get("files", {})
    }


@app.get("/api/case-memory")
def list_case_memory(
    query: str = "",
    kind: str = "",
    status: str = "",
    limit: int = 50,
):
    """List/search local Case Memory entries backed by the evidence vault."""
    return search_case_memory(
        query=query,
        kind=kind,
        status=status,
        limit=limit,
        url_prefix="/api/evidence/vault",
    )


@app.post("/api/case-memory/diff")
def create_case_memory_diff(req: CaseMemoryDiffRequest):
    """Compare KPI artifacts from two saved Case Memory vault entries."""
    try:
        diff_id = validate_diff_id(req.diff_id)
        out_dir = Path(tempfile.mkdtemp(prefix=f"abaqus-agent-case-memory-diff-{diff_id}."))
        result = collect_case_memory_diff(
            baseline_vault_id=req.baseline_vault_id,
            candidate_vault_id=req.candidate_vault_id,
            out_dir=out_dir,
            diff_id=diff_id,
            baseline_filename=req.baseline_filename,
            candidate_filename=req.candidate_filename,
        )
        diff_json_path = out_dir / "diff.json"
        diff_markdown_path = out_dir / "diff.md"
        vault = _create_vault_entry(
            kind="case-memory-diff",
            title=diff_id,
            files={"diff.json": diff_json_path, "diff.md": diff_markdown_path},
            summary={
                "overall_status": result["overall_status"],
                "diff_status": result["diff"]["status"],
                "changed_count": result["diff"]["changed_count"],
                "added_count": result["diff"]["added_count"],
                "removed_count": result["diff"]["removed_count"],
                "baseline_vault_id": req.baseline_vault_id,
                "candidate_vault_id": req.candidate_vault_id,
                "baseline_filename": req.baseline_filename or "",
                "candidate_filename": req.candidate_filename or "",
                "real_env_verified": result["real_env_verified"],
            },
        )
        return {
            "diff_id": result["diff_id"],
            **vault,
            "overall_status": result["overall_status"],
            "real_env_verified": result["real_env_verified"],
            "diff": result["diff"],
            "case_memory_diff": result["case_memory_diff"],
            "diff_path": str(diff_json_path),
            "report_path": str(diff_markdown_path),
            "report_markdown": diff_markdown_path.read_text(encoding="utf-8"),
        }
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/kpi-recipes")
def list_builtin_kpi_recipes(case: str = "", kpi_type: str = ""):
    """List built-in ODB Lens KPI recipes."""
    return list_kpi_recipes(case=case, kpi_type=kpi_type)


@app.get("/api/kpi-recipes/{recipe_id}")
def get_builtin_kpi_recipe(recipe_id: str):
    try:
        return get_kpi_recipe(recipe_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# ── Simulation Diff endpoints ─────────────────────────────────────

@app.post("/api/simdiff/kpis")
def create_simulation_diff(req: SimulationDiffRequest):
    """Compare supplied baseline/candidate KPI dictionaries without invoking Abaqus."""
    try:
        diff_id = validate_diff_id(req.diff_id)
        out_dir = Path(tempfile.mkdtemp(prefix=f"abaqus-agent-simdiff-{diff_id}."))
        result = collect_kpi_diff(
            baseline_kpis=req.baseline_kpis,
            candidate_kpis=req.candidate_kpis,
            tolerances=req.tolerances,
            out_dir=out_dir,
            diff_id=diff_id,
            input_metadata=req.input_metadata,
        )
        diff_json_path = out_dir / "diff.json"
        diff_markdown_path = out_dir / "diff.md"
        vault = _create_vault_entry(
            kind="simulation-diff",
            title=diff_id,
            files={
                "diff.json": diff_json_path,
                "diff.md": diff_markdown_path,
            },
            summary={
                "overall_status": result["overall_status"],
                "diff_status": result["diff"]["status"],
                "total": result["diff"]["total"],
                "changed_count": result["diff"]["changed_count"],
                "added_count": result["diff"]["added_count"],
                "removed_count": result["diff"]["removed_count"],
                "real_env_verified": result["real_env_verified"],
            },
        )
        return {
            "diff_id": result["diff_id"],
            **vault,
            "overall_status": result["overall_status"],
            "real_env_verified": result["real_env_verified"],
            "diff": result["diff"],
            "diff_path": str(diff_json_path),
            "report_path": str(diff_markdown_path),
            "report_markdown": diff_markdown_path.read_text(encoding="utf-8"),
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# ── Solver Doctor endpoints ───────────────────────────────────────

@app.get("/api/doctor/patterns")
def list_solver_doctor_patterns(category: str = "", severity: str = ""):
    """List supported Solver Doctor diagnostic categories and parser patterns."""
    return list_doctor_patterns(category=category, severity=severity)


@app.post("/api/doctor/diagnose")
def diagnose_solver_logs(req: DoctorDiagnoseRequest):
    """Diagnose supplied Abaqus log text without invoking Abaqus."""
    try:
        report = diagnose_log_texts(
            job_name=req.job_name,
            logs={
                ".msg": req.msg_text,
                ".dat": req.dat_text,
                ".sta": req.sta_text,
                ".log": req.log_text,
            },
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    report_dir = Path(report.workdir)
    report_json_path = report_dir / "doctor.json"
    report_markdown_path = report_dir / "doctor.md"
    report_json_path.write_text(
        json.dumps(report.to_dict(), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    report_markdown_path.write_text(render_markdown(report), encoding="utf-8")
    vault = _create_vault_entry(
        kind="solver-doctor",
        title=report.job_name,
        files={
            "doctor.json": report_json_path,
            "doctor.md": report_markdown_path,
        },
        summary={
            "status": report.status,
            "primary_category": report.primary_category,
            "finding_count": len(report.findings),
            "real_env_verified": False,
        },
    )
    return {
        "job_name": report.job_name,
        **vault,
        "status": report.status,
        "primary_category": report.primary_category,
        "summary": report.summary,
        "completed": report.completed,
        "finding_count": len(report.findings),
        "report": report.to_dict(),
        "report_markdown": render_markdown(report),
        "real_env_verified": False,
    }


# ── Run endpoints ─────────────────────────────────────────────────

@app.post("/api/run/start")
async def start_run(req: StartRunRequest, background_tasks: BackgroundTasks):
    """Start a pipeline run asynchronously."""
    try:
        spec_dict = yaml.safe_load(req.spec_yaml)
        valid, errors = validate_spec(spec_dict)
        if not valid:
            raise HTTPException(status_code=400, detail={"errors": errors})
    except yaml.YAMLError as e:
        raise HTTPException(status_code=400, detail=f"Invalid YAML: {e}")

    run_id = make_run_id(req.spec_yaml)
    RUNS[run_id] = {
        "run_id": run_id,
        "status": "PENDING",
        "spec": spec_dict,
        "runner_cfg": req.runner_cfg,
        "stages": {},
        "kpis": {},
        "started_at": time.time(),
        "finished_at": None,
        "progress_pct": 0,
    }

    background_tasks.add_task(run_pipeline, run_id, RUNS)
    return {"run_id": run_id, "status": "PENDING"}


@app.get("/api/run/{run_id}")
def get_run(run_id: str):
    """Get current run status and results."""
    if run_id not in RUNS:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    run = RUNS[run_id]
    return {**run, "elapsed": time.time() - run["started_at"]}


@app.get("/api/run/{run_id}/report")
def get_run_report(run_id: str, template: str = "standard"):
    if run_id not in RUNS:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    return _build_run_report(RUNS[run_id], template=template)


@app.get("/api/run/{run_id}/report.md")
def get_run_report_markdown(run_id: str, template: str = "standard"):
    if run_id not in RUNS:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    report = _build_run_report(RUNS[run_id], template=template)
    return Response(
        content=report.get("markdown", "") + "\n",
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="abaqus-report-{run_id}.md"'},
    )


@app.get("/api/run/{run_id}/report.html")
def get_run_report_html(run_id: str, template: str = "standard", download: bool = True):
    if run_id not in RUNS:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    report = _build_run_report(RUNS[run_id], template=template, embed_images=True)
    disposition = "attachment" if download else "inline"
    return Response(
        content=report.get("html", ""),
        media_type="text/html; charset=utf-8",
        headers={"Content-Disposition": f'{disposition}; filename="abaqus-report-{run_id}.html"'},
    )


@app.get("/api/run/{run_id}/report.pdf")
def get_run_report_pdf(run_id: str, template: str = "standard"):
    if run_id not in RUNS:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    report = _build_run_report(RUNS[run_id], template=template, embed_images=True)
    try:
        content = render_html_to_pdf(report.get("html", ""))
    except RuntimeError as e:
        raise HTTPException(status_code=501, detail=str(e))
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="abaqus-report-{run_id}.pdf"'},
    )


@app.get("/api/run/{run_id}/report.zip")
def get_run_report_bundle(
    run_id: str,
    template: str = "standard",
    max_artifact_bytes: int = 25_000_000,
):
    if run_id not in RUNS:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    content = _build_run_report_bundle(
        RUNS[run_id],
        template=template,
        max_artifact_bytes=max_artifact_bytes,
    )
    return Response(
        content=content,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="abaqus-report-{run_id}.zip"'},
    )


@app.get("/api/run/{run_id}/capsule")
def get_run_capsule(run_id: str):
    if run_id not in RUNS:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    capsule = _load_run_capsule(RUNS[run_id])
    if not capsule:
        raise HTTPException(status_code=404, detail=f"Run {run_id} has no capsule")
    return capsule


@app.get("/api/run/{baseline_run_id}/diff/{candidate_run_id}")
def get_run_diff(
    baseline_run_id: str,
    candidate_run_id: str,
    rtol: float = 0.05,
    tolerances_json: str = "",
):
    if baseline_run_id not in RUNS:
        raise HTTPException(status_code=404, detail=f"Run {baseline_run_id} not found")
    if candidate_run_id not in RUNS:
        raise HTTPException(status_code=404, detail=f"Run {candidate_run_id} not found")
    try:
        tolerances = _parse_tolerances_json(tolerances_json)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    diff = diff_runs(
        _run_diff_payload(RUNS[baseline_run_id]),
        _run_diff_payload(RUNS[candidate_run_id]),
        default_rtol=rtol,
        tolerances=tolerances,
    )
    diff["markdown"] = render_run_markdown(diff)
    return diff


@app.get("/api/run/{baseline_run_id}/diff/{candidate_run_id}/diff.md")
def get_run_diff_markdown(
    baseline_run_id: str,
    candidate_run_id: str,
    rtol: float = 0.05,
    tolerances_json: str = "",
):
    diff = get_run_diff(
        baseline_run_id,
        candidate_run_id,
        rtol=rtol,
        tolerances_json=tolerances_json,
    )
    return Response(
        diff["markdown"] + "\n",
        media_type="text/markdown; charset=utf-8",
        headers={
            "Content-Disposition": (
                f'attachment; filename="abaqus-diff-{baseline_run_id}-vs-{candidate_run_id}.md"'
            )
        },
    )


@app.post("/api/diff")
def post_diff(req: DiffRequest):
    try:
        diff = diff_runs(req.baseline, req.candidate, default_rtol=req.rtol, tolerances=req.tolerances)
    except (FileNotFoundError, OSError, json.JSONDecodeError, yaml.YAMLError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    diff["markdown"] = render_run_markdown(diff)
    return diff


@app.post("/api/memory/search")
def post_memory_search(req: MemorySearchRequest):
    try:
        result = search_run_case_memory(
            CaseMemoryQuery(
                roots=tuple(req.roots),
                query=req.query,
                match_mode=req.match_mode,
                similar_to=req.similar_to or None,
                status=req.status,
                model_name=req.model_name,
                geometry_type=req.geometry_type,
                solver=req.solver,
                material_name=req.material_name,
                contract=req.contract,
                contracts_passed=req.contracts_passed,
                diagnosis_id=req.diagnosis_id,
                kpi=req.kpi,
                artifact=req.artifact,
                limit=req.limit,
                include_artifacts=req.include_artifacts,
                sort_by=req.sort_by,
                sort_order=req.sort_order,
                min_score=req.min_score,
            )
        )
    except (OSError, json.JSONDecodeError, yaml.YAMLError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    result["markdown"] = render_memory_markdown(result)
    return result


@app.get("/api/run/{run_id}/artifact/{artifact_name:path}")
def get_run_artifact(run_id: str, artifact_name: str):
    if run_id not in RUNS:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    workdir = _run_workdir(RUNS[run_id])
    if not workdir:
        raise HTTPException(status_code=404, detail=f"Run {run_id} has no artifact directory")
    artifact_path = (workdir / artifact_name).resolve()
    if workdir not in artifact_path.parents and artifact_path != workdir:
        raise HTTPException(status_code=400, detail="Invalid artifact path")
    if not artifact_path.is_file():
        raise HTTPException(status_code=404, detail=f"Artifact not found: {artifact_name}")
    return FileResponse(str(artifact_path))


@app.get("/api/run/{run_id}/stream")
async def stream_run(run_id: str):
    """
    Server-Sent Events stream for real-time pipeline updates.
    Frontend: const es = new EventSource('/api/run/<id>/stream')
    """
    if run_id not in RUNS:
        raise HTTPException(status_code=404)

    async def event_gen() -> AsyncGenerator[str, None]:
        last_status = None
        last_stages_hash = None
        timeout = 300  # max 5 min
        t0 = time.time()

        while time.time() - t0 < timeout:
            run = RUNS.get(run_id, {})
            cur_status = run.get("status")
            stages_hash = hashlib.md5(
                json.dumps(run.get("stages", {}), sort_keys=True, default=str).encode()
            ).hexdigest()

            if cur_status != last_status or stages_hash != last_stages_hash:
                payload = {
                    "run_id": run_id,
                    "status": cur_status,
                    "progress_pct": run.get("progress_pct", 0),
                    "stages": run.get("stages", {}),
                    "kpis": run.get("kpis", {}),
                    "elapsed": time.time() - run.get("started_at", time.time()),
                }
                yield f"data: {json.dumps(payload)}\n\n"
                last_status = cur_status
                last_stages_hash = stages_hash

            if cur_status in ("COMPLETED", "FAILED", "ABORTED"):
                yield "data: {\"event\": \"done\"}\n\n"
                break

            await asyncio.sleep(0.3)

    return StreamingResponse(event_gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})


# ── Benchmark endpoints ───────────────────────────────────────────

@app.get("/api/benchmark")
def get_benchmark():
    """Return all benchmark case definitions."""
    cases = []
    for case_dir in sorted(CASES_DIR.iterdir()):
        if not case_dir.is_dir():
            continue
        spec_path = case_dir / "spec.yaml"
        exp_path  = case_dir / "expected.json"
        if not spec_path.exists():
            continue
        spec = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
        expected = json.loads(exp_path.read_text()) if exp_path.exists() else {}
        cases.append({
            "name": case_dir.name,
            "spec": spec,
            "expected": expected,
            "has_runner_cfg": (case_dir / "runner.json").exists(),
        })
    return {"cases": cases, "total": len(cases)}


@app.post("/api/benchmark/run")
async def run_benchmark(background_tasks: BackgroundTasks, dry_run: bool = True):
    """Trigger benchmark run across all cases."""
    cases = []
    for case_dir in sorted(CASES_DIR.iterdir()):
        if not case_dir.is_dir() or not (case_dir / "spec.yaml").exists():
            continue
        cases.append(case_dir.name)

    run_id = "bench_" + str(uuid.uuid4())[:8]
    RUNS[run_id] = {
        "run_id": run_id,
        "status": "PENDING",
        "type": "benchmark",
        "cases": cases,
        "results": {},
        "started_at": time.time(),
        "progress_pct": 0,
    }
    background_tasks.add_task(run_benchmark_async, run_id, RUNS, dry_run)
    return {"run_id": run_id, "cases": cases, "dry_run": dry_run}


# ── Premium feature endpoints ─────────────────────────────────────

@app.get("/api/premium/features")
def get_premium_features():
    """Return status of all premium features."""
    try:
        from premium.feature_registry import list_premium_capabilities
        from premium.licensing import PREMIUM_FEATURES, feature_gate
        return {
            "features": {
                name: {
                    "display_name": PREMIUM_FEATURES[name],
                    "enabled": feature_gate.is_enabled(name),
                }
                for name in PREMIUM_FEATURES
            },
            "capabilities": list_premium_capabilities(),
        }
    except ImportError:
        return {"features": {}, "capabilities": {}, "error": "Premium module not available"}


@app.post("/api/premium/activate")
def activate_premium(license_key: str = ""):
    """Activate premium features with a license key."""
    try:
        from premium.licensing import feature_gate
        if license_key:
            valid = feature_gate.set_license_key(license_key)
            return {"valid": valid, "features": feature_gate.enabled_features()}
        return {"valid": False, "error": "No license key provided"}
    except ImportError:
        return {"valid": False, "error": "Premium module not available"}


def _build_run_report(run: dict, template: str = "standard", embed_images: bool = False) -> dict:
    capsule = _load_run_capsule(run)
    artifacts = capsule.get("artifacts", {}) if capsule else {}
    image_artifacts = [
        name
        for name in artifacts
        if Path(name).suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".svg"}
    ]
    contracts = run.get("contracts") or (capsule.get("contracts", {}) if capsule else {})
    report = {
        "summary": {
            "run_id": run.get("run_id"),
            "status": run.get("status"),
            "model_name": run.get("spec", {}).get("meta", {}).get("model_name"),
            "abaqus_release": run.get("spec", {}).get("meta", {}).get("abaqus_release"),
            "started_at": run.get("started_at"),
            "finished_at": run.get("finished_at"),
            "capsule_path": run.get("capsule_path"),
            "result_path": run.get("result_path"),
            "workdir": str(_run_workdir(run) or ""),
        },
        "kpis": run.get("kpis", {}),
        "regression": run.get("regression", {}),
        "contracts": contracts,
        "stages": run.get("stages", {}),
        "capsule": capsule,
        "artifacts": artifacts,
        "image_artifacts": image_artifacts,
        "diagnosis": capsule.get("diagnosis", {}) if capsule else {},
        "template": template,
    }
    if embed_images:
        report["image_artifact_sources"] = _load_image_artifact_sources(run, image_artifacts)
    report["markdown"] = render_run_report_markdown(report, template=template)
    report["html"] = render_run_report_html(report, template=template)
    return report


def _load_run_capsule(run: dict) -> dict | None:
    capsule_path = run.get("capsule_path")
    if not capsule_path:
        return None
    path = Path(capsule_path)
    if not path.exists() or not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _run_workdir(run: dict) -> Path | None:
    if run.get("workdir"):
        return Path(run["workdir"]).resolve()
    capsule_path = run.get("capsule_path")
    if capsule_path:
        return Path(capsule_path).resolve().parent
    return None


def _load_image_artifact_sources(run: dict, image_artifacts: list[str]) -> dict[str, str]:
    workdir = _run_workdir(run)
    if not workdir:
        return {}
    sources = {}
    for name in image_artifacts:
        artifact_path = (workdir / name).resolve()
        if workdir not in artifact_path.parents and artifact_path != workdir:
            continue
        if not artifact_path.is_file() or artifact_path.stat().st_size > 5 * 1024 * 1024:
            continue
        media_type = mimetypes.guess_type(artifact_path.name)[0] or "application/octet-stream"
        data = base64.b64encode(artifact_path.read_bytes()).decode("ascii")
        sources[name] = f"data:{media_type};base64,{data}"
    return sources


def _build_run_report_bundle(
    run: dict,
    template: str = "standard",
    max_artifact_bytes: int = 25_000_000,
) -> bytes:
    report = _build_run_report(run, template=template, embed_images=True)
    workdir = _run_workdir(run)
    manifest = {
        "run_id": run.get("run_id"),
        "template": template,
        "included_artifacts": [],
        "skipped_artifacts": [],
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr("report.md", report.get("markdown", "") + "\n")
        bundle.writestr("report.html", report.get("html", ""))
        if report.get("capsule"):
            bundle.writestr("capsule.json", json.dumps(report["capsule"], indent=2, sort_keys=True))
        if workdir:
            for name in sorted(report.get("artifacts", {})):
                artifact_path = (workdir / name).resolve()
                if workdir not in artifact_path.parents and artifact_path != workdir:
                    manifest["skipped_artifacts"].append({"name": name, "reason": "invalid_path"})
                    continue
                if not artifact_path.is_file():
                    manifest["skipped_artifacts"].append({"name": name, "reason": "missing"})
                    continue
                size = artifact_path.stat().st_size
                if size > max_artifact_bytes:
                    manifest["skipped_artifacts"].append(
                        {"name": name, "reason": "too_large", "bytes": size}
                    )
                    continue
                bundle.write(artifact_path, _artifact_zip_name(name))
                manifest["included_artifacts"].append({"name": name, "bytes": size})
        bundle.writestr("artifact_manifest.json", json.dumps(manifest, indent=2, sort_keys=True))
    return buffer.getvalue()


def _artifact_zip_name(name: str) -> str:
    return str(Path("artifacts") / Path(name).name)


def _run_diff_payload(run: dict) -> dict:
    return {
        "run_id": run.get("run_id"),
        "status": run.get("status"),
        "spec": run.get("spec", {}),
        "kpis": run.get("kpis", {}),
        "contracts": run.get("contracts", {}),
    }


def _parse_tolerances_json(raw: str) -> dict:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid tolerances_json: {e}") from e
    if not isinstance(data, dict):
        raise ValueError("tolerances_json must decode to an object")
    return data


# ── Main ──────────────────────────────────────────────────────────

def main():
    """Entry point for `abaqus-agent` CLI command."""
    import uvicorn
    print("\n  Abaqus Agent API")
    print("  ─────────────────────────────")
    print("  Frontend : http://localhost:8000")
    print("  API docs : http://localhost:8000/docs")
    print(f"  Abaqus   : {'✓ found' if check_abaqus() else '✗ not found (simulation mode)'}")
    print(f"  Cases    : {list_cases()}")
    print()
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)


if __name__ == "__main__":
    main()
