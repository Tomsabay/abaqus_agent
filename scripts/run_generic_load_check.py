#!/usr/bin/env python3
"""Real-solver check for the dispatched step / condition layer.

`steps:` was the last enumerated block in v2: one step type (Static), six
boundary condition types, two load types. Everything else Abaqus can analyse --
frequency extraction, implicit and explicit dynamics, buckling, heat transfer,
Riks -- was unreachable, and so were moments, body forces, gravity, velocity
boundary conditions and predefined fields.

Rig: 10 x 10 x 100 cantilever, C3D8I, 10 mm seed, encastred at z = 0.
E = 210000, nu = 0.3, rho = 7.85e-9, I = 833.333.

    0.1 MPa on the top face   ->  q L^4 / (8 E I) = -0.0714286 mm
    100 N at the tip          ->  P L^3 / (3 E I) = -0.1904762 mm
    first bending mode        ->  (1.875104^2 / 2pi) sqrt(EI / (rho A L^4))
                                = 835.5 Hz by Euler-Bernoulli

  1. `loads_dispatched_static_matches_the_named_form`
  2. `loads_a_frequency_step_is_now_expressible` -- the enumerated block could
     only ever say Static
  3. `loads_a_stated_point_count_gives_the_load_that_was_meant`
  4. `loads_the_magnitude_is_written_at_every_node` -- the same call with the
     undivided number is four times the load, and the job completes
  5. `loads_a_multi_node_cload_without_a_stated_count_is_refused`
  6. `loads_a_wrong_point_count_is_refused`
  7. `loads_a_face_region_slips_past_caes_own_guard` -- consistencyChecking=OFF
     means CAE's own load-region validation never runs in this pipeline
  8. `loads_step_order_is_asserted`
  9. `loads_reversed_steps_solve_to_the_wrong_answer` -- the same deck with the
     order assertion deleted: COMPLETED, steps reversed
 10. `loads_abaqus_refuses_these_itself` -- the two that were already loud,
     recorded so the layer does not guard them twice

Exit codes: 0 = nothing failed (no Abaqus => "skipped", still 0);
            1 = at least one item ran and failed.
"""

from __future__ import annotations

import argparse
import copy
import json
import re
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

MODEL = "GenericLoadCheck"
W = H = 10.0
L = 100.0
E, NU, RHO = 210000.0, 0.3, 7.85e-9
PRESSURE = 0.1
TIP_FORCE = 100.0
INERTIA = W * H ** 3 / 12.0

UDL_TIP = PRESSURE * W * L ** 4 / (8.0 * E * INERTIA)
POINT_TIP = TIP_FORCE * L ** 3 / (3.0 * E * INERTIA)
# Euler-Bernoulli, which ignores shear and rotary inertia. At L/h = 10 the beam
# is stubby enough that the real answer sits a little under this, so the item
# checks a band rather than a number.
FIRST_MODE_HZ = 835.5

TOLERANCE = 0.05
STEP_RE = re.compile(r"^\*Step, name=([^,\n]+)", re.MULTILINE)


def _part() -> dict:
    return {
        "name": "Beam",
        "features": [
            {"op": "sketch", "id": "outline", "plane": "XY",
             "profile": {"rect": {"corner1": [0.0, 0.0], "corner2": [W, H]}}},
            {"op": "extrude", "sketch": "outline", "depth": L},
        ],
        "section": {"type": "solid", "material": "Steel"},
        "mesh": {"seed": 10.0, "element": "C3D8I", "technique": "structured"},
    }


def _spec(steps: list, conditions: list, kpis: list | None = None) -> dict:
    return {
        "meta": {"abaqus_release": "2021", "model_name": MODEL,
                 "units": "mm_MPa_t"},
        "material": {"name": "Steel", "E": E, "nu": NU, "density": RHO},
        "parts": [_part()],
        "assembly": {"instances": [
            {"name": "Bar", "part": "Beam", "translate": [0.0, 0.0, 0.0]}]},
        "steps": steps,
        "conditions": conditions,
        "outputs": {"kpis": kpis if kpis is not None else [
            {"name": "U_TIP", "type": "field_min", "location": "whole_model",
             "component": "U2"}]},
    }


