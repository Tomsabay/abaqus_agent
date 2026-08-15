#!/usr/bin/env python3
"""Real-solver check for the connector layer.

Connectors were the one family of "joining instances" the spec could not
express at any price: springs, joints, hinges, bolts modelled as connectors.
Unlike a tie, a connector is not one call -- it is a wire on the assembly, a
ConnectorSection on the model, an elasticity built by a module the generated
script did not import, and a SectionAssignment on the assembly, in that order
and no other.

Two blocks 20x20x10, 20 mm apart, joined at their four corners by axial springs
of k = 25 N/mm each. The lower block is built in; the upper one keeps only its
axial freedom. Pull it with 1000 N and it should travel exactly F/k = 10.000 mm,
because a spring in series with two very stiff blocks is a spring.

  1. `connector_spring_travels_exactly_f_over_k`
  2. `connector_stiffness_sweep_is_linear` -- four stiffnesses, measured
     against F/k each time. The chart is the evidence.
  3. `connector_refuses_a_wire_with_no_section`
  4. `connector_unassigned_wire_solves_to_the_wrong_answer` -- the same model
     with the check off: it COMPLETES, 33% wrong, no error, no warning
  5. `connector_asserts_the_wire_count`
  6. `connector_refuses_a_vertex_that_is_not_there`
  7. `connector_elasticity_comes_from_a_module_the_deck_now_imports`
  8. `connector_section_must_exist_before_it_is_assigned`

Exit codes: 0 = nothing failed (no Abaqus => "skipped", still 0);
            1 = at least one item ran and failed.
"""

from __future__ import annotations

import argparse
import copy
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.helpers import check_abaqus  # noqa: E402
from runner import (
    arg_forms,
    build_v2,  # noqa: E402
)
from tools.abaqus_cmd import detect_abaqus_release, get_abaqus_cmd  # noqa: E402

SIDE, THICK, SPAN = 20.0, 10.0, 20.0
K_EACH = 25.0
FORCE = 1000.0
CORNERS = ((0.0, 0.0), (SIDE, 0.0), (SIDE, SIDE), (0.0, SIDE))
SWEEP = (10.0, 25.0, 50.0, 200.0)

# The blocks are not rigid, so the answer is F/k plus their own stretch. Two
# 10 mm blocks of 400 mm^2 at 210000 MPa contribute 1000*20/(400*210000) =
# 2.4e-4 mm, five orders below the spring travel -- hence a tolerance well
# inside 1% rather than an exact equality.
TOLERANCE = 0.01


def _wire_ends(x: float, y: float):
    return ([x, y, THICK], [x, y, THICK + SPAN])


