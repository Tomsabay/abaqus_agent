#!/usr/bin/env python3
"""Real-solver check for positioning by constraint.

`instances` positions by arithmetic: every position is a vector somebody worked
out by hand. Abaqus's own way is to say "this face against that face" and let
the kernel compute it -- FaceToFace, ParallelFace, EdgeToEdge, CoincidentPoint.
Those were reachable in the dialect and could not work, for a reason nothing
downstream could see.

Measured on Abaqus 2021 (artifacts/probe_position_seq/probe_out.txt, 12 models,
one CAE session):

    handed a GeomSequence   returns None, adds nothing to a.features, grows no
                            repository, moves nothing -- before and after
                            a.regenerate(). No exception.
    handed the entity       returns a named Feature ('Face to Face-1'), grows
                            a.features 3->4, and moves the instance:
                            FaceToFace 40.0, ParallelFace 10.0,
                            EdgeToEdge 30.0, CoincidentPoint 30.0 mm.

`{select:}` can only ever compile to the first shape: core/selectors.py returns
what getByBoundingBox produced, never an entity out of it. So a spec written
the obvious way built a deck that meshed, solved and reported COMPLETED with
the part still 40 mm from where the author said to put it.

The same run measured why the guard reads the RETURN VALUE rather than "did
anything change": makeIndependent and seedPartInstance also change no
repository and move nothing, and they are the documented way to mesh a boolean
result. A rule about change would refuse the escape hatch.

Items:

  1. `position_one_moves_the_instance` -- FaceToFace through {one:}, end to
     end, checked by assembly.expect.at against the joined position.
  2. `position_expect_at_is_not_vacuous` -- the same run with the centroid
     stated where the block STARTED must abort. Without this, item 1 passes
     for a check that is not looking.
  3. `position_a_sequence_is_refused` -- the same spec with {select:} must
     abort with CALL_RECORDED_NOTHING before anything solves.
  4. `position_a_set_from_one_face_still_builds` -- the false-refusal
     counterexample. `a.Set(faces=<sequence of one>)` is exactly right; an
     earlier generation-time version of the guard refused it, and the repo's
     own suite caught that. The guard is still emitted here and must not fire.

Nothing is written inside the repository: everything runs under %TEMP%.
Exit codes: 0 = nothing failed (no Abaqus => "skipped", still 0);
            1 = at least one item ran and failed.
"""

from __future__ import annotations

import argparse
import copy
import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.helpers import check_abaqus            # noqa: E402
from runner import build_v2                      # noqa: E402
from tools.abaqus_cmd import (                   # noqa: E402
    detect_abaqus_release, get_abaqus_cmd)

# Two 10 mm cubes. Fixed spans 0..10; Mover starts 40 mm away in +x, centroid
# (45, 5, 5). FaceToFace(flip=OFF, clearance=0) makes the two faces COINCIDENT
# with opposed normals, so Mover lands back on 0..10 and its centroid ends at
# (5, 5, 5) -- a 40 mm move. Measured, not derived: this is the same number the
# probe reports as FTF_single_BBOX_AFTER (0,0,0)..(10,10,10), and it is the
# whole point of the gate that the number comes from Abaqus rather than from
# somebody's arithmetic. The rig never solves, so the two blocks ending up in
# the same place costs nothing here.
SIDE = 10.0
START_X = 40.0
JOINED_CENTROID = [5.0, 5.0, 5.0]
START_CENTROID = [45.0, 5.0, 5.0]

BLOCK = {
    "name": "Blk",
    "features": [
        {"op": "sketch", "id": "outline", "plane": "XY",
         "profile": {"rect": {"corner1": [0.0, 0.0], "corner2": [SIDE, SIDE]}}},
        {"op": "extrude", "sketch": "outline", "depth": SIDE},
    ],
    "section": {"type": "solid", "material": "Steel"},
    "mesh": {"seed": 5.0, "element": "C3D8R"},
}


