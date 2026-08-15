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
  get_features        - optional feature modules and registered capabilities
  get_offline_evidence_example_tool - load an offline evidence example
  create_local_demo_pack_tool - create local demo pack artifact
  run_local_cli_smoke_tool - run no-server local CLI smoke evidence
  verify_local_demo_pack_bundle_tool - verify a local demo pack ZIP manifest
  verify_local_cli_smoke_bundle_tool - verify a local CLI smoke ZIP manifest
  search_evidence_vault_tool - search local evidence vault records
  get_evidence_vault_record_tool - inspect one local evidence vault record
  read_evidence_vault_file_tool - read one safe text file from local evidence vault
  copy_evidence_vault_file_tool - copy one local evidence vault artifact to a path
  verify_evidence_vault_demo_pack_bundle_tool - verify a vault-stored demo pack ZIP
  verify_evidence_vault_smoke_bundle_tool - verify a vault-stored local CLI smoke ZIP
  search_case_memory_tool - search local evidence vault memories
  diff_case_memory_tool - compare saved Case Memory KPI artifacts
  get_kpi_recipe_tool - load one built-in KPI extraction recipe
  diagnose_solver_logs_tool - diagnose supplied Abaqus log text
  run_simulation_diff_tool - compare supplied KPI dictionaries
  get_solver_doctor_patterns_tool - list Solver Doctor diagnostic patterns

Resources:
  benchmark://cases    - benchmark case definitions
  features://capabilities - optional feature modules and capabilities
  evidence://examples  - offline evidence example gallery
  evidence-vault://entries - local evidence vault records
  case-memory://vault  - local evidence vault memory entries
  kpi-recipes://examples - built-in ODB Lens KPI recipes
  simdiff://example     - built-in Simulation Diff example payload
  doctor-patterns://catalog - Solver Doctor diagnostic pattern catalog

Run:
  python mcp_server.py
