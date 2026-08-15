"""
ccx_solve.py
------------
Run a flat deck through CalculiX and refuse to call a bad solve good.

The post-run gate is belt-and-braces, NOT the primary safety mechanism — that
is the refuse-before-run whitelist in runner/ccx_whitelist.py. ccx exits 0 with
a silently unloaded model when it meets a load keyword it does not know, so
``returncode == 0`` proves nothing on its own. What is checked here:

  * exit code 0
  * ``No analysis was selected`` absent (fires when the STEP procedure itself
    was uninterpretable)
  * no ``Card image cannot be interpreted`` line (fires when ANY card was
    dropped, including the dangerous silent-load case)
  * a result file that actually contains results, not just a mesh echo

The raw console text is persisted next to the results as the evidence artefact.
"""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

from tools.ccx_cmd import get_ccx_cmd
from tools.errors import AbaqusAgentError, ErrorCode

CONSOLE_NAME = "ccx_console.txt"

_NO_ANALYSIS = "No analysis was selected"
_UNINTERPRETED = "cannot be interpreted"


def classify_ccx_error(text: str) -> ErrorCode:
    lowered = text.lower()
    if "*error reading" in lowered or ("calinput" in lowered and "*error" in lowered):
        return ErrorCode.SYNTAX_ERROR
    if "did not converge" in lowered or "divergence" in lowered or "too many iterations" in lowered:
        return ErrorCode.NONCONVERGENCE
    return ErrorCode.JOB_FAILED


def _dropped_cards(text: str) -> list[str]:
    out = []
    for line in text.splitlines():
        if _UNINTERPRETED in line:
            out.append(line.strip())
    return out


def solve_ccx(
    inp_path: str | Path,
    workdir: str | Path,
    *,
    timeout_seconds: int = 1800,
    cpus: int = 1,
    ccx_cmd: str | None = None,
) -> dict:
    """Run ``ccx -i <job>``. Returns the same shape runner.submit_job.submit_job does.

    Raises AbaqusAgentError when the solve failed OR when it "succeeded" in a
    way we cannot trust.
    """
    inp_path = Path(inp_path)
    workdir = Path(workdir)
    job_name = inp_path.stem

    exe = ccx_cmd or get_ccx_cmd()
    if not exe:
        raise AbaqusAgentError(
            ErrorCode.CALCULIX_NOT_FOUND,
            "找不到 CalculiX（ccx）：把它加进 PATH，或用 ABAQUS_AGENT_CCX_EXE 指定 ccx.exe 的完整路径",
            workdir=str(workdir),
        )

    env = dict(os.environ)
    # ccx has no -cpus flag; threads come from OMP_NUM_THREADS.
    env["OMP_NUM_THREADS"] = str(max(1, int(cpus or 1)))

    cmd = [str(exe), "-i", job_name]
    started = time.time()
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(workdir),
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
        )
        output, returncode = proc.stdout or "", proc.returncode
    except subprocess.TimeoutExpired as exc:
        partial = exc.output or ""
        if isinstance(partial, bytes):
            partial = partial.decode("utf-8", "replace")
        (workdir / CONSOLE_NAME).write_text(partial, encoding="utf-8", errors="replace")
        raise AbaqusAgentError(
            ErrorCode.TIMEOUT,
            "CalculiX 超时（%d 秒）未结束" % timeout_seconds,
            workdir=str(workdir),
        )

    log_path = workdir / CONSOLE_NAME
    log_path.write_text(output, encoding="utf-8", errors="replace")
    elapsed = time.time() - started

    dat_path = workdir / ("%s.dat" % job_name)
    frd_path = workdir / ("%s.frd" % job_name)

    if returncode != 0:
        raise AbaqusAgentError(
            classify_ccx_error(output),
            "CalculiX 退出码 %d，求解失败" % returncode,
            log_snippet=output[-2000:],
            workdir=str(workdir),
        )

    dropped = _dropped_cards(output)
    if dropped:
        raise AbaqusAgentError(
            ErrorCode.SYNTAX_ERROR,
            "CalculiX 忽略了 %d 张它看不懂的卡（退出码仍是 0，但结果不可信）：%s"
            % (len(dropped), "; ".join(dropped[:3])),
            log_snippet=output[-2000:],
            workdir=str(workdir),
        )

    if _NO_ANALYSIS in output:
        raise AbaqusAgentError(
            ErrorCode.JOB_FAILED,
            "CalculiX 报告 “No analysis was selected”：分析步没有被识别，没有算任何东西",
            log_snippet=output[-2000:],
            workdir=str(workdir),
        )

    has_dat_results = dat_path.exists() and dat_path.stat().st_size > 0
    has_frd_results = frd_path.exists() and " -4" in frd_path.read_text(
        encoding="utf-8", errors="replace"
    )
    if not has_dat_results and not has_frd_results:
        raise AbaqusAgentError(
            ErrorCode.KPI_EXTRACTION_FAILED,
            "CalculiX 退出码 0，但没有写出任何结果块（.dat 为空且 .frd 只有网格）",
            log_snippet=output[-2000:],
            workdir=str(workdir),
        )

    return {
        "job_id": job_name,
        "job_name": job_name,
        "workdir": workdir,
        "inp_path": inp_path,
        "cmd": cmd,
        "log_path": log_path,
        "status": "completed",
        "returncode": returncode,
        "elapsed_s": round(elapsed, 3),
        "dat_path": dat_path if dat_path.exists() else None,
        "frd_path": frd_path if frd_path.exists() else None,
        "solver": "calculix",
    }
