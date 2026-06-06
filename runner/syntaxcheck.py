"""
syntaxcheck.py
--------------
Tool: syntaxcheck_inp(inp_path) -> {ok, warnings, errors}

Uses Abaqus analysis execution with `syntaxcheck` option.
Per official docs, syntaxcheck does NOT consume license tokens.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

from tools.errors import AbaqusAgentError, ErrorCode


def syntaxcheck_inp(inp_path: str | Path, workdir: str | Path | None = None) -> dict:
    """
    Run Abaqus syntaxcheck on a .inp file.

    Returns
    -------
    dict:
        ok       : bool   - True if no errors found
        warnings : list   - warning messages extracted from output
        errors   : list   - error messages extracted from output
        log_path : str    - path to the check log
    """
    inp_path = Path(inp_path).resolve()
    if not inp_path.exists():
        raise AbaqusAgentError(ErrorCode.FILE_NOT_FOUND, f"inp not found: {inp_path}")

    workdir = Path(workdir) if workdir else inp_path.parent
    workdir.mkdir(parents=True, exist_ok=True)

    job_name = inp_path.stem + "_syntaxcheck"
    log_path = workdir / f"{job_name}.log"

    from tools.abaqus_cmd import get_abaqus_cmd

    # Official: abaqus job=<name> input=<path> syntaxcheck
    cmd = [
        get_abaqus_cmd(),
        f"job={job_name}",
        f"input={inp_path}",
        "syntaxcheck",
        "interactive",
    ]

    try:
        result = subprocess.run(
            cmd,
            cwd=str(workdir),
            capture_output=True,
            text=True,
            timeout=120,
        )
        combined = result.stdout + "\n" + result.stderr
        log_path.write_text(combined, encoding="utf-8")
    except subprocess.TimeoutExpired:
        raise AbaqusAgentError(ErrorCode.TIMEOUT, "syntaxcheck timed out after 120s")
    except FileNotFoundError:
        raise AbaqusAgentError(ErrorCode.ABAQUS_NOT_FOUND, "'abaqus' not found in PATH")

    # Also read the .dat file which has the detailed check output
    dat_path = workdir / f"{job_name}.dat"
    dat_text = dat_path.read_text(encoding="utf-8", errors="replace") if dat_path.exists() else ""

    warnings, errors = _parse_check_output(combined + "\n" + dat_text)
    ok = len(errors) == 0 and result.returncode == 0

    return {
        "ok": ok,
        "warnings": warnings,
        "errors": errors,
        "log_path": str(log_path),
        "returncode": result.returncode,
    }


def _parse_check_output(text: str) -> tuple[list, list]:
    """Parse Abaqus syntaxcheck output for warnings and errors."""
    warnings = []
    errors = []

    for line in text.splitlines():
        line_stripped = line.strip()
        # Abaqus error patterns
        if re.search(r"\*\*\*ERROR|ERROR:|Abaqus Error", line_stripped, re.IGNORECASE):
            errors.append(line_stripped)
        elif re.search(r"\*\*\*WARNING|WARNING:", line_stripped, re.IGNORECASE):
            warnings.append(line_stripped)
        # Common fatal patterns
        elif re.search(r"exited with (signal|code)", line_stripped, re.IGNORECASE):
            errors.append(line_stripped)

    return warnings, errors


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python syntaxcheck.py <file.inp> [workdir]")
        sys.exit(1)
    result = syntaxcheck_inp(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["ok"] else 1)
