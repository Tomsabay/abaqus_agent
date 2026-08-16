"""
workbench/routes.py
-------------------
FastAPI routes for the Cursor-style workbench.

Wire-up from server.py:
    from workbench.routes import configure as configure_workbench, router as workbench_router
    configure_workbench(RUNS)
    app.include_router(workbench_router)

The run machinery (RUNS dict, run_pipeline, SSE stream, artifact serving) is
shared with the existing /api/run/* endpoints; accepting a proposal here just
creates a normal run that the existing endpoints can stream and serve.
"""

from __future__ import annotations

import asyncio
import hashlib
import time
from pathlib import Path

import yaml
from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from core.pipeline import run_pipeline
from tools.schema_validator import validate_spec
from workbench import store
from workbench.chat_flow import get_session_or_404 as _get_session_or_404
from workbench.chat_flow import router as _chat_flow_router
from workbench.model_tree import build_tree

router = APIRouter()
# The chat → proposal flow (plain POST, SSE stream, plan confirmation) lives
# in workbench/chat_flow.py; imports flow strictly routes → chat_flow.
router.include_router(_chat_flow_router)

_RUNS: dict | None = None
_FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

_ACTIVE_RUN_STATES = ("PENDING", "RUNNING")
# REFUSED is terminal too — the backend declined to solve the spec rather than
# failing partway (agent/ccx_orchestrator.py). It was missing here, so a
# refused run was never treated as finished on either side of the wire.
_TERMINAL_RUN_STATES = ("COMPLETED", "FAILED", "ABORTED", "ERROR", "REFUSED")


def configure(runs: dict) -> None:
    global _RUNS
    _RUNS = runs


def _runs_store() -> dict:
    if _RUNS is None:
        raise HTTPException(status_code=503, detail="Workbench not configured")
    return _RUNS


class CreateSessionRequest(BaseModel):
    title: str = ""


class AcceptRequest(BaseModel):
    runner_cfg: dict = Field(default_factory=dict)
    # Optional: submit this spec instead of pending.spec_yaml. Used by the
    # parametric-slider panel — user tweaks L/W/H etc. on the client, then
    # accepts. The base proposal id is preserved for provenance.
    spec_yaml: str | None = None


def _visual_names(run: dict) -> list[str]:
    names = []
    for entry in run.get("orchestrator_result", {}).get("visuals", []) or []:
        if isinstance(entry, str):
            names.append(Path(entry).name)
        elif isinstance(entry, dict):
            raw = entry.get("file") or entry.get("path") or entry.get("png") or ""
            if raw:
                names.append(Path(str(raw)).name)
    return names


def _animation_video(run: dict) -> str | None:
    anim = run.get("orchestrator_result", {}).get("animation") or {}
    video = anim.get("video")
    return Path(str(video)).name if video else None


def _enrich_runs(session: dict) -> bool:
    """Sync session run records from the live RUNS dict. Returns True if changed."""
    runs = _runs_store()
    changed = False
    for record in session.get("runs", []):
        live = runs.get(record.get("run_id", ""))
        if not live:
            continue
        status = live.get("status")
        if status and status != record.get("status"):
            record["status"] = status
            changed = True
        # Which solver produced this run has to survive a server restart too,
        # otherwise the archived view silently reads as a full-Abaqus result.
        # `error` and `kpi_notice` are the only record a failed or refused run
        # leaves behind. Without them a server restart turns "solve refused,
        # here is why" into a bare FAILED chip with nothing to show, because
        # /api/run/{id} 404s once RUNS is empty.
        # `regression` and `contracts` are the verdict on the numbers. They
        # belong on the same list for the same reason: /api/run/{id} 404s once
        # RUNS is empty, and an archived run that shows KPIs with no verdict
        # beside them reads as a clean result.
        for key in ("backend", "limitations", "kpi_provenance", "kpis_missing",
                    "mesh_risks", "error", "kpi_notice",
                    "regression", "contracts"):
            value = live.get(key)
            if value and record.get(key) != value:
                record[key] = value
                changed = True
        if status in _TERMINAL_RUN_STATES:
            kpis = live.get("kpis", {})
            if kpis and record.get("kpis") != kpis:
                record["kpis"] = kpis
                changed = True
            visuals = _visual_names(live)
            if visuals and record.get("visuals") != visuals:
                record["visuals"] = visuals
                changed = True
            animation = _animation_video(live)
            if animation and record.get("animation") != animation:
                record["animation"] = animation
                changed = True
    return changed