def _fix(step="Initial") -> dict:
    return {"call": "EncastreBC", "name": {"literal": "Fix"},
            "createStepName": {"literal": step},
            "region": {"set": "Bar:face@z=min", "name": "FIX",
                       "expect": "=1"}}


def _static(name="Press", previous="Initial") -> dict:
    return {"call": "StaticStep", "name": {"literal": name},
            "previous": {"literal": previous}}


def _pressure(step="Press", magnitude=PRESSURE) -> dict:
    return {"call": "Pressure", "name": {"literal": "Top"},
            "createStepName": {"literal": step},
            "region": {"surface": "Bar:face@y=max", "name": "TOP",
                       "expect": "=1"},
            "magnitude": magnitude}


def _tip_force(magnitude: float, points=None) -> dict:
    """All four tip corners; only the magnitude changes.

    A prism has four vertices at z = max and the selector cannot pick one of
    them, so the pair that proves per-node scaling is -25 against -100 on the
    same four nodes: the first totals the 100 N the closed form is about, the
    second totals 400 N.
    """
    entry = {"call": "ConcentratedForce", "name": {"literal": "Tip"},
             "createStepName": {"literal": "Press"},
             "region": {"set": "Bar:vertex@z=max", "name": "TIP",
                        "expect": "=4"},
             "cf2": magnitude}
    if points is not None:
        entry["expect"] = {"points": points}
    return entry


# --- plumbing --------------------------------------------------------------

def _build(work: Path, spec: dict, strip: str | None = None) -> dict:
    """Generate, optionally delete one generated line, then run CAE."""
    work = work.resolve()
    work.mkdir(parents=True, exist_ok=True)
    log_path = work / "selectors.log"
    if log_path.exists():
        log_path.unlink()
    try:
        text = build_v2.generate_script(spec)
    except Exception as exc:
        return {"built": False, "log": "", "stripped": None,
                "error": "%s: %s" % (type(exc).__name__, exc)}
    removed = None
    if strip is not None:
        kept = [ln for ln in text.splitlines() if not ln.startswith(strip)]
        removed = [ln for ln in text.splitlines() if ln.startswith(strip)]
        text = "\n".join(kept) + "\n"
    (work / "build_model_script.py").write_text(text, encoding="utf-8")
    proc = subprocess.run(
        [get_abaqus_cmd(), "cae", "noGUI=build_model_script.py", "--",
         str(work), "spec"],
        cwd=str(work), capture_output=True, text=True,
        errors="replace", encoding="utf-8", stdin=subprocess.DEVNULL,
        timeout=1800)
    log = (log_path.read_text(encoding="utf-8", errors="replace")
           if log_path.exists() else "")
    return {"built": True, "log": log, "stripped": removed,
            "error": (proc.stderr or "")[-4000:]}


def _solve_inp(work: Path) -> dict:
    """Run the .inp the build wrote, without going through the orchestrator.

    Frequency extraction has no KPI type behind it, and the reversed-step deck
    is deliberately not a spec the generator would emit, so both need the job
    run directly. The launcher always returns 0, so the verdict comes from the
    .sta file.
    """
    inp = work / ("%s.inp" % MODEL)
    if not inp.exists():
        return {"ran": False, "why": "no %s" % inp.name}
    subprocess.run(
        [get_abaqus_cmd(), "job=%s" % MODEL, "interactive", "ask_delete=OFF"],
        cwd=str(work), capture_output=True, text=True, errors="replace",
        encoding="utf-8", stdin=subprocess.DEVNULL, timeout=3600)
    out = {"ran": True, "steps_in_inp": STEP_RE.findall(
        inp.read_text(encoding="utf-8", errors="replace"))}
    sta = work / ("%s.sta" % MODEL)
    text = sta.read_text(encoding="utf-8", errors="replace") if sta.exists() else ""
    out["completed"] = "COMPLETED SUCCESSFULLY" in text
    dat = work / ("%s.dat" % MODEL)
    if dat.exists():
        out["dat"] = dat.read_text(encoding="utf-8", errors="replace")
    return out


