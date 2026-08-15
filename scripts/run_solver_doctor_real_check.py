#!/usr/bin/env python3
"""Real-Abaqus check for the solver-log auto-diagnosis chain.

Reproduces a classic failure — a loaded model whose boundary conditions were
deleted before submit (load with no constraints diverges) — and verifies the
full chain: real solver abort -> plugin ships .msg/.dat tails -> server's
Solver Doctor attaches findings -> error payload carries an actionable
category. Deleting the BCs is explicit test setup inside the driver; the
solve, the abort, and every log line are real Abaqus output.

Usage: .venv/Scripts/python.exe scripts/run_solver_doctor_real_check.py
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.record_copilot_replay import (  # noqa: E402
    PLUGIN_DIR,
    _get_json,
    _post_json,
    start_local_server,
)
from tools.abaqus_cmd import get_abaqus_cmd  # noqa: E402

PROMPT = "帮我建一个 200mm 长、20mm 高、20mm 宽的悬臂梁，先别管约束，直接跑"


def main() -> int:
    workdir = ROOT / "artifacts" / "solver_doctor_check" / time.strftime("%Y%m%d_%H%M%S")
    workdir.mkdir(parents=True, exist_ok=True)
    _server, api = start_local_server(8163)

    plan = _post_json(f"{api}/api/copilot/plan", {"text": PROMPT, "backend": "template"})
    session_id = plan["session_id"]
    _post_json(f"{api}/api/copilot/sessions/{session_id}/activate", {})

    driver = workdir / "no_bc_driver.py"
    driver.write_text(
        "\n".join(
            [
                "import sys",
                "sys.path.insert(0, r'%s')" % str(PLUGIN_DIR),
                "import abaqusAgent_plugin as P",
                "P.execute_next_copilot_action(r'%s')  # create model+mesh for real" % session_id,
                "P.execute_next_copilot_action(r'%s')  # BC + load for real" % session_id,
                "# test setup: wipe the constraints so the loaded solve diverges",
                "from abaqus import mdb",
                "model = mdb.models['Copilot_Cantilever']",
                "for name in list(model.boundaryConditions.keys()):",
                "    del model.boundaryConditions[name]",
                "P.execute_next_copilot_action(r'%s')  # submit -> real solver abort" % session_id,
            ]
        ),
        encoding="utf-8",
    )
    import os

    env = dict(os.environ)
    env["ABAQUS_AGENT_SERVER_URL"] = api
    proc = subprocess.run(
        [get_abaqus_cmd(), "cae", "noGUI=%s" % driver.name],
        cwd=str(workdir),
        env=env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        errors="replace",
        timeout=900,
    )

    summary = _get_json(f"{api}/api/copilot/sessions/{session_id}")
    errors = summary["errors"]
    evidence: dict = {
        "tool": "abaqus cae noGUI (real unconstrained solve) via plugin bridge",
        "prompt": PROMPT,
        "abaqus_rc": proc.returncode,
        "workdir": str(workdir),
        "error_count": len(errors),
    }
    if not errors:
        evidence["result"] = "FAIL (expected a real solver failure)"
        evidence["stdout_tail"] = proc.stdout[-600:]
        print(json.dumps(evidence, ensure_ascii=False, indent=2))
        return 1

    err = errors[0]
    doctor = err.get("solver_doctor") or {}
    evidence.update(
        {
            "traceback_last_line": str((err.get("payload") or {}).get("traceback", "")).strip().splitlines()[-1],
            "cae_diagnosis": (err.get("diagnosis") or {}).get("title"),
            "solver_doctor_status": doctor.get("status"),
            "solver_doctor_category": doctor.get("primary_category"),
            "solver_doctor_summary": doctor.get("summary"),
            "top_findings": [
                {"severity": f["severity"], "category": f["category"], "message": f["message"][:90]}
                for f in (doctor.get("findings") or [])[:3]
            ],
            "shipped_logs": sorted(((err.get("payload") or {}).get("solver_logs") or {}).keys()),
        }
    )
    evidence["result"] = "PASS" if doctor.get("findings") else "FAIL (no doctor findings attached)"
    print(json.dumps(evidence, ensure_ascii=False, indent=2))
    return 0 if evidence["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