@router.get("/workbench")
def workbench_page():
    page = _FRONTEND_DIR / "workbench.html"
    if not page.exists():
        raise HTTPException(status_code=404, detail="workbench.html not found")
    return FileResponse(str(page))


@router.get("/api/workbench/sessions")
def get_sessions():
    return {"sessions": store.list_sessions()}


@router.post("/api/workbench/sessions")
def create_session(req: CreateSessionRequest):
    return store.new_session(req.title)


@router.get("/api/workbench/sessions/{session_id}")
def get_session(session_id: str):
    session = _get_session_or_404(session_id)
    if _enrich_runs(session):
        store.save_session(session)
    return session


@router.post("/api/workbench/sessions/{session_id}/accept")
async def accept(session_id: str, req: AcceptRequest, background_tasks: BackgroundTasks):
    runs = _runs_store()
    session = _get_session_or_404(session_id)
    pending = session.get("pending")
    if not pending:
        raise HTTPException(status_code=409, detail="No pending proposal")

    _enrich_runs(session)
    for record in session.get("runs", []):
        if record.get("status") in _ACTIVE_RUN_STATES:
            raise HTTPException(
                status_code=409,
                detail=f"Run {record['run_id']} still active (single license)")

    # req.spec_yaml wins over pending — this is the slider-panel path where
    # the user tweaked geometry values client-side and wants the solve to run
    # on the tweaked spec, not the AI's original proposal.
    spec_yaml = req.spec_yaml or pending["spec_yaml"]
    spec = yaml.safe_load(spec_yaml)
    valid, errors = validate_spec(spec)
    if not valid:
        raise HTTPException(status_code=400, detail={"errors": errors})

    # Refuse BEFORE a run record exists, naming the way out. A run record for a
    # machine that cannot solve anything is a row in the session history that
    # looks like work happened.
    from core.backends import refusal_messages, select_backend
    from core.helpers import check_abaqus as _check_abaqus
    decision = select_backend(
        spec,
        abaqus_available=_check_abaqus(),
        override=(req.runner_cfg or {}).get("backend"),
    )
    if not decision.supported:
        raise HTTPException(status_code=400, detail={
            "errors": refusal_messages(decision),
            "backend": decision.as_dict(),
        })

    run_id = hashlib.sha256(
        f"{session_id}:{time.time_ns()}:{spec_yaml}".encode()).hexdigest()[:16]
    # An empty runner_cfg used to fall through to the orchestrator's bare
    # defaults — cpus=1, timeout_seconds=1800 — which no case's runner.json
    # actually uses, and which an assembly cannot live inside: measured
    # 2026-08-08, bearing_block accepted through this endpoint had finished
    # steps 1-2 and was 17.5% into the friction step when the 30-minute
    # ceiling would have cut it down. cpus=2 is what every shipped runner.json
    # and every real gate runs; 7200 is a ceiling, not a solver setting.
    # Caller-provided values always win.
    runner_cfg = {"cpus": 2, "timeout_seconds": 7200, **(req.runner_cfg or {})}
    runs[run_id] = {
        "run_id": run_id,
        "status": "PENDING",
        "spec": spec,
        "runner_cfg": runner_cfg,
        "stages": {},
        "kpis": {},
        "started_at": time.time(),
        "finished_at": None,
        "progress_pct": 0,
    }
    background_tasks.add_task(run_pipeline, run_id, runs)

    session["current_spec_yaml"] = spec_yaml
    session["pending"] = None
    session["runs"].append({
        "run_id": run_id,
        "status": "PENDING",
        "accepted_at": time.time(),
        "proposal_id": pending["proposal_id"],
        "model_name": (spec.get("meta") or {}).get("model_name", ""),
    })
    session["messages"].append({
        "role": "assistant",
        "text": f"提案已接受，已提交真实求解（run {run_id[:8]}）。",
        "ts": time.time(),
        "run_id": run_id,
    })
    store.save_session(session)
    return {"run_id": run_id, "session": session}


