"""Pipeline routing across backends, and what the UI channel carries.

Hermetic: the orchestrator is mocked, no solver runs. What is under test is
that the backend decision reaches run_pipeline, that CalculiX gets its own
stage wording, and that backend/limitation/provenance data survives into the
snapshot the SSE stream and /api/run/{id} already serve.
"""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.pipeline import CALCULIX_STAGE_DESCS, DEMO_KPI_NOTICE, _run_snapshot, run_pipeline


def _make_run(run_id: str) -> dict:
    return {
        "run_id": run_id,
        "status": "PENDING",
        "spec": {
            "meta": {"model_name": "Cantilever", "abaqus_release": "2021"},
            "geometry": {"type": "cantilever_block", "L": 100.0, "W": 10.0, "H": 10.0,
                         "seed_size": 5.0},
            "material": {"name": "Steel", "E": 210000.0, "nu": 0.3},
            "analysis": {"solver": "standard", "step_type": "Static"},
            "bc_load": {"load_type": "concentrated_force", "value": -1.0, "direction": 2},
            "outputs": {"kpis": [{"name": "U_tip", "type": "nodal_displacement",
                                  "location": "tip_center", "component": "U2"}]},
        },
        "runner_cfg": {},
        "stages": {}, "kpis": {},
        "started_at": time.time(), "finished_at": None, "progress_pct": 0,
    }


def _run(runs, run_id):
    asyncio.new_event_loop().run_until_complete(run_pipeline(run_id, runs))


def test_falls_back_to_calculix_when_abaqus_is_absent():
    runs = {"r": _make_run("r")}
    mock_orch = MagicMock()
    mock_orch.run.return_value = {
        "status": "COMPLETED",
        "kpis": {"U_tip": -0.001903958},
        "backend": {"backend": "calculix", "label": "CalculiX 2.23"},
        "kpi_provenance": {"U_tip": {"abaqus_equivalent": True}},
        "limitations": [{"feature": "outputs.kpis[MISES].type", "value": "field_max",
                         "reason": "定义不同", "kind": "caveat"}],
        "visuals_notice": "CalculiX 不产生 .odb",
    }
    with patch("core.pipeline.check_abaqus", return_value=False), \
         patch("core.backends.check_calculix", return_value=True), \
         patch("core.backends.detect_ccx_version", return_value="2.23"), \
         patch("agent.orchestrator.build_orchestrator", return_value=mock_orch):
        _run(runs, "r")

    run = runs["r"]
    assert run["status"] == "COMPLETED"
    assert run["backend"]["backend"] == "calculix"
    assert run["kpis"] == {"U_tip": -0.001903958}
    assert run["limitations"]
    assert run["visuals_notice"]


def test_demo_mode_when_neither_solver_is_present():
    runs = {"r": _make_run("r")}
    with patch("core.pipeline.check_abaqus", return_value=False), \
         patch("core.backends.check_calculix", return_value=False):
        _run(runs, "r")

    run = runs["r"]
    assert run["status"] == "COMPLETED"
    assert run["demo_mode"] is True
    assert run["kpis"] == {}
    assert run["backend"]["backend"] == "demo"
    assert "CalculiX" in DEMO_KPI_NOTICE


def test_abaqus_still_wins_and_keeps_its_own_stage_wording():
    runs = {"r": _make_run("r")}
    mock_orch = MagicMock()
    mock_orch.run.return_value = {"status": "COMPLETED", "kpis": {"U_tip": -0.002}}
    with patch("core.pipeline.check_abaqus", return_value=True), \
         patch("core.backends.check_calculix", return_value=True), \
         patch("core.backends.detect_abaqus_release", return_value="2021"), \
         patch("agent.orchestrator.build_orchestrator", return_value=mock_orch):
        _run(runs, "r")

    run = runs["r"]
    assert run["backend"]["backend"] == "abaqus"
    assert run["stages"]["submit_job"]["desc"] == "提交 Abaqus 作业"
    assert run["stages"]["extract_kpis"]["desc"] == "从 ODB 提取 KPI"


def test_calculix_stage_labels_never_mention_an_odb():
    """A run that made no .odb must not say it extracted KPIs from one."""
    assert "ODB" not in CALCULIX_STAGE_DESCS["extract_kpis"]
    assert "CalculiX" in CALCULIX_STAGE_DESCS["submit_job"]
    assert "跳过" in CALCULIX_STAGE_DESCS["syntaxcheck"]


def test_explicit_abaqus_override_when_absent_fails_loudly(monkeypatch):
    monkeypatch.setenv("ABAQUS_AGENT_SOLVER_BACKEND", "abaqus")
    runs = {"r": _make_run("r")}
    with patch("core.pipeline.check_abaqus", return_value=False), \
         patch("core.backends.check_calculix", return_value=True):
        _run(runs, "r")

    run = runs["r"]
    assert run["status"] == "FAILED", "must not slide into demo mode"
    assert run.get("demo_mode") is not True
    assert "ABAQUS_AGENT_ABAQUS_CMD" in run["kpi_notice"]


def test_snapshot_carries_backend_provenance_to_the_ui():
    run = _make_run("r")
    run.update({
        "backend": {"backend": "calculix", "label": "CalculiX 2.23"},
        "limitations": [{"feature": "x", "value": "y", "reason": "z", "kind": "caveat"}],
        "kpi_provenance": {"MISES_MAX": {"abaqus_equivalent": False}},
        "visuals_notice": "无云图",
    })
    snapshot = _run_snapshot(run)
    assert snapshot["backend"]["label"] == "CalculiX 2.23"
    assert snapshot["limitations"][0]["reason"] == "z"
    assert snapshot["kpi_provenance"]["MISES_MAX"]["abaqus_equivalent"] is False
    assert snapshot["visuals_notice"] == "无云图"


def test_snapshot_defaults_stay_empty_for_a_plain_abaqus_run():
    snapshot = _run_snapshot(_make_run("r"))
    assert snapshot["backend"] == {}
    assert snapshot["limitations"] == []
    assert snapshot["kpi_provenance"] == {}


def test_a_bogus_backend_setting_is_reported_not_ignored(monkeypatch):
    monkeypatch.setenv("ABAQUS_AGENT_SOLVER_BACKEND", "nastran")
    runs = {"r": _make_run("r")}
    with patch("core.pipeline.check_abaqus", return_value=True), \
         patch("core.backends.check_calculix", return_value=True):
        _run(runs, "r")

    run = runs["r"]
    assert run["status"] == "FAILED"
    assert run.get("demo_mode") is not True
    assert "auto" in run["kpi_notice"]
