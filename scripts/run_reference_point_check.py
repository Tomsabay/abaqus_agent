#!/usr/bin/env python3
"""Real-solver check for the control point a constraint needs.

Coupling, RigidBody and MultipointConstraint all take one, and until
`{reference_point:}` existed a spec could not produce one. Measured on
Abaqus 2021 (artifacts/probe_rp), the round trip is three objects deep and none
of them is nameable from a spec: `a.ReferencePoint(...)` returns a Feature, the
point is `a.referencePoints[feature.id]`, and the constraint wants a Region
over that. The deck then names the set it was given --
`*Coupling, constraint name=Cpl, ref node=RP, surface=TIPFACE`.

Rig: a 10 x 10 x 100 cantilever, C3D8I at seed 5.0, encastred at z = 0, and
100 N pressed down ON THE REFERENCE POINT -- so the load reaches the bar only
through the coupling. Beam theory is P L^3 / 3EI = 0.190476 mm. If the coupling
does not bind, that load has nowhere to go.

  1. `coupling_carries_the_load_through_a_reference_point` -- coordinates.
  2. `coupling_placed_at_a_selector_needs_no_coordinates` -- the same answer
     with the point put at a face centroid instead, which is what takes the
     arithmetic out of the common case.
  3. `a_control_point_in_the_wrong_place_is_silent` -- the reason item 2
     exists. The same model with the point 50 mm past the end of the bar
     solves with 0 errors, 0 warnings and COMPLETED, and answers the spec's
     `location: whole_model` KPI with -0.61471903 against a theory of
     -0.19047619. That reading is the reference point's OWN node, which is
     not part of the structure; the bar's tip in the same run is -0.33120051.
     Both wrong, and the one a spec receives is the wronger -- so the item
     reads the run twice and requires the two to separate. It is NOT refused:
     an offset control point is also how a moment is applied, and from here
     the deliberate one and the mistaken one are identical. What ships is the
     position in the log, and this item pins that it is there.
  4. `rigid_body_and_mpc_take_the_same_control_point` -- one form, three
     constraints, or it is a Coupling feature rather than a control point.
  5. `a_coupling_onto_an_empty_surface_is_caught_before_the_solve` -- measured,
     Abaqus itself answers that one with 6 fatal errors, so the question is
     whether this side gets there first with something a person can act on.
  6. `a_load_on_a_set_nothing_created_aborts_the_build` -- the counterexample
     for `{named_set:}`, the second form this task needed. A reference point
     is on no face and no edge, so no selector can re-find it and a coupling
     could be created and then never loaded; `{named_set:}` is how the load
     gets to it. Item 1 shows that form saying yes, and a form that has only
     ever been shown saying yes has been shown nothing.

Exit codes: 0 = nothing failed (no Abaqus => "skipped", still 0);
            1 = at least one item ran and failed.
"""

from __future__ import annotations

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
from runner import build_v2  # noqa: E402
from tools.abaqus_cmd import detect_abaqus_release, get_abaqus_cmd  # noqa: E402

MODEL = "ReferencePointCheck"
W = H = 10.0
L = 100.0
E, NU, RHO = 210000.0, 0.3, 7.85e-9
SEED = 5.0
TIP_LOAD = 100.0
INERTIA = W * H ** 3 / 12.0
BEAM_TIP = TIP_LOAD * L ** 3 / (3.0 * E * INERTIA)       # 0.190476... mm
# What this gate measures, by moving only the point, read two ways because the
# reference point is itself a node and the two readings come apart:
#                               whole model     tip face only
#   (5, 5, 100) centre of the   -0.18944125     -0.18944125     0.5% out
#               tip face
#   (5, 5, 150) 50 mm past      -0.61471903     -0.33120051     223% / 74%
#               the end                                         0 err, 0 warn
OFFSET_MM = 50.0
BAND = 0.05             # a coarse mesh is stiff; 5% is the room that needs
WRONG_AT_LEAST = 0.50   # and the misplaced point has to be far outside it


def _part() -> dict:
    return {"name": "Bar",
            "features": [{"op": "sketch", "id": "o", "plane": "XY",
                          "profile": {"rect": {"corner1": [0.0, 0.0],
                                               "corner2": [W, H]}}},
                         {"op": "extrude", "sketch": "o", "depth": L}],
            "section": {"type": "solid", "material": "Steel"},
            "mesh": {"seed": SEED, "element": "C3D8I",
                     "technique": "structured"}}