def _eigen_hz(dat: str, how_many=3) -> list:
    """The frequency column of the EIGENVALUE OUTPUT table in the .dat."""
    lines = dat.splitlines()
    start = None
    for i, line in enumerate(lines):
        # Anchored on the OUTPUT table, not on the step header a hundred lines
        # earlier, which also says "E I G E N V A L U E" and carries no numbers.
        if "E I G E N V A L U E" in line and "O U T P U T" in line:
            start = i
            break
    if start is None:
        return []
    found = []
    for line in lines[start:start + 60]:
        parts = line.split()
        # MODE NO, EIGENVALUE, FREQUENCY (RAD/TIME), FREQUENCY (CYCLES/TIME), ...
        if len(parts) >= 4 and parts[0].isdigit():
            try:
                found.append(float(parts[3]))
            except ValueError:
                continue
        if len(found) >= how_many:
            break
    return found


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
    for line in (out.get("log") or "").splitlines():
        if needle in line:
            return line.strip()
    return ""


def _skipped(item_id: str, reason: str) -> dict:
    return {"id": item_id, "status": "skipped", "reason": reason}


# --- items -----------------------------------------------------------------

def check_static(work: Path) -> dict:
    spec = _spec([_static()], [_fix(), _pressure()])
    result = _solve(spec, work / "static")
    tip = _kpi(result, "U_TIP")
    problems = []
    if result.get("status") != "COMPLETED":
        problems.append("status %s: %s" % (result.get("status"),
                                           result.get("error")))
    elif tip is None:
        problems.append("no U_TIP")
    elif abs(abs(tip) - UDL_TIP) / UDL_TIP > TOLERANCE:
        problems.append("tip %r against theory %r" % (tip, -UDL_TIP))
    return {
        "id": "loads_dispatched_static_matches_the_named_form",
        "status": "pass" if not problems else "fail",
        "predicted": -UDL_TIP, "measured": tip,
        "relative_deviation": (None if tip is None
                               else abs(abs(tip) - UDL_TIP) / UDL_TIP),
        "note": "StaticStep, EncastreBC and Pressure written as the Abaqus "
                "calls they are, giving the same answer as the enumerated "
                "form that hard-coded all three.",
        "problems": problems,
    }


def check_frequency(work: Path) -> dict:
    """The capability the enumerated block could not express at any price."""
    folder = work / "frequency"
    spec = _spec(
        [{"call": "FrequencyStep", "name": {"literal": "Modes"},
          "previous": {"literal": "Initial"}, "numEigen": 5}],
        [_fix()])
    out = _build(folder, spec)
    problems = []
    if not out["built"]:
        problems.append("did not generate: %s" % out.get("error"))
        return {"id": "loads_a_frequency_step_is_now_expressible",
                "status": "fail", "problems": problems}
    run = _solve_inp(folder)
    hz = _eigen_hz(run.get("dat", ""))
    if not run.get("completed"):
        problems.append("the frequency job did not complete")
    elif not hz:
        problems.append("no eigenvalue table in the .dat")
    elif abs(hz[0] - FIRST_MODE_HZ) / FIRST_MODE_HZ > 0.05:
        problems.append("first mode %r against Euler-Bernoulli %r"
                        % (hz[0], FIRST_MODE_HZ))
    return {
        "id": "loads_a_frequency_step_is_now_expressible",
        "status": "pass" if not problems else "fail",
        "steps_in_inp": run.get("steps_in_inp"),
        "first_modes_hz": hz,
        "euler_bernoulli_hz": FIRST_MODE_HZ,
        "note": "the enumerated block accepted exactly one step type. This is "
                "the same dispatch as everywhere else, and it needed no new "
                "case: FrequencyStep is a method on the model.",
        "problems": problems,
    }


