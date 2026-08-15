"""The grading layer must actually run, and must not claim a check it skipped.

Measured 2026-08-09, before this file existed: `core.pipeline` built the
orchestrator with `decision / spec_dict / runner_cfg / on_progress` and nothing
else. `AbaqusOrchestrator` only compares KPIs `if self.expected`, so every run
started through that module -- workbench Accept, POST /api/run/start, MCP
start_run, and the benchmark loop -- finished with `regression: {}` and
`contracts: {}`. The whole 2532-test suite passed in that state, which is why
these are here: each one fails against the old wiring.

The second half is the shape of the answer. "Not compared" is not "passed":
`{"passed": True, "results": []}` was what 11 of the 12 shipped cases reported
for physics contracts, and case_memory indexed all of them as contract-passing
runs.
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.orchestrator import AbaqusOrchestrator  # noqa: E402
from core.pipeline import _run_snapshot, run_benchmark_async, run_pipeline  # noqa: E402

SPEC = {
    "meta": {"model_name": "Cantilever", "abaqus_release": "2021"},
    "geometry": {"type": "cantilever_block", "L": 100.0, "W": 10.0, "H": 10.0,
                 "seed_size": 5.0},
    "material": {"name": "Steel", "E": 210000.0, "nu": 0.3},
    "analysis": {"solver": "standard", "step_type": "Static"},
    "bc_load": {"load_type": "concentrated_force", "value": -1.0, "direction": 2},
    "outputs": {"kpis": [{"name": "U_tip", "type": "nodal_displacement",
                          "location": "tip_center", "component": "U2"}]},
}


def _make_run(run_id: str, **extra) -> dict:
    run = {
        "run_id": run_id, "status": "PENDING", "spec": SPEC,
        "runner_cfg": {}, "stages": {}, "kpis": {},
        "started_at": time.time(), "finished_at": None, "progress_pct": 0,
    }
    run.update(extra)
    return run


def _completed_orchestrator(**result_extra):
    orch = MagicMock()
    result = {"status": "COMPLETED", "kpis": {"U_tip": -0.0019}}
    result.update(result_extra)
    orch.run.return_value = result
    return orch


def _drive(runs, run_id):
    """Run the pipeline with Abaqus reported present but mocked out."""
    asyncio.new_event_loop().run_until_complete(run_pipeline(run_id, runs))


# ── the wiring itself ────────────────────────────────────────────────


def test_the_pipeline_hands_the_orchestrator_its_baseline():
    runs = {"r": _make_run("r",
                           expected_path="/cases/cantilever/expected.json",
                           contracts_path="/cases/cantilever/contracts.yaml")}
    orch = _completed_orchestrator()
    with patch("core.pipeline.check_abaqus", return_value=True), \
         patch("agent.orchestrator.build_orchestrator", return_value=orch) as build:
        _drive(runs, "r")

    kwargs = build.call_args.kwargs
    assert kwargs["expected_path"] == "/cases/cantilever/expected.json"
    assert kwargs["contracts_path"] == "/cases/cantilever/contracts.yaml"


def test_a_caller_with_no_baseline_passes_none_rather_than_omitting_it():
    """Omitting the argument and passing None look the same to the
    orchestrator, but only one of them is a decision the reader can see."""
    runs = {"r": _make_run("r")}
    orch = _completed_orchestrator()
    with patch("core.pipeline.check_abaqus", return_value=True), \
         patch("agent.orchestrator.build_orchestrator", return_value=orch) as build:
        _drive(runs, "r")

    kwargs = build.call_args.kwargs
    assert kwargs["expected_path"] is None
    assert kwargs["contracts_path"] is None


def test_the_benchmark_uses_the_case_files_it_had_been_ignoring():
    """cases/<name>/ holds expected.json, contracts.yaml and runner.json. The
    benchmark passed `runner_cfg: {}` and no paths at all, so it graded nothing
    and solved with the orchestrator's bare defaults (cpus=1, timeout 1800s)
    rather than the case's own settings."""
    runs = {"b": {"run_id": "b", "cases": ["cantilever"], "results": {},
                  "status": "PENDING", "started_at": time.time()}}
    captured = {}

    async def fake_run_pipeline(case_run_id, all_runs, *a, **kw):
        captured.update(all_runs[case_run_id])
        all_runs[case_run_id]["status"] = "COMPLETED"

    with patch("core.pipeline.run_pipeline", new=fake_run_pipeline):
        asyncio.new_event_loop().run_until_complete(
            run_benchmark_async("b", runs, dry_run=False))

    assert captured["expected_path"].endswith("expected.json")
    assert Path(captured["expected_path"]).is_file()
    assert captured["contracts_path"].endswith("contracts.yaml")
    # cantilever/runner.json is the only source for these; {} meant the
    # orchestrator's defaults, which no shipped case actually uses.
    on_disk = json.loads((ROOT / "cases" / "cantilever" / "runner.json")
                         .read_text(encoding="utf-8"))
    assert captured["runner_cfg"] == on_disk
    assert captured["runner_cfg"], "runner.json is empty -- test asserts nothing"


