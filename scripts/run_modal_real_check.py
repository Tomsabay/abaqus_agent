#!/usr/bin/env python3
"""Real-Abaqus check for the cantilever modal scenario.

Runs the full Copilot chain (template plan -> plugin bridge -> real Lanczos
solve) and compares the first natural frequency against the Euler-Bernoulli
cantilever solution f1 = (1.875104^2 / 2*pi) * sqrt(EI / (rho*A*L^4)).
A stubby L/h=10 solid beam on a coarse mesh deviates a few percent
(shear/rotary inertia), so the gate accepts 0.85..1.15 of theory.

Usage: .venv/Scripts/python.exe scripts/run_modal_real_check.py
"""

from __future__ import annotations

import json
import math
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

PROMPT = "帮我做一个 200mm 长、20mm 高、20mm 宽悬臂梁的模态分析，看前 5 阶固有频率"
JOB_NAME = "Copilot_Modal_Job"

LENGTH, HEIGHT, WIDTH = 200.0, 20.0, 20.0
E_MOD, RHO = 210000.0, 7.85e-9  # MPa, tonne/mm^3


def cantilever_f1_hz() -> float:
    inertia = WIDTH * HEIGHT**3 / 12.0
    area = WIDTH * HEIGHT
    return (1.875104**2 / (2.0 * math.pi)) * math.sqrt(
        E_MOD * inertia / (RHO * area * LENGTH**4)
    )


def main() -> int:
    workdir = ROOT / "artifacts" / "modal_check" / time.strftime("%Y%m%d_%H%M%S")
    workdir.mkdir(parents=True, exist_ok=True)
    _server, api = start_local_server(8169)

    plan = _post_json(f"{api}/api/copilot/plan", {"text": PROMPT, "backend": "template"})
    assert plan["model_type"] == "cantilever_modal", plan["model_type"]
    session_id = plan["session_id"]
    _post_json(f"{api}/api/copilot/sessions/{session_id}/activate", {})

    proc = run_plugin_driver(session_id, api, workdir)
    summary = _get_json(f"{api}/api/copilot/sessions/{session_id}")

    result_file = workdir / f"{JOB_NAME}_copilot_result.json"
    evidence: dict = {
        "tool": "abaqus cae noGUI (real Lanczos solve) via plugin bridge",
        "prompt": PROMPT,
        "session": {
            "completed": summary["completed_count"],
            "actions": summary["action_count"],
            "errors": [
                {
                    "diagnosis": (e.get("diagnosis") or {}).get("title"),
                    "last_line": str((e.get("payload") or {}).get("traceback", "")).strip().splitlines()[-1:],
                }
                for e in summary["errors"]
            ],
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
    theory = cantilever_f1_hz()
    measured = float(kpis["first_frequency_hz"])
    ratio = measured / theory
    evidence.update(
        {
            "kpis": kpis,
            "theory_f1_hz": round(theory, 2),
            "measured_f1_hz": round(measured, 2),
            "measured_over_theory": round(ratio, 3),
            "result": "PASS" if 0.85 <= ratio <= 1.15 and len(kpis["natural_frequencies_hz"]) >= 3 else "FAIL",
        }
    )
    print(json.dumps(evidence, ensure_ascii=False, indent=2))
    return 0 if evidence["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
