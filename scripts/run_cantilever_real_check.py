#!/usr/bin/env python3
"""Real-Abaqus check for the cantilever tip-load scenario.

Runs the full Copilot chain (template plan -> plugin bridge -> real solve)
and compares the dial-gauge tip deflection (bottom node at the free end)
against Euler-Bernoulli theory delta = PL^3 / 3EI. The coarse demo mesh and
shear deformation push the FE value above the slender-beam formula, so the
gate accepts 0.8..1.4 of theory and reports the actual ratio.

Usage: .venv/Scripts/python.exe scripts/run_cantilever_real_check.py
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

PROMPT = "帮我建一个 200mm 长、20mm 高、20mm 宽的悬臂梁，材料钢，左端固定，右端向下 100N，运行并提取最大位移和最大 Mises 应力"
JOB_NAME = "Copilot_Cantilever_Job"

LENGTH, HEIGHT, WIDTH, FORCE, E_MOD = 200.0, 20.0, 20.0, 100.0, 210000.0


def main() -> int:
    workdir = ROOT / "artifacts" / "cantilever_check" / time.strftime("%Y%m%d_%H%M%S")
    workdir.mkdir(parents=True, exist_ok=True)
    _server, api = start_local_server(8171)

    plan = _post_json(f"{api}/api/copilot/plan", {"text": PROMPT, "backend": "template"})
    assert plan["model_type"] == "cantilever", plan["model_type"]
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
    theory = FORCE * LENGTH**3 / (3.0 * E_MOD * inertia)
    measured = float(kpis["tip_deflection"])
    ratio = measured / theory

    evidence.update(
        {
            "kpis": kpis,
            "theory_tip_mm": round(theory, 6),
            "measured_tip_mm": round(measured, 6),
            "measured_over_theory": round(ratio, 3),
            "result": "PASS" if 0.8 <= ratio <= 1.4 and kpis["status"] == "COMPLETED" else "FAIL",
        }
    )
    print(json.dumps(evidence, ensure_ascii=False, indent=2))
    return 0 if evidence["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
