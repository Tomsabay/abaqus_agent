"""
copilot/routes.py
-----------------
FastAPI routes for the Abaqus/CAE Copilot, and the session store behind them.

Wire-up from server.py:
    from copilot.routes import router as copilot_router
    app.include_router(copilot_router)

Lifted out of server.py, which had 71 routes in one file. These 21 own their
own state (COPILOT_SESSIONS and its on-disk mirror), so they move as a unit
rather than leaving the store behind. server.py re-exports COPILOT_SESSIONS
and COPILOT_SESSION_FILE because the CAE plug-in tests reach for them there.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any, AsyncGenerator

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from copilot.models import CopilotPlan
from copilot.planner import CodexUnavailable, build_copilot_plan, execute_plan
from core import config
from core.helpers import check_abaqus
from doctor.cae_errors import diagnose_cae_traceback
from doctor.solver_doctor import diagnose_log_texts
from scripts.package_copilot_alpha import build_copilot_alpha_package
from scripts.verify_copilot_alpha_package import verify_copilot_alpha_package
from scripts.verify_copilot_alpha_release import collect_release_gate

router = APIRouter()

# server.py sat at the repo root, so `Path(__file__).parent` meant the repo
# there. This module is one level down; every path that used to be built
# that way has to keep pointing at the repo, not at copilot/.
REPO_ROOT = Path(__file__).resolve().parent.parent

COPILOT_SESSIONS: dict[str, dict[str, Any]] = {}
COPILOT_SESSION_FILE = Path(
    os.environ.get("ABAQUS_AGENT_SESSION_FILE") or (Path.home() / ".abaqus_agent_session")
)

# Copilot sessions survive server restarts: every mutation persists the session
# to disk (viewport PNG as base64) and the store is rehydrated at import, so the
# CAE plugin's session file never points at a dead session after a dev restart.
# config resolves override → packaged data dir → repo-local (dev).
COPILOT_SESSION_STORE_DIR = config.copilot_session_dir()
COPILOT_SESSION_STORE_KEEP = 50


def _persist_copilot_session(session_id: str) -> None:
    record = COPILOT_SESSIONS.get(session_id)
    if record is None:
        return
    try:
        COPILOT_SESSION_STORE_DIR.mkdir(parents=True, exist_ok=True)
        serializable = dict(record)
        viewport = record.get("viewport")
        if viewport and isinstance(viewport.get("png"), (bytes, bytearray)):
            serializable["viewport"] = {
                **viewport,
                "png": base64.b64encode(viewport["png"]).decode("ascii"),
                "png_encoding": "base64",
            }
        target = COPILOT_SESSION_STORE_DIR / f"{session_id}.json"
        tmp = target.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps(serializable, ensure_ascii=False, default=str), encoding="utf-8"
        )
        tmp.replace(target)
        _prune_copilot_session_store()
    except OSError:
        pass  # persistence is best-effort; the live session keeps working


def _prune_copilot_session_store() -> None:
    files = sorted(
        COPILOT_SESSION_STORE_DIR.glob("copilot-*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for stale in files[COPILOT_SESSION_STORE_KEEP:]:
        try:
            stale.unlink()
        except OSError:
            pass


def _load_copilot_sessions_from_disk() -> int:
    if not COPILOT_SESSION_STORE_DIR.exists():
        return 0
    loaded = 0
    files = sorted(
        COPILOT_SESSION_STORE_DIR.glob("copilot-*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for path in files[:COPILOT_SESSION_STORE_KEEP]:
        session_id = path.stem
        if session_id in COPILOT_SESSIONS:
            continue
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue  # a corrupt file must not block startup
        viewport = record.get("viewport")
        if viewport and viewport.get("png_encoding") == "base64":
            try:
                viewport["png"] = base64.b64decode(viewport["png"])
                viewport.pop("png_encoding", None)
            except (ValueError, TypeError):
                record["viewport"] = None
        COPILOT_SESSIONS[session_id] = record
        loaded += 1
    return loaded


_load_copilot_sessions_from_disk()


class CopilotPlanRequest(BaseModel):
    text: str
    backend: str = "codex"

class CopilotExecuteRequest(BaseModel):
    session_id: str
    bridge_mode: str = "mock"

class CopilotActionResultRequest(BaseModel):
    action_index: int
    status: str
    message: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)

class CopilotModelStateRequest(BaseModel):
    """mdb snapshot reported by the Abaqus/CAE plug-in after each action."""

    models: list[dict[str, Any]] = Field(default_factory=list)
    active_model: str = ""
    source: str = "abaqus-cae-plugin"

class CopilotViewportRequest(BaseModel):
    """Viewport PNG captured by the Abaqus/CAE plug-in, base64-encoded."""

    image_base64: str
    caption: str = ""


# ── Copilot endpoints ─────────────────────────────────────────────

@router.get("/api/copilot/status")
def get_copilot_status():
    """Expose the user-facing Copilot runtime status."""
    return {
        "status": "ok",
        "codex_app_server": "available",
        "auth_mode": "local_codex_app_server",
        "abaqus_available": check_abaqus(),
        "supported_actions": [
            "create_cantilever_model",
            "apply_boundary_condition",
            "submit_job_or_prepare_run",
        ],
        "sessions": len(COPILOT_SESSIONS),
    }


COPILOT_REPLAY_DIR = REPO_ROOT / "evidence" / "copilot_replay"
COPILOT_REPLAY_FILE = COPILOT_REPLAY_DIR / "replay.json"
# whitelist: recording names come from the URL, never map them to arbitrary paths
COPILOT_REPLAY_RECORDINGS: dict[str, dict[str, str]] = {
    "default": {"file": "replay.json", "title": "悬臂梁：真实报错 → 一键修复 → 出结果"},
    "simple_beam": {"file": "replay_simple_beam.json", "title": "简支梁三点弯：跨中挠度对照理论解"},
    "plate_hole": {"file": "replay_plate_hole.json", "title": "开孔板：孔边应力集中 Kt 验证"},
    "modal": {"file": "replay_modal.json", "title": "悬臂梁模态：前 5 阶固有频率对照解析解"},
}


def _replay_path(name: str) -> Path:
    if name == "default":
        return COPILOT_REPLAY_FILE  # module attr so tests can monkeypatch it
    return COPILOT_REPLAY_DIR / COPILOT_REPLAY_RECORDINGS[name]["file"]


@router.get("/api/copilot/replays")
def list_copilot_replays():
    """List available demo recordings for the workspace replay picker."""
    recordings = [
        {"name": name, "title": meta["title"]}
        for name, meta in COPILOT_REPLAY_RECORDINGS.items()
        if _replay_path(name).exists()
    ]
    return {"recordings": recordings}


@router.get("/api/copilot/replay")
@router.head("/api/copilot/replay")  # frontend probes availability before showing the demo hint
def get_copilot_replay(name: str = "default"):
    """Serve a recorded real-Abaqus session so the workspace can replay it without CAE."""
    if name not in COPILOT_REPLAY_RECORDINGS:
        raise HTTPException(status_code=404, detail=f"Unknown replay recording: {name}")
    path = _replay_path(name)
    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail=(
                "No replay recording available. Run scripts/record_copilot_replay.py "
                "on a machine with Abaqus to create one."
            ),
        )
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise HTTPException(status_code=500, detail=f"Replay recording unreadable: {exc}")


@router.get("/api/copilot/plugin-guide")
def get_copilot_plugin_guide(request: Request):
    """Return copy-paste setup details for the Abaqus/CAE Copilot plug-in."""
    server_url = str(request.base_url).rstrip("/")
    return {
        "server_url": server_url,
        "install_command": "abaqus-agent-copilot-install-plugin --plugin-dir <ABAQUS_PLUGIN_DIR>",
        "remote_server_env": f"ABAQUS_AGENT_SERVER_URL={server_url}",
        "session_file": str(COPILOT_SESSION_FILE),
        "open_sidecar_action": "AbaqusAgent Copilot: Open Sidecar",
        "run_plan_action": "AbaqusAgent Copilot: Run Current Plan",
        "execute_next_action": "AbaqusAgent Copilot: Execute Next Action",
        "status_action": "AbaqusAgent Copilot: Check Session Status",
        "execution_loop": "优先点击 Run Current Plan 一键执行完整队列；需要调试时再用 Execute Next Action 单步执行。",
    }


@router.get("/api/copilot/release-gate")
def get_copilot_release_gate(strict_gui: bool = False):
    """Return current Copilot Alpha/release evidence status."""
    return collect_release_gate(root=REPO_ROOT, strict_gui=strict_gui)


@router.get("/api/copilot/alpha-package.zip")
def get_copilot_alpha_package(request: Request):
    """Build and download the current Copilot Alpha package."""
    server_url = str(request.base_url).rstrip("/")
    result = build_copilot_alpha_package(root=REPO_ROOT, server_url=server_url)
    package_path = Path(result["package_path"])
    if not package_path.exists():
        raise HTTPException(status_code=404, detail="Copilot Alpha package not found")
    return FileResponse(
        package_path,
        media_type="application/zip",
        filename=result["package_name"],
    )


@router.get("/api/copilot/alpha-package/verify")
def verify_copilot_alpha_package_endpoint(request: Request):
    """Build and verify the current Copilot Alpha package."""
    server_url = str(request.base_url).rstrip("/")
    package = build_copilot_alpha_package(root=REPO_ROOT, server_url=server_url)
    verification = verify_copilot_alpha_package(package["package_path"])
    return {
        "package": package,
        "verification": verification,
    }


@router.post("/api/copilot/plan")
def create_copilot_plan(req: CopilotPlanRequest):
    """Convert a beginner-friendly Abaqus request into safe CAE actions."""
    try:
        plan = build_copilot_plan(req.text, backend=req.backend)
    except CodexUnavailable as e:
        raise HTTPException(status_code=503, detail=f"Codex app-server unavailable: {e}")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    plan_data = plan.model_dump()
    COPILOT_SESSIONS[plan.session_id] = {
        "plan": plan_data,
        "pending_actions": plan_data["actions"].copy(),
        "results": [],
        "created_at": time.time(),
    }
    _persist_copilot_session(plan.session_id)
    return plan_data


@router.post("/api/copilot/execute")
def execute_copilot_plan(req: CopilotExecuteRequest):
    """Prepare or execute a Copilot action plan through the local bridge."""
    record = COPILOT_SESSIONS.get(req.session_id)
    if not record:
        raise HTTPException(status_code=404, detail="Copilot session not found")
    plan = CopilotPlan.model_validate(record["plan"])
    result = execute_plan(plan, bridge_mode=req.bridge_mode)
    result_data = result.model_dump()
    record["execution"] = result_data
    _persist_copilot_session(req.session_id)
    return result_data


def _build_copilot_session_summary(session_id: str, record: dict) -> dict:
    plan = record.get("plan") or {}
    pending_actions = record.get("pending_actions") or []
    results = record.get("results") or []
    model_state = record.get("model_state") or {}
    viewport = record.get("viewport") or {}
    kpis = None
    for item in reversed(results):
        payload_kpis = (item.get("payload") or {}).get("kpis")
        if payload_kpis:
            kpis = payload_kpis
            break
    return {
        "session_id": session_id,
        "backend": plan.get("backend"),
        "user_summary": plan.get("user_summary"),
        "action_count": len(plan.get("actions") or []),
        "pending_count": len(pending_actions),
        # only genuinely completed actions count; a failed action must not
        # let the UI claim "3/3 完成"
        "completed_count": len([r for r in results if r.get("status") == "completed"]),
        "results": results,
        "errors": [r for r in results if r.get("status") == "failed"],
        "kpis": kpis,
        "model_state_at": model_state.get("reported_at"),
        "viewport_at": viewport.get("captured_at"),
        "execution": record.get("execution"),
        "created_at": record.get("created_at"),
    }


def _session_with_plan(session_id: str, record: dict) -> dict:
    return {
        "session_id": session_id,
        "plan": record.get("plan"),
        "summary": _build_copilot_session_summary(session_id, record),
    }


@router.get("/api/copilot/sessions")
def list_copilot_sessions(limit: int = 20):
    """List recent Copilot sessions (newest first) for the history picker."""
    summaries = [
        _build_copilot_session_summary(session_id, record)
        for session_id, record in COPILOT_SESSIONS.items()
    ]
    summaries.sort(key=lambda s: s.get("created_at") or 0, reverse=True)
    return {"sessions": summaries[: max(1, min(limit, 100))]}


@router.get("/api/copilot/sessions/active")
def get_active_copilot_session():
    """Return the session the local plugin pointer targets, with its plan.

    Lets the workspace re-attach after a page refresh or server restart:
    sessions are persisted to disk and the pointer file survives both.
    """
    if not COPILOT_SESSION_FILE.exists():
        raise HTTPException(status_code=404, detail="No active Copilot session")
    session_id = COPILOT_SESSION_FILE.read_text(encoding="utf-8").strip()
    record = COPILOT_SESSIONS.get(session_id)
    if not session_id or not record:
        raise HTTPException(status_code=404, detail="Active Copilot session not found")
    return _session_with_plan(session_id, record)


@router.get("/api/copilot/sessions/{session_id}/full")
def get_copilot_session_full(session_id: str):
    """Return plan + summary so the workspace can restore any stored session."""
    record = COPILOT_SESSIONS.get(session_id)
    if not record:
        raise HTTPException(status_code=404, detail="Copilot session not found")
    return _session_with_plan(session_id, record)


@router.get("/api/copilot/sessions/{session_id}")
def get_copilot_session(session_id: str):
    """Return a Copilot session summary for sidecar/plugin progress UI."""
    record = COPILOT_SESSIONS.get(session_id)
    if not record:
        raise HTTPException(status_code=404, detail="Copilot session not found")
    return _build_copilot_session_summary(session_id, record)


@router.get("/api/copilot/sessions/{session_id}/stream")
async def stream_copilot_session(session_id: str):
    """
    Server-Sent Events stream for near-real-time Copilot workspace updates.
    Replaces 3s client polling: server checks every 0.3s and only pushes on change,
    so the model tree / viewport / error panes update as soon as the plugin reports them.
    Frontend: const es = new EventSource('/api/copilot/sessions/<id>/stream')
    """
    if session_id not in COPILOT_SESSIONS:
        raise HTTPException(status_code=404, detail="Copilot session not found")

    async def event_gen() -> AsyncGenerator[str, None]:
        last_fingerprint = None
        timeout = 1800  # 30 min per connection; EventSource auto-reconnects after
        t0 = time.time()

        while time.time() - t0 < timeout:
            record = COPILOT_SESSIONS.get(session_id)
            if record is None:
                yield "data: {\"event\": \"done\"}\n\n"
                break

            summary = _build_copilot_session_summary(session_id, record)
            fingerprint = hashlib.md5(
                json.dumps(summary, sort_keys=True, default=str).encode()
            ).hexdigest()

            if fingerprint != last_fingerprint:
                yield f"data: {json.dumps(summary, default=str)}\n\n"
                last_fingerprint = fingerprint

            await asyncio.sleep(0.3)

    return StreamingResponse(event_gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})


@router.get("/api/copilot/sessions/{session_id}/next-action")
def get_copilot_next_action(session_id: str):
    """Endpoint polled by the Abaqus/CAE plugin bridge."""
    record = COPILOT_SESSIONS.get(session_id)
    if not record:
        raise HTTPException(status_code=404, detail="Copilot session not found")
    pending = record.get("pending_actions") or []
    if not pending:
        return {"session_id": session_id, "action": None}
    return {
        "session_id": session_id,
        "action_index": len(record.get("results", [])),
        "action": pending[0],
    }


@router.post("/api/copilot/sessions/{session_id}/activate")
def activate_copilot_session(session_id: str):
    """Make a Copilot session the default session for the local CAE plug-in."""
    if session_id not in COPILOT_SESSIONS:
        raise HTTPException(status_code=404, detail="Copilot session not found")
    COPILOT_SESSION_FILE.write_text(session_id, encoding="utf-8")
    return {
        "session_id": session_id,
        "session_file": str(COPILOT_SESSION_FILE),
        "plugin_action": "AbaqusAgent Copilot: Run Current Plan",
        "debug_plugin_action": "AbaqusAgent Copilot: Execute Next Action",
        "message": "Copilot session activated for the local Abaqus/CAE plug-in.",
    }


@router.post("/api/copilot/sessions/{session_id}/action-result")
def post_copilot_action_result(session_id: str, req: CopilotActionResultRequest):
    """Record a result from the Abaqus/CAE plugin bridge."""
    record = COPILOT_SESSIONS.get(session_id)
    if not record:
        raise HTTPException(status_code=404, detail="Copilot session not found")
    pending = record.get("pending_actions") or []
    if pending:
        pending.pop(0)
    result = {
        "action_index": req.action_index,
        "status": req.status,
        "message": req.message,
        "payload": req.payload,
        "received_at": time.time(),
    }
    if req.status == "failed":
        payload = req.payload or {}
        traceback_text = str(payload.get("traceback") or req.message or "")
        result["diagnosis"] = diagnose_cae_traceback(traceback_text)
        solver_logs = payload.get("solver_logs") or {}
        job_name = str(payload.get("job_name") or "")
        if solver_logs and job_name:
            try:
                report = diagnose_log_texts(job_name=job_name, logs=solver_logs)
                result["solver_doctor"] = {
                    "status": report.status,
                    "summary": report.summary,
                    "primary_category": report.primary_category,
                    "findings": [finding.to_dict() for finding in report.findings[:5]],
                }
            except (ValueError, OSError):
                pass  # malformed plugin logs must not break result recording
    record.setdefault("results", []).append(result)
    _persist_copilot_session(session_id)
    return {
        "session_id": session_id,
        "remaining_actions": len(record.get("pending_actions") or []),
        "result": result,
    }


COPILOT_VIEWPORT_MAX_BYTES = 4 * 1024 * 1024


@router.post("/api/copilot/sessions/{session_id}/model-state")
def post_copilot_model_state(session_id: str, req: CopilotModelStateRequest):
    """Receive an mdb snapshot from the Abaqus/CAE plug-in (Copilot's eyes)."""
    record = COPILOT_SESSIONS.get(session_id)
    if not record:
        raise HTTPException(status_code=404, detail="Copilot session not found")
    record["model_state"] = {
        "models": req.models,
        "active_model": req.active_model,
        "source": req.source,
        "reported_at": time.time(),
    }
    _persist_copilot_session(session_id)
    return {
        "session_id": session_id,
        "model_count": len(req.models),
        "reported_at": record["model_state"]["reported_at"],
    }


@router.get("/api/copilot/sessions/{session_id}/model-state")
def get_copilot_model_state(session_id: str):
    """Return the latest mdb snapshot for the sidecar model tree panel."""
    record = COPILOT_SESSIONS.get(session_id)
    if not record:
        raise HTTPException(status_code=404, detail="Copilot session not found")
    state = record.get("model_state")
    if not state:
        return {"session_id": session_id, "models": [], "active_model": "", "reported_at": None}
    return {"session_id": session_id, **state}


@router.post("/api/copilot/sessions/{session_id}/viewport")
def post_copilot_viewport(session_id: str, req: CopilotViewportRequest):
    """Receive a viewport PNG from the Abaqus/CAE plug-in."""
    record = COPILOT_SESSIONS.get(session_id)
    if not record:
        raise HTTPException(status_code=404, detail="Copilot session not found")
    try:
        image = base64.b64decode(req.image_base64, validate=True)
    except ValueError:
        raise HTTPException(status_code=400, detail="image_base64 is not valid base64")
    if len(image) > COPILOT_VIEWPORT_MAX_BYTES:
        raise HTTPException(status_code=413, detail="Viewport image exceeds 4 MB limit")
    if not image.startswith(b"\x89PNG"):
        raise HTTPException(status_code=400, detail="Viewport image must be PNG")
    record["viewport"] = {
        "png": image,
        "caption": req.caption,
        "captured_at": time.time(),
    }
    _persist_copilot_session(session_id)
    return {
        "session_id": session_id,
        "bytes": len(image),
        "captured_at": record["viewport"]["captured_at"],
    }


@router.get("/api/copilot/sessions/{session_id}/viewport.png")
def get_copilot_viewport_png(session_id: str):
    """Serve the latest viewport PNG for the sidecar viewport panel."""
    record = COPILOT_SESSIONS.get(session_id)
    if not record:
        raise HTTPException(status_code=404, detail="Copilot session not found")
    viewport = record.get("viewport")
    if not viewport:
        raise HTTPException(status_code=404, detail="No viewport captured yet")
    return Response(content=viewport["png"], media_type="image/png")