class PreviewRequest(BaseModel):
    spec_yaml: str | None = None  # falls back to session.pending.spec_yaml


@router.post("/api/workbench/sessions/{session_id}/tree")
async def model_tree(session_id: str, req: PreviewRequest):
    """The model tree, from the spec alone.

    Deliberately separate from /preview and deliberately not validated: the
    tree is what the spec SAYS, and the moment it is most worth reading is
    while the spec is still wrong. A CAE cold start is 5-15 s, so a tree that
    waited for the mesh would leave the pane empty for exactly as long as the
    user is wondering what the model even contains.
    """
    session = _get_session_or_404(session_id)
    spec_yaml = req.spec_yaml
    if not spec_yaml:
        pending = session.get("pending") or {}
        spec_yaml = pending.get("spec_yaml") or session.get("current_spec_yaml")
    if not spec_yaml:
        return {"tree": build_tree(None), "spec_ok": False,
                "problems": ["还没有 spec"]}
    try:
        spec = yaml.safe_load(spec_yaml)
    except yaml.YAMLError as exc:
        return {"tree": build_tree(None), "spec_ok": False,
                "problems": ["YAML 解析失败：%s" % str(exc)[:200]]}
    valid, errors = validate_spec(spec)
    return {"tree": build_tree(spec), "spec_ok": bool(valid),
            "problems": [] if valid else list(errors)[:8]}


# ── In-memory preview cache: hash(spec_yaml) -> mesh dict (LRU-lite) ──
_PREVIEW_CACHE: dict = {}
_PREVIEW_CACHE_MAX = 32


def _preview_hash(spec_yaml: str) -> str:
    # v2: switched CAE dump to label-keyed connectivity (was 0-based indices).
    # Bumping the prefix here bypasses stale cached workdirs from before.
    return hashlib.sha256(("v2:" + spec_yaml).encode("utf-8")).hexdigest()[:16]


def _preview_workdir(key: str) -> Path:
    from core import config
    base = config.run_root() or (Path(__file__).resolve().parent.parent
                                  / "artifacts" / "workbench_preview")
    d = base / "preview" / key
    d.mkdir(parents=True, exist_ok=True)
    return d


def _resolve_deck_path(spec_yaml: str) -> str:
    """A deck spec may carry a RELATIVE path, which build_model resolves against
    the spec file's own directory. Preview copies the spec into a hashed scratch
    workdir, so a relative path would resolve there and always miss — which is
    why cases/steel_frame_blast could never be previewed.

    Rewrite a relative path to an absolute one before the spec leaves its
    original context. Returns the spec unchanged when there is nothing to fix or
    no candidate exists, so the normal FILE_NOT_FOUND error still surfaces.
    """
    try:
        spec = yaml.safe_load(spec_yaml)
        deck = (spec or {}).get("deck") or {}
        if not deck.get("file"):
            return spec_yaml
        holder, key = deck, "file"
        raw = holder.get(key)
        if not raw or Path(raw).is_absolute():
            return spec_yaml

        repo_root = Path(__file__).resolve().parent.parent
        name = Path(raw).name
        candidates = [repo_root / raw, repo_root / "cases" / raw]
        cases_dir = repo_root / "cases"
        if cases_dir.is_dir():
            candidates.extend(sorted(cases_dir.glob("*/" + name)))
        from core import config
        data_root = config.run_root()
        if data_root:
            candidates.append(Path(data_root) / raw)

        for c in candidates:
            if c.is_file():
                holder[key] = str(c.resolve())
                return yaml.safe_dump(spec, allow_unicode=True, sort_keys=False)
    except Exception:
        pass
    return spec_yaml


