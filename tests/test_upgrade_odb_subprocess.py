from __future__ import annotations

import importlib
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

upgrade_module = importlib.import_module("post.upgrade_odb")


def test_upgrade_odb_invokes_abaqus_python_and_reads_result(tmp_path, monkeypatch):
    odb_path = tmp_path / "model.odb"
    odb_path.write_text("fake odb placeholder", encoding="utf-8")
    result_payload = {
        "upgrade_required": True,
        "upgraded": True,
        "original_path": str(odb_path.resolve()),
        "output_path": str((tmp_path / "model_upgraded.odb").resolve()),
        "error": None,
    }
    writer_calls: list[Path] = []
    run_calls: list[dict] = []

    def fake_write_inner_script(path):
        writer_calls.append(path)

    def fake_run(cmd, capture_output, text, timeout, **kwargs):
        run_calls.append(
            {
                "cmd": cmd,
                "capture_output": capture_output,
                "text": text,
                "timeout": timeout,
            }
        )
        Path(cmd[-1]).write_text(json.dumps(result_payload), encoding="utf-8")
        return SimpleNamespace(returncode=0, stdout="ODB_UPGRADED", stderr="")

    monkeypatch.setattr(upgrade_module, "_write_inner_script", fake_write_inner_script)
    monkeypatch.setattr(subprocess, "run", fake_run)

    result = upgrade_module.upgrade_odb_if_needed(odb_path)

    inner_script = Path(upgrade_module.__file__).parent / "_upgrade_inner.py"
    result_file = odb_path.resolve().parent / "_upgrade_result.json"
    assert result == result_payload
    assert writer_calls == [inner_script]
    assert run_calls == [
        {
            "cmd": [
                "abaqus",
                "python",
                str(inner_script),
                "--",
                str(odb_path.resolve()),
                str((tmp_path / "model_upgraded.odb").resolve()),
                str(result_file),
            ],
            "capture_output": True,
            "text": True,
            "timeout": 300,
        }
    ]


def test_upgrade_odb_uses_explicit_upgraded_path_in_command(tmp_path, monkeypatch):
    odb_path = tmp_path / "model.odb"
    upgraded_path = tmp_path / "custom-output.odb"
    run_calls: list[list[str]] = []

    monkeypatch.setattr(upgrade_module, "_write_inner_script", lambda path: None)

    def fake_run(cmd, **kwargs):
        run_calls.append(cmd)
        Path(cmd[-1]).write_text(
            json.dumps(
                {
                    "upgrade_required": False,
                    "upgraded": False,
                    "original_path": str(odb_path.resolve()),
                    "output_path": str(odb_path.resolve()),
                    "error": None,
                }
            ),
            encoding="utf-8",
        )
        return SimpleNamespace(returncode=0, stdout="ODB_OK", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = upgrade_module.upgrade_odb_if_needed(odb_path, upgraded_path=upgraded_path)

    assert result["upgrade_required"] is False
    assert run_calls[0][-2] == str(upgraded_path.resolve())


def test_upgrade_odb_returns_missing_abaqus_error(tmp_path, monkeypatch):
    odb_path = tmp_path / "model.odb"

    monkeypatch.setattr(upgrade_module, "_write_inner_script", lambda path: None)

    def fake_run(*args, **kwargs):
        raise FileNotFoundError("abaqus")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = upgrade_module.upgrade_odb_if_needed(odb_path)

    assert result == {
        "upgrade_required": None,
        "upgraded": False,
        "original_path": str(odb_path.resolve()),
        "output_path": str(odb_path.resolve()),
        "error": "'abaqus' not found in PATH",
    }


def test_upgrade_odb_returns_timeout_error(tmp_path, monkeypatch):
    odb_path = tmp_path / "model.odb"

    monkeypatch.setattr(upgrade_module, "_write_inner_script", lambda path: None)

    def fake_run(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd=cmd, timeout=kwargs["timeout"])

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = upgrade_module.upgrade_odb_if_needed(odb_path)

    assert result == {
        "upgrade_required": None,
        "upgraded": False,
        "original_path": str(odb_path.resolve()),
        "output_path": str(odb_path.resolve()),
        "error": "Upgrade timed out",
    }


def test_upgrade_odb_uses_stderr_when_result_file_missing(tmp_path, monkeypatch):
    odb_path = tmp_path / "model.odb"

    monkeypatch.setattr(upgrade_module, "_write_inner_script", lambda path: None)

    def fake_run(*args, **kwargs):
        return SimpleNamespace(returncode=1, stdout="", stderr="ODB upgrade failed")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = upgrade_module.upgrade_odb_if_needed(odb_path)

    assert result == {
        "upgrade_required": None,
        "upgraded": False,
        "original_path": str(odb_path.resolve()),
        "output_path": str(odb_path.resolve()),
        "error": "ODB upgrade failed",
    }


def test_write_inner_script_contains_odb_access_upgrade_calls(tmp_path):
    script_path = tmp_path / "_upgrade_inner.py"

    upgrade_module._write_inner_script(script_path)

    text = script_path.read_text(encoding="utf-8")
    assert "import odbAccess" in text
    assert "isUpgradeRequiredForOdb" in text
    assert "upgradeOdb" in text
    assert "ODB_UPGRADED" in text
