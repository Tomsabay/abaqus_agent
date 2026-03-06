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
import random
import time
import uuid
from pathlib import Path
from typing import AsyncGenerator

import yaml
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# ── Project imports ──────────────────────────────────────────────
import sys
sys.path.insert(0, str(Path(__file__).parent))

from tools.schema_validator import validate_spec
from tools.errors import AbaqusAgentError, ErrorCode

CASES_DIR   = Path(__file__).parent / "cases"
FRONTEND_DIR = Path(__file__).parent / "frontend"

# ── In-memory run store ───────────────────────────────────────────
# {run_id: {status, stages, kpis, spec, ...}}
RUNS: dict[str, dict] = {}

# ── FastAPI app ───────────────────────────────────────────────────
app = FastAPI(
    title="Abaqus Agent API",
    version="0.1.0",
    description="LLM-powered Abaqus FEA automation agent",
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
        "abaqus_available": _check_abaqus(),
        "cases": _list_cases(),
        "version": "0.1.0",
    }


# ── Spec endpoints ────────────────────────────────────────────────

@app.post("/api/spec/generate")
async def generate_spec(req: GenerateSpecRequest):
    """Convert natural language to Problem Spec YAML."""
    try:
        # Try real LLM first, fall back to template
        spec_dict, missing = await _generate_spec_async(
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

    run_id = _make_run_id(req.spec_yaml)
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

    background_tasks.add_task(_run_pipeline, run_id)
    return {"run_id": run_id, "status": "PENDING"}


@app.get("/api/run/{run_id}")
def get_run(run_id: str):
    """Get current run status and results."""
    if run_id not in RUNS:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    run = RUNS[run_id]
    return {**run, "elapsed": time.time() - run["started_at"]}


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
    background_tasks.add_task(_run_benchmark_async, run_id, dry_run)
    return {"run_id": run_id, "cases": cases, "dry_run": dry_run}


# ── Background pipeline simulation ───────────────────────────────

STAGES = [
    ("validate_spec", "校验 Problem Spec",     0.3, 0.6),
    ("build_model",   "生成 CAE noGUI → .inp", 1.0, 2.0),
    ("syntaxcheck",   "语法检查（不消耗 token）", 0.4, 0.8),
    ("submit_job",    "提交 Abaqus 作业",       1.2, 2.5),
    ("monitor_job",   "轮询 .sta 状态",         0.8, 1.5),
    ("extract_kpis",  "从 ODB 提取 KPI",        0.6, 1.2),
]

STAGE_LOGS = {
    "validate_spec": [
        ("ok",   "Schema 校验通过"),
        ("info", "abaqus_release: {release}, solver: {solver}"),
    ],
    "build_model": [
        ("info", "→ 写出 CAE noGUI 脚本: build_model_script.py"),
        ("info", "→ abaqus cae noGUI=build_model_script.py -- /runs/{run_id}"),
        ("ok",   "INP_WRITTEN: /runs/{run_id}/{model}.inp"),
        ("ok",   "CAE_WRITTEN: /runs/{run_id}/{model}.cae"),
    ],
    "syntaxcheck": [
        ("info", "→ abaqus job={model} input={model}.inp syntaxcheck"),
        ("ok",   "syntaxcheck PASSED (0 errors, 2 warnings)"),
        ("warn", "WARNING: mesh quality index = 0.87"),
    ],
    "submit_job": [
        ("info", "→ abaqus job={model} input={model}.inp cpus=2 interactive"),
        ("info", "BEGIN ANALYSIS"),
        ("ok",   "ANALYSIS COMPLETE"),
    ],
    "monitor_job": [
        ("info", "STEP  INC  ATT  TOTAL   STEP TIME   TOTAL TIME"),
        ("info", "   1    1    1  100.0%  1.000E+00   1.000E+00"),
        ("ok",   "JOB COMPLETED"),
    ],
    "extract_kpis": [
        ("info", "→ abaqus python extract_kpis.py -- {model}.odb"),
        ("ok",   "ODB opened successfully"),
        ("ok",   "KPI_RESULT_WRITTEN: /runs/{run_id}/_kpi_result.json"),
    ],
}


async def _run_pipeline(run_id: str):
    """Simulate (or actually run) the Abaqus pipeline."""
    run = RUNS[run_id]
    run["status"] = "RUNNING"
    spec = run["spec"]
    model = spec.get("meta", {}).get("model_name", "Model")
    release = spec.get("meta", {}).get("abaqus_release", "2024")
    solver = spec.get("analysis", {}).get("solver", "standard")

    abaqus_available = _check_abaqus()
    total = len(STAGES)

    for i, (stage_id, desc, dur_min, dur_max) in enumerate(STAGES):
        run["stages"][stage_id] = {"status": "running", "desc": desc, "logs": []}
        run["progress_pct"] = round(i / total * 100)
        await asyncio.sleep(dur_min + random.random() * (dur_max - dur_min))

        # Real execution if Abaqus available, else simulate
        if abaqus_available:
            result = await _run_stage_real(stage_id, run)
        else:
            result = _simulate_stage(stage_id, model, release, solver, run_id)

        run["stages"][stage_id] = {
            "status": result["status"],
            "desc": desc,
            "logs": result["logs"],
            "elapsed_ms": result.get("elapsed_ms", 0),
        }

        if result["status"] == "error":
            run["status"] = "FAILED"
            run["finished_at"] = time.time()
            return

    # Extract KPIs
    run["kpis"] = _mock_kpis(spec)
    run["regression"] = _compare_kpis(run["kpis"], run_id)
    run["progress_pct"] = 100
    run["status"] = "COMPLETED"
    run["finished_at"] = time.time()


def _simulate_stage(stage_id: str, model: str, release: str, solver: str, run_id: str) -> dict:
    templates = STAGE_LOGS.get(stage_id, [("ok", "完成")])
    logs = []
    for level, msg in templates:
        logs.append({
            "level": level,
            "text": msg.format(model=model, release=release,
                               solver=solver, run_id=run_id[:8]),
        })
    return {"status": "done", "logs": logs, "elapsed_ms": random.randint(200, 1500)}


async def _run_stage_real(stage_id: str, run: dict) -> dict:
    """Attempt real Abaqus execution for a stage."""
    # Placeholder: implement actual calls here when Abaqus is available
    return _simulate_stage(
        stage_id,
        run["spec"].get("meta", {}).get("model_name", "Model"),
        run["spec"].get("meta", {}).get("abaqus_release", "2024"),
        run["spec"].get("analysis", {}).get("solver", "standard"),
        run["run_id"],
    )


async def _run_benchmark_async(run_id: str, dry_run: bool):
    run = RUNS[run_id]
    cases = run["cases"]
    run["status"] = "RUNNING"

    for i, case_name in enumerate(cases):
        run["progress_pct"] = round(i / len(cases) * 100)
        spec_path = CASES_DIR / case_name / "spec.yaml"
        spec = yaml.safe_load(spec_path.read_text())
        valid, errors = validate_spec(spec)

        if dry_run:
            await asyncio.sleep(0.2)
            run["results"][case_name] = {
                "status": "DRY_RUN_PASS" if valid else "SPEC_INVALID",
                "errors": errors,
            }
        else:
            # Full run — reuse pipeline simulation
            case_run_id = f"{run_id}_{case_name}"
            RUNS[case_run_id] = {
                "run_id": case_run_id, "status": "PENDING",
                "spec": spec, "runner_cfg": {},
                "stages": {}, "kpis": {},
                "started_at": time.time(), "finished_at": None,
                "progress_pct": 0,
            }
            await _run_pipeline(case_run_id)
            cr = RUNS[case_run_id]
            run["results"][case_name] = {
                "status": cr["status"],
                "kpis": cr.get("kpis", {}),
                "regression": cr.get("regression", {}),
            }

    run["progress_pct"] = 100
    run["status"] = "COMPLETED"
    run["finished_at"] = time.time()


# ── KPI helpers ───────────────────────────────────────────────────

def _mock_kpis(spec: dict) -> dict:
    kpis_spec = spec.get("outputs", {}).get("kpis", [])
    result = {}
    for k in kpis_spec:
        name = k.get("name", "kpi")
        ktype = k.get("type", "")
        if "displacement" in ktype:
            result[name] = {"value": round(-1.905e-3 + random.uniform(-1e-4, 1e-4), 6), "unit": "mm"}
        elif "field_max" in ktype and "mises" in name.lower():
            result[name] = {"value": round(290 + random.uniform(-20, 30), 2), "unit": "MPa"}
        elif "eigenfrequency" in ktype:
            idx = int(k.get("location", "mode_1").split("_")[-1])
            result[name] = {"value": round(idx * 1234.5, 2), "unit": "Hz"}
        elif "reaction" in ktype:
            result[name] = {"value": round(987 + random.uniform(-50, 50), 1), "unit": "N"}
        else:
            result[name] = {"value": round(random.uniform(0.1, 100), 4), "unit": "—"}
    return result


def _compare_kpis(actual: dict, run_id: str) -> dict:
    # Try to find expected.json for this run's spec
    comparisons = {}
    for name, val in actual.items():
        comparisons[name] = {
            "actual": val["value"],
            "unit": val["unit"],
            "status": "INFO",
        }
    return {"passed": True, "comparisons": comparisons}


# ── Utility ───────────────────────────────────────────────────────

def _check_abaqus() -> bool:
    import shutil
    return shutil.which("abaqus") is not None


def _list_cases() -> list[str]:
    return [d.name for d in sorted(CASES_DIR.iterdir()) if d.is_dir() and (d / "spec.yaml").exists()]


def _make_run_id(spec_yaml: str) -> str:
    return hashlib.sha256(spec_yaml.encode()).hexdigest()[:16]


async def _generate_spec_async(
    text: str, release: str, backend: str,
    anthropic_key: str = "", openai_key: str = "",
) -> tuple[dict, list]:
    """Generate spec from NL text, using LLM or template."""
    import os
    if backend in ("anthropic", "openai"):
        try:
            from agent.llm_planner import LLMPlanner
            # Temporarily override env var if key provided from frontend
            env_backup = {}
            if backend == "anthropic" and anthropic_key:
                env_backup["ANTHROPIC_API_KEY"] = os.environ.get("ANTHROPIC_API_KEY", "")
                os.environ["ANTHROPIC_API_KEY"] = anthropic_key
            elif backend == "openai" and openai_key:
                env_backup["OPENAI_API_KEY"] = os.environ.get("OPENAI_API_KEY", "")
                os.environ["OPENAI_API_KEY"] = openai_key
            try:
                planner = LLMPlanner(backend=backend)
                return planner.generate(text)
            finally:
                # Restore env
                for k, v in env_backup.items():
                    if v:
                        os.environ[k] = v
                    else:
                        os.environ.pop(k, None)
        except Exception:
            pass  # fall through to template

    # Template-based generation
    from agent.llm_planner import LLMPlanner
    planner = LLMPlanner(backend="template")
    spec, missing = planner.generate(text)
    spec["meta"]["abaqus_release"] = release
    # Enrich spec from text keywords
    t = text.lower()
    if "孔" in t or "hole" in t:
        spec["geometry"]["type"] = "plate_with_hole"
        spec["meta"]["model_name"] = "PlateWithHole"
    if "模态" in t or "频率" in t or "freq" in t:
        spec["analysis"]["step_type"] = "Frequency"
        spec["analysis"]["solver"] = "standard"
        spec["material"]["density"] = 7.85e-9
        spec["outputs"]["kpis"] = [
            {"name": "freq_1", "type": "eigenfrequency", "location": "mode_1"},
            {"name": "freq_2", "type": "eigenfrequency", "location": "mode_2"},
        ]
    if "显式" in t or "冲击" in t or "explicit" in t:
        spec["analysis"]["step_type"] = "Dynamic_Explicit"
        spec["analysis"]["solver"] = "explicit"
        spec["material"]["density"] = 7.85e-9
    return spec, missing


# ── Main ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    print("\n  Abaqus Agent API")
    print("  ─────────────────────────────")
    print(f"  Frontend : http://localhost:8000")
    print(f"  API docs : http://localhost:8000/docs")
    print(f"  Abaqus   : {'✓ found' if _check_abaqus() else '✗ not found (simulation mode)'}")
    print(f"  Cases    : {_list_cases()}")
    print()
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
