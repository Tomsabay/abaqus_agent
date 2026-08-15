from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from copilot import routes as copilot_routes

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def server_app(monkeypatch, tmp_path):
    import server
    # The store and the routes that own it live in copilot/routes.py; the
    # names patched here have to be the ones the routes read, so they are
    # patched there. server.COPILOT_SESSIONS is the same dict object.
    from copilot import routes as copilot_routes

    monkeypatch.setenv("ABAQUS_AGENT_EVIDENCE_VAULT", str(tmp_path / "vault"))
    monkeypatch.setattr(copilot_routes, "COPILOT_SESSION_STORE_DIR",
                        tmp_path / "copilot_sessions")
    monkeypatch.setattr(copilot_routes, "COPILOT_SESSION_FILE",
                        tmp_path / ".abaqus_agent_session")
    original_runs = dict(server.RUNS)
    original_copilot = dict(server.COPILOT_SESSIONS)
    server.RUNS.clear()
    server.COPILOT_SESSIONS.clear()
    try:
        yield server
    finally:
        server.RUNS.clear()
        server.RUNS.update(original_runs)
        server.COPILOT_SESSIONS.clear()
        server.COPILOT_SESSIONS.update(original_copilot)


def test_copilot_plan_execute_and_plugin_queue(server_app, tmp_path, monkeypatch) -> None:
    def fake_build_copilot_alpha_package(*, root, server_url="http://127.0.0.1:8000"):
        package_path = tmp_path / "server-alpha.zip"
        _write_alpha_package_zip(package_path, server_url=server_url)
        return {
            "status": "packaged",
            "package_path": str(package_path),
            "package_name": "abaqus-agent-copilot-alpha.zip",
            "overall_status": "ALPHA_READY_WITH_GUI_BLOCKER",
            "included_files": [],
            "missing_files": [],
            "manifest": {"overall_status": "ALPHA_READY_WITH_GUI_BLOCKER"},
        }

    monkeypatch.setattr(copilot_routes, "build_copilot_alpha_package", fake_build_copilot_alpha_package)
    client = TestClient(server_app.app, raise_server_exceptions=False)

    status = client.get("/api/copilot/status")
    assert status.status_code == 200
    status_data = status.json()
    assert status_data["auth_mode"] == "local_codex_app_server"
    assert "create_cantilever_model" in status_data["supported_actions"]

    plugin_guide = client.get("/api/copilot/plugin-guide")
    assert plugin_guide.status_code == 200
    plugin_guide_data = plugin_guide.json()
    assert plugin_guide_data["server_url"].startswith("http://testserver")
    assert "abaqus-agent-copilot-install-plugin" in plugin_guide_data["install_command"]
    assert plugin_guide_data["open_sidecar_action"] == "AbaqusAgent Copilot: Open Sidecar"
    assert plugin_guide_data["run_plan_action"] == "AbaqusAgent Copilot: Run Current Plan"
    assert plugin_guide_data["execute_next_action"] == "AbaqusAgent Copilot: Execute Next Action"
    assert plugin_guide_data["status_action"] == "AbaqusAgent Copilot: Check Session Status"
    assert plugin_guide_data["session_file"].endswith(".abaqus_agent_session")

    release_gate = client.get("/api/copilot/release-gate")
    assert release_gate.status_code == 200
    release_gate_data = release_gate.json()
    assert release_gate_data["overall_status"] in {
        "ALPHA_READY_WITH_GUI_BLOCKER",
        "FAIL",
        "RELEASE_READY",
    }
    assert any(
        check["id"] == "interactive_cae_gui_visual"
        for check in release_gate_data["checks"]
    )

    alpha_package = client.get("/api/copilot/alpha-package.zip")
    assert alpha_package.status_code == 200
    assert alpha_package.headers["content-type"] == "application/zip"
    package_path = tmp_path / "alpha.zip"
    package_path.write_bytes(alpha_package.content)
    with zipfile.ZipFile(package_path) as bundle:
        names = set(bundle.namelist())
        config = bundle.read("plugin/abaqus_agent_config.example.json").decode("utf-8")
    assert "plugin/abaqusAgent_plugin.py" in names
    assert "PACKAGE_MANIFEST.json" in names
    assert "http://testserver" in config

    alpha_package_verify = client.get("/api/copilot/alpha-package/verify")
    assert alpha_package_verify.status_code == 200
    alpha_package_verify_data = alpha_package_verify.json()
    assert alpha_package_verify_data["verification"]["overall_status"] == "PASS"
    assert alpha_package_verify_data["package"]["overall_status"] in {
        "ALPHA_READY_WITH_GUI_BLOCKER",
        "RELEASE_READY",
    }

    planned = client.post(
        "/api/copilot/plan",
        json={
            "text": "帮我建一个 200mm 悬臂梁，左端固定，右端 100N 下压",
            "backend": "template",
        },
    )
    assert planned.status_code == 200
    plan = planned.json()
    assert plan["backend"] == "template"
    assert plan["session_id"].startswith("copilot-")
    assert [item["action"] for item in plan["actions"]] == [
        "create_cantilever_model",
        "apply_boundary_condition",
        "submit_job_or_prepare_run",
    ]

    first_action = client.get(f"/api/copilot/sessions/{plan['session_id']}/next-action")
    assert first_action.status_code == 200
    assert first_action.json()["action"]["action"] == "create_cantilever_model"

    activated = client.post(f"/api/copilot/sessions/{plan['session_id']}/activate")
    assert activated.status_code == 200
    activated_data = activated.json()
    assert activated_data["session_id"] == plan["session_id"]
    assert activated_data["session_file"].endswith(".abaqus_agent_session")
    assert activated_data["plugin_action"] == "AbaqusAgent Copilot: Run Current Plan"
    assert activated_data["debug_plugin_action"] == "AbaqusAgent Copilot: Execute Next Action"

    session_before = client.get(f"/api/copilot/sessions/{plan['session_id']}")
    assert session_before.status_code == 200
    session_before_data = session_before.json()
    assert session_before_data["action_count"] == 3
    assert session_before_data["pending_count"] == 3
    assert session_before_data["completed_count"] == 0

    action_result = client.post(
        f"/api/copilot/sessions/{plan['session_id']}/action-result",
        json={"action_index": 0, "status": "completed", "message": "ok"},
    )
    assert action_result.status_code == 200
    assert action_result.json()["remaining_actions"] == 2

    session_after = client.get(f"/api/copilot/sessions/{plan['session_id']}")
    assert session_after.status_code == 200
    session_after_data = session_after.json()
    assert session_after_data["pending_count"] == 2
    assert session_after_data["completed_count"] == 1
    assert session_after_data["results"][0]["message"] == "ok"

    executed = client.post(
        "/api/copilot/execute",
        json={"session_id": plan["session_id"], "bridge_mode": "mock"},
    )
    assert executed.status_code == 200
    execution = executed.json()
    assert execution["status"] == "mock_executed"
    assert execution["bridge_mode"] == "mock"
    assert execution["script_path"].endswith("abaqus_copilot_actions.py")


