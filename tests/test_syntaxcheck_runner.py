from types import SimpleNamespace

import pytest

import runner.syntaxcheck as syntaxcheck_module
from tools.errors import AbaqusAgentError, ErrorCode


def test_syntaxcheck_builds_command_writes_log_and_parses_warnings(tmp_path, monkeypatch):
    inp_path = tmp_path / "model.inp"
    inp_path.write_text("*Heading\n", encoding="utf-8")
    workdir = tmp_path / "work"
    calls = []

    def fake_run(cmd, cwd, capture_output, text, timeout):
        calls.append(
            {
                "cmd": cmd,
                "cwd": cwd,
                "capture_output": capture_output,
                "text": text,
                "timeout": timeout,
            }
        )
        (workdir / "model_syntaxcheck.dat").write_text(
            "***WARNING: CHECK THIS SECTION\n",
            encoding="utf-8",
        )
        return SimpleNamespace(returncode=0, stdout="Abaqus syntaxcheck complete", stderr="")

    monkeypatch.setattr(syntaxcheck_module.subprocess, "run", fake_run)

    result = syntaxcheck_module.syntaxcheck_inp(inp_path, workdir)

    assert calls == [
        {
            "cmd": [
                "abaqus",
                "job=model_syntaxcheck",
                f"input={inp_path.resolve()}",
                "syntaxcheck",
                "interactive",
            ],
            "cwd": str(workdir),
            "capture_output": True,
            "text": True,
            "timeout": 120,
        }
    ]
    assert result["ok"] is True
    assert result["warnings"] == ["***WARNING: CHECK THIS SECTION"]
    assert result["errors"] == []
    assert result["returncode"] == 0
    assert (workdir / "model_syntaxcheck.log").read_text(encoding="utf-8") == (
        "Abaqus syntaxcheck complete\n"
    )


def test_syntaxcheck_reports_dat_errors_even_with_zero_returncode(tmp_path, monkeypatch):
    inp_path = tmp_path / "bad.inp"
    inp_path.write_text("*Heading\n", encoding="utf-8")

    def fake_run(cmd, cwd, capture_output, text, timeout):
        workdir = tmp_path / "work"
        (workdir / "bad_syntaxcheck.dat").write_text(
            "***ERROR: UNKNOWN KEYWORD\n",
            encoding="utf-8",
        )
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(syntaxcheck_module.subprocess, "run", fake_run)

    result = syntaxcheck_module.syntaxcheck_inp(inp_path, tmp_path / "work")

    assert result["ok"] is False
    assert result["warnings"] == []
    assert result["errors"] == ["***ERROR: UNKNOWN KEYWORD"]
    assert result["returncode"] == 0


def test_syntaxcheck_missing_abaqus_raises_structured_error(tmp_path, monkeypatch):
    inp_path = tmp_path / "model.inp"
    inp_path.write_text("*Heading\n", encoding="utf-8")

    def fake_run(cmd, cwd, capture_output, text, timeout):
        raise FileNotFoundError("abaqus")

    monkeypatch.setattr(syntaxcheck_module.subprocess, "run", fake_run)

    with pytest.raises(AbaqusAgentError) as exc_info:
        syntaxcheck_module.syntaxcheck_inp(inp_path, tmp_path / "work")

    assert exc_info.value.code == ErrorCode.ABAQUS_NOT_FOUND
    assert "'abaqus' not found in PATH" in str(exc_info.value)
