"""
Tests for core/ shared business logic modules.
"""
import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


# ── core.helpers ──────────────────────────────────────────────────

class TestHelpers:
    def test_check_abaqus_returns_bool(self):
        from core.helpers import check_abaqus
        result = check_abaqus()
        assert isinstance(result, bool)

    def test_list_cases_returns_list(self):
        from core.helpers import list_cases
        result = list_cases()
        assert isinstance(result, list)
        assert "cantilever" in result

    def test_make_run_id_deterministic(self):
        from core.helpers import make_run_id
        id1 = make_run_id("test spec yaml")
        id2 = make_run_id("test spec yaml")
        assert id1 == id2
        assert len(id1) == 16

    def test_make_run_id_different_input(self):
        from core.helpers import make_run_id
        id1 = make_run_id("spec A")
        id2 = make_run_id("spec B")
        assert id1 != id2

    def test_cases_dir_exists(self):
        from core.helpers import CASES_DIR
        assert CASES_DIR.exists()
        assert CASES_DIR.is_dir()

    def test_get_abaqus_cmd_returns_string(self):
        from tools.abaqus_cmd import get_abaqus_cmd
        result = get_abaqus_cmd()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_get_abaqus_cmd_consistent_with_check(self):
        """get_abaqus_cmd should return a resolved path when abaqus is found."""
        from core.helpers import check_abaqus
        from tools.abaqus_cmd import get_abaqus_cmd
        cmd = get_abaqus_cmd()
        if check_abaqus():
            # When abaqus is installed, should return a resolved path (not bare "abaqus")
            assert cmd != "abaqus"
        else:
            # When not installed, falls back to "abaqus"
            assert cmd == "abaqus"


# ── core.pipeline ─────────────────────────────────────────────────

class TestPipeline:
    def test_stages_defined(self):
        from core.pipeline import STAGE_LOGS, STAGES
        assert len(STAGES) == 6
        assert all(len(s) == 4 for s in STAGES)
        assert len(STAGE_LOGS) == 6

    def test_simulate_stage(self):
        from core.pipeline import simulate_stage
        result = simulate_stage("validate_spec", "Model", "2024", "standard", "abc12345")
        assert result["status"] == "done"
        assert isinstance(result["logs"], list)
        assert len(result["logs"]) > 0
        assert "elapsed_ms" in result

    def test_simulate_stage_unknown(self):
        from core.pipeline import simulate_stage
        result = simulate_stage("unknown_stage", "M", "2024", "standard", "x")
        assert result["status"] == "done"

    def test_mock_kpis_displacement(self):
        from core.pipeline import mock_kpis
        spec = {"outputs": {"kpis": [
            {"name": "U_tip", "type": "nodal_displacement", "location": "tip"},
        ]}}
        kpis = mock_kpis(spec)
        assert "U_tip" in kpis
        assert "value" in kpis["U_tip"]
        assert kpis["U_tip"]["unit"] == "mm"

    def test_mock_kpis_eigenfrequency(self):
        from core.pipeline import mock_kpis
        spec = {"outputs": {"kpis": [
            {"name": "freq_1", "type": "eigenfrequency", "location": "mode_1"},
        ]}}
        kpis = mock_kpis(spec)
        assert "freq_1" in kpis
        assert kpis["freq_1"]["unit"] == "Hz"

    def test_mock_kpis_empty(self):
        from core.pipeline import mock_kpis
        kpis = mock_kpis({})
        assert kpis == {}

    def test_compare_kpis(self):
        from core.pipeline import compare_kpis
        actual = {"U_tip": {"value": -0.002, "unit": "mm"}}
        result = compare_kpis(actual, "test_run")
        assert result["passed"] is True
        assert "U_tip" in result["comparisons"]

    def test_run_pipeline_async(self):
        import yaml

        from core.pipeline import run_pipeline

        spec_path = Path(__file__).parent.parent / "cases" / "cantilever" / "spec.yaml"
        spec = yaml.safe_load(spec_path.read_text())

        runs = {}
        run_id = "test_001"
        runs[run_id] = {
            "run_id": run_id,
            "status": "PENDING",
            "spec": spec,
            "runner_cfg": {},
            "stages": {},
            "kpis": {},
            "started_at": time.time(),
            "finished_at": None,
            "progress_pct": 0,
        }

        # Collect callback events
        events = []

        async def on_update(stage_id, snapshot):
            events.append((stage_id, snapshot["status"]))

        asyncio.get_event_loop().run_until_complete(
            run_pipeline(run_id, runs, on_stage_update=on_update)
        )

        assert runs[run_id]["status"] == "COMPLETED"
        assert runs[run_id]["progress_pct"] == 100
        assert len(runs[run_id]["stages"]) == 6
        assert len(events) > 0
        # Last event should be "done"
        assert events[-1][0] == "done"

    def test_run_pipeline_no_callback(self):
        import yaml

        from core.pipeline import run_pipeline

        spec_path = Path(__file__).parent.parent / "cases" / "cantilever" / "spec.yaml"
        spec = yaml.safe_load(spec_path.read_text())

        runs = {}
        run_id = "test_002"
        runs[run_id] = {
            "run_id": run_id,
            "status": "PENDING",
            "spec": spec,
            "runner_cfg": {},
            "stages": {},
            "kpis": {},
            "started_at": time.time(),
            "finished_at": None,
            "progress_pct": 0,
        }

        asyncio.get_event_loop().run_until_complete(
            run_pipeline(run_id, runs)
        )

        assert runs[run_id]["status"] == "COMPLETED"


# ── core.spec_generator ──────────────────────────────────────────

class TestSpecGenerator:
    def test_generate_template_spec(self):
        from core.spec_generator import generate_spec_async
        spec, missing = asyncio.get_event_loop().run_until_complete(
            generate_spec_async("简单悬臂梁分析", "2024", "template")
        )
        assert "meta" in spec
        assert "geometry" in spec
        assert "material" in spec
        assert spec["meta"]["abaqus_release"] == "2024"

    def test_generate_spec_with_hole(self):
        from core.spec_generator import generate_spec_async
        spec, _ = asyncio.get_event_loop().run_until_complete(
            generate_spec_async("带孔板分析 plate with hole", "2024", "template")
        )
        assert spec["geometry"]["type"] == "plate_with_hole"

    def test_generate_spec_modal(self):
        from core.spec_generator import generate_spec_async
        spec, _ = asyncio.get_event_loop().run_until_complete(
            generate_spec_async("模态频率分析", "2024", "template")
        )
        assert spec["analysis"]["step_type"] == "Frequency"

    def test_generate_spec_explicit(self):
        from core.spec_generator import generate_spec_async
        spec, _ = asyncio.get_event_loop().run_until_complete(
            generate_spec_async("显式冲击分析 explicit", "2024", "template")
        )
        assert spec["analysis"]["step_type"] == "Dynamic_Explicit"
        assert spec["analysis"]["solver"] == "explicit"
