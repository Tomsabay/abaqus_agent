"""CalculiX orchestrator and solve gate. Hermetic: ccx is never invoked.

The solver call is stubbed at subprocess.run so the post-run gate can be
exercised against the exact console text ccx 2.23 produces in each failure
mode — including the one where it exits 0 and is still wrong.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.ccx_orchestrator import CalculiXOrchestrator
from agent.orchestrator import AbaqusOrchestrator, build_orchestrator
from core.backends import BackendDecision, Limitation, select_backend
from runner import ccx_solve
from tools.errors import AbaqusAgentError


def _spec(**overrides) -> dict:
    spec = {
        "meta": {"model_name": "Cantilever", "abaqus_release": "2021"},
        "geometry": {"type": "cantilever_block", "L": 100.0, "W": 10.0, "H": 10.0,
                     "seed_size": 5.0},
        "material": {"name": "Steel", "E": 210000.0, "nu": 0.3},
        "analysis": {"solver": "standard", "step_type": "Static", "cpus": 1},
        "bc_load": {"fixed_face": "z=0", "load_face": "z=L",
                    "load_type": "concentrated_force", "value": -1.0, "direction": 2},
        "outputs": {"kpis": [{"name": "U_tip", "type": "nodal_displacement",
                              "location": "tip_center", "component": "U2"}]},
    }
    spec.update(overrides)
    return spec


def _decision(blockers=(), caveats=()) -> BackendDecision:
    return BackendDecision(
        backend="calculix", label="CalculiX 2.23",
        reason="未检测到 Abaqus，降级到 CalculiX", source="auto", version="2.23",
        blockers=tuple(blockers), caveats=tuple(caveats),
    )


# ── factory ─────────────────────────────────────────────────────────────────

def test_factory_returns_abaqus_orchestrator_by_default(tmp_path):
    orch = build_orchestrator(spec_dict=_spec(), workdir=tmp_path)
    assert type(orch) is AbaqusOrchestrator


def test_factory_returns_calculix_orchestrator_for_a_calculix_decision(tmp_path):
    orch = build_orchestrator(decision=_decision(), spec_dict=_spec(), workdir=tmp_path)
    assert isinstance(orch, CalculiXOrchestrator)


def test_abaqus_decision_still_gets_the_abaqus_orchestrator(tmp_path):
    decision = select_backend(_spec(), abaqus_available=True, calculix_available=True)
    orch = build_orchestrator(decision=decision, spec_dict=_spec(), workdir=tmp_path)
    assert type(orch) is AbaqusOrchestrator


# ── refusal ─────────────────────────────────────────────────────────────────

def test_refused_run_produces_no_kpis_and_says_why(tmp_path):
    blocker = Limitation("bc_load.load_type", "blast_conwep",
                         "CalculiX 不认识 CONWEP 爆炸载荷，会静默丢掉这张卡")
    orch = CalculiXOrchestrator(
        spec_dict=_spec(), workdir=tmp_path, decision=_decision(blockers=[blocker]))
    result = orch.run()

    assert result["status"] == "REFUSED"
    assert result["kpis"] == {}
    assert "CONWEP" in result["error"]["message"]
    assert result["error"]["refusals"]
    assert result["limitations"][0]["feature"] == "bc_load.load_type"
    assert "无法忠实求解" in result["kpi_notice"]


def test_refusal_is_archived_to_result_json(tmp_path):
    import json

    blocker = Limitation("analysis.step_type", "Dynamic_Explicit", "未验证")
    orch = CalculiXOrchestrator(
        spec_dict=_spec(), workdir=tmp_path, decision=_decision(blockers=[blocker]))
    orch.run()
    saved = json.loads((tmp_path / "result.json").read_text(encoding="utf-8"))
    assert saved["status"] == "REFUSED"
    assert saved["backend"]["backend"] == "calculix"


def test_a_refused_deck_ends_the_same_way_a_refused_spec_does(tmp_path, monkeypatch):
    """Two gates, one verdict.

    The capability matrix reads the spec and refuses in _preflight. The
    card-by-card whitelist reads the deck, which does not exist until the build
    stage, so its refusal travels as an exception — and the shared run loop
    calls every exception FAILED. That left the deck refusal with no
    kpi_notice saying why there are no numbers, reading to a caller as a crash.
    """
    import json

    from runner.ccx_whitelist import DeckRefused

    def _refuse(_deck_text):
        raise DeckRefused(["*FREQUENCY 是分析步类型卡：还没有跟 Abaqus 对过基准值"])

    monkeypatch.setattr("agent.ccx_orchestrator.assert_translatable", _refuse)
    monkeypatch.setattr(subprocess, "run", _boom_on_solver)
    orch = CalculiXOrchestrator(
        spec_dict=_spec(), workdir=tmp_path, decision=_decision())
    result = orch.run()

    assert result["status"] == "REFUSED"
    assert result["kpis"] == {}
    assert "*FREQUENCY" in result["error"]["message"]
    assert result["error"]["error_code"] == "BACKEND_UNSUPPORTED"
    assert "无法忠实求解" in result["kpi_notice"]
    saved = json.loads((tmp_path / "result.json").read_text(encoding="utf-8"))
    assert saved["status"] == "REFUSED"


_REAL_SUBPROCESS_RUN = subprocess.run


def _boom_on_solver(*args, **kwargs):
    """Any subprocess is treated as a solver launch, with one carve-out.

    On Linux the stdlib itself calls `uname -p` the first time
    platform.platform() renders (capsule/store.py records it), through
    subprocess.run — measured on public CI 2026-08-15, where this boom fired
    from inside functools' cached_property and failed a run that never went
    near a solver. Windows reads the registry instead, which is why the trap
    never fired locally. `uname` goes through; everything else still booms,
    so the trap stays fail-closed for the thing it guards.
    """
    argv = args[0] if args else kwargs.get("args")
    head = argv[0] if isinstance(argv, (list, tuple)) and argv else argv
    if Path(str(head)).name == "uname":
        return _REAL_SUBPROCESS_RUN(*args, **kwargs)
    raise AssertionError("a refused deck must not reach any solver")


def test_refusal_never_touches_the_solver(tmp_path, monkeypatch):
    monkeypatch.setattr(subprocess, "run", _boom_on_solver)
    orch = CalculiXOrchestrator(
        spec_dict=_spec(), workdir=tmp_path,
        decision=_decision(blockers=[Limitation("geometry.type", "cohesive_layer", "没有 cohesive 单元")]))
    assert orch.run()["status"] == "REFUSED"


# ── run directory namespacing ───────────────────────────────────────────────

def test_run_id_is_namespaced_so_it_cannot_overwrite_an_abaqus_baseline(tmp_path):
    """runner/build_model hashes the spec ALONE; sharing that dir would clobber
    cases/cantilever/runs/dd6ec1145b8de62f, the frozen Abaqus evidence."""
    from runner.build_model import _run_id as abaqus_run_id

    orch = CalculiXOrchestrator(spec_dict=_spec(), workdir=tmp_path, decision=_decision())
    ccx_id = orch._run_id()
    assert ccx_id.endswith("-ccx")
    assert ccx_id != abaqus_run_id(_spec())
    assert not ccx_id.startswith(abaqus_run_id(_spec()))


# ── capsule provenance ──────────────────────────────────────────────────────

def test_capsule_never_claims_an_abaqus_release_for_a_calculix_run(tmp_path, monkeypatch):
    monkeypatch.setattr("agent.ccx_orchestrator.detect_ccx_version", lambda *a, **k: "2.23")
    orch = CalculiXOrchestrator(spec_dict=_spec(), workdir=tmp_path, decision=_decision())
    meta = orch._capsule_metadata()
    assert meta["solver_backend"] == "calculix"
    assert meta["solver_release"] == "2.23"
    assert meta["abaqus_release"] is None


def test_abaqus_capsule_metadata_is_unchanged(tmp_path):
    orch = AbaqusOrchestrator(spec_dict=_spec(), workdir=tmp_path)
    meta = orch._capsule_metadata()
    assert meta["abaqus_release"] == "2021"
    assert meta["solver_backend"] == "abaqus"


# ── syntaxcheck honesty ─────────────────────────────────────────────────────

def test_syntaxcheck_is_reported_skipped_not_passed(tmp_path):
    orch = CalculiXOrchestrator(spec_dict=_spec(), workdir=tmp_path, decision=_decision())
    orch._stage_syntaxcheck(tmp_path / "x.inp", tmp_path)
    stage = orch.result["stages"]["syntaxcheck"]
    assert stage["status"] == "skipped"
    assert stage["ok"] is None, "a skipped pre-check must not read as ok"
    assert "没有 syntaxcheck" in stage["reason"]


def test_visual_export_explains_the_missing_contour_plots(tmp_path):
    orch = CalculiXOrchestrator(spec_dict=_spec(), workdir=tmp_path, decision=_decision())
    orch._stage_export_visuals(tmp_path / "x.odb")
    assert orch.result["visuals"] == []
    assert ".odb" in orch.result["visuals_notice"]


# ── regression grading policy ───────────────────────────────────────────────

def test_definition_mismatched_kpi_is_not_graded_against_an_abaqus_baseline(tmp_path):
    orch = CalculiXOrchestrator(spec_dict=_spec(), workdir=tmp_path, decision=_decision())
    orch.expected = {"kpis": {
        "U_tip": {"value": -0.0019039579201489687, "rtol": 0.1},
        "MISES_MAX": {"value": 0.6528551578521729, "rtol": 0.2},
    }}
    orch.result["kpi_provenance"] = {
        "U_tip": {"abaqus_equivalent": True},
        "MISES_MAX": {"abaqus_equivalent": False, "note": "定义不同"},
    }
    orch._stage_compare({"U_tip": -0.001903958, "MISES_MAX": 0.6108512433})

    comparisons = orch.result["regression"]["comparisons"]
    assert comparisons["U_tip"]["status"] == "PASS"
    assert comparisons["MISES_MAX"]["status"] == "NOT_COMPARABLE"
    assert orch.result["regression"]["not_comparable"] == ["MISES_MAX"]
    # An excluded KPI must not come back as MISSING and fail the whole run.
    assert orch.result["regression"]["passed"] is True


def test_an_excluded_kpi_does_not_flip_the_overall_verdict(tmp_path):
    events = []
    orch = CalculiXOrchestrator(
        spec_dict=_spec(), workdir=tmp_path, decision=_decision(),
        on_progress=lambda stage, data: events.append((stage, data)))
    orch.expected = {"kpis": {
        "U_tip": {"value": -0.0019039579201489687, "rtol": 0.1},
        "MISES_MAX": {"value": 0.6528551578521729, "rtol": 0.2},
    }}
    orch.result["kpi_provenance"] = {
        "U_tip": {"abaqus_equivalent": True},
        "MISES_MAX": {"abaqus_equivalent": False, "note": "定义不同"},
    }
    orch._stage_compare({"U_tip": -0.001903958, "MISES_MAX": 0.6108512433})

    compare_events = [d for s, d in events if s == "compare_kpis"]
    assert len(compare_events) == 1, "exactly one, non-contradictory verdict event"
    assert compare_events[0]["passed"] is True
    assert compare_events[0]["details"]["MISES_MAX"]["status"] == "NOT_COMPARABLE"
    # self.expected must be restored, not left narrowed.
    assert set(orch.expected["kpis"]) == {"U_tip", "MISES_MAX"}


def test_a_genuinely_wrong_comparable_kpi_still_fails(tmp_path):
    """Excluding stress must not become a blanket amnesty."""
    orch = CalculiXOrchestrator(spec_dict=_spec(), workdir=tmp_path, decision=_decision())
    orch.expected = {"kpis": {"U_tip": {"value": -0.0019039579201489687, "rtol": 0.01,
                                        "atol": 0.0}}}
    orch.result["kpi_provenance"] = {"U_tip": {"abaqus_equivalent": True}}
    orch._stage_compare({"U_tip": -0.009})
    assert orch.result["regression"]["passed"] is False
    assert orch.result["regression"]["comparisons"]["U_tip"]["status"] == "FAIL"


# ── the post-run gate ───────────────────────────────────────────────────────

class _FakeProc:
    def __init__(self, stdout: str, returncode: int = 0):
        self.stdout, self.returncode = stdout, returncode


def _stub_ccx(monkeypatch, tmp_path, stdout: str, returncode: int = 0,
              dat: str | None = "results", frd: str | None = " -4  DISP"):
    (tmp_path / "Job.inp").write_text("*HEADING\n", encoding="utf-8")
    if dat is not None:
        (tmp_path / "Job.dat").write_text(dat, encoding="utf-8")
    if frd is not None:
        (tmp_path / "Job.frd").write_text(frd, encoding="utf-8")
    monkeypatch.setattr(ccx_solve, "get_ccx_cmd", lambda: "ccx")
    monkeypatch.setattr(subprocess, "run",
                        lambda *a, **k: _FakeProc(stdout, returncode))


def test_successful_solve_returns_the_submit_job_shape(monkeypatch, tmp_path):
    _stub_ccx(monkeypatch, tmp_path, "Static analysis was selected\n Job finished\n")
    out = ccx_solve.solve_ccx(tmp_path / "Job.inp", tmp_path)
    assert out["status"] == "completed"
    assert out["job_name"] == "Job"
    assert out["solver"] == "calculix"
    assert (tmp_path / "ccx_console.txt").exists(), "console text is the evidence artefact"


def test_exit_zero_with_a_dropped_card_is_still_a_failure(monkeypatch, tmp_path):
    """THE case: ccx ignores CONWEP, exits 0, and reports zero displacement."""
    console = (
        " *WARNING in calinput. Card image cannot be interpreted:\n"
        "         *INCIDENTWAVEINTERACTIONPROPERTY,NAME=BLAST\n"
        " Job finished\n"
    )
    _stub_ccx(monkeypatch, tmp_path, console, returncode=0)
    with pytest.raises(AbaqusAgentError) as excinfo:
        ccx_solve.solve_ccx(tmp_path / "Job.inp", tmp_path)
    assert "忽略" in str(excinfo.value)


def test_no_analysis_selected_is_a_failure(monkeypatch, tmp_path):
    _stub_ccx(monkeypatch, tmp_path, " No analysis was selected\n", returncode=0)
    with pytest.raises(AbaqusAgentError, match="No analysis was selected"):
        ccx_solve.solve_ccx(tmp_path / "Job.inp", tmp_path)


def test_exit_zero_without_any_result_block_is_a_failure(monkeypatch, tmp_path):
    _stub_ccx(monkeypatch, tmp_path, " Job finished\n", returncode=0, dat="", frd="mesh only")
    with pytest.raises(AbaqusAgentError, match="没有写出任何结果块"):
        ccx_solve.solve_ccx(tmp_path / "Job.inp", tmp_path)


def test_nonzero_exit_is_classified(monkeypatch, tmp_path):
    _stub_ccx(monkeypatch, tmp_path, " *ERROR reading *BOUNDARY\n", returncode=201)
    with pytest.raises(AbaqusAgentError) as excinfo:
        ccx_solve.solve_ccx(tmp_path / "Job.inp", tmp_path)
    assert excinfo.value.code.value == "SYNTAX_ERROR"


def test_missing_ccx_is_a_clear_message(monkeypatch, tmp_path):
    monkeypatch.setattr(ccx_solve, "get_ccx_cmd", lambda: None)
    with pytest.raises(AbaqusAgentError, match="ABAQUS_AGENT_CCX_EXE"):
        ccx_solve.solve_ccx(tmp_path / "Job.inp", tmp_path)


def test_cpus_are_mapped_onto_omp_num_threads(monkeypatch, tmp_path):
    captured = {}

    def _capture(*args, **kwargs):
        captured.update(kwargs.get("env") or {})
        return _FakeProc(" Job finished\n", 0)

    _stub_ccx(monkeypatch, tmp_path, " Job finished\n")
    monkeypatch.setattr(subprocess, "run", _capture)
    ccx_solve.solve_ccx(tmp_path / "Job.inp", tmp_path, cpus=4)
    assert captured["OMP_NUM_THREADS"] == "4"
