"""
core/pipeline.py
----------------
Pipeline execution logic shared between FastAPI server and MCP server.

When Abaqus is available: uses the real AbaqusOrchestrator (runner/ + post/).
When Abaqus is not available: runs a demo (flow-walkthrough) mode that never
fabricates results — no numeric KPI without a solver source, every log line
carries the DEMO MODE prefix, and the KPI section stays empty with an explicit
未检测到 Abaqus notice (gate G2).
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

# G2 demo-mode contract: without a solver the pipeline may only demonstrate
# the FLOW. No line may claim solver output happened (no "ANALYSIS COMPLETE",
# no "syntaxcheck PASSED", no fabricated numbers) and every line carries the
# DEMO MODE prefix so a console screenshot can never pass as a real solve.
DEMO_PREFIX = "DEMO MODE"
DEMO_KPI_NOTICE = "未检测到 Abaqus，也未检测到 CalculiX，无法求解；演示模式不输出任何数值 KPI"

# Stage wording for the CalculiX fallback. The Abaqus labels above stay exactly
# as they were: a console screenshot must never be ambiguous about which solver
# produced the numbers, and "从 ODB 提取 KPI" on a run that never made an .odb
# would be its own small lie.
CALCULIX_STAGE_DESCS = {
    "build_model": "生成 CalculiX .inp（纯 Python 网格器）",
    "syntaxcheck": "语法检查（CalculiX 无预检，跳过）",
    "submit_job": "提交 CalculiX 作业",
    "monitor_job": "等待 CalculiX 求解结束",
    "extract_kpis": "从 .dat / .frd 提取 KPI",
}

STAGE_LOGS = {
    "validate_spec": [
        ("info", DEMO_PREFIX + " | abaqus_release: {release}, solver: {solver}"),
    ],
    "build_model": [
        ("info", DEMO_PREFIX + " | 流程演示：此阶段会生成 CAE noGUI 脚本并产出 {model}.inp（未检测到 Abaqus，未执行）"),
    ],
    "syntaxcheck": [
        ("info", DEMO_PREFIX + " | 流程演示：此阶段会运行 abaqus syntaxcheck 预检 .inp（未检测到 Abaqus，未执行）"),
    ],
    "submit_job": [
        ("info", DEMO_PREFIX + " | 流程演示：此阶段会提交 Abaqus 求解作业（未检测到 Abaqus，未执行）"),
    ],
    "monitor_job": [
        ("info", DEMO_PREFIX + " | 流程演示：此阶段会轮询 .sta 作业状态（未检测到 Abaqus，未执行）"),
    ],
    "extract_kpis": [
        ("warn", DEMO_PREFIX + " | 未检测到 Abaqus，无法求解 —— 不生成任何数值 KPI"),
    ],
    "physics_contracts": [
        ("info", DEMO_PREFIX + " | 流程演示：无求解 KPI 可评估，Physics Contracts 跳过"),
    ],
}

# ── Stage descriptions for progress display ───────────────────────

STAGE_DESCS = {s[0]: s[1] for s in STAGES}


def _warning_lines(val) -> list[dict]:
    """Stage log lines for a `warnings` progress value.

    One key, two meanings. agent/orchestrator.py:436 sends a count
    (`len(result["warnings"])`); four other sites and the CalculiX
    orchestrator send a list of texts. The formatter only ever handled the
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


def simulate_stage(stage_id: str, model: str, release: str,
                   solver: str, run_id: str) -> dict:
    """Demo-mode stage log lines (flow walkthrough only, never solver claims)."""
    templates = STAGE_LOGS.get(stage_id, [("info", DEMO_PREFIX + " | 流程演示（未执行）")])
    logs = []
    for level, msg in templates:
        logs.append({
            "level": level,
            "text": msg.format(model=model, release=release,
                               solver=solver, run_id=run_id[:8]),
        })
    return {"status": "done", "logs": logs}


# ── Real Abaqus pipeline (via orchestrator) ───────────────────────