def _spec(movable, fixed, at=None, extra_ops=()):
    operations = [{"call": "FaceToFace",
                   "movablePlane": copy.deepcopy(movable),
                   "fixedPlane": copy.deepcopy(fixed),
                   "flip": "OFF", "clearance": 0.0}]
    operations.extend(copy.deepcopy(op) for op in extra_ops)
    assembly = {
        "instances": [
            {"name": "Fixed", "part": "Blk", "translate": [0.0, 0.0, 0.0]},
            {"name": "Mover", "part": "Blk", "translate": [START_X, 0.0, 0.0]},
        ],
        "operations": operations,
    }
    if at is not None:
        assembly["expect"] = {"instances": 2, "at": copy.deepcopy(at)}
    return {
        "meta": {"abaqus_release": "2021", "model_name": "PositionCheck",
                 "units": "mm_MPa_t",
                 "description": "positioning by constraint, gate rig"},
        "material": {"name": "Steel", "E": 210000.0, "nu": 0.3},
        "parts": [copy.deepcopy(BLOCK)],
        "assembly": assembly,
        "steps": [{"name": "Load", "type": "Static",
                   "bcs": [{"name": "Fix", "type": "encastre",
                            "region": "Fixed:face@x=min", "expect": "=1"}]}],
        "outputs": {"kpis": [{"name": "U", "type": "field_min",
                              "location": "whole_model", "component": "U2"}]},
    }


def _build(work: Path, spec: dict) -> dict:
    """Generate and run the build script; return rc plus the selectors log."""
    work = work.resolve()
    work.mkdir(parents=True, exist_ok=True)
    log_path = work / "selectors.log"
    if log_path.exists():
        log_path.unlink()
    try:
        text = build_v2.generate_script(spec)
    except Exception as exc:
        return {"rc": None, "log": "",
                "error": "%s: %s" % (type(exc).__name__, exc)}
    script = work / "build_model_script.py"
    script.write_text(text, encoding="utf-8")
    proc = subprocess.run(
        [get_abaqus_cmd(), "cae", "noGUI=" + script.name, "--", str(work), "spec"],
        cwd=str(work), capture_output=True, text=True,
        errors="replace", encoding="utf-8", stdin=subprocess.DEVNULL,
        timeout=1800)
    log = (log_path.read_text(encoding="utf-8", errors="replace")
           if log_path.exists() else "")
    return {"rc": proc.returncode, "log": log, "error": (proc.stderr or "")[-4000:]}


def _line(out: dict, prefix: str) -> str:
    for line in out["log"].splitlines():
        if line.startswith(prefix):
            return line
    return ""


def _inp_written(work: Path) -> bool:
    return any(work.glob("*.inp"))


def check_one_moves_the_instance(work: Path) -> dict:
    run = work / "one_moves"
    out = _build(run, _spec(
        {"one": "Mover:face@x=min"}, {"one": "Fixed:face@x=max"},
        at=[{"instance": "Mover", "centroid": JOINED_CENTROID, "tol": 0.01}]))

    problems: list[str] = []
    placed = _line(out, "EXPECT_OK: Mover at")
    if not _inp_written(run):
        problems.append("no .inp was written: %s"
                        % (out.get("error") or out["log"][-400:]))
    if not placed:
        problems.append("no EXPECT_OK line for Mover; the position check did not pass: %s"
                        % out["log"][-400:])
    if "FaceToFace" not in out["log"]:
        problems.append("the constraint was never dispatched")
    return {
        "id": "position_one_moves_the_instance",
        "status": "pass" if not problems else "fail",
        "identity": "two 10 mm cubes, Mover parked at x=%.1f, joined by "
                    "FaceToFace(clearance=0) written with {one:}" % START_X,
        "expected_centroid": JOINED_CENTROID,
        "placed_line": placed,
        "problems": problems,
    }


