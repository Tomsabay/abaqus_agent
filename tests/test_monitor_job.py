"""
test_monitor_job.py
-------------------
Unit tests for .sta / .log parsing in monitor_job.
No Abaqus required (uses fixture files).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from runner.monitor_job import JobStatus, _parse_messages, _parse_sta, _status_from_log, monitor_job


class TestMonitorJobPublicAPI:
    def test_pending_when_job_files_are_absent(self, tmp_path):
        result = monitor_job("Model", tmp_path)

        assert result["status"] == JobStatus.PENDING
        assert result["progress_pct"] == -1.0
        assert result["last_increment"] == 0
        assert result["last_time"] == 0.0
        assert result["errors"] == []
        assert result["warnings"] == []
        assert result["odb_exists"] is False
        assert result["sta_path"] == str(tmp_path / "Model.sta")
        assert result["odb_path"] is None

    def test_running_sta_with_log_and_msg_dedupes_diagnostics(self, tmp_path):
        (tmp_path / "Model.sta").write_text(
            """
    1          7    1       0      4   75.0%   0.750   7.500E-01   0.2
""",
            encoding="utf-8",
        )
        (tmp_path / "Model.log").write_text(
            """
***WARNING: Mesh quality below threshold
***ERROR: Contact did not converge
""",
            encoding="utf-8",
        )
        (tmp_path / "Model.msg").write_text(
            """
***WARNING: Mesh quality below threshold
WARNING: Solver switched controls
""",
            encoding="utf-8",
        )

        result = monitor_job("Model", tmp_path)

        assert result["status"] == JobStatus.RUNNING
        assert result["progress_pct"] == 75.0
        assert result["last_increment"] == 7
        assert result["last_time"] == 0.75
        assert result["errors"] == ["***ERROR: Contact did not converge"]
        assert result["warnings"] == [
            "***WARNING: Mesh quality below threshold",
            "WARNING: Solver switched controls",
        ]

    def test_completed_log_with_odb_reports_completed_and_odb_path(self, tmp_path):
        (tmp_path / "Model.log").write_text("Abaqus JOB Model JOB COMPLETED\n", encoding="utf-8")
        (tmp_path / "Model.odb").write_text("fake odb placeholder", encoding="utf-8")

        result = monitor_job("Model", tmp_path)

        assert result["status"] == JobStatus.COMPLETED
        assert result["odb_exists"] is True
        assert result["odb_path"] == str(tmp_path / "Model.odb")

    def test_failed_sta_status_wins_even_when_odb_exists(self, tmp_path):
        (tmp_path / "Model.sta").write_text(
            """
    1          2    1       0      3   20.0%   0.200   2.000E-01   0.1
***ERROR: Analysis aborted
""",
            encoding="utf-8",
        )
        (tmp_path / "Model.odb").write_text("partial odb placeholder", encoding="utf-8")

        result = monitor_job("Model", tmp_path)

        assert result["status"] == JobStatus.FAILED
        assert result["odb_exists"] is True
        assert result["odb_path"] == str(tmp_path / "Model.odb")


class TestParseStaFile:
    def test_completed_analysis(self):
        text = """
 STEP  INCREMENT  ATT  SEVERE  EQUIL  TOTAL    STEP TIME   TOTAL TIME  CPU TIME
    1          1    1       0      3  100.0%   1.000   1.000E+00   0.5
ANALYSIS COMPLETE
"""
        status, last_inc, last_time, progress = _parse_sta(text)
        assert status == JobStatus.COMPLETED
        assert last_inc == 1
        assert progress == 100.0

    def test_running_analysis(self):
        text = """
    1          3    1       0      4   30.0%   0.300   3.000E-01   0.1
    1          5    1       0      4   50.0%   0.500   5.000E-01   0.2
"""
        status, last_inc, last_time, progress = _parse_sta(text)
        assert status == JobStatus.RUNNING
        assert last_inc == 5
        assert progress == 50.0

    def test_failed_analysis(self):
        text = """
    1          2    1       0      3   20.0%   0.200   2.000E-01   0.1
***ERROR: Analysis aborted
"""
        status, last_inc, last_time, progress = _parse_sta(text)
        assert status == JobStatus.FAILED

    def test_empty_sta(self):
        status, inc, t, p = _parse_sta("")
        assert status == JobStatus.PENDING
        assert inc == 0


class TestParseMessages:
    def test_error_extraction(self):
        log = """
Abaqus running...
***ERROR: No elements in model
Some other line
"""
        errors, warnings = _parse_messages(log)
        assert any("ERROR" in e for e in errors)

    def test_warning_extraction(self):
        log = """
***WARNING: Mesh quality below threshold
"""
        errors, warnings = _parse_messages(log)
        assert any("WARNING" in w for w in warnings)

    def test_clean_log(self):
        log = "Abaqus 2024 running. Analysis complete."
        errors, warnings = _parse_messages(log)
        assert errors == []
        assert warnings == []


class TestStatusFromLog:
    def test_completed(self):
        assert _status_from_log("ANALYSIS COMPLETE") == JobStatus.COMPLETED

    def test_aborted(self):
        assert _status_from_log("Analysis ABORTED due to error") == JobStatus.ABORTED

    def test_unknown(self):
        assert _status_from_log("Starting Abaqus...") == JobStatus.UNKNOWN
