import importlib
import json
from types import SimpleNamespace

import pytest

from tools.errors import AbaqusAgentError, ErrorCode

submit_job_module = importlib.import_module("runner.submit_job")


def test_submit_job_interactive_passes_license_env_writes_log_and_meta(tmp_path, monkeypatch):
    inp_path = tmp_path / "model.inp"
    inp_path.write_text("*Heading\n", encoding="utf-8")
    workdir = tmp_path / "work"
    calls = []

    def fake_run(cmd, cwd, capture_output, text, timeout, env):
        calls.append(
            {
                "cmd": cmd,
                "cwd": cwd,
                "capture_output": capture_output,
                "text": text,
                "timeout": timeout,
                "env": env,
            }
        )
        return SimpleNamespace(returncode=0, stdout="JOB COMPLETED", stderr="")

    monkeypatch.setattr(submit_job_module.subprocess, "run", fake_run)

    result = submit_job_module.submit_job(
        inp_path,
        workdir=workdir,
        cpus=4,
        mp_mode="mpi",
        memory="8192 mb",
        interactive=True,
        background=False,
        timeout_seconds=99,
    )

    expected_cmd = [
        "abaqus",
        "job=model",
        f"input={inp_path.resolve()}",
        "cpus=4",
        "mp_mode=mpi",
        "memory=8192 mb",
        "interactive",
    ]
    assert calls[0]["cmd"] == expected_cmd
    assert calls[0]["cwd"] == str(workdir)
    assert calls[0]["timeout"] == 99
    assert calls[0]["env"]["lmhanglimit"] == "1"
    assert result["status"] == "completed"
    assert result["job_name"] == "model"
    assert result["cmd"] == " ".join(expected_cmd)
    assert (workdir / "model.log").read_text(encoding="utf-8") == "JOB COMPLETED\n"
    meta = json.loads((workdir / "model_meta.json").read_text(encoding="utf-8"))
    assert meta["cmd"] == " ".join(expected_cmd)
    assert meta["cpus"] == "4"
    assert meta["mp_mode"] == "mpi"


def test_submit_job_interactive_failure_classifies_license_error(tmp_path, monkeypatch):
    inp_path = tmp_path / "model.inp"
    inp_path.write_text("*Heading\n", encoding="utf-8")

    def fake_run(cmd, cwd, capture_output, text, timeout, env):
        return SimpleNamespace(returncode=1, stdout="license checkout failed", stderr="")

    monkeypatch.setattr(submit_job_module.subprocess, "run", fake_run)

    with pytest.raises(AbaqusAgentError) as exc_info:
        submit_job_module.submit_job(
            inp_path,
            workdir=tmp_path / "work",
            interactive=True,
            background=False,
        )

    assert exc_info.value.code == ErrorCode.LICENSE_UNAVAILABLE
    assert "Job model failed" in str(exc_info.value)


def test_submit_job_background_uses_popen_and_respects_license_queue(tmp_path, monkeypatch):
    inp_path = tmp_path / "model.inp"
    inp_path.write_text("*Heading\n", encoding="utf-8")
    workdir = tmp_path / "work"
    calls = []

    def fake_popen(cmd, cwd, stdout, stderr, env):
        calls.append({"cmd": cmd, "cwd": cwd, "stdout_name": stdout.name, "stderr": stderr, "env": env})
        stdout.close()
        return SimpleNamespace(pid=1234)

    monkeypatch.setattr(submit_job_module.subprocess, "Popen", fake_popen)

    result = submit_job_module.submit_job(
        inp_path,
        workdir=workdir,
        background=True,
        interactive=False,
        allow_license_queue=True,
    )

    assert calls == [
        {
            "cmd": [
                "abaqus",
                "job=model",
                f"input={inp_path.resolve()}",
                "cpus=1",
                "mp_mode=threads",
                "memory=90%",
                "background",
            ],
            "cwd": str(workdir),
            "stdout_name": str(workdir / "model.log"),
            "stderr": submit_job_module.subprocess.STDOUT,
            "env": None,
        }
    ]
    assert result["status"] == "submitted"
    assert result["job_name"] == "model"


def test_submit_job_missing_abaqus_raises_structured_error(tmp_path, monkeypatch):
    inp_path = tmp_path / "model.inp"
    inp_path.write_text("*Heading\n", encoding="utf-8")

    def fake_run(cmd, cwd, capture_output, text, timeout, env):
        raise FileNotFoundError("abaqus")

    monkeypatch.setattr(submit_job_module.subprocess, "run", fake_run)

    with pytest.raises(AbaqusAgentError) as exc_info:
        submit_job_module.submit_job(
            inp_path,
            workdir=tmp_path / "work",
            interactive=True,
            background=False,
        )

    assert exc_info.value.code == ErrorCode.ABAQUS_NOT_FOUND
    assert "'abaqus' not found in PATH" in str(exc_info.value)
