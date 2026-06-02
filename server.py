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
import sys
import time
import uuid
import zipfile
from pathlib import Path
from typing import AsyncGenerator

import yaml
from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

try:
    from pydantic import BaseModel, ConfigDict
except ImportError:  # pragma: no cover - pydantic v1 compatibility
    from pydantic import BaseModel
    ConfigDict = None

sys.path.insert(0, str(Path(__file__).parent))

# ── Project imports ──────────────────────────────────────────────
from case_memory import CaseMemoryQuery, render_memory_markdown, search_case_memory
from core.helpers import CASES_DIR, check_abaqus, list_cases, make_run_id
from core.pipeline import (
    run_benchmark_async,
    run_pipeline,
)
from core.spec_generator import generate_spec_async
from reporting import (
    build_offline_report_bundle,
    build_offline_report_pdf,
    build_offline_run_report,
    render_html_to_pdf,
    render_run_report_html,
    render_run_report_markdown,
)
from simdiff import diff_runs, render_run_markdown
from tools.schema_validator import validate_spec
from validation import render_preflight_markdown, run_environment_preflight

FRONTEND_DIR = Path(__file__).parent / "frontend"

# ── In-memory run store ───────────────────────────────────────────
# {run_id: {status, stages, kpis, spec, ...}}
RUNS: dict[str, dict] = {}