def test_copilot_model_state_viewport_and_error_feedback(server_app) -> None:
    """The Cursor-style loop contract: plugin reports eyes (model tree,
    viewport PNG) and ears (failed action tracebacks) back to the sidecar."""
    import base64

    client = TestClient(server_app.app, raise_server_exceptions=False)

    planned = client.post(
        "/api/copilot/plan",
        json={"text": "帮我建一个悬臂梁", "backend": "template"},
    )
    assert planned.status_code == 200
    session_id = planned.json()["session_id"]

    # Fresh session: no model state, no viewport, no errors.
    empty_state = client.get(f"/api/copilot/sessions/{session_id}/model-state")
    assert empty_state.status_code == 200
    assert empty_state.json()["models"] == []
    assert empty_state.json()["reported_at"] is None
    assert client.get(f"/api/copilot/sessions/{session_id}/viewport.png").status_code == 404

    session = client.get(f"/api/copilot/sessions/{session_id}").json()
    assert session["errors"] == []
    assert session["model_state_at"] is None
    assert session["viewport_at"] is None

    # Plugin reports an mdb snapshot.
    snapshot = {
        "models": [
            {
                "name": "Model-1",
                "parts": ["Beam"],
                "materials": ["Steel"],
                "steps": ["Initial", "LoadStep"],
                "loads": ["TipLoad"],
                "bcs": ["Fixed"],
                "instances": ["Beam-1"],
                "mesh_elements": 1200,
            }
        ],
        "active_model": "Model-1",
    }
    reported = client.post(
        f"/api/copilot/sessions/{session_id}/model-state", json=snapshot
    )
    assert reported.status_code == 200
    assert reported.json()["model_count"] == 1

    state = client.get(f"/api/copilot/sessions/{session_id}/model-state").json()
    assert state["models"][0]["parts"] == ["Beam"]
    assert state["active_model"] == "Model-1"
    assert state["reported_at"] is not None

    # Plugin posts a viewport PNG; bad payloads are rejected.
    png_bytes = b"\x89PNG\r\n\x1a\n" + b"fake-image-body"
    posted = client.post(
        f"/api/copilot/sessions/{session_id}/viewport",
        json={"image_base64": base64.b64encode(png_bytes).decode("ascii"), "caption": "step 1"},
    )
    assert posted.status_code == 200
    assert posted.json()["bytes"] == len(png_bytes)

    served = client.get(f"/api/copilot/sessions/{session_id}/viewport.png")
    assert served.status_code == 200
    assert served.headers["content-type"] == "image/png"
    assert served.content == png_bytes

    not_base64 = client.post(
        f"/api/copilot/sessions/{session_id}/viewport",
        json={"image_base64": "not-base64!!!"},
    )
    assert not_base64.status_code == 400

    not_png = client.post(
        f"/api/copilot/sessions/{session_id}/viewport",
        json={"image_base64": base64.b64encode(b"GIF89a...").decode("ascii")},
    )
    assert not_png.status_code == 400

    # Plugin reports a failed action with traceback; session surfaces it.
    failed = client.post(
        f"/api/copilot/sessions/{session_id}/action-result",
        json={
            "action_index": 0,
            "status": "failed",
            "message": "Abaqus/CAE execution failed",
            "payload": {"action": "create_cantilever_model", "traceback": "Traceback ...\nKeyError: 'x'"},
        },
    )
    assert failed.status_code == 200

    session = client.get(f"/api/copilot/sessions/{session_id}").json()
    assert len(session["errors"]) == 1
    assert session["errors"][0]["payload"]["traceback"].startswith("Traceback")
    # a failed action is not "completed": the queue stamp must not show 1/3 done
    assert session["completed_count"] == 0
    assert session["model_state_at"] is not None
    assert session["viewport_at"] is not None

    # Unknown sessions 404 across the new endpoints.
    assert client.get("/api/copilot/sessions/nope/model-state").status_code == 404
    assert client.post("/api/copilot/sessions/nope/model-state", json={}).status_code == 404
    assert client.get("/api/copilot/sessions/nope/viewport.png").status_code == 404
    assert (
        client.post(
            "/api/copilot/sessions/nope/viewport", json={"image_base64": "aGk="}
        ).status_code
        == 404
    )