def check_expect_at_is_not_vacuous(work: Path) -> dict:
    """The same run, with the centroid stated where the block STARTED."""
    run = work / "at_not_vacuous"
    out = _build(run, _spec(
        {"one": "Mover:face@x=min"}, {"one": "Fixed:face@x=max"},
        at=[{"instance": "Mover", "centroid": START_CENTROID, "tol": 0.01}]))

    problems: list[str] = []
    refusal = _line(out, "EXPECT_PLACED: instance Mover")
    if _inp_written(run):
        problems.append("an .inp was written for an instance that is 30 mm "
                        "from where the spec says it is")
    if not refusal:
        problems.append("no EXPECT_PLACED refusal: expect.at passed a position it "
                        "should have caught, so item 1 proves nothing")
    return {
        "id": "position_expect_at_is_not_vacuous",
        "status": "pass" if not problems else "fail",
        "identity": "same spec, expect.at stating the pre-constraint centroid "
                    "%s instead of %s" % (START_CENTROID, JOINED_CENTROID),
        "refusal_line": refusal[:300],
        "problems": problems,
    }


def check_a_sequence_is_refused(work: Path) -> dict:
    run = work / "sequence_refused"
    out = _build(run, _spec(
        {"select": "Mover:face@x=min"}, {"one": "Fixed:face@x=max"},
        at=[{"instance": "Mover", "centroid": JOINED_CENTROID, "tol": 0.01}]))

    problems: list[str] = []
    refusal = _line(out, "CALL_RECORDED_NOTHING")
    if _inp_written(run):
        problems.append("an .inp was written for a constraint that did nothing")
    if not refusal:
        problems.append("no CALL_RECORDED_NOTHING line: the no-op was silent, "
                        "which is the defect this item exists for. Log tail: %s"
                        % out["log"][-400:])
    elif "movablePlane" not in refusal:
        problems.append("the refusal does not name the argument: %s" % refusal)
    elif "{one:" not in refusal:
        problems.append("the refusal does not name the way out: %s" % refusal)
    return {
        "id": "position_a_sequence_is_refused",
        "status": "pass" if not problems else "fail",
        "identity": "the same spec with {select: \"Mover:face@x=min\"}, which "
                    "compiles to a sequence of exactly one",
        "refusal_line": refusal[:400],
        "problems": problems,
    }


def check_a_set_from_one_face_still_builds(work: Path) -> dict:
    """The counterexample. A Set wants the sequence, and must not be refused."""
    run = work / "set_not_refused"
    out = _build(run, _spec(
        {"one": "Mover:face@x=min"}, {"one": "Fixed:face@x=max"},
        at=[{"instance": "Mover", "centroid": JOINED_CENTROID, "tol": 0.01}],
        extra_ops=[{"call": "Set", "name": {"literal": "RIM"},
                    "faces": {"select": "Fixed:face@y=max"}}]))

    problems: list[str] = []
    if not _inp_written(run):
        problems.append("a Set built from a one-element sequence was refused "
                        "or failed: %s" % (out.get("error") or out["log"][-400:]))
    if _line(out, "CALL_RECORDED_NOTHING"):
        problems.append("the guard fired on a Set, which returns the Set it "
                        "made -- this is a false refusal")
    if not _line(out, "EXPECT_OK: Mover at"):
        problems.append("the positioning in the same spec stopped working")
    return {
        "id": "position_a_set_from_one_face_still_builds",
        "status": "pass" if not problems else "fail",
        "identity": "FaceToFace via {one:} plus a.Set(faces={select: one face})",
        "note": "an earlier generation-time version of the guard refused this; "
                "the repo's own suite caught it, which is why the guard reads "
                "the return value instead",
        "problems": problems,
    }


