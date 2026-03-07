"""
Tests for the real Abaqus pipeline integration path in core/pipeline.py.

These tests mock the orchestrator and check_abaqus() to verify the real
pipeline code path works correctly without requiring actual Abaqus installation.
"""
import asyncio
import time
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

import yaml


def _make_run(run_id="test_real_001", spec=None):
    """Create a standard run dict for testing."""
    if spec is None:
        spec_path = Path(__file__).parent.parent / "cases" / "cantilever" / "spec.yaml"
        spec = yaml.safe_load(spec_path.read_text())
    return {
        "run_id": run_id,
        "status": "PENDING",
        "spec": spec,
        "runner_cfg": {"cpus": 2, "mp_mode": "threads"},
        "stages": {},
        "kpis": {},
        "started_at": time.time(),
        "finished_at": None,
        "progress_pct": 0,
    }


class TestRealPipelineDispatch:
    """Test that run_pipeline dispatches to real vs simulated correctly."""

    def test_dispatches_to_simulated_when_no_abaqus(self):
        from core.pipeline import run_pipeline

        runs = {}
        run_id = "dispatch_sim"
        runs[run_id] = _make_run(run_id)

        with patch("core.pipeline.check_abaqus", return_value=False):
            asyncio.get_event_loop().run_until_complete(
                run_pipeline(run_id, runs)
            )

        assert runs[run_id]["status"] == "COMPLETED"
        # Simulated path sets all 6 stages
        assert len(runs[run_id]["stages"]) == 6

    def test_dispatches_to_real_when_abaqus_available(self):
        from core.pipeline import run_pipeline

        runs = {}
        run_id = "dispatch_real"
        runs[run_id] = _make_run(run_id)

        mock_result = {
            "status": "COMPLETED",
            "kpis": {"U_tip": -0.002},
            "regression": {"passed": True},
        }

        mock_orch = MagicMock()
        mock_orch.run.return_value = mock_result

        with patch("core.pipeline.check_abaqus", return_value=True), \
             patch("agent.orchestrator.AbaqusOrchestrator", return_value=mock_orch):
            asyncio.get_event_loop().run_until_complete(
                run_pipeline(run_id, runs)
            )

        assert runs[run_id]["status"] == "COMPLETED"
        assert runs[run_id]["kpis"] == {"U_tip": -0.002}


