"""Tests for capsule persistence in the orchestrator."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.orchestrator import AbaqusOrchestrator
from tools.errors import AbaqusAgentError, ErrorCode

REPO_ROOT = Path(__file__).parent.parent


@pytest.fixture(autouse=True)
def _simulate_abaqus_present(monkeypatch):
    """These tests unit-test the REAL pipeline flow with every solver stage
    mocked out. The G2 demo-mode guard in run() keys off check_abaqus(), so
    force it True here to take the real-flow branch. No real solver can
    launch: the solver stages are replaced inside the tests below, and any
    残留 subprocess still fails on the hidden PATH exactly as before."""
    import core.helpers
    monkeypatch.setattr(core.helpers, "check_abaqus", lambda: True)


def _write_spec(tmp_path: Path) -> Path:
    """A deck spec: hand over a finished .inp and say nothing about the model.

    This file is about what the capsule records, not about how the model got
    built, so the spec that says the least is the right one. It used to be
    written `geometry: {type: custom_inp}` — the same passthrough in the v1
    dialect, which dragged `analysis` and `bc_load` along as required siblings
    that nothing read.
    """
    spec = {
        "meta": {"abaqus_release": "2021", "model_name": "CapsuleModel"},
        "deck": {"file": "model.inp"},
        "material": {"name": "Steel", "E": 210000, "nu": 0.3},
        "analysis": {"solver": "standard"},
        "outputs": {"kpis": [{"name": "U_tip", "type": "nodal_displacement"}]},
    }
    spec_path = tmp_path / "spec.yaml"
    spec_path.write_text(yaml.safe_dump(spec), encoding="utf-8")
    (tmp_path / "model.inp").write_text("*Heading\nmodel\n", encoding="utf-8")
    return spec_path


def _write_stepped_spec(tmp_path: Path, step_call: str) -> Path:
    """A described model, for the two tests whose subject IS the step type.

    v1 stated the analysis kind in `analysis.step_type` ("Static" against
    "Dynamic_Explicit"); v2 states it by naming the Abaqus step method, and a
    `deck` spec cannot state it at all — the steps live inside the .inp and
    nothing in the spec reports what they are. So the animation pair keeps the
    dialect that can still express the distinction, and differs in exactly the
    one thing being tested: the step call.
    """
    spec = {
        "meta": {"abaqus_release": "2021", "model_name": "CapsuleModel",
                 "units": "mm_MPa_t"},
        "material": {"name": "Steel", "E": 210000.0, "nu": 0.3},
        "parts": [{
            "name": "Bar",
            "features": [
                {"op": "sketch", "id": "s", "plane": "XY",
                 "profile": {"rect": {"corner1": [0.0, 0.0],
                                      "corner2": [10.0, 10.0]}}},
                {"op": "extrude", "sketch": "s", "depth": 100.0},
            ],
            "section": {"type": "solid", "material": "Steel"},
            "mesh": {"seed": 5.0, "element": "C3D8I"},
        }],
        "assembly": {"instances": [
            {"name": "Bar-1", "part": "Bar", "translate": [0.0, 0.0, 0.0]}]},
        "steps": [{"call": step_call, "name": {"literal": "Step-1"},
                   "previous": {"literal": "Initial"}}],
        "conditions": [{
            "call": "EncastreBC", "name": {"literal": "Fixed"},
            "createStepName": {"literal": "Initial"},
            "region": {"set": "Bar-1:face@z=min", "name": "FIXED_END",
                       "expect": "=1"},
        }],
        "outputs": {"kpis": [{"name": "U_tip", "type": "field_min",
                              "component": "U2", "location": "whole_model"}]},
    }
    spec_path = tmp_path / "spec.yaml"
    spec_path.write_text(yaml.safe_dump(spec), encoding="utf-8")
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


def test_orchestrator_collects_exported_odb_images(tmp_path, monkeypatch):
    workdir = tmp_path / "run"
    spec_path = _write_spec(tmp_path)
    orch = AbaqusOrchestrator(spec_path=spec_path, workdir=workdir)

    def fake_build():
        workdir.mkdir(parents=True, exist_ok=True)
        inp = workdir / "CapsuleModel.inp"
        inp.write_text("*Heading\nmodel\n", encoding="utf-8")
        odb = workdir / "CapsuleModel.odb"
        odb.write_text("fake odb marker\n", encoding="utf-8")
        orch.workdir = workdir
        orch._build_result = {"workdir": workdir, "inp_path": inp, "run_id": "visual123"}
        return orch._build_result

    def fake_export(_odb_path, plot_spec, export_workdir):
        image = Path(export_workdir) / "u_magnitude.png"
        image.write_bytes(b"\x89PNG\r\n\x1a\n")
        return {
            "images": [{"name": "u_magnitude", "path": image.name, "bytes": image.stat().st_size}],
            "errors": [],
            "plot_spec": plot_spec,
        }

    monkeypatch.setattr("agent.orchestrator.export_odb_images", fake_export)
    orch._stage_build = fake_build
    orch._stage_syntaxcheck = lambda _inp, _workdir: None
    orch._stage_submit = lambda _inp, _workdir: {"job_name": "CapsuleModel", "workdir": str(workdir), "status": "completed"}
    orch._stage_monitor = lambda _submit: None
    orch._stage_extract = lambda _odb: {"kpis": {"U_tip": -0.002}, "errors": []}

    result = orch.run()

    capsule = json.loads((workdir / "capsule.json").read_text(encoding="utf-8"))
    assert result["status"] == "COMPLETED"
    assert result["visuals"][0]["path"] == "u_magnitude.png"
    assert "u_magnitude.png" in capsule["artifacts"]


def test_orchestrator_exports_animation_for_dynamic_step(tmp_path, monkeypatch):
    workdir = tmp_path / "run"
    spec_path = _write_stepped_spec(tmp_path, "ExplicitDynamicsStep")
    orch = AbaqusOrchestrator(spec_path=spec_path, workdir=workdir)

    def fake_build():
        workdir.mkdir(parents=True, exist_ok=True)
        inp = workdir / "CapsuleModel.inp"
        inp.write_text("*Heading\nmodel\n", encoding="utf-8")
        odb = workdir / "CapsuleModel.odb"
        odb.write_text("fake odb marker\n", encoding="utf-8")
        orch.workdir = workdir
        orch._build_result = {"workdir": workdir, "inp_path": inp, "run_id": "anim123"}
        return orch._build_result

    anim_calls = []

    def fake_anim(odb_path, anim_workdir):
        anim_calls.append(str(odb_path))
        return {"frames": 5, "video": "anim.mp4",
                "out_dir": str(Path(anim_workdir) / "anim"), "errors": []}

    monkeypatch.setattr("agent.orchestrator.export_odb_images",
                        lambda *_a, **_k: {"images": [], "errors": []})
    monkeypatch.setattr("agent.orchestrator.export_odb_mesh",
                        lambda *_a, **_k: {"mesh_file": None, "errors": []})
    monkeypatch.setattr("agent.orchestrator.export_odb_animation", fake_anim)
    orch._stage_build = fake_build
    orch._stage_syntaxcheck = lambda _inp, _workdir: None
    orch._stage_submit = lambda _inp, _workdir: {"job_name": "CapsuleModel", "workdir": str(workdir), "status": "completed"}
    orch._stage_monitor = lambda _submit: None
    orch._stage_extract = lambda _odb: {"kpis": {"U_tip": -0.002}, "errors": []}

    result = orch.run()

    assert result["status"] == "COMPLETED"
    assert anim_calls and anim_calls[0].endswith("CapsuleModel.odb")
    assert result["animation"] == {"frames": 5, "video": "anim.mp4"}
    assert result["stages"]["export_odb_animation"]["video"] == "anim.mp4"


def test_orchestrator_skips_animation_for_static_step(tmp_path, monkeypatch):
    workdir = tmp_path / "run"
    spec_path = _write_stepped_spec(tmp_path, "StaticStep")
    orch = AbaqusOrchestrator(spec_path=spec_path, workdir=workdir)

    def fake_build():
        workdir.mkdir(parents=True, exist_ok=True)
        inp = workdir / "CapsuleModel.inp"
        inp.write_text("*Heading\nmodel\n", encoding="utf-8")
        orch.workdir = workdir
        orch._build_result = {"workdir": workdir, "inp_path": inp, "run_id": "static123"}
        return orch._build_result

    anim_calls = []
    monkeypatch.setattr("agent.orchestrator.export_odb_animation",
                        lambda *a, **k: anim_calls.append(a))
    monkeypatch.setattr("agent.orchestrator.export_odb_images",
                        lambda *_a, **_k: {"images": [], "errors": []})
    monkeypatch.setattr("agent.orchestrator.export_odb_mesh",
                        lambda *_a, **_k: {"mesh_file": None, "errors": []})
    orch._stage_build = fake_build
    orch._stage_syntaxcheck = lambda _inp, _workdir: None
    orch._stage_submit = lambda _inp, _workdir: {"job_name": "CapsuleModel", "workdir": str(workdir), "status": "completed"}
    orch._stage_monitor = lambda _submit: None
    orch._stage_extract = lambda _odb: {"kpis": {"U_tip": -0.002}, "errors": []}

    result = orch.run()

    assert result["status"] == "COMPLETED"
    assert anim_calls == []
    assert "animation" not in result
    assert "export_odb_animation" not in result["stages"]


def test_orchestrator_evaluates_contracts_and_persists_capsule(tmp_path):
    workdir = tmp_path / "run"
    spec_path = _write_spec(tmp_path)
    contracts_path = tmp_path / "contracts.yaml"
    contracts_path.write_text(
        yaml.safe_dump({
            "contracts": [
                {
                    "name": "tip_down",
                    "check": "operator",
                    "kpi": "U_tip",
                    "operator": "<",
                    "value": 0.0,
                    "severity": "error",
                }
            ]
        }),
        encoding="utf-8",
    )
    orch = AbaqusOrchestrator(spec_path=spec_path, workdir=workdir, contracts_path=contracts_path)

    def fake_build():
        workdir.mkdir(parents=True, exist_ok=True)
        inp = workdir / "CapsuleModel.inp"
        inp.write_text("*Heading\nmodel\n", encoding="utf-8")
        orch.workdir = workdir
        orch._build_result = {"workdir": workdir, "inp_path": inp, "run_id": "contract123"}
        return orch._build_result

    def fake_extract(_odb):
        orch.result["kpis"] = {"U_tip": -0.002}
        return {"kpis": {"U_tip": -0.002}, "errors": []}

    orch._stage_build = fake_build
    orch._stage_syntaxcheck = lambda _inp, _workdir: None
    orch._stage_submit = lambda _inp, _workdir: {"job_name": "CapsuleModel", "workdir": str(workdir), "status": "completed"}
    orch._stage_monitor = lambda _submit: None
    orch._stage_extract = fake_extract
    orch._stage_export_visuals = lambda _odb: {"images": [], "errors": []}

    result = orch.run()

    capsule = json.loads((workdir / "capsule.json").read_text(encoding="utf-8"))
    assert result["contracts"]["passed"] is True
    assert result["contracts"]["results"][0]["name"] == "tip_down"
    assert capsule["contracts"]["passed"] is True


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