def check_the_default_tolerance_is_derived_in_the_kernel(work: Path) -> dict:
    """`at` with no `tol`, which is the only way that code path ever runs.

    An instance carries no radius to scale a tolerance against, and its size is
    not knowable until the assembly exists -- so when the spec states no `tol`,
    the generator emits None and `_expect_placed` derives
    max(1e-3, span * 2e-3) from the box it has to measure anyway. Every rig in
    this repository states a tolerance, so without this item that branch would
    ship having never run on Abaqus.

    Both halves are checked. The derived tolerance must accept a correctly
    placed instance, and it must still refuse a wrong one: 10 mm cubes give a
    span of 10 and a default of 0.02, so the 40 mm error the next line states
    is three orders of magnitude outside it.
    """
    run = work / "default_tol"
    out = _build(run, _spec(
        {"one": "Mover:face@x=min"}, {"one": "Fixed:face@x=max"},
        at=[{"instance": "Mover", "centroid": JOINED_CENTROID}]))
    wrong = _build(work / "default_tol_wrong", _spec(
        {"one": "Mover:face@x=min"}, {"one": "Fixed:face@x=max"},
        at=[{"instance": "Mover", "centroid": START_CENTROID}]))

    placed = _line(out, "EXPECT_OK: Mover at")
    refusal = _line(wrong, "EXPECT_PLACED: instance Mover")
    problems: list[str] = []
    if not _inp_written(run):
        problems.append("a correctly placed instance was refused by the "
                        "derived default: %s"
                        % (out.get("error") or out["log"][-400:]))
    if not placed:
        problems.append("no EXPECT_OK line, so the derived default never ran")
    elif "allowed" not in placed:
        problems.append("the margin was not logged, so nobody can see how "
                        "close this came to being refused: %s" % placed)
    if _inp_written(work / "default_tol_wrong"):
        problems.append("the derived default accepted an instance 40 mm from "
                        "where the spec says it is")
    elif "default, from a span of" not in refusal:
        problems.append("the refusal does not say the tolerance was derived "
                        "or what it was derived from: %s" % refusal[:300])

    return {
        "id": "position_default_tolerance_is_derived_from_the_instance",
        "status": "pass" if not problems else "fail",
        "identity": "10 mm cubes -> span 10 -> max(1e-3, 10*2e-3) = 0.02 mm, "
                    "computed in the kernel because the span does not exist "
                    "until the assembly does",
        "expected_centroid": JOINED_CENTROID,
        "placed_line": placed,
        "refusal_line": refusal[:400],
        "problems": problems,
    }


CHECKS = (
    check_one_moves_the_instance,
    check_expect_at_is_not_vacuous,
    check_a_sequence_is_refused,
    check_a_set_from_one_face_still_builds,
    check_the_default_tolerance_is_derived_in_the_kernel,
)
ITEM_IDS = (
    "position_one_moves_the_instance",
    "position_expect_at_is_not_vacuous",
    "position_a_sequence_is_refused",
    "position_a_set_from_one_face_still_builds",
    "position_default_tolerance_is_derived_from_the_instance",
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json-out", type=Path, default=None)
    parser.add_argument("--work-dir", type=Path, default=None)
    parser.add_argument("--keep", action="store_true")
    args = parser.parse_args(argv)

    if args.work_dir is not None:
        work = args.work_dir
        work.mkdir(parents=True, exist_ok=True)
        keep = True
    else:
        work = Path(tempfile.mkdtemp(prefix="assembly_position_check_"))
        keep = args.keep

    started = time.time()
    if not check_abaqus():
        items = [{"id": item, "status": "skipped",
                  "reason": "Abaqus not found (set ABAQUS_AGENT_ABAQUS_CMD)"}
                 for item in ITEM_IDS]
    else:
        items = [check(work) for check in CHECKS]
    elapsed = time.time() - started

    statuses = [item["status"] for item in items]
    if "fail" in statuses:
        overall = "fail"
    elif all(s == "skipped" for s in statuses):
        overall = "skipped"
    elif "skipped" in statuses:
        overall = "partial"
    else:
        overall = "pass"

    failed = overall == "fail"
    if not keep and not failed and work.exists():
        shutil.rmtree(work, ignore_errors=True)

    report = {
        "schema": "assembly_position_check/1",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "abaqus_release": detect_abaqus_release() if check_abaqus() else None,
        "work_dir": str(work),
        "work_dir_kept": keep or failed,
        "seconds": round(elapsed, 1),
        "overall": overall,
        "items": items,
    }
    for item in items:
        print("  %-42s %s%s" % (
            item["id"], item["status"],
            "" if not item.get("problems") else
            "  <- %s" % "; ".join(item["problems"])[:200]))
    text = json.dumps(report, indent=2, ensure_ascii=False)
    print(text)
    if args.json_out is not None:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(text + "\n", encoding="utf-8")
    return 1 if overall == "fail" else 0


if __name__ == "__main__":
    sys.exit(main())
