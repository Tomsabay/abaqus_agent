"""Copilot sessions must survive a server restart.

The dev loop restarts the FastAPI server constantly; before persistence, the
plugin's session file pointed at a dead session and the workspace went blank.
These tests simulate the restart: mutate a session, wipe the in-memory store,
rehydrate from disk, and expect identical behavior.
"""

from __future__ import annotations

import base64
import json

import pytest
from fastapi.testclient import TestClient

from copilot import routes as copilot_routes

PNG = b"\x89PNG\r\n\x1a\n" + b"restart-me"


@pytest.fixture
def persistent_server(monkeypatch, tmp_path):
    import server

    # The store lives in copilot/routes.py now, so patch the names the routes
    # actually read. server.COPILOT_SESSIONS is the same dict object.
    from copilot import routes as copilot_routes

    monkeypatch.setattr(copilot_routes, "COPILOT_SESSION_FILE",
                        tmp_path / ".abaqus_agent_session")
    monkeypatch.setattr(copilot_routes, "COPILOT_SESSION_STORE_DIR",
                        tmp_path / "copilot_sessions")
    original = dict(server.COPILOT_SESSIONS)
    server.COPILOT_SESSIONS.clear()
    try:
        yield server
    finally:
        server.COPILOT_SESSIONS.clear()
        server.COPILOT_SESSIONS.update(original)


def _build_session(server) -> str:
    client = TestClient(server.app)
    plan = client.post(
        "/api/copilot/plan", json={"text": "帮我建一个悬臂梁", "backend": "template"}
    ).json()
    session_id = plan["session_id"]
    client.post(
        f"/api/copilot/sessions/{session_id}/action-result",
        json={"action_index": 0, "status": "completed", "message": "ok"},
    )
    client.post(
        f"/api/copilot/sessions/{session_id}/action-result",
        json={
            "action_index": 1,
            "status": "failed",
            "message": "Abaqus/CAE execution failed",
            "payload": {"traceback": "IOError: Job.cae: Permission denied (.lck)"},
        },
    )
    client.post(
        f"/api/copilot/sessions/{session_id}/model-state",
        json={"models": [{"name": "Beam", "parts": ["Beam"]}], "active_model": "Beam"},
    )
    client.post(
        f"/api/copilot/sessions/{session_id}/viewport",
        json={"image_base64": base64.b64encode(PNG).decode("ascii"), "caption": "step"},
    )
    return session_id


def test_session_survives_restart_with_viewport_and_diagnosis(persistent_server) -> None:
    server = persistent_server
    session_id = _build_session(server)

    # simulated restart: in-memory store gone, disk store rehydrated
    server.COPILOT_SESSIONS.clear()
    loaded = copilot_routes._load_copilot_sessions_from_disk()
    assert loaded == 1

    client = TestClient(server.app)
    summary = client.get(f"/api/copilot/sessions/{session_id}").json()
    assert summary["completed_count"] == 1
    assert summary["pending_count"] == 1
    assert summary["errors"][0]["diagnosis"]["pattern_id"] == "stale_lock_or_readonly_cae"

    state = client.get(f"/api/copilot/sessions/{session_id}/model-state").json()
    assert state["models"][0]["name"] == "Beam"

    png = client.get(f"/api/copilot/sessions/{session_id}/viewport.png")
    assert png.status_code == 200
    assert png.content == PNG

    # the rehydrated session keeps accepting plugin results
    result = client.post(
        f"/api/copilot/sessions/{session_id}/action-result",
        json={"action_index": 2, "status": "completed", "message": "ok"},
    )
    assert result.status_code == 200
    assert result.json()["remaining_actions"] == 0


def test_corrupt_session_file_does_not_block_startup(persistent_server) -> None:
    server = persistent_server
    session_id = _build_session(server)
    (copilot_routes.COPILOT_SESSION_STORE_DIR / "copilot-corrupt.json").write_text(
        "{broken", encoding="utf-8"
    )

    server.COPILOT_SESSIONS.clear()
    loaded = copilot_routes._load_copilot_sessions_from_disk()

    assert loaded == 1
    assert session_id in server.COPILOT_SESSIONS
    assert "copilot-corrupt" not in server.COPILOT_SESSIONS


def test_store_prunes_to_keep_limit(persistent_server, monkeypatch) -> None:
    server = persistent_server
    monkeypatch.setattr(copilot_routes, "COPILOT_SESSION_STORE_KEEP", 3)
    client = TestClient(server.app)
    for _ in range(6):
        client.post("/api/copilot/plan", json={"text": "悬臂梁", "backend": "template"})

    files = list(copilot_routes.COPILOT_SESSION_STORE_DIR.glob("copilot-*.json"))
    assert len(files) == 3


def test_persisted_file_is_valid_json_with_base64_viewport(persistent_server) -> None:
    server = persistent_server
    session_id = _build_session(server)

    raw = json.loads(
        (copilot_routes.COPILOT_SESSION_STORE_DIR / f"{session_id}.json").read_text(encoding="utf-8")
    )
    assert raw["viewport"]["png_encoding"] == "base64"
    assert base64.b64decode(raw["viewport"]["png"]) == PNG