FIX = {"call": "EncastreBC", "name": {"literal": "Fix"},
       "createStepName": {"literal": "Initial"},
       "region": {"set": "Bar:face@z=min", "name": "FIX", "expect": "=1"}}


def _coupling(control, surface=None) -> dict:
    return {"call": "Coupling", "name": {"literal": "Cpl"},
            "controlPoint": control,
            "surface": surface if surface is not None
            else {"surface": "Bar:face@z=max", "name": "TIPFACE",
                  "expect": "=1"},
            "influenceRadius": "WHOLE_SURFACE", "couplingType": "KINEMATIC",
            "localCsys": None,
            "u1": "ON", "u2": "ON", "u3": "ON",
            "ur1": "ON", "ur2": "ON", "ur3": "ON"}


# The load goes on the SAME named set the coupling controls. That is the whole
# point of naming it: without a name there is nothing for a second call to
# refer to, and a reference point nothing loads is a reference point nothing
# tests.
def _tip_force(set_name: str) -> dict:
    return {"call": "ConcentratedForce", "name": {"literal": "Tip"},
            "createStepName": {"literal": "One"},
            "region": {"named_set": set_name},
            "cf2": -TIP_LOAD, "distributionType": "UNIFORM",
            "localCsys": None}


# A real output request, and the only way to get a NODE set on the tip face.
# Measured first: `location: TIPFACE` -- the coupling's own surface -- resolves
# and then dies inside the extractor with "Surface based region for getSubset
# is not supported", and the KPI vanishes from result["kpis"] while the job
# reports COMPLETED. A surface is not subsettable; a set is.
def _tip_history() -> dict:
    return {"call": "HistoryOutputRequest", "name": {"literal": "TipHist"},
            "createStepName": {"literal": "One"},
            # `{literal:}` because a bare ALL-CAPS string is read as an
            # abaqusConstants symbol, and there IS a `U2` constant -- measured,
            # the build stops at "variables; found tuple, expecting sequence of
            # Strings". Loud, which is the point, but it has to be written
            # right here.
            "variables": [{"literal": "U2"}],
            "region": {"set": "Bar:face@z=max", "name": "TIPNODES",
                       "expect": "=1"}}


def _spec(conditions) -> dict:
    return {"meta": {"abaqus_release": "2021", "model_name": MODEL,
                     "units": "mm_MPa_t"},
            "material": {"name": "Steel", "E": E, "nu": NU, "density": RHO},
            "parts": [_part()],
            "assembly": {"instances": [{"name": "Bar", "part": "Bar",
                                        "translate": [0.0, 0.0, 0.0]}]},
            "steps": [{"call": "StaticStep", "name": {"literal": "One"},
                       "previous": {"literal": "Initial"}}],
            "conditions": conditions,
            "outputs": {"kpis": [
                # Two readings of the same run, and the difference between
                # them is item 3. The reference point is a NODE in the model,
                # so once it is moved off the end of the bar it becomes the
                # whole-model minimum -- and a spec asking "how far did
                # anything move" is then answered about a point that is not
                # part of the structure. Naming the tip face separately is
                # what makes both numbers visible instead of one.
                {"name": "U_TIP", "type": "field_min",
                 "location": "whole_model", "component": "U2"},
                {"name": "U_BAR_TIP", "type": "field_min",
                 "location": "TIPNODES", "component": "U2"}]}}


# --- plumbing --------------------------------------------------------------

def _fresh(work: Path) -> Path:
    """An empty room.

    build_model reuses a deck when the fingerprint matches, and a reused deck
    means no CAE run and therefore last time's selectors.log sitting next to
    this time's answer. A gate that reads a log it did not just produce is a
    gate reporting on a run that never happened.
    """
    import shutil

    work = work.resolve()
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True, exist_ok=True)
    return work


