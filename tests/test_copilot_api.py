from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def server_app(monkeypatch, tmp_path):
    import server
    from premium.licensing import feature_gate

    monkeypatch.setenv("ABAQUS_AGENT_EVIDENCE_VAULT", str(tmp_path / "vault"))
    original_runs = dict(server.RUNS)
    original_copilot = dict(server.COPILOT_SESSIONS)
    original_session_file = server.COPILOT_SESSION_FILE
    server.COPILOT_SESSION_FILE = tmp_path / ".abaqus_agent_session"
    server.RUNS.clear()
    server.COPILOT_SESSIONS.clear()
    feature_gate.reset()
    try:
        yield server
    finally:
        server.RUNS.clear()
        server.RUNS.update(original_runs)
        server.COPILOT_SESSIONS.clear()
        server.COPILOT_SESSIONS.update(original_copilot)
        server.COPILOT_SESSION_FILE = original_session_file
        feature_gate.reset()


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

    monkeypatch.setattr(server_app, "build_copilot_alpha_package", fake_build_copilot_alpha_package)
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
    ]
    missing = [marker for marker in required_markers if marker not in source]
    assert missing == []


def test_install_copilot_plugin_copies_plugin_and_writes_session(monkeypatch, tmp_path) -> None:
    from scripts.install_copilot_plugin import install_copilot_plugin

    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    target = tmp_path / "abaqus_plugins"
    result = install_copilot_plugin(
        target,
        server_url="http://100.109.206.119:8000",
        session_id="copilot-test",
        write_session_file=True,
    )

    plugin_path = Path(result["plugin_path"])
    assert result["status"] == "installed"
    assert plugin_path.exists()
    assert plugin_path.name == "abaqusAgent_plugin.py"
    assert Path(result["config_path"]).exists()
    config = Path(result["config_path"]).read_text(encoding="utf-8")
    assert "http://100.109.206.119:8000" in config
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
