"""Workbench API tests: sessions, chat proposals, diff-accept, reject.

Hermetic: Abaqus is hidden by conftest, and the claude CLI path is either
monkeypatched out or fed canned output — no real LLM calls, no real solves.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from workbench import planner


@pytest.fixture
def wb(monkeypatch, tmp_path):
    import server

    monkeypatch.setenv("ABAQUS_AGENT_WORKBENCH_SESSION_DIR", str(tmp_path / "wb_sessions"))
    # Hermetic: never let tests shell out to a real claude CLI.
    monkeypatch.setattr(planner, "claude_cli_available", lambda: False)
    original_runs = dict(server.RUNS)
    server.RUNS.clear()
    try:
        yield server
    finally:
        server.RUNS.clear()
        server.RUNS.update(original_runs)


@pytest.fixture
def client(wb):
    return TestClient(wb.app, raise_server_exceptions=False)


async def _fake_pipeline_completed(run_id: str, runs: dict, on_stage_update=None) -> None:
    runs[run_id]["status"] = "COMPLETED"
    runs[run_id]["progress_pct"] = 100
    runs[run_id]["kpis"] = {"U_tip": {"value": -1.9e-3, "unit": "mm"}}
    runs[run_id]["orchestrator_result"] = {
        "visuals": [{"file": "C:/some/workdir/Model_mises.png", "label": "Mises"}],
        "animation": {"frames": 12, "video": "anim.mp4"},
    }


async def _fake_pipeline_stuck_running(run_id: str, runs: dict, on_stage_update=None) -> None:
    runs[run_id]["status"] = "RUNNING"


def _chat(client, sid: str, text: str, backend: str = "template") -> dict:
    resp = client.post(f"/api/workbench/sessions/{sid}/chat",
                       json={"text": text, "backend": backend})
    assert resp.status_code == 200, resp.text
    return resp.json()


# ── Sessions ─────────────────────────────────────────────────────────────────

def test_session_create_list_get(client):
    created = client.post("/api/workbench/sessions", json={"title": "悬臂梁试算"}).json()
    sid = created["session_id"]
    assert sid.startswith("wb-")
    assert created["title"] == "悬臂梁试算"
    assert created["pending"] is None

    listed = client.get("/api/workbench/sessions").json()["sessions"]
    assert any(s["session_id"] == sid for s in listed)

    fetched = client.get(f"/api/workbench/sessions/{sid}").json()
    assert fetched["session_id"] == sid


def test_session_get_missing_and_traversal_rejected(client):
    assert client.get("/api/workbench/sessions/wb-nonexist000").status_code == 404
    assert client.get("/api/workbench/sessions/wb-..%2F..%2Fetc").status_code == 404


# ── Chat proposals ───────────────────────────────────────────────────────────

def test_chat_template_creates_proposal_with_diff(client):
    sid = client.post("/api/workbench/sessions", json={}).json()["session_id"]
    data = _chat(client, sid, "帮我建一个悬臂梁，钢，末端集中力")

    pending = data["pending"]
    assert pending is not None
    assert pending["backend"] == "template"
    assert "cantilever" in pending["spec_yaml"]
    # First proposal diffs against an empty spec: everything is an addition.
    assert "+geometry:" in pending["diff"] or "+  type: cantilever_block" in pending["diff"]

    session = data["session"]
    assert session["title"] != "新会话"
    roles = [m["role"] for m in session["messages"]]
    assert roles == ["user", "assistant"]


def test_chat_keyword_enrichment_modal(client):
    sid = client.post("/api/workbench/sessions", json={}).json()["session_id"]
    data = _chat(client, sid, "改成模态分析，提取前两阶频率")
    assert "Frequency" in data["pending"]["spec_yaml"]


def test_chat_empty_message_rejected(client):
    sid = client.post("/api/workbench/sessions", json={}).json()["session_id"]
    resp = client.post(f"/api/workbench/sessions/{sid}/chat",
                       json={"text": "   ", "backend": "template"})
    assert resp.status_code == 400


def test_chat_claude_cli_unavailable_reports_error(client):
    sid = client.post("/api/workbench/sessions", json={}).json()["session_id"]
    resp = client.post(f"/api/workbench/sessions/{sid}/chat",
                       json={"text": "悬臂梁", "backend": "claude_cli"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["pending"] is None
    assert data["session"]["messages"][-1].get("error") is True


# ── Accept / reject ──────────────────────────────────────────────────────────

def test_accept_runs_pipeline_and_syncs_session(client, wb, monkeypatch):
    from workbench import routes

    monkeypatch.setattr(routes, "run_pipeline", _fake_pipeline_completed)
    sid = client.post("/api/workbench/sessions", json={}).json()["session_id"]
    _chat(client, sid, "悬臂梁 100x10x10，末端 1N")

    resp = client.post(f"/api/workbench/sessions/{sid}/accept", json={})
    assert resp.status_code == 200, resp.text
    run_id = resp.json()["run_id"]
    assert run_id in wb.RUNS

    session = client.get(f"/api/workbench/sessions/{sid}").json()
    assert session["pending"] is None
    assert session["current_spec_yaml"]
    record = session["runs"][0]
    assert record["run_id"] == run_id
    assert record["status"] == "COMPLETED"
    assert record["kpis"]["U_tip"]["value"] == pytest.approx(-1.9e-3)
    assert record["visuals"] == ["Model_mises.png"]
    assert record["animation"] == "anim.mp4"


def test_accept_without_pending_409(client):
    sid = client.post("/api/workbench/sessions", json={}).json()["session_id"]
    assert client.post(f"/api/workbench/sessions/{sid}/accept", json={}).status_code == 409


def test_accept_defaults_the_runner_cfg_and_the_caller_wins(client, wb, monkeypatch):
    """An empty runner_cfg must NOT fall through to the orchestrator's bare
    defaults (cpus=1, 30-minute ceiling): measured 2026-08-08, bearing_block
    accepted through this endpoint died inside them, while every shipped
    runner.json runs cpus=2. Caller-provided values always win."""
    from workbench import routes

    monkeypatch.setattr(routes, "run_pipeline", _fake_pipeline_completed)
    sid = client.post("/api/workbench/sessions", json={}).json()["session_id"]
    _chat(client, sid, "悬臂梁 100x10x10，末端 1N")
    run_id = client.post(f"/api/workbench/sessions/{sid}/accept",
                         json={}).json()["run_id"]
    assert wb.RUNS[run_id]["runner_cfg"] == {"cpus": 2, "timeout_seconds": 7200}

    _chat(client, sid, "载荷改大一点")
    run_id = client.post(
        f"/api/workbench/sessions/{sid}/accept",
        json={"runner_cfg": {"cpus": 8, "timeout_seconds": 600}},
    ).json()["run_id"]
    assert wb.RUNS[run_id]["runner_cfg"] == {"cpus": 8, "timeout_seconds": 600}


def test_accept_blocked_while_run_active(client, monkeypatch):
    from workbench import routes

    monkeypatch.setattr(routes, "run_pipeline", _fake_pipeline_stuck_running)
    sid = client.post("/api/workbench/sessions", json={}).json()["session_id"]
    _chat(client, sid, "悬臂梁")
    assert client.post(f"/api/workbench/sessions/{sid}/accept", json={}).status_code == 200

    _chat(client, sid, "载荷改大一点")
    resp = client.post(f"/api/workbench/sessions/{sid}/accept", json={})
    assert resp.status_code == 409
    assert "active" in resp.json()["detail"]


def test_reject_clears_pending_keeps_spec(client):
    sid = client.post("/api/workbench/sessions", json={}).json()["session_id"]
    _chat(client, sid, "悬臂梁")
    resp = client.post(f"/api/workbench/sessions/{sid}/reject")
    assert resp.status_code == 200
    session = resp.json()["session"]
    assert session["pending"] is None
    assert session["current_spec_yaml"] is None


def test_session_persists_across_store_reload(client, tmp_path):
    from workbench import store

    sid = client.post("/api/workbench/sessions", json={}).json()["session_id"]
    _chat(client, sid, "开孔板拉伸")
    reloaded = store.load_session(sid)
    assert reloaded is not None
    assert reloaded["pending"] is not None
    assert reloaded["messages"][0]["text"] == "开孔板拉伸"


# ── Static page contract ─────────────────────────────────────────────────────

def test_workbench_page_served(client):
    resp = client.get("/workbench")
    assert resp.status_code == 200
    html = resp.text
    for marker in ("ABQ", "chat-input", "/api/workbench/sessions",
                   "vendor/three.min.js", "workbench_viewport.js", "vp-slot"):
        assert marker in html


def test_every_asset_the_workbench_asks_for_is_actually_served(client):
    """The UI copy moved out of the page when it was split, and so did the
    stylesheet. A markup file that references four assets and gets a 404 on one
    of them still returns 200 for itself -- the page just arrives unstyled, or
    with every label blank, which is what this checks instead."""
    import re

    html = client.get("/workbench").text
    refs = set(re.findall(r'(?:src|href)="(/static/[^"]+)"', html))
    assert "/static/workbench.css" in refs
    assert "/static/workbench_i18n.js" in refs
    for ref in sorted(refs):
        asset = client.get(ref)
        assert asset.status_code == 200, "%s -> %d" % (ref, asset.status_code)

    # The Chinese UI copy used to be inline in the page; it is in the
    # catalogue now, and it still has to reach the browser.
    catalogue = client.get("/static/workbench_i18n.js").text
    for marker in ("变更提案", "接受并求解"):
        assert marker in catalogue


# ── Planner unit tests ───────────────────────────────────────────────────────

_VALID_SPEC_YAML = """meta:
  abaqus_release: "2024"
  model_name: "TestBeam"
  units: "mm_MPa_t"
