"""
workbench/chat_flow.py
----------------------
The chat → proposal flow, split out of workbench/routes.py when it crossed
the 800-line gate: request models, the propose/degrade logic shared by the
plain POST and the SSE flavor, and the plan-confirmation endpoints.

The SSE flavor is the product path: the user watches the model write (stage +
text deltas), from-scratch stops at the design sheet for confirmation, and
only then is drafting time spent. The plain POST stays for non-interactive
callers (scripts, MCP) and auto-chains the same stages.

routes.py includes this module's router; imports flow strictly
routes → chat_flow, never back.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time

import yaml
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from core import messages
from core.spec_generator import generate_spec_async
from workbench import live_geometry, planner, store
from workbench import selection as selection_mod

# Used only when no solver can be probed. schema/spec_schema.json requires a
# year from its enum, so something has to go in the field — this value is
# always announced as a placeholder rather than reported as detected.
_FALLBACK_RELEASE = "2021"

MAX_MESSAGE_CHARS = 4000

router = APIRouter()


class ChatRequest(BaseModel):
    text: str
    backend: str = Field(default="auto", pattern="^(auto|claude_cli|template)$")
    # @-mentions. Each entry is a tree-row ref ({"ref": "part:Plate", ...}) or
    # a viewport pick ({"kind": "selector", "selector": "P:face@box=...", ...}).
    # Resolved server-side against the SAME spec text the tree drew; a ref
    # that does not resolve is a 400 naming it, never a silent drop.
    selection: list[dict] = Field(default_factory=list)
    # The UI's language, not the browser's: a user who switched the interface
    # to English wants the assistant to answer in English regardless of what
    # Accept-Language says. Empty falls back to the header, then the process
    # default.
    lang: str = ""


class PlanConfirmRequest(BaseModel):
    # The design sheet as the user confirmed it — possibly edited. Empty means
    # "use the stored sheet unchanged".
    plan: str = ""
    lang: str = ""


def get_session_or_404(session_id: str) -> dict:
    session = store.load_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
    return session


# Stage of each in-flight claude_cli proposal, keyed by session id and read by
# the progress endpoint. A from-scratch proposal holds its chat POST for up to
# 4 CLI calls' worth of wall time; without this the UI can only show seconds
# ticking. Plain dict: uvicorn runs single-process, and the one writer is the
# to_thread worker.
_PROPOSE_STAGE: dict[str, str] = {}


def _sse(event: str, payload: dict) -> str:
    return "event: %s\ndata: %s\n\n" % (
        event, json.dumps(payload, separators=(",", ":"), ensure_ascii=False))


# Throttle for the live-geometry parse: the draft streams several deltas a
# second and each parse walks the whole accumulated YAML, so parsing per delta
# would burn the worker thread for no visible gain — a part appearing within a
# second of being written already reads as live.
_GEOM_INTERVAL_S = 1.0


async def _run_streaming(sid: str, work):
    """Bridge a sync planner call into an async event stream.

    `work(on_stage, on_text, on_think)` runs in a thread and RETURNS the
    terminal event as ("plan"/"proposal"/"error", payload); its callbacks
    surface here as ("stage"/"text"/"think"/"geom", payload) items along the
    way. EVERYTHING the flow must not lose on a client disconnect — saving the
    session, the error message, the degraded template proposal — happens inside
    the worker before it returns: the consumer of this generator dies with the
    connection, the thread does not, so a disconnect changes what the user
    sees, never what happened."""
    loop = asyncio.get_running_loop()
    events: asyncio.Queue = asyncio.Queue()

    def put(kind: str, payload) -> None:
        loop.call_soon_threadsafe(events.put_nowait, (kind, payload))

    def on_stage(stage: str) -> None:
        _PROPOSE_STAGE[sid] = stage
        put("stage", {"stage": stage})

    # The draft text so far, and what was last drawn from it. A `geom` event
    # only goes out when the drawable shape CHANGED, so a stream that spends a
    # minute writing steps and KPIs does not repaint the viewport 200 times.
    drafted: list[str] = []
    geom_state = {"t": 0.0, "sent": None}

    def on_text(chunk: str) -> None:
        put("text", {"text": chunk})
        drafted.append(chunk)
        now = time.monotonic()
        if now - geom_state["t"] < _GEOM_INTERVAL_S:
            return
        geom_state["t"] = now
        payload = live_geometry.preview_payload(
            live_geometry.partial_spec("".join(drafted)))
        if payload is None:
            return
        stamp = json.dumps(payload, separators=(",", ":"), sort_keys=True)
        if stamp != geom_state["sent"]:
            geom_state["sent"] = stamp
            put("geom", payload)

    def on_think(chunk: str) -> None:
        put("think", {"text": chunk})

    def run() -> None:
        try:
            put("__outcome__", work(on_stage, on_text, on_think))
        except Exception as e:  # noqa: BLE001
            # ANY escape must still become the terminal event: a worker that
            # dies silently leaves the consumer awaiting a queue forever — no
            # terminal SSE event, a composer disabled for good, and the
            # exception itself unretrieved. Includes non-planner failures
            # (session save races, subprocess cleanup) on purpose.
            put("__outcome__", ("error", {
                "message": "%s: %s" % (type(e).__name__, e), "session": None}))
        finally:
            _PROPOSE_STAGE.pop(sid, None)

    worker = asyncio.create_task(asyncio.to_thread(run))
    while True:
        kind, payload = await events.get()
        if kind == "__outcome__":
            await worker
            yield "outcome", payload
            return
        yield kind, payload


def _finish_proposal(session: dict, spec_yaml: str, reply: str,
                     backend_used: str, missing: list) -> dict:
    """The tail every successful proposal shares (plain POST and SSE alike):
    build the pending record, append the assistant message, save."""
    proposal_id = "prop-" + hashlib.sha256(
        f"{session['session_id']}:{time.time_ns()}".encode()).hexdigest()[:10]
    pending = {
        "proposal_id": proposal_id,
        "spec_yaml": spec_yaml,
        "diff": planner.make_diff(session.get("current_spec_yaml"), spec_yaml),
        "summary": reply,
        "backend": backend_used,
        "missing_questions": missing,
        "created_at": time.time(),
    }
    session["pending"] = pending
    session["messages"].append({
        "role": "assistant", "text": reply, "ts": time.time(),
        "proposal_id": proposal_id, "backend": backend_used,
    })
    store.save_session(session)
    return pending


def _resolve_selection(session: dict, refs: list[dict]) -> list[dict]:
    """@-mentions resolve against the SAME spec text the tree drew — the
    pending proposal when there is one, else the accepted spec. Resolving
    against the other one answers about an object the user is not looking at."""
    if not refs:
        return []
    pending = session.get("pending") or {}
    spec_text = pending.get("spec_yaml") or session.get("current_spec_yaml")
    try:
        spec_for_refs = yaml.safe_load(spec_text) if spec_text else None
        return selection_mod.resolve_refs(spec_for_refs, refs)
    except selection_mod.SelectionError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


def _append_user_message(session: dict, text: str,
                         resolved_selection: list[dict]) -> None:
    user_msg = {"role": "user", "text": text, "ts": time.time()}
    if resolved_selection:
        # Labels only: the chat transcript draws chips, and a fragment that was
        # true at send time reads as current state a day later.
        user_msg["refs"] = [item["label"] for item in resolved_selection]
    session["messages"].append(user_msg)
    if session["title"] == "新会话":
        session["title"] = text[:40]


def _validated_text(req: ChatRequest) -> str:
    text = req.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Empty message")
    if len(text) > MAX_MESSAGE_CHARS:
        raise HTTPException(status_code=400,
                            detail=f"Message too long (>{MAX_MESSAGE_CHARS})")
    return text


async def _propose(session: dict, text: str, lang: str,
                   backend: str,
                   selection: list[dict] | None = None
                   ) -> tuple[dict | None, str, str, list, str]:
    """Returns (spec_dict, spec_yaml, reply, missing_questions, backend_used).
    spec_dict None = hard failure."""
    current = session.get("current_spec_yaml")
    history = session.get("messages", [])

    if backend in ("auto", "claude_cli") and planner.claude_cli_available():
        sid = session.get("session_id", "")

        def _note(stage: str) -> None:
            _PROPOSE_STAGE[sid] = stage

        try:
            spec, spec_yaml, reply = await asyncio.to_thread(
                planner.propose_with_claude, text, current, history, selection,
                progress=_note)
            return spec, spec_yaml, reply, [], "claude_cli"
        except planner.PlannerUnavailable:
            pass
        except planner.PlannerError as e:
            if backend == "claude_cli":
                return None, "", messages.render("planner.claude_failed", lang,
                                             error=str(e)), [], "claude_cli"
            reply_prefix = f"（Claude 规划失败已降级模板：{str(e)[:120]}）\n"
            spec, spec_yaml, reply, missing = await _propose_template(
                session, text, lang, selection)
            return spec, spec_yaml, reply_prefix + reply, missing, "template"
        finally:
            _PROPOSE_STAGE.pop(sid, None)
    elif backend == "claude_cli":
        return None, "", messages.render("planner.cli_unavailable", lang), [], "claude_cli"

    spec, spec_yaml, reply, missing = await _propose_template(
        session, text, lang, selection)
    return spec, spec_yaml, reply, missing, "template"


async def _propose_template(session: dict, text: str, lang: str = "",
                            selection: list[dict] | None = None
                            ) -> tuple[dict, str, str, list]:
    user_texts = [m.get("text", "") for m in session.get("messages", [])
                  if m.get("role") == "user"]
    if text not in user_texts:
        user_texts.append(text)
    combined = "\n".join(user_texts)[-2000:]
    # Probe, never assert. A hardcoded "2024" here put a release this machine
    # does not have into the proposed spec, onto the workbench screen and into
    # the archived report — the class of defect P2-d fixed everywhere else
    # (core/pipeline.py detects the release at run time).
    #
    # meta.abaqus_release is a required year enum in schema/spec_schema.json,
    # so an undetected solver cannot be written as "unknown". It falls back —
    # but the fallback is stated in the reply instead of passing for a fact.
    from tools.abaqus_cmd import detect_abaqus_release
    detected = detect_abaqus_release()
    release = detected or _FALLBACK_RELEASE
    spec, missing = await generate_spec_async(combined, release=release, backend="template")
    spec_yaml = yaml.dump(spec, allow_unicode=True, default_flow_style=False, sort_keys=False)
    reply = "已用模板引擎生成 spec 提案（离线模式，按关键词推断）。"
    if not detected:
        reply += ("\n⚠ 未检测到已安装的 Abaqus，spec 里的版本号 %s 是占位默认值、不是实测结果；"
                  "真正求解时会以运行时探测到的版本为准。" % release)
    if missing:
        reply += "\n待确认信息：" + "；".join(str(q) for q in missing[:5])
    if selection:
        # The template engine matches keywords and cannot aim an edit at an
        # object, and pretending otherwise is worse than saying so.
        reply += ("\n已看到你 @ 的：%s。模板引擎按关键词工作，"
                  "@ 引用只有 Claude 后端能精确落到对象上。"
                  % "、".join(str(item.get("label")) for item in selection))
    return spec, spec_yaml, reply, list(missing or [])


def _claude_failure_outcome(sid: str, fallback_session: dict, text: str,
                            lang: str, backend: str, selection: list[dict],
                            error_text: str) -> tuple[str, dict]:
    """Persist a claude failure FROM THE WORKER THREAD — a client disconnect
    must not change what happened, only what was watched. backend=claude_cli
    records the error message; auto degrades to the template engine, run
    synchronously right here (asyncio.run is legal in a worker thread)."""
    fresh = store.load_session(sid) or fallback_session
    if backend == "claude_cli":
        reply = messages.render("planner.claude_failed", lang, error=error_text)
        fresh["messages"].append({"role": "assistant", "text": reply,
                                  "ts": time.time(), "error": True})
        store.save_session(fresh)
        return "error", {"message": reply, "session": fresh}
    prefix = f"（Claude 规划失败已降级模板：{error_text[:120]}）\n"
    _spec, spec_yaml, reply, missing = asyncio.run(
        _propose_template(fresh, text, lang, selection))
    pending = _finish_proposal(fresh, spec_yaml, prefix + reply,
                               "template", missing)
    return "proposal", {"session": fresh, "pending": pending}


@router.post("/api/workbench/sessions/{session_id}/chat")
async def chat(session_id: str, req: ChatRequest):
    session = get_session_or_404(session_id)
    text = _validated_text(req)
    resolved_selection = _resolve_selection(session, req.selection)
    _append_user_message(session, text, resolved_selection)
    # Same semantics as the SSE flavor: a new message supersedes any design
    # sheet still awaiting confirmation — a stale sheet confirmed later would
    # draft an intent the user already moved past.
    session["pending_plan"] = None

    spec, spec_yaml, reply, missing, backend_used = await _propose(
        session, text, req.lang, req.backend, resolved_selection)

    if spec is None:
        session["messages"].append(
            {"role": "assistant", "text": reply, "ts": time.time(), "error": True})
        store.save_session(session)
        return {"session": session, "pending": None}

    pending = _finish_proposal(session, spec_yaml, reply, backend_used, missing)
    return {"session": session, "pending": pending}


@router.post("/api/workbench/sessions/{session_id}/chat/stream")
async def chat_stream(session_id: str, req: ChatRequest):
    """SSE flavor of /chat — the user watches the model work instead of staring
    at a spinner. Events: `stage` (plan/draft/repair-N), `think` (the reasoning
    that fills the minutes before the first written word — measured at 176
    deltas over 170 s on a plan call), `text` (the answer as it is written),
    `geom` (the drawable shape of the half-written spec, so the viewport fills
    in as parts are typed), then exactly one terminal event: `plan`
    (from-scratch stops at the design sheet for the user to confirm),
    `proposal`, or `error`. Template and degradation paths emit their terminal
    event with no stream at all, so the frontend has a single code path."""
    session = get_session_or_404(session_id)
    text = _validated_text(req)
    resolved_selection = _resolve_selection(session, req.selection)
    _append_user_message(session, text, resolved_selection)
    # A new message supersedes any design sheet still awaiting confirmation.
    session["pending_plan"] = None
    store.save_session(session)

    current = session.get("current_spec_yaml")
    history = session.get("messages", [])
    sid = session["session_id"]
    use_claude = (req.backend in ("auto", "claude_cli")
                  and planner.claude_cli_available())

    def work(on_stage, on_text, on_think):
        # Persistence targets a FRESH load of the session: this thread holds
        # its snapshot for minutes, and saving the snapshot would roll back
        # whatever accept/reject/enrich wrote in the meantime — measured
        # consequence: a solve's run record vanishing, and with it the
        # single-license active-run gate.
        try:
            if current:
                _spec, spec_yaml, reply = planner.propose_with_claude(
                    text, current, history, resolved_selection,
                    progress=on_stage, on_text=on_text, on_think=on_think)
                fresh = store.load_session(sid) or session
                pending = _finish_proposal(fresh, spec_yaml, reply,
                                           "claude_cli", [])
                return "proposal", {"session": fresh, "pending": pending}
            on_stage("plan")
            plan = planner.plan_with_claude(text, history, resolved_selection,
                                            on_text=on_text, on_think=on_think)
            fresh = store.load_session(sid) or session
            fresh["pending_plan"] = {
                "instruction": text,
                "plan": plan,
                "selection": resolved_selection,
                "created_at": time.time(),
            }
            store.save_session(fresh)
            return "plan", {"session": fresh}
        except (planner.PlannerUnavailable, planner.PlannerError) as e:
            return _claude_failure_outcome(sid, session, text, req.lang,
                                           req.backend, resolved_selection,
                                           str(e))

    async def gen():
        if not use_claude:
            if req.backend == "claude_cli":
                reply = messages.render("planner.cli_unavailable", req.lang)
                session["messages"].append({"role": "assistant", "text": reply,
                                            "ts": time.time(), "error": True})
                store.save_session(session)
                yield _sse("error", {"message": reply, "session": session})
                return
            spec, spec_yaml, reply, missing = await _propose_template(
                session, text, req.lang, resolved_selection)
            pending = _finish_proposal(session, spec_yaml, reply,
                                       "template", missing)
            yield _sse("proposal", {"session": session, "pending": pending})
            return

        async for kind, payload in _run_streaming(sid, work):
            if kind == "outcome":
                status, value = payload
                yield _sse(status, value)
            else:
                yield _sse(kind, payload)

    return StreamingResponse(gen(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no",
                 "Connection": "keep-alive"})


@router.post("/api/workbench/sessions/{session_id}/plan/confirm")
async def plan_confirm(session_id: str, req: PlanConfirmRequest):
    """Draft the confirmed (possibly user-edited) design sheet into a spec.
    SSE with the same event vocabulary as /chat/stream. A failed draft keeps
    the sheet so the user can edit and retry instead of replanning."""
    session = get_session_or_404(session_id)
    pending_plan = session.get("pending_plan")
    if not pending_plan:
        raise HTTPException(status_code=400,
                            detail="No design sheet awaiting confirmation")
    plan_text = req.plan.strip() or pending_plan.get("plan", "")
    if not plan_text:
        raise HTTPException(status_code=400, detail="Empty design sheet")
    pending_plan["plan"] = plan_text
    store.save_session(session)

    instruction = pending_plan.get("instruction", "")
    selection = pending_plan.get("selection") or []
    history = session.get("messages", [])
    sid = session["session_id"]

    def work(on_stage, on_text, on_think):
        try:
            _spec, spec_yaml, reply = planner.draft_with_claude(
                instruction, plan_text, history, selection,
                progress=on_stage, on_text=on_text, on_think=on_think)
        except (planner.PlannerUnavailable, planner.PlannerError) as e:
            # Persisted here in the worker — a disconnected client must still
            # find the failure in the transcript. The sheet stays (it is on
            # disk already) so the user edits and retries instead of
            # replanning.
            fresh = store.load_session(sid) or session
            reply = messages.render("planner.claude_failed", req.lang,
                                    error=str(e))
            fresh["messages"].append({"role": "assistant", "text": reply,
                                      "ts": time.time(), "error": True})
            store.save_session(fresh)
            return "error", {"message": reply, "session": fresh}
        fresh = store.load_session(sid) or session
        fresh["pending_plan"] = None
        pending = _finish_proposal(fresh, spec_yaml, reply, "claude_cli", [])
        return "proposal", {"session": fresh, "pending": pending}

    async def gen():
        async for kind, payload in _run_streaming(sid, work):
            if kind == "outcome":
                status, value = payload
                yield _sse(status, value)
            else:
                yield _sse(kind, payload)

    return StreamingResponse(gen(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no",
                 "Connection": "keep-alive"})


@router.post("/api/workbench/sessions/{session_id}/plan/cancel")
async def plan_cancel(session_id: str):
    """Drop the design sheet awaiting confirmation. No chat message is added —
    the card disappearing IS the feedback, and nothing was generated yet."""
    session = get_session_or_404(session_id)
    if session.get("pending_plan"):
        session["pending_plan"] = None
        store.save_session(session)
    return {"session": session}


@router.get("/api/workbench/sessions/{session_id}/progress")
async def chat_progress(session_id: str):
    """Stage of the in-flight claude_cli proposal (plan / draft / repair-N),
    null when none. Read-only side channel for the UI to poll while the chat
    POST is still holding its connection."""
    return {"stage": _PROPOSE_STAGE.get(session_id)}