def _spec(k_each: float = K_EACH, corners: int = 4, assign: int | None = None,
          wires_expect=None, bad_vertex: bool = False,
          skip_section: bool = False) -> dict:
    """The two-block spring rig.

    `corners` is how many springs are built; `assign` how many of those carry a
    section. corners=3 is a rig with a corner left bare -- physically the same
    thing as forgetting one assignment, and it passes the check honestly, which
    is what lets it be solved.
    """
    if assign is None:
        assign = corners
    setup = []
    if not skip_section:
        setup = [
            {"call": "ConnectorSection", "name": {"literal": "Spring"},
             "translationalType": "AXIAL", "as": "spring"},
            {"call": "setValues", "target": {"ref": "spring"},
             "behaviorOptions": [
                 {"new": "connectorBehavior.ConnectorElasticity",
                  "behavior": "LINEAR", "components": [1],
                  "table": [[float(k_each)]]}]},
        ]

    operations = []
    for i, (x, y) in enumerate(CORNERS[:corners]):
        low, high = _wire_ends(x, y)
        if bad_vertex and i == 0:
            # 3 mm above the real corner: there is no vertex there.
            low = [x, y, THICK + 3.0]
        operations.append({
            "call": "WirePolyLine",
            "points": [[{"vertex": {"instance": "Fixed", "at": low}},
                        {"vertex": {"instance": "Free", "at": high}}]],
            "mergeType": "IMPRINT", "meshable": "OFF"})
    for i, (x, y) in enumerate(CORNERS[:corners]):
        low, high = _wire_ends(x, y)
        operations.append({
            "call": "Set", "name": {"literal": "WIRE%d" % i},
            "edges": {"wire_at": [low, high]}, "as": "w%d" % i})
        if i < assign:
            operations.append({
                "call": "SectionAssignment", "region": {"ref": "w%d" % i},
                "sectionName": {"literal": "Spring"}})

    expect = {"instances": 2}
    if wires_expect is not None:
        expect["wires"] = wires_expect

    spec = {
        "meta": {"abaqus_release": "2021", "model_name": "GenericConnCheck",
                 "units": "mm_MPa_t"},
        "material": {"name": "Steel", "E": 210000.0, "nu": 0.3},
        "parts": [{
            "name": "Blk",
            "features": [
                {"op": "sketch", "id": "outline", "plane": "XY",
                 "profile": {"rect": {"corner1": [0.0, 0.0],
                                      "corner2": [SIDE, SIDE]}}},
                {"op": "extrude", "sketch": "outline", "depth": THICK},
            ],
            "section": {"type": "solid", "material": "Steel"},
            "mesh": {"seed": 10.0, "element": "C3D8I"},
        }],
        "assembly": {
            "instances": [
                {"name": "Fixed", "part": "Blk", "translate": [0.0, 0.0, 0.0]},
                {"name": "Free", "part": "Blk",
                 "translate": [0.0, 0.0, THICK + SPAN]},
            ],
            "operations": operations,
            "expect": expect,
        },
        "steps": [{
            "name": "Pull", "type": "Static",
            "bcs": [
                {"name": "Fix", "type": "encastre",
                 "region": "Fixed:face@z=min", "expect": "=1"},
                {"name": "Guide", "type": "displacement",
                 "region": "Free:cell@all", "expect": "=1",
                 "u1": 0.0, "u2": 0.0},
            ],
            "loads": [
                # Pressure acts INTO the face, so a negative magnitude pulls
                # the free block away and stretches the springs.
                {"name": "Pull", "type": "pressure", "region": "Free:face@z=max",
                 "expect": "=1", "value": -FORCE / (SIDE * SIDE)},
            ],
        }],
        "outputs": {"kpis": [
            {"name": "U_PULL", "type": "field_max", "location": "whole_model",
             "component": "U3"}]},
    }
    if setup:
        spec["model_setup"] = setup
    return spec


# --- plumbing --------------------------------------------------------------

def _build(work: Path, spec: dict) -> dict:
    work = work.resolve()
    work.mkdir(parents=True, exist_ok=True)
    log_path = work / "selectors.log"
    if log_path.exists():
        log_path.unlink()
    try:
        text = build_v2.generate_script(spec)
    except Exception as exc:
        return {"rc": None, "built": False, "log": "",
                "error": "%s: %s" % (type(exc).__name__, exc)}
    (work / "build_model_script.py").write_text(text, encoding="utf-8")
    proc = subprocess.run(
        [get_abaqus_cmd(), "cae", "noGUI=build_model_script.py", "--",
         str(work), "spec"],
        cwd=str(work), capture_output=True, text=True,
        errors="replace", encoding="utf-8", stdin=subprocess.DEVNULL,
        timeout=1800)
    log = (log_path.read_text(encoding="utf-8", errors="replace")
           if log_path.exists() else "")
    return {"rc": proc.returncode, "built": True, "log": log,
            "error": (proc.stderr or "")[-4000:]}


def _solve(spec: dict, work: Path) -> dict:
    from agent.orchestrator import build_orchestrator
    work.mkdir(parents=True, exist_ok=True)
    orch = build_orchestrator(spec_dict=copy.deepcopy(spec), workdir=work,
                              expected_path=None, runner_cfg=None)
    return orch.run()


def _kpi(result: dict, name: str):
    value = result.get("kpis", {}).get(name)
    if isinstance(value, dict):
        return value.get("value")
    return value


def _evidence(out: dict) -> str:
    return "\n".join([out.get("error") or "", out.get("log") or ""])


def _line(out: dict, needle: str) -> str:
    for line in out["log"].splitlines():
        if needle in line:
            return line.strip()
    return ""


def _skipped(item_id: str, reason: str) -> dict:
    return {"id": item_id, "status": "skipped", "reason": reason}


# --- items -----------------------------------------------------------------

def check_exact(work: Path) -> dict:
    result = _solve(_spec(), work / "spring_exact")
    travel = _kpi(result, "U_PULL")
    want = FORCE / (4 * K_EACH)
    problems = []
    if result.get("status") != "COMPLETED":
        problems.append("orchestrator status %s: %s"
                        % (result.get("status"), result.get("error")))
    elif travel is None:
        problems.append("no U_PULL in the result")
    elif abs(travel - want) / want > TOLERANCE:
        problems.append("travelled %r, F/k says %r" % (travel, want))
    return {
        "id": "connector_spring_travels_exactly_f_over_k",
        "status": "pass" if not problems else "fail",
        "k_total": 4 * K_EACH, "force": FORCE,
        "predicted": want, "measured": travel,
        "relative_deviation": (None if travel is None
                               else abs(travel - want) / want),
        "note": "four axial springs at the corners, built as WirePolyLine on "
                "the assembly with ConnectorSection on the model and the "
                "elasticity from connectorBehavior. Every one of those is "
                "named by the spec.",
        "problems": problems,
    }