"""

from __future__ import annotations

import asyncio
import base64
import json
import shutil
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any

import yaml
from mcp.server.fastmcp import FastMCP

sys.path.insert(0, str(Path(__file__).parent))

from capsule.store import init_from_inp
from case_memory import (
    CaseMemoryQuery,
    render_memory_markdown,
)
from case_memory import (
    search_case_memory as search_run_case_memory,
)
from contracts import evaluate_contracts
from core.helpers import CASES_DIR, check_abaqus, list_cases, make_run_id
from core.pipeline import (
    run_benchmark_async,
    run_pipeline,
)
from core.spec_generator import generate_spec_async
from doctor import diagnose_logs
from doctor.cae_errors import diagnose_cae_traceback
from doctor.solver_doctor import diagnose_log_texts, list_doctor_patterns, render_markdown
from evidence.case_memory import search_case_memory
from evidence.case_memory_diff import collect_case_memory_diff
from evidence.examples import get_example, list_examples
from evidence.offline import collect_evidence_from_values, validate_run_id
from evidence.vault import (
    create_vault_entry,
    get_vault_file_path,
    get_vault_record,
    list_vault_entries,
)
from post.kpi_recipes import get_kpi_recipe, list_kpi_recipes
from reporting import build_offline_report_pdf, build_offline_run_report
from scripts.run_local_cli_smoke import collect_local_cli_smoke
from scripts.run_local_demo_pack import create_local_demo_pack
from scripts.verify_local_cli_smoke_bundle import verify_smoke_bundle
from scripts.verify_local_demo_pack_bundle import verify_demo_pack_bundle
from simdiff import diff_runs, render_run_markdown
from simdiff.service import collect_kpi_diff, validate_diff_id
from tools.schema_validator import validate_spec
from validation import render_preflight_markdown, run_environment_preflight

# ── MCP Server ────────────────────────────────────────────────────

mcp = FastMCP(
    "abaqus-agent",
    instructions=(
        "Local Simulation QA and regression framework for Abaqus FEA: "
        "validate specs, run local evidence workflows, inspect benchmark cases, "
        "and expose dry-run/mock-real/real-runtime boundaries."
    ),
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
    abaqus_release: str = "",   # empty = probe the installed solver
    llm_backend: str = "template",
    anthropic_key: str = "",
    openai_key: str = "",
) -> str:
    from tools.abaqus_cmd import detect_abaqus_release
    abaqus_release = abaqus_release or detect_abaqus_release() or "unknown"
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
        return json.dumps(
            {
                "source": source,
                "template": template,
                "format": "pdf",
                "bytes": len(content),
                "content_base64": base64.b64encode(content).decode("ascii"),
            },
            ensure_ascii=False,
        )
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
    geometry_type: str = "",
    solver: str = "",
    material_name: str = "",
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
        result = search_run_case_memory(
            CaseMemoryQuery(
                roots=tuple(roots),
                query=query,
                match_mode=match_mode,
                similar_to=similar_to or None,
                status=status,
                model_name=model_name,
                geometry_type=geometry_type,
                solver=solver,
                material_name=material_name,
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
            )
        )
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


@mcp.tool(description="Run offline KPI contract/diff/capsule evidence workflow")
async def run_offline_evidence_tool(
    baseline_kpis: dict[str, Any],
    candidate_kpis: dict[str, Any],
    contracts: list[dict[str, Any]],
    run_id: str = "offline-evidence",
    input_path: str = "",
    input_metadata: str = "{}",
) -> str:
    try:
        safe_run_id = validate_run_id(run_id)
        metadata = json.loads(input_metadata or "{}")
        if not isinstance(metadata, dict):
            metadata = {}
        input_paths = []
        if input_path:
            path = Path(input_path).expanduser()
            if not path.exists() or not path.is_file():
                return json.dumps({"error": f"Input path not found: {input_path}"})
            input_paths.append(path)
        out_dir = Path(tempfile.mkdtemp(prefix=f"abaqus-agent-offline-{safe_run_id}."))
        evidence = collect_evidence_from_values(
            baseline_kpis=baseline_kpis,
            candidate_kpis=candidate_kpis,
            contracts=contracts,
            out_dir=out_dir,
            run_id=safe_run_id,
            input_paths=input_paths,
            input_metadata=metadata,
        )
        report_path = out_dir / "evidence.md"
        html_path = out_dir / "evidence.html"
        return json.dumps({
            "run_id": evidence["run_id"],
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
            "evidence_path": str(out_dir / "evidence.json"),
            "report_path": str(report_path),
            "html_path": str(html_path),
            "report_markdown": report_path.read_text(encoding="utf-8"),
        }, ensure_ascii=False)
    except (FileNotFoundError, ValueError) as exc:
        return json.dumps({"error": str(exc)})


@mcp.tool(description="Load one built-in offline evidence example payload")
async def get_offline_evidence_example_tool(case_name: str) -> str:
    try:
        return json.dumps(get_example(case_name), ensure_ascii=False)
    except KeyError as exc:
        return json.dumps({"error": str(exc)})


@mcp.tool(description="Create a local offline demo pack ZIP without invoking Abaqus")
async def create_local_demo_pack_tool(out_dir: str = "") -> str:
    try:
        if out_dir:
            out_path = Path(out_dir).expanduser()
        else:
            out_path = Path(tempfile.mkdtemp(prefix="abaqus-agent-mcp-demo-pack."))
        index = create_local_demo_pack(out_path)
        index_markdown_path = out_path / "index.md"
        index_html_path = out_path / "index.html"
        return json.dumps(
            {
                "overall_status": index["overall_status"],
                "real_env_verified": index["real_env_verified"],
                "index": index,
                "index_path": str(out_path / "index.json"),
                "index_markdown_path": str(index_markdown_path),
                "index_markdown": index_markdown_path.read_text(encoding="utf-8"),
                "index_html_path": str(index_html_path),
                "index_html": index_html_path.read_text(encoding="utf-8"),
                "pack_zip_path": index["pack_zip_path"],
            },
            ensure_ascii=False,
        )
    except OSError as exc:
        return json.dumps({"error": str(exc)})


@mcp.tool(description="Run the no-server local CLI smoke and write JSON/Markdown/HTML evidence")
async def run_local_cli_smoke_tool(out_dir: str = "") -> str:
    try:
        if out_dir:
            out_path = Path(out_dir).expanduser()
        else:
            out_path = Path(tempfile.mkdtemp(prefix="abaqus-agent-mcp-cli-smoke."))
        report = collect_local_cli_smoke(out_path)
        markdown_path = Path(report["markdown_path"])
        html_path = Path(report["html_path"])
        return json.dumps(
            {
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
                "zip_path": report["zip_path"],
                "smoke_vault_files": report["smoke_vault_files"],
                "report_markdown": markdown_path.read_text(encoding="utf-8"),
                "report_html": html_path.read_text(encoding="utf-8"),
            },
            ensure_ascii=False,
        )
    except OSError as exc:
        return json.dumps({"error": str(exc)})


@mcp.tool(description="Verify a local CLI smoke ZIP bundle against its embedded manifest")
async def verify_local_cli_smoke_bundle_tool(zip_path: str) -> str:
    try:
        return json.dumps(verify_smoke_bundle(Path(zip_path).expanduser()), ensure_ascii=False)
    except OSError as exc:
        return json.dumps({"error": str(exc), "zip_path": zip_path})


@mcp.tool(description="Verify a local demo pack ZIP bundle against its embedded manifest")
async def verify_local_demo_pack_bundle_tool(zip_path: str) -> str:
    try:
        return json.dumps(verify_demo_pack_bundle(Path(zip_path).expanduser()), ensure_ascii=False)
    except OSError as exc:
        return json.dumps({"error": str(exc), "zip_path": zip_path})


@mcp.tool(description="Verify a vault-stored local CLI smoke ZIP bundle by vault id")
async def verify_evidence_vault_smoke_bundle_tool(
    vault_id: str,
    filename: str = "local_cli_smoke.zip",
    vault_root: str = "",
) -> str:
    try:
        source = get_vault_file_path(vault_id, filename, root=vault_root or None)
        data = verify_smoke_bundle(source)
        data["vault_id"] = vault_id
        data["filename"] = filename
        data["vault_root"] = vault_root
        data["source_path"] = str(source)
        return json.dumps(data, ensure_ascii=False)
    except (FileNotFoundError, ValueError, OSError) as exc:
        return json.dumps({
            "error": str(exc),
            "vault_id": vault_id,
            "filename": filename,
            "vault_root": vault_root,
        })


@mcp.tool(description="Verify a vault-stored local demo pack ZIP bundle by vault id")
async def verify_evidence_vault_demo_pack_bundle_tool(
    vault_id: str,
    filename: str = "local-demo-pack.zip",
    vault_root: str = "",
) -> str:
    try:
        source = get_vault_file_path(vault_id, filename, root=vault_root or None)
        data = verify_demo_pack_bundle(source)
        data["vault_id"] = vault_id
        data["filename"] = filename
        data["vault_root"] = vault_root
        data["source_path"] = str(source)
        return json.dumps(data, ensure_ascii=False)
    except (FileNotFoundError, ValueError, OSError) as exc:
        return json.dumps({
            "error": str(exc),
            "vault_id": vault_id,
            "filename": filename,
            "vault_root": vault_root,
        })


@mcp.tool(description="Search persisted local Evidence Vault records")
async def search_evidence_vault_tool(
    query: str = "",
    kind: str = "",
    status: str = "",
    limit: int = 20,
) -> str:
    return json.dumps(
        _with_vault_urls(
            list_vault_entries(
                query=query,
                kind=kind,
                status=status,
                limit=limit,
            )
        ),
        ensure_ascii=False,
    )


@mcp.tool(description="Inspect one persisted local Evidence Vault record")
async def get_evidence_vault_record_tool(vault_id: str) -> str:
    try:
        return json.dumps(
            _with_vault_urls({"item": get_vault_record(vault_id)})["item"],
            ensure_ascii=False,
        )
    except (FileNotFoundError, ValueError) as exc:
        return json.dumps({"error": str(exc)})


@mcp.tool(description="Read one safe text artifact from a persisted local Evidence Vault record")
async def read_evidence_vault_file_tool(
    vault_id: str,
    filename: str,
    max_chars: int = 20000,
) -> str:
    try:
        path = get_vault_file_path(vault_id, filename)
        if path.suffix not in {".json", ".md", ".html"}:
            return json.dumps({
                "error": f"Unsupported text vault file type: {filename}",
                "vault_id": vault_id,
                "filename": filename,
                "size_bytes": path.stat().st_size,
            })
        safe_max_chars = max(1, min(max_chars, 50000))
        content = path.read_text(encoding="utf-8")
        return json.dumps(
            {
                "vault_id": vault_id,
                "filename": filename,
                "vault_url": f"evidence-vault://entries/{vault_id}/{filename}",
                "size_bytes": path.stat().st_size,
                "truncated": len(content) > safe_max_chars,
                "content": content[:safe_max_chars],
            },
            ensure_ascii=False,
        )
    except (FileNotFoundError, UnicodeDecodeError, ValueError) as exc:
        return json.dumps({"error": str(exc), "vault_id": vault_id, "filename": filename})


@mcp.tool(description="Copy one local Evidence Vault artifact to a requested path")
async def copy_evidence_vault_file_tool(
    vault_id: str,
    filename: str,
    out_path: str,
) -> str:
    try:
        source = get_vault_file_path(vault_id, filename)
        target = Path(out_path).expanduser()
        if target.exists() and target.is_dir():
            target = target / Path(filename).name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        return json.dumps(
            {
                "vault_id": vault_id,
                "filename": filename,
                "source_path": str(source),
                "output_path": str(target),
                "size_bytes": target.stat().st_size,
            },
            ensure_ascii=False,
        )
    except (FileNotFoundError, ValueError, OSError) as exc:
        return json.dumps({"error": str(exc), "vault_id": vault_id, "filename": filename})


@mcp.tool(description="Search local Case Memory entries backed by the evidence vault")
async def search_case_memory_tool(
    query: str = "",
    kind: str = "",
    status: str = "",
    limit: int = 20,
) -> str:
    return json.dumps(
        search_case_memory(
            query=query,
            kind=kind,
            status=status,
            limit=limit,
            url_prefix="case-memory://vault",
        ),
        ensure_ascii=False,
    )


@mcp.tool(description="Compare two saved Case Memory KPI artifacts without invoking Abaqus")
async def diff_case_memory_tool(
    baseline_vault_id: str,
    candidate_vault_id: str,
    diff_id: str = "case-memory-diff",
    baseline_filename: str | None = None,
    candidate_filename: str | None = None,
    persist_to_vault: bool = True,
) -> str:
    try:
        safe_diff_id = validate_diff_id(diff_id)
        out_dir = Path(tempfile.mkdtemp(prefix=f"abaqus-agent-case-memory-diff-{safe_diff_id}."))
        result = collect_case_memory_diff(
            baseline_vault_id=baseline_vault_id,
            candidate_vault_id=candidate_vault_id,
            out_dir=out_dir,
            diff_id=safe_diff_id,
            baseline_filename=baseline_filename,
            candidate_filename=candidate_filename,
        )
        report_path = out_dir / "diff.md"
        response = {
            "diff_id": result["diff_id"],
            "overall_status": result["overall_status"],
            "real_env_verified": result["real_env_verified"],
            "diff": result["diff"],
            "case_memory_diff": result["case_memory_diff"],
            "diff_path": str(out_dir / "diff.json"),
            "report_path": str(report_path),
            "report_markdown": report_path.read_text(encoding="utf-8"),
        }
        if persist_to_vault:
            record = create_vault_entry(
                kind="case-memory-diff",
                title=safe_diff_id,
                files={"diff.json": out_dir / "diff.json", "diff.md": report_path},
                summary={
                    "overall_status": result["overall_status"],
                    "diff_status": result["diff"]["status"],
                    "changed_count": result["diff"]["changed_count"],
                    "added_count": result["diff"]["added_count"],
                    "removed_count": result["diff"]["removed_count"],
                    "baseline_vault_id": baseline_vault_id,
                    "candidate_vault_id": candidate_vault_id,
                    "baseline_filename": baseline_filename or "",
                    "candidate_filename": candidate_filename or "",
                    "real_env_verified": result["real_env_verified"],
                },
            )
            response["vault_id"] = record["vault_id"]
            response["vault_urls"] = {
                filename: f"case-memory://vault/{record['vault_id']}/{filename}"
                for filename in record["files"]
            }
        return json.dumps(response, ensure_ascii=False)
    except (OSError, ValueError) as exc:
        return json.dumps({"error": str(exc)})


@mcp.tool(description="Load one built-in ODB Lens KPI extraction recipe")
async def get_kpi_recipe_tool(recipe_id: str) -> str:
    try:
        return json.dumps(get_kpi_recipe(recipe_id), ensure_ascii=False)
    except KeyError as exc:
        return json.dumps({"error": str(exc)})


@mcp.tool(description="Diagnose supplied Abaqus .msg/.dat/.sta/.log text without invoking Abaqus")
async def diagnose_solver_logs_tool(
    job_name: str = "Job-1",
    msg_text: str = "",
    dat_text: str = "",
    sta_text: str = "",
    log_text: str = "",
) -> str:
    try:
        report = diagnose_log_texts(
            job_name=job_name,
            logs={
                ".msg": msg_text,
                ".dat": dat_text,
                ".sta": sta_text,
                ".log": log_text,
            },
        )
    except ValueError as exc:
        return json.dumps({"error": str(exc)})
    return json.dumps(
        {
            "job_name": report.job_name,
            "status": report.status,
            "primary_category": report.primary_category,
            "summary": report.summary,
            "completed": report.completed,
            "finding_count": len(report.findings),
            "report": report.to_dict(),
            "report_markdown": render_markdown(report),
            "real_env_verified": False,
        },
        ensure_ascii=False,
    )


@mcp.tool(description="Compare supplied baseline/candidate KPI dictionaries without invoking Abaqus")
async def run_simulation_diff_tool(
    baseline_kpis: dict[str, Any],
    candidate_kpis: dict[str, Any],
    tolerances: dict[str, dict[str, float]] | None = None,
    diff_id: str = "simulation-diff",
    input_metadata: str = "{}",
) -> str:
    try:
        safe_diff_id = validate_diff_id(diff_id)
        metadata = json.loads(input_metadata or "{}")
        if not isinstance(metadata, dict):
            metadata = {}
        out_dir = Path(tempfile.mkdtemp(prefix=f"abaqus-agent-simdiff-{safe_diff_id}."))
        result = collect_kpi_diff(
            baseline_kpis=baseline_kpis,
            candidate_kpis=candidate_kpis,
            tolerances=tolerances or {},
            out_dir=out_dir,
            diff_id=safe_diff_id,
            input_metadata=metadata,
        )
        report_path = out_dir / "diff.md"
        return json.dumps(
            {
                "diff_id": result["diff_id"],
                "overall_status": result["overall_status"],
                "real_env_verified": result["real_env_verified"],
                "diff": result["diff"],
                "diff_path": str(out_dir / "diff.json"),
                "report_path": str(report_path),
                "report_markdown": report_path.read_text(encoding="utf-8"),
            },
            ensure_ascii=False,
        )
    except (OSError, ValueError) as exc:
        return json.dumps({"error": str(exc)})


@mcp.tool(description="List supported Solver Doctor diagnostic categories and parser patterns")
async def get_solver_doctor_patterns_tool(
    category: str = "",
    severity: str = "",
) -> str:
    return json.dumps(
        list_doctor_patterns(category=category, severity=severity),
        ensure_ascii=False,
    )


@mcp.tool(
    description=(
        "Diagnose an Abaqus/CAE Python traceback in plain language "
        "(15 known CAE failure patterns: stale locks, missing objects, license, "
        "geometry selection, aborted jobs, ...). Returns title/explanation/suggestion."
    )
)
async def diagnose_cae_error_tool(traceback_text: str) -> str:
    text = (traceback_text or "").strip()
    if not text:
        return json.dumps({"error": "traceback_text is required"}, ensure_ascii=False)
    return json.dumps(diagnose_cae_traceback(text[:20000]), ensure_ascii=False)


@mcp.tool(description="Health check — returns server status and solver availability")
async def health_check() -> str:
    # An MCP client deciding whether to propose a solve needs to know it may
    # land on the reduced CalculiX subset, not just that "a solver exists".
    from core.backends import backend_label, check_calculix, select_backend

    decision = select_backend({})
    return json.dumps({
        "status": "ok",
        "abaqus_available": check_abaqus(),
        "calculix_available": check_calculix(),
        "solver_backend": decision.backend,
        "solver_label": backend_label(decision.backend, decision.version),
        "cases": list_cases(),
        "version": "0.1.0",
        "transport": "mcp",
    })


@mcp.tool(description="List the optional feature modules and their registered capabilities")
async def get_features() -> str:
    from features.feature_registry import list_capabilities, list_feature_modules
    return json.dumps({
        "features": list_feature_modules(),
        "capabilities": list_capabilities(),
    })


def _with_vault_urls(data: dict[str, Any]) -> dict[str, Any]:
    def attach(record: dict[str, Any]) -> dict[str, Any]:
        record["vault_urls"] = {
            filename: f"evidence-vault://entries/{record['vault_id']}/{filename}"
            for filename in record.get("files", {})
        }
        return record

    if "items" in data:
        for item in data["items"]:
            attach(item)
    if "item" in data:
        attach(data["item"])
    return data


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


@mcp.resource("features://capabilities", description="Optional feature modules and registered capabilities")
async def get_features_resource() -> str:
    from features.feature_registry import list_capabilities, list_feature_modules
    return json.dumps({
        "features": list_feature_modules(),
        "capabilities": list_capabilities(),
    })


@mcp.resource("evidence://examples", description="Offline evidence example gallery")
async def get_offline_evidence_examples_resource() -> str:
    return json.dumps(list_examples(), ensure_ascii=False)


@mcp.resource("evidence-vault://entries", description="Local evidence vault records")
async def get_evidence_vault_resource() -> str:
    return json.dumps(
        _with_vault_urls(list_vault_entries(limit=20)),
        ensure_ascii=False,
    )


@mcp.resource("case-memory://vault", description="Local evidence vault Case Memory")
async def get_case_memory_resource() -> str:
    return json.dumps(
        search_case_memory(url_prefix="case-memory://vault"),
        ensure_ascii=False,
    )


@mcp.resource("kpi-recipes://examples", description="Built-in ODB Lens KPI recipes")
async def get_kpi_recipes_resource() -> str:
    return json.dumps(list_kpi_recipes(), ensure_ascii=False)


@mcp.resource("simdiff://example", description="Built-in Simulation Diff example payload")
async def get_simulation_diff_example_resource() -> str:
    return json.dumps(
        {
            "diff_id": "cantilever-simdiff-example",
            "baseline_kpis": {"U_tip_y": -2.10, "max_mises": 120.0, "reaction_sum": 0.0},
            "candidate_kpis": {"U_tip_y": -2.14, "max_mises": 121.5, "reaction_sum": 0.002},
            "tolerances": {
                "U_tip_y": {"rtol": 0.05},
                "max_mises": {"rtol": 0.02},
                "reaction_sum": {"atol": 0.01},
            },
            "real_env_verified": False,
        },
        ensure_ascii=False,
    )


@mcp.resource("doctor-patterns://catalog", description="Solver Doctor diagnostic pattern catalog")
async def get_solver_doctor_patterns_resource() -> str:
    return json.dumps(list_doctor_patterns(), ensure_ascii=False)


# ── Main ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    mcp.run(transport="stdio")