def _run_preview_build(spec_yaml: str, key: str) -> dict:
    """Synchronous helper (call from a thread). Writes spec.yaml, runs the CAE
    noGUI build, reads back preview_mesh.json. Returns the mesh dict or an
    error dict {'error': str}."""
    import json as _json

    from runner.build_model import build_model

    workdir = _preview_workdir(key)
    spec_path = workdir / "spec.yaml"
    spec_path.write_text(_resolve_deck_path(spec_yaml), encoding="utf-8")
    try:
        result = build_model(spec_path, workdir)
    except Exception as e:
        return {"error": "build_model failed: %s" % e}
    mesh_name = result.get("preview_mesh")
    if not mesh_name:
        return {"error": "preview_mesh not produced (CAE dump missing)"}
    mesh_path = workdir / mesh_name
    if not mesh_path.exists():
        return {"error": "preview_mesh file missing: %s" % mesh_path}
    mesh = _json.loads(mesh_path.read_text(encoding="utf-8"))
    # A mesh that admits it is not renderable must surface as an ERROR, not
    # as an empty viewport with success chrome around it. Before this gate, a
    # deck the parser could not read showed "0 part · 0 节点 · 0 单元" and the
    # user concluded the model was simply not drawing — then submitted a solve
    # of geometry the UI never actually showed.
    if isinstance(mesh.get("parts"), list):
        if mesh.get("parse_ok") is False or not mesh["parts"]:
            reasons = mesh.get("problems") or ["预览网格为空（0 个可渲染部件）"]
            return {"error": "；".join(str(r) for r in reasons)}
    elif not mesh.get("nodes"):
        return {"error": "预览网格为空（CAE 导出的网格里没有节点）"}
    return mesh


@router.post("/api/workbench/sessions/{session_id}/preview")
async def preview(session_id: str, req: PreviewRequest):
    """Build the current (or pending) spec into a 3D mesh for the diff panel.
    Synchronous return — the mesh JSON is small (<500KB for typical parts)
    and CAE noGUI cold-start is 5-15s. Result is cached by spec hash so
    repeated fetches from the frontend are cheap."""
    session = _get_session_or_404(session_id)
    spec_yaml = req.spec_yaml
    if not spec_yaml:
        pending = session.get("pending") or {}
        spec_yaml = pending.get("spec_yaml") or session.get("current_spec_yaml")
    if not spec_yaml:
        raise HTTPException(status_code=400, detail="No spec available for preview")

    spec = yaml.safe_load(spec_yaml)
    valid, errors = validate_spec(spec)
    if not valid:
        raise HTTPException(status_code=400, detail={"errors": errors})

    key = _preview_hash(spec_yaml)
    cached = _PREVIEW_CACHE.get(key)
    if cached is not None:
        return {"cached": True, "mesh": cached, "elapsed_s": 0}

    t0 = time.time()
    mesh_or_err = await asyncio.to_thread(_run_preview_build, spec_yaml, key)
    elapsed = round(time.time() - t0, 2)
    if isinstance(mesh_or_err, dict) and mesh_or_err.get("error"):
        raise HTTPException(status_code=500,
                            detail={"error": mesh_or_err["error"], "elapsed_s": elapsed})

    # LRU-lite: drop oldest key when full.
    if len(_PREVIEW_CACHE) >= _PREVIEW_CACHE_MAX:
        _PREVIEW_CACHE.pop(next(iter(_PREVIEW_CACHE)))
    _PREVIEW_CACHE[key] = mesh_or_err
    return {"cached": False, "mesh": mesh_or_err, "elapsed_s": elapsed}