def test_copilot_session_stream_pushes_updates(server_app) -> None:
    """SSE stream replaces the frontend's 3s poll: it must push the current
    session summary immediately and reflect model-state updates as soon as
    they're reported, with no client-side wait. Drives the route's async
    generator directly instead of through TestClient: the stream never hits
    a terminal state on its own, and TestClient's transport runs the whole
    ASGI call to completion before returning anything -- which would block
    for the full 30-minute connection timeout if driven over real HTTP.

    Uses a private event loop (not asyncio.run/asyncio.get_event_loop) so it
    doesn't touch the process-wide "current event loop" flag that other
    tests' legacy asyncio.get_event_loop() calls depend on."""
    import asyncio

    client = TestClient(server_app.app, raise_server_exceptions=False)

    planned = client.post(
        "/api/copilot/plan",
        json={"text": "帮我建一个悬臂梁", "backend": "template"},
    )
    assert planned.status_code == 200
    session_id = planned.json()["session_id"]

    async def next_event() -> dict:
        response = await copilot_routes.stream_copilot_session(session_id)
        gen = response.body_iterator
        try:
            async for chunk in gen:
                text = chunk.decode() if isinstance(chunk, bytes) else chunk
                for line in text.splitlines():
                    if line.startswith("data:"):
                        return json.loads(line[5:].strip())
            raise AssertionError("stream produced no data event")
        finally:
            await gen.aclose()

    loop = asyncio.new_event_loop()
    try:
        initial = loop.run_until_complete(next_event())
        assert initial["session_id"] == session_id
        assert initial["action_count"] == 3
        assert initial["model_state_at"] is None
        assert initial["viewport_at"] is None

        client.post(
            f"/api/copilot/sessions/{session_id}/model-state",
            json={"models": [{"name": "Model-1", "parts": ["Beam"]}], "active_model": "Model-1"},
        )

        updated = loop.run_until_complete(next_event())
        assert updated["model_state_at"] is not None
    finally:
        loop.close()

    assert client.get("/api/copilot/sessions/nope/stream").status_code == 404