def _build(work: Path, spec: dict) -> dict:
    work = _fresh(work)
    try:
        text = build_v2.generate_script(spec)
    except Exception as exc:
        return {"built": False, "log": "", "inp": "", "inp_written": False,
                "refused_at_generation": "%s: %s" % (type(exc).__name__, exc)}
    (work / "build_model_script.py").write_text(text, encoding="utf-8")
    proc = subprocess.run(
        [get_abaqus_cmd(), "cae", "noGUI=build_model_script.py", "--",
         str(work), "spec"],
        cwd=str(work), stdin=subprocess.DEVNULL, capture_output=True,
        text=True, errors="replace", encoding="utf-8", timeout=1800)
    log = work / "selectors.log"
    inp = work / ("%s.inp" % MODEL)
    return {"built": True,
            "log": log.read_text(encoding="utf-8", errors="replace")
                   if log.exists() else "",
            "inp": inp.read_text(encoding="utf-8", errors="replace")
                   if inp.exists() else "",
            "inp_written": inp.exists(),
            "stderr": (proc.stderr or "")[-2000:],
            "refused_at_generation": None}


def _solve(spec: dict, work: Path) -> dict:
    from agent.orchestrator import build_orchestrator
    _fresh(work)
    return build_orchestrator(spec_dict=copy.deepcopy(spec), workdir=work,
                              expected_path=None, runner_cfg=None).run()


def _kpi(result: dict, name: str):
    value = (result.get("kpis") or {}).get(name)
    return value.get("value") if isinstance(value, dict) else value


def _line(out: dict, needle: str) -> str:
    for line in (out.get("log") or "").splitlines():
        if needle in line:
            return line.strip()
    return ""


def _log_line(work: Path, needle: str) -> str:
    log = work / "selectors.log"
    if not log.exists():
        return ""
    for line in log.read_text(encoding="utf-8", errors="replace").splitlines():
        if needle in line:
            return line.strip()
    return ""


def _dat_counts(work: Path) -> dict:
    """The job's own .dat, named rather than globbed.

    The syntaxcheck stage writes one too, and a glob would hand back whichever
    sorts first -- so a silent solve could be reported off a datacheck that
    never ran the increment.
    """
    dat = work / ("%s.dat" % MODEL)
    if not dat.exists():
        return {"errors": None, "warnings": None, "file": None}
    text = dat.read_text(encoding="utf-8", errors="replace")
    return {"errors": text.upper().count("***ERROR"),
            "warnings": text.upper().count("***WARNING"),
            "file": dat.name}


def _skipped(item_id: str, reason: str) -> dict:
    return {"id": item_id, "status": "skipped", "reason": reason}


# --- items -----------------------------------------------------------------

def _load_through_a_point(item_id: str, work: Path, control: dict,
                          note: str) -> dict:
    """One reference point, one load on it, and beam theory at the other end."""
    conditions = [FIX, _coupling(control), _tip_force("RP"), _tip_history()]
    result = _solve(_spec(conditions), work)
    tip = _kpi(result, "U_TIP")
    bar_tip = _kpi(result, "U_BAR_TIP")
    placed = _log_line(work, "REFERENCE_POINT_OK")
    named = _log_line(work, "NAMED_SET_OK")
    deck = work / ("%s.inp" % MODEL)
    text = deck.read_text(encoding="utf-8", errors="replace") \
        if deck.exists() else ""

    problems = []
    if result.get("status") != "COMPLETED":
        problems.append("the job did not complete: %s / %s"
                        % (result.get("status"), str(result.get("error"))[:200]))
    if "ref node=RP" not in text:
        problems.append(
            "the deck does not carry `ref node=RP`. The card names the SET, "
            "so if the name is not there the coupling is not controlled by "
            "the point this spec built.")
    if tip is None:
        problems.append("no U_TIP came back")
    else:
        deviation = abs(tip - (-BEAM_TIP)) / BEAM_TIP
        if deviation > BAND:
            problems.append(
                "tip %.7g against beam theory %.7g is %.2f%% out; the load "
                "goes on the reference point and reaches the bar only through "
                "the coupling, so this says the coupling did not bind"
                % (tip, -BEAM_TIP, deviation * 100.0))
    if bar_tip is None:
        problems.append("no U_BAR_TIP came back, so `location: TIPFACE` did "
                        "not resolve and the two readings cannot be compared")
    elif tip is not None and abs(bar_tip - tip) > 1e-9:
        # With the point ON the tip face these are the same node's answer, and
        # they have to agree -- if they do not, the whole-model minimum is
        # somewhere neither this item nor the reader is looking.
        problems.append(
            "the whole-model minimum %.8g and the tip face minimum %.8g "
            "disagree, and with the control point on the tip face they are "
            "the same node" % (tip, bar_tip))
    if not placed:
        problems.append("no REFERENCE_POINT_OK line, so the position was not "
                        "recorded")
    if not named:
        problems.append(
            "no NAMED_SET_OK line. The load reaches the point through "
            "`{named_set:}`, and without that form a coupling can be created "
            "and then never loaded -- which is the only reason to create one.")

    return {"id": item_id,
            "status": "pass" if not problems else "fail",
            "measured_tip": tip,
            "measured_bar_tip": bar_tip,
            "beam_theory_tip": -BEAM_TIP,
            "placed_line": placed,
            "named_set_line": named,
            "note": note,
            "problems": problems}