def _corner_case(work: Path, tag: str, magnitude: float, points) -> dict:
    spec = _spec([_static()], [_fix(), _tip_force(magnitude, points)])
    result = _solve(spec, work / tag)
    return {"stated_magnitude": magnitude, "stated_points": points,
            "job_status": result.get("status"),
            "measured": _kpi(result, "U_TIP"),
            "error": result.get("error")}


def check_stated_total(work: Path) -> dict:
    """-25 at each of four corners is the 100 N the closed form is about."""
    row = _corner_case(work, "total_100N", -TIP_FORCE / 4.0, 4)
    tip = row["measured"]
    problems = []
    if row["job_status"] != "COMPLETED":
        problems.append("status %s: %s" % (row["job_status"], row["error"]))
    elif tip is None:
        problems.append("no U_TIP")
    elif abs(abs(tip) - POINT_TIP) / POINT_TIP > TOLERANCE:
        problems.append("tip %r against theory %r" % (tip, -POINT_TIP))
    return {
        "id": "loads_a_stated_point_count_gives_the_load_that_was_meant",
        "status": "pass" if not problems else "fail",
        "stated_magnitude": -TIP_FORCE / 4.0, "stated_points": 4,
        "implied_total": -TIP_FORCE,
        "predicted": -POINT_TIP, "measured": tip,
        "relative_deviation": (None if tip is None
                               else abs(abs(tip) - POINT_TIP) / POINT_TIP),
        "note": "the spec divides the total by the point count it stated, and "
                "the answer lands on P L^3 / (3 E I). A prism has four "
                "vertices at z = max and the selector cannot pick one of them, "
                "so this is the honest way to apply 100 N at the tip.",
        "problems": problems,
    }


def check_four_times(work: Path, stated: dict) -> dict:
    """The same call with the undivided magnitude: four times the load."""
    row = _corner_case(work, "total_400N", -TIP_FORCE, 4)
    tip = row["measured"]
    base = stated.get("measured")
    problems = []
    if row["job_status"] != "COMPLETED":
        problems.append(
            "the four-times model did not complete (%s). The item depends on "
            "it completing: a job that fails is not the dangerous case."
            % row["job_status"])
    elif tip is None or base is None:
        problems.append("no U_TIP to compare")
    elif abs(tip / base - 4.0) > 0.02:
        problems.append("expected four times %r, got %r (ratio %r)"
                        % (base, tip, tip / base))
    return {
        "id": "loads_the_magnitude_is_written_at_every_node",
        "status": "pass" if not problems else "fail",
        "job_status": row["job_status"],
        "stated_magnitude": -TIP_FORCE, "nodes": 4,
        "as_written": base, "measured": tip,
        "ratio": (None if not base else tip / base),
        "implied_total_load": -4 * TIP_FORCE,
        "note": "-100 at four nodes is 400 N, not 100 N. Measured reaction at "
                "the built-in end: 400 N, job COMPLETED, no warning. Nothing "
                "in the model or the log says the number in the spec was not "
                "the load -- which is why the count has to be stated.",
        "problems": problems,
    }


def check_unstated_count(work: Path) -> dict:
    """No `expect.points`, so the deck refuses after reading its own input."""
    folder = work / "no_points"
    out = _build(folder, _spec([_static()], [_fix(), _tip_force(-TIP_FORCE)]))
    evidence = _evidence(out)
    problems = []
    if "CLOAD_PER_NODE" not in evidence:
        problems.append("a four-node *Cload was accepted with no count: %s"
                        % evidence[-700:])
    if (folder / ("%s.inp" % MODEL)).exists():
        problems.append(
            "the input file was left on disk after the refusal, so a caller "
            "that tests for it would take this for a good build")
    return {
        "id": "loads_a_multi_node_cload_without_a_stated_count_is_refused",
        "status": "pass" if not problems else "fail",
        "log_line": _line(out, "CLOAD_PER_NODE"),
        "note": "read back out of the .inp Abaqus just wrote, not guessed from "
                "the selector: a concentrated force and a moment both come out "
                "as *Cload, and so will whatever the next release adds.",
        "problems": problems,
    }


