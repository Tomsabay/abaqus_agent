"""CAE plugin failures must come with a plain-language diagnosis.

Covers doctor/cae_errors.py pattern matching and the server wiring that
attaches a diagnosis to failed action-results so the workspace error pane
can explain failures instead of only dumping tracebacks.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from copilot import routes as copilot_routes

from doctor.cae_errors import diagnose_cae_traceback, list_cae_error_patterns

# Shapes captured from real plugin failures. The paths are rewritten to a
# neutral install root — the matcher keys off the exception type and message,
# never the path, and a real checkout path in a fixture is the sort of thing
# that ends up published.
REAL_LOCK_TRACEBACK = """Traceback (most recent call last):
  File "C:\\sim\\abaqus_agent\\plugins\\abaqus_agent\\abaqusAgent_plugin.py", line 214, in execute_next_copilot_action
    exec(script, globals(), globals())
  File "<string>", line 5, in <module>
IOError: IOError: C:/sim/abaqus_agent/artifacts/replay_recordings/20260705_144400/Copilot_Cantilever_Job.cae: Permission denied
"""


REAL_EXEC_KEYERROR_TRACEBACK = """Traceback (most recent call last):
  File "C:\\sim\\abaqus_agent\\plugins\\abaqus_agent\\abaqusAgent_plugin.py", line 240, in execute_next_copilot_action
    exec(script, globals(), globals())
  File "<string>", line 2, in <module>
