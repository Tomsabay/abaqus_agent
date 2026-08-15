#!/usr/bin/env python3
"""Real-Abaqus check for the plate-with-hole (stress concentration) scenario.

Runs the full Copilot chain (template plan -> plugin bridge -> real solve)
and compares the stress concentration factor Kt = max_mises / applied
tension against the classic Howland result: for hole d / plate width W = 0.2
the gross-section Kt is about 3.1 (infinite plate: 3.0). Coarse demo meshes
under-predict the peak, so the gate accepts 2.3..3.8 and reports the actual.

Usage: .venv/Scripts/python.exe scripts/run_plate_hole_real_check.py
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

PROMPT = "做一个 100mm 长、50mm 宽、5mm 厚的开孔板，孔径 10mm，右端拉 100MPa，看孔边应力集中"
JOB_NAME = "Copilot_PlateHole_Job"
TENSION_MPA = 100.0
KT_THEORY = 3.1  # Howland, d/W = 0.2, gross section


def main() -> int:
    workdir = ROOT / "artifacts" / "plate_hole_check" / time.strftime("%Y%m%d_%H%M%S")
    workdir.mkdir(parents=True, exist_ok=True)
    _server, api = start_local_server(8167)

    plan = _post_json(f"{api}/api/copilot/plan", {"text": PROMPT, "backend": "template"})
    assert plan["model_type"] == "plate_with_hole", plan["model_type"]
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
            "errors": [
                {
                    "message": e.get("message"),
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
    kt = float(kpis["max_mises"]) / TENSION_MPA
    evidence.update(
        {
            "kpis": kpis,
            "kt_theory_gross": KT_THEORY,
            "kt_measured": round(kt, 3),
            "kt_ratio_vs_theory": round(kt / KT_THEORY, 3),
            "result": "PASS" if 2.3 <= kt <= 3.8 and kpis["status"] == "COMPLETED" else "FAIL",
        }
    )
    print(json.dumps(evidence, ensure_ascii=False, indent=2))
    return 0 if evidence["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
