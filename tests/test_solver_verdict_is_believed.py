"""When the solver says it did not finish, the product must not say COMPLETED.

Measured on cantilever_plastic (a case whose expected.json declares
``expected_outcome: NONCONVERGENCE`` on purpose):

    .sta tail : THE ANALYSIS HAS NOT BEEN COMPLETED
    .msg      : ***ERROR: TIME INCREMENT REQUIRED IS LESS THAN THE MINIMUM
    reported  : status COMPLETED, regression passed=True
    extracted : U_tip = -221.5 mm   (on a 100 mm beam)

Three independent guards had to fail at once for that to happen:

1. ``runner/submit_job.py`` decides success from the launcher's exit code, and
   the Abaqus launcher exits 0 even when the analysis aborts.
2. ``agent/orchestrator.py`` short-circuited the monitor stage whenever submit
   said "completed", so the .sta verdict was never read on interactive runs —
   the parsing existed, it just sat in the background-polling branch.
3. ``_stage_compare`` reported ``passed: True`` for an empty comparison set.

Each is pinned separately below.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from runner.monitor_job import JobStatus, monitor_job
from tools.errors import AbaqusAgentError, ErrorCode

DIVERGED_STA = """
   STEP  INC ATT SEVERE EQUIL TOTAL  TOTAL    STEP       INC OF
                 DISCON ITERS ITERS  TIME     TIME/LPF   TIME/LPF
   1    15   1U    0     1     1  0.131      0.131      1.500e-05
   1    15   2U    0     1     1  0.131      0.131      1.000e-05

 THE ANALYSIS HAS NOT BEEN COMPLETED
"""

SUCCESS_STA = """
   1     1   1    0     3   100.0%   1.000   1.000E+00   0.2

 THE ANALYSIS HAS COMPLETED SUCCESSFULLY
"""


# ── guard 1: the .sta verdict itself ────────────────────────────────────────

def test_not_been_completed_is_failed_not_pending(tmp_path):
    """Its increment rows carry no percentage column, so the progress regex
    never matched and it fell through to PENDING — 'waiting to start' for an
    analysis the solver had already abandoned."""
    (tmp_path / "Job.sta").write_text(DIVERGED_STA, encoding="utf-8")

    result = monitor_job("Job", tmp_path)

    assert result["status"] == JobStatus.FAILED


def test_a_partial_odb_does_not_buy_a_completed_verdict(tmp_path):
    """An aborted analysis still leaves an .odb behind."""
    (tmp_path / "Job.sta").write_text(DIVERGED_STA, encoding="utf-8")
    (tmp_path / "Job.odb").write_bytes(b"partial")

    result = monitor_job("Job", tmp_path)

    assert result["status"] == JobStatus.FAILED
    assert result["odb_exists"] is True


def test_fatal_errors_without_progress_are_not_pending(tmp_path):
    (tmp_path / "Job.msg").write_text(
        "***ERROR: TIME INCREMENT REQUIRED IS LESS THAN THE MINIMUM SPECIFIED\n",
        encoding="utf-8")

    result = monitor_job("Job", tmp_path)

    assert result["status"] == JobStatus.FAILED


def test_a_successful_run_still_reads_as_completed(tmp_path):
    """The other half of the contract: no false alarms."""
    (tmp_path / "Job.sta").write_text(SUCCESS_STA, encoding="utf-8")
    (tmp_path / "Job.odb").write_bytes(b"real")

    assert monitor_job("Job", tmp_path)["status"] == JobStatus.COMPLETED


# ── guard 2: the orchestrator must read that verdict on interactive runs ────

def _orchestrator(tmp_path, spec_extra=None):
    import yaml

    from agent.orchestrator import AbaqusOrchestrator

    spec = {
        "meta": {"model_name": "Job", "abaqus_release": "2021"},
        "geometry": {"type": "cantilever_block", "L": 100.0, "W": 10.0, "H": 10.0},
        "material": {"name": "Steel", "E": 210000.0, "nu": 0.3},
        "analysis": {"step_type": "Static"},
        "outputs": {"kpis": []},
    }
    spec.update(spec_extra or {})
    spec_path = tmp_path / "spec.yaml"
    spec_path.write_text(yaml.safe_dump(spec), encoding="utf-8")
    orch = AbaqusOrchestrator(str(spec_path))
    orch.workdir = tmp_path
    return orch


def test_interactive_run_reads_the_sta_before_claiming_completion(tmp_path):
    """submit_job says 'completed' purely from an exit code the launcher always
    sets to 0. That must not be the last word."""
    (tmp_path / "Job.sta").write_text(DIVERGED_STA, encoding="utf-8")
    (tmp_path / "Job.odb").write_bytes(b"partial")
    orch = _orchestrator(tmp_path)

    with pytest.raises(AbaqusAgentError) as exc:
        orch._stage_monitor({"status": "completed", "job_name": "Job",
                             "workdir": str(tmp_path)})

    assert exc.value.code == ErrorCode.JOB_FAILED
    # The solver's own words must reach the user verbatim, not be paraphrased.
    assert "THE ANALYSIS HAS NOT BEEN COMPLETED" in str(exc.value)


def test_interactive_run_still_passes_a_genuinely_finished_job(tmp_path):
    (tmp_path / "Job.sta").write_text(SUCCESS_STA, encoding="utf-8")
    (tmp_path / "Job.odb").write_bytes(b"real")
    orch = _orchestrator(tmp_path)

    orch._stage_monitor({"status": "completed", "job_name": "Job",
                         "workdir": str(tmp_path)})

    assert orch.result["stages"]["monitor_job"]["status"] == JobStatus.COMPLETED


# ── guard 3: an empty comparison set is not a pass ──────────────────────────

def test_no_expected_kpis_is_not_reported_as_passed(tmp_path):
    orch = _orchestrator(tmp_path)
    orch.expected = {"kpis": {}}
    progress = []
    orch.on_progress = lambda stage, data: progress.append((stage, data))

    orch._stage_compare({"U_tip": -221.4966583251953})

    regression = orch.result["regression"]
    assert regression["passed"] is None, (
        "nothing was compared, so nothing passed")
    assert "没有给任何 KPI 基准" in regression["not_compared_reason"]
    stage, data = progress[-1]
    assert stage == "compare_kpis"
    assert data["passed"] is None
    assert data["caveat"]


def test_real_expectations_still_grade_normally(tmp_path):
    orch = _orchestrator(tmp_path)
    orch.expected = {"kpis": {"U_tip": {"value": -0.0019, "rtol": 0.1}}}
    orch.on_progress = lambda stage, data: None

    orch._stage_compare({"U_tip": -0.0019039579201489687})

    assert orch.result["regression"]["passed"] is True


def test_the_nonconvergence_case_ships_without_a_numeric_baseline():
    """If this ever gains KPI values, the guard above stops being exercised by
    the case that motivated it."""
    expected = json.loads(
        (Path(__file__).resolve().parent.parent / "cases" / "cantilever_plastic"
         / "expected.json").read_text(encoding="utf-8"))

    assert expected["kpis"] == {}
    assert expected["expected_outcome"] == "NONCONVERGENCE"