class TestRealPipelineExecution:
    """Test the _run_pipeline_real function with mocked orchestrator."""

    def test_real_pipeline_completed(self):
        from core.pipeline import _run_pipeline_real

        runs = {}
        run_id = "real_ok"
        runs[run_id] = _make_run(run_id)

        mock_result = {
            "status": "COMPLETED",
            "kpis": {"max_mises": 290.5, "U_tip": -0.00195},
            "regression": {"passed": True, "comparisons": {}},
        }

        mock_orch = MagicMock()
        mock_orch.run.return_value = mock_result

        with patch("agent.orchestrator.AbaqusOrchestrator", return_value=mock_orch):
            asyncio.get_event_loop().run_until_complete(
                _run_pipeline_real(run_id, runs)
            )

        run = runs[run_id]
        assert run["status"] == "COMPLETED"
        assert run["progress_pct"] == 100
        assert run["kpis"] == mock_result["kpis"]
        assert run["regression"] == mock_result["regression"]
        assert run["finished_at"] is not None

    def test_real_pipeline_failed(self):
        from core.pipeline import _run_pipeline_real

        runs = {}
        run_id = "real_fail"
        runs[run_id] = _make_run(run_id)

        mock_result = {
            "status": "FAILED",
            "kpis": {},
            "regression": {},
            "error": {"error_code": "NONCONVERGENCE", "message": "Job did not converge"},
        }

        mock_orch = MagicMock()
        mock_orch.run.return_value = mock_result

        with patch("agent.orchestrator.AbaqusOrchestrator", return_value=mock_orch):
            asyncio.get_event_loop().run_until_complete(
                _run_pipeline_real(run_id, runs)
            )

        run = runs[run_id]
        assert run["status"] == "FAILED"
        assert run["finished_at"] is not None

    def test_real_pipeline_exception(self):
        from core.pipeline import _run_pipeline_real

        runs = {}
        run_id = "real_exc"
        runs[run_id] = _make_run(run_id)

        mock_orch = MagicMock()
        mock_orch.run.side_effect = RuntimeError("Abaqus crashed")

        with patch("agent.orchestrator.AbaqusOrchestrator", return_value=mock_orch):
            asyncio.get_event_loop().run_until_complete(
                _run_pipeline_real(run_id, runs)
            )

        run = runs[run_id]
        assert run["status"] == "FAILED"
        assert run["stages"]["submit_job"]["status"] == "error"
        assert "Abaqus crashed" in run["stages"]["submit_job"]["logs"][0]["text"]

    def test_real_pipeline_with_callback(self):
        from core.pipeline import _run_pipeline_real

        runs = {}
        run_id = "real_cb"
        runs[run_id] = _make_run(run_id)

        mock_result = {
            "status": "COMPLETED",
            "kpis": {},
            "regression": {},
        }

        mock_orch = MagicMock()
        mock_orch.run.return_value = mock_result

        events = []

        async def on_update(stage_id, snapshot):
            events.append(stage_id)

        with patch("agent.orchestrator.AbaqusOrchestrator", return_value=mock_orch):
            asyncio.get_event_loop().run_until_complete(
                _run_pipeline_real(run_id, runs, on_stage_update=on_update)
            )

        assert "start" in events
        assert "done" in events

    def test_real_pipeline_sets_initial_stages(self):
        """Verify all 6 stages are initialized before orchestrator runs."""
        from core.pipeline import _run_pipeline_real

        runs = {}
        run_id = "real_init"
        runs[run_id] = _make_run(run_id)

        captured_stages = {}

        def fake_orch_init(**kwargs):
            mock = MagicMock()
            def run():
                # At this point, stages should already be set to pending
                for sid, sdata in runs[run_id]["stages"].items():
                    captured_stages[sid] = sdata.copy()
                return {"status": "COMPLETED", "kpis": {}, "regression": {}}
            mock.run = run
            return mock

        with patch("agent.orchestrator.AbaqusOrchestrator", side_effect=fake_orch_init):
            asyncio.get_event_loop().run_until_complete(
                _run_pipeline_real(run_id, runs)
            )

        # All 6 stages should have been initialized
        assert len(captured_stages) == 6
        for stage_data in captured_stages.values():
            assert stage_data["status"] == "pending"

    def test_real_pipeline_passes_spec_and_runner_cfg(self):
        from core.pipeline import _run_pipeline_real

        runs = {}
        run_id = "real_cfg"
        spec = yaml.safe_load(
            (Path(__file__).parent.parent / "cases" / "cantilever" / "spec.yaml").read_text()
        )
        runs[run_id] = _make_run(run_id, spec)
        runs[run_id]["runner_cfg"] = {"cpus": 4, "memory": "8gb"}

        mock_orch = MagicMock()
        mock_orch.run.return_value = {"status": "COMPLETED", "kpis": {}, "regression": {}}

        with patch("agent.orchestrator.AbaqusOrchestrator", return_value=mock_orch) as MockOrch:
            asyncio.get_event_loop().run_until_complete(
                _run_pipeline_real(run_id, runs)
            )

        # Verify orchestrator was called with correct args
        call_kwargs = MockOrch.call_args[1]
        assert call_kwargs["spec_dict"] == spec
        assert call_kwargs["runner_cfg"] == {"cpus": 4, "memory": "8gb"}
        assert call_kwargs["on_progress"] is not None


