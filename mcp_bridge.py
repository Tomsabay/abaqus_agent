"""
mcp_bridge.py
-------------
HTTP/SSE bridge between browser and MCP server.

Spawns mcp_server.py as a subprocess communicating via JSON-RPC 2.0
over stdin/stdout. Exposes the same REST API shape as server.py so
the frontend needs minimal changes — just point to port 8001/mcp.

Endpoints mirror server.py under /mcp prefix:
  POST /mcp/api/spec/generate    → tools/call generate_spec
  POST /mcp/api/spec/validate    → tools/call validate_spec_tool
  POST /mcp/api/run/start        → tools/call start_run
  GET  /mcp/api/run/{run_id}     → tools/call get_run_status
  GET  /mcp/api/run/{run_id}/stream → SSE polling get_run_status
  GET  /mcp/api/benchmark        → resources/read benchmark://cases
  POST /mcp/api/benchmark/run    → tools/call run_benchmark_tool
  GET  /mcp/health               → tools/call health_check
  GET  /mcp/api/features         → tools/call get_features

Run:
  python mcp_bridge.py
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sys
import tempfile
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncGenerator

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from doctor.solver_doctor import diagnose_log_texts, list_doctor_patterns, render_markdown
from evidence.artifact_registry import ArtifactNotFound, EvidenceArtifactRegistry
from evidence.case_memory import search_case_memory
from evidence.demo_gallery import collect_demo_gallery
from evidence.examples import get_example, list_examples
from evidence.vault import (
    get_vault_file_path,
    get_vault_record,
    list_vault_entries,
)
from post.kpi_recipes import get_kpi_recipe, list_kpi_recipes
from reporting import (
    build_offline_report_bundle,
    build_offline_report_pdf,
    build_offline_run_report,
)
from scripts.run_local_demo_pack import collect_demo_pack_vault_files, create_local_demo_pack
from simdiff.service import validate_diff_id

FRONTEND_DIR = Path(__file__).parent / "frontend"


# ── MCP Subprocess Connection ─────────────────────────────────────

class MCPConnection:
    """Manages communication with mcp_server.py subprocess via JSON-RPC."""

    def __init__(self):
        self.process: asyncio.subprocess.Process | None = None
        self._request_id = 0
        self._pending: dict[int, asyncio.Future] = {}
        self._read_task: asyncio.Task | None = None
        self._initialized = False

    async def start(self):
        """Start the MCP server subprocess."""
        self.process = await asyncio.create_subprocess_exec(
            sys.executable, str(Path(__file__).parent / "mcp_server.py"),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        self._read_task = asyncio.create_task(self._read_loop())
        await self._initialize()

    async def _initialize(self):
        """Send MCP initialize handshake."""
        result = await self._send_request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "abaqus-bridge", "version": "0.1.0"},
        })
        # Send initialized notification
        await self._send_notification("notifications/initialized", {})
        self._initialized = True
        return result

    async def _read_loop(self):
        """Read JSON-RPC messages from MCP server stdout."""
        assert self.process and self.process.stdout
        while True:
            try:
                line = await self.process.stdout.readline()
                if not line:
                    break
                text = line.decode("utf-8").strip()
                if not text:
                    continue
                try:
                    msg = json.loads(text)
                except json.JSONDecodeError:
                    continue

                # Route responses to pending futures
                msg_id = msg.get("id")
                if msg_id is not None and msg_id in self._pending:
                    future = self._pending.pop(msg_id)
                    if not future.done():
                        if "error" in msg:
                            future.set_exception(
                                Exception(msg["error"].get("message", "MCP error"))
                            )
                        else:
                            future.set_result(msg.get("result"))
            except asyncio.CancelledError:
                break
            except Exception:
                continue

    async def _send_request(self, method: str, params: dict) -> dict:
        """Send a JSON-RPC request and await response."""
        assert self.process and self.process.stdin
        self._request_id += 1
        req_id = self._request_id
        msg = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
            "params": params,
        }
        future: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending[req_id] = future
        data = json.dumps(msg) + "\n"
        self.process.stdin.write(data.encode("utf-8"))
        await self.process.stdin.drain()
        try:
            result = await asyncio.wait_for(future, timeout=60)
            return result
        except asyncio.TimeoutError:
            self._pending.pop(req_id, None)
            raise Exception("MCP request timed out")

    async def _send_notification(self, method: str, params: dict):
        """Send a JSON-RPC notification (no response expected)."""
        assert self.process and self.process.stdin
        msg = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
        }
        data = json.dumps(msg) + "\n"
        self.process.stdin.write(data.encode("utf-8"))
        await self.process.stdin.drain()

    async def call_tool(self, tool_name: str, arguments: dict) -> dict:
        """Call an MCP tool and return the parsed result."""
        result = await self._send_request("tools/call", {
            "name": tool_name,
            "arguments": arguments,
        })
        # MCP tools return content array; extract text
        if isinstance(result, dict) and "content" in result:
            for item in result["content"]:
                if item.get("type") == "text":
                    try:
                        return json.loads(item["text"])
                    except json.JSONDecodeError:
                        return {"raw": item["text"]}
        return result or {}

    async def read_resource(self, uri: str) -> dict:
        """Read an MCP resource."""
        result = await self._send_request("resources/read", {"uri": uri})
        if isinstance(result, dict) and "contents" in result:
            for item in result["contents"]:
                text = item.get("text", "")
                try:
                    return json.loads(text)
                except json.JSONDecodeError:
                    return {"raw": text}
        return result or {}

    async def stop(self):
        if self.process:
            self.process.terminate()
            await self.process.wait()
        if self._read_task:
            self._read_task.cancel()


mcp_conn = MCPConnection()
EVIDENCE = EvidenceArtifactRegistry("/mcp/api/evidence")
# Same two dicts the registry keeps, under the names they have always had here.
EVIDENCE_ARTIFACTS = EVIDENCE.artifacts
DEMO_GALLERY_ARTIFACTS = EVIDENCE.demo_galleries


# ── Lifecycle ─────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    await mcp_conn.start()
    try:
        yield
    finally:
        await mcp_conn.stop()


# ── FastAPI bridge app ────────────────────────────────────────────

app = FastAPI(
    title="Abaqus Agent MCP Bridge",
    version="0.1.0",
    description=(
        "HTTP/SSE bridge to the Abaqus Agent MCP server for Local Simulation QA "
        "evidence workflows, exposing dry-run/mock-real/real-runtime boundaries "
        "to browser clients."
    ),
    lifespan=lifespan,
)

# Same rule as server.py: cross-origin access is opt-in, not the default.
# `allow_origins=["*"]` on a service with no authentication that can launch
# solver jobs meant any page in the browser could drive it.
_cors_origins = [
    o.strip() for o in os.environ.get("ABAQUS_AGENT_CORS_ORIGINS", "").split(",")
    if o.strip()
]
if _cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


# ── Request models ────────────────────────────────────────────────

class GenerateSpecRequest(BaseModel):
    text: str
    # Empty = let the MCP tool probe the installed solver (never assume a year).
    abaqus_release: str = ""
    llm_backend: str = "template"
    anthropic_key: str = ""
    openai_key: str = ""

class ValidateSpecRequest(BaseModel):
    spec_yaml: str

class StartRunRequest(BaseModel):
    spec_yaml: str
    runner_cfg: dict = Field(default_factory=dict)

class DoctorRequest(BaseModel):
    paths: list[str] = Field(default_factory=list)
    text: str = ""

class DiffRequest(BaseModel):
    baseline: str
    candidate: str
    rtol: float = 0.05
    tolerances: dict = Field(default_factory=dict)

class MemorySearchRequest(BaseModel):
    roots: list[str]
    query: str = ""
    match_mode: str = "any"
    similar_to: str = ""
    status: str = ""
    model_name: str = ""
    geometry_type: str = ""
    solver: str = ""
    material_name: str = ""
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
    workdir: str = ""
    runner_cfg: dict = Field(default_factory=dict)

class OfflineReportRequest(BaseModel):
    source: str
    template: str = "standard"
    max_artifact_bytes: int = 25_000_000

class OfflineEvidenceRequest(BaseModel):
    baseline_kpis: dict[str, Any]
    candidate_kpis: dict[str, Any]
    contracts: list[dict[str, Any]]
    run_id: str = "offline-evidence"
    input_path: str = ""
    input_metadata: dict[str, Any] = Field(default_factory=dict)

class SimulationDiffRequest(BaseModel):
    baseline_kpis: dict[str, Any]
    candidate_kpis: dict[str, Any]
    tolerances: dict[str, dict[str, float]] = Field(default_factory=dict)
    diff_id: str = "simulation-diff"
    input_metadata: dict[str, Any] = Field(default_factory=dict)

class CaseMemoryDiffRequest(BaseModel):
    baseline_vault_id: str
    candidate_vault_id: str
    diff_id: str = "case-memory-diff"
    baseline_filename: str | None = None
    candidate_filename: str | None = None

class VaultSmokeVerifyRequest(BaseModel):
    filename: str = "local_cli_smoke.zip"
    vault_root: str = ""

class VaultDemoPackVerifyRequest(BaseModel):
    filename: str = "local-demo-pack.zip"
    vault_root: str = ""

class DoctorDiagnoseRequest(BaseModel):
    job_name: str = "Job-1"
    msg_text: str = ""
    dat_text: str = ""
    sta_text: str = ""
    log_text: str = ""


# ── Bridge endpoints ──────────────────────────────────────────────

@app.get("/")
def root():
    index = FRONTEND_DIR / "index.html"
    if index.exists():
        return FileResponse(str(index))
    return {"status": "ok", "message": "Abaqus Agent MCP Bridge running"}


@app.get("/mcp/health")
async def bridge_health():
    try:
        return await mcp_conn.call_tool("health_check", {})
    except Exception as e:
        return {"status": "error", "detail": str(e)}


@app.post("/mcp/api/doctor")
async def bridge_doctor(req: DoctorRequest):
    try:
        return await mcp_conn.call_tool(
            "diagnose_logs_tool",
            {"paths_json": json.dumps(req.paths), "text": req.text},
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/mcp/api/diff")
async def bridge_diff(req: DiffRequest):
    try:
        return await mcp_conn.call_tool(
            "simulation_diff_tool",
            {
                "baseline": req.baseline,
                "candidate": req.candidate,
                "rtol": req.rtol,
                "tolerances_json": json.dumps(req.tolerances),
            },
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/mcp/api/memory/search")
async def bridge_memory_search(req: MemorySearchRequest):
    try:
        return await mcp_conn.call_tool(
            "case_memory_search_tool",
            {
                "roots_json": json.dumps(req.roots),
                "query": req.query,
                "match_mode": req.match_mode,
                "similar_to": req.similar_to,
                "status": req.status,
                "model_name": req.model_name,
                "geometry_type": req.geometry_type,
                "solver": req.solver,
                "material_name": req.material_name,
                "contract": req.contract,
                "contracts_passed": req.contracts_passed,
                "diagnosis_id": req.diagnosis_id,
                "kpi": req.kpi,
                "artifact": req.artifact,
                "limit": req.limit,
                "include_artifacts": req.include_artifacts,
                "sort_by": req.sort_by,
                "sort_order": req.sort_order,
                "min_score": req.min_score,
            },
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/mcp/api/validate/env")
async def bridge_environment_preflight(req: EnvironmentPreflightRequest):
    try:
        return await mcp_conn.call_tool(
            "environment_preflight_tool",
            {
                "abaqus_cmd": req.abaqus_cmd,
                "timeout_seconds": req.timeout_seconds,
                "check_release": req.check_release,
                "expected_release": req.expected_release,
                "workdir": req.workdir,
                "runner_cfg_json": json.dumps(req.runner_cfg),
            },
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/mcp/api/report/export")
async def bridge_offline_report_export(req: OfflineReportRequest):
    try:
        return await mcp_conn.call_tool(
            "offline_report_export_tool",
            {"source": req.source, "template": req.template},
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/mcp/api/report/export.zip")
async def bridge_offline_report_export_bundle(req: OfflineReportRequest):
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
    return Response(
        content=content,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="abaqus-report-{run_id}.zip"'},
    )


@app.post("/mcp/api/report/export.pdf")
async def bridge_offline_report_export_pdf(req: OfflineReportRequest):
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


@app.post("/mcp/api/spec/generate")
async def bridge_generate_spec(req: GenerateSpecRequest):
    try:
        return await mcp_conn.call_tool("generate_spec", {
            "text": req.text,
            "abaqus_release": req.abaqus_release,
            "llm_backend": req.llm_backend,
            "anthropic_key": req.anthropic_key,
            "openai_key": req.openai_key,
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/mcp/api/spec/validate")
async def bridge_validate_spec(req: ValidateSpecRequest):
    try:
        return await mcp_conn.call_tool("validate_spec_tool", {
            "spec_yaml": req.spec_yaml,
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/mcp/api/run/start")
async def bridge_start_run(req: StartRunRequest):
    try:
        return await mcp_conn.call_tool("start_run", {
            "spec_yaml": req.spec_yaml,
            "runner_cfg": json.dumps(req.runner_cfg),
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/mcp/api/run/{run_id}")
async def bridge_get_run(run_id: str):
    try:
        return await mcp_conn.call_tool("get_run_status", {"run_id": run_id})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/mcp/api/run/{run_id}/stream")
async def bridge_stream_run(run_id: str):
    """
    SSE stream — polls the MCP server's get_run_status tool
    and pushes updates when state changes (same format as server.py).
    """
    async def event_gen() -> AsyncGenerator[str, None]:
        last_status = None
        last_stages_hash = None
        timeout = 300
        t0 = time.time()

        while time.time() - t0 < timeout:
            try:
                run = await mcp_conn.call_tool("get_run_status", {"run_id": run_id})
            except Exception:
                break

            if "error" in run:
                yield f"data: {json.dumps({'error': run['error']})}\n\n"
                break

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
                    "elapsed": run.get("elapsed", 0),
                }
                yield f"data: {json.dumps(payload)}\n\n"
                last_status = cur_status
                last_stages_hash = stages_hash

            if cur_status in ("COMPLETED", "FAILED", "ABORTED"):
                yield "data: {\"event\": \"done\"}\n\n"
                break

            await asyncio.sleep(0.3)

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/mcp/api/benchmark")
async def bridge_get_benchmark():
    try:
        return await mcp_conn.read_resource("benchmark://cases")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/mcp/api/benchmark/run")
async def bridge_run_benchmark(dry_run: bool = True):
    try:
        return await mcp_conn.call_tool("run_benchmark_tool", {"dry_run": dry_run})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/mcp/api/evidence/offline")
async def bridge_offline_evidence(req: OfflineEvidenceRequest):
    try:
        result = await mcp_conn.call_tool(
            "run_offline_evidence_tool",
            {
                "baseline_kpis": req.baseline_kpis,
                "candidate_kpis": req.candidate_kpis,
                "contracts": req.contracts,
                "run_id": req.run_id,
                "input_path": req.input_path,
                "input_metadata": json.dumps(req.input_metadata),
            },
        )
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        result.update(
            EVIDENCE.register_evidence(
                run_id=result["run_id"],
                evidence=result,
                evidence_path=Path(result["evidence_path"]),
                report_path=Path(result["report_path"]),
                html_path=Path(result["html_path"]),
                capsule_manifest_path=Path(result["capsule"]["manifest_path"]),
            )
        )
        artifact_files = EVIDENCE.evidence_files(result["artifact_id"])
        result.update(
            EVIDENCE.create_vault_entry(
                kind="offline-evidence",
                title=result["run_id"],
                files={
                    "evidence.json": artifact_files["evidence.json"],
                    "evidence.md": artifact_files["evidence.md"],
                    "evidence.html": artifact_files["evidence.html"],
                    "capsule.json": artifact_files["capsule.json"],
                    "bundle.zip": artifact_files["bundle.zip"],
                },
                summary={
                    "overall_status": result["overall_status"],
                    "real_env_verified": result["real_env_verified"],
                    "contracts_status": result["contracts"]["status"],
                    "diff_status": result["diff"]["status"],
                },
            )
        )
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/mcp/api/evidence/examples")
async def bridge_list_offline_evidence_examples():
    return list_examples()


@app.get("/mcp/api/evidence/examples/{case_name}")
async def bridge_get_offline_evidence_example(case_name: str):
    try:
        return get_example(case_name)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/mcp/api/evidence/demo-gallery")
async def bridge_create_offline_demo_gallery():
    out_dir = Path(tempfile.mkdtemp(prefix="abaqus-agent-bridge-demo-gallery."))
    index = collect_demo_gallery(out_dir)
    artifacts = EVIDENCE.register_demo_gallery(index=index, out_dir=out_dir)
    vault = EVIDENCE.create_vault_entry(
        kind="demo-gallery",
        title="offline-demo-gallery",
        files={
            "index.json": out_dir / "index.json",
            "index.md": out_dir / "index.md",
            "index.html": out_dir / "index.html",
            "offline-demo-gallery.zip": Path(index["gallery_zip_path"]),
        },
        summary={
            "overall_status": index["overall_status"],
            "case_count": index["case_count"],
        },
    )
    return {
        **artifacts["record"],
        **vault,
        "index": index,
        "index_markdown": (out_dir / "index.md").read_text(encoding="utf-8"),
        "index_html": (out_dir / "index.html").read_text(encoding="utf-8"),
        "index_html_url": vault["vault_urls"]["index.html"],
    }


@app.get("/mcp/api/evidence/demo-gallery/{artifact_id}/{filename}")
async def bridge_get_offline_demo_gallery_artifact(artifact_id: str, filename: str):
    media_types = {
        "index.json": "application/json",
        "index.md": "text/markdown; charset=utf-8",
        "index.html": "text/html; charset=utf-8",
        "offline-demo-gallery.zip": "application/zip",
    }
    if filename not in media_types:
        raise HTTPException(status_code=404, detail="Demo gallery artifact not found")
    try:
        path = EVIDENCE.demo_gallery_path(artifact_id, filename)
    except ArtifactNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return FileResponse(path, media_type=media_types[filename], filename=filename)


@app.post("/mcp/api/evidence/demo-pack")
async def bridge_create_local_demo_pack():
    out_dir = Path(tempfile.mkdtemp(prefix="abaqus-agent-bridge-local-demo-pack."))
    index = create_local_demo_pack(out_dir)
    vault = EVIDENCE.create_vault_entry(
        kind="local-demo-pack",
        title="local-demo-pack",
        files=collect_demo_pack_vault_files(index),
        summary={
            "overall_status": index["overall_status"],
            "real_env_verified": index["real_env_verified"],
            "gallery_case_count": index["offline_demo_gallery"]["case_count"],
            "doctor_status": index["solver_doctor"]["status"],
            "simulation_diff_status": index["simulation_diff"]["status"],
        },
    )
    return {
        **vault,
        "overall_status": index["overall_status"],
        "real_env_verified": index["real_env_verified"],
        "index": index,
        "index_markdown": (out_dir / "index.md").read_text(encoding="utf-8"),
        "index_html": (out_dir / "index.html").read_text(encoding="utf-8"),
        "index_html_url": vault["vault_urls"]["index.html"],
        "pack_zip_url": vault["vault_urls"]["local-demo-pack.zip"],
    }


@app.post("/mcp/api/evidence/local-cli-smoke")
async def bridge_run_local_cli_smoke():
    out_dir = Path(tempfile.mkdtemp(prefix="abaqus-agent-bridge-cli-smoke."))
    return await mcp_conn.call_tool(
        "run_local_cli_smoke_tool",
        {"out_dir": str(out_dir)},
    )


@app.get("/mcp/api/evidence/artifacts/{artifact_id}/{filename}")
async def bridge_get_offline_evidence_artifact(artifact_id: str, filename: str):
    media_types = {
        "evidence.json": "application/json",
        "capsule.json": "application/json",
        "evidence.md": "text/markdown; charset=utf-8",
        "evidence.html": "text/html; charset=utf-8",
        "bundle.zip": "application/zip",
    }
    if filename not in media_types:
        raise HTTPException(status_code=404, detail="Evidence artifact not found")
    try:
        path = EVIDENCE.evidence_path(artifact_id, filename)
    except ArtifactNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return FileResponse(path, media_type=media_types[filename], filename=filename)


@app.get("/mcp/api/evidence/artifacts")
async def bridge_list_offline_evidence_artifacts(limit: int = 20):
    return EVIDENCE.list_evidence_records(limit)


@app.get("/mcp/api/evidence/vault")
async def bridge_list_evidence_vault(
    limit: int = 50,
    query: str = "",
    kind: str = "",
    status: str = "",
):
    data = list_vault_entries(limit=limit, query=query, kind=kind, status=status)
    for item in data["items"]:
        EVIDENCE.attach_vault_urls(item)
    return data


@app.post("/mcp/api/evidence/vault/{vault_id}/verify-smoke")
async def bridge_verify_evidence_vault_smoke_bundle(
    vault_id: str,
    req: VaultSmokeVerifyRequest | None = None,
):
    payload = req or VaultSmokeVerifyRequest()
    return await mcp_conn.call_tool(
        "verify_evidence_vault_smoke_bundle_tool",
        {
            "vault_id": vault_id,
            "filename": payload.filename,
            "vault_root": payload.vault_root,
        },
    )


@app.post("/mcp/api/evidence/vault/{vault_id}/verify-demo-pack")
async def bridge_verify_evidence_vault_demo_pack_bundle(
    vault_id: str,
    req: VaultDemoPackVerifyRequest | None = None,
):
    payload = req or VaultDemoPackVerifyRequest()
    return await mcp_conn.call_tool(
        "verify_evidence_vault_demo_pack_bundle_tool",
        {
            "vault_id": vault_id,
            "filename": payload.filename,
            "vault_root": payload.vault_root,
        },
    )


@app.get("/mcp/api/evidence/vault/{vault_id}/{filename:path}")
async def bridge_get_evidence_vault_file(vault_id: str, filename: str):
    media_types = {
        ".json": "application/json",
        ".md": "text/markdown; charset=utf-8",
        ".html": "text/html; charset=utf-8",
        ".zip": "application/zip",
    }
    try:
        path = get_vault_file_path(vault_id, filename)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return FileResponse(
        path,
        media_type=media_types.get(path.suffix, "application/octet-stream"),
        filename=filename,
    )


@app.get("/mcp/api/evidence/vault/{vault_id}")
async def bridge_get_evidence_vault_record(vault_id: str):
    if Path(vault_id).suffix in {".json", ".md", ".html", ".zip"}:
        raise HTTPException(status_code=400, detail=f"Vault id is invalid: {vault_id}")
    try:
        record = get_vault_record(vault_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    EVIDENCE.attach_vault_urls(record)
    return record


@app.get("/mcp/api/case-memory")
async def bridge_list_case_memory(
    query: str = "",
    kind: str = "",
    status: str = "",
    limit: int = 50,
):
    return search_case_memory(
        query=query,
        kind=kind,
        status=status,
        limit=limit,
        url_prefix="/mcp/api/evidence/vault",
    )


@app.post("/mcp/api/case-memory/diff")
async def bridge_create_case_memory_diff(req: CaseMemoryDiffRequest):
    try:
        validate_diff_id(req.diff_id)
        result = await mcp_conn.call_tool(
            "diff_case_memory_tool",
            {
                "baseline_vault_id": req.baseline_vault_id,
                "candidate_vault_id": req.candidate_vault_id,
                "diff_id": req.diff_id,
                "baseline_filename": req.baseline_filename,
                "candidate_filename": req.candidate_filename,
                "persist_to_vault": False,
            },
        )
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        vault = EVIDENCE.create_vault_entry(
            kind="case-memory-diff",
            title=result["diff_id"],
            files={
                "diff.json": Path(result["diff_path"]),
                "diff.md": Path(result["report_path"]),
            },
            summary={
                "overall_status": result["overall_status"],
                "diff_status": result["diff"]["status"],
                "changed_count": result["diff"]["changed_count"],
                "added_count": result["diff"]["added_count"],
                "removed_count": result["diff"]["removed_count"],
                "baseline_vault_id": req.baseline_vault_id,
                "candidate_vault_id": req.candidate_vault_id,
                "baseline_filename": req.baseline_filename or "",
                "candidate_filename": req.candidate_filename or "",
                "real_env_verified": result["real_env_verified"],
            },
        )
        return {**result, **vault}
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/mcp/api/kpi-recipes")
async def bridge_list_builtin_kpi_recipes(case: str = "", kpi_type: str = ""):
    return list_kpi_recipes(case=case, kpi_type=kpi_type)


@app.get("/mcp/api/kpi-recipes/{recipe_id}")
async def bridge_get_builtin_kpi_recipe(recipe_id: str):
    try:
        return get_kpi_recipe(recipe_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/mcp/api/simdiff/kpis")
async def bridge_create_simulation_diff(req: SimulationDiffRequest):
    try:
        validate_diff_id(req.diff_id)
        result = await mcp_conn.call_tool(
            "run_simulation_diff_tool",
            {
                "baseline_kpis": req.baseline_kpis,
                "candidate_kpis": req.candidate_kpis,
                "tolerances": req.tolerances,
                "diff_id": req.diff_id,
                "input_metadata": json.dumps(req.input_metadata),
            },
        )
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        vault = EVIDENCE.create_vault_entry(
            kind="simulation-diff",
            title=result["diff_id"],
            files={
                "diff.json": Path(result["diff_path"]),
                "diff.md": Path(result["report_path"]),
            },
            summary={
                "overall_status": result["overall_status"],
                "diff_status": result["diff"]["status"],
                "total": result["diff"]["total"],
                "changed_count": result["diff"]["changed_count"],
                "added_count": result["diff"]["added_count"],
                "removed_count": result["diff"]["removed_count"],
                "real_env_verified": result["real_env_verified"],
            },
        )
        return {**result, **vault}
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/mcp/api/doctor/diagnose")
async def bridge_diagnose_solver_logs(req: DoctorDiagnoseRequest):
    try:
        report = diagnose_log_texts(
            job_name=req.job_name,
            logs={
                ".msg": req.msg_text,
                ".dat": req.dat_text,
                ".sta": req.sta_text,
                ".log": req.log_text,
            },
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    report_dir = Path(report.workdir)
    report_json_path = report_dir / "doctor.json"
    report_markdown_path = report_dir / "doctor.md"
    report_json_path.write_text(
        json.dumps(report.to_dict(), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    report_markdown_path.write_text(render_markdown(report), encoding="utf-8")
    vault = EVIDENCE.create_vault_entry(
        kind="solver-doctor",
        title=report.job_name,
        files={
            "doctor.json": report_json_path,
            "doctor.md": report_markdown_path,
        },
        summary={
            "status": report.status,
            "primary_category": report.primary_category,
            "finding_count": len(report.findings),
            "real_env_verified": False,
        },
    )
    return {
        "job_name": report.job_name,
        **vault,
        "status": report.status,
        "primary_category": report.primary_category,
        "summary": report.summary,
        "completed": report.completed,
        "finding_count": len(report.findings),
        "report": report.to_dict(),
        "report_markdown": render_markdown(report),
        "real_env_verified": False,
    }


@app.get("/mcp/api/doctor/patterns")
async def bridge_list_solver_doctor_patterns(category: str = "", severity: str = ""):
    return list_doctor_patterns(category=category, severity=severity)


@app.get("/mcp/api/features")
async def bridge_get_features():
    try:
        return await mcp_conn.call_tool("get_features", {})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Main ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    from core import config

    # Loopback, for the same reason server.py binds loopback: this service has
    # no authentication and can launch solver jobs, so 0.0.0.0 handed the whole
    # LAN a job submitter. ABAQUS_AGENT_HOST is how someone who wants LAN
    # access says so and owns that decision.
    host = config.host()
    port = config.bridge_port()
    print("\n  Abaqus Agent MCP Bridge")
    print("  ─────────────────────────────")
    print(f"  Bridge   : http://{host}:{port}")
    print(f"  MCP API  : http://{host}:{port}/mcp/...")
    print(f"  Frontend : http://{host}:{port}")
    print("  Transport: stdin/stdout → mcp_server.py")
    print()
    uvicorn.run("mcp_bridge:app", host=host, port=port, reload=False)
