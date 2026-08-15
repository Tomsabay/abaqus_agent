"""
core/pipeline.py
----------------
Pipeline execution logic shared between FastAPI server and MCP server.

With Abaqus: uses the real AbaqusOrchestrator (runner/ + post/).

Without Abaqus: refuses, and names the environment variable that fixes it.
There is no second solver and no walkthrough mode. Both used to live here and
both were removed 2026-08-15 -- this is an Abaqus agent, so "no Abaqus" is an
answer, not a situation to simulate around. The rule that outlives them is the
one that mattered all along: no numeric KPI without a solver that produced it.
"""
from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Awaitable, Callable

import yaml

from core.helpers import CASES_DIR, check_abaqus
from tools.schema_validator import validate_spec

# ── Pipeline stage definitions ────────────────────────────────────

STAGES = [
    ("validate_spec", "校验 Problem Spec",          0.3, 0.6),
    ("build_model",   "生成 CAE noGUI → .inp",      1.0, 2.0),
    ("syntaxcheck",   "语法检查（求解前检查）",      0.4, 0.8),
    ("submit_job",    "提交 Abaqus 作业",            1.2, 2.5),
    ("monitor_job",   "轮询 .sta 状态",              0.8, 1.5),
    ("extract_kpis",  "从 ODB 提取 KPI",             0.6, 1.2),
    ("physics_contracts", "评估 Physics Contracts",  0.2, 0.5),
]


# ── Stage descriptions for progress display ───────────────────────

STAGE_DESCS = {s[0]: s[1] for s in STAGES}


def _warning_lines(val) -> list[dict]:
    """Stage log lines for a `warnings` progress value.

    One key, two meanings. agent/orchestrator.py:436 sends a count
    (`len(result["warnings"])`); four other sites send a list of texts. The formatter only ever handled the
    count, so a list rendered as

        ⚠ ['85 tie nodes were left unconstrained'] warnings

    with the Python repr on screen, an empty list rendered as `⚠ [] warnings`
    -- a warning banner announcing there were none -- and a clean syntax check
    put `⚠ 0 warnings` on every successful run.
    """
    if val is None:
        return []
    if isinstance(val, (list, tuple, set)):
        texts = [str(item).strip() for item in val]
        return [{"level": "warn", "text": "⚠ %s" % text} for text in texts if text]
    try:
        count = int(val)
    except (TypeError, ValueError):
        text = str(val).strip()
        return [{"level": "warn", "text": "⚠ %s" % text}] if text else []
    if count <= 0:
        return []
    return [{"level": "warn", "text": "⚠ %d warnings" % count}]


