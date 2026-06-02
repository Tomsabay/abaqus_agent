"""Tests for validation environment preflight checks."""

from __future__ import annotations

import subprocess
from pathlib import Path

from validation.preflight import render_preflight_markdown, run_environment_preflight


def test_preflight_reports_missing_abaqus(monkeypatch):
    monkeypatch.setattr("validation.preflight.shutil.which", lambda _cmd: None)

    result = run_environment_preflight(abaqus_cmd="abaqus_missing_for_test")

    assert result["status"] == "missing_abaqus"
    assert result["abaqus"]["command_found"] is False
    assert result["abaqus"]["release_check"]["status"] == "not_run"


def test_preflight_detects_release(monkeypatch, tmp_path):
    fake_cmd = tmp_path / "abaqus.bat"
    fake_cmd.write_text("@echo off\n", encoding="utf-8")

    def fake_run(command, **_kwargs):
        assert command == [str(fake_cmd), "information=release"]
        return subprocess.CompletedProcess(
            command,
            0,
            stdout="Abaqus 2026\n",
            stderr="",
        )

    monkeypatch.setattr("validation.preflight.subprocess.run", fake_run)

    result = run_environment_preflight(abaqus_cmd=str(fake_cmd), timeout_seconds=1.0, expected_release="Abaqus 2026")

    assert result["status"] == "ready"
    assert result["abaqus"]["release_check"]["status"] == "pass"
    assert result["abaqus"]["release_check"]["version"] == "2026"
    assert result["abaqus"]["expected_release"] == "2026"
    assert result["abaqus"]["release_match"]["status"] == "pass"
    assert result["checks"][-1]["name"] == "abaqus_release_target"


def test_preflight_detects_release_mismatch(monkeypatch, tmp_path):
    fake_cmd = tmp_path / "abaqus"
    fake_cmd.write_text("#!/bin/sh\n", encoding="utf-8")

    def fake_run(command, **_kwargs):
        return subprocess.CompletedProcess(
            command,
            0,
            stdout="SIMULIA Abaqus 2021\n",
            stderr="",
        )

    monkeypatch.setattr("validation.preflight.subprocess.run", fake_run)

    result = run_environment_preflight(abaqus_cmd=str(fake_cmd), expected_release="2026")

    assert result["status"] == "release_mismatch"
    assert result["abaqus"]["release_match"]["status"] == "fail"
    assert result["abaqus"]["release_match"]["detected"] == "2021"


def test_preflight_skip_release_check(monkeypatch):
    monkeypatch.setattr("validation.preflight.shutil.which", lambda _cmd: "/opt/abaqus/abaqus")

    result = run_environment_preflight(abaqus_cmd="abaqus", check_release=False)

    assert result["status"] == "unknown"
    assert result["abaqus"]["resolved_path"] == str(Path("/opt/abaqus/abaqus"))
    assert result["abaqus"]["release_check"]["status"] == "skipped"


def test_preflight_markdown_contains_evidence():
    text = render_preflight_markdown({
        "status": "ready",
        "platform": {
            "system": "Windows",
            "release": "11",
            "machine": "AMD64",
            "python_version": "3.12.0",
            "python_executable": "python",
            "cwd": "D:\\tmp",
        },
        "abaqus": {
            "command": "abaqus",
            "resolved_path": "C:\\SIMULIA\\Commands\\abaqus.bat",
            "command_found": True,
            "release_check": {
                "status": "pass",
                "version": "2026",
                "command": ["abaqus", "information=release"],
                "returncode": 0,
                "output": "Abaqus 2026",
                "error": "",
            },
            "expected_release": "2026",
            "release_match": {"status": "pass", "expected": "2026", "detected": "2026"},
        },
        "checks": [{"name": "abaqus_command", "status": "pass", "detail": "ok"}],
    })

    assert "Abaqus Environment Preflight" in text
    assert "Overall: READY" in text
    assert "Detected release: 2026" in text
    assert "Expected release: 2026" in text
    assert "Release match: pass" in text