def test_plugin_bridge_supports_remote_server_and_py2_py3_urllib() -> None:
    source = (ROOT / "plugins" / "abaqus_agent" / "abaqusAgent_plugin.py").read_text(
        encoding="utf-8"
    )
    required_markers = [
        'os.environ.get("ABAQUS_AGENT_SERVER_URL"',
        "abaqus_agent_config.json",
        "CONFIG_FILENAMES",
        "CONFIG.get(\"server_url\")",
        "CONFIG.get(\"session_id\")",
        "SESSION_FILE",
        "open_copilot_sidecar",
        "AbaqusAgent Copilot: Open Sidecar",
        "import urllib2",
        "import urllib.request as urllib2",
        "execute_next_copilot_action(session_id)",
        "execute_all_copilot_actions(session_id",
        "execute_all_copilot_actions_from_env",
        "inspect_copilot_session_from_env",
        "PLUGIN_MENU_ENTRIES",
        "get_plugin_manifest",
        "write_plugin_manifest",
        '"default_action": "AbaqusAgent Copilot: Run Current Plan"',
        "AbaqusAgent Copilot: Run Current Plan",
        "AbaqusAgent Copilot: Check Session Status",
        "action_name not in ALLOWED_ACTIONS",
        "action-result",
        # failed solves ship their solver log tails for sidecar diagnosis
        "_collect_solver_log_tails(action)",
        '"solver_logs"',
        "data[-6000:].decode(\"utf-8\", \"replace\")",
        # completed submit actions ship the extract script's KPI dict back
        'success_payload["kpis"] = kpi_result',
        'globals().get("result")',
    ]
    missing = [marker for marker in required_markers if marker not in source]
    assert missing == []


def test_copilot_session_history_lists_newest_first_with_full_restore(server_app) -> None:
    client = TestClient(server_app.app)

    assert client.get("/api/copilot/sessions").json()["sessions"] == []

    first = client.post(
        "/api/copilot/plan", json={"text": "帮我建一个悬臂梁", "backend": "template"}
    ).json()
    second = client.post(
        "/api/copilot/plan", json={"text": "做一个简支梁三点弯 500N", "backend": "template"}
    ).json()
    client.post(
        f"/api/copilot/sessions/{first['session_id']}/action-result",
        json={"action_index": 0, "status": "completed", "message": "ok"},
    )

    listed = client.get("/api/copilot/sessions").json()["sessions"]
    assert [s["session_id"] for s in listed] == [second["session_id"], first["session_id"]]
    assert listed[1]["completed_count"] == 1
    assert "简支" in listed[0]["user_summary"]

    # the history picker restores any stored session with its full plan
    full = client.get(f"/api/copilot/sessions/{first['session_id']}/full")
    assert full.status_code == 200
    data = full.json()
    assert data["plan"]["session_id"] == first["session_id"]
    assert len(data["plan"]["actions"]) == 3
    assert data["summary"]["completed_count"] == 1
    assert client.get("/api/copilot/sessions/nope/full").status_code == 404

    # limit is respected
    limited = client.get("/api/copilot/sessions?limit=1").json()["sessions"]
    assert len(limited) == 1
    assert limited[0]["session_id"] == second["session_id"]


