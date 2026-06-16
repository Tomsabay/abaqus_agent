from __future__ import annotations

import json
import zipfile
from pathlib import Path

from scripts.package_copilot_alpha import build_copilot_alpha_package
from scripts.verify_copilot_alpha_package import verify_copilot_alpha_package


def test_build_copilot_alpha_package_includes_plugin_docs_and_evidence(tmp_path: Path) -> None:
    _write_package_inputs(tmp_path)

    result = build_copilot_alpha_package(
        root=tmp_path,
        out_dir=Path("out"),
        server_url="http://100.109.206.119:8000/",
    )

    package_path = Path(result["package_path"])
    assert result["status"] == "packaged"
    assert result["overall_status"] == "ALPHA_READY_WITH_GUI_BLOCKER"
    assert package_path.exists()
    with zipfile.ZipFile(package_path) as bundle:
        names = set(bundle.namelist())
        assert "plugin/abaqusAgent_plugin.py" in names
        assert "plugin/abaqus_agent_config.example.json" in names
        assert "docs/COPILOT_MVP.md" in names
        assert "evidence/copilot_alpha_release_gate.json" in names
        assert "evidence/plugin_manifest/abaqus_agent_plugin_manifest.json" in names
        assert "PACKAGE_MANIFEST.json" in names
        manifest = json.loads(bundle.read("PACKAGE_MANIFEST.json").decode("utf-8"))
        config = json.loads(bundle.read("plugin/abaqus_agent_config.example.json").decode("utf-8"))
    assert manifest["overall_status"] == "ALPHA_READY_WITH_GUI_BLOCKER"
    assert manifest["strict_gui_ready"] is False
    assert manifest["default_server_url"] == "http://100.109.206.119:8000"
    assert config["server_url"] == "http://100.109.206.119:8000"
    assert "plugin/abaqus_agent_config.example.json" in manifest["included_files"]

    verification = verify_copilot_alpha_package(package_path)
    assert verification["overall_status"] == "PASS"
    assert {check["id"] for check in verification["checks"]} == {
        "required_members",
        "package_manifest",
        "release_gate_evidence",
        "config_example",
    }


def _write_package_inputs(root: Path) -> None:
    _write_text(root / "plugins/abaqus_agent/abaqusAgent_plugin.py", "# plugin")
    _write_text(root / "plugins/abaqus_agent/README.md", "# plugin readme")
    _write_text(root / "docs/COPILOT_MVP.md", "# docs")
    _write_json(
        root / "artifacts/copilot/real_smoke_cli_codex/Cantilever_200mm_Static_copilot_result.json",
        {"status": "COMPLETED"},
    )
    _write_json(
        root / "artifacts/copilot/plugin_run_plan_codex/copilot_plugin_run_plan_trace.json",
        {"status": "completed", "summary": {"completed_count": 3, "pending_count": 0}},
    )
    _write_json(
        root / "artifacts/copilot/plugin_run_plan_codex/Cantilever_200mm_Static_copilot_result.json",
        {"status": "COMPLETED"},
    )
    _write_json(
        root / "artifacts/copilot/plugin_manifest/abaqus_agent_plugin_manifest.json",
        {
            "default_action": "AbaqusAgent Copilot: Run Current Plan",
            "menu_entries": [
                "AbaqusAgent Copilot: Open Sidecar",
                "AbaqusAgent Copilot: Run Current Plan",
                "AbaqusAgent Copilot: Execute Next Action",
                "AbaqusAgent Copilot: Check Session Status",
            ],
        },
    )
    screenshot = root / "artifacts/copilot/desktop_before_cae.png"
    screenshot.parent.mkdir(parents=True, exist_ok=True)
    screenshot.write_bytes(b"black")


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