def check_coupling_by_coordinates(work: Path) -> dict:
    return _load_through_a_point(
        "coupling_carries_the_load_through_a_reference_point",
        work / "by_coords",
        {"reference_point": [W / 2.0, H / 2.0, L], "name": "RP"},
        "100 N on the reference point, which reaches the bar only through the "
        "coupling. The deck's `ref node=` names the set this form built.")


def check_coupling_at_a_selector(work: Path) -> dict:
    return _load_through_a_point(
        "coupling_placed_at_a_selector_needs_no_coordinates",
        work / "at_selector",
        {"reference_point": {"at": "Bar:face@z=max"}, "name": "RP"},
        "the same answer with the point put at the centroid of the face it "
        "controls, so no coordinate is typed and the arithmetic that item 3 "
        "shows is silent cannot be got wrong.")


def check_a_misplaced_point_is_silent(work: Path) -> dict:
    """The hazard this form cannot refuse, measured rather than argued.

    An offset control point is a legitimate way to apply a moment, so the
    deliberate one and the mistaken one are the same call with a different
    number. What ships is the position in the log; this item proves the hazard
    is real AND that the record exists.
    """
    room = work / "misplaced"
    conditions = [FIX,
                  _coupling({"reference_point": [W / 2.0, H / 2.0,
                                                 L + OFFSET_MM],
                             "name": "RP"}),
                  _tip_force("RP"), _tip_history()]
    result = _solve(_spec(conditions), room)
    tip = _kpi(result, "U_TIP")
    bar_tip = _kpi(result, "U_BAR_TIP")
    counts = _dat_counts(room)
    placed = _log_line(room, "REFERENCE_POINT_OK")

    problems = []
    if result.get("status") != "COMPLETED":
        problems.append(
            "the misplaced point did not COMPLETE (%s). That would make it "
            "loud, which is a better world -- and it would mean this item's "
            "premise, and the `{at:}` form it justifies, need remeasuring."
            % result.get("status"))
    if counts.get("errors"):
        problems.append(
            "the solve reported %d error(s), so this is not the silent case"
            % counts["errors"])
    if tip is None or bar_tip is None:
        problems.append("no U_TIP / U_BAR_TIP came back")
    else:
        deviation = abs(tip - (-BEAM_TIP)) / BEAM_TIP
        if deviation < WRONG_AT_LEAST:
            problems.append(
                "the reported minimum %.7g is only %.1f%% from beam theory. "
                "The point is %g mm past the end of the bar; if that no "
                "longer moves the answer, the case for `{at:}` is not what "
                "this says it is." % (tip, deviation * 100.0, OFFSET_MM))
        # The two readings have to SEPARATE here, and that separation is the
        # sharpest thing this item has to say. Off the end of the bar the
        # reference point is itself the whole-model minimum, so a spec asking
        # "how far did anything move" is answered about a node that is not
        # part of the structure -- wrong twice over, and by different amounts.
        if abs(bar_tip - tip) < 1e-6:
            problems.append(
                "the whole-model minimum and the tip face minimum are the "
                "same value (%.8g). Off the end of the bar the reference "
                "point should BE the minimum; if it is not, the reading this "
                "item calls silent is not the reading a user gets." % tip)
    # The log is the only mitigation that ships, so its content IS the item.
    wanted = "at (%.6g, %.6g, %.6g)" % (W / 2.0, H / 2.0, L + OFFSET_MM)
    if wanted not in placed:
        problems.append(
            "the log does not carry %r, so after a run like this nobody can "
            "answer \"which point was it?\" without building it again. The "
            "line was %r" % (wanted, placed or "(absent)"))

    return {
        "id": "a_control_point_in_the_wrong_place_is_silent",
        "status": "pass" if not problems else "fail",
        "measured_tip": tip,
        "measured_bar_tip": bar_tip,
        "beam_theory_tip": -BEAM_TIP,
        "offset_mm": OFFSET_MM,
        "dat_errors": counts.get("errors"),
        "dat_warnings": counts.get("warnings"),
        "placed_line": placed,
        "note": "the point 50 mm past the end of the bar. Nothing refuses it, "
                "because that is also how a moment is applied -- so what "
                "ships is the position in the log and a `{at:}` form that "
                "needs no coordinate at all.",
        "problems": problems,
    }