def check_wrong_count(work: Path) -> dict:
    out = _build(work / "wrong_points",
                 _spec([_static()], [_fix(), _tip_force(-TIP_FORCE, 1)]))
    evidence = _evidence(out)
    problems = []
    if "POINTS_MISMATCH" not in evidence:
        problems.append("a wrong point count was accepted: %s"
                        % evidence[-600:])
    return {
        "id": "loads_a_wrong_point_count_is_refused",
        "status": "pass" if not problems else "fail",
        "log_line": _line(out, "POINTS_MISMATCH"),
        "note": "counted in CAE against the set that was just built, before "
                "the job is written.",
        "problems": problems,
    }


def check_face_slips_past_cae(work: Path) -> dict:
    """The sharpest one: CAE's own guard is not running in this pipeline.

    Submitting a concentrated force on a face-based set FROM CAE is refused --
    "The region selected for the following loads contains invalid geometry or
    mesh components for the load type", and no input file is written. But the
    generated deck calls writeInput(consistencyChecking=OFF), which skips that
    check, and the card comes out as `*Cload / TIP, 2, -100.` against an Nset
    of four nodes. The face case is also the worse one, because the node count
    moves with the mesh seed.
    """
    folder = work / "face_region"
    spec = _spec([_static()],
                 [_fix(),
                  {"call": "ConcentratedForce", "name": {"literal": "Tip"},
                   "createStepName": {"literal": "Press"},
                   "region": {"set": "Bar:face@z=max", "name": "TIP",
                              "expect": "=1"},
                   "cf2": -TIP_FORCE}])
    out = _build(folder, spec)
    evidence = _evidence(out)
    problems = []
    if "CLOAD_PER_NODE" not in evidence:
        problems.append(
            "a concentrated force on a face-based set was accepted: %s"
            % evidence[-700:])
    if (folder / ("%s.inp" % MODEL)).exists():
        problems.append("the input file was left on disk after the refusal")
    return {
        "id": "loads_a_face_region_slips_past_caes_own_guard",
        "status": "pass" if not problems else "fail",
        "log_line": _line(out, "CLOAD_PER_NODE"),
        "note": "CAE refuses this at submit and writes no input file. This "
                "deck does not submit from CAE -- it calls "
                "writeInput(consistencyChecking=OFF) and hands the .inp to the "
                "solver, so the guard never runs and *Cload comes out against "
                "a four-node Nset.",
        "problems": problems,
    }


def _reversed_spec() -> dict:
    """Two steps that both say they follow Initial. Written One then Two."""
    return _spec(
        [_static("One", "Initial"), _static("Two", "Initial")],
        [_fix(), _pressure(step="One")])


def check_step_order(work: Path) -> dict:
    out = _build(work / "step_order", _reversed_spec())
    evidence = _evidence(out)
    problems = []
    if "STEP_ORDER" not in evidence:
        problems.append("a reversed step order was accepted: %s"
                        % evidence[-600:])
    return {
        "id": "loads_step_order_is_asserted",
        "status": "pass" if not problems else "fail",
        "log_line": _line(out, "STEP_ORDER"),
        "note": "Abaqus inserts a step AFTER the one named in `previous:`, so "
                "two steps that both follow Initial come out in the reverse of "
                "the order they were written. Both are accepted.",
        "problems": problems,
    }


def check_reversed_solves(work: Path) -> dict:
    """Why the item above is load-bearing: the same deck, minus one line."""
    folder = work / "step_order_unguarded"
    out = _build(folder, _reversed_spec(), strip="_expect_steps(")
    problems = []
    if not out["stripped"]:
        problems.append("the order assertion was not in the deck to remove")
    run = _solve_inp(folder)
    order = run.get("steps_in_inp") or []
    if not run.get("completed"):
        problems.append(
            "the reversed model did not complete. The item depends on it "
            "completing: a job that fails is not the dangerous case.")
    elif order != ["Two", "One"]:
        problems.append("expected the analysis to run Two then One, got %r"
                        % (order,))
    return {
        "id": "loads_reversed_steps_solve_to_the_wrong_answer",
        "status": "pass" if not problems else "fail",
        "removed_lines": out.get("stripped"),
        "spec_wrote": ["One", "Two"],
        "analysis_runs": order,
        "job_completed": run.get("completed"),
        "note": "one line deleted from the generated deck and nothing else. "
                "The pressure the spec put in the first step is applied in the "
                "second, and the job reports success.",
        "problems": problems,
    }


