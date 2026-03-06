"""
submit_job.py
-------------
Tool: submit_job(inp_path, cpus, mp_mode, ...) -> {job_id, workdir, status}

Submits an Abaqus analysis job using the official analysis execution procedure.
Supports background mode, timeout, and license queue control.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
import uuid
from pathlib import Path

from tools.errors import AbaqusAgentError, ErrorCode


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def submit_job(
    inp_path: str | Path,
    workdir: str | Path | None = None,
    cpus: int = 1,
    mp_mode: str = "threads",
    memory: str = "90%",
    background: bool = True,
    interactive: bool = False,
    allow_license_queue: bool = False,
    timeout_seconds: int = 3600,
) -> dict:
    """
    Submit an Abaqus analysis job.

    Parameters
    ----------
    inp_path          : path to .inp file
    workdir           : run directory (defaults to inp parent)
    cpus              : number of CPUs
    mp_mode           : 'threads' or 'mpi'
    memory            : memory allocation e.g. '90%' or '8192 mb'
    background        : run in background (non-blocking)
    interactive       : run interactively (blocking, mutually exclusive with background)
    allow_license_queue : if False, fail immediately on license unavailable
    timeout_seconds   : max wall time (only enforced in interactive mode)

    Returns
    -------
    dict:
        job_id    : str   - unique job identifier
        job_name  : str   - Abaqus job name (inp stem)
        workdir   : Path  - working directory
        status    : str   - 'submitted' or 'completed' or 'failed'
        log_path  : str   - path to .log file
    """
    inp_path = Path(inp_path).resolve()
    if not inp_path.exists():
        raise AbaqusAgentError(ErrorCode.FILE_NOT_FOUND, f".inp not found: {inp_path}")
    if len(str(inp_path)) > 256:
        raise AbaqusAgentError(
            ErrorCode.PATH_TOO_LONG,
            f"Abaqus path length limit is 256 chars. Got {len(str(inp_path))}.",
        )

    workdir = Path(workdir) if workdir else inp_path.parent
    workdir.mkdir(parents=True, exist_ok=True)

    job_name = inp_path.stem
    job_id   = str(uuid.uuid4())[:8]
    log_path = workdir / f"{job_name}.log"

    # Build the command (official analysis execution procedure)
    cmd = _build_cmd(
        job_name=job_name,
        inp_path=inp_path,
        cpus=cpus,
        mp_mode=mp_mode,
        memory=memory,
        background=background,
        interactive=interactive,
    )

    # License queue env variable
    env_extra = {}
    if not allow_license_queue:
        env_extra["lmhanglimit"] = "1"   # fail quickly if no license

    meta = {
        "job_id": job_id,
        "job_name": job_name,
        "workdir": workdir,
        "inp_path": str(inp_path),
        "cpus": cpus,
        "mp_mode": mp_mode,
        "cmd": " ".join(cmd),
        "log_path": str(log_path),
    }

    try:
        if interactive:
            result = subprocess.run(
                cmd,
                cwd=str(workdir),
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
            )
            log_path.write_text(result.stdout + "\n" + result.stderr, encoding="utf-8")
            _write_meta(workdir, job_name, meta)

            if result.returncode != 0:
                err_code = _classify_error(result.stdout + result.stderr)
                raise AbaqusAgentError(
                    err_code,
                    f"Job {job_name} failed (rc={result.returncode}). See {log_path}",
                    log_snippet=result.stderr[-2000:],
                    workdir=str(workdir),
                )
            meta["status"] = "completed"
        else:
            # Background: fire-and-forget, user polls via monitor_job
            subprocess.Popen(
                cmd,
                cwd=str(workdir),
                stdout=open(log_path, "w"),
                stderr=subprocess.STDOUT,
            )
            meta["status"] = "submitted"
            _write_meta(workdir, job_name, meta)

    except subprocess.TimeoutExpired:
        raise AbaqusAgentError(
            ErrorCode.TIMEOUT,
            f"Job {job_name} exceeded timeout of {timeout_seconds}s",
            workdir=str(workdir),
        )
    except FileNotFoundError:
        raise AbaqusAgentError(ErrorCode.ABAQUS_NOT_FOUND, "'abaqus' not found in PATH")

    meta["workdir"] = str(workdir)
    return meta


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_cmd(
    job_name: str,
    inp_path: Path,
    cpus: int,
    mp_mode: str,
    memory: str,
    background: bool,
    interactive: bool,
) -> list[str]:
    cmd = [
        "abaqus",
        f"job={job_name}",
        f"input={inp_path}",
        f"cpus={cpus}",
        f"mp_mode={mp_mode}",
        f"memory={memory}",
    ]
    if interactive:
        cmd.append("interactive")
    elif background:
        cmd.append("background")
    return cmd


def _classify_error(output: str) -> ErrorCode:
    """Classify Abaqus job failure from log output."""
    o = output.upper()
    if "LICENSE" in o or "TOKEN" in o or "CHECKOUT" in o:
        return ErrorCode.LICENSE_UNAVAILABLE
    if "NOT CONVERGE" in o or "CONVERGENCE" in o or "DIVERGE" in o:
        return ErrorCode.NONCONVERGENCE
    if "SYNTAX" in o:
        return ErrorCode.SYNTAX_ERROR
    if "MEMORY" in o:
        return ErrorCode.MEMORY_ERROR
    return ErrorCode.JOB_FAILED


def _write_meta(workdir: Path, job_name: str, meta: dict) -> None:
    meta_path = workdir / f"{job_name}_meta.json"
    serializable = {k: str(v) for k, v in meta.items()}
    meta_path.write_text(json.dumps(serializable, indent=2), encoding="utf-8")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python submit_job.py <file.inp> [cpus] [--interactive]")
        sys.exit(1)
    cpus_arg = int(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2].isdigit() else 1
    interactive_arg = "--interactive" in sys.argv
    r = submit_job(sys.argv[1], cpus=cpus_arg, interactive=interactive_arg, background=not interactive_arg)
    print(json.dumps({k: str(v) for k, v in r.items()}, indent=2))
