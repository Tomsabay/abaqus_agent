from __future__ import annotations

import importlib
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

extract_module = importlib.import_module("post.extract_kpis")


def test_extract_kpis_invokes_abaqus_python_and_reads_result(tmp_path, monkeypatch):
    odb_path = tmp_path / "model.odb"
    odb_path.write_text("fake odb placeholder", encoding="utf-8")
    workdir = tmp_path / "work"
    workdir.mkdir()
    kpi_spec = [{"name": "U_tip", "type": "nodal_displacement", "component": "U2"}]
    calls: list[dict] = []

    def fake_run(cmd, cwd, capture_output, text, timeout, **kwargs):
        calls.append(
            {
                "cmd": cmd,
                "cwd": cwd,
                "capture_output": capture_output,
                "text": text,
                "timeout": timeout,
            }
        )
        Path(cmd[-1]).write_text(
            json.dumps(
                {
                    "kpis": {"U_tip": -0.0025},
                    "errors": [],
                    "odb_path": str(odb_path.resolve()),
                }
            ),
            encoding="utf-8",
        )
        return SimpleNamespace(returncode=0, stdout="KPI_RESULT_WRITTEN", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = extract_module.extract_kpis(odb_path, kpi_spec, workdir=workdir)

    assert result == {
        "kpis": {"U_tip": -0.0025},
        "errors": [],
        "odb_path": str(odb_path.resolve()),
    }
    assert calls == [
        {
            "cmd": [
                "abaqus",
                "python",
                str(Path(extract_module.__file__).resolve()),
                "--",
                str(odb_path.resolve()),
                str(workdir / "_kpi_spec.json"),
                str(workdir / "_kpi_result.json"),
            ],
            "cwd": str(workdir),
            "capture_output": True,
            "text": True,
            "timeout": 300,
        }
    ]
    assert json.loads((workdir / "_kpi_spec.json").read_text(encoding="utf-8")) == kpi_spec


def test_extract_kpis_returns_missing_abaqus_error(tmp_path, monkeypatch):
    odb_path = tmp_path / "model.odb"
    workdir = tmp_path / "work"
    workdir.mkdir()

    def fake_run(*args, **kwargs):
        raise FileNotFoundError("abaqus")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = extract_module.extract_kpis(odb_path, [], workdir=workdir)

    assert result == {
        "kpis": {},
        "errors": ["'abaqus' not found in PATH"],
        "odb_path": str(odb_path.resolve()),
    }


def test_extract_kpis_returns_timeout_error(tmp_path, monkeypatch):
    odb_path = tmp_path / "model.odb"
    workdir = tmp_path / "work"
    workdir.mkdir()

    def fake_run(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd=cmd, timeout=kwargs["timeout"])

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = extract_module.extract_kpis(odb_path, [], workdir=workdir)

    assert result == {
        "kpis": {},
        "errors": ["KPI extraction timed out after 300s"],
        "odb_path": str(odb_path.resolve()),
    }


def test_extract_kpis_uses_stderr_when_result_file_missing(tmp_path, monkeypatch):
    odb_path = tmp_path / "model.odb"
    workdir = tmp_path / "work"
    workdir.mkdir()

    def fake_run(*args, **kwargs):
        return SimpleNamespace(returncode=1, stdout="", stderr="ODB failed with details")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = extract_module.extract_kpis(odb_path, [], workdir=workdir)

    assert result == {
        "kpis": {},
        "errors": ["ODB failed with details"],
        "odb_path": str(odb_path.resolve()),
    }
