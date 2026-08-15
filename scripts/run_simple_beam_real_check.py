#!/usr/bin/env python3
"""Real-Abaqus check for the simply-supported beam scenario.

Runs the full Copilot chain (template plan -> plugin bridge -> real solve)
and compares the mid-span displacement against beam theory PL^3/48EI.
Coarse C3D8R meshes deviate from thin-beam theory, so this is an
order-of-magnitude sanity gate (0.5x..1.5x), with the actual ratio reported.

Usage: .venv/Scripts/python.exe scripts/run_simple_beam_real_check.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.record_copilot_replay import (  # noqa: E402
    _get_json,
    _post_json,
    run_plugin_driver,
    start_local_server,
)

PROMPT = "帮我做一个 200mm 长、20mm 高、20mm 宽 的简支梁，跨中往下压 500N，看跨中挠度和最大应力"
JOB_NAME = "Copilot_SimpleBeam_Job"

LENGTH, HEIGHT, WIDTH, FORCE, E_MOD = 200.0, 20.0, 20.0, 500.0, 210000.0


def main() -> int:
    workdir = ROOT / "artifacts" / "simple_beam_check" / time.strftime("%Y%m%d_%H%M%S")
    workdir.mkdir(parents=True, exist_ok=True)
    _server, api = start_local_server(8161)

    plan = _post_json(f"{api}/api/copilot/plan", {"text": PROMPT, "backend": "template"})
    assert plan["model_type"] == "simply_supported_beam", plan["model_type"]
    session_id = plan["session_id"]
    _post_json(f"{api}/api/copilot/sessions/{session_id}/activate", {})

    proc = run_plugin_driver(session_id, api, workdir)
    summary = _get_json(f"{api}/api/copilot/sessions/{session_id}")

    result_file = workdir / f"{JOB_NAME}_copilot_result.json"
    evidence: dict = {
        "tool": "abaqus cae noGUI (real solve) via plugin bridge",
        "prompt": PROMPT,
        "session": {
            "completed": summary["completed_count"],
            "actions": summary["action_count"],
            "errors": [e.get("message") for e in summary["errors"]],
        },
        "abaqus_rc": proc.returncode,
        "workdir": str(workdir),
    }
    if summary["errors"] or not result_file.exists():
        evidence["result"] = "FAIL"
        evidence["stdout_tail"] = proc.stdout[-800:]
        print(json.dumps(evidence, ensure_ascii=False, indent=2))
        return 1

    kpis = json.loads(result_file.read_text(encoding="utf-8"))
    inertia = WIDTH * HEIGHT**3 / 12.0
    theory = FORCE * LENGTH**3 / (48.0 * E_MOD * inertia)
    # compare the dial-gauge position (bottom mid-span node), not the global max:
    # the global max sits under the point load and includes local indentation
    measured = float(kpis["midspan_deflection"])
    ratio = measured / theory

    workspace_kpis = summary.get("kpis") or {}
    evidence.update(
        {
            "kpis": kpis,
            # the plugin must have shipped the same KPIs back to the workspace
            # (tolerance: py2 json serializes floats at lower precision than py3)
            "kpis_in_workspace": bool(workspace_kpis)
            and abs(float(workspace_kpis.get("max_mises") or 0.0) - float(kpis.get("max_mises") or 0.0)) < 1e-6,
            "theory_midspan_mm": round(theory, 6),
            "measured_midspan_mm": round(measured, 6),
            "measured_over_theory": round(ratio, 3),
            "result": (
                "PASS"
                if 0.5 <= ratio <= 1.5
                and kpis["status"] == "COMPLETED"
                and bool(workspace_kpis)
                else "FAIL"
            ),
        }
    )
    print(json.dumps(evidence, ensure_ascii=False, indent=2))
    return 0 if evidence["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
