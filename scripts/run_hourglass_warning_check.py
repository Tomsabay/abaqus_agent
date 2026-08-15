#!/usr/bin/env python3
"""Real-solver check that a hourglass-prone element WARNS and is still solved.

#72. The trigger is one string in `mesh.element`, and the answer it produces is
not "a bit soft" -- it is the wrong order of magnitude, from a job that reports
COMPLETED. This gate solves the two-element-code experiment on every run so the
warning can never drift away from the phenomenon it claims to describe.

THE EXPERIMENT. A 10 x 10 x 100 bar built from this dialect, encastre at
z=min, a uniform pressure on the x=max side face, so the bar bends. The only
difference between the two specs is the element code, and the mesh is seeded so
there is ONE element through the 10 mm thickness -- which is the condition, not
the element on its own:

    seed 10 (1 layer)   C3D8I -0.7126152   C3D8R -65.66674    ~92x
    seed  5 (2 layers)  C3D8I -0.7104333   C3D8R  -0.9517219  ~1.34x

Read the C3D8I column first. It moves 0.3% between the two meshes, so it is
already converged: the C3D8R number is not a coarse mesh, it is an element with
no bending stiffness when there is one layer of it. This reproduced the 90.5x
originally measured on an entirely different model (an imported orphan mesh
under a tip force), which is what turned one observation into a rule.

WHAT IS ASSERTED, AND THE DIRECTION THAT IS EASY TO FORGET.
  * C3D8R warns, names the spec key, and the run still reports COMPLETED --
    #72 was decided as "warn and put it in the report", not "refuse". An item
    fails if the run is refused or failed.
  * C3D8I does NOT warn. A warning on every element would be a warning on none.
  * The archived report carries it. The live page is not where a result goes
    when it is sent to somebody who was not in the room.
  * The gap between the two answers is still enormous. If a future Abaqus, or a
    change in what this generator emits, quietly fixes the hourglassing, the
    warning is now describing something that no longer happens and this fails
    so that gets noticed rather than shipped.

Two solves, both small. Exit 0 = every item passed, or no Abaqus (skipped).
Nothing is written inside cases/.
"""

from __future__ import annotations

import copy
import json
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.element_risk import spec_hourglass_findings  # noqa: E402
from core.helpers import check_abaqus  # noqa: E402
from reporting.export import build_offline_run_report  # noqa: E402
from tools.abaqus_cmd import detect_abaqus_release  # noqa: E402

OUT_DIR = ROOT / "artifacts" / "hourglass_warning_check"

# One element through the 10 mm thickness. The whole effect lives here: at
# seed 5 the same pair is 1.34x apart, which would make a weak gate.
SEED = 10.0
# The ratio measured on this rig was 92.1. A floor of 10 leaves room for a
# different machine or release without letting a silent fix through.
MIN_RATIO = 10.0


def _spec(element: str) -> dict:
    return {
        "meta": {"abaqus_release": "2021", "model_name": "Hg" + element,
                 "units": "mm_MPa_t",
                 "description": "cantilever bar, %s, one element through the "
                                "thickness" % element,
                 "missing_questions": []},
        "material": {"name": "Steel", "E": 210000.0, "nu": 0.3},
        "parts": [{
            "name": "Bar",
            "features": [
                {"op": "sketch", "id": "outline", "plane": "XY",
                 "profile": {"rect": {"corner1": [0.0, 0.0],
                                      "corner2": [10.0, 10.0]}}},
                {"op": "extrude", "sketch": "outline", "depth": 100.0},
            ],
            "section": {"type": "solid", "material": "Steel"},
            "mesh": {"seed": SEED, "element": element},
        }],
        "assembly": {"instances": [{"name": "B", "part": "Bar",
                                    "translate": [0.0, 0.0, 0.0]}]},
        "steps": [{
            "name": "Bend", "type": "Static",
            "bcs": [{"name": "Fix", "region": "B:face@z=min",
                     "type": "encastre"}],
            "loads": [{"name": "Side", "region": "B:face@x=max",
                       "type": "pressure", "value": 1.0}],
        }],
        "outputs": {"kpis": [{"name": "U_TIP", "type": "field_min",
                              "location": "whole_model", "component": "U1"}]},
    }