def test_copilot_active_session_endpoint_supports_reattach(server_app) -> None:
    client = TestClient(server_app.app)

    # nothing activated yet
    assert client.get("/api/copilot/sessions/active").status_code == 404

    plan = client.post(
        "/api/copilot/plan", json={"text": "帮我建一个悬臂梁", "backend": "template"}
    ).json()
    client.post(f"/api/copilot/sessions/{plan['session_id']}/activate")

    active = client.get("/api/copilot/sessions/active")
    assert active.status_code == 200
    data = active.json()
    assert data["session_id"] == plan["session_id"]
    assert [a["action"] for a in data["plan"]["actions"]] == [
        a["action"] for a in plan["actions"]
    ]
    assert data["summary"]["pending_count"] == 3

    # a stale pointer (session no longer in the store) must 404, not crash
    copilot_routes.COPILOT_SESSION_FILE.write_text("copilot-gone", encoding="utf-8")
    assert client.get("/api/copilot/sessions/active").status_code == 404


def test_copilot_replay_endpoint_missing_recording_returns_404(server_app, monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(copilot_routes, "COPILOT_REPLAY_FILE", tmp_path / "missing.json")
    client = TestClient(server_app.app)

    res = client.get("/api/copilot/replay")

    assert res.status_code == 404
    assert "record_copilot_replay" in res.json()["detail"]


def test_copilot_replay_endpoint_serves_recorded_frames(server_app, monkeypatch, tmp_path) -> None:
    replay = {
        "version": 1,
        "recorded_at": "2026-07-05T00:00:00Z",
        "abaqus_real": True,
        "frames": [
            {"dt": 0.0, "kind": "chat", "role": "user", "text": "建一个悬臂梁"},
            {"dt": 0.8, "kind": "plan", "plan": {"session_id": "copilot-demo", "actions": []}},
            {"dt": 2.5, "kind": "session", "session": {"session_id": "copilot-demo", "errors": []}},
            {"dt": 3.0, "kind": "model_state", "model_state": {"models": []}},
            {"dt": 3.2, "kind": "viewport", "png_base64": "aGk=", "captured_at": 3.2},
        ],
    }
    replay_file = tmp_path / "replay.json"
    replay_file.write_text(json.dumps(replay, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(copilot_routes, "COPILOT_REPLAY_FILE", replay_file)
    client = TestClient(server_app.app)

    res = client.get("/api/copilot/replay")

    assert res.status_code == 200
    # the workspace probes with HEAD to decide whether to show the demo hint
    assert client.head("/api/copilot/replay").status_code == 200
    data = res.json()
    assert data["version"] == 1
    assert data["abaqus_real"] is True
    assert [frame["kind"] for frame in data["frames"]] == [
        "chat",
        "plan",
        "session",
        "model_state",
        "viewport",
    ]


def test_copilot_replay_recordings_picker(server_app, monkeypatch, tmp_path) -> None:
    default_file = tmp_path / "replay.json"
    default_file.write_text(json.dumps({"version": 1, "frames": []}), encoding="utf-8")
    plate_file = tmp_path / "replay_plate_hole.json"
    plate_file.write_text(
        json.dumps({"version": 1, "frames": [], "scenario": "plate"}), encoding="utf-8"
    )
    monkeypatch.setattr(copilot_routes, "COPILOT_REPLAY_FILE", default_file)
    monkeypatch.setattr(copilot_routes, "COPILOT_REPLAY_DIR", tmp_path)
    client = TestClient(server_app.app)

    listing = client.get("/api/copilot/replays").json()["recordings"]
    assert [r["name"] for r in listing] == ["default", "plate_hole"]
    assert "开孔板" in listing[1]["title"]

    assert client.get("/api/copilot/replay?name=plate_hole").json()["scenario"] == "plate"
    # names are whitelisted; anything else 404s instead of touching the filesystem
    assert client.get("/api/copilot/replay?name=../../etc/passwd").status_code == 404

    plate_file.unlink()
    listing = client.get("/api/copilot/replays").json()["recordings"]
    assert [r["name"] for r in listing] == ["default"]
    assert client.get("/api/copilot/replay?name=plate_hole").status_code == 404


def test_copilot_replay_endpoint_corrupt_recording_returns_500(server_app, monkeypatch, tmp_path) -> None:
    replay_file = tmp_path / "replay.json"
    replay_file.write_text("{not valid json", encoding="utf-8")
    monkeypatch.setattr(copilot_routes, "COPILOT_REPLAY_FILE", replay_file)
    client = TestClient(server_app.app)

    res = client.get("/api/copilot/replay")

    assert res.status_code == 500
    assert "unreadable" in res.json()["detail"]


def test_install_copilot_plugin_copies_plugin_and_writes_session(monkeypatch, tmp_path) -> None:
    from scripts.install_copilot_plugin import install_copilot_plugin

    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    target = tmp_path / "abaqus_plugins"
    result = install_copilot_plugin(
        target,
        server_url="http://198.51.100.7:8000",
        session_id="copilot-test",
        write_session_file=True,
    )

    plugin_path = Path(result["plugin_path"])
    assert result["status"] == "installed"
    assert plugin_path.exists()
    assert plugin_path.name == "abaqusAgent_plugin.py"
    assert Path(result["config_path"]).exists()
    config = Path(result["config_path"]).read_text(encoding="utf-8")
    assert "http://198.51.100.7:8000" in config
    assert "copilot-test" in config
    assert "AbaqusAgent Copilot: Open Sidecar" in plugin_path.read_text(encoding="utf-8")
    assert Path(result["session_file"]).read_text(encoding="utf-8") == "copilot-test"


def _write_alpha_package_zip(path: Path, *, server_url: str) -> None:
    required_files = {
        "README.md": "# package\n",
        "plugin/abaqusAgent_plugin.py": "# plugin\n",
        "plugin/README.md": "# plugin readme\n",
        "plugin/abaqus_agent_config.example.json": json.dumps(
            {"server_url": server_url, "session_id": ""}
        ),
        "docs/COPILOT_MVP.md": "# docs\n",
        "evidence/copilot_alpha_release_gate.json": json.dumps(
            {
                "overall_status": "ALPHA_READY_WITH_GUI_BLOCKER",
                "checks": [
                    {"id": "codex_strict_real_abaqus_smoke", "status": "PASS"},
                    {"id": "plugin_run_current_plan_real_abaqus", "status": "PASS"},
                    {"id": "plugin_runtime_manifest", "status": "PASS"},
                    {"id": "interactive_cae_gui_visual", "status": "BLOCKED"},
                ],
            }
        ),
        "evidence/copilot_alpha_release_gate.md": "# gate\n",
        "evidence/real_smoke/Cantilever_200mm_Static_copilot_result.json": json.dumps(
            {"status": "COMPLETED"}
        ),
        "evidence/plugin_run_plan/copilot_plugin_run_plan_trace.json": json.dumps(
            {"status": "completed"}
        ),
        "evidence/plugin_run_plan/Cantilever_200mm_Static_copilot_result.json": json.dumps(
            {"status": "COMPLETED"}
        ),
        "evidence/plugin_manifest/abaqus_agent_plugin_manifest.json": json.dumps(
            {"menu_entries": []}
        ),
    }
    package_manifest = {
        "package": "abaqus-agent-copilot-alpha",
        "overall_status": "ALPHA_READY_WITH_GUI_BLOCKER",
        "strict_gui_ready": False,
        "included_files": [
            name for name in required_files if name not in {"README.md", "PACKAGE_MANIFEST.json"}
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as bundle:
        for name, content in required_files.items():
            bundle.writestr(name, content)
        bundle.writestr("PACKAGE_MANIFEST.json", json.dumps(package_manifest))


def test_completed_submit_kpis_surface_in_session_summary(server_app) -> None:
    client = TestClient(server_app.app)
    session_id = client.post(
        "/api/copilot/plan", json={"text": "帮我建一个悬臂梁", "backend": "template"}
    ).json()["session_id"]

    assert client.get(f"/api/copilot/sessions/{session_id}").json()["kpis"] is None

    client.post(
        f"/api/copilot/sessions/{session_id}/action-result",
        json={
            "action_index": 2,
            "status": "completed",
            "message": "Executed inside Abaqus/CAE",
            "payload": {
                "action": "submit_job_or_prepare_run",
                "kpis": {
                    "job_name": "Copilot_Cantilever_Job",
                    "status": "COMPLETED",
                    "max_displacement": 0.1286,
                    "max_mises": 9.58,
                },
            },
        },
    )

    summary = client.get(f"/api/copilot/sessions/{session_id}").json()
    assert summary["kpis"]["max_mises"] == 9.58
    assert summary["kpis"]["job_name"] == "Copilot_Cantilever_Job"
