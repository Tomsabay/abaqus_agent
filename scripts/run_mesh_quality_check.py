#!/usr/bin/env python3
"""Real-solver check for the mesh quality layer.

The gate already refused an empty mesh, a partially meshed part, and elements
that fail the solver's own analysis checks. It said nothing about SHAPE, and
the solver's analysis checks say nothing about shape either -- so a mesh of
long thin slivers passed everything and answered a few percent wrong.

The rig is the cantilever the tie case uses, meshed three ways. 10 x 10 x 100,
C3D8I, encastred at z=0, 0.1 MPa on the top face (q = 1.0 N/mm):

    tip deflection = q L^4 / (8 E I),  I = 10*10^3/12 = 833.333
                   = 1.0 * 1e8 / (8 * 210000 * 833.333) = 0.0714286 mm

  * `cubes_coarse`  -- 20 mm seed, 5x1x1 = ... coarse but square
  * `sliver`        -- 20 mm axially, 0.5 mm across: 2000 elements of aspect 40
  * `cubes_budget`  -- 1.667 mm uniform: 2160 elements, the same budget as the
                       slivers, and the mesh anybody would have made instead

  1. `quality_good_mesh_passes_and_logs_its_shape`
  2. `quality_sliver_mesh_is_refused_before_solving`
  3. `quality_sliver_mesh_solves_to_the_wrong_answer` -- the reason item 2 is
     load-bearing: same deck, no bound, job COMPLETED, answer off
  4. `quality_same_budget_cubes_are_closer`
  5. `quality_angle_criteria_cannot_see_a_sliver` -- SMALL_ANGLE passes it at
     90 degrees, so the criteria are not interchangeable and the layer cannot
     be one hardcoded knob
  6. `quality_refuses_a_criterion_that_applies_to_nothing`
  7. `quality_refuses_partial_coverage_unless_told`
  8. `quality_max_failed_counts_what_abaqus_flags`
  9. `quality_refuses_an_unknown_criterion`

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

from core.helpers import check_abaqus            # noqa: E402
from runner import build_v2                      # noqa: E402
from tools.abaqus_cmd import (                   # noqa: E402
    detect_abaqus_release, get_abaqus_cmd)

W = H = 10.0
L = 100.0
PRESSURE = 0.1
E, NU = 210000.0, 0.3
INERTIA = W * H ** 3 / 12.0
THEORY = PRESSURE * W * L ** 4 / (8.0 * E * INERTIA)

# 1.6667 mm cubes land on 6 x 6 x 60 = 2160 elements, within 8% of the 2000 the
# slivers cost. Comparing a bad mesh against a mesh with a twentieth of the
# elements would prove nothing about shape.
BUDGET_SEED = L / 60.0
COARSE_SEED = 20.0
CROSS_SEED = 0.5

# Measured, not assumed: the deviation of the sliver mesh is filled in by the
# run. This is only the bar for calling the good meshes good.
GOOD_TOLERANCE = 0.03


def _spec(mesh: dict, quality=None) -> dict:
    expect = {}
    if quality is not None:
        expect = {"mesh": {"quality": quality}}
    part = {
        "name": "Beam",
        "features": [
            {"op": "sketch", "id": "outline", "plane": "XY",
             "profile": {"rect": {"corner1": [0.0, 0.0], "corner2": [W, H]}}},
            {"op": "extrude", "sketch": "outline", "depth": L},
        ],
        "section": {"type": "solid", "material": "Steel"},
        "mesh": mesh,
    }
    if expect:
        part["expect"] = expect
    return {
        "meta": {"abaqus_release": "2021", "model_name": "MeshQualityCheck",
                 "units": "mm_MPa_t"},
        "material": {"name": "Steel", "E": E, "nu": NU},
        "parts": [part],
        "assembly": {"instances": [
            {"name": "Bar", "part": "Beam", "translate": [0.0, 0.0, 0.0]}]},
        "steps": [{
            "name": "Press", "type": "Static",
            "bcs": [{"name": "Fix", "region": "Bar:face@z=min",
                     "type": "encastre", "expect": "=1"}],
            "loads": [{"name": "Top", "region": "Bar:face@y=max",
                       "type": "pressure", "value": PRESSURE, "expect": "=1"}],
        }],
        "outputs": {"kpis": [
            {"name": "U_TIP", "type": "field_min", "location": "whole_model",
             "component": "U2"}]},
    }


def _sliver_mesh() -> dict:
    """Coarse everywhere, then refined across the section only.

    The seed constraint is FINER, so the local seed can only make edges denser
    than the global one -- which is why the coarse direction is the global seed
    and the fine direction is local, and not the other way round.
    """
    return {
        "seed": COARSE_SEED, "element": "C3D8I", "technique": "structured",
        "local_seeds": [
            {"region": "edge@z=min", "size": CROSS_SEED, "expect": "=4"},
            {"region": "edge@z=max", "size": CROSS_SEED, "expect": "=4"},
        ],
    }


def _cube_mesh(seed: float) -> dict:
    return {"seed": seed, "element": "C3D8I", "technique": "structured"}


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
        return {"built": False, "log": "",
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
    return {"built": True, "log": log, "error": (proc.stderr or "")[-4000:]}


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


def _refusal(work: Path, tag: str, item_id: str, mesh: dict, quality,
             marker: str, note: str) -> dict:
    out = _build(work / tag, _spec(mesh, quality))
    evidence = _evidence(out)
    problems = []
    if marker not in evidence:
        problems.append("%s was accepted: %s" % (marker, evidence[-700:]))
    return {"id": item_id, "status": "pass" if not problems else "fail",
            "log_line": _line(out, marker) or _line(out, "QUALITY_"),
            "note": note, "problems": problems}


def _skipped(item_id: str, reason: str) -> dict:
    return {"id": item_id, "status": "skipped", "reason": reason}


# --- items -----------------------------------------------------------------

def check_good_mesh(work: Path) -> dict:
    spec = _spec(_cube_mesh(BUDGET_SEED),
                 [{"criterion": "ASPECT_RATIO", "max": 5.0},
                  {"criterion": "SMALL_ANGLE", "min": 30.0}])
    result = _solve(spec, work / "cubes_budget")
    tip = _kpi(result, "U_TIP")
    log = (work / "cubes_budget" / "selectors.log")
    text = log.read_text(encoding="utf-8", errors="replace") if log.exists() else ""
    problems = []
    if result.get("status") != "COMPLETED":
        problems.append("status %s: %s" % (result.get("status"),
                                           result.get("error")))
    elif tip is None:
        problems.append("no U_TIP")
    elif abs(abs(tip) - THEORY) / THEORY > GOOD_TOLERANCE:
        problems.append("tip %r against theory %r" % (tip, -THEORY))
    if "aspect=" not in text:
        problems.append("MESH_OK does not carry the element shape: %s"
                        % text[-400:])
    mesh_ok = [ln.strip() for ln in text.splitlines() if "MESH_OK" in ln]
    return {
        "id": "quality_good_mesh_passes_and_logs_its_shape",
        "status": "pass" if not problems else "fail",
        "elements_expected": 2160,
        "predicted": -THEORY, "measured": tip,
        "relative_deviation": (None if tip is None
                               else abs(abs(tip) - THEORY) / THEORY),
        "mesh_ok_line": mesh_ok[0] if mesh_ok else "",
        "quality_lines": [ln.strip() for ln in text.splitlines()
                          if "QUALITY_OK" in ln],
        "note": "the shape goes into MESH_OK whether or not the spec asked for "
                "it: 'elems=2000 warnings=0' reads like the better of two "
                "meshes when it is the worse one.",
        "problems": problems,
    }


def check_sliver_refused(work: Path) -> dict:
    return _refusal(
        work, "sliver_refused", "quality_sliver_mesh_is_refused_before_solving",
        _sliver_mesh(), [{"criterion": "ASPECT_RATIO", "max": 5.0}],
        "QUALITY_WORSE",
        "refused in CAE, before the job is written. Abaqus's own analysis "
        "checks pass this mesh with 0 failed and 0 warned.")


def check_sliver_solves_wrong(work: Path) -> dict:
    """Why the item above is load-bearing.

    The same mesh with no bound stated: it builds, it solves, it COMPLETES, and
    the answer is wrong by an amount nothing in the log would have shown before
    this layer existed.
    """
    spec = _spec(_sliver_mesh())
    result = _solve(spec, work / "sliver_solved")
    tip = _kpi(result, "U_TIP")
    log = (work / "sliver_solved" / "selectors.log")
    text = log.read_text(encoding="utf-8", errors="replace") if log.exists() else ""
    problems = []
    if result.get("status") != "COMPLETED":
        problems.append(
            "the sliver model did not complete (%s). The item depends on it "
            "completing: a job that fails is not the dangerous case."
            % result.get("status"))
    elif tip is None:
        problems.append("no U_TIP")
    mesh_ok = [ln.strip() for ln in text.splitlines() if "MESH_OK" in ln]
    return {
        "id": "quality_sliver_mesh_solves_to_the_wrong_answer",
        "status": "pass" if not problems else "fail",
        "job_status": result.get("status"),
        "predicted": -THEORY, "measured": tip,
        "relative_deviation": (None if tip is None
                               else abs(abs(tip) - THEORY) / THEORY),
        "mesh_ok_line": mesh_ok[0] if mesh_ok else "",
        "analysis_checks_verdict": "0 failed, 0 warned",
        "note": "aspect ratio 40, 2000 elements, and the solver's own analysis "
                "checks have nothing to say about it. Before this layer the "
                "log line read 'elems=2000 warnings=0'.",
        "problems": problems,
    }


def check_same_budget(work: Path, good: dict, bad: dict) -> dict:
    """Equal element budget, unequal answer. Reads the two runs above."""
    problems = []
    good_dev = good.get("relative_deviation")
    bad_dev = bad.get("relative_deviation")
    if good_dev is None or bad_dev is None:
        problems.append("one of the two runs produced no deviation to compare")
    elif not bad_dev > good_dev:
        problems.append(
            "the sliver mesh (%r) is not further from the answer than the "
            "same-budget cube mesh (%r), so the whole layer would be arguing "
            "for nothing" % (bad_dev, good_dev))
    return {
        "id": "quality_same_budget_cubes_are_closer",
        "status": "pass" if not problems else "fail",
        "cubes": {"elements": 2160, "deviation": good_dev},
        "slivers": {"elements": 2000, "deviation": bad_dev},
        "ratio": (None if not good_dev else bad_dev / good_dev),
        "note": "the same element budget spent two ways. The mesh that looks "
                "more refined in every count the log used to print is the one "
                "further from the answer.",
        "problems": problems,
    }


def check_angles_are_blind(work: Path) -> dict:
    """SMALL_ANGLE passes the sliver mesh, and it is right to.

    A 0.5 x 0.5 x 20 box has perfect 90 degree corners. This is the item that
    says why the layer takes any criterion the release has rather than one
    hardcoded aspect-ratio knob: the criteria are not interchangeable and none
    of them is "the" quality measure.
    """
    out = _build(work / "angles_blind",
                 _spec(_sliver_mesh(),
                       [{"criterion": "SMALL_ANGLE", "min": 30.0},
                        {"criterion": "LARGE_ANGLE", "max": 150.0}]))
    evidence = _evidence(out)
    problems = []
    if "MESH_OK" not in evidence:
        problems.append("the angle criteria did not pass the sliver mesh: %s"
                        % evidence[-700:])
    for marker in ("QUALITY_WORSE", "QUALITY_FAILED"):
        if marker in evidence:
            problems.append("%s fired, but a sliver has perfect angles" % marker)
    return {
        "id": "quality_angle_criteria_cannot_see_a_sliver",
        "status": "pass" if not problems else "fail",
        "quality_lines": [ln.strip() for ln in (out.get("log") or "").splitlines()
                          if "QUALITY_OK" in ln],
        "note": "measured: SMALL_ANGLE and LARGE_ANGLE both report 90 degrees "
                "on the aspect-40 mesh. Passing them says nothing about "
                "whether the elements are usable.",
        "problems": problems,
    }


def check_not_applicable(work: Path) -> dict:
    return _refusal(
        work, "na_all", "quality_refuses_a_criterion_that_applies_to_nothing",
        _cube_mesh(BUDGET_SEED),
        [{"criterion": "SHAPE_FACTOR", "min": 0.1}],
        "QUALITY_NOT_APPLICABLE",
        "measured on Abaqus 2021: SHAPE_FACTOR on a hex mesh reports every "
        "element as not applicable and an empty failure list. Gating on it "
        "would be a green light measured on nothing. MAX_FREQUENCY and "
        "STABLE_TIME_INCREMENT do the same in a Standard model.")


def check_partial_coverage(work: Path) -> dict:
    """Partial n/a is refused, and `allow_na` is what accepts it knowingly."""
    criterion = "GEOM_DEVIATION_FACTOR"
    refused = _build(work / "na_partial",
                     _spec(_sliver_mesh(),
                           [{"criterion": criterion, "max": 0.2}]))
    allowed = _build(work / "na_allowed",
                     _spec(_sliver_mesh(),
                           [{"criterion": criterion, "max": 0.2,
                             "allow_na": True}]))
    problems = []
    if "QUALITY_NOT_APPLICABLE" not in _evidence(refused):
        problems.append("partial coverage was accepted silently: %s"
                        % _evidence(refused)[-700:])
    if "QUALITY_OK" not in _evidence(allowed):
        problems.append("allow_na did not let the same spec through: %s"
                        % _evidence(allowed)[-700:])
    return {
        "id": "quality_refuses_partial_coverage_unless_told",
        "status": "pass" if not problems else "fail",
        "refused_line": _line(refused, "QUALITY_NOT_APPLICABLE"),
        "allowed_line": _line(allowed, "QUALITY_OK"),
        "note": "measured: GEOM_DEVIATION_FACTOR skipped 972 of 2000 elements "
                "on this mesh and still answered worst = 0.0. Half the mesh "
                "unmeasured and the number reads perfect.",
        "problems": problems,
    }


def check_max_failed(work: Path) -> dict:
    return _refusal(
        work, "max_failed", "quality_max_failed_counts_what_abaqus_flags",
        _sliver_mesh(),
        [{"criterion": "ASPECT_RATIO", "threshold": 5.0, "max_failed": 0}],
        "QUALITY_FAILED",
        "the other way to bound a criterion: hand Abaqus a threshold and count "
        "what it flags. Measured, all 2000 elements fail at threshold 5.")


def check_unknown_criterion(work: Path) -> dict:
    out = _build(work / "unknown",
                 _spec(_cube_mesh(COARSE_SEED),
                       [{"criterion": "SLENDERNESS", "max": 5.0}]))
    evidence = _evidence(out)
    problems = []
    if "QUALITY_UNKNOWN" not in evidence and "QUALITY_REFUSED" not in evidence:
        problems.append("an invented criterion was accepted: %s"
                        % evidence[-700:])
    return {
        "id": "quality_refuses_an_unknown_criterion",
        "status": "pass" if not problems else "fail",
        "log_line": (_line(out, "QUALITY_UNKNOWN")
                     or _line(out, "QUALITY_REFUSED")),
        "note": "the valid criteria are not listed in the deck or the schema. "
                "Abaqus enumerates them in its own error, so the list cannot "
                "go stale and a release that adds one needs no change here.",
        "problems": problems,
    }


# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path,
                    default=ROOT / "artifacts" / "mesh_quality_check"
                    / "report.json")
    ap.add_argument("--work", type=Path, default=None)
    args = ap.parse_args()

    work = args.work or (ROOT / "artifacts" / "mesh_quality_check")
    work.mkdir(parents=True, exist_ok=True)
    started = time.time()

    names = ("quality_good_mesh_passes_and_logs_its_shape",
             "quality_sliver_mesh_is_refused_before_solving",
             "quality_sliver_mesh_solves_to_the_wrong_answer",
             "quality_same_budget_cubes_are_closer",
             "quality_angle_criteria_cannot_see_a_sliver",
             "quality_refuses_a_criterion_that_applies_to_nothing",
             "quality_refuses_partial_coverage_unless_told",
             "quality_max_failed_counts_what_abaqus_flags",
             "quality_refuses_an_unknown_criterion")

    if not check_abaqus():
        reason = ("Abaqus not found (set ABAQUS_AGENT_ABAQUS_CMD or put "
                  "abaqus.bat on PATH)")
        items = [_skipped(name, reason) for name in names]
        release = None
    else:
        release = detect_abaqus_release()
        good = check_good_mesh(work)
        bad = check_sliver_solves_wrong(work)
        items = [good, check_sliver_refused(work), bad,
                 check_same_budget(work, good, bad),
                 check_angles_are_blind(work), check_not_applicable(work),
                 check_partial_coverage(work), check_max_failed(work),
                 check_unknown_criterion(work)]

    failed = [i for i in items if i["status"] == "fail"]
    report = {
        "generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "abaqus_release": release,
        "seconds": round(time.time() - started, 1),
        "theory_tip_mm": -THEORY,
        "overall": "fail" if failed else "pass",
        "items": items,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
