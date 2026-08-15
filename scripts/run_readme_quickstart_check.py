"""Run the README's Quick Start exactly as written, and check its claims.

A README that documents a command nobody re-runs rots silently. Before this
existed, its first Quick Start command (`pytest tests/ -v`) failed on any
fresh clone, it never mentioned CalculiX once, and the only documented way to
solve a case said "on a machine with Abaqus installed" — leaving every visitor
without a licence with nothing to try.

This drives the CalculiX path end to end on a real solver and asserts the
numbers the README prints.

Run:  .venv\\Scripts\\python.exe scripts\\run_readme_quickstart_check.py
Needs ABAQUS_AGENT_CCX_EXE (or ccx on PATH).
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

# What the README's table claims, and the tolerance each is claimed to.
CLAIM_U_TIP = -1.903958e-3      # "agrees to seven significant figures"
CLAIM_MISES_CCX = 0.6109        # explicitly NOT comparable to Abaqus


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

    # 1. The section has to actually tell a licence-less visitor what to do.
    for marker in ("CalculiX", "ABAQUS_AGENT_CCX_EXE",
                   "agent/orchestrator.py cases/cantilever/spec.yaml"):
        if marker not in section:
            failures.append("Quick Start no longer mentions %r" % marker)

    # 2. It must not resurrect the command that fails on a fresh clone.
    if "pytest tests/ -v" in section:
        failures.append("`pytest tests/ -v` needs gitignored run dirs; use `pytest -q`")

    ccx = os.environ.get("ABAQUS_AGENT_CCX_EXE") or shutil.which("ccx")
    if not ccx or not Path(ccx).is_file():
        print("SKIP: no CalculiX found (set ABAQUS_AGENT_CCX_EXE)")
        if failures:
            print("\nRESULT: FAIL")
            for f in failures:
                print("  - %s" % f)
        else:
            print("RESULT: PASS (documentation checks only)")
        return _verdict(failures, solver="none, documentation checks only")

    # 3. Run the documented command for real, into a scratch run root so no
    #    archived evidence is touched.
    run_root = Path(tempfile.mkdtemp(prefix="readme_quickstart_"))
    env = {
        **os.environ,
        "ABAQUS_AGENT_CCX_EXE": ccx,
        "ABAQUS_AGENT_SOLVER_BACKEND": "calculix",
        "ABAQUS_AGENT_RUN_ROOT": str(run_root),
    }
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

    results = sorted(run_root.glob("*/result.json"))
    if not results:
        failures.append("no result.json produced")
    else:
        data = json.loads(results[0].read_text(encoding="utf-8"))
        kpis = data.get("kpis", {})
        prov = data.get("kpi_provenance", {})
        print(json.dumps({"status": data.get("status"), "kpis": kpis},
                         ensure_ascii=False, indent=1))

        u = kpis.get("U_tip")
        if u is None or abs(u - CLAIM_U_TIP) > abs(CLAIM_U_TIP) * 1e-6:
            failures.append("U_tip %r does not match the documented %r"
                            % (u, CLAIM_U_TIP))
        m = kpis.get("MISES_MAX")
        if m is None or abs(m - CLAIM_MISES_CCX) > 0.001:
            failures.append("MISES_MAX %r does not match the documented %r"
                            % (m, CLAIM_MISES_CCX))

        # The README's whole point in that table: the stress number is
        # produced but marked not-Abaqus-equivalent.
        mises_prov = prov.get("MISES_MAX", {})
        if mises_prov.get("abaqus_equivalent") is not False:
            failures.append("MISES_MAX is not tagged as non-equivalent: %r"
                            % mises_prov)
        if (prov.get("U_tip", {}) or {}).get("abaqus_equivalent") is not True:
            failures.append("U_tip should be tagged Abaqus-equivalent")

        regression = data.get("regression", {})
        if regression.get("passed") is not True:
            failures.append("regression did not pass: %r" % regression.get("passed"))

    shutil.rmtree(run_root, ignore_errors=True)

    # 4. The numbers printed in the README table must be the ones just measured.
    table = [ln for ln in section.splitlines() if ln.startswith("| `U_tip`")]
    if not table:
        failures.append("the comparison table lost its U_tip row")
    elif "1.903958e-3" not in table[0].replace("−", "-"):
        failures.append("the table's U_tip no longer matches: %s" % table[0])

    if failures:
        print("\nRESULT: FAIL")
        for f in failures:
            print("  - %s" % f)
    else:
        print("\nRESULT: PASS")
    return _verdict(failures, solver="calculix")


if __name__ == "__main__":
    sys.exit(main())