async def _run_pipeline_real(
    run_id: str,
    runs: dict,
    on_stage_update: Callable[[str, dict], Awaitable[None]] | None = None,
    decision=None,
) -> None:
    """Run the solver pipeline."""
    from agent.orchestrator import build_orchestrator

    run = runs[run_id]
    run["status"] = "RUNNING"
    spec = run["spec"]
    runner_cfg = run.get("runner_cfg", {})
    stage_descs = dict(STAGE_DESCS)
    if decision is not None:
        run["backend"] = decision.as_dict()

    # Map orchestrator stages to pipeline stage IDs
    _STAGE_ORDER = [
        "validate_spec", "build_model", "syntaxcheck",
        "submit_job", "monitor_job", "extract_kpis", "physics_contracts",
    ]

    def _on_progress(stage: str, data: dict):
        """Sync callback from orchestrator → update run state."""
        desc = stage_descs.get(stage, stage)
        logs = []

        # Convert orchestrator progress data to log entries
        if isinstance(data, dict):
            for key, val in data.items():
                if key == "ok" and val:
                    logs.append({"level": "ok", "text": f"✓ {stage} 完成"})
                elif key == "inp":
                    logs.append({"level": "ok", "text": f"INP_WRITTEN: {val}"})
                elif key == "warnings":
                    logs += _warning_lines(val)
                elif key == "cache_reason":
                    # A proven reuse is expected behaviour -> info. A rebuild
                    # forced by a fingerprint mismatch is worth a louder line:
                    # it means the cached deck did NOT correspond to the spec.
                    level = "info" if data.get("cached") else "warn"
                    logs.append({"level": level, "text": val})
                elif key == "cached":
                    pass  # rendered via cache_reason
                elif key == "skipped":
                    logs.append({"level": "warn", "text": f"跳过：{val}"})
                elif key == "caveat":
                    # Same key, two meanings: a stage tagging a number it
                    # qualified, versus a grading stage saying nothing was
                    # compared at all. "降级说明" on the latter reads as a
                    # solver problem.
                    prefix = ("未评级" if stage in ("compare_kpis", "physics_contracts")
                              else "降级说明")
                    logs.append({"level": "warn", "text": f"{prefix}：{val}"})
                elif key == "refusals":
                    for reason in val:
                        logs.append({"level": "error", "text": f"拒绝求解：{reason}"})
                elif key == "status":
                    logs.append({"level": "info", "text": f"status: {val}"})
                elif key == "kpis":
                    for kname, kval in val.items():
                        logs.append({"level": "ok", "text": f"  {kname} = {kval}"})
                elif key == "passed":
                    label = "physics contracts" if stage == "physics_contracts" else "regression"
                    # None is neither. It means the check did not run -- no
                    # baseline, or no contracts -- and rendering it as FAIL in
                    # red sends people hunting for a defect in the model.
                    if val is None:
                        logs.append({"level": "warn",
                                     "text": f"{label}: NOT GRADED（未做比对）"})
                    else:
                        logs.append({"level": "ok" if val else "error",
                                     "text": f"{label}: {'PASS' if val else 'FAIL'}"})
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
            run["progress_pct"] = round(6 / len(_STAGE_ORDER) * 100)

        # Update stage status
        existing = run["stages"].get(stage, {"status": "running", "desc": desc, "logs": []})
        existing_logs = existing.get("logs", [])
        existing_logs.extend(logs)

        if data.get("skipped"):
            status = "skipped"
        # `"passed" in data`, not `data.get("passed") is not None`: a grading
        # stage that answers None HAS finished -- its answer is "not graded" --
        # and the old test left compare_kpis spinning at "running" forever on
        # every run without a baseline.
        elif (data.get("ok") or "passed" in data or data.get("inp")
              or data.get("kpis") or data.get("status") == "completed"):
            status = "done"
        else:
            status = "running"
        run["stages"][stage] = {
            "status": status,
            "desc": desc,
            "logs": existing_logs,
        }

    # Set initial running state for all stages
    for stage_id, desc, _, _ in STAGES:
        run["stages"][stage_id] = {
            "status": "pending", "desc": stage_descs.get(stage_id, desc), "logs": [],
        }

    if on_stage_update:
        await on_stage_update("start", _run_snapshot(run))

    # Run orchestrator in thread pool (it's synchronous)
    loop = asyncio.get_event_loop()
    # expected_path / contracts_path were simply never passed here. The
    # orchestrator only compares KPIs `if self.expected`, so every run started
    # through this module -- workbench Accept, POST /api/run/start, MCP
    # start_run, the benchmark loop -- finished with `regression: {}` and
    # `contracts: {}`: the grading layer this project is built around did not
    # run on any path a user actually walks. A run whose caller supplies
    # neither now gets an explicit NOT GRADED record instead of an empty dict
    # (AbaqusOrchestrator._stage_no_baseline).
    orch = build_orchestrator(
        decision=decision,
        spec_dict=spec,
        runner_cfg=runner_cfg,
        expected_path=run.get("expected_path"),
        contracts_path=run.get("contracts_path"),
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
    run["contracts"] = result.get("contracts", {})
    run["capsule_path"] = result.get("capsule_path")
    run["result_path"] = str(run.get("capsule_path", "")).replace("capsule.json", "result.json") \
        if result.get("capsule_path") else None
    build_stage = result.get("stages", {}).get("build_model", {})
    run["workdir"] = build_stage.get("workdir")
    run["artifacts"] = result.get("artifacts", {})
    run["orchestrator_result"] = result
    run["finished_at"] = time.time()
    run["progress_pct"] = 100 if run["status"] == "COMPLETED" else run.get("progress_pct", 0)

    # Backend provenance rides the same channel the UI already polls, so a
    # degraded run can never render as if a full solver produced it.
    if result.get("backend"):
        run["backend"] = result["backend"]
    if result.get("limitations"):
        run["limitations"] = result["limitations"]
    if result.get("kpi_provenance"):
        run["kpi_provenance"] = result["kpi_provenance"]
    # Unconditional, unlike its neighbours: an empty list is the ANSWER "nothing
    # was dropped", and a stale non-empty one from an earlier run of the same
    # id would be a claim about numbers that are no longer on screen.
    run["kpis_missing"] = result.get("kpis_missing", [])
    run["mesh_risks"] = result.get("mesh_risks", [])
    if result.get("kpi_notice"):
        run["kpi_notice"] = result["kpi_notice"]
    if result.get("visuals_notice"):
        run["visuals_notice"] = result["visuals_notice"]

    # Mark all completed stages
    if run["status"] == "COMPLETED":
        for stage_id in _STAGE_ORDER:
            if stage_id in run["stages"] and run["stages"][stage_id]["status"] != "skipped":
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
    When not available: refuses, naming the variable that fixes it.

    Args:
        run_id: Run identifier
        runs: Shared runs dict (mutated in-place)
        on_stage_update: Optional async callback(stage_id, full_run_snapshot)
    """
    from core.backends import select_backend

    run = runs[run_id]
    decision = select_backend(
        run.get("spec", {}),
        abaqus_available=check_abaqus(),
        override=(run.get("runner_cfg") or {}).get("backend"),
    )
    run["backend"] = decision.as_dict()

    # No Abaqus, no run. There is nothing to fall back to, and a walkthrough
    # that produced no numbers was still a screen that looked like a run.
    if not decision.supported:
        from core.backends import refusal_fields, refusal_messages
        run.update(refusal_fields(decision))
        run["finished_at"] = time.time()
        run["stages"]["validate_spec"] = {
            "status": "error",
            "desc": STAGE_DESCS["validate_spec"],
            "logs": [{"level": "error", "text": m} for m in refusal_messages(decision)],
        }
        if on_stage_update:
            await on_stage_update("done", _run_snapshot(run))
        return

    await _run_pipeline_real(run_id, runs, on_stage_update, decision=decision)


def _run_snapshot(run: dict) -> dict:
    """Create a JSON-serializable snapshot of a run."""
    return {
        "run_id": run["run_id"],
        "status": run.get("status"),
        "progress_pct": run.get("progress_pct", 0),
        "stages": run.get("stages", {}),
        "kpis": run.get("kpis", {}),
        "kpis_missing": run.get("kpis_missing", []),
        "mesh_risks": run.get("mesh_risks", []),
        "kpi_notice": run.get("kpi_notice", ""),
        "unsolved": not (run.get("backend") or {}).get("supported", True),
        # Which solver produced these numbers, and what it could not do.
        "backend": run.get("backend", {}),
        "limitations": run.get("limitations", []),
        "kpi_provenance": run.get("kpi_provenance", {}),
        "visuals_notice": run.get("visuals_notice", ""),
        "regression": run.get("regression", {}),
        "contracts": run.get("contracts", {}),
        "capsule_path": run.get("capsule_path"),
        "result_path": run.get("result_path"),
        "elapsed": time.time() - run.get("started_at", time.time()),
    }


def _path_if_exists(path: Path) -> str | None:
    """Absolute path as a string, or None -- what the orchestrator expects."""
    return str(path) if path.is_file() else None


def _read_runner_cfg(path: Path) -> dict:
    """A case's runner.json, or {} when it has none or it is unreadable.

    Unreadable is worth a line on stderr rather than a crash: the solver
    settings are a performance choice, and losing them must not take the whole
    benchmark down with them.
    """
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        import sys
        print("[pipeline] runner.json not used (%s): %s: %s"
              % (path, type(exc).__name__, exc), file=sys.stderr)
        return {}


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
            # The case directory holds all three of these and the benchmark
            # used to ignore every one: `runner_cfg: {}` fell through to the
            # orchestrator's bare defaults (cpus=1, timeout 1800s) rather than
            # the case's own runner.json, and with no expected.json the
            # benchmark reported per-case `regression` and `contracts` that
            # were empty by construction -- a benchmark that graded nothing.
            case_dir = CASES_DIR / case_name
            runs[case_run_id] = {
                "run_id": case_run_id, "status": "PENDING",
                "spec": spec,
                "runner_cfg": _read_runner_cfg(case_dir / "runner.json"),
                "expected_path": _path_if_exists(case_dir / "expected.json"),
                "contracts_path": _path_if_exists(case_dir / "contracts.yaml"),
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
                "contracts": cr.get("contracts", {}),
            }

    run["progress_pct"] = 100
    run["status"] = "COMPLETED"
    run["finished_at"] = time.time()
