"""
mcp_server.py
-------------
MCP (Model Context Protocol) server for Abaqus Agent.

Exposes the same pipeline functionality as server.py but via
JSON-RPC 2.0 over stdin/stdout (standard MCP transport).

Tools:
  generate_spec       - NL text → spec YAML
  validate_spec       - validate spec YAML
  start_run           - start pipeline run
  get_run_status      - get run status/results
  diagnose_logs_tool  - Solver Doctor log diagnosis
  simulation_diff_tool - run/capsule/KPI diff report
  check_contracts_tool - physics contract evaluation
  capsule_init_from_inp_tool - initialize capsule from .inp
  case_memory_search_tool - search local run/capsule case memory
  run_benchmark       - trigger benchmark dry-run
  health_check        - health status
  get_premium_features - premium feature status
  activate_premium    - activate premium license

Resources:
  benchmark://cases    - benchmark case definitions
  premium://features   - premium feature status

Run:
  python mcp_server.py
"""

from __future__ import annotations

import asyncio
import base64
import json
import sys
import time
import uuid
from pathlib import Path

import yaml
from mcp.server.fastmcp import FastMCP

sys.path.insert(0, str(Path(__file__).parent))

from capsule.store import init_from_inp
from case_memory import CaseMemoryQuery, render_memory_markdown, search_case_memory
from contracts import evaluate_contracts
from core.helpers import CASES_DIR, check_abaqus, list_cases, make_run_id
from core.pipeline import (
    run_benchmark_async,
    run_pipeline,
)
from core.spec_generator import generate_spec_async
from doctor import diagnose_logs
from reporting import build_offline_report_pdf, build_offline_run_report
from simdiff import diff_runs, render_run_markdown
from tools.schema_validator import validate_spec
from validation import render_preflight_markdown, run_environment_preflight

# ── MCP Server ────────────────────────────────────────────────────

mcp = FastMCP(
    "abaqus-agent",
    instructions="LLM-powered Abaqus FEA automation agent",
)

# ── In-memory run store (shared within this process) ──────────────
RUNS: dict[str, dict] = {}

# ── Notification queues for progress streaming ────────────────────
# {run_id: [asyncio.Queue, ...]}
_progress_queues: dict[str, list[asyncio.Queue]] = {}


def subscribe_progress(run_id: str) -> asyncio.Queue:
    """Subscribe to progress updates for a run."""
    q: asyncio.Queue = asyncio.Queue()
    _progress_queues.setdefault(run_id, []).append(q)
    return q


def unsubscribe_progress(run_id: str, q: asyncio.Queue) -> None:
    """Unsubscribe from progress updates."""
    queues = _progress_queues.get(run_id, [])
    if q in queues:
        queues.remove(q)
    if not queues:
        _progress_queues.pop(run_id, None)


async def _broadcast_progress(run_id: str, data: dict) -> None:
    """Broadcast progress update to all subscribers."""
    for q in _progress_queues.get(run_id, []):
        await q.put(data)


# ── Tools ─────────────────────────────────────────────────────────

@mcp.tool(description="Convert natural language to Problem Spec YAML")
async def generate_spec(
    text: str,
    abaqus_release: str = "2024",
    llm_backend: str = "template",
    anthropic_key: str = "",
    openai_key: str = "",
) -> str:
    spec_dict, missing = await generate_spec_async(
        text, abaqus_release, llm_backend,
        anthropic_key=anthropic_key,
        openai_key=openai_key,
    )
    spec_yaml = yaml.dump(spec_dict, allow_unicode=True, default_flow_style=False)
    valid, errors = validate_spec(spec_dict)
    return json.dumps({
        "spec_yaml": spec_yaml,
        "spec_dict": spec_dict,
        "valid": valid,
        "errors": errors,
        "missing_questions": missing,
    }, ensure_ascii=False, default=str)


@mcp.tool(description="Validate a spec YAML string against the schema")
async def validate_spec_tool(spec_yaml: str) -> str:
    try:
        spec_dict = yaml.safe_load(spec_yaml)
        valid, errors = validate_spec(spec_dict)
        return json.dumps({"valid": valid, "errors": errors})
    except yaml.YAMLError as e:
        return json.dumps({"valid": False, "errors": [f"YAML parse error: {e}"]})


@mcp.tool(description="Start a pipeline run. Returns run_id. Use get_run_status to poll or subscribe to progress.")
async def start_run(spec_yaml: str, runner_cfg: str = "{}") -> str:
    try:
        spec_dict = yaml.safe_load(spec_yaml)
        valid, errors = validate_spec(spec_dict)
        if not valid:
            return json.dumps({"error": "Invalid spec", "errors": errors})
    except yaml.YAMLError as e:
        return json.dumps({"error": f"Invalid YAML: {e}"})

    try:
        cfg = json.loads(runner_cfg)
    except (json.JSONDecodeError, TypeError):
        cfg = {}

    run_id = make_run_id(spec_yaml)
    RUNS[run_id] = {
        "run_id": run_id,
        "status": "PENDING",
        "spec": spec_dict,
        "runner_cfg": cfg,
        "stages": {},
        "kpis": {},
        "started_at": time.time(),
        "finished_at": None,
        "progress_pct": 0,
    }

    async def _on_stage_update(stage_id: str, snapshot: dict) -> None:
        await _broadcast_progress(run_id, snapshot)

    # Launch pipeline in background
    asyncio.create_task(run_pipeline(run_id, RUNS, on_stage_update=_on_stage_update))
    return json.dumps({"run_id": run_id, "status": "PENDING"})


