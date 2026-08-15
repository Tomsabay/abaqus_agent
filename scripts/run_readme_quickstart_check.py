"""Run the README's Quick Start exactly as written, and check its claims.

A README that documents a command nobody re-runs rots silently. Before this
existed, its first Quick Start command (`pytest tests/ -v`) failed on any fresh
clone.

Until 2026-08-15 this gate drove a CalculiX fallback end to end, because the
Quick Start's whole point was giving a visitor without a licence something to
run. There is no fallback now — the README says so in plain words — so what is
left to verify is that the one documented command still works on the one solver
this tool drives, and that the numbers it prints are the frozen baseline.

Run:  .venv\\Scripts\\python.exe scripts\\run_readme_quickstart_check.py
Needs Abaqus (or ABAQUS_AGENT_ABAQUS_CMD). Without it the documentation checks
still run and the gate reports what it could not measure.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
README = ROOT / "README.md"
EXPECTED = ROOT / "cases" / "cantilever" / "expected.json"


def _readme_quickstart() -> str:
    body = README.read_text(encoding="utf-8")
    start = body.index("## Quick Start")
    end = body.index("\n## ", start + 10)
    return body[start:end]


def _verdict(failures: list[str], solver: str) -> int:
    """Print the JSON verdict scripts/run_all_real_checks.py reads.

    It has to be the last parseable JSON object on stdout, and this gate
    prints a KPI payload of its own earlier in the run.
    """
    print(json.dumps({"schema": "readme_quickstart_check/1",
                      "result": "FAIL" if failures else "PASS",
                      "solver": solver, "failures": failures},
                     ensure_ascii=False))
    return 1 if failures else 0


def main() -> int:
    failures: list[str] = []
    section = _readme_quickstart()

    # 1. The section has to tell a visitor what to run and how to point at a
    #    solver that is not on PATH.
    for marker in ("ABAQUS_AGENT_ABAQUS_CMD",
                   "agent/orchestrator.py cases/cantilever/spec.yaml"):
        if marker not in section:
            failures.append("Quick Start no longer mentions %r" % marker)

    # 2. It must not resurrect the command that fails on a fresh clone.
    if "pytest tests/ -v" in section:
        failures.append("`pytest tests/ -v` needs gitignored run dirs; use `pytest -q`")

    # 3. It must not promise a second solver again. The README explains the
    #    removal in prose, so a bare mention is fine; an env var or an install
    #    instruction is a broken promise.
    for stale in ("ABAQUS_AGENT_CCX_EXE", "calculix.de", "ccx.exe"):
        if stale in section:
            failures.append("Quick Start still points at a removed backend: %r" % stale)

    sys.path.insert(0, str(ROOT))
    from core.helpers import check_abaqus

    if not check_abaqus():
        print("SKIP: no Abaqus found (set ABAQUS_AGENT_ABAQUS_CMD)")
        if failures:
            print("\nRESULT: FAIL")
            for f in failures:
                print("  - %s" % f)
        else:
            print("RESULT: PASS (documentation checks only)")
        return _verdict(failures, solver="none, documentation checks only")

    # 4. Run the documented command for real, into a scratch run root so no
    #    archived evidence is touched.
    run_root = Path(tempfile.mkdtemp(prefix="readme_quickstart_"))
    env = {**os.environ, "ABAQUS_AGENT_RUN_ROOT": str(run_root)}
    cmd = [sys.executable, "agent/orchestrator.py",
           "cases/cantilever/spec.yaml",
           "cases/cantilever/expected.json",
           "cases/cantilever/runner.json"]
    proc = subprocess.run(cmd, cwd=str(ROOT), env=env, capture_output=True,
                          text=True, encoding="utf-8", errors="replace",
                          stdin=subprocess.DEVNULL, timeout=1800)
    print("exit=%d" % proc.returncode)
    if proc.returncode != 0:
        failures.append("the documented command exited %d" % proc.returncode)
        print(proc.stdout[-2500:])

    baseline = json.loads(EXPECTED.read_text(encoding="utf-8"))["kpis"]
    results = sorted(run_root.glob("*/result.json"))
    if not results:
        failures.append("no result.json produced")
    else:
        data = json.loads(results[0].read_text(encoding="utf-8"))
        kpis = data.get("kpis", {})
        print(json.dumps({"status": data.get("status"), "kpis": kpis},
                         ensure_ascii=False, indent=1))

        # Against the frozen baseline, to its own declared tolerance -- not a
        # number retyped into this file, which is how a gate ends up asserting
        # the docs against the docs.
        for name, spec in baseline.items():
            got = kpis.get(name)
            want = spec["value"]
            if got is None:
                failures.append("%s was not produced" % name)
                continue
            if abs(got - want) > abs(want) * spec["rtol"] + spec["atol"]:
                failures.append("%s %r is outside the frozen baseline %r"
                                % (name, got, want))

        regression = data.get("regression", {})
        if regression.get("passed") is not True:
            failures.append("regression did not pass: %r" % regression.get("passed"))

    shutil.rmtree(run_root, ignore_errors=True)

    if failures:
        print("\nRESULT: FAIL")
        for f in failures:
            print("  - %s" % f)
    else:
        print("\nRESULT: PASS")
    return _verdict(failures, solver="abaqus")


if __name__ == "__main__":
    sys.exit(main())
