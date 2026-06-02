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
    workdir = tmp_path / "runs"
    workdir.mkdir()
    monkeypatch.setenv("LM_LICENSE_FILE", "masked")

    def fake_run(command, **_kwargs):
        assert command == [str(fake_cmd), "information=release"]
        return subprocess.CompletedProcess(
            command,
            0,
            stdout="Abaqus 2026\n",
            stderr="",
        )

    monkeypatch.setattr("validation.preflight.subprocess.run", fake_run)

    result = run_environment_preflight(
        abaqus_cmd=str(fake_cmd),
        timeout_seconds=1.0,
        expected_release="Abaqus 2026",
        workdir=str(workdir),
        runner_cfg={"cpus": 4, "mp_mode": "threads", "timeout_seconds": 120},
    )

    assert result["status"] == "ready"
    assert result["schema_version"] == "0.2"
    assert result["abaqus"]["release_check"]["status"] == "pass"
    assert result["abaqus"]["release_check"]["version"] == "2026"
    assert result["abaqus"]["expected_release"] == "2026"
    assert result["abaqus"]["release_match"]["status"] == "pass"
    assert result["environment"]["workdir"]["writable"] is True
    assert result["environment"]["license"]["present"] == ["LM_LICENSE_FILE"]
    assert result["runner"]["status"] == "pass"
    assert {check["name"] for check in result["checks"]} >= {
        "abaqus_release_target",
        "workdir_writable",
        "license_environment",
        "runner_cfg",
    }


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


def test_preflight_fails_missing_workdir(monkeypatch, tmp_path):
    fake_cmd = tmp_path / "abaqus"
    fake_cmd.write_text("#!/bin/sh\n", encoding="utf-8")

    def fake_run(command, **_kwargs):
        return subprocess.CompletedProcess(command, 0, stdout="Abaqus 2026\n", stderr="")

    monkeypatch.setattr("validation.preflight.subprocess.run", fake_run)

    result = run_environment_preflight(
        abaqus_cmd=str(fake_cmd),
        workdir=str(tmp_path / "missing"),
    )

    assert result["status"] == "environment_failed"
    assert result["environment"]["workdir"]["status"] == "fail"
    assert any(check["name"] == "workdir_writable" and check["status"] == "fail" for check in result["checks"])


def test_preflight_fails_invalid_runner_cfg(monkeypatch, tmp_path):
    fake_cmd = tmp_path / "abaqus"
    fake_cmd.write_text("#!/bin/sh\n", encoding="utf-8")

    def fake_run(command, **_kwargs):
        return subprocess.CompletedProcess(command, 0, stdout="Abaqus 2026\n", stderr="")

    monkeypatch.setattr("validation.preflight.subprocess.run", fake_run)

    result = run_environment_preflight(
        abaqus_cmd=str(fake_cmd),
        runner_cfg={"cpus": 0, "mp_mode": "bad", "timeout_seconds": -1},
    )

    assert result["status"] == "runner_cfg_failed"
    assert result["runner"]["status"] == "fail"
    assert "cpus must be >= 1" in result["runner"]["issues"]
    assert "mp_mode must be 'threads' or 'mpi'" in result["runner"]["issues"]


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
        "environment": {
            "workdir": {"status": "pass", "path": "D:\\tmp", "exists": True, "writable": True},
            "license": {"status": "warn", "present": [], "missing": ["LM_LICENSE_FILE"]},
        },
        "runner": {
            "status": "pass",
            "cpus": 4,
            "mp_mode": "threads",
            "memory": "8gb",
            "timeout_seconds": 120,
            "issues": [],
        },
        "checks": [{"name": "abaqus_command", "status": "pass", "detail": "ok"}],
        "next_actions": ["Confirm license configuration."],
    })

    assert "Abaqus Environment Preflight" in text
    assert "Overall: READY" in text
    assert "Detected release: 2026" in text
    assert "Expected release: 2026" in text
    assert "Release match: pass" in text
    assert "Run Environment" in text
    assert "License variables present" in text
    assert "Runner Config" in text
