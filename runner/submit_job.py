"""
submit_job.py
-------------
Tool: submit_job(inp_path, cpus, mp_mode, ...) -> {job_id, workdir, status}

Submits an Abaqus analysis job using the official analysis execution procedure.
Supports background mode, timeout, and license queue control.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
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
    job_options: dict | None = None,
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
    job_options       : the spec's `job:` block -- extra launcher options
                        (double, user, oldjob, gpus, scratch ...) passed
                        through as `name=value`. See _job_option_args.

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

    # Resolved before the command is built, so a missing subroutine or restart
    # file stops here rather than after a licence checkout.
    job_option_args = _job_option_args(job_options, workdir)

    # Build the command (official analysis execution procedure)
    cmd = _build_cmd(
        job_name=job_name,
        inp_path=inp_path,
        job_option_args=job_option_args,
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
    subprocess_env = {**os.environ, **env_extra} if env_extra else None

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
                # text=True alone decodes as UTF-8 and dies on the first
                # non-ASCII byte the solver emits. Abaqus/Explicit prints
                # Windows locale messages in the system codepage (GBK here),
                # so explicit_impact and blast_plate both crashed with
                # "'utf-8' codec can't decode byte 0xd4" — inside the reader
                # THREAD, i.e. after a real solve had already been paid for,
                # and surfacing as a bare ERROR/UNKNOWN with no log written.
                text=True, encoding="utf-8", errors="replace",
                timeout=timeout_seconds,
                env=subprocess_env,
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
            # rc == 0 is not the same as "it ran". Measured on Abaqus 2021, a
            # command line the launcher rejects -- an unknown option, an option
            # value it does not take, a subroutine or restart file that is not
            # there -- exits 0, writes no .dat and no .odb, and puts the reason
            # on stdout only. Without this the run reaches the monitor stage as
            # a missing .sta and the sentence Abaqus already wrote is thrown
            # away, which is the sentence that names the offending option.
            refusal = _launcher_refused(result.stdout, result.stderr)
            if refusal:
                # Deliberately NOT _classify_error. That function keyword-scans
                # the output, and the launcher's rejection message PRINTS ITS
                # OWN OPTION LIST -- which contains the word "memory", so a
                # bogus option came back classified MEMORY_ERROR. A wrong code
                # on a correct refusal sends the reader to look at RAM.
                raise AbaqusAgentError(
                    ErrorCode.SPEC_INVALID,
                    f"Job {job_name} never started: the Abaqus launcher "
                    f"refused the command line and still exited 0. {refusal}",
                    log_snippet=result.stdout[-2000:],
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
                env=subprocess_env,
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

# Options this pipeline already puts on the command line. A `job:` block that
# set one of them would produce the flag twice, and the duplicate is NOT an
# error: measured on Abaqus 2021, `abaqus job=d input=d.inp cpus=1 cpus=2`
# runs to COMPLETED with no complaint and checks out 6 licence tokens -- the
# two-cpu count -- so the LATER value wins in silence. Job options are
# appended after the pipeline's own, which means a spec writing `job: {cpus:
# 8}` would quietly override runner.json. Refused, with a pointer to where the
# setting really lives.
_RESERVED_JOB_OPTIONS = {
    "job": "the job name comes from the .inp file name",
    "input": "the deck comes from the build stage",
    "interactive": "the pipeline decides how it waits",
    "background": "the pipeline decides how it waits",
    "cpus": "runner.json `cpus`",
    "mp_mode": "runner.json `mp_mode`",
    "memory": "runner.json `memory`",
}

# Options whose value is a file the launcher will look for. Checked here rather
# than left to Abaqus, because Abaqus checks them AFTER taking a licence:
# measured, `user=nosuch.f` answers "The following file(s) could not be
# located: nosuch.f" and `oldjob=neverran` with a *RESTART, READ deck answers
# the same about neverran.odb -- both with EXIT CODE 0 and no .dat.
_FILE_JOB_OPTIONS = {"user": None, "oldjob": ".odb"}


def _job_option_args(job_options: dict | None, workdir: Path) -> list[str]:
    """Turn a spec's `job:` block into launcher arguments.

    A passthrough rather than an enumerated set of supported flags, and the
    measurement is what makes that safe. Every wrong option was tried on
    Abaqus 2021 (artifacts/probe_job):

      bogusoption=1   "Abaqus Error: ..." + the launcher's own list of the 36
                      options it accepts, then no .dat and no .odb
      double=banana   "The specified value ... is not supported"
      user=nosuch.f   "The following file(s) could not be located"
      oldjob=neverran the same, about neverran.odb, when the deck really does
                      carry *RESTART, READ

    ALL FOUR EXIT 0. So the option name is never guessed at here; Abaqus is
    left to judge it, and what this side must not do is read the exit code --
    which is the same rule as everywhere else in this project.

    The launcher's printed list is deliberately NOT used as a validator. It
    omits `gpus`, and `gpus=1` runs: measured, it took 6 licence tokens instead
    of 5 and 3m45s instead of 11s on the same one-element deck. A validator
    built from that list would refuse an option that works.
    """
    if not job_options:
        return []
    if not isinstance(job_options, dict):
        raise AbaqusAgentError(
            ErrorCode.SPEC_INVALID,
            "`job:` must be a mapping of launcher options, e.g. "
            "`job: {double: both}`. Got %s." % type(job_options).__name__)

    args = []
    for key in sorted(job_options):
        name = str(key).strip()
        if name in _RESERVED_JOB_OPTIONS:
            raise AbaqusAgentError(
                ErrorCode.SPEC_INVALID,
                "job.%s is set by the pipeline, not by the spec (%s). Setting "
                "it here would put the option on the command line twice, and "
                "a duplicate is not an error: measured on Abaqus 2021, "
                "`cpus=1 cpus=2` runs to COMPLETED and takes the 2-cpu licence "
                "count, so the later value wins in silence. Job options are "
                "appended last, which means this would quietly override the "
                "pipeline's own." % (name, _RESERVED_JOB_OPTIONS[name]))
        value = job_options[key]
        if value is None or isinstance(value, bool):
            raise AbaqusAgentError(
                ErrorCode.SPEC_INVALID,
                "job.%s has value %r. Launcher options are `name=value` "
                "strings; write the value Abaqus expects, e.g. "
                "`double: both`." % (name, value))
        text = str(value).strip()
        if not text:
            raise AbaqusAgentError(
                ErrorCode.SPEC_INVALID,
                "job.%s is empty. Give it the value Abaqus expects." % name)

        if name in _FILE_JOB_OPTIONS:
            suffix = _FILE_JOB_OPTIONS[name] or ""
            candidate = Path(text)
            if suffix and not candidate.suffix:
                candidate = candidate.with_suffix(suffix)
            if not candidate.is_absolute():
                candidate = workdir / candidate
            if not candidate.exists():
                raise AbaqusAgentError(
                    ErrorCode.FILE_NOT_FOUND,
                    "job.%s names %s, and %s is not there. Abaqus does check "
                    "this, but only after checking out a licence and with "
                    "exit code 0, so it is checked here first."
                    % (name, text, candidate))
        args.append("%s=%s" % (name, text))
    return args


def _launcher_refused(stdout: str, stderr: str) -> str:
    """The launcher's own complaint, or "" if it did not make one.

    Needed because the return code cannot carry it. Measured on Abaqus 2021,
    every rejected command line above exits 0 and says so only on stdout, so a
    run that never started otherwise reaches the monitor stage as a missing
    .sta rather than as the sentence Abaqus already wrote.
    """
    blob = "%s\n%s" % (stdout or "", stderr or "")
    lines = [ln.strip() for ln in blob.splitlines() if ln.strip()]
    for i, line in enumerate(lines):
        if line.startswith("Abaqus Error"):
            return " | ".join(lines[i:i + 4])[:1200]
    return ""


def _build_cmd(
    job_name: str,
    inp_path: Path,
    cpus: int,
    mp_mode: str,
    memory: str,
    background: bool,
    interactive: bool,
    job_option_args: list[str] | None = None,
) -> list[str]:
    from tools.abaqus_cmd import get_abaqus_cmd
    cmd = [
        get_abaqus_cmd(),
        f"job={job_name}",
        f"input={inp_path}",
        f"cpus={cpus}",
        f"mp_mode={mp_mode}",
        f"memory={memory}",
    ]
    cmd.extend(job_option_args or [])
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