def check_sweep(work: Path) -> dict:
    rows = []
    problems = []
    for k in SWEEP:
        result = _solve(_spec(k_each=k), work / ("sweep_k%g" % k))
        travel = _kpi(result, "U_PULL")
        want = FORCE / (4 * k)
        row = {"k_each": k, "k_total": 4 * k, "predicted": want,
               "measured": travel, "status": result.get("status")}
        if result.get("status") != "COMPLETED" or travel is None:
            problems.append("k=%g did not solve (%s)" % (k, result.get("status")))
        else:
            row["relative_deviation"] = abs(travel - want) / want
            if row["relative_deviation"] > TOLERANCE:
                problems.append("k=%g: measured %r against F/k = %r"
                                % (k, travel, want))
        rows.append(row)
    return {
        "id": "connector_stiffness_sweep_is_linear",
        "status": "pass" if not problems else "fail",
        "force": FORCE,
        "rows": rows,
        "note": "the same deck at four stiffnesses. If the connector were not "
                "carrying the load the travel would not track F/k at all.",
        "problems": problems,
    }


def check_refuses_unassigned(work: Path) -> dict:
    out = _build(work / "wire_unassigned", _spec(assign=3))  # 4 wires, 3 assigned
    evidence = _evidence(out)
    problems = []
    if "WIRE_UNASSIGNED" not in evidence:
        problems.append("a wire with no section was accepted: %s"
                        % evidence[-600:])
    return {
        "id": "connector_refuses_a_wire_with_no_section",
        "status": "pass" if not problems else "fail",
        "wires": 4, "assigned": 3,
        "log_line": _line(out, "WIRE_UNASSIGNED"),
        "note": "checked in CAE from a.sectionAssignments against a.edges, "
                "which holds only wires (measured: 4 wires there while the "
                "instance carried 12 edges of its own).",
        "problems": problems,
    }


def check_unassigned_solves_wrong(work: Path) -> dict:
    """Why the item above is load-bearing.

    The check is bypassed by declaring three wires, so the fourth is never made
    at all -- the same physical model as forgetting one assignment, and the one
    the solver was measured on.
    """
    spec = _spec(corners=3, wires_expect=3)
    result = _solve(spec, work / "three_springs")
    travel = _kpi(result, "U_PULL")
    want_three = FORCE / (3 * K_EACH)
    want_four = FORCE / (4 * K_EACH)
    problems = []
    if result.get("status") != "COMPLETED":
        problems.append(
            "the three-spring model did not complete (%s). The item depends on "
            "it completing: a job that fails is not the dangerous case."
            % result.get("status"))
    elif travel is None:
        problems.append("no U_PULL in the result")
    elif abs(travel - want_three) / want_three > TOLERANCE:
        problems.append("travelled %r, three springs predict %r"
                        % (travel, want_three))
    return {
        "id": "connector_unassigned_wire_solves_to_the_wrong_answer",
        "status": "pass" if not problems else "fail",
        "job_status": result.get("status"),
        "measured": travel,
        "three_springs_predict": want_three,
        "four_springs_predict": want_four,
        "error_if_taken_for_four": (None if travel is None
                                    else travel / want_four - 1.0),
        "note": "one spring short is a third more travel and nothing says so: "
                "measured on Abaqus 2021, the four-of-four job and the "
                "three-of-four job both COMPLETE with no error and no warning.",
        "problems": problems,
    }


def check_wire_count(work: Path) -> dict:
    out = _build(work / "wire_count", _spec(wires_expect=7))
    evidence = _evidence(out)
    problems = []
    if "EXPECT_WIRES" not in evidence:
        problems.append("a wrong wire count was accepted: %s" % evidence[-500:])
    return {
        "id": "connector_asserts_the_wire_count",
        "status": "pass" if not problems else "fail",
        "stated": 7, "actual": 4,
        "log_line": _line(out, "EXPECT_WIRES"),
        "problems": problems,
    }


