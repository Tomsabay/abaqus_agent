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
  GET  /mcp/api/premium/features → tools/call get_premium_features
  POST /mcp/api/premium/activate → tools/call activate_premium

Run:
  python mcp_bridge.py
"""

from __future__ import annotations

import asyncio
import json
import hashlib
import sys
import time
from pathlib import Path
from typing import AsyncGenerator

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

FRONTEND_DIR = Path(__file__).parent / "frontend"

# ── FastAPI bridge app ────────────────────────────────────────────

app = FastAPI(
    title="Abaqus Agent MCP Bridge",
    version="0.1.0",
    description="HTTP/SSE bridge to MCP server for browser access",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


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


# ── Lifecycle ─────────────────────────────────────────────────────

@app.on_event("startup")
async def startup():
    await mcp_conn.start()


@app.on_event("shutdown")
async def shutdown():
    await mcp_conn.stop()


# ── Request models ────────────────────────────────────────────────

class GenerateSpecRequest(BaseModel):
    text: str
    abaqus_release: str = "2024"
    llm_backend: str = "template"
    anthropic_key: str = ""
    openai_key: str = ""

class ValidateSpecRequest(BaseModel):
    spec_yaml: str

class StartRunRequest(BaseModel):
    spec_yaml: str
    runner_cfg: dict = {}


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


@app.get("/mcp/api/premium/features")
async def bridge_get_premium_features():
    try:
        return await mcp_conn.call_tool("get_premium_features", {})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/mcp/api/premium/activate")
async def bridge_activate_premium(license_key: str = ""):
    try:
        return await mcp_conn.call_tool("activate_premium", {"license_key": license_key})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Main ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    print("\n  Abaqus Agent MCP Bridge")
    print("  ─────────────────────────────")
    print("  Bridge   : http://localhost:8001")
    print("  MCP API  : http://localhost:8001/mcp/...")
    print("  Frontend : http://localhost:8001")
    print("  Transport: stdin/stdout → mcp_server.py")
    print()
    uvicorn.run("mcp_bridge:app", host="0.0.0.0", port=8001, reload=False)