def check_rigid_body_and_mpc(work: Path) -> dict:
    """One form, three constraints, or it is a Coupling feature.

    Built rather than solved: both are accepted by Abaqus (measured), and what
    this asks is whether the same argument form reaches them and whether the
    deck carries the cards. A RigidBody tying the whole bar to a point makes
    the cantilever rigid, which is a different model, not a better test.
    """
    rigid = _build(work / "rigid_body", _spec([
        FIX,
        {"call": "RigidBody", "name": {"literal": "RB"},
         "refPointRegion": {"reference_point": [W / 2.0, H / 2.0, L],
                            "name": "RPRB"},
         "tieRegion": {"set": "Bar:face@z=max", "name": "TIED",
                       "expect": "=1"}}]))
    mpc = _build(work / "mpc", _spec([
        FIX,
        {"call": "MultipointConstraint", "name": {"literal": "MPC"},
         "controlPoint": {"reference_point": [W / 2.0, H / 2.0, L],
                          "name": "RPMPC"},
         "surface": {"surface": "Bar:face@z=max", "name": "MPCFACE",
                     "expect": "=1"},
         "mpcType": "BEAM_MPC", "userMode": "DOF_MODE_MPC", "userType": 0,
         "csys": None}]))

    problems = []
    for label, out, card in (("RigidBody", rigid, "*Rigid Body"),
                             ("MultipointConstraint", mpc, "*MPC")):
        if not out.get("inp_written"):
            problems.append(
                "%s wrote no input file: %s"
                % (label, str(out.get("refused_at_generation")
                              or out.get("stderr"))[:250]))
        elif card not in (out.get("inp") or ""):
            problems.append(
                "%s built a deck with no %s card in it, so the constraint was "
                "accepted and did not reach the analysis" % (label, card))
        if "REFERENCE_POINT_OK" not in (out.get("log") or ""):
            problems.append("%s: no REFERENCE_POINT_OK line" % label)

    return {
        "id": "rigid_body_and_mpc_take_the_same_control_point",
        "status": "pass" if not problems else "fail",
        "rigid_body_card": "*Rigid Body" in (rigid.get("inp") or ""),
        "mpc_card": "*MPC" in (mpc.get("inp") or ""),
        "note": "the same `{reference_point:}` through refPointRegion and "
                "through controlPoint -- three constraints, one form. Built "
                "rather than solved: a RigidBody tying the whole tip makes a "
                "different model, not a better test.",
        "problems": problems,
    }


