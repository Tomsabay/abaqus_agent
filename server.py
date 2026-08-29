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
import os

# ── Project imports ──────────────────────────────────────────────
import sys
import tempfile
import time
import uuid
import zipfile
from pathlib import Path
from typing import Any, AsyncGenerator

import yaml
from fastapi import BackgroundTasks, FastAPI, HTTPException
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
from core import config
from core.helpers import CASES_DIR, check_abaqus, list_cases, make_run_id
from core.pipeline import (
    run_benchmark_async,
    run_pipeline,
)
from core.spec_generator import generate_spec_async
from doctor.cae_errors import diagnose_cae_traceback, list_cae_error_patterns
from doctor.solver_doctor import diagnose_log_texts, list_doctor_patterns, render_markdown
from evidence.artifact_registry import ArtifactNotFound, EvidenceArtifactRegistry
from evidence.case_memory import search_case_memory
from evidence.case_memory_diff import collect_case_memory_diff
from evidence.demo_gallery import collect_demo_gallery
from evidence.examples import get_example, list_examples
from evidence.offline import collect_evidence_from_values, validate_run_id
from evidence.vault import (
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
from scripts.run_local_cli_smoke import collect_local_cli_smoke
from scripts.run_local_demo_pack import collect_demo_pack_vault_files, create_local_demo_pack
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

EVIDENCE = EvidenceArtifactRegistry("/api/evidence")
# The two dicts the registry keeps, under the names they have always had here.
# They are the same objects, not copies, so clearing one clears the registry --
# which is what the test fixtures do between cases.
EVIDENCE_ARTIFACTS = EVIDENCE.artifacts
DEMO_GALLERY_ARTIFACTS = EVIDENCE.demo_galleries

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

# This server drives a real solver and reads/writes the local filesystem, and
# it has no authentication. It also serves its own frontend, so the workbench
# is same-origin and needs no CORS at all. A wildcard here would let any page
# the user happens to visit script their local install through the browser.
# Cross-origin access is therefore opt-in, explicit, and never wildcarded.
_cors_origins = [
    o.strip() for o in os.environ.get("ABAQUS_AGENT_CORS_ORIGINS", "").split(",") if o.strip()
]
if _cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# Serve frontend
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

# Cursor-style workbench (chat → spec diff → accept → run)
# The 21 /api/copilot/* routes and the session store they own.
# COPILOT_SESSIONS is re-exported because tests and the CAE plug-in path reach
# for it here; it is the same dict object, so mutating it through either name
# works. Nothing else is re-exported on purpose -- rebinding a re-exported
# Path (COPILOT_SESSION_FILE) here would leave the routes reading the old one.
from copilot.routes import COPILOT_SESSIONS  # noqa: E402,F401
from copilot.routes import router as copilot_router  # noqa: E402
from workbench.routes import configure as configure_workbench  # noqa: E402
from workbench.routes import router as workbench_router  # noqa: E402

configure_workbench(RUNS)
app.include_router(workbench_router)
app.include_router(copilot_router)


# ── Request / Response models ─────────────────────────────────────

class GenerateSpecRequest(BaseModel):
    text: str
    # Empty = probe the installed solver. A literal default put a release this
    # machine may not have into every generated spec.
    abaqus_release: str = ""
    llm_backend: str = "template"
    anthropic_key: str = ""   # Optional: override ANTHROPIC_API_KEY env var
    openai_key: str = ""      # Optional: override OPENAI_API_KEY env var
    deepseek_key: str = ""    # Optional: override DEEPSEEK_API_KEY env var

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



# ── Routes ───────────────────────────────────────────────────────

@app.get("/")
def root():
    index = FRONTEND_DIR / "index.html"
    if index.exists():
        return FileResponse(str(index))
    return {"status": "ok", "message": "Abaqus Agent API running"}


@app.get("/api/i18n/messages")
def i18n_messages(lang: str = ""):
    """The backend's own message catalogue, for the browser to render with.

    Refusals travel as a key plus parameters rather than as finished prose,
    because a refusal is written into result.json and read back later —
    possibly by someone reading in the other language. That means whoever
    displays it needs the catalogue, and the browser is the one displaying it.

    Serving it beats duplicating it in the frontend: one wording, one place to
    fix it, and no way for the two to end up describing the same refusal
    differently.
    """
    from core import messages
    resolved = messages.resolve_lang(lang or None)
    return {"lang": resolved, "messages": messages.catalogue_for(resolved)}


@app.get("/health")
def health():
    # The release is what the installed solver reports, never a spec field
    # (those drift). Short timeout: the first call pays for the probe, the
    # rest read the process cache, and an absent solver just yields None.
    from core.backends import ENV_BACKEND, backend_label, select_backend
    from tools.abaqus_cmd import detect_abaqus_release

    try:
        release = detect_abaqus_release(timeout=15.0)
    except Exception:
        release = None
    # What auto-detection would pick right now, so the UI can say which solver
    # is in charge before the user starts a run rather than after it degrades.
    decision = select_backend({})
    return {
        "status": "ok",
        "abaqus_available": check_abaqus(),
        "abaqus_release": release,
        "solver_backend": decision.backend,
        "solver_label": backend_label(decision.backend, decision.version),
        "solver_reason": decision.reason,
        "backend_override": os.environ.get(ENV_BACKEND) or None,
        "cases": list_cases(),
        "version": "0.1.0",
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
        from tools.abaqus_cmd import detect_abaqus_release
        release = req.abaqus_release or detect_abaqus_release() or "unknown"
        spec_dict, missing = await generate_spec_async(
            req.text, release, req.llm_backend,
            anthropic_key=req.anthropic_key,
            openai_key=req.openai_key,
            deepseek_key=req.deepseek_key,
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
        artifacts = EVIDENCE.register_evidence(
            run_id=run_id,
            evidence=evidence,
            evidence_path=evidence_path,
            report_path=report_path,
            html_path=html_path,
            capsule_manifest_path=Path(evidence["capsule"]["manifest_path"]),
        )
        artifact_files = EVIDENCE.evidence_files(artifacts["artifact_id"])
        vault = EVIDENCE.create_vault_entry(
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
    artifacts = EVIDENCE.register_demo_gallery(index=index, out_dir=out_dir)
    vault = EVIDENCE.create_vault_entry(
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
    try:
        path = EVIDENCE.demo_gallery_path(artifact_id, filename)
    except ArtifactNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return FileResponse(path, media_type=media_types[filename], filename=filename)


@app.post("/api/evidence/demo-pack")
def create_local_demo_pack_endpoint():
    """Generate a downloadable local product demo pack."""
    out_dir = Path(tempfile.mkdtemp(prefix="abaqus-agent-local-demo-pack."))
    index = create_local_demo_pack(out_dir)
    vault = EVIDENCE.create_vault_entry(
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
    try:
        path = EVIDENCE.evidence_path(artifact_id, filename)
    except ArtifactNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return FileResponse(path, media_type=media_types[filename], filename=filename)


@app.get("/api/evidence/artifacts")
def list_offline_evidence_artifacts(limit: int = 20):
    """List recent offline evidence artifacts registered in this server process."""
    return EVIDENCE.list_evidence_records(limit)


@app.get("/api/evidence/vault")
def list_evidence_vault(limit: int = 50, query: str = "", kind: str = "", status: str = ""):
    """List persisted local evidence vault entries."""
    data = list_vault_entries(limit=limit, query=query, kind=kind, status=status)
    for item in data["items"]:
        EVIDENCE.attach_vault_urls(item)
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
    EVIDENCE.attach_vault_urls(record)
    return record


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
        vault = EVIDENCE.create_vault_entry(
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
        vault = EVIDENCE.create_vault_entry(
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


@app.get("/api/doctor/cae-patterns")
def get_doctor_cae_patterns():
    """CAE-side (plugin execution) failure pattern catalog with plain-language guidance."""
    patterns = list_cae_error_patterns()
    return {"total": len(patterns), "patterns": patterns}


class CaeDiagnoseRequest(BaseModel):
    traceback: str = Field(..., max_length=20000)


@app.post("/api/doctor/cae-diagnose")
def post_doctor_cae_diagnose(req: CaeDiagnoseRequest):
    """Diagnose a pasted CAE/Abaqus-Python traceback in plain language."""
    text = req.traceback.strip()
    if not text:
        raise HTTPException(status_code=400, detail="请把 CAE 报错的 traceback 贴进来")
    return diagnose_cae_traceback(text)


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
    vault = EVIDENCE.create_vault_entry(
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


@app.get("/api/run/{run_id}/doctor")
def get_run_doctor(run_id: str):
    """Plain-language diagnosis of a run, for the panel a failed run shows.

    Read-only on purpose, and deliberately NOT `POST /api/doctor/diagnose`:
    that one writes doctor.json/doctor.md and creates an evidence-vault entry
    as a side effect, which would litter the vault with one entry per page view.

    The contract the UI depends on: `error` is echoed verbatim whether or not
    anything matched, and `findings` is empty when no pattern fired. A
    diagnosis is only ever something the pattern engine produced — never
    something invented to fill the panel.
    """
    if run_id not in RUNS:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    run = RUNS[run_id]

    payload = {
        "run_id": run_id,
        "status": run.get("status"),
        "matched": False,
        "findings": [],
        "summary": "",
        "error": run.get("error") or None,
        "kpi_notice": run.get("kpi_notice") or "",
        "limitations": run.get("limitations") or [],
        "source": "none",
    }

    workdir = _run_workdir(run)
    raw_job_name = (run.get("spec", {}).get("meta", {}) or {}).get("model_name") or ""
    if not workdir or not raw_job_name:
        return payload

    # diagnose_job_logs builds paths as workdir/<job_name><suffix> and, unlike
    # diagnose_log_texts, does NOT validate the name itself. model_name comes
    # from a user-supplied spec and the schema puts no pattern on it, so
    # without this the endpoint is an arbitrary-file-read scoped to
    # .msg/.sta/.dat/.log.
    from doctor.solver_doctor import diagnose_job_logs, validate_job_name
    try:
        job_name = validate_job_name(raw_job_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"invalid model_name: {exc}")

    try:
        report = diagnose_job_logs(workdir, job_name)
    except Exception as exc:  # a missing/unreadable log is not a server error
        payload["source"] = "unavailable"
        payload["summary"] = f"没有可读的求解日志，无法诊断：{exc}"
        return payload

    payload.update({
        "matched": bool(report.findings),
        "findings": [f.to_dict() for f in report.findings],
        "summary": report.summary,
        "doctor_status": report.status,
        "primary_category": report.primary_category,
        "evidence_files": [Path(p).name for p in report.evidence_files],
        "source": "solver_doctor",
    })
    return payload


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


# ── Feature module endpoints ──────────────────────────────────────

@app.get("/api/features")
def get_features():
    """Return the optional feature modules and everything they registered."""
    from features.feature_registry import list_capabilities, list_feature_modules
    return {
        "features": list_feature_modules(),
        "capabilities": list_capabilities(),
    }


def _run_is_unsolved(run: dict) -> bool:
    """No solver ran, so the report must not look like one that did.

    Read from the backend decision rather than from a flag on the run: the run
    used to carry `demo_mode`, set by a walkthrough that no longer exists. A
    job that ran and aborted is NOT this -- that one has a solver behind it and
    a .msg file to read.
    """
    backend = run.get("backend") or {}
    return "supported" in backend and not backend["supported"]


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
            "solver_backend": (run.get("backend") or {}).get("backend") or "abaqus",
            "solver_label": (run.get("backend") or {}).get("label"),
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
        # The caveats travel with the report or they do not exist. A report is
        # the artifact that outlives the session and gets mailed to someone who
        # never saw the screen it was rendered from.
        #
        # reporting/templates.py has always known how to render all four --
        # the no-solve banner, the limitations table, the missing-KPI rows --
        # and never received any of them, so those branches were dead on the
        # whole /api/run/{id}/report.* family. The unsolved case was the
        # damaging one: a run where nothing was solved exported a report that
        # read exactly like a real one.
        "unsolved": _run_is_unsolved(run),
        "kpi_notice": run.get("kpi_notice") or "",
        "limitations": run.get("limitations") or [],
        "kpis_missing": run.get("kpis_missing") or [],
        "kpi_provenance": run.get("kpi_provenance") or {},
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

    host = config.host()
    port = config.port()
    dev = config.is_dev()
    print("\n  Abaqus Agent API")
    print("  ─────────────────────────────")
    print(f"  Frontend : http://{host}:{port}")
    print(f"  API docs : http://{host}:{port}/docs")
    print(f"  Mode     : {'dev (reload)' if dev else 'packaged'}")
    print(f"  Abaqus   : {'✓ found' if check_abaqus() else '✗ not found (simulation mode)'}")
    print(f"  Cases    : {list_cases()}")
    print()
    # reload needs the import-string form and a live-reloader; packaged mode
    # runs the app object directly so it works inside a frozen executable.
    if dev:
        uvicorn.run("server:app", host=host, port=port, reload=True)
    else:
        uvicorn.run(app, host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
