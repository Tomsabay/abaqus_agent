"""Tests for capsule persistence in the orchestrator."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.orchestrator import AbaqusOrchestrator
from tools.errors import AbaqusAgentError, ErrorCode

REPO_ROOT = Path(__file__).parent.parent


def _write_spec(tmp_path: Path) -> Path:
    spec = {
        "meta": {"abaqus_release": "2024", "model_name": "CapsuleModel"},
        "geometry": {"type": "custom_inp", "inp_path": "model.inp"},
        "material": {"name": "Steel", "E": 210000, "nu": 0.3},
        "analysis": {"solver": "standard", "step_type": "Static"},
        "bc_load": {},
        "outputs": {"kpis": [{"name": "U_tip", "type": "nodal_displacement"}]},
    }
    spec_path = tmp_path / "spec.yaml"
    spec_path.write_text(yaml.safe_dump(spec), encoding="utf-8")
    (tmp_path / "model.inp").write_text("*Heading\nmodel\n", encoding="utf-8")
    return spec_path


def test_orchestrator_writes_capsule_on_success(tmp_path):
    workdir = tmp_path / "run"
    spec_path = _write_spec(tmp_path)
    orch = AbaqusOrchestrator(spec_path=spec_path, workdir=workdir)

    def fake_build():
        workdir.mkdir(parents=True, exist_ok=True)
        inp = workdir / "CapsuleModel.inp"
        inp.write_text("*Heading\nmodel\n", encoding="utf-8")
        orch.workdir = workdir
        orch._build_result = {"workdir": workdir, "inp_path": inp, "run_id": "abc123"}
        orch.result["stages"]["build_model"] = {"inp_path": str(inp)}
        return orch._build_result

    orch._stage_build = fake_build
    orch._stage_syntaxcheck = lambda _inp, _workdir: orch.result["stages"].update({"syntaxcheck": {"ok": True}})
    orch._stage_submit = lambda _inp, _workdir: {"job_name": "CapsuleModel", "workdir": str(workdir), "status": "completed"}
    orch._stage_monitor = lambda _submit: orch.result["stages"].update({"monitor_job": {"status": "COMPLETED"}})
    orch._stage_extract = lambda _odb: {"kpis": {"U_tip": -0.002}, "errors": []}

    result = orch.run()

    capsule = json.loads((workdir / "capsule.json").read_text(encoding="utf-8"))
    assert result["status"] == "COMPLETED"
    assert result["capsule_path"] == str(workdir / "capsule.json")
    assert capsule["run_id"] == "abc123"
    assert "CapsuleModel.inp" in capsule["artifacts"]


def test_orchestrator_writes_capsule_and_diagnosis_on_failure(tmp_path):
    workdir = tmp_path / "run"
    spec_path = _write_spec(tmp_path)
    orch = AbaqusOrchestrator(spec_path=spec_path, workdir=workdir)

    def fake_build():
        workdir.mkdir(parents=True, exist_ok=True)
        inp = workdir / "CapsuleModel.inp"
        inp.write_text("*Heading\nmodel\n", encoding="utf-8")
        (workdir / "CapsuleModel.msg").write_text(
            "Too many attempts made for this increment\n",
            encoding="utf-8",
        )
        orch.workdir = workdir
        orch._build_result = {"workdir": workdir, "inp_path": inp, "run_id": "failed123"}
        return orch._build_result

    def fail_submit(_inp, _workdir):
        raise AbaqusAgentError(ErrorCode.NONCONVERGENCE, "did not converge", workdir=str(workdir))

    orch._stage_build = fake_build
    orch._stage_syntaxcheck = lambda _inp, _workdir: None
    orch._stage_submit = fail_submit

    result = orch.run()

    capsule = json.loads((workdir / "capsule.json").read_text(encoding="utf-8"))
    assert result["status"] == "FAILED"
    assert capsule["provenance"]["status"] == "FAILED"
    assert capsule["diagnosis"]["matched"] is True
    assert capsule["diagnosis"]["matches"][0]["id"] == "too_many_attempts"


def test_orchestrator_script_entrypoint_imports_top_level_packages():
    proc = subprocess.run(
        [sys.executable, "agent/orchestrator.py"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert proc.returncode == 1
    assert "Usage: python agent/orchestrator.py" in proc.stdout
    assert "ModuleNotFoundError" not in proc.stderr