async def _run_pipeline_real(
    run_id: str,
    runs: dict,
    on_stage_update: Callable[[str, dict], Awaitable[None]] | None = None,
    decision=None,
) -> None:
    """Run a real solver pipeline (Abaqus by default, CalculiX when decided)."""
    from agent.orchestrator import build_orchestrator

    run = runs[run_id]
    run["status"] = "RUNNING"
    spec = run["spec"]
    runner_cfg = run.get("runner_cfg", {})
    is_ccx = getattr(decision, "backend", None) == "calculix"
    stage_descs = dict(STAGE_DESCS)
    if is_ccx:
        stage_descs.update(CALCULIX_STAGE_DESCS)
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
                    # Same key, two very different meanings: the CalculiX
                    # fallback tags a number it computed differently, while the
                    # grading stages use it to say nothing was compared at all.
                    # "降级说明" on the latter reads as a solver problem.
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
    When not available: runs demo (flow-walkthrough) mode — see DEMO_PREFIX.

    Args:
        run_id: Run identifier
        runs: Shared runs dict (mutated in-place)
        on_stage_update: Optional async callback(stage_id, full_run_snapshot)
    """
    from core.backends import check_calculix, select_backend

    run = runs[run_id]
    decision = select_backend(
        run.get("spec", {}),
        abaqus_available=check_abaqus(),
        calculix_available=check_calculix(),
        override=(run.get("runner_cfg") or {}).get("backend"),
    )
    run["backend"] = decision.as_dict()

    # A bad backend setting, or an explicit override naming an absent Abaqus,
    # must fail loudly rather than slide into demo mode: the user asked for a
    # specific solver and did not get it. (An unsupported CalculiX spec is
    # refused by CalculiXOrchestrator itself, with the spec field named.)
    if decision.backend != "calculix" and not decision.supported:
        from core.backends import refusal_messages
        run["status"] = "FAILED"
        run["limitations"] = [b.as_dict() for b in decision.blockers]
        run["kpi_notice"] = "；".join(refusal_messages(decision))
        run["finished_at"] = time.time()
        run["stages"]["validate_spec"] = {
            "status": "error",
            "desc": STAGE_DESCS["validate_spec"],
            "logs": [{"level": "error", "text": m} for m in refusal_messages(decision)],
        }
        if on_stage_update:
            await on_stage_update("done", _run_snapshot(run))
        return

    if decision.backend in ("abaqus", "calculix"):
        await _run_pipeline_real(run_id, runs, on_stage_update, decision=decision)
        return

    # ── Fallback: demo (flow-walkthrough) mode, gate G2 ───────────
    # Nothing numeric may be produced here: KPIs stay empty with an explicit
    # notice, and every stage log line carries the DEMO MODE prefix. The only
    # genuinely executed step is schema validation (needs no solver).
    run = runs[run_id]
    run["status"] = "RUNNING"
    run["demo_mode"] = True
    run["kpi_notice"] = DEMO_KPI_NOTICE
    spec = run["spec"]
    model = spec.get("meta", {}).get("model_name", "Model")
    # The installed solver is the authority, not the spec field — that field is
    # unvalidated user metadata and has drifted before. Only fall back to the
    # spec (and label it) when no solver can be probed.
    from tools.abaqus_cmd import detect_abaqus_release
    detected = detect_abaqus_release()
    if detected:
        release = detected
    else:
        stated = spec.get("meta", {}).get("abaqus_release") or "未知"
        release = f"{stated}（spec 声明值，未探测到求解器）"
    solver = spec.get("analysis", {}).get("solver", "standard")

    total = len(STAGES)

    for i, (stage_id, desc, dur_min, _dur_max) in enumerate(STAGES):
        run["stages"][stage_id] = {"status": "running", "desc": desc, "logs": []}
        run["progress_pct"] = round(i / total * 100)

        if on_stage_update:
            await on_stage_update(stage_id, _run_snapshot(run))

        stage_start = time.time()
        # UI pacing only — fixed short delay so the flow demo stays watchable.
        await asyncio.sleep(dur_min)

        result = simulate_stage(stage_id, model, release, solver, run_id)
        status = result["status"]
        logs = result["logs"]

        if stage_id == "validate_spec":
            # Schema validation is real work that needs no solver — run it.
            valid, errors = validate_spec(spec)
            if valid:
                logs = [{"level": "ok",
                         "text": DEMO_PREFIX + " | Schema 校验通过（真实执行，无需求解器）"}] + logs
            else:
                status = "error"
                logs = [{"level": "error",
                         "text": DEMO_PREFIX + " | Schema 校验失败: " + "; ".join(errors)}]

        run["stages"][stage_id] = {
            "status": status,
            "desc": desc,
            "logs": logs,
            "elapsed_ms": int((time.time() - stage_start) * 1000),
        }

        if on_stage_update:
            await on_stage_update(stage_id, _run_snapshot(run))

        if status == "error":
            run["status"] = "FAILED"
            run["finished_at"] = time.time()
            if on_stage_update:
                await on_stage_update("done", _run_snapshot(run))
            return

    # G2: no solver ran, so there is nothing to report — no KPIs, no
    # regression verdict, no contract evaluation against fabricated values.
    run["kpis"] = {}
    run["regression"] = {}
    run["contracts"] = {}
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
        "kpis_missing": run.get("kpis_missing", []),
        "mesh_risks": run.get("mesh_risks", []),
        "kpi_notice": run.get("kpi_notice", ""),
        "demo_mode": run.get("demo_mode", False),
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


# ── Demo flow for the orchestrator entry (gate G2) ───────────────────────────────────────────────────

def run_demo_flow(
    spec: dict,
    spec_path: str | Path | None = None,
    workdir: str | Path | None = None,
    on_progress: Callable[[str, dict], None] | None = None,
) -> dict:
    """Solver-less demo flow used by AbaqusOrchestrator when no Abaqus resolves.

    Contract (G2): performs only the real, solver-free step (schema
    validation), announces every skipped solver stage with a DEMO MODE
    prefix, and persists a result.json whose KPI section is empty plus an
    explicit 未检测到 Abaqus notice. The workdir defaults to a fresh temp dir
    so demo output can never overwrite a case's runs/ cache from real solves.
    """
    import tempfile
    from datetime import datetime

    progress = on_progress or (lambda s, d: None)
    progress("demo_mode", {
        "notice": DEMO_PREFIX + " | 未检测到 Abaqus，无法求解 —— 进入演示模式：仅演示流程，不生成任何数值 KPI",
    })

    result: dict = {
        "demo_mode": True,
        "spec_path": str(spec_path) if spec_path else None,
        "started_at": datetime.now().isoformat(),
        "stages": {},
        "kpis": {},
        "kpi_notice": DEMO_KPI_NOTICE,
        "regression": {},
        "contracts": {},
        "status": "DEMO",
    }

    valid, errors = validate_spec(spec)
    result["stages"]["validate_spec"] = {"valid": valid, "errors": errors, "demo": True}
    if not valid:
        result["status"] = "FAILED"
        result["error"] = {
            "error_code": "SPEC_INVALID",
            "message": "Spec validation failed: " + "; ".join(errors),
        }
        progress("validate_spec", {
            "error": DEMO_PREFIX + " | Schema 校验失败: " + "; ".join(errors),
        })
    else:
        progress("validate_spec", {
            "ok": True,
            "demo": DEMO_PREFIX + " | Schema \u6821\u9a8c\u901a\u8fc7\uff08\u771f\u5b9e\u6267\u884c\uff0c\u65e0\u9700\u6c42\u89e3\u5668\uff09",
        })
        for stage_id, desc, _dur_min, _dur_max in STAGES[1:]:
            note = DEMO_PREFIX + " | \u6d41\u7a0b\u6f14\u793a\uff1a" + desc + "\uff08\u672a\u68c0\u6d4b\u5230 Abaqus\uff0c\u672a\u6267\u884c\uff09"
            result["stages"][stage_id] = {"status": "demo_skipped", "demo": True, "notice": note}
            progress(stage_id, {"demo": note})

    result["finished_at"] = datetime.now().isoformat()

    out_dir = Path(workdir) if workdir else Path(tempfile.mkdtemp(prefix="abaqus_agent_demo_"))
    out_dir.mkdir(parents=True, exist_ok=True)
    result["workdir"] = str(out_dir)
    result_path = out_dir / "result.json"
    result["result_path"] = str(result_path)
    try:
        result_path.write_text(
            json.dumps(result, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )
    except OSError:
        result["result_path"] = None
    progress("demo_mode", {"result_json": result.get("result_path")})
    return result