@mcp.tool(description="Get current status and results of a pipeline run")
async def get_run_status(run_id: str) -> str:
    if run_id not in RUNS:
        return json.dumps({"error": f"Run {run_id} not found"})
    run = RUNS[run_id]
    return json.dumps(
        {**run, "elapsed": time.time() - run["started_at"]},
        default=str, ensure_ascii=False,
    )


@mcp.tool(description="Check local OS, Python, and Abaqus command readiness for real validation")
async def environment_preflight_tool(
    abaqus_cmd: str = "",
    timeout_seconds: float = 15.0,
    check_release: bool = True,
    expected_release: str = "",
    workdir: str = "",
    runner_cfg_json: str = "{}",
) -> str:
    try:
        runner_cfg = json.loads(runner_cfg_json or "{}")
        if not isinstance(runner_cfg, dict):
            return json.dumps({"error": "runner_cfg_json must decode to an object"})
        result = run_environment_preflight(
            abaqus_cmd=abaqus_cmd or None,
            timeout_seconds=timeout_seconds,
            check_release=check_release,
            expected_release=expected_release,
            workdir=workdir or None,
            runner_cfg=runner_cfg,
        )
        result["markdown"] = render_preflight_markdown(result)
        return json.dumps(result, ensure_ascii=False, default=str)
    except (OSError, ValueError) as e:
        return json.dumps({"error": str(e)})


@mcp.tool(description="Build a Markdown/HTML report from an offline run directory, capsule.json, or result.json")
async def offline_report_export_tool(source: str, template: str = "standard") -> str:
    try:
        report = build_offline_run_report(source, template=template, embed_images=True)
        report["offline_source"] = source
        return json.dumps(report, ensure_ascii=False, default=str)
    except (FileNotFoundError, OSError, json.JSONDecodeError, ValueError) as e:
        return json.dumps({"error": str(e)})


@mcp.tool(description="Build a PDF report from an offline run directory, capsule.json, or result.json")
async def offline_report_pdf_export_tool(source: str, template: str = "standard") -> str:
    try:
        content = build_offline_report_pdf(source, template=template)
        return json.dumps({
            "source": source,
            "template": template,
            "format": "pdf",
            "bytes": len(content),
            "content_base64": base64.b64encode(content).decode("ascii"),
        }, ensure_ascii=False)
    except (FileNotFoundError, OSError, json.JSONDecodeError, ValueError, RuntimeError) as e:
        return json.dumps({"error": str(e)})


@mcp.tool(description="Diagnose Abaqus .sta/.msg/.log/.dat files or raw log text with Solver Doctor patterns")
async def diagnose_logs_tool(paths_json: str = "[]", text: str = "") -> str:
    try:
        paths = json.loads(paths_json or "[]")
        if isinstance(paths, str):
            paths = [paths]
        if not isinstance(paths, list):
            return json.dumps({"error": "paths_json must decode to a list of paths"})
        diagnosis = diagnose_logs(paths=paths, text=text)
        return json.dumps(diagnosis, ensure_ascii=False)
    except json.JSONDecodeError as e:
        return json.dumps({"error": f"Invalid paths_json: {e}"})


@mcp.tool(description="Compare two Abaqus runs, capsules, result JSON files, or KPI JSON files")
async def simulation_diff_tool(
    baseline: str,
    candidate: str,
    rtol: float = 0.05,
    tolerances_json: str = "",
) -> str:
    try:
        tolerances = json.loads(tolerances_json or "{}")
        if not isinstance(tolerances, dict):
            return json.dumps({"error": "tolerances_json must decode to an object"})
        diff = diff_runs(baseline, candidate, default_rtol=rtol, tolerances=tolerances)
        diff["markdown"] = render_run_markdown(diff)
        return json.dumps(diff, ensure_ascii=False, default=str)
    except (FileNotFoundError, OSError, json.JSONDecodeError, yaml.YAMLError) as e:
        return json.dumps({"error": str(e)})


@mcp.tool(description="Evaluate physics contracts against KPI JSON")
async def check_contracts_tool(kpis_json: str, contracts_yaml: str) -> str:
    try:
        kpis = json.loads(kpis_json)
        contracts = yaml.safe_load(contracts_yaml) or []
        if isinstance(contracts, dict):
            contracts = contracts.get("contracts", [])
        result = evaluate_contracts(contracts, kpis)
        return json.dumps(result, ensure_ascii=False, default=str)
    except (json.JSONDecodeError, yaml.YAMLError, TypeError, ValueError) as e:
        return json.dumps({"error": str(e)})