def check_bad_vertex(work: Path) -> dict:
    out = _build(work / "bad_vertex", _spec(bad_vertex=True))
    evidence = _evidence(out)
    problems = []
    if "VERTEX_NOT_FOUND" not in evidence:
        problems.append("a wire endpoint in mid-air was accepted: %s"
                        % evidence[-600:])
    return {
        "id": "connector_refuses_a_vertex_that_is_not_there",
        "status": "pass" if not problems else "fail",
        "log_line": _line(out, "VERTEX_NOT_FOUND"),
        "note": "a wire built from a bare coordinate is ACCEPTED by Abaqus, "
                "adds a real edge, takes a section assignment, and then fails "
                "in the solver with 'CONNECTOR ELEMENT 1 (ASSEMBLY) NODE "
                "NUMBERS CANNOT BE BOTH ZERO'. Nothing at build time can tell "
                "the two apart, so the spec cannot write the coordinate form: "
                "it names an instance and a corner, and the corner is counted.",
        "problems": problems,
    }


def check_module_import(work: Path) -> dict:
    spec = _spec()
    try:
        text = build_v2.generate_script(spec)
    except Exception as exc:
        text = ""
        error = "%s: %s" % (type(exc).__name__, exc)
    else:
        error = ""
    problems = []
    if error:
        problems.append(error)
    elif "connectorBehavior" not in arg_forms._IMPORT_LINE:
        problems.append("connectorBehavior is not imported by the deck")
    elif "_gnew('connectorBehavior', 'ConnectorElasticity'" not in text:
        problems.append("the elasticity is not built through {new:}")
    elif "'connectorBehavior': connectorBehavior" not in text:
        problems.append(
            "the runtime module table does not carry connectorBehavior, so "
            "{new:} would meet a KeyError. It is generated from the import "
            "line for exactly this reason.")
    return {
        "id": "connector_elasticity_comes_from_a_module_the_deck_now_imports",
        "status": "pass" if not problems else "fail",
        "import_line": arg_forms._IMPORT_LINE,
        "note": "ConnectorElasticity lives in connectorBehavior, which the "
                "generated script did not import. The runtime table is derived "
                "from the import line rather than written out again, so the "
                "host-side allowlist and the script cannot disagree.",
        "problems": problems,
    }


def check_ordering(work: Path) -> dict:
    """The section has to exist before the assignment names it."""
    out = _build(work / "no_section", _spec(skip_section=True))
    evidence = _evidence(out)
    problems = []
    if "does not exist in the model" not in evidence \
            and "GENERIC_FAILED" not in evidence:
        problems.append(
            "assigning a section that was never made was accepted: %s"
            % evidence[-600:])
    return {
        "id": "connector_section_must_exist_before_it_is_assigned",
        "status": "pass" if not problems else "fail",
        "log_line": _line(out, "GENERIC_FAILED"),
        "note": "measured: a.SectionAssignment naming a section that does not "
                "exist raises ValueError. That is why model_setup exists -- "
                "interactions run after the assembly, and this cannot wait.",
        "problems": problems,
    }


# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path,
                    default=ROOT / "artifacts" / "generic_connector_check"
                    / "report.json")
    ap.add_argument("--work", type=Path, default=None)
    args = ap.parse_args()

    work = args.work or (ROOT / "artifacts" / "generic_connector_check")
    work.mkdir(parents=True, exist_ok=True)
    started = time.time()

    names = ("connector_spring_travels_exactly_f_over_k",
             "connector_stiffness_sweep_is_linear",
             "connector_refuses_a_wire_with_no_section",
             "connector_unassigned_wire_solves_to_the_wrong_answer",
             "connector_asserts_the_wire_count",
             "connector_refuses_a_vertex_that_is_not_there",
             "connector_elasticity_comes_from_a_module_the_deck_now_imports",
             "connector_section_must_exist_before_it_is_assigned")

    if not check_abaqus():
        reason = ("Abaqus not found (set ABAQUS_AGENT_ABAQUS_CMD or put "
                  "abaqus.bat on PATH)")
        items = [_skipped(name, reason) for name in names]
        release = None
    else:
        release = detect_abaqus_release()
        items = [check_exact(work), check_sweep(work),
                 check_refuses_unassigned(work),
                 check_unassigned_solves_wrong(work), check_wire_count(work),
                 check_bad_vertex(work), check_module_import(work),
                 check_ordering(work)]

    failed = [i for i in items if i["status"] == "fail"]
    report = {
        "generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "abaqus_release": release,
        "seconds": round(time.time() - started, 1),
        "overall": "fail" if failed else "pass",
        "items": items,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