def check_already_loud(work: Path) -> dict:
    """Two ways to get this wrong that Abaqus already refuses by itself.

    Recorded so the layer does not grow a second guard for something the
    solver already catches -- every guard that is not load-bearing is a guard
    that will one day refuse something legitimate.

    A third trial used to live here -- a concentrated force on a face -- on the
    assumption that CAE refuses it. CAE does; this pipeline never asks CAE.
    It is now its own item, one line up.
    """
    trials = [
        ("pressure_in_a_frequency_step",
         _spec([{"call": "FrequencyStep", "name": {"literal": "Modes"},
                 "previous": {"literal": "Initial"}, "numEigen": 3}],
               [_fix(), _pressure(step="Modes")])),
        ("createStepName_that_is_not_a_step",
         _spec([_static()], [_fix(), _pressure(step="Typo")])),
    ]
    rows = {}
    problems = []
    for name, spec in trials:
        out = _build(work / name, spec)
        evidence = _evidence(out)
        loud = ("GENERIC_FAILED" in evidence or "Abaqus Error" in evidence
                or "invalid geometry" in evidence
                or "Invalid load" in evidence
                or "does not exist" in evidence)
        rows[name] = {"loud": loud, "line": _line(out, "GENERIC_FAILED")
                      or (out.get("error") or "")[-260:]}
        if not loud:
            problems.append("%s was accepted quietly: %s" % (name,
                                                             evidence[-500:]))
    return {
        "id": "loads_abaqus_refuses_these_itself",
        "status": "pass" if not problems else "fail",
        "trials": rows,
        "note": "measured: 'Invalid load for given step type.' and 'The "
                "specified step either does not exist or is the Initial "
                "step.' Neither needs a guard here.",
        "problems": problems,
    }


# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path,
                    default=ROOT / "artifacts" / "generic_load_check"
                    / "report.json")
    ap.add_argument("--work", type=Path, default=None)
    args = ap.parse_args()

    work = args.work or (ROOT / "artifacts" / "generic_load_check")
    work.mkdir(parents=True, exist_ok=True)
    started = time.time()

    names = ("loads_dispatched_static_matches_the_named_form",
             "loads_a_frequency_step_is_now_expressible",
             "loads_a_stated_point_count_gives_the_load_that_was_meant",
             "loads_the_magnitude_is_written_at_every_node",
             "loads_a_multi_node_cload_without_a_stated_count_is_refused",
             "loads_a_wrong_point_count_is_refused",
             "loads_a_face_region_slips_past_caes_own_guard",
             "loads_step_order_is_asserted",
             "loads_reversed_steps_solve_to_the_wrong_answer",
             "loads_abaqus_refuses_these_itself")

    if not check_abaqus():
        reason = ("Abaqus not found (set ABAQUS_AGENT_ABAQUS_CMD or put "
                  "abaqus.bat on PATH)")
        items = [_skipped(name, reason) for name in names]
        release = None
    else:
        release = detect_abaqus_release()
        stated = check_stated_total(work)
        items = [check_static(work), check_frequency(work), stated,
                 check_four_times(work, stated), check_unstated_count(work),
                 check_wrong_count(work), check_face_slips_past_cae(work),
                 check_step_order(work), check_reversed_solves(work),
                 check_already_loud(work)]

    failed = [i for i in items if i["status"] == "fail"]
    report = {
        "generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "abaqus_release": release,
        "seconds": round(time.time() - started, 1),
        "theory": {"udl_tip_mm": -UDL_TIP, "point_tip_mm": -POINT_TIP,
                   "first_mode_hz": FIRST_MODE_HZ},
        "overall": "fail" if failed else "pass",
        "items": items,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