def _solve(element: str) -> dict:
    from agent.orchestrator import build_orchestrator

    work = OUT_DIR / element.lower()
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True, exist_ok=True)
    result = build_orchestrator(spec_dict=copy.deepcopy(_spec(element)),
                               workdir=work, expected_path=None,
                               runner_cfg=None).run()
    return {"result": result, "workdir": work}


def _skipped(name: str, reason: str) -> dict:
    return {"id": name, "status": "skipped", "note": reason}


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    started = time.time()
    names = ("1_the_risky_element_warns_and_names_the_spec_key",
             "2_the_run_is_still_completed",
             "3_the_safe_element_does_not_warn",
             "4_the_archived_report_carries_it",
             "5_the_two_answers_are_still_orders_of_magnitude_apart")

    release = None
    if not check_abaqus():
        items = [_skipped(n, "Abaqus not found (set ABAQUS_AGENT_ABAQUS_CMD "
                             "or put abaqus.bat on PATH)") for n in names]
        payload = {"schema": "gate/1", "overall": "skipped", "items": items,
                   "seconds": round(time.time() - started, 1)}
        for item in items:
            print("[%-7s] %s — %s" % (item["status"], item["id"], item["note"]))
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0

    release = detect_abaqus_release()
    risky = _solve("C3D8R")
    safe = _solve("C3D8I")
    r_res, s_res = risky["result"], safe["result"]
    r_risks = r_res.get("mesh_risks", [])
    s_risks = s_res.get("mesh_risks", [])
    r_u = r_res.get("kpis", {}).get("U_TIP")
    s_u = s_res.get("kpis", {}).get("U_TIP")

    items = []
    items.append({
        "id": names[0],
        "status": "pass" if ([f["element"] for f in r_risks] == ["C3D8R"]
                             and r_risks
                             and r_risks[0]["where"] == "parts[Bar].mesh.element")
                  else "fail",
        "note": "mesh_risks=%s" % [(f.get("where"), f.get("element"))
                                   for f in r_risks],
    })
    items.append({
        # #72 as decided: warn, do not refuse. A gate that only checked for the
        # warning would pass a build that started refusing C3D8R outright.
        "id": names[1],
        "status": "pass" if r_res.get("status") == "COMPLETED" else "fail",
        "note": "status=%s" % r_res.get("status"),
    })
    items.append({
        "id": names[2],
        "status": "pass" if not s_risks and not spec_hourglass_findings(
            _spec("C3D8I")) else "fail",
        "note": "C3D8I mesh_risks=%s" % s_risks,
    })

    report_ok, report_note = False, "report not rendered"
    try:
        report = build_offline_run_report(risky["workdir"], template="standard")
        text = report["markdown"]
        report_ok = ("## Known Limitations" in text and "C3D8R" in text
                     and "Known Limitations" in report["html"])
        report_note = "markdown carries the section: %s" % (
            "yes" if report_ok else text[-200:])
    except Exception as exc:                     # noqa: BLE001
        report_note = "%s: %s" % (type(exc).__name__, exc)
    items.append({"id": names[3],
                  "status": "pass" if report_ok else "fail",
                  "note": report_note})

    ratio = None
    if isinstance(r_u, (int, float)) and isinstance(s_u, (int, float)) and s_u:
        ratio = abs(r_u) / abs(s_u)
    items.append({
        "id": names[4],
        "status": "pass" if (ratio is not None and ratio >= MIN_RATIO)
                  else "fail",
        "note": "C3D8R %s vs C3D8I %s -> ratio %s (floor %s). A ratio that "
                "collapses means the warning now describes something that no "
                "longer happens." % (r_u, s_u,
                                     round(ratio, 2) if ratio else ratio,
                                     MIN_RATIO),
        "measured": r_u, "reference": s_u,
    })

    failed = [i for i in items if i["status"] != "pass"]
    payload = {"schema": "gate/1",
               "overall": "fail" if failed else "pass",
               "abaqus_release": release,
               "items": items,
               "seconds": round(time.time() - started, 1)}
    (OUT_DIR / "report.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    for item in items:
        print("[%-7s] %s — %s" % (item["status"], item["id"],
                                  str(item["note"])[:170]))
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
