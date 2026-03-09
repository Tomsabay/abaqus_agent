"""
core/pipeline.py
----------------
Pipeline execution logic shared between FastAPI server and MCP server.

When Abaqus is available: uses the real AbaqusOrchestrator (runner/ + post/).
When Abaqus is not available: falls back to simulated stages.
"""
from __future__ import annotations

import asyncio
import random
import time
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

# ── Stage descriptions for progress display ───────────────────────

STAGE_DESCS = {s[0]: s[1] for s in STAGES}


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


# ── Real Abaqus pipeline (via orchestrator) ───────────────────────

async def _run_pipeline_real(
    run_id: str,
    runs: dict,
    on_stage_update: Callable[[str, dict], Awaitable[None]] | None = None,
) -> None:
    """Run the real Abaqus pipeline using AbaqusOrchestrator."""
    from agent.orchestrator import AbaqusOrchestrator

    run = runs[run_id]
    run["status"] = "RUNNING"
    spec = run["spec"]
    runner_cfg = run.get("runner_cfg", {})

    # Map orchestrator stages to pipeline stage IDs
    _STAGE_ORDER = [
        "validate_spec", "build_model", "syntaxcheck",
        "submit_job", "monitor_job", "extract_kpis",
    ]

    def _on_progress(stage: str, data: dict):
        """Sync callback from orchestrator → update run state."""
        desc = STAGE_DESCS.get(stage, stage)
        logs = []

        # Convert orchestrator progress data to log entries
        if isinstance(data, dict):
            for key, val in data.items():
                if key == "ok" and val:
                    logs.append({"level": "ok", "text": f"✓ {stage} 完成"})
                elif key == "inp":
                    logs.append({"level": "ok", "text": f"INP_WRITTEN: {val}"})
                elif key == "warnings":
                    logs.append({"level": "warn", "text": f"⚠ {val} warnings"})
                elif key == "status":
                    logs.append({"level": "info", "text": f"status: {val}"})
                elif key == "kpis":
                    for kname, kval in val.items():
                        logs.append({"level": "ok", "text": f"  {kname} = {kval}"})
                elif key == "passed":
                    level = "ok" if val else "error"
                    logs.append({"level": level, "text": f"regression: {'PASS' if val else 'FAIL'}"})
                elif key not in ("attempt", "max", "index", "total"):
                    logs.append({"level": "info", "text": f"{key}: {val}"})

        if not logs:
            logs = [{"level": "info", "text": f"{stage}: {data}" if data else f"{stage}..."}]

        # Determine progress percentage
        if stage in _STAGE_ORDER:
            idx = _STAGE_ORDER.index(stage)
            run["progress_pct"] = round((idx + 1) / len(_STAGE_ORDER) * 100)
        elif stage == "autorepair":
            pass  # keep current progress
        elif stage == "compare_kpis":
            run["progress_pct"] = 100

        # Update stage status
        existing = run["stages"].get(stage, {"status": "running", "desc": desc, "logs": []})
        existing_logs = existing.get("logs", [])
        existing_logs.extend(logs)

        run["stages"][stage] = {
            "status": "done" if data.get("ok") or data.get("passed") is not None or
                      data.get("inp") or data.get("kpis") or data.get("status") == "completed"
                      else "running",
            "desc": desc,
            "logs": existing_logs,
        }

    # Set initial running state for all stages
    for stage_id, desc, _, _ in STAGES:
        run["stages"][stage_id] = {"status": "pending", "desc": desc, "logs": []}

    if on_stage_update:
        await on_stage_update("start", _run_snapshot(run))

    # Run orchestrator in thread pool (it's synchronous)
    loop = asyncio.get_event_loop()
    orch = AbaqusOrchestrator(
        spec_dict=spec,
        runner_cfg=runner_cfg,
        on_progress=_on_progress,
    )

    try:
        result = await loop.run_in_executor(None, orch.run)
    except Exception as e:
        run["status"] = "FAILED"
        run["finished_at"] = time.time()
        run["stages"]["submit_job"] = {
            "status": "error",
            "desc": STAGE_DESCS.get("submit_job", ""),
            "logs": [{"level": "error", "text": str(e)}],
        }
        if on_stage_update:
            await on_stage_update("error", _run_snapshot(run))
        return

    # Map orchestrator result back to run state
    run["status"] = result.get("status", "FAILED")
    run["kpis"] = result.get("kpis", {})
    run["regression"] = result.get("regression", {})
    run["finished_at"] = time.time()
    run["progress_pct"] = 100 if run["status"] == "COMPLETED" else run.get("progress_pct", 0)

    # Mark all completed stages
    if run["status"] == "COMPLETED":
        for stage_id in _STAGE_ORDER:
            if stage_id in run["stages"]:
                run["stages"][stage_id]["status"] = "done"

    if result.get("error"):
        error_info = result["error"]
        # Find the failing stage and mark it
        error_stage = None
        for s in reversed(_STAGE_ORDER):
            if s in run["stages"] and run["stages"][s]["status"] == "running":
                error_stage = s
                break
        if error_stage:
            run["stages"][error_stage]["status"] = "error"
            run["stages"][error_stage]["logs"].append(
                {"level": "error", "text": error_info.get("message", str(error_info))}
            )

    if on_stage_update:
        await on_stage_update("done", _run_snapshot(run))


# ── Main pipeline entry point ─────────────────────────────────────

async def run_pipeline(
    run_id: str,
    runs: dict,
    on_stage_update: Callable[[str, dict], Awaitable[None]] | None = None,
) -> None:
    """
    Execute the Abaqus pipeline.

    When Abaqus is available: calls the real AbaqusOrchestrator.
    When not available: falls back to simulated stages.

    Args:
        run_id: Run identifier
        runs: Shared runs dict (mutated in-place)
        on_stage_update: Optional async callback(stage_id, full_run_snapshot)
    """
    if check_abaqus():
        await _run_pipeline_real(run_id, runs, on_stage_update)
        return

    # ── Fallback: simulated pipeline ──────────────────────────────
    run = runs[run_id]
    run["status"] = "RUNNING"
    spec = run["spec"]
    model = spec.get("meta", {}).get("model_name", "Model")
    release = spec.get("meta", {}).get("abaqus_release", "2024")
    solver = spec.get("analysis", {}).get("solver", "standard")

    total = len(STAGES)

    for i, (stage_id, desc, dur_min, dur_max) in enumerate(STAGES):
        run["stages"][stage_id] = {"status": "running", "desc": desc, "logs": []}
        run["progress_pct"] = round(i / total * 100)

        if on_stage_update:
            await on_stage_update(stage_id, _run_snapshot(run))

        await asyncio.sleep(dur_min + random.random() * (dur_max - dur_min))

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
        "regression": run.get("regression", {}),
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
