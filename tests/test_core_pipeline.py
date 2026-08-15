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

    def test_the_id_the_api_reports_is_the_directory_the_run_writes(self):
        """POST /api/run/start and MCP start_run hand back make_run_id(); the
        run directory is named by runner/build_model._run_id(). They were two
        different hashes of two different things -- raw YAML text against the
        parsed spec -- so on the shipped cantilever the API said
        `64f474736b4b2019` while the evidence sat in `dd6ec1145b8de62f`.
        Anyone who copied the id off the workbench found nothing.
        """
        import yaml

        from core.helpers import CASES_DIR, make_run_id
        from runner.build_model import _run_id

        text = (CASES_DIR / "cantilever" / "spec.yaml").read_text(encoding="utf-8")

        assert make_run_id(text) == _run_id(yaml.safe_load(text))

    def test_two_spellings_of_one_model_are_one_run(self):
        """Follows from hashing the parsed spec: comments, key order and
        quoting are not part of what a model is."""
        from core.helpers import make_run_id

        assert make_run_id("a: 1\nb: 2\n") == make_run_id("# note\nb: 2\na: 1\n")
        assert make_run_id("a: 1\n") != make_run_id("a: 2\n")

    def test_an_unparseable_spec_still_gets_an_id(self):
        """The spec validator reports syntax errors. This must not raise on
        the way there."""
        from core.helpers import make_run_id

        assert len(make_run_id("a: [1, 2")) == 16

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
        from core.pipeline import STAGES
        assert len(STAGES) == 7
        assert all(len(s) == 4 for s in STAGES)

    def test_no_kpi_fabrication_helpers_left(self):
        """The KPI fabrication helpers must stay gone."""
        import core.pipeline as pipeline_mod
        assert not hasattr(pipeline_mod, "mock_kpis")
        assert not hasattr(pipeline_mod, "compare_kpis")
        source = Path(pipeline_mod.__file__).with_suffix(".py").read_text(encoding="utf-8")
        assert "random.uniform" not in source
        assert "1234.5" not in source

    def test_the_walkthrough_mode_is_gone(self):
        """No Abaqus is an answer, not a thing to simulate around.

        The walkthrough produced no numbers — that part was honest — but it
        still narrated seven stages and finished COMPLETED, so a screenshot of
        a machine that cannot solve anything was indistinguishable at a glance
        from one that had. Removed 2026-08-15 along with the CalculiX
        fallback; this pins the helpers so they cannot return quietly.
        """
        import core.pipeline as pipeline_mod

        for gone in ("run_demo_flow", "simulate_stage", "STAGE_LOGS",
                     "DEMO_PREFIX", "DEMO_KPI_NOTICE"):
            assert not hasattr(pipeline_mod, gone), gone

        source = Path(pipeline_mod.__file__).with_suffix(".py").read_text(encoding="utf-8")
        assert "DEMO MODE" not in source

    def test_a_machine_without_abaqus_is_refused_not_walked_through(self):
        """The whole user-facing consequence, asserted end to end."""
        import yaml

        from core import pipeline as pipeline_mod
        from core.pipeline import run_pipeline

        spec_path = Path(__file__).parent.parent / "cases" / "cantilever" / "spec.yaml"
        spec = yaml.safe_load(spec_path.read_text(encoding="utf-8"))

        runs = {"r1": {"run_id": "r1", "spec": spec, "stages": {},
                       "started_at": 0.0}}
        original = pipeline_mod.check_abaqus
        pipeline_mod.check_abaqus = lambda *a, **k: False
        try:
            asyncio.get_event_loop().run_until_complete(run_pipeline("r1", runs))
        finally:
            pipeline_mod.check_abaqus = original

        run = runs["r1"]
        assert run["status"] == "FAILED", "a refusal must not read as a run"
        assert run.get("kpis", {}) == {}
        assert not run.get("demo_mode")
        # The refusal has to carry the way out, or it is a dead end.
        assert "ABAQUS_AGENT_ABAQUS_CMD" in run["kpi_notice"]
        # And it must not have narrated stages it did not perform.
        assert set(run["stages"]) == {"validate_spec"}, run["stages"]

    def test_the_refusal_reaches_the_screen_through_the_callback(self):
        """The workbench only ever learns what the callback tells it.

        A refusal that updated `runs` but never fired would leave the browser
        on "running" forever, which is worse than the walkthrough it replaced.
        """
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

        events = []

        async def on_update(stage_id, snapshot):
            events.append((stage_id, snapshot["status"]))

        asyncio.get_event_loop().run_until_complete(
            run_pipeline(run_id, runs, on_stage_update=on_update)
        )

        assert runs[run_id]["status"] == "FAILED"
        assert runs[run_id]["kpis"] == {}
        assert not runs[run_id].get("demo_mode")
        assert events, "the browser was never told anything"
        assert events[-1][0] == "done"

    def test_run_pipeline_no_callback(self):
        """Same path with no listener: it must return, not raise."""
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

        assert runs[run_id]["status"] == "FAILED"


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


# ── where a spec that arrived as text gets built ────────────────────────────

def test_an_adhoc_spec_builds_in_a_directory_named_by_its_run_id(monkeypatch, tmp_path):
    r"""POST /api/run/start and the workbench send the spec as YAML text, so
    the orchestrator has no spec file and picks the working directory itself.
    It used to be `mkdtemp(prefix="abaqus_run_")` -- measured through the real
    HTTP path, `...\Temp\abaqus_run_mbmomka_`: unrelated to the run id the
    same request returned, so the evidence could not be found from it, and
    different on every request, so the same spec re-solved every time.
    """
    from agent.orchestrator import AbaqusOrchestrator
    from core import config
    from core.helpers import run_id_for_spec

    spec = {"meta": {"model_name": "Beam", "units": "mm_MPa_t"},
            "geometry": {"type": "cantilever_block", "L": 100.0}}
    monkeypatch.setenv(config.ENV_RUN_ROOT, str(tmp_path))

    orch = AbaqusOrchestrator(spec_dict=spec)
    workdir = orch._adhoc_workdir()

    assert run_id_for_spec(spec) in workdir.name
    assert workdir.parent == tmp_path, "ABAQUS_AGENT_RUN_ROOT was ignored here"


def test_the_same_adhoc_spec_gets_the_same_directory_twice(tmp_path, monkeypatch):
    """Which is what lets the build cache hit at all on this path."""
    from agent.orchestrator import AbaqusOrchestrator
    from core import config

    spec = {"meta": {"model_name": "Beam"}, "geometry": {"type": "cantilever_block"}}
    monkeypatch.setenv(config.ENV_RUN_ROOT, str(tmp_path))

    first = AbaqusOrchestrator(spec_dict=spec)._adhoc_workdir()
    second = AbaqusOrchestrator(spec_dict=spec)._adhoc_workdir()

    assert first == second