def test_a_case_without_contracts_yaml_passes_none_not_a_missing_path():
    """11 of the 12 shipped cases have no contracts.yaml. A path string
    pointing at a file that is not there would reach `Path(...).exists()` and
    be silently dropped; None is the same outcome stated out loud."""
    runs = {"b": {"run_id": "b", "cases": ["modal"], "results": {},
                  "status": "PENDING", "started_at": time.time()}}
    captured = {}

    async def fake_run_pipeline(case_run_id, all_runs, *a, **kw):
        captured.update(all_runs[case_run_id])
        all_runs[case_run_id]["status"] = "COMPLETED"

    with patch("core.pipeline.run_pipeline", new=fake_run_pipeline):
        asyncio.new_event_loop().run_until_complete(
            run_benchmark_async("b", runs, dry_run=False))

    assert not (ROOT / "cases" / "modal" / "contracts.yaml").exists()
    assert captured["contracts_path"] is None
    assert captured["expected_path"] is not None


# ── the shape of "not graded" ────────────────────────────────────────


def _orchestrator() -> AbaqusOrchestrator:
    return AbaqusOrchestrator(spec_dict=dict(SPEC))


def test_no_baseline_is_recorded_as_not_graded_not_as_an_empty_dict():
    orch = _orchestrator()
    orch._stage_no_baseline()
    regression = orch.result["regression"]
    assert regression["passed"] is None, "None means not graded; False means failed"
    assert regression["comparisons"] == {}
    assert "expected.json" in regression["not_compared_reason"]


def test_zero_contracts_is_not_a_contract_pass():
    orch = _orchestrator()
    assert orch.contracts == [], "this spec carries no contracts block"
    orch._stage_contracts({"U_tip": -0.0019})
    contracts = orch.result["contracts"]
    assert contracts["passed"] is None, (
        "zero checks reported as passed: %r" % contracts)
    assert contracts["results"] == []
    assert contracts["not_checked_reason"]


def test_the_contract_stage_still_reports_a_real_verdict():
    """The None above must not have swallowed the case that matters."""
    orch = AbaqusOrchestrator(spec_dict=dict(
        SPEC, contracts=[{"name": "tip_down", "check": "operator",
                          "kpi": "U_tip", "operator": "<", "value": 0.0,
                          "severity": "error"}]))
    orch._stage_contracts({"U_tip": -0.0019})
    assert orch.result["contracts"]["passed"] is True
    assert orch.result["contracts"]["results"]


# ── what reaches the UI ──────────────────────────────────────────────


def test_the_not_graded_verdict_reaches_the_run_snapshot():
    runs = {"r": _make_run("r")}
    orch = _completed_orchestrator(regression={
        "passed": None, "comparisons": {},
        "not_compared_reason": "没有提供 expected.json 基准"})
    with patch("core.pipeline.check_abaqus", return_value=True), \
         patch("agent.orchestrator.build_orchestrator", return_value=orch):
        _drive(runs, "r")

    snapshot = _run_snapshot(runs["r"])
    assert snapshot["regression"]["passed"] is None
    assert snapshot["regression"]["not_compared_reason"]


@pytest.mark.parametrize("stage,label", [
    ("compare_kpis", "regression"),
    ("physics_contracts", "physics contracts"),
])
def test_a_not_graded_stage_logs_a_warning_not_a_red_fail(stage, label):
    """`passed: None` used to render as FAIL in red, which sends a reader
    hunting for a defect in a model that was never checked."""
    runs = {"r": _make_run("r")}
    captured = {}

    def fake_build(**kwargs):
        orch = MagicMock()

        def _run():
            kwargs["on_progress"](stage, {"passed": None, "caveat": "没有基准"})
            captured["stages"] = runs["r"]["stages"]
            return {"status": "COMPLETED", "kpis": {}}

        orch.run.side_effect = _run
        return orch

    with patch("core.pipeline.check_abaqus", return_value=True), \
         patch("agent.orchestrator.build_orchestrator", new=fake_build):
        _drive(runs, "r")

    logs = captured["stages"][stage]["logs"]
    text = " ".join(entry["text"] for entry in logs)
    assert "NOT GRADED" in text
    assert f"{label}: FAIL" not in text
    assert not any(entry["level"] == "error" for entry in logs), logs
    # A stage whose answer is "not graded" has finished. It used to stay at
    # "running" forever because the terminal test was `passed is not None`.
    assert captured["stages"][stage]["status"] == "done"
    # And the caveat must not be labelled a solver downgrade.
    assert "降级说明" not in text