class TestProgressCallback:
    """Test the progress callback mapping from orchestrator to run state."""

    def test_progress_callback_validate(self):
        from core.pipeline import _run_pipeline_real

        runs = {}
        run_id = "prog_val"
        runs[run_id] = _make_run(run_id)

        progress_calls = []

        def capture_progress(stage, data):
            progress_calls.append((stage, data))

        mock_orch = MagicMock()

        def run_with_progress():
            # Simulate orchestrator calling on_progress
            cb = mock_orch.call_args_not_used  # won't work, use different approach
            return {"status": "COMPLETED", "kpis": {}, "regression": {}}

        mock_orch.run.return_value = {"status": "COMPLETED", "kpis": {}, "regression": {}}

        with patch("agent.orchestrator.AbaqusOrchestrator", return_value=mock_orch) as MockOrch:
            asyncio.get_event_loop().run_until_complete(
                _run_pipeline_real(run_id, runs)
            )

        # Verify orchestrator constructor received on_progress callback
        assert MockOrch.call_args[1]["on_progress"] is not None

    def test_progress_callback_updates_stages(self):
        """Simulate orchestrator calling on_progress and verify run state updates."""
        from core.pipeline import _run_pipeline_real

        runs = {}
        run_id = "prog_up"
        runs[run_id] = _make_run(run_id)

        captured_callback = {}

        def fake_orch_init(**kwargs):
            captured_callback["fn"] = kwargs.get("on_progress")
            mock = MagicMock()

            def run():
                cb = captured_callback["fn"]
                # Simulate progress calls from orchestrator
                cb("validate_spec", {"ok": True})
                cb("build_model", {"inp": "/tmp/model.inp"})
                cb("syntaxcheck", {"ok": True, "warnings": 2})
                cb("submit_job", {"status": "completed"})
                cb("monitor_job", {"status": "COMPLETED"})
                cb("extract_kpis", {"kpis": {"U_tip": -0.002}})
                return {"status": "COMPLETED", "kpis": {"U_tip": -0.002}, "regression": {}}

            mock.run = run
            return mock

        with patch("agent.orchestrator.AbaqusOrchestrator", side_effect=fake_orch_init):
            asyncio.get_event_loop().run_until_complete(
                _run_pipeline_real(run_id, runs)
            )

        run = runs[run_id]
        assert run["status"] == "COMPLETED"
        assert run["progress_pct"] == 100

        # Check that stages were populated with logs
        assert "validate_spec" in run["stages"]
        assert "build_model" in run["stages"]
        assert "extract_kpis" in run["stages"]

        # validate_spec should have "ok" log
        val_logs = run["stages"]["validate_spec"]["logs"]
        assert any("完成" in log["text"] for log in val_logs)

        # build_model should have inp log
        build_logs = run["stages"]["build_model"]["logs"]
        assert any("INP_WRITTEN" in log["text"] for log in build_logs)


class TestOrchestratorEnhancements:
    """Test the orchestrator enhancements for spec_dict and runner_cfg."""

    def test_orchestrator_accepts_spec_dict(self):
        from agent.orchestrator import AbaqusOrchestrator

        spec = {
            "meta": {"model_name": "test", "abaqus_release": "2024"},
            "geometry": {"type": "beam"},
            "material": {"name": "Steel", "E": 210000, "nu": 0.3},
            "analysis": {"solver": "standard", "step_type": "Static"},
            "outputs": {"kpis": []},
        }

        orch = AbaqusOrchestrator(spec_dict=spec)
        assert orch.spec == spec
        assert orch.spec_path is None

    def test_orchestrator_accepts_runner_cfg_dict(self):
        from agent.orchestrator import AbaqusOrchestrator

        spec = {"meta": {"model_name": "test", "abaqus_release": "2024"}}
        cfg = {"cpus": 8, "memory": "16gb"}

        orch = AbaqusOrchestrator(spec_dict=spec, runner_cfg=cfg)
        assert orch.runner_cfg["cpus"] == 8
        assert orch.runner_cfg["memory"] == "16gb"
        # Default values should still be present for unspecified keys
        assert orch.runner_cfg["mp_mode"] == "threads"

    def test_orchestrator_requires_spec(self):
        from agent.orchestrator import AbaqusOrchestrator

        with pytest.raises(ValueError, match="Either spec_path or spec_dict"):
            AbaqusOrchestrator()

    def test_orchestrator_spec_dict_priority(self):
        """When both spec_dict and spec_path given, spec_dict wins."""
        from agent.orchestrator import AbaqusOrchestrator

        spec = {"meta": {"model_name": "from_dict", "abaqus_release": "2024"}}

        orch = AbaqusOrchestrator(
            spec_dict=spec,
            spec_path="/nonexistent/path.yaml",  # should be ignored
        )
        assert orch.spec["meta"]["model_name"] == "from_dict"
        assert orch.spec_path is None


class TestRunSnapshot:
    """Test the _run_snapshot helper."""

    def test_snapshot_contains_required_fields(self):
        from core.pipeline import _run_snapshot

        run = {
            "run_id": "snap_001",
            "status": "RUNNING",
            "progress_pct": 50,
            "stages": {"validate_spec": {"status": "done"}},
            "kpis": {"U_tip": -0.002},
            "started_at": time.time() - 10,
        }

        snap = _run_snapshot(run)
        assert snap["run_id"] == "snap_001"
        assert snap["status"] == "RUNNING"
        assert snap["progress_pct"] == 50
        assert "validate_spec" in snap["stages"]
        assert snap["elapsed"] > 0

    def test_snapshot_handles_missing_fields(self):
        from core.pipeline import _run_snapshot

        run = {"run_id": "snap_002"}
        snap = _run_snapshot(run)
        assert snap["run_id"] == "snap_002"
        assert snap["progress_pct"] == 0
        assert snap["stages"] == {}
