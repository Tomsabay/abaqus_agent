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
import hashlib
import json

# ── Project imports ──────────────────────────────────────────────
import sys
import time
import uuid
from pathlib import Path
from typing import AsyncGenerator

import yaml
from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).parent))

from case_memory import CaseMemoryQuery, render_memory_markdown, search_case_memory
from core.helpers import CASES_DIR, check_abaqus, list_cases, make_run_id
from core.pipeline import (
    run_benchmark_async,
    run_pipeline,
)
from core.spec_generator import generate_spec_async
from reporting import render_run_report_markdown
from simdiff import diff_runs, render_run_markdown
from tools.schema_validator import validate_spec

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

class MemorySearchRequest(BaseModel):
    roots: list[str]
    query: str = ""
    similar_to: str = ""
    status: str = ""
    model_name: str = ""
    diagnosis_id: str = ""
    kpi: str = ""
    limit: int = 10


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
def get_run_diff(baseline_run_id: str, candidate_run_id: str, rtol: float = 0.05):
    """Diff two in-memory runs by run id."""
    if baseline_run_id not in RUNS:
        raise HTTPException(status_code=404, detail=f"Run {baseline_run_id} not found")
    if candidate_run_id not in RUNS:
        raise HTTPException(status_code=404, detail=f"Run {candidate_run_id} not found")
    diff = diff_runs(_run_diff_payload(RUNS[baseline_run_id]), _run_diff_payload(RUNS[candidate_run_id]), default_rtol=rtol)
    diff["markdown"] = render_run_markdown(diff)
    return diff


@app.post("/api/diff")
def post_diff(req: DiffRequest):
    """Diff two local run/capsule/result/KPI paths."""
    try:
        diff = diff_runs(req.baseline, req.candidate, default_rtol=req.rtol)
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
            diagnosis_id=req.diagnosis_id,
            kpi=req.kpi,
            limit=req.limit,
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

def _build_run_report(run: dict, template: str = "standard") -> dict:
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
    report["template"] = template
    report["markdown"] = _render_run_report_markdown(report, template=template)
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


def _render_run_report_markdown(report: dict, template: str = "standard") -> str:
    return render_run_report_markdown(report, template=template)


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
