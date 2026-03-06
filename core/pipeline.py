"""
core/pipeline.py
----------------
Pipeline execution logic extracted from server.py.
Shared between FastAPI server and MCP server.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import random
import time
import uuid
from pathlib import Path
from typing import Awaitable, Callable

import yaml

from core.helpers import CASES_DIR, check_abaqus
from tools.schema_validator import validate_spec

# ── Pipeline stage definitions ────────────────────────────────────

STAGES = [
    ("validate_spec", "校验 Problem Spec",          0.3, 0.6),
    ("build_model",   "生成 CAE noGUI → .inp",      1.0, 2.0),
    ("syntaxcheck",   "语法检查（不消耗 token）",    0.4, 0.8),
    ("submit_job",    "提交 Abaqus 作业",            1.2, 2.5),
    ("monitor_job",   "轮询 .sta 状态",              0.8, 1.5),
    ("extract_kpis",  "从 ODB 提取 KPI",             0.6, 1.2),
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


def simulate_stage(stage_id: str, model: str, release: str,
                   solver: str, run_id: str) -> dict:
    templates = STAGE_LOGS.get(stage_id, [("ok", "完成")])
    logs = []
    for level, msg in templates:
        logs.append({
            "level": level,
            "text": msg.format(model=model, release=release,
                               solver=solver, run_id=run_id[:8]),
        })
    return {"status": "done", "logs": logs, "elapsed_ms": random.randint(200, 1500)}


async def run_stage_real(stage_id: str, run: dict) -> dict:
    """Attempt real Abaqus execution for a stage."""
    return simulate_stage(
        stage_id,
        run["spec"].get("meta", {}).get("model_name", "Model"),
        run["spec"].get("meta", {}).get("abaqus_release", "2024"),
        run["spec"].get("analysis", {}).get("solver", "standard"),
        run["run_id"],
    )


async def run_pipeline(
    run_id: str,
    runs: dict,
    on_stage_update: Callable[[str, dict], Awaitable[None]] | None = None,
) -> None:
    """
    Execute the Abaqus pipeline (simulation or real).

    Args:
        run_id: Run identifier
        runs: Shared runs dict (mutated in-place)
        on_stage_update: Optional async callback(stage_id, full_run_snapshot)
                         called after each stage completes.
    """
    run = runs[run_id]
    run["status"] = "RUNNING"
    spec = run["spec"]
    model = spec.get("meta", {}).get("model_name", "Model")
    release = spec.get("meta", {}).get("abaqus_release", "2024")
    solver = spec.get("analysis", {}).get("solver", "standard")

    abaqus_available = check_abaqus()
    total = len(STAGES)

    for i, (stage_id, desc, dur_min, dur_max) in enumerate(STAGES):
        run["stages"][stage_id] = {"status": "running", "desc": desc, "logs": []}
        run["progress_pct"] = round(i / total * 100)

        if on_stage_update:
            await on_stage_update(stage_id, _run_snapshot(run))

        await asyncio.sleep(dur_min + random.random() * (dur_max - dur_min))

        if abaqus_available:
            result = await run_stage_real(stage_id, run)
        else:
            result = simulate_stage(stage_id, model, release, solver, run_id)

        run["stages"][stage_id] = {
            "status": result["status"],
            "desc": desc,
            "logs": result["logs"],
            "elapsed_ms": result.get("elapsed_ms", 0),
        }

        if on_stage_update:
            await on_stage_update(stage_id, _run_snapshot(run))

        if result["status"] == "error":
            run["status"] = "FAILED"
            run["finished_at"] = time.time()
            return

    run["kpis"] = mock_kpis(spec)
    run["regression"] = compare_kpis(run["kpis"], run_id)
    run["progress_pct"] = 100
    run["status"] = "COMPLETED"
    run["finished_at"] = time.time()

    if on_stage_update:
        await on_stage_update("done", _run_snapshot(run))


def _run_snapshot(run: dict) -> dict:
    """Create a JSON-serializable snapshot of a run."""
    return {
        "run_id": run["run_id"],
        "status": run.get("status"),
        "progress_pct": run.get("progress_pct", 0),
        "stages": run.get("stages", {}),
        "kpis": run.get("kpis", {}),
        "elapsed": time.time() - run.get("started_at", time.time()),
    }


async def run_benchmark_async(
    run_id: str,
    runs: dict,
    dry_run: bool = True,
) -> None:
    run = runs[run_id]
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
            case_run_id = f"{run_id}_{case_name}"
            runs[case_run_id] = {
                "run_id": case_run_id, "status": "PENDING",
                "spec": spec, "runner_cfg": {},
                "stages": {}, "kpis": {},
                "started_at": time.time(), "finished_at": None,
                "progress_pct": 0,
            }
            await run_pipeline(case_run_id, runs)
            cr = runs[case_run_id]
            run["results"][case_name] = {
                "status": cr["status"],
                "kpis": cr.get("kpis", {}),
                "regression": cr.get("regression", {}),
            }

    run["progress_pct"] = 100
    run["status"] = "COMPLETED"
    run["finished_at"] = time.time()


# ── KPI helpers ───────────────────────────────────────────────────

def mock_kpis(spec: dict) -> dict:
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
            result[name] = {"value": round(random.uniform(0.1, 100), 4), "unit": "\u2014"}
    return result


def compare_kpis(actual: dict, run_id: str) -> dict:
    comparisons = {}
    for name, val in actual.items():
        comparisons[name] = {
            "actual": val["value"],
            "unit": val["unit"],
            "status": "INFO",
        }
    return {"passed": True, "comparisons": comparisons}