KeyError: 'Copilot_Cantilever'
"""


@pytest.mark.parametrize(
    ("traceback_text", "expected_pattern"),
    [
        (REAL_LOCK_TRACEBACK, "stale_lock_or_readonly_cae"),
        ("MdbError: The model database D:/x/Job.cae is locked by another session", "stale_lock_or_readonly_cae"),
        ("AbaqusException: License checkout failed for cae", "license_checkout_failed"),
        # exec-ed scripts hide the source line, so this is what a missing
        # model/part/set really looks like coming from the plugin
        (REAL_EXEC_KEYERROR_TRACEBACK, "model_or_part_missing"),
        ("KeyError: mdb.models['Copilot_Cantilever'] not found", "model_or_part_missing"),
        ("NameError: name 'COPILOT_MODEL_NAME' is not defined", "model_or_part_missing"),
        ("RuntimeError: Copilot could not find the left fixed face", "geometry_selection_failed"),
        ("RuntimeError: Copilot could not find right-end load nodes", "geometry_selection_failed"),
        ("RuntimeError: Copilot could not find mid-span load nodes", "geometry_selection_failed"),
        ("OdbError: Cannot open file Copilot_Cantilever_Job.odb", "odb_missing_or_unreadable"),
        ("AbaqusException: Job Copilot_Cantilever_Job aborted due to errors", "job_aborted"),
        ("RuntimeError: Abaqus job Copilot_Cantilever_Job aborted (status None); see the .msg/.sta logs", "job_aborted"),
        ("AbaqusException: The name Copilot_Cantilever_Job is already in use", "name_already_in_use"),
        ("AbaqusException: Feature creation failed.", "feature_creation_failed"),
        ("SyntaxError: invalid syntax (<string>, line 3)", "generated_code_syntax_error"),
        ("TypeError: rectangle() got an unexpected keyword argument 'point3'", "api_parameter_mismatch"),
        ("IOError: [Errno 28] No space left on device: 'Copilot_Cantilever_Job.odb'", "disk_full"),
        ("IOError: [Errno 2] No such file or directory: 'Copilot_Cantilever_Job.inp'", "file_not_found"),
        ("IOError: [Errno 13] Permission denied: 'report.txt'", "permission_denied"),
        ("MemoryError", "out_of_memory"),
        ("***ERROR: 80 elements have been defined without section properties", "section_or_material_missing"),
    ],
)
def test_known_cae_failures_get_matched_diagnosis(traceback_text, expected_pattern) -> None:
    diagnosis = diagnose_cae_traceback(traceback_text)

    assert diagnosis["matched"] is True
    assert diagnosis["pattern_id"] == expected_pattern
    # every matched diagnosis must speak Chinese to the user, not solver-ese
    assert diagnosis["title"]
    assert diagnosis["explanation"]
    assert diagnosis["suggestion"]


def test_unknown_failure_still_returns_usable_fallback() -> None:
    diagnosis = diagnose_cae_traceback("ZeroDivisionError: division by zero")

    assert diagnosis["matched"] is False
    assert diagnosis["pattern_id"] == "unknown"
    assert diagnosis["error_line"] == "ZeroDivisionError: division by zero"
    assert diagnosis["suggestion"]


def test_empty_traceback_does_not_crash() -> None:
    diagnosis = diagnose_cae_traceback("")

    assert diagnosis["matched"] is False
    assert diagnosis["error_line"] == ""


def test_pattern_catalog_is_well_formed() -> None:
    patterns = list_cae_error_patterns()

    assert len(patterns) >= 14
    assert len({pattern["id"] for pattern in patterns}) == len(patterns)
    for pattern in patterns:
        assert set(pattern) == {"id", "regex", "title", "explanation", "suggestion"}


def test_failed_action_result_gets_diagnosis_attached(monkeypatch, tmp_path) -> None:
    import server

    monkeypatch.setattr(copilot_routes, "COPILOT_SESSION_FILE", tmp_path / ".abaqus_agent_session")
    monkeypatch.setattr(copilot_routes, "COPILOT_SESSION_STORE_DIR", tmp_path / "copilot_sessions")
    original = dict(server.COPILOT_SESSIONS)
    server.COPILOT_SESSIONS.clear()
    try:
        client = TestClient(server.app)
        planned = client.post(
            "/api/copilot/plan", json={"text": "帮我建一个悬臂梁", "backend": "template"}
        )
        session_id = planned.json()["session_id"]

        client.post(
            f"/api/copilot/sessions/{session_id}/action-result",
            json={
                "action_index": 2,
                "status": "failed",
                "message": "Abaqus/CAE execution failed",
                "payload": {"action": "submit_job_or_prepare_run", "traceback": REAL_LOCK_TRACEBACK},
            },
        )

        session = client.get(f"/api/copilot/sessions/{session_id}").json()
        error = session["errors"][0]
        assert error["diagnosis"]["pattern_id"] == "stale_lock_or_readonly_cae"
        assert error["diagnosis"]["title"] == "模型数据库被锁定或无法写入"
        assert ".lck" in error["diagnosis"]["suggestion"]

        # successful results must NOT carry a diagnosis
        client.post(
            f"/api/copilot/sessions/{session_id}/action-result",
            json={"action_index": 0, "status": "completed", "message": "ok"},
        )
        session = client.get(f"/api/copilot/sessions/{session_id}").json()
        completed = [r for r in session["results"] if r["status"] == "completed"]
        assert completed and "diagnosis" not in completed[0]
    finally:
        server.COPILOT_SESSIONS.clear()
        server.COPILOT_SESSIONS.update(original)


def test_failed_solve_with_solver_logs_gets_doctor_findings(monkeypatch, tmp_path) -> None:
    import server

    monkeypatch.setattr(copilot_routes, "COPILOT_SESSION_FILE", tmp_path / ".abaqus_agent_session")
    monkeypatch.setattr(copilot_routes, "COPILOT_SESSION_STORE_DIR", tmp_path / "copilot_sessions")
    original = dict(server.COPILOT_SESSIONS)
    server.COPILOT_SESSIONS.clear()
    try:
        client = TestClient(server.app)
        session_id = client.post(
            "/api/copilot/plan", json={"text": "帮我建一个悬臂梁", "backend": "template"}
        ).json()["session_id"]

        client.post(
            f"/api/copilot/sessions/{session_id}/action-result",
            json={
                "action_index": 2,
                "status": "failed",
                "message": "Abaqus/CAE execution failed",
                "payload": {
                    "action": "submit_job_or_prepare_run",
                    "traceback": "AbaqusException: Job Copilot_Cantilever_Job aborted due to errors",
                    "job_name": "Copilot_Cantilever_Job",
                    "solver_logs": {
                        ".msg": "***ERROR: TOO MANY ATTEMPTS MADE FOR THIS INCREMENT\n",
                        ".sta": "THE ANALYSIS HAS NOT BEEN COMPLETED\n",
                    },
                },
            },
        )

        error = client.get(f"/api/copilot/sessions/{session_id}").json()["errors"][0]
        assert error["diagnosis"]["pattern_id"] == "job_aborted"
        doctor = error["solver_doctor"]
        assert doctor["status"] == "FAILED"
        assert doctor["primary_category"] == "CONVERGENCE"
        assert doctor["findings"]
        assert doctor["findings"][0]["recommendation"]
    finally:
        server.COPILOT_SESSIONS.clear()
        server.COPILOT_SESSIONS.update(original)


def test_malformed_solver_logs_do_not_break_result_recording(monkeypatch, tmp_path) -> None:
    import server

    monkeypatch.setattr(copilot_routes, "COPILOT_SESSION_FILE", tmp_path / ".abaqus_agent_session")
    monkeypatch.setattr(copilot_routes, "COPILOT_SESSION_STORE_DIR", tmp_path / "copilot_sessions")
    original = dict(server.COPILOT_SESSIONS)
    server.COPILOT_SESSIONS.clear()
    try:
        client = TestClient(server.app)
        session_id = client.post(
            "/api/copilot/plan", json={"text": "帮我建一个悬臂梁", "backend": "template"}
        ).json()["session_id"]

        res = client.post(
            f"/api/copilot/sessions/{session_id}/action-result",
            json={
                "action_index": 0,
                "status": "failed",
                "message": "boom",
                "payload": {
                    "traceback": "RuntimeError: x",
                    "job_name": "../..;evil name",  # rejected by validate_job_name
                    "solver_logs": {".weird": "unsupported suffix"},
                },
            },
        )

        assert res.status_code == 200
        error = client.get(f"/api/copilot/sessions/{session_id}").json()["errors"][0]
        assert "solver_doctor" not in error
        assert error["diagnosis"]["pattern_id"] == "unknown"
    finally:
        server.COPILOT_SESSIONS.clear()
        server.COPILOT_SESSIONS.update(original)


def test_cae_pattern_catalog_endpoint_serves_gallery() -> None:
    import server
    client = TestClient(server.app)

    data = client.get("/api/doctor/cae-patterns").json()

    assert data["total"] >= 14
    assert data["total"] == len(data["patterns"])
    first = data["patterns"][0]
    assert {"id", "regex", "title", "explanation", "suggestion"} <= set(first)
    # the gallery speaks Chinese to the user
    assert any("锁定" in p["title"] for p in data["patterns"])


def test_cae_diagnose_endpoint_diagnoses_pasted_traceback() -> None:
    import server
    client = TestClient(server.app)

    res = client.post("/api/doctor/cae-diagnose", json={"traceback": REAL_LOCK_TRACEBACK})
    assert res.status_code == 200
    data = res.json()
    assert data["matched"] is True
    assert data["pattern_id"] == "stale_lock_or_readonly_cae"
    assert data["title"] == "模型数据库被锁定或无法写入"

    unknown = client.post(
        "/api/doctor/cae-diagnose", json={"traceback": "ZeroDivisionError: division by zero"}
    ).json()
    assert unknown["matched"] is False
    assert unknown["pattern_id"] == "unknown"

    assert client.post("/api/doctor/cae-diagnose", json={"traceback": "   "}).status_code == 400