@mcp.tool(description="Initialize an experiment capsule from an existing Abaqus .inp file")
async def capsule_init_from_inp_tool(from_inp: str, out: str, model_name: str = "") -> str:
    try:
        capsule = init_from_inp(from_inp, out, model_name=model_name or None)
        return json.dumps(capsule, ensure_ascii=False, default=str)
    except (FileNotFoundError, OSError, ValueError) as e:
        return json.dumps({"error": str(e)})


@mcp.tool(description="Search local run/capsule directories as deterministic case memory")
async def case_memory_search_tool(
    roots_json: str,
    query: str = "",
    match_mode: str = "any",
    similar_to: str = "",
    status: str = "",
    model_name: str = "",
    contract: str = "",
    contracts_passed: str = "",
    diagnosis_id: str = "",
    kpi: str = "",
    artifact: str = "",
    limit: int = 10,
    include_artifacts: bool = False,
    sort_by: str = "score",
    sort_order: str = "desc",
    min_score: float = 0.0,
) -> str:
    try:
        roots = json.loads(roots_json or "[]")
        if isinstance(roots, str):
            roots = [roots]
        if not isinstance(roots, list):
            return json.dumps({"error": "roots_json must decode to a list of paths"})
        result = search_case_memory(CaseMemoryQuery(
            roots=tuple(roots),
            query=query,
            match_mode=match_mode,
            similar_to=similar_to or None,
            status=status,
            model_name=model_name,
            contract=contract,
            contracts_passed=contracts_passed,
            diagnosis_id=diagnosis_id,
            kpi=kpi,
            artifact=artifact,
            limit=limit,
            include_artifacts=include_artifacts,
            sort_by=sort_by,
            sort_order=sort_order,
            min_score=min_score,
        ))
        result["markdown"] = render_memory_markdown(result)
        return json.dumps(result, ensure_ascii=False, default=str)
    except (json.JSONDecodeError, OSError, ValueError, yaml.YAMLError) as e:
        return json.dumps({"error": str(e)})


@mcp.tool(description="Trigger benchmark dry-run across all cases")
async def run_benchmark_tool(dry_run: bool = True) -> str:
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
    asyncio.create_task(run_benchmark_async(run_id, RUNS, dry_run))
    return json.dumps({"run_id": run_id, "cases": cases, "dry_run": dry_run})


@mcp.tool(description="Health check — returns server status and Abaqus availability")
async def health_check() -> str:
    return json.dumps({
        "status": "ok",
        "abaqus_available": check_abaqus(),
        "cases": list_cases(),
        "version": "0.1.0",
        "transport": "mcp",
    })


@mcp.tool(description="Get premium feature status and capabilities")
async def get_premium_features() -> str:
    try:
        from premium.feature_registry import list_premium_capabilities
        from premium.licensing import PREMIUM_FEATURES, feature_gate
        return json.dumps({
            "features": {
                name: {
                    "display_name": PREMIUM_FEATURES[name],
                    "enabled": feature_gate.is_enabled(name),
                }
                for name in PREMIUM_FEATURES
            },
            "capabilities": list_premium_capabilities(),
        })
    except ImportError:
        return json.dumps({
            "features": {},
            "capabilities": {},
            "error": "Premium module not available",
        })


@mcp.tool(description="Activate premium features with a license key")
async def activate_premium(license_key: str) -> str:
    try:
        from premium.licensing import feature_gate
        if license_key:
            valid = feature_gate.set_license_key(license_key)
            return json.dumps({
                "valid": valid,
                "features": feature_gate.enabled_features(),
            })
        return json.dumps({"valid": False, "error": "No license key provided"})
    except ImportError:
        return json.dumps({"valid": False, "error": "Premium module not available"})


# ── Resources ─────────────────────────────────────────────────────

@mcp.resource("benchmark://cases", description="All benchmark case definitions")
async def get_benchmark_cases() -> str:
    cases = []
    for case_dir in sorted(CASES_DIR.iterdir()):
        if not case_dir.is_dir():
            continue
        spec_path = case_dir / "spec.yaml"
        exp_path = case_dir / "expected.json"
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
    return json.dumps({"cases": cases, "total": len(cases)}, default=str, ensure_ascii=False)


@mcp.resource("premium://features", description="Premium feature status")
async def get_premium_features_resource() -> str:
    try:
        from premium.feature_registry import list_premium_capabilities
        from premium.licensing import PREMIUM_FEATURES, feature_gate
        return json.dumps({
            "features": {
                name: {
                    "display_name": PREMIUM_FEATURES[name],
                    "enabled": feature_gate.is_enabled(name),
                }
                for name in PREMIUM_FEATURES
            },
            "capabilities": list_premium_capabilities(),
        })
    except ImportError:
        return json.dumps({
            "features": {},
            "capabilities": {},
            "error": "Premium module not available",
        })


# ── Main ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    mcp.run(transport="stdio")
