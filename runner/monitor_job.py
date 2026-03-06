"""
monitor_job.py
--------------
Tool: monitor_job(job_name, workdir) -> {status, progress, errors}

Polls Abaqus job status by reading .sta and .log files.
Abaqus writes incremental status to .sta during analysis.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from tools.errors import AbaqusAgentError, ErrorCode


# Job status enum
class JobStatus:
    PENDING    = "PENDING"
    RUNNING    = "RUNNING"
    COMPLETED  = "COMPLETED"
    FAILED     = "FAILED"
    ABORTED    = "ABORTED"
    UNKNOWN    = "UNKNOWN"


def monitor_job(job_name: str, workdir: str | Path) -> dict:
    """
    Check the status of a submitted Abaqus job.

    Returns
    -------
    dict:
        status        : str   - JobStatus value
        progress_pct  : float - estimated % complete (0-100), -1 if unknown
        last_increment: int   - last completed increment from .sta
        last_time     : float - last analysis time from .sta
        errors        : list  - error messages from log
        warnings      : list  - warning messages
        odb_exists    : bool  - whether .odb has been written
    """
    workdir = Path(workdir)
    sta_path = workdir / f"{job_name}.sta"
    log_path = workdir / f"{job_name}.log"
    msg_path = workdir / f"{job_name}.msg"
    odb_path = workdir / f"{job_name}.odb"

    odb_exists = odb_path.exists()
    status     = JobStatus.UNKNOWN
    progress   = -1.0
    last_inc   = 0
    last_time  = 0.0
    errors     = []
    warnings   = []

    # ── Parse .sta (primary status file) ────────────────────────────────────
    if sta_path.exists():
        sta_text = sta_path.read_text(encoding="utf-8", errors="replace")
        status, last_inc, last_time, progress = _parse_sta(sta_text)
    elif log_path.exists():
        log_text = log_path.read_text(encoding="utf-8", errors="replace")
        status = _status_from_log(log_text)
    else:
        status = JobStatus.PENDING

    # ── Parse .log / .msg for errors and warnings ────────────────────────────
    for fpath in [log_path, msg_path]:
        if fpath.exists():
            text = fpath.read_text(encoding="utf-8", errors="replace")
            e, w = _parse_messages(text)
            errors.extend(e)
            warnings.extend(w)

    # Deduplicate
    errors   = list(dict.fromkeys(errors))[:20]
    warnings = list(dict.fromkeys(warnings))[:20]

    # If ODB exists and no error → completed
    if odb_exists and status == JobStatus.UNKNOWN:
        status = JobStatus.COMPLETED

    return {
        "status": status,
        "progress_pct": progress,
        "last_increment": last_inc,
        "last_time": last_time,
        "errors": errors,
        "warnings": warnings,
        "odb_exists": odb_exists,
        "sta_path": str(sta_path),
        "odb_path": str(odb_path) if odb_exists else None,
    }


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------

def _parse_sta(text: str) -> tuple[str, int, float, float]:
    """Parse Abaqus .sta file for job progress."""
    lines = text.strip().splitlines()
    if not lines:
        return JobStatus.PENDING, 0, 0.0, 0.0

    last_inc  = 0
    last_time = 0.0
    progress  = 0.0

    for line in lines:
        # .sta format: STEP  INCREMENT  ATT  SEVERE  EQUIL  TOTAL    STEP TIME   TOTAL TIME  CPU TIME
        # Example:        1          1    1       0      3  100.0%   0.100   1.000E-01   0.2
        m = re.match(
            r"\s*(\d+)\s+(\d+)\s+\d+\s+\d+\s+\d+\s+([\d.]+)%\s+([\d.E+\-]+)\s+([\d.E+\-]+)",
            line
        )
        if m:
            last_inc  = int(m.group(2))
            progress  = float(m.group(3))
            last_time = float(m.group(5))

    # Determine status
    if "ANALYSIS COMPLETE" in text.upper() or "JOB COMPLETED" in text.upper():
        return JobStatus.COMPLETED, last_inc, last_time, 100.0
    if any(x in text.upper() for x in ["ERROR", "ABORTED", "TERMINATED"]):
        return JobStatus.FAILED, last_inc, last_time, progress
    if last_inc > 0:
        return JobStatus.RUNNING, last_inc, last_time, progress
    return JobStatus.PENDING, 0, 0.0, 0.0


def _status_from_log(log_text: str) -> str:
    upper = log_text.upper()
    if "ANALYSIS COMPLETE" in upper or "JOB COMPLETED" in upper:
        return JobStatus.COMPLETED
    if "ABORTED" in upper or "TERMINATED" in upper:
        return JobStatus.ABORTED
    if any(x in upper for x in ["***ERROR", "ERROR:"]):
        return JobStatus.FAILED
    if "BEGIN ANALYSIS" in upper or "COMPLETED ABAQUS" in upper:
        return JobStatus.RUNNING
    return JobStatus.UNKNOWN


def _parse_messages(text: str) -> tuple[list, list]:
    errors   = []
    warnings = []
    for line in text.splitlines():
        s = line.strip()
        if re.search(r"\*\*\*ERROR|ERROR:|Abaqus Error", s, re.IGNORECASE):
            errors.append(s)
        elif re.search(r"\*\*\*WARNING|WARNING:", s, re.IGNORECASE):
            warnings.append(s)
    return errors, warnings


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python monitor_job.py <job_name> <workdir>")
        sys.exit(1)
    r = monitor_job(sys.argv[1], sys.argv[2])
    print(json.dumps(r, indent=2))
