from __future__ import annotations

import json
from pathlib import Path

from scripts.verify_copilot_alpha_release import collect_release_gate, write_release_gate


def test_copilot_alpha_release_gate_allows_alpha_with_gui_blocker(tmp_path: Path) -> None:
    _write_release_evidence(tmp_path)

    report = collect_release_gate(root=tmp_path)

    assert report["overall_status"] == "ALPHA_READY_WITH_GUI_BLOCKER"
    checks = {check["id"]: check for check in report["checks"]}
    assert checks["codex_strict_real_abaqus_smoke"]["status"] == "PASS"
    assert checks["plugin_run_current_plan_real_abaqus"]["status"] == "PASS"
    assert checks["plugin_runtime_manifest"]["status"] == "PASS"
    assert checks["interactive_cae_gui_visual"]["status"] == "BLOCKED"
    assert "RDP/console" in checks["interactive_cae_gui_visual"]["evidence"]["blocker"]


def test_copilot_alpha_release_gate_strict_gui_fails(tmp_path: Path) -> None:
    _write_release_evidence(tmp_path)

    report = collect_release_gate(root=tmp_path, strict_gui=True)

    assert report["overall_status"] == "FAIL"


def test_copilot_alpha_release_gate_writes_json_and_markdown(tmp_path: Path) -> None:
    _write_release_evidence(tmp_path)
    report = collect_release_gate(root=tmp_path)

    files = write_release_gate(report, tmp_path / "out")

    assert Path(files["json"]).exists()
    assert Path(files["markdown"]).exists()
    assert "ALPHA_READY_WITH_GUI_BLOCKER" in Path(files["markdown"]).read_text(encoding="utf-8")


def _write_release_evidence(root: Path) -> None:
    _write_json(
        root / "artifacts/copilot/real_smoke_cli_codex/Cantilever_200mm_Static_copilot_result.json",
        {
            "job_name": "Cantilever_200mm_Static",
            "max_displacement": 0.12858134508132935,
            "max_mises": 9.57726764678955,
            "status": "COMPLETED",
        },
    )
    _write_json(
        root / "artifacts/copilot/plugin_run_plan_codex/copilot_plugin_run_plan_trace.json",
        {
            "status": "completed",
            "executed": [
                {"action": "create_cantilever_model"},
                {"action": "apply_boundary_condition"},
                {"action": "submit_job_or_prepare_run"},
            ],
            "summary": {"completed_count": 3, "pending_count": 0},
        },
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
            "server_url": "http://100.109.206.119:8000",
            "session_id": "copilot-test",
        },
    )
    screenshot = root / "artifacts/copilot/desktop_before_cae.png"
    screenshot.parent.mkdir(parents=True, exist_ok=True)
    screenshot.write_bytes(b"black")


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
