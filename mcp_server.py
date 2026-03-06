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
import json
import time
import uuid
from pathlib import Path

import yaml
from mcp.server.fastmcp import FastMCP

import sys
sys.path.insert(0, str(Path(__file__).parent))

from tools.schema_validator import validate_spec
from core.helpers import check_abaqus, list_cases, make_run_id, CASES_DIR
from core.pipeline import (
    run_pipeline, run_benchmark_async, mock_kpis, compare_kpis,
    STAGES as PIPELINE_STAGES,
)
from core.spec_generator import generate_spec_async

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
        from premium.licensing import feature_gate, PREMIUM_FEATURES
        from premium.feature_registry import list_premium_capabilities
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
        from premium.licensing import feature_gate, PREMIUM_FEATURES
        from premium.feature_registry import list_premium_capabilities
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