@router.post("/api/workbench/sessions/{session_id}/preview/stream")
async def preview_stream(session_id: str, req: PreviewRequest):
    """SSE flavor of /preview — emits one 'meta' event, one 'part' event per
    part (with a small delay so users see the assembly grow in the viewport),
    then a final 'done' event. Cached hits skip the delay. Single-mesh legacy
    output is wrapped as a one-part payload so the frontend has one code path.
    """
    import json as _json

    session = _get_session_or_404(session_id)
    spec_yaml = req.spec_yaml
    if not spec_yaml:
        pending = session.get("pending") or {}
        spec_yaml = pending.get("spec_yaml") or session.get("current_spec_yaml")
    if not spec_yaml:
        raise HTTPException(status_code=400, detail="No spec available for preview")

    spec = yaml.safe_load(spec_yaml)
    valid, errors = validate_spec(spec)
    if not valid:
        raise HTTPException(status_code=400, detail={"errors": errors})

    key = _preview_hash(spec_yaml)

    async def gen():
        def sse(event: str, payload: dict) -> str:
            return "event: %s\ndata: %s\n\n" % (
                event, _json.dumps(payload, separators=(",", ":")))

        t0 = time.time()
        cached = _PREVIEW_CACHE.get(key)
        if cached is not None:
            mesh = cached
            was_cached = True
        else:
            yield sse("build", {"msg": "building model…"})
            mesh_or_err = await asyncio.to_thread(_run_preview_build, spec_yaml, key)
            if isinstance(mesh_or_err, dict) and mesh_or_err.get("error"):
                yield sse("error", {"error": mesh_or_err["error"]})
                return
            if len(_PREVIEW_CACHE) >= _PREVIEW_CACHE_MAX:
                _PREVIEW_CACHE.pop(next(iter(_PREVIEW_CACHE)))
            _PREVIEW_CACHE[key] = mesh_or_err
            mesh = mesh_or_err
            was_cached = False

        if isinstance(mesh.get("parts"), list):
            parts = mesh["parts"]
            bbox = mesh.get("bbox")
            node_count = mesh.get("node_count", 0)
            element_count = mesh.get("element_count", 0)
            triangle_count = mesh.get("render_triangle_count", 0)
        else:
            # Wrap single-mesh legacy shape as a one-part payload.
            parts = [{
                "name": "PART-1",
                "family": "surface",
                "element_type": mesh.get("element_type", ""),
                "nodes": mesh.get("nodes", []),
                "tris": mesh.get("tris", []),
                "node_count": mesh.get("node_count", 0),
                "tri_count": mesh.get("tri_count", 0),
                "color": None,
            }]
            bbox = mesh.get("bbox")
            node_count = mesh.get("node_count", 0)
            # A CAE-side dump gives us the exterior surface triangulation, not a
            # element count. Report it as what it is; the UI must not label
            # triangles as 单元.
            element_count = None
            triangle_count = mesh.get("tri_count", 0)

        yield sse("meta", {
            "format": mesh.get("format", "abaqus-agent-mesh/2-parts"),
            "cached": was_cached,
            "part_count": len(parts),
            "bbox": bbox,
            "node_count": node_count,
            "element_count": element_count,
            "triangle_count": triangle_count,
            # Non-fatal parse warnings (dropped element families, skipped
            # dangling elements). Without these a partial render reads as the
            # complete model.
            "problems": mesh.get("problems") or [],
            # The named surfaces and sets, which interaction joins which of
            # them, and the triangles of each. Computed all along by
            # post/parse_inp.py:_overlay_region and then dropped here, so the
            # tree could dim two whole bodies for a contact pair and never show
            # the faces that were actually joined -- the one thing a spec author
            # cannot check by reading the spec.
            #
            # None for an .inp-derived payload and for a CAE dump written
            # before the key existed, which the viewport treats as "no
            # highlight available" rather than as an empty model.
            #
            # Measured on bearing_block (5 surfaces, 2 interactions, 8460
            # facets): 119 KB against a 477 KB mesh. Every list in it is
            # already capped upstream -- PREVIEW_REGION_CAP regions,
            # PREVIEW_REGION_NODE_CAP nodes each, MAX_FACETS_PER_SURFACE
            # triangles -- and what a cap dropped is named in `degraded`.
            "assembly": mesh.get("assembly"),
        })

        delay = 0.0 if was_cached else 0.25
        for i, part in enumerate(parts):
            yield sse("part", {"index": i, "total": len(parts), "part": part})
            if delay and i < len(parts) - 1:
                await asyncio.sleep(delay)

        yield sse("done", {"elapsed_s": round(time.time() - t0, 2)})

    return StreamingResponse(gen(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no",
                 "Connection": "keep-alive"})


@router.post("/api/workbench/sessions/{session_id}/reject")
def reject(session_id: str):
    session = _get_session_or_404(session_id)
    if not session.get("pending"):
        raise HTTPException(status_code=409, detail="No pending proposal")
    session["pending"] = None
    session["messages"].append({
        "role": "assistant", "text": "提案已拒绝，当前 spec 保持不变。", "ts": time.time(),
    })
    store.save_session(session)
    return {"session": session}