geometry:
  type: cantilever_block
  L: 100.0
  W: 10.0
  H: 10.0
material:
  name: Steel
  E: 210000.0
  nu: 0.3
analysis:
  solver: standard
  step_type: Static
  cpus: 1
bc_load:
  fixed_face: "x=0"
  load_face: "x=L"
  load_type: concentrated_force
  value: -1.0
outputs:
  kpis:
    - name: U_tip
      type: nodal_displacement
      location: tip_center
"""


def test_parse_response_plain_and_fenced():
    raw = f"===SPEC===\n{_VALID_SPEC_YAML}===REPLY===\n把梁建好了。"
    spec_yaml, reply = planner.parse_response(raw)
    assert "TestBeam" in spec_yaml
    assert reply == "把梁建好了。"

    fenced = f"===SPEC===\n```yaml\n{_VALID_SPEC_YAML}```\n===REPLY===\nok"
    spec_yaml2, _ = planner.parse_response(fenced)
    assert "TestBeam" in spec_yaml2


def test_parse_response_missing_marker_raises():
    with pytest.raises(planner.PlannerError):
        planner.parse_response("no markers here")


def test_build_prompt_includes_context():
    prompt = planner.build_prompt(
        "载荷改成 20N",
        "meta:\n  model_name: Old\n",
        [{"role": "user", "text": "建个悬臂梁"}],
    )
    assert "载荷改成 20N" in prompt
    assert "model_name: Old" in prompt
    assert "建个悬臂梁" in prompt


def test_propose_from_scratch_plans_then_drafts_then_repairs(monkeypatch):
    """From scratch is staged: a dialect-free plan call, then a draft under the
    full dialect, then validation repairs. One giant call was measured failing
    three times over (180 s / 900 s / >11 min) while staged calls are the shape
    the fast modify path already has."""
    calls = []

    def fake_call(prompt: str, model: str | None = None, on_text=None,
                  on_think=None) -> str:
        calls.append(prompt)
        if len(calls) == 1:
            return "【模型名】TestBeam\n【假设与待确认】无"
        if len(calls) == 2:
            return "===SPEC===\nmeta: {}\n===REPLY===\n半成品"
        return f"===SPEC===\n{_VALID_SPEC_YAML}===REPLY===\n修好了"

    stages = []
    monkeypatch.setattr(planner, "_call_claude", fake_call)
    spec, spec_yaml, reply = planner.propose_with_claude(
        "悬臂梁", None, [], progress=stages.append)

    assert len(calls) == 3
    # The plan prompt must stay small: no dialect doc, no output contract.
    assert planner._SPEC_MARK not in calls[0]
    assert "设计清单" in calls[0]
    # The design sheet reaches the draft prompt; the draft carries the dialect.
    assert "【模型名】TestBeam" in calls[1]
    assert planner._SPEC_MARK in calls[1]
    # meta.missing_questions has maxItems:5 in the schema. An assumption-heavy
    # from-scratch design easily lists more, and the validator's message for it
    # ("[...] is too long") names no field — so the draft prompt must state the
    # cap up front instead of burning a repair call on it.
    assert "上限 5 条" in calls[1]
    # The repair call carries the validation errors.
    assert "未通过 schema 校验" in calls[2]
    assert spec["meta"]["model_name"] == "TestBeam"
    # The user sees the design decisions, not just the transcription note.
    assert "【设计清单】" in reply and "修好了" in reply
    assert stages == ["plan", "draft", "repair-1"]


def test_propose_with_a_current_spec_stays_single_call(monkeypatch):
    """The modify path measured 50-100 s as one call — staging it would only
    add latency, so it must not grow a plan stage."""
    calls = []

    def fake_call(prompt: str, model: str | None = None, on_text=None,
                  on_think=None) -> str:
        calls.append(prompt)
        return f"===SPEC===\n{_VALID_SPEC_YAML}===REPLY===\n改好了"

    monkeypatch.setattr(planner, "_call_claude", fake_call)
    spec, _, reply = planner.propose_with_claude(
        "载荷改成 20N", "meta:\n  model_name: Old\n", [])
    assert len(calls) == 1
    assert "model_name: Old" in calls[0]
    assert reply == "改好了"


def test_from_scratch_plan_failures_name_their_stage(monkeypatch):
    """A staged path that can take minutes must say WHICH stage died — a bare
    'timed out' does not tell the user whether planning or drafting is slow."""
    def dead_cli(prompt: str, model: str | None = None, on_text=None,
                 on_think=None) -> str:
        raise planner.PlannerError("claude CLI timed out after 180s")

    monkeypatch.setattr(planner, "_call_claude", dead_cli)
    with pytest.raises(planner.PlannerError) as caught:
        planner.propose_with_claude("悬臂梁", None, [])
    assert "规划" in str(caught.value)
    assert "timed out" in str(caught.value)


def test_from_scratch_draft_failures_name_their_stage(monkeypatch):
    calls = []

    def fake_call(prompt: str, model: str | None = None, on_text=None,
                  on_think=None) -> str:
        calls.append(prompt)
        if len(calls) == 1:
            return "【模型名】TestBeam"
        raise planner.PlannerError("claude CLI timed out after 180s")

    monkeypatch.setattr(planner, "_call_claude", fake_call)
    with pytest.raises(planner.PlannerError) as caught:
        planner.propose_with_claude("悬臂梁", None, [])
    assert "落稿" in str(caught.value)


def test_a_timeout_still_reports_the_earlier_attempts_validation_errors(monkeypatch):
    """A bearing run burned 35 minutes on two invalid drafts plus a timeout,
    and the report only said 'timed out' — the validation errors, the one clue
    to why the drafts were invalid, died with the last attempt."""
    calls = []

    def fake_call(prompt: str, model: str | None = None, on_text=None,
                  on_think=None) -> str:
        calls.append(prompt)
        if len(calls) == 1:
            return "【模型名】TestBeam"
        if len(calls) == 2:
            return "===SPEC===\nmeta: {}\n===REPLY===\n半成品"
        raise planner.PlannerError("claude CLI timed out after 480s")

    monkeypatch.setattr(planner, "_call_claude", fake_call)
    with pytest.raises(planner.PlannerError) as caught:
        planner.propose_with_claude("轴承座", None, [])
    msg = str(caught.value)
    assert "timed out" in msg
    assert "第1次输出未过校验" in msg


def test_propose_with_a_current_spec_retries_once_on_invalid(monkeypatch):
    """The modify path keeps exactly one validation retry: an invalid first
    response is re-asked with the error list appended, not surfaced raw."""
    calls = []

    def fake_call(prompt: str, model: str | None = None, on_text=None,
                  on_think=None) -> str:
        calls.append(prompt)
        if len(calls) == 1:
            return "===SPEC===\nmeta: {}\n===REPLY===\n半成品"
        return f"===SPEC===\n{_VALID_SPEC_YAML}===REPLY===\n修好了"

    monkeypatch.setattr(planner, "_call_claude", fake_call)
    spec, _, reply = planner.propose_with_claude(
        "载荷改成 20N", "meta:\n  model_name: Old\n", [])
    assert len(calls) == 2
    assert "未通过 schema 校验" in calls[1]
    assert reply == "修好了"


def test_propose_with_a_current_spec_gives_up_after_two_calls(monkeypatch):
    """attempts=2 is a measured budget (50-100 s per call), not a loop bound
    that may quietly grow."""
    calls = []

    def fake_call(prompt: str, model: str | None = None, on_text=None,
                  on_think=None) -> str:
        calls.append(prompt)
        return "===SPEC===\nmeta: {}\n===REPLY===\n还是坏的"

    monkeypatch.setattr(planner, "_call_claude", fake_call)
    with pytest.raises(planner.PlannerError):
        planner.propose_with_claude("改", "meta:\n  model_name: Old\n", [])
    assert len(calls) == 2


def test_the_draft_model_covers_draft_and_repair_but_not_plan_or_modify(monkeypatch):
    """Plan decides, draft transcribes: the from-scratch draft/repair calls go
    to CLAUDE_DRAFT_MODEL while the plan call and the whole modify path stay on
    CLAUDE_MODEL (model=None → _call_claude falls back to it)."""
    models = []

    def fake_call(prompt: str, model: str | None = None, on_text=None,
                  on_think=None) -> str:
        models.append(model)
        if planner._SPEC_MARK not in prompt:
            return "【模型名】TestBeam"
        return f"===SPEC===\n{_VALID_SPEC_YAML}===REPLY===\nok"

    monkeypatch.setattr(planner, "_call_claude", fake_call)
    monkeypatch.setattr(planner, "CLAUDE_DRAFT_MODEL", "haiku")

    planner.propose_with_claude("悬臂梁", None, [])
    assert models == [None, "haiku"]

    models.clear()
    planner.propose_with_claude("载荷改成 20N", "meta:\n  model_name: Old\n", [])
    assert models == [None]


def test_chat_wires_stage_progress_and_the_endpoint_reads_it(client, monkeypatch):
    """The stage callback exists for exactly one consumer — the UI polling
    /progress while the chat POST holds its connection for minutes. Wired
    through the chat route, populated during the call, cleared after (a stale
    stage would decorate the NEXT proposal with the last one's state)."""
    from workbench import chat_flow

    seen = {}

    def fake_propose(text, current, history, selection=None, progress=None):
        assert progress is not None
        progress("draft")
        seen["during_call"] = dict(chat_flow._PROPOSE_STAGE)
        return ({"meta": {"model_name": "X"}}, "meta:\n  model_name: X\n", "ok")

    monkeypatch.setattr(planner, "claude_cli_available", lambda: True)
    monkeypatch.setattr(planner, "propose_with_claude", fake_propose)

    sid = client.post("/api/workbench/sessions",
                      json={"title": "t"}).json()["session_id"]
    resp = client.post(f"/api/workbench/sessions/{sid}/chat",
                       json={"text": "建个悬臂梁", "backend": "claude_cli"})
    assert resp.status_code == 200
    assert seen["during_call"] == {sid: "draft"}
    assert client.get(f"/api/workbench/sessions/{sid}/progress"
                      ).json() == {"stage": None}


# ── Streaming chat + plan confirmation ──────────────────────────────────────

def _events(resp) -> list[tuple[str, object]]:
    import json as _json
    out = []
    for block in resp.text.split("\n\n"):
        if not block.strip():
            continue
        ev, data = "message", ""
        for line in block.split("\n"):
            if line.startswith("event: "):
                ev = line[7:]
            elif line.startswith("data: "):
                data += line[6:]
        out.append((ev, _json.loads(data) if data else None))
    return out


def test_chat_stream_from_scratch_stops_at_the_plan(client, monkeypatch):
    """The SSE flow pauses after the design sheet: the whole point of the
    split is that no drafting minutes are spent on unconfirmed assumptions."""
    def fake_plan(instruction, history, selection=None, on_text=None,
                  on_think=None):
        on_text("【模型名】")
        on_text("TestBeam")
        return "【模型名】TestBeam"

    monkeypatch.setattr(planner, "claude_cli_available", lambda: True)
    monkeypatch.setattr(planner, "plan_with_claude", fake_plan)

    sid = client.post("/api/workbench/sessions", json={}).json()["session_id"]
    resp = client.post(f"/api/workbench/sessions/{sid}/chat/stream",
                       json={"text": "建个轴承座", "backend": "claude_cli"})
    assert resp.status_code == 200
    events = _events(resp)
    assert [e for e, _ in events] == ["stage", "text", "text", "plan"]
    assert events[0][1] == {"stage": "plan"}
    assert events[1][1]["text"] == "【模型名】"
    sess = events[-1][1]["session"]
    assert sess["pending_plan"]["plan"] == "【模型名】TestBeam"
    assert sess["pending_plan"]["instruction"] == "建个轴承座"
    # Persisted by the worker, not just echoed — a dropped connection must not
    # lose a finished plan.
    stored = client.get(f"/api/workbench/sessions/{sid}").json()
    assert stored["pending_plan"]["plan"] == "【模型名】TestBeam"


def test_plan_confirm_drafts_the_edited_sheet(client, monkeypatch):
    captured = {}

    def fake_draft(instruction, plan, history, selection=None,
                   progress=None, on_text=None, on_think=None):
        captured["plan"] = plan
        progress("draft")
        on_text("meta:")
        import yaml as _yaml
        return _yaml.safe_load(_VALID_SPEC_YAML), _VALID_SPEC_YAML, "落好了"

    monkeypatch.setattr(planner, "claude_cli_available", lambda: True)
    monkeypatch.setattr(planner, "plan_with_claude",
                        lambda *a, **k: "【模型名】X")
    monkeypatch.setattr(planner, "draft_with_claude", fake_draft)

    sid = client.post("/api/workbench/sessions", json={}).json()["session_id"]
    client.post(f"/api/workbench/sessions/{sid}/chat/stream",
                json={"text": "建个轴承座", "backend": "claude_cli"})
    resp = client.post(f"/api/workbench/sessions/{sid}/plan/confirm",
                       json={"plan": "【模型名】X\n【材料】改成铝"})
    assert resp.status_code == 200
    events = _events(resp)
    assert [e for e, _ in events] == ["stage", "text", "proposal"]
    # What gets drafted is the sheet as the user edited it.
    assert captured["plan"] == "【模型名】X\n【材料】改成铝"
    final = events[-1][1]
    assert final["pending"]["spec_yaml"] == _VALID_SPEC_YAML
    assert final["session"]["pending_plan"] is None
    assert final["session"]["pending"]["proposal_id"] == final["pending"]["proposal_id"]

    # With the sheet consumed, confirming again is a named 400, not a rerun.
    resp2 = client.post(f"/api/workbench/sessions/{sid}/plan/confirm", json={})
    assert resp2.status_code == 400


def test_plan_confirm_failure_keeps_the_sheet_for_retry(client, monkeypatch):
    def dead_draft(*a, **k):
        raise planner.PlannerError("落稿（draft）阶段失败：claude CLI timed out after 600s")

    monkeypatch.setattr(planner, "claude_cli_available", lambda: True)
    monkeypatch.setattr(planner, "plan_with_claude", lambda *a, **k: "【模型名】X")
    monkeypatch.setattr(planner, "draft_with_claude", dead_draft)

    sid = client.post("/api/workbench/sessions", json={}).json()["session_id"]
    client.post(f"/api/workbench/sessions/{sid}/chat/stream",
                json={"text": "建个轴承座", "backend": "claude_cli"})
    resp = client.post(f"/api/workbench/sessions/{sid}/plan/confirm", json={})
    events = _events(resp)
    assert events[-1][0] == "error"
    assert "落稿" in events[-1][1]["message"]
    # The sheet survives the failure — edit and retry, don't replan.
    stored = client.get(f"/api/workbench/sessions/{sid}").json()
    assert stored["pending_plan"]["plan"] == "【模型名】X"
    assert stored["messages"][-1]["error"] is True


def test_plan_cancel_clears_the_sheet(client, monkeypatch):
    monkeypatch.setattr(planner, "claude_cli_available", lambda: True)
    monkeypatch.setattr(planner, "plan_with_claude", lambda *a, **k: "【模型名】X")

    sid = client.post("/api/workbench/sessions", json={}).json()["session_id"]
    client.post(f"/api/workbench/sessions/{sid}/chat/stream",
                json={"text": "建个轴承座", "backend": "claude_cli"})
    resp = client.post(f"/api/workbench/sessions/{sid}/plan/cancel")
    assert resp.json()["session"]["pending_plan"] is None
    stored = client.get(f"/api/workbench/sessions/{sid}").json()
    assert stored["pending_plan"] is None


def test_chat_stream_modify_path_goes_straight_to_a_proposal(client, monkeypatch):
    """With a current spec there is nothing to confirm — the modify path
    streams the one draft call and lands on the proposal."""
    from workbench import store as wb_store

    def fake_propose(text, current, history, selection=None,
                     progress=None, on_text=None, on_think=None):
        assert current == "meta:\n  model_name: Old\n"
        progress("draft")
        on_text("meta:\n")
        import yaml as _yaml
        return _yaml.safe_load(_VALID_SPEC_YAML), _VALID_SPEC_YAML, "改好了"

    monkeypatch.setattr(planner, "claude_cli_available", lambda: True)
    monkeypatch.setattr(planner, "propose_with_claude", fake_propose)

    sid = client.post("/api/workbench/sessions", json={}).json()["session_id"]
    sess = wb_store.load_session(sid)
    sess["current_spec_yaml"] = "meta:\n  model_name: Old\n"
    wb_store.save_session(sess)

    resp = client.post(f"/api/workbench/sessions/{sid}/chat/stream",
                       json={"text": "载荷改成 20N", "backend": "claude_cli"})
    events = _events(resp)
    assert [e for e, _ in events] == ["stage", "text", "proposal"]
    assert events[-1][1]["pending"]["backend"] == "claude_cli"


def test_a_new_message_supersedes_the_pending_sheet(client, monkeypatch):
    """Typing something new instead of confirming means the user moved on —
    the stale sheet must not survive next to a fresh proposal flow."""
    monkeypatch.setattr(planner, "claude_cli_available", lambda: True)
    monkeypatch.setattr(planner, "plan_with_claude", lambda *a, **k: "【模型名】X")

    sid = client.post("/api/workbench/sessions", json={}).json()["session_id"]
    client.post(f"/api/workbench/sessions/{sid}/chat/stream",
                json={"text": "建个轴承座", "backend": "claude_cli"})
    resp = client.post(f"/api/workbench/sessions/{sid}/chat/stream",
                       json={"text": "建个悬臂梁", "backend": "template"})
    events = _events(resp)
    assert events[-1][0] == "proposal"          # template path: one terminal event
    assert events[-1][1]["session"]["pending_plan"] is None
    assert events[-1][1]["pending"]["backend"] == "template"


def test_the_reasoning_streams_as_its_own_event_and_stays_out_of_the_spec(
        client, monkeypatch):
    """Measured on a real plan call: 176 thinking deltas over 170 s BEFORE the
    first written word. Dropping them is what made the UI look frozen. They
    stream as `think`, never joined into the answer — parse_response would
    otherwise be handed the model's musings."""
    def fake_plan(instruction, history, selection=None, on_text=None,
                  on_think=None):
        on_think("用户要一个轴承座，")
        on_think("先定单位制。")
        on_text("【模型名】X")
        return "【模型名】X"

    monkeypatch.setattr(planner, "claude_cli_available", lambda: True)
    monkeypatch.setattr(planner, "plan_with_claude", fake_plan)

    sid = client.post("/api/workbench/sessions", json={}).json()["session_id"]
    resp = client.post(f"/api/workbench/sessions/{sid}/chat/stream",
                       json={"text": "建个轴承座", "backend": "claude_cli"})
    events = _events(resp)
    assert [e for e, _ in events] == ["stage", "think", "think", "text", "plan"]
    assert events[1][1]["text"] == "用户要一个轴承座，"
    # The sheet that gets stored is the answer only.
    assert events[-1][1]["session"]["pending_plan"]["plan"] == "【模型名】X"


def test_a_thinking_delta_is_parsed_as_thinking_not_as_answer_text():
    """The two delta types differ by one field name. Getting it wrong either
    way is silent: thinking joined into the answer poisons the YAML, and an
    answer routed to `think` shows the user nothing."""
    import json as _json
    think_line = _json.dumps({"type": "stream_event", "event": {
        "type": "content_block_delta",
        "delta": {"type": "thinking_delta", "thinking": "先定单位制"}}})
    text_line = _json.dumps({"type": "stream_event", "event": {
        "type": "content_block_delta",
        "delta": {"type": "text_delta", "text": "meta:"}}})
    assert planner._parse_stream_line(think_line) == (None, "先定单位制", None)
    assert planner._parse_stream_line(text_line) == ("meta:", None, None)
    assert planner._parse_stream_line("not json") == (None, None, None)


def test_the_draft_streams_drawable_geometry_before_it_finishes(
        client, monkeypatch):
    """The viewport used to stay empty for the whole draft. Now each part is
    drawable as soon as its extrude is written — the `geom` event carries the
    shape, not a mesh, and nothing has run to produce it."""
    import time as _time

    def fake_draft(instruction, plan, history, selection=None,
                   progress=None, on_text=None, on_think=None):
        progress("draft")
        head, tail = _V2_HOLE_SPEC_YAML.split("assembly:", 1)
        on_text("===SPEC===\n" + head)
        # The throttle is wall-clock; without this the second half arrives in
        # the same tick and only one geom event is emitted.
        _time.sleep(1.1)
        on_text("assembly:" + tail + "===REPLY===\n落好了")
        import yaml as _yaml
        return (_yaml.safe_load(_V2_HOLE_SPEC_YAML), _V2_HOLE_SPEC_YAML, "落好了")

    monkeypatch.setattr(planner, "claude_cli_available", lambda: True)
    monkeypatch.setattr(planner, "plan_with_claude", lambda *a, **k: "【模型名】X")
    monkeypatch.setattr(planner, "draft_with_claude", fake_draft)

    sid = client.post("/api/workbench/sessions", json={}).json()["session_id"]
    client.post(f"/api/workbench/sessions/{sid}/chat/stream",
                json={"text": "开孔板", "backend": "claude_cli"})
    resp = client.post(f"/api/workbench/sessions/{sid}/plan/confirm", json={})
    events = _events(resp)
    kinds = [e for e, _ in events]
    assert "geom" in kinds
    assert kinds.index("geom") < kinds.index("proposal")   # DURING the draft
    geoms = [d for e, d in events if e == "geom"]
    assert [p["name"] for p in geoms[0]["parts"]] == ["Plate"]
    assert geoms[0]["parts"][0]["holes"][0]["r"] == 6.0
    # The part draws before the assembly block exists, then again once the
    # placement is written: one event per CHANGE in the drawable shape, not
    # one per delta — a stream that keeps writing steps and KPIs after the
    # geometry is settled must not repaint the viewport on every token.
    assert kinds.count("geom") == 2
    assert geoms[0]["instances"] == []
    assert [i["part"] for i in geoms[1]["instances"]] == ["Plate"]


def test_chat_stream_claude_failure_is_persisted_by_the_worker(client, monkeypatch):
    """The failure must reach the transcript even if nobody watched the SSE:
    the worker thread persists it before returning, so a client that
    disconnected mid-stream still finds the error message on reload."""
    def dead_plan(*a, **k):
        raise planner.PlannerError("规划（plan）阶段失败：claude CLI exit 1: boom")

    monkeypatch.setattr(planner, "claude_cli_available", lambda: True)
    monkeypatch.setattr(planner, "plan_with_claude", dead_plan)

    sid = client.post("/api/workbench/sessions", json={}).json()["session_id"]
    resp = client.post(f"/api/workbench/sessions/{sid}/chat/stream",
                       json={"text": "建个轴承座", "backend": "claude_cli"})
    events = _events(resp)
    assert events[-1][0] == "error"
    assert "规划" in events[-1][1]["message"]
    assert events[-1][1]["session"] is not None
    stored = client.get(f"/api/workbench/sessions/{sid}").json()
    assert stored["messages"][-1]["error"] is True
    assert "规划" in stored["messages"][-1]["text"]
    assert stored["pending"] is None


def test_chat_stream_auto_failure_degrades_to_template_and_says_so(client, monkeypatch):
    """backend=auto: a dead claude falls back to the template engine, and the
    reply SAYS it degraded — a silent fallback would pass keyword guesses off
    as the model's work. Persisted by the worker like every other outcome."""
    def dead_plan(*a, **k):
        raise planner.PlannerError("claude CLI timed out after 600s")

    monkeypatch.setattr(planner, "claude_cli_available", lambda: True)
    monkeypatch.setattr(planner, "plan_with_claude", dead_plan)

    sid = client.post("/api/workbench/sessions", json={}).json()["session_id"]
    resp = client.post(f"/api/workbench/sessions/{sid}/chat/stream",
                       json={"text": "帮我建一个悬臂梁", "backend": "auto"})
    events = _events(resp)
    assert events[-1][0] == "proposal"
    pending = events[-1][1]["pending"]
    assert pending["backend"] == "template"
    assert pending["summary"].startswith("（Claude 规划失败已降级模板：")
    assert "timed out" in pending["summary"]
    stored = client.get(f"/api/workbench/sessions/{sid}").json()
    assert stored["pending"]["proposal_id"] == pending["proposal_id"]


# A v2 spec the schema accepts and the builder compiles — the plate-with-hole
# scenario, kept in the dialect the planner prompt teaches. The builder-lint
# tests below flip its local seed to a face selector: still schema-valid,
# refused only by the generator.
_V2_HOLE_SPEC_YAML = """meta:
  abaqus_release: "2021"
  model_name: PlateHole
  units: mm_MPa_t
material:
  name: Steel
  E: 210000.0
  nu: 0.3
parts:
  - name: Plate
    features:
      - {op: sketch, id: outline, plane: XY,
         profile: {rect: {corner1: [0.0, 0.0], corner2: [60.0, 240.0]}}}
      - {op: extrude, sketch: outline, depth: 5.0}
      - {op: sketch, id: hole, plane: XY,
         profile: {circle: {center: [30.0, 120.0], r: 6.0}}}
      - {op: cut_extrude, sketch: hole, depth: 5.0}
    section: {type: solid, material: Steel}
    mesh:
      seed: 5.0
      element: C3D20R
      local_seeds:
        - {region: "edges@r=6", size: 1.2, expect: "=2"}
assembly:
  instances:
    - {name: Plate, part: Plate}
steps:
  - name: Pull
    type: Static
    bcs:
      - {name: Root, region: "Plate:face@y=min", type: encastre}
    loads:
      - {name: Tension, region: "Plate:face@y=max", type: pressure, value: -1.0}
outputs:
  regions:
    - {name: HoleWall, region: "Plate:face@r=6"}
  kpis:
    - {name: HOOP_MAX, type: field_max, invariant: MISES,
       location: "REGION_HOLEWALL"}
"""


def _face_seed_variant() -> dict:
    import yaml as _yaml
    spec = _yaml.safe_load(_V2_HOLE_SPEC_YAML)
    spec["parts"][0]["mesh"]["local_seeds"][0]["region"] = "face@r=6"
    return spec


def test_builder_errors_name_what_the_schema_lets_through():
    """schema-valid ≠ buildable: `local_seeds: face@r=12` was measured passing
    validation and dying only at preview. _builder_errors is the generator's
    own lint, run hermetically (no CAE, no solver)."""
    import yaml as _yaml
    assert planner._builder_errors(_yaml.safe_load(_V2_HOLE_SPEC_YAML)) == []
    errs = planner._builder_errors(_face_seed_variant())
    assert len(errs) == 1
    assert "selects face" in errs[0]
    # v1 specs go through a different generator; the lint stays out of their way.
    assert planner._builder_errors(_yaml.safe_load(_VALID_SPEC_YAML)) == []


def test_the_builder_lint_feeds_the_repair_loop(monkeypatch):
    """The generator's refusal must become a repair prompt, not a preview-time
    surprise: draft comes back schema-valid but with a face seed, the repair
    call carries the builder's own words, the retry fixes it."""
    import yaml as _yaml
    bad_yaml = _yaml.dump(_face_seed_variant(), allow_unicode=True,
                          default_flow_style=False, sort_keys=False)
    calls = []

    def fake_call(prompt: str, model: str | None = None, on_text=None,
                  on_think=None) -> str:
        calls.append(prompt)
        if len(calls) == 1:
            return "【模型名】PlateHole"
        if len(calls) == 2:
            return f"===SPEC===\n{bad_yaml}===REPLY===\n初稿"
        return f"===SPEC===\n{_V2_HOLE_SPEC_YAML}===REPLY===\n修好了"

    stages = []
    monkeypatch.setattr(planner, "_call_claude", fake_call)
    spec, _, reply = planner.propose_with_claude(
        "开孔板拉伸", None, [], progress=stages.append)
    assert len(calls) == 3
    assert "selects face" in calls[2]   # the builder's refusal, relayed verbatim
    assert stages == ["plan", "draft", "repair-1"]
    assert spec["parts"][0]["mesh"]["local_seeds"][0]["region"] == "edges@r=6"


def test_make_diff_marks_changed_lines():
    old = "a: 1\nb: 2\n"
    new = "a: 1\nb: 3\n"
    diff = planner.make_diff(old, new)
    assert "-b: 2" in diff
    assert "+b: 3" in diff


# ── Backend degradation surface ──────────────────────────────────────────────

def test_accept_refuses_an_unsupported_spec_before_creating_a_run(client, wb, monkeypatch):
    """On a CalculiX-only machine the user is told no, with the field named,
    and no run record is created to look like something happened."""
    from core import backends
    from workbench import routes

    monkeypatch.setattr(routes, "run_pipeline", _fake_pipeline_completed)
    monkeypatch.setattr(backends, "detect_ccx_version", lambda *a, **k: "2.23")
    monkeypatch.setattr("core.helpers.check_abaqus", lambda: False)
    monkeypatch.setattr(backends, "check_calculix", lambda: True)

    sid = client.post("/api/workbench/sessions", json={}).json()["session_id"]
    _chat(client, sid, "悬臂梁 100x10x10，末端 1N")

    # Force the pending spec onto something CalculiX must refuse.
    import yaml
    session = client.get(f"/api/workbench/sessions/{sid}").json()
    spec = yaml.safe_load(session["pending"]["spec_yaml"])
    spec["analysis"]["step_type"] = "Dynamic_Explicit"
    spec["bc_load"]["load_type"] = "blast_conwep"
    spec["bc_load"]["blast_tnt_kg"] = 1.0
    spec["bc_load"]["blast_standoff_mm"] = 500.0

    before = set(wb.RUNS)
    resp = client.post(f"/api/workbench/sessions/{sid}/accept",
                       json={"spec_yaml": yaml.safe_dump(spec, allow_unicode=True)})
    assert resp.status_code == 400, resp.text
    detail = resp.json()["detail"]
    assert detail["backend"]["backend"] == "calculix"
    assert any("blast_conwep" in e for e in detail["errors"])
    assert any("CONWEP" in e for e in detail["errors"])
    assert set(wb.RUNS) == before, "a refused spec must not create a run record"


def test_accept_allows_a_supported_spec_on_calculix(client, wb, monkeypatch):
    from core import backends
    from workbench import routes

    monkeypatch.setattr(routes, "run_pipeline", _fake_pipeline_completed)
    monkeypatch.setattr(backends, "detect_ccx_version", lambda *a, **k: "2.23")
    monkeypatch.setattr("core.helpers.check_abaqus", lambda: False)
    monkeypatch.setattr(backends, "check_calculix", lambda: True)

    import yaml

    sid = client.post("/api/workbench/sessions", json={}).json()["session_id"]
    _chat(client, sid, "悬臂梁 100x10x10，末端 1N")
    session = client.get(f"/api/workbench/sessions/{sid}").json()
    spec = yaml.safe_load(session["pending"]["spec_yaml"])
    # The template planner defaults to a pressure load, which CalculiX has not
    # been verified for; the verified subset is a tip point load.
    spec["bc_load"]["load_type"] = "concentrated_force"
    spec["bc_load"]["direction"] = 2
    resp = client.post(f"/api/workbench/sessions/{sid}/accept",
                       json={"spec_yaml": yaml.safe_dump(spec, allow_unicode=True)})
    assert resp.status_code == 200, resp.text


def test_session_record_keeps_the_backend_after_a_restart(client, wb, monkeypatch):
    """The archived view must still say which solver produced the numbers."""
    from workbench import routes

    async def _ccx_pipeline(run_id, runs, on_stage_update=None):
        runs[run_id]["status"] = "COMPLETED"
        runs[run_id]["kpis"] = {"U_tip": -1.9e-3}
        runs[run_id]["backend"] = {"backend": "calculix", "label": "CalculiX 2.23"}
        runs[run_id]["limitations"] = [{"feature": "outputs.kpis[MISES].type",
                                        "value": "field_max", "reason": "定义不同",
                                        "kind": "caveat"}]
        runs[run_id]["kpi_provenance"] = {"U_tip": {"abaqus_equivalent": True}}

    monkeypatch.setattr(routes, "run_pipeline", _ccx_pipeline)
    sid = client.post("/api/workbench/sessions", json={}).json()["session_id"]
    _chat(client, sid, "悬臂梁 100x10x10，末端 1N")
    client.post(f"/api/workbench/sessions/{sid}/accept", json={})

    record = client.get(f"/api/workbench/sessions/{sid}").json()["runs"][0]
    assert record["backend"]["label"] == "CalculiX 2.23"
    assert record["limitations"][0]["kind"] == "caveat"


# ── Preview honesty (P2-d #3: never render a wrong or empty model as success) ─

def _make_session_with_spec(client) -> str:
    sid = client.post("/api/workbench/sessions", json={"title": "t"}).json()["session_id"]
    _chat(client, sid, "悬臂梁 100x10x10 mm，钢，末端向下 1N")
    return sid


def test_preview_refuses_unrenderable_mesh_instead_of_empty_success(
        client, wb, monkeypatch, tmp_path):
    """parse_ok False (or 0 parts) must become an HTTP error, not a mesh."""
    from workbench import routes as wr

    def fake_build(spec_path, workdir):
        import json
        out = Path(workdir) / "preview_mesh.json"
        out.write_text(json.dumps({
            "format": "abaqus-agent-mesh/2-parts",
            "parse_ok": False,
            "problems": ["没有解析出任何可渲染的部件：ELSET=X 外表面提取失败"],
            "parts": [], "part_count": 0, "node_count": 0, "element_count": 0,
            "bbox": [[0, 0, 0], [0, 0, 0]],
            "render_triangle_count": 0, "render_line_count": 0,
        }), encoding="utf-8")
        return {"preview_mesh": "preview_mesh.json"}

    # runner/__init__ re-exports the function under the module's own name,
    # so the dotted string resolves to the function; go via sys.modules.
    monkeypatch.setattr(sys.modules["runner.build_model"], "build_model", fake_build)
    wr._PREVIEW_CACHE.clear()
    sid = _make_session_with_spec(client)

    resp = client.post(f"/api/workbench/sessions/{sid}/preview", json={})

    assert resp.status_code == 500
    detail = resp.json()["detail"]
    assert "没有解析出任何可渲染的部件" in detail["error"]
    # A refusal must not be cached as if it were a mesh.
    assert not wr._PREVIEW_CACHE


def test_preview_stream_meta_carries_parse_problems(client, wb, monkeypatch):
    """A partial render must arrive with its warnings, or it reads complete."""
    from workbench import routes as wr

    def fake_build(spec_path, workdir):
        import json
        out = Path(workdir) / "preview_mesh.json"
        out.write_text(json.dumps({
            "format": "abaqus-agent-mesh/2-parts",
            "parse_ok": True,
            "problems": ["已忽略无法预览的单元块：ELSET=CONNECTORS（TYPE=CONN3D2，该单元族不支持预览）"],
            "parts": [{"name": "BLOCK", "family": "surface", "element_type": "C3D8",
                       "nodes": [0, 0, 0, 1, 0, 0, 1, 1, 0], "tris": [0, 1, 2],
                       "node_count": 3, "tri_count": 1, "element_count": 1,
                       "color": None}],
            "part_count": 1, "node_count": 3, "element_count": 1,
            "bbox": [[0, 0, 0], [1, 1, 0]],
            "render_triangle_count": 1, "render_line_count": 0,
        }), encoding="utf-8")
        return {"preview_mesh": "preview_mesh.json"}

    monkeypatch.setattr(sys.modules["runner.build_model"], "build_model", fake_build)
    wr._PREVIEW_CACHE.clear()
    sid = _make_session_with_spec(client)

    resp = client.post(f"/api/workbench/sessions/{sid}/preview/stream", json={})

    assert resp.status_code == 200
    body = resp.text
    assert "event: meta" in body
    assert "CONNECTORS" in body and "CONN3D2" in body, (
        "the meta event must carry the parse problems for the stats bar")


# ── the proposed spec must not carry a release this machine does not have ───

def test_template_proposal_uses_the_probed_release(monkeypatch):
    """A hardcoded "2024" here put a version number the machine may not have
    onto the workbench screen and into the archived report."""
    import asyncio

    import tools.abaqus_cmd as abaqus_cmd
    from workbench import chat_flow

    monkeypatch.setattr(abaqus_cmd, "detect_abaqus_release",
                        lambda *a, **k: "2019")
    spec, _yaml, reply, _missing = asyncio.run(
        chat_flow._propose_template({"messages": []}, "悬臂梁 100x10x10 端部集中力"))

    assert spec["meta"]["abaqus_release"] == "2019"
    assert "占位默认值" not in reply, "a detected release must not be hedged"


def test_template_proposal_announces_an_undetected_release(monkeypatch):
    """schema/spec_schema.json requires a year, so the field cannot be blank —
    but the fallback must be labelled as a guess rather than pass for fact."""
    import asyncio

    import tools.abaqus_cmd as abaqus_cmd
    from workbench import chat_flow

    monkeypatch.setattr(abaqus_cmd, "detect_abaqus_release", lambda *a, **k: None)
    spec, _yaml, reply, _missing = asyncio.run(
        chat_flow._propose_template({"messages": []}, "悬臂梁 100x10x10 端部集中力"))

    assert spec["meta"]["abaqus_release"] == chat_flow._FALLBACK_RELEASE
    assert "未检测到已安装的 Abaqus" in reply
    assert "占位默认值" in reply


def test_preview_stream_meta_carries_the_assembly_overlay(client, wb, monkeypatch):
    """The named surfaces, and which interaction joined which of them.

    Computed all along by post/parse_inp.py and then dropped on the floor here,
    which is why the model tree could only ever dim two whole bodies for a
    contact pair. Dimming both plates of a tie tells the user what they already
    knew; the facets Abaqus actually put in the surface are the thing a spec
    author cannot check by reading the spec, because a selector that caught the
    outside of a flange instead of the bore reads identically in YAML.
    """
    from workbench import routes as wr

    def fake_build(spec_path, workdir):
        import json
        out = Path(workdir) / "preview_mesh.json"
        out.write_text(json.dumps({
            "format": "abaqus-agent-mesh/3-assembly",
            "parse_ok": True,
            "problems": [],
            "parts": [{"name": "LOWER", "instance": "Lower", "family": "surface",
                       "element_type": "C3D8", "nodes": [0, 0, 0, 1, 0, 0, 1, 1, 0],
                       "tris": [0, 1, 2], "node_count": 3, "tri_count": 1,
                       "element_count": 1, "color": None}],
            "assembly": {
                "surfaces": [{"name": "MIDPLANE_MAIN", "instance": "Lower",
                              "node_count": 3, "drawn_nodes": 3, "capped": False,
                              "parts": [{"part": 0, "facets": [0, 1, 2],
                                         "facet_count": 1}]}],
                "sets": [],
                "interactions": [{"name": "MidPlane", "kind": "tie", "call": "",
                                  "surfaces": ["MIDPLANE_MAIN"], "gap": 0.0,
                                  "gap_nodes": [3, 3]}],
                "conditions": [], "counts": {}, "degraded": [],
            },
            "part_count": 1, "node_count": 3, "element_count": 1,
            "bbox": [[0, 0, 0], [1, 1, 0]],
            "render_triangle_count": 1, "render_line_count": 0,
        }), encoding="utf-8")
        return {"preview_mesh": "preview_mesh.json"}

    monkeypatch.setattr(sys.modules["runner.build_model"], "build_model", fake_build)
    wr._PREVIEW_CACHE.clear()
    sid = _make_session_with_spec(client)

    resp = client.post(f"/api/workbench/sessions/{sid}/preview/stream", json={})
    assert resp.status_code == 200

    import json
    meta = None
    for block in resp.text.split("\n\n"):
        if block.startswith("event: meta"):
            meta = json.loads(block.split("data: ", 1)[1])
    assert meta is not None, "no meta event"

    overlay = meta.get("assembly")
    assert overlay is not None, "the overlay never reached the wire"
    assert overlay["interactions"][0]["surfaces"] == ["MIDPLANE_MAIN"]
    # The facets themselves, not just the name: a name with no triangles behind
    # it is a tree row that highlights nothing.
    assert overlay["surfaces"][0]["parts"][0]["facets"] == [0, 1, 2]


def test_preview_stream_meta_says_null_when_there_is_no_overlay(client, wb, monkeypatch):
    """An .inp-derived payload never had a CAE session, so it has no named
    surfaces. Null rather than an empty object: "no highlight available" and "a
    model with no surfaces" are different answers and the viewport must not
    confuse them."""
    from workbench import routes as wr

    def fake_build(spec_path, workdir):
        import json
        out = Path(workdir) / "preview_mesh.json"
        out.write_text(json.dumps({
            "format": "abaqus-agent-mesh/2-parts", "parse_ok": True, "problems": [],
            "parts": [{"name": "BLOCK", "family": "surface", "element_type": "C3D8",
                       "nodes": [0, 0, 0, 1, 0, 0, 1, 1, 0], "tris": [0, 1, 2],
                       "node_count": 3, "tri_count": 1, "element_count": 1,
                       "color": None}],
            "part_count": 1, "node_count": 3, "element_count": 1,
            "bbox": [[0, 0, 0], [1, 1, 0]],
            "render_triangle_count": 1, "render_line_count": 0,
        }), encoding="utf-8")
        return {"preview_mesh": "preview_mesh.json"}

    monkeypatch.setattr(sys.modules["runner.build_model"], "build_model", fake_build)
    wr._PREVIEW_CACHE.clear()
    sid = _make_session_with_spec(client)

    resp = client.post(f"/api/workbench/sessions/{sid}/preview/stream", json={})
    import json
    meta = None
    for block in resp.text.split("\n\n"):
        if block.startswith("event: meta"):
            meta = json.loads(block.split("data: ", 1)[1])
    assert meta is not None
    assert "assembly" in meta and meta["assembly"] is None


# ── @-mentions on the chat endpoint ─────────────────────────────────────────
# The resolver's own behaviour lives in test_workbench_selection.py; what is
# pinned here is the ROUTE contract: resolution happens at send time against
# the spec the tree drew, a dangling mention is a 400 naming it (never a
# silent drop), and what the LLM path receives is the resolved fragment.

def test_chat_selection_resolves_and_is_recorded(client):
    sid = client.post("/api/workbench/sessions", json={}).json()["session_id"]
    _chat(client, sid, "帮我建一个悬臂梁，钢，末端集中力")

    data = client.post(
        f"/api/workbench/sessions/{sid}/chat",
        json={"text": "@几何 加长一倍", "backend": "template",
              "selection": [{"ref": "geometry", "label": "几何"}]})
    assert data.status_code == 200, data.text
    session = data.json()["session"]
    user_msgs = [m for m in session["messages"] if m["role"] == "user"]
    # Labels ride the transcript so the chips survive a reload.
    assert user_msgs[-1].get("refs")
    # The template engine cannot aim an edit, and the reply says so instead of
    # letting the chip imply an ability that is not there.
    reply = [m for m in session["messages"] if m["role"] == "assistant"][-1]
    assert "模板引擎" in reply["text"]


def test_chat_selection_that_does_not_resolve_is_a_400_naming_it(client):
    sid = client.post("/api/workbench/sessions", json={}).json()["session_id"]
    _chat(client, sid, "帮我建一个悬臂梁，钢，末端集中力")

    resp = client.post(
        f"/api/workbench/sessions/{sid}/chat",
        json={"text": "@Ghost 改一下", "backend": "template",
              "selection": [{"ref": "part:Ghost", "label": "Ghost"}]})
    assert resp.status_code == 400
    assert "part:Ghost" in resp.json()["detail"]
    # The failed send must not have appended a half-message to the transcript.
    session = client.get(f"/api/workbench/sessions/{sid}").json()
    assert all("Ghost" not in m.get("text", "") for m in session["messages"])


def test_chat_selection_with_no_spec_is_a_400(client):
    sid = client.post("/api/workbench/sessions", json={}).json()["session_id"]
    resp = client.post(
        f"/api/workbench/sessions/{sid}/chat",
        json={"text": "@x", "backend": "template",
              "selection": [{"ref": "geometry", "label": "几何"}]})
    assert resp.status_code == 400
    assert "先让助手生成" in resp.json()["detail"]


def test_chat_selection_reaches_the_claude_prompt(client, monkeypatch):
    """The whole point: the fragment lands in front of the model."""
    captured = {}

    def fake_propose(instruction, current, history, selection=None,
                     progress=None):
        captured["selection"] = selection
        from workbench.planner import build_prompt
        captured["prompt"] = build_prompt(instruction, current, history, selection)
        spec_yaml = (
            "meta:\n  abaqus_release: '2021'\n  model_name: Beam\n"
            "  units: mm_MPa_t\ngeometry:\n  type: cantilever_block\n"
            "  L: 200.0\n  W: 10.0\n  H: 10.0\n  seed_size: 2.5\n"
            "material:\n  name: Steel\n  E: 210000.0\n  nu: 0.3\n"
            "analysis:\n  solver: standard\n  step_type: Static\n"
            "bc_load:\n  fixed_face: z=0\n  load_face: z=L\n"
            "  load_type: pressure\n  value: -1.0\n  direction: 2\n"
            "outputs:\n  kpis:\n  - name: U_tip\n    type: nodal_displacement\n"
            "    location: tip_center\n")
        import yaml as _yaml
        return _yaml.safe_load(spec_yaml), spec_yaml, "改好了"

    monkeypatch.setattr(planner, "claude_cli_available", lambda: True)
    monkeypatch.setattr(planner, "propose_with_claude", fake_propose)

    sid = client.post("/api/workbench/sessions", json={}).json()["session_id"]
    _chat(client, sid, "帮我建一个悬臂梁，钢，末端集中力")
    resp = client.post(
        f"/api/workbench/sessions/{sid}/chat",
        json={"text": "@几何 加长一倍", "backend": "claude_cli",
              "selection": [{"ref": "geometry", "label": "几何"}]})
    assert resp.status_code == 200, resp.text
    assert captured["selection"] and captured["selection"][0]["path"] == "geometry"
    assert "## 用户选中" in captured["prompt"]
    assert "cantilever_block" in captured["prompt"].split("## 用户选中", 1)[1]
