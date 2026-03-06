"""
Tests for advanced failure auto-repair (premium).
No Abaqus installation required.
"""

import pytest
import tempfile
from pathlib import Path

from premium.autorepair.log_parser import (
    parse_job_diagnostics,
    DiagnosticCategory,
    DiagnosticSeverity,
    ParseResult,
)
from premium.autorepair.diagnosis import _rule_based_diagnosis
from premium.autorepair.repair_strategies import apply_repairs, can_retry


class TestLogParser:
    def test_parse_empty_workdir(self, tmp_path):
        result = parse_job_diagnostics(tmp_path, "nonexistent")
        assert isinstance(result, ParseResult)
        assert len(result.events) == 0
        assert not result.completed

    def test_parse_convergence_failure(self, tmp_path):
        msg = tmp_path / "TestJob.msg"
        msg.write_text(
            "STEP     1  INCREMENT     5\n"
            "***NOTE: THE SOLUTION HAS NOT CONVERGED\n"
            "TIME INCREMENT   1.00E-06 LESS THAN MINIMUM\n"
        )
        result = parse_job_diagnostics(tmp_path, "TestJob")
        assert len(result.errors) >= 1
        assert result.primary_category == DiagnosticCategory.CONVERGENCE

    def test_parse_distortion_error(self, tmp_path):
        msg = tmp_path / "TestJob.msg"
        msg.write_text("***ERROR: EXCESSIVE DISTORTION OF ELEMENTS 123, 456\n")
        result = parse_job_diagnostics(tmp_path, "TestJob")
        assert result.primary_category == DiagnosticCategory.ELEMENT_DISTORTION

    def test_parse_zero_pivot(self, tmp_path):
        msg = tmp_path / "TestJob.msg"
        msg.write_text("***WARNING: ZERO PIVOT DETECTED AT DOF 3 NODE 100\n")
        result = parse_job_diagnostics(tmp_path, "TestJob")
        assert any(e.category == DiagnosticCategory.RIGID_BODY_MOTION for e in result.events)

    def test_parse_sta_file(self, tmp_path):
        sta = tmp_path / "TestJob.sta"
        sta.write_text(
            "  STEP  INC  ATT  TOTAL   STEP TIME   TOTAL TIME\n"
            "     1    1    1  5.000E-01  5.000E-01\n"
            "     1    2    1  1.000E+00  1.000E+00\n"
        )
        result = parse_job_diagnostics(tmp_path, "TestJob")
        assert result.last_increment.get("step") == 1
        assert result.last_increment.get("increment") == 2

    def test_parse_completed_log(self, tmp_path):
        log = tmp_path / "TestJob.log"
        log.write_text("Abaqus JOB TestJob COMPLETED\n")
        result = parse_job_diagnostics(tmp_path, "TestJob")
        assert result.completed

    def test_to_llm_context(self, tmp_path):
        msg = tmp_path / "TestJob.msg"
        msg.write_text("***ERROR: THE SOLUTION HAS NOT CONVERGED\n")
        result = parse_job_diagnostics(tmp_path, "TestJob")
        context = result.to_llm_context()
        assert "CONVERGENCE" in context
        assert "NOT CONVERGED" in context


class TestDiagnosis:
    def test_convergence_diagnosis(self, tmp_path):
        msg = tmp_path / "TestJob.msg"
        msg.write_text("***ERROR: THE SOLUTION HAS NOT CONVERGED\n")
        result = parse_job_diagnostics(tmp_path, "TestJob")

        diagnosis = _rule_based_diagnosis(result, "TestJob", "NONCONVERGENCE")
        assert diagnosis["severity"] == "RECOVERABLE"
        assert diagnosis["retry_recommended"]
        assert len(diagnosis["parameter_changes"]) > 0

    def test_memory_diagnosis(self, tmp_path):
        dat = tmp_path / "TestJob.dat"
        dat.write_text("***ERROR: INSUFFICIENT MEMORY FOR SOLVER\n")
        result = parse_job_diagnostics(tmp_path, "TestJob")

        diagnosis = _rule_based_diagnosis(result, "TestJob", "MEMORY_ERROR")
        assert diagnosis["severity"] == "RECOVERABLE"

    def test_unknown_failure_is_fatal(self):
        result = ParseResult()
        diagnosis = _rule_based_diagnosis(result, "TestJob", "UNKNOWN")
        assert diagnosis["severity"] == "FATAL"
        assert not diagnosis["retry_recommended"]


class TestRepairStrategies:
    def test_apply_nlgeom_repair(self):
        spec = {"analysis": {"step_type": "Static"}, "geometry": {"seed_size": 10}}
        diagnosis = {
            "severity": "RECOVERABLE",
            "fix_action": "Enable nlgeom",
            "parameter_changes": [
                {"param": "nlgeom", "current": "OFF", "suggested": "ON", "reason": "test"},
            ],
            "retry_recommended": True,
        }
        repaired = apply_repairs(spec, diagnosis)
        assert repaired["analysis"]["nlgeom"] is True
        assert "_repair_history" in repaired["meta"]

    def test_apply_seed_size_reduction(self):
        spec = {"geometry": {"seed_size": 10.0}, "analysis": {}}
        diagnosis = {
            "parameter_changes": [
                {"param": "seed_size", "current": "10", "suggested": "reduce by 50%", "reason": "test"},
            ],
        }
        repaired = apply_repairs(spec, diagnosis)
        assert repaired["geometry"]["seed_size"] == 5.0

    def test_apply_increment_change(self):
        spec = {"analysis": {"step_type": "Static"}, "meta": {}}
        diagnosis = {
            "parameter_changes": [
                {"param": "initial_increment", "current": "0.1", "suggested": "0.01", "reason": "test"},
            ],
        }
        repaired = apply_repairs(spec, diagnosis)
        assert repaired["analysis"]["_initial_inc"] == 0.01

    def test_can_retry_recoverable(self):
        assert can_retry({"severity": "RECOVERABLE", "retry_recommended": True})

    def test_cannot_retry_fatal(self):
        assert not can_retry({"severity": "FATAL", "retry_recommended": False})

    def test_cannot_retry_no_recommendation(self):
        assert not can_retry({"severity": "RECOVERABLE", "retry_recommended": False})
