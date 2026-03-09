"""
test_monitor_job.py
-------------------
Unit tests for .sta / .log parsing in monitor_job.
No Abaqus required (uses fixture files).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from runner.monitor_job import JobStatus, _parse_messages, _parse_sta, _status_from_log


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