def check_empty_surface(work: Path) -> dict:
    """Abaqus answers this one with 6 fatal errors. Does this side get there
    first with something a person can act on?

    The count assertion on `{surface:}` predates the reference point layer, so
    this is not a new guard -- it is a check that the new form did not route
    around an old one.
    """
    out = _build(work / "empty_surface", _spec([
        FIX,
        _coupling({"reference_point": [W / 2.0, H / 2.0, L], "name": "RP"},
                  surface={"surface": "Bar:face@z=max", "name": "TIPFACE",
                           "expect": "=2"})]))
    # Named exactly, not a prefix. `SELECTOR` alone matches SELECTOR_OK, so a
    # first pass here recorded the FIX selector SUCCEEDING as this item's
    # evidence -- a green tick carrying a line that says nothing about it.
    refusal = _line(out, "SELECTOR_MISMATCH")
    problems = []
    if out.get("inp_written"):
        problems.append(
            "a surface asserting 2 faces where the bar has 1 wrote a deck. "
            "Measured on Abaqus 2021, a coupling onto a surface with no faces "
            "is created without complaint and dies at the solve with 6 fatal "
            "errors -- so the count assertion is what stands between a spec "
            "mistake and a log to read.")
    if not refusal:
        problems.append("no SELECTOR_MISMATCH line, so whatever stopped the "
                        "build did not say which selector missed")
    elif "Bar:face@z=max" not in refusal:
        problems.append("the mismatch line does not name the selector that "
                        "missed: %r" % refusal)
    return {
        "id": "a_coupling_onto_an_empty_surface_is_caught_before_the_solve",
        "status": "pass" if not problems else "fail",
        "refusal_line": refusal,
        "note": "not a new guard: the count assertion on `{surface:}` is what "
                "catches it, and this pins that the reference point form did "
                "not route around it.",
        "problems": problems,
    }


def check_a_name_nothing_created(work: Path) -> dict:
    """The counterexample for `{named_set:}`, which has to have one.

    A gate that only ever shows the form working proves it can say yes. This
    is the other direction: the same rig with the load pointed at a set no
    call in the spec ever built. It has to stop before a deck exists, because
    if it did not, `region=` would silently fall to whatever Abaqus does with
    a missing name and the 100 N would land somewhere nobody chose.
    """
    out = _build(work / "absent_name", _spec(
        [FIX, _coupling({"reference_point": [W / 2.0, H / 2.0, L],
                         "name": "RP"}),
         _tip_force("NOSUCHSET")]))
    refusal = _line(out, "NAMED_SET_MISSING")
    problems = []
    if out.get("inp_written"):
        problems.append(
            "a load on a set nothing created wrote a deck; the 100 N in it "
            "is on a region no line of the spec chose")
    if not refusal:
        problems.append(
            "nothing in the log says NAMED_SET_MISSING, so whatever stopped "
            "it did not say which name was wrong")
    elif "RP" not in refusal:
        problems.append(
            "the refusal does not list the sets that DO exist, which is the "
            "one thing that turns it from a stop into a fix: %r" % refusal)
    return {
        "id": "a_load_on_a_set_nothing_created_aborts_the_build",
        "status": "pass" if not problems else "fail",
        "refusal_line": refusal,
        "note": "the other direction. Item 1 shows the form can say yes; "
                "without this one, that is all it shows.",
        "problems": problems,
    }


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path,
                    default=ROOT / "artifacts" / "reference_point_check"
                    / "report.json")
    ap.add_argument("--work", type=Path, default=None)
    args = ap.parse_args()

    work = args.work or (ROOT / "artifacts" / "reference_point_check")
    work.mkdir(parents=True, exist_ok=True)
    started = time.time()

    names = ("coupling_carries_the_load_through_a_reference_point",
             "coupling_placed_at_a_selector_needs_no_coordinates",
             "a_control_point_in_the_wrong_place_is_silent",
             "rigid_body_and_mpc_take_the_same_control_point",
             "a_coupling_onto_an_empty_surface_is_caught_before_the_solve",
             "a_load_on_a_set_nothing_created_aborts_the_build")

    release = None
    if not check_abaqus():
        reason = ("Abaqus not found (set ABAQUS_AGENT_ABAQUS_CMD or put "
                  "abaqus.bat on PATH)")
        items = [_skipped(name, reason) for name in names]
    else:
        release = detect_abaqus_release()
        items = [check_coupling_by_coordinates(work),
                 check_coupling_at_a_selector(work),
                 check_a_misplaced_point_is_silent(work),
                 check_rigid_body_and_mpc(work),
                 check_empty_surface(work),
                 check_a_name_nothing_created(work)]

    failed = [i for i in items if i["status"] == "fail"]
    report = {
        "generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "abaqus_release": release,
        "seconds": round(time.time() - started, 1),
        "rig": {"beam_theory_tip": -BEAM_TIP, "tip_load_n": TIP_LOAD,
                "offset_mm": OFFSET_MM},
        "overall": "fail" if failed else "pass",
        "items": items,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