# ── FastAPI app ───────────────────────────────────────────────────
app = FastAPI(
    title="Abaqus Agent API",
    version="0.1.0",
    description="Local simulation QA and regression framework for Abaqus FEA",
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
    runner_cfg: dict = {}

class DiffRequest(BaseModel):
    baseline: str
    candidate: str
    rtol: float = 0.05
    tolerances: dict = {}

class MemorySearchRequest(BaseModel):
    if ConfigDict:
        model_config = ConfigDict(protected_namespaces=())

    roots: list[str]
    query: str = ""
    similar_to: str = ""
    status: str = ""
    model_name: str = ""
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


class OfflineReportRequest(BaseModel):
    source: str
    template: str = "standard"
    max_artifact_bytes: int = 25_000_000


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


# ── Validation endpoints ──────────────────────────────────────────

@app.post("/api/validate/env")
def post_environment_preflight(req: EnvironmentPreflightRequest):
    """Check local OS, Python, and Abaqus command readiness for real validation."""
    try:
        result = run_environment_preflight(
            abaqus_cmd=req.abaqus_cmd or None,
            timeout_seconds=req.timeout_seconds,
            check_release=req.check_release,
            expected_release=req.expected_release,
        )
    except (OSError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    result["markdown"] = render_preflight_markdown(result)
    return result


# ── Offline report endpoints ──────────────────────────────────────

@app.post("/api/report/export")
def post_offline_report_export(req: OfflineReportRequest):
    """Build a report from a run directory, capsule.json, or result.json source path."""
    try:
        report = build_offline_run_report(req.source, template=req.template, embed_images=True)
    except (FileNotFoundError, OSError, json.JSONDecodeError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    report["offline_source"] = req.source
    return report


@app.post("/api/report/export.zip")
def post_offline_report_export_bundle(req: OfflineReportRequest):
    """Download an offline report bundle from a run directory, capsule.json, or result.json."""
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
    filename = f"abaqus-report-{run_id}.zip"
    return Response(
        content=content,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.post("/api/report/export.pdf")
def post_offline_report_export_pdf(req: OfflineReportRequest):
    """Download an offline report as PDF using the optional Playwright renderer."""
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
        "contracts": {},
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
    """Return a UI-friendly report assembled from a run, result.json, and capsule.json."""
    if run_id not in RUNS:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    return _build_run_report(RUNS[run_id], template=template)


@app.get("/api/run/{run_id}/report.md")
def get_run_report_markdown(run_id: str, template: str = "standard"):
    """Download a run report as Markdown."""
    if run_id not in RUNS:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    report = _build_run_report(RUNS[run_id], template=template)
    filename = f"abaqus-report-{run_id}.md"
    return Response(
        content=report.get("markdown", "") + "\n",
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/run/{run_id}/report.html")
def get_run_report_html(run_id: str, template: str = "standard", download: bool = True):
    """Download or preview a run report as standalone HTML."""
    if run_id not in RUNS:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    report = _build_run_report(RUNS[run_id], template=template, embed_images=True)
    filename = f"abaqus-report-{run_id}.html"
    disposition = "attachment" if download else "inline"
    return Response(
        content=report.get("html", ""),
        media_type="text/html; charset=utf-8",
        headers={"Content-Disposition": f'{disposition}; filename="{filename}"'},
    )


@app.get("/api/run/{run_id}/report.pdf")
def get_run_report_pdf(run_id: str, template: str = "standard"):
    """Download a run report as PDF using the optional Playwright renderer."""
    if run_id not in RUNS:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    report = _build_run_report(RUNS[run_id], template=template, embed_images=True)
    try:
        content = render_html_to_pdf(report.get("html", ""))
    except RuntimeError as e:
        raise HTTPException(status_code=501, detail=str(e))
    filename = f"abaqus-report-{run_id}.pdf"
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/run/{run_id}/report.zip")
def get_run_report_bundle(run_id: str, template: str = "standard", max_artifact_bytes: int = 25_000_000):
    """Download a report bundle with Markdown, HTML, capsule, and small artifacts."""
    if run_id not in RUNS:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    content = _build_run_report_bundle(RUNS[run_id], template=template, max_artifact_bytes=max_artifact_bytes)
    filename = f"abaqus-report-{run_id}.zip"
    return Response(
        content=content,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/run/{run_id}/capsule")
def get_run_capsule(run_id: str):
    """Return capsule.json for a completed real Abaqus run."""
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
    """Diff two in-memory runs by run id."""
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
    """Download a Markdown diff report for two in-memory runs by run id."""
    diff = get_run_diff(
        baseline_run_id,
        candidate_run_id,
        rtol=rtol,
        tolerances_json=tolerances_json,
    )
    filename = f"abaqus-diff-{baseline_run_id}-vs-{candidate_run_id}.md"
    return Response(
        diff["markdown"] + "\n",
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.post("/api/diff")
def post_diff(req: DiffRequest):
    """Diff two local run/capsule/result/KPI paths."""
    try:
        diff = diff_runs(req.baseline, req.candidate, default_rtol=req.rtol, tolerances=req.tolerances)
    except (FileNotFoundError, OSError, json.JSONDecodeError, yaml.YAMLError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    diff["markdown"] = render_run_markdown(diff)
    return diff


@app.post("/api/memory/search")
def post_memory_search(req: MemorySearchRequest):
    """Search local run/capsule directories as deterministic case memory."""
    try:
        result = search_case_memory(CaseMemoryQuery(
            roots=tuple(req.roots),
            query=req.query,
            similar_to=req.similar_to or None,
            status=req.status,
            model_name=req.model_name,
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
        ))
    except (OSError, json.JSONDecodeError, yaml.YAMLError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    result["markdown"] = render_memory_markdown(result)
    return result


@app.get("/api/run/{run_id}/artifact/{artifact_name:path}")
def get_run_artifact(run_id: str, artifact_name: str):
    """Download a run artifact from the capsule workdir."""
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
        last_payload_hash = None
        timeout = 300  # max 5 min
        t0 = time.time()

        while time.time() - t0 < timeout:
            run = RUNS.get(run_id, {})
            cur_status = run.get("status")
            payload_hash = hashlib.md5(json.dumps({
                "status": cur_status,
                "progress_pct": run.get("progress_pct", 0),
                "stages": run.get("stages", {}),
                "kpis": run.get("kpis", {}),
                "regression": run.get("regression", {}),
                "contracts": run.get("contracts", {}),
                "capsule_path": run.get("capsule_path"),
                "result_path": run.get("result_path"),
            }, sort_keys=True, default=str).encode()).hexdigest()

            if payload_hash != last_payload_hash:
                payload = {
                    "run_id": run_id,
                    "status": cur_status,
                    "progress_pct": run.get("progress_pct", 0),
                    "stages": run.get("stages", {}),
                    "kpis": run.get("kpis", {}),
                    "regression": run.get("regression", {}),
                    "contracts": run.get("contracts", {}),
                    "capsule_path": run.get("capsule_path"),
                    "result_path": run.get("result_path"),
                    "elapsed": time.time() - run.get("started_at", time.time()),
                }
                yield f"data: {json.dumps(payload)}\n\n"
                last_payload_hash = payload_hash

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
        "contracts": {},
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


# ── Report helpers ────────────────────────────────────────────────

def _build_run_report(run: dict, template: str = "standard", embed_images: bool = False) -> dict:
    capsule = _load_run_capsule(run)
    artifacts = capsule.get("artifacts", {}) if capsule else {}
    image_artifacts = [
        name for name in artifacts
        if Path(name).suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".svg"}
    ]
    diagnosis = capsule.get("diagnosis", {}) if capsule else {}
    contracts = run.get("contracts") or (capsule.get("contracts", {}) if capsule else {})
    summary = {
        "run_id": run.get("run_id"),
        "status": run.get("status"),
        "model_name": run.get("spec", {}).get("meta", {}).get("model_name"),
        "abaqus_release": run.get("spec", {}).get("meta", {}).get("abaqus_release"),
        "started_at": run.get("started_at"),
        "finished_at": run.get("finished_at"),
        "capsule_path": run.get("capsule_path"),
        "result_path": run.get("result_path"),
        "workdir": str(_run_workdir(run) or ""),
    }
    report = {
        "summary": summary,
        "kpis": run.get("kpis", {}),
        "regression": run.get("regression", {}),
        "contracts": contracts,
        "stages": run.get("stages", {}),
        "capsule": capsule,
        "artifacts": artifacts,
        "image_artifacts": image_artifacts,
        "diagnosis": diagnosis,
    }
    if embed_images:
        report["image_artifact_sources"] = _load_image_artifact_sources(run, image_artifacts)
    report["template"] = template
    report["markdown"] = _render_run_report_markdown(report, template=template)
    report["html"] = _render_run_report_html(report, template=template)
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


def _build_run_report_bundle(run: dict, template: str = "standard", max_artifact_bytes: int = 25_000_000) -> bytes:
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
                    manifest["skipped_artifacts"].append({"name": name, "reason": "too_large", "bytes": size})
                    continue
                bundle.write(artifact_path, _artifact_zip_name(name))
                manifest["included_artifacts"].append({"name": name, "bytes": size})
        bundle.writestr("artifact_manifest.json", json.dumps(manifest, indent=2, sort_keys=True))
    return buffer.getvalue()


def _artifact_zip_name(name: str) -> str:
    parts = [part for part in Path(name).parts if part not in {"", ".", ".."}]
    return "artifacts/" + "/".join(parts or ["artifact"])


def _run_diff_payload(run: dict) -> dict:
    capsule = _load_run_capsule(run) or {}
    return {
        "source": run.get("run_id"),
        "run_id": run.get("run_id"),
        "status": run.get("status"),
        "kpis": run.get("kpis", {}),
        "contracts": run.get("contracts") or capsule.get("contracts", {}),
        "regression": run.get("regression", {}),
        "spec": run.get("spec", {}),
        "inputs": capsule.get("inputs", {}),
        "provenance": capsule.get("provenance", {}),
        "artifacts": capsule.get("artifacts", {}),
    }


def _parse_tolerances_json(raw: str) -> dict:
    if not raw:
        return {}
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("tolerances_json must decode to an object")
    return data


def _render_run_report_markdown(report: dict, template: str = "standard") -> str:
    return render_run_report_markdown(report, template=template)


def _render_run_report_html(report: dict, template: str = "standard") -> str:
    return render_run_report_html(report, template=template)


# ── Main ──────────────────────────────────────────────────────────

def main():
    """Entry point for the `abaqus-agent serve` command."""
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
