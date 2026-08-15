#!/usr/bin/env python3
"""Real-solver check for the generic part layer.

The named ops (`op: sketch` / `extrude` / `cut_extrude`) can only build shapes
somebody already wrote a branch for. Abaqus exposes 292 callables on Part and 71
on ConstrainedSketch, and the lists grow every release, so this layer lets a
spec name the method directly:

    - call: BaseSolidRevolve
      sketch: {sketch: profile}
      angle: 360.0
      flipRevolveDirection: "OFF"

``getattr(part, name)(**kwargs)`` does the rest. That is safe only because every
way of getting it wrong was measured to be loud -- unknown method, unknown
keyword, wrong type -- and because what it gives up (a schema that knows what
each op was supposed to produce) is replaced by an `expect:` block checked
against the built geometry.

The items below are arithmetic identities and mutations, in that order:

  1. `generic_flange_volume` - a revolved flange, entirely from data, against
     pi*(30^2-4^2)*10 + pi*(10^2-4^2)*15.
  2. `generic_fillet_uses_the_tuple_shim` - Round(edgeList=) refuses the
     GeomSequence that Set(edges=) requires. The shim converts and retries; the
     resulting volume change has a closed form, 2*pi*r^3*(5/3 - pi/2), which
     falls out of Pappus and is independent of the corner radius because one of
     the two filleted corners is concave and the other convex.
  3. `generic_cut_through_a_datum_plane` - a cut on a part whose top face is an
     annulus, so there is no straight edge to orient a sketch against and the
     named cut_extrude recipe cannot work at all.
  4. `generic_refuses_an_unknown_method`
  5. `generic_refuses_an_unknown_keyword`
  6. `generic_refuses_a_wrong_volume`
  7. `generic_refuses_a_cut_that_missed` - holes moved off the solid. Measured:
     Abaqus does nothing, raises nothing and exits 0.
  8. `generic_refuses_a_transposed_cut` - the same holes with the sketch
     oriented against the wrong principal axis. This one runs the build TWICE:
     once with an `expect` of volume and counts, which PASSES because a
     transposition changes neither, and once with `expect.cylinders`, which
     catches it. The pass is the point -- it is the evidence that positions
     have to be stated.
  9. `generic_matches_the_named_op` - the same plate built both ways.
 10. `generic_part_solves_end_to_end` - a generically built plate through the
     whole pipeline, checked on equilibrium: total reaction = pressure x area.

Exit codes: 0 = nothing failed (no Abaqus => "skipped", still 0);
            1 = at least one item ran and failed.
"""

from __future__ import annotations

import argparse
import copy
import json
import math
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

# --- the flange, and what it should measure --------------------------------
#
# Profile revolved about x = 0: a 30 mm flange 10 mm thick, a 10 mm boss up to
# y = 25, bored 4 mm all the way through.
R_OUTER, R_BOSS, R_BORE = 30.0, 10.0, 4.0
Y_FLANGE, Y_TOP = 10.0, 25.0

FLANGE_VOLUME = (math.pi * (R_OUTER ** 2 - R_BORE ** 2) * Y_FLANGE
                 + math.pi * (R_BOSS ** 2 - R_BORE ** 2) * (Y_TOP - Y_FLANGE))

FILLET_R = 2.0
# Pappus, applied to the sliver a fillet adds at a concave corner and removes at
# a convex one. Both filleted edges sit at radius R_BOSS, and the R terms cancel
# exactly, which is why this is a number and not a function of the geometry:
#
#   concave  integral x dA = r^2(R + r/2) - (pi r^2/4)(R + r) + r^3/3
#   convex   integral x dA = r^2(R - r/2) - (pi r^2/4)(R - r) - r^3/3
#   dV = 2 pi (concave - convex) = 2 pi r^3 (5/3 - pi/2)
FILLET_DELTA_V = 2.0 * math.pi * FILLET_R ** 3 * (5.0 / 3.0 - math.pi / 2.0)

BOLT_R, BOLT_PCD = 3.0, 20.0
BOLT_DELTA_V = -2.0 * math.pi * BOLT_R ** 2 * Y_FLANGE
# Measured: with the sketch oriented against XAXIS, sketch x maps to global z,
# so the holes land on the z axis at mid-depth of the flange.
BOLT_CENTROIDS = [(0.0, Y_FLANGE / 2.0, BOLT_PCD),
                  (0.0, Y_FLANGE / 2.0, -BOLT_PCD)]

PLATE_W, PLATE_L, PLATE_T = 60.0, 100.0, 5.0
PLATE_VOLUME = PLATE_W * PLATE_L * PLATE_T
PLATE_PRESSURE = 0.1
EQUILIBRIUM_TOLERANCE_REL = 1.0e-3

# A bore big enough that getCentroid()'s own tessellation error is larger than
# the flat 0.05 mm tolerance that `at_tol` used to default to. Measured on
# Abaqus 2021 in this plate: the centroid is exact at r = 4, 12, 50 and 100,
# 2.0e-06 out at r = 200, and 0.0709 out at r = 300. So 300 it is -- anything
# smaller and the item would pass without demonstrating anything.
#
# The position is asymmetric in x and y on purpose: a transposed hole has to
# land somewhere else, or the counterexample would also pass by accident.
BORE_SIDE, BORE_DEPTH, BORE_R = 900.0, 60.0, 300.0
BORE_CX, BORE_CY = 380.0, 470.0
BORE_SEED = 120.0
OLD_FLAT_TOL = 0.05

BORE_FEATURES = [
    {"op": "sketch", "id": "outline", "plane": "XY",
     "profile": {"rect": {"corner1": [0.0, 0.0],
                          "corner2": [BORE_SIDE, BORE_SIDE]}}},
    {"op": "extrude", "sketch": "outline", "depth": BORE_DEPTH},
    {"op": "sketch", "id": "bore", "plane": "XY",
     "profile": {"circle": {"center": [BORE_CX, BORE_CY], "r": BORE_R}}},
    {"op": "cut_extrude", "sketch": "bore", "depth": BORE_DEPTH},
]

FLANGE_PROFILE = [
    {"call": "ConstructionLine", "point1": [0.0, 0.0], "point2": [0.0, 10.0]},
    {"call": "Line", "point1": [R_BORE, 0.0], "point2": [R_OUTER, 0.0]},
    {"call": "Line", "point1": [R_OUTER, 0.0], "point2": [R_OUTER, Y_FLANGE]},
    {"call": "Line", "point1": [R_OUTER, Y_FLANGE], "point2": [R_BOSS, Y_FLANGE]},
    {"call": "Line", "point1": [R_BOSS, Y_FLANGE], "point2": [R_BOSS, Y_TOP]},
    {"call": "Line", "point1": [R_BOSS, Y_TOP], "point2": [R_BORE, Y_TOP]},
    {"call": "Line", "point1": [R_BORE, Y_TOP], "point2": [R_BORE, 0.0]},
]

REVOLVE = [
    {"op": "sketch", "id": "profile", "entities": FLANGE_PROFILE},
    {"call": "BaseSolidRevolve", "sketch": {"sketch": "profile"},
     "angle": 360.0, "flipRevolveDirection": "OFF"},
]


def _drill(axis: str = "XAXIS", pcd: float = BOLT_PCD) -> list[dict]:
    """Two bolt holes, oriented by a datum plane and a datum axis.

    There is no other way to do this on this part. The top of the flange is an
    annulus, so every edge on it is a circle, and MakeSketchTransform needs
    something straight to orient against -- which is exactly what the named
    cut_extrude looks for and refuses to proceed without.
    """
    return [
        {"call": "DatumPlaneByPrincipalPlane", "principalPlane": "XZPLANE",
         "offset": Y_FLANGE, "as": "flangeTop"},
        {"call": "DatumAxisByPrincipalAxis", "principalAxis": axis,
         "as": "upAxis"},
        {"call": "MakeSketchTransform", "sketchPlane": {"datum": "flangeTop"},
         "sketchUpEdge": {"datum": "upAxis"}, "sketchPlaneSide": "SIDE1",
         "sketchOrientation": "RIGHT", "origin": [0.0, Y_FLANGE, 0.0],
         "as": "boltXf"},
        {"op": "sketch", "id": "bolts", "transform": {"ref": "boltXf"},
         "sheet_size": 200.0,
         "entities": [
             {"call": "CircleByCenterPerimeter", "center": [pcd, 0.0],
              "point1": [pcd + BOLT_R, 0.0]},
             {"call": "CircleByCenterPerimeter", "center": [-pcd, 0.0],
              "point1": [-pcd + BOLT_R, 0.0]},
         ]},
        {"call": "CutExtrude", "sketchPlane": {"datum": "flangeTop"},
         "sketchUpEdge": {"datum": "upAxis"}, "sketchPlaneSide": "SIDE1",
         "sketchOrientation": "RIGHT", "sketch": {"sketch": "bolts"},
         "depth": Y_FLANGE, "flipExtrudeDirection": "OFF"},
    ]


GENERIC_PLATE = [
    {"op": "sketch", "id": "outline", "entities": [
        {"call": "Line", "point1": [0.0, 0.0], "point2": [PLATE_W, 0.0]},
        {"call": "Line", "point1": [PLATE_W, 0.0], "point2": [PLATE_W, PLATE_T]},
        {"call": "Line", "point1": [PLATE_W, PLATE_T], "point2": [0.0, PLATE_T]},
        {"call": "Line", "point1": [0.0, PLATE_T], "point2": [0.0, 0.0]},
    ]},
    {"call": "BaseSolidExtrude", "sketch": {"sketch": "outline"},
     "depth": PLATE_L},
]

NAMED_PLATE = [
    {"op": "sketch", "id": "outline", "plane": "XY",
     "profile": {"rect": {"corner1": [0.0, 0.0],
                          "corner2": [PLATE_W, PLATE_T]}}},
    {"op": "extrude", "sketch": "outline", "depth": PLATE_L},
]


# ---------------------------------------------------------------------------
# Running one build
# ---------------------------------------------------------------------------

# These items measure geometry and most of them never submit, so they used to
# leave `mesh:` out entirely. The generator refuses that now: every deck it
# writes ends in writeInput, and an unmeshed part reaches the .inp as an empty
# `*Part` with a live `*Instance`. Linear tets at a seed far coarser than the
# part, because nothing here reads a displacement -- item 10 brings its own
# mesh. The flange cannot be hex-meshed at all once the bolt holes are cut.
GEOMETRY_MESH = {"seed": 5.0, "element": "C3D4"}


def _spec(part_name: str, features: list, expect: dict | None,
          mesh: dict | None = None, steps: list | None = None,
          outputs: dict | None = None) -> dict:
    part = {"name": part_name, "features": copy.deepcopy(features),
            "section": {"type": "solid", "material": "Steel"},
            "mesh": copy.deepcopy(mesh if mesh is not None else GEOMETRY_MESH)}
    if expect is not None:
        part["expect"] = copy.deepcopy(expect)
    spec = {
        "meta": {"abaqus_release": "2021", "model_name": "Generic" + part_name,
                 "units": "mm_MPa_t"},
        "material": {"name": "Steel", "E": 210000.0, "nu": 0.3},
        "parts": [part],
        "assembly": {"instances": [{"name": "I1", "part": part_name}]},
        "steps": copy.deepcopy(steps) if steps else [{
            "name": "Step-1", "type": "Static",
            "bcs": [{"name": "Fix", "type": "encastre",
                     "region": "I1:face@y=min", "expect": ">=1"}]}],
    }
    if outputs is not None:
        spec["outputs"] = copy.deepcopy(outputs)
    return spec


def _build(work: Path, spec: dict) -> dict:
    """Run one CAE build and report what the geometry layer logged.

    Deliberately not through the orchestrator: these items measure geometry, and
    a solve would add minutes per item without adding evidence. Item 10 goes the
    whole way.
    """
    # Resolved, not just made. The generated script chdirs to the workdir it is
    # handed while CAE already runs with cwd=workdir, so a relative path is
    # re-interpreted relative to itself and dies as WindowsError(3) on line 10 --
    # the same trap runner/build_model.py carries a comment about.
    work = work.resolve()
    work.mkdir(parents=True, exist_ok=True)
    log_path = work / "selectors.log"
    if log_path.exists():
        log_path.unlink()
    try:
        text = build_v2.generate_script(spec)
    except Exception as exc:                       # host-side refusal
        return {"stage": "generate", "rc": None, "log": "",
                "error": "%s: %s" % (type(exc).__name__, exc)}
    script = work / "build_model_script.py"
    script.write_text(text, encoding="utf-8")
    proc = subprocess.run(
        [get_abaqus_cmd(), "cae", "noGUI=" + script.name, "--", str(work), "spec"],
        cwd=str(work), capture_output=True, text=True,
        errors="replace", encoding="utf-8", stdin=subprocess.DEVNULL,
        timeout=600)
    log = log_path.read_text(encoding="utf-8", errors="replace") if log_path.exists() else ""
    return {"stage": "cae", "rc": proc.returncode, "log": log,
            "error": (proc.stderr or "")[-3000:]}


def _expect_line(out: dict) -> str:
    for line in out["log"].splitlines():
        if line.startswith("EXPECT_OK:"):
            return line
    return ""


def _volume(out: dict) -> float | None:
    line = _expect_line(out)
    marker = "volume="
    if marker not in line:
        return None
    try:
        return float(line.split(marker, 1)[1].split(" ", 1)[0])
    except ValueError:
        return None


def _built(out: dict) -> bool:
    return out["rc"] == 0 and bool(_expect_line(out))


def _refusal(out: dict) -> str:
    """Everything a refusal could have been written to, as one string."""
    return "\n".join([out.get("error") or "", out.get("log") or ""])


def _skipped(item_id: str, reason: str) -> dict:
    return {"id": item_id, "status": "skipped", "reason": reason}


def _relative(got: float, want: float) -> float:
    return abs(got - want) / abs(want)


# ---------------------------------------------------------------------------
# Items
# ---------------------------------------------------------------------------

def check_revolve(work: Path) -> dict:
    expect = {"volume": FLANGE_VOLUME, "cells": 1, "faces": 6,
              "cylindrical_faces": 3}
    out = _build(work / "revolve", _spec("Flange", REVOLVE, expect))
    got = _volume(out)
    problems = []
    if not _built(out):
        problems.append("build did not complete: %s" % _refusal(out)[-600:])
    deviation = _relative(got, FLANGE_VOLUME) if got is not None else None
    if got is None:
        problems.append("no volume in the build log")
    return {
        "id": "generic_flange_volume",
        "status": "pass" if not problems else "fail",
        "identity": "pi*(30^2-4^2)*10 + pi*(10^2-4^2)*15",
        "theory_volume": FLANGE_VOLUME,
        "measured_volume": got,
        "relative_deviation": deviation,
        "note": "seven Line calls and one BaseSolidRevolve, dispatched by name. "
                "No branch anywhere in this repo knows what a flange is.",
        "problems": problems,
    }


def check_fillet(work: Path) -> dict:
    want = FLANGE_VOLUME + FILLET_DELTA_V
    features = REVOLVE + [
        {"call": "Round", "radius": FILLET_R,
         "edgeList": {"select": "edges@r=%g" % R_BOSS, "expect": "=2"}}]
    expect = {"volume": want, "cells": 1, "faces": 8}
    out = _build(work / "fillet", _spec("Flange", features, expect))
    got = _volume(out)
    problems = []
    if not _built(out):
        problems.append("build did not complete: %s" % _refusal(out)[-600:])
    if "GENERIC_RETRIED" not in out["log"]:
        problems.append(
            "the tuple shim did not fire. Round(edgeList=) was measured to "
            "refuse a GeomSequence with 'found GeomSequence, expecting tuple' "
            "while Set(edges=) requires one, so either the shim is dead code "
            "or this release changed and the note behind it is now wrong.")
    return {
        "id": "generic_fillet_uses_the_tuple_shim",
        "status": "pass" if not problems else "fail",
        "identity": "dV = 2*pi*r^3*(5/3 - pi/2), Pappus on the two slivers",
        "theory_delta_v": FILLET_DELTA_V,
        "theory_volume": want,
        "measured_volume": got,
        "relative_deviation": _relative(got, want) if got is not None else None,
        "shim_fired": "GENERIC_RETRIED" in out["log"],
        "note": "the corner radius cancels because one filleted edge is "
                "concave and the other convex, so this number is not fitted to "
                "anything.",
        "problems": problems,
    }


def check_datum_cut(work: Path) -> dict:
    want = FLANGE_VOLUME + BOLT_DELTA_V
    expect = {"volume": want, "cells": 1, "cylindrical_faces": 5,
              "cylinders": [{"r": BOLT_R, "at": list(at)}
                            for at in BOLT_CENTROIDS]}
    out = _build(work / "datum_cut", _spec("Flange", REVOLVE + _drill(), expect))
    got = _volume(out)
    problems = []
    if not _built(out):
        problems.append("build did not complete: %s" % _refusal(out)[-600:])
    return {
        "id": "generic_cut_through_a_datum_plane",
        "status": "pass" if not problems else "fail",
        "identity": "two through holes remove 2*pi*r^2*t",
        "theory_volume": want,
        "measured_volume": got,
        "relative_deviation": _relative(got, want) if got is not None else None,
        "hole_centroids": [list(at) for at in BOLT_CENTROIDS],
        "note": "the top of this flange is an annulus, so every edge on it is a "
                "circle and there is nothing straight to orient a sketch "
                "against. The named cut_extrude refuses this part outright; a "
                "datum plane needs no edge at all.",
        "problems": problems,
    }


def check_unknown_method(work: Path) -> dict:
    features = copy.deepcopy(REVOLVE)
    features[1]["call"] = "BaseSolidRevolv"
    expect = {"volume": FLANGE_VOLUME}
    out = _build(work / "bad_method", _spec("Flange", features, expect))
    evidence = _refusal(out)
    problems = []
    if _built(out):
        problems.append("a method that does not exist built a part anyway")
    elif "GENERIC_NO_METHOD" not in evidence and "BaseSolidRevolv" not in evidence:
        problems.append("refused, but without naming the method: %s"
                        % evidence[-400:])
    return {
        "id": "generic_refuses_an_unknown_method",
        "status": "pass" if not problems else "fail",
        "mutation": "BaseSolidRevolve -> BaseSolidRevolv",
        "aborted": not _built(out),
        "problems": problems,
    }


def check_unknown_keyword(work: Path) -> dict:
    features = copy.deepcopy(REVOLVE)
    features[1].pop("angle")
    features[1]["angel"] = 360.0
    expect = {"volume": FLANGE_VOLUME}
    out = _build(work / "bad_keyword", _spec("Flange", features, expect))
    evidence = _refusal(out)
    problems = []
    if _built(out):
        problems.append("a keyword that does not exist built a part anyway")
    elif "angel" not in evidence:
        problems.append("refused, but without naming the keyword: %s"
                        % evidence[-400:])
    return {
        "id": "generic_refuses_an_unknown_keyword",
        "status": "pass" if not problems else "fail",
        "mutation": "angle= -> angel=",
        "aborted": not _built(out),
        "problems": problems,
    }


def check_wrong_volume(work: Path) -> dict:
    expect = {"volume": FLANGE_VOLUME * 1.1}
    out = _build(work / "wrong_volume", _spec("Flange", REVOLVE, expect))
    evidence = _refusal(out)
    problems = []
    if _built(out):
        problems.append("a volume 10%% out was accepted")
    elif "EXPECT_VOLUME" not in evidence:
        problems.append("aborted, but not on the volume check: %s"
                        % evidence[-400:])
    return {
        "id": "generic_refuses_a_wrong_volume",
        "status": "pass" if not problems else "fail",
        "mutation": "expect.volume x 1.1",
        "aborted": not _built(out),
        "problems": problems,
    }


def check_missed_cut(work: Path) -> dict:
    """Holes moved past the outer radius, so the cut lands on nothing."""
    want = FLANGE_VOLUME + BOLT_DELTA_V
    expect = {"volume": want, "cells": 1, "cylindrical_faces": 5}
    features = REVOLVE + _drill(pcd=R_OUTER + 20.0)
    out = _build(work / "missed_cut", _spec("Flange", features, expect))
    evidence = _refusal(out)
    problems = []
    if _built(out):
        problems.append(
            "a cut that landed off the solid was accepted. Measured on Abaqus "
            "2021 this is completely silent: same volume, same face count, "
            "exit 0.")
    elif "EXPECT_" not in evidence:
        problems.append("aborted, but not on an expect check: %s"
                        % evidence[-400:])
    return {
        "id": "generic_refuses_a_cut_that_missed",
        "status": "pass" if not problems else "fail",
        "mutation": "bolt circle radius 20 -> 50, past the 30 mm flange",
        "aborted": not _built(out),
        "note": "measured directly: with the holes off the solid Abaqus returns "
                "0, raises nothing, and leaves the volume byte-identical to the "
                "un-drilled part.",
        "problems": problems,
    }


def check_transposed_cut(work: Path) -> dict:
    """The same holes, oriented against the wrong axis.

    Run twice on purpose. The first build states volume and counts and MUST
    pass, because a transposition changes neither -- that pass is the evidence
    that `expect.cylinders` has to exist. The second states positions and must
    abort.
    """
    features = REVOLVE + _drill(axis="ZAXIS")
    blind_expect = {"volume": FLANGE_VOLUME + BOLT_DELTA_V, "cells": 1,
                    "cylindrical_faces": 5}
    blind = _build(work / "transposed_blind",
                   _spec("Flange", features, blind_expect))

    seeing_expect = dict(blind_expect)
    seeing_expect["cylinders"] = [{"r": BOLT_R, "at": list(at)}
                                  for at in BOLT_CENTROIDS]
    seeing = _build(work / "transposed_seen",
                    _spec("Flange", features, seeing_expect))

    problems = []
    if not _built(blind):
        problems.append(
            "the volume-and-counts build did NOT pass on a transposed cut. "
            "That is the premise of this item: if counts can see a "
            "transposition then expect.cylinders is unnecessary, and the "
            "reasoning behind it needs rewriting: %s" % _refusal(blind)[-400:])
    if _built(seeing):
        problems.append("expect.cylinders accepted holes 90 degrees away")
    elif "EXPECT_CYLINDER" not in _refusal(seeing):
        problems.append("aborted, but not on the cylinder check: %s"
                        % _refusal(seeing)[-400:])
    return {
        "id": "generic_refuses_a_transposed_cut",
        "status": "pass" if not problems else "fail",
        "mutation": "sketchUpEdge axis XAXIS -> ZAXIS",
        "volume_and_counts_passed": _built(blind),
        "cylinders_aborted": not _built(seeing),
        "blind_volume": _volume(blind),
        "correct_volume": FLANGE_VOLUME + BOLT_DELTA_V,
        "note": "the holes move 90 degrees around the axis and the volume "
                "changes by 1.5e-7 relative, which is faceting. Faces, edges, "
                "vertices and cylindrical_faces are all identical. On a "
                "symmetric part no global measure can tell the two models "
                "apart.",
        "problems": problems,
    }


def check_named_op_agreement(work: Path) -> dict:
    expect = {"volume": PLATE_VOLUME, "cells": 1, "faces": 6, "edges": 12,
              "vertices": 8}
    generic = _build(work / "plate_generic",
                     _spec("Plate", GENERIC_PLATE, expect))
    named = _build(work / "plate_named", _spec("Plate", NAMED_PLATE, expect))
    problems = []
    for label, out in (("generic", generic), ("named", named)):
        if not _built(out):
            problems.append("%s plate did not build: %s"
                            % (label, _refusal(out)[-400:]))
    got_g, got_n = _volume(generic), _volume(named)
    if got_g is not None and got_n is not None and got_g != got_n:
        problems.append("the two paths disagree: %r vs %r" % (got_g, got_n))
    return {
        "id": "generic_matches_the_named_op",
        "status": "pass" if not problems else "fail",
        "identity": "60 x 100 x 5 = %s either way" % PLATE_VOLUME,
        "generic_volume": got_g,
        "named_volume": got_n,
        "note": "four Line calls and a BaseSolidExtrude against rect + extrude. "
                "The named ops stay because they are shorter, not because they "
                "can do anything the generic path cannot.",
        "problems": problems,
    }


def check_end_to_end(work: Path) -> dict:
    """A generically built part through the whole pipeline, on equilibrium.

    Pressure on the top face has to come back out of the ODB as reaction force
    at the clamp. It is the one identity that touches every stage: geometry,
    mesh, section, step, load, solve and extraction.
    """
    from agent.orchestrator import build_orchestrator

    area = PLATE_W * PLATE_L
    spec = _spec(
        "Plate", GENERIC_PLATE,
        {"volume": PLATE_VOLUME, "cells": 1, "faces": 6},
        mesh={"seed": 10.0, "element": "C3D8R"},
        steps=[{
            "name": "Press", "type": "Static",
            "bcs": [{"name": "Fix", "type": "encastre",
                     "region": "I1:face@z=min", "expect": "=1"}],
            "loads": [{"name": "Top", "type": "pressure",
                       "region": "I1:face@y=max", "value": PLATE_PRESSURE,
                       "expect": "=1"}],
        }],
        outputs={"kpis": [
            {"name": "RF_TOTAL", "type": "reaction_force_max",
             "location": "BC_FIX", "component": "RF2", "reducer": "sum"},
        ]})

    orch = build_orchestrator(spec_dict=spec, workdir=work / "end_to_end")
    result = orch.run()
    raw = result.get("kpis", {}).get("RF_TOTAL")
    total = raw.get("value") if isinstance(raw, dict) else raw

    # Pressure is positive INTO the surface, so 0.1 MPa on the y=max face is
    # 600 N acting in -y. The reaction that holds it is equal and opposite, so
    # sum(RF2) at the clamp is +600 N.
    want = PLATE_PRESSURE * area
    problems = []
    if result.get("status") != "COMPLETED":
        problems.append("orchestrator status %s: %s"
                        % (result.get("status"), result.get("error")))
    deviation = None
    if total is None:
        problems.append("RF_TOTAL missing from KPIs")
    else:
        deviation = _relative(total, want)
        if deviation >= EQUILIBRIUM_TOLERANCE_REL:
            problems.append(
                "reaction %.6f N against an applied %.6f N (%.3f%% out). "
                "Equilibrium is exact in a linear static solve, so anything "
                "beyond rounding means the load or the restraint is not on the "
                "face this spec names." % (total, want, deviation * 100))
    return {
        "id": "generic_part_solves_end_to_end",
        "status": "pass" if not problems else "fail",
        "identity": "sum(RF2) at the clamp = -pressure * area",
        "applied_n": want,
        "measured_n": total,
        "relative_deviation": deviation,
        "problems": problems,
    }


def check_big_bore_tolerance(work: Path) -> dict:
    """A bore in exactly the right place that the old fixed tolerance refused.

    `expect.cylinders[].at_tol` used to default to a flat 0.05 mm, sized once
    against a 30 mm flange. getCentroid() is a tessellation estimate, so on a
    large enough feature its own error exceeds that -- measured here at
    r = 300 in a 900 mm plate, where the centroid comes back 0.0709 off an
    analytically exact position. The default now follows the radius,
    max(1e-3, r * 2e-3), which is 0.6 here.

    Three builds, because loosening a tolerance is only defensible if the check
    still refuses a real error afterwards:

      1. the correct position, no at_tol  -- must build, and the margin it logs
         must exceed 0.05, or this part is too small to be the counterexample
         and the item is not testing what it claims;
      2. the correct position, at_tol 0.05 -- must abort. This IS the old
         default, stated by hand, refusing a bore that is where the spec says;
      3. the position moved by 5 mm, no at_tol -- must still abort.
    """
    at = [BORE_CX, BORE_CY, BORE_DEPTH / 2.0]
    def spec(cylinder):
        return _spec("Bore", BORE_FEATURES,
                     {"cells": 1, "cylindrical_faces": 1,
                      "cylinders": [cylinder]},
                     mesh={"seed": BORE_SEED, "element": "C3D4"})

    right = _build(work / "bore_right", spec({"r": BORE_R, "at": at}))
    old = _build(work / "bore_old_tol",
                 spec({"r": BORE_R, "at": at, "at_tol": OLD_FLAT_TOL}))
    moved = _build(work / "bore_moved",
                   spec({"r": BORE_R, "at": [at[0] + 5.0, at[1], at[2]]}))

    margin = None
    for line in right["log"].splitlines():
        if "worst off by" in line:
            margin = float(line.split("worst off by")[1].split("of")[0])
            break

    problems = []
    if not _built(right):
        problems.append("the correct position was refused: %s"
                        % _refusal(right)[-500:])
    if margin is None:
        problems.append("no margin was logged, so this item cannot say how "
                        "close the passing build came to being refused")
    elif margin <= OLD_FLAT_TOL:
        problems.append(
            "the centroid came back only %.6g off, inside the old %s default. "
            "This geometry is then not a counterexample and the item proves "
            "nothing -- the bore has to be bigger." % (margin, OLD_FLAT_TOL))
    if _built(old):
        problems.append(
            "at_tol %s accepted this bore, so the old default did NOT refuse "
            "it and the premise of this item is wrong" % OLD_FLAT_TOL)
    elif "EXPECT_CYLINDER" not in _refusal(old):
        problems.append("aborted, but not on the cylinder check: %s"
                        % _refusal(old)[-400:])
    if _built(moved):
        problems.append(
            "the relative default accepted a bore 5 mm from where the spec "
            "said. Widening the tolerance has turned the check off.")
    elif "EXPECT_CYLINDER" not in _refusal(moved):
        problems.append("the moved bore aborted, but not on the cylinder "
                        "check: %s" % _refusal(moved)[-400:])

    return {
        "id": "generic_big_bore_survives_its_own_instrument",
        "status": "pass" if not problems else "fail",
        "identity": "a through bore's cylindrical face is centred on the "
                    "sketch circle at mid-depth, exactly",
        "bore_radius": BORE_R,
        "stated_centroid": at,
        "measured_offset": margin,
        "old_flat_default": OLD_FLAT_TOL,
        "new_default": max(1.0e-3, BORE_R * 2.0e-3),
        "correct_position_accepted": _built(right),
        "old_default_refused_it": not _built(old),
        "moved_bore_still_refused": not _built(moved),
        "note": "the offset here is the instrument's, not the geometry's: the "
                "same probe measured zero error at r = 4, 12, 50 and 100 in "
                "this same plate, so the error is a property of how Abaqus "
                "tessellates a large face and not of the cut.",
        "problems": problems,
    }


ITEM_IDS = [
    "generic_flange_volume",
    "generic_fillet_uses_the_tuple_shim",
    "generic_cut_through_a_datum_plane",
    "generic_refuses_an_unknown_method",
    "generic_refuses_an_unknown_keyword",
    "generic_refuses_a_wrong_volume",
    "generic_refuses_a_cut_that_missed",
    "generic_refuses_a_transposed_cut",
    "generic_matches_the_named_op",
    "generic_part_solves_end_to_end",
    "generic_big_bore_survives_its_own_instrument",
]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Real Abaqus check for the generic part layer.")
    parser.add_argument("--json-out", type=Path, default=None)
    parser.add_argument("--work-dir", type=Path, default=None)
    parser.add_argument("--only", action="append", default=None,
                        help="run just these item ids (repeatable)")
    args = parser.parse_args(argv)

    work = args.work_dir or Path(tempfile.mkdtemp(prefix="generic_part_"))
    work.mkdir(parents=True, exist_ok=True)

    if not check_abaqus():
        reason = "Abaqus not found (set ABAQUS_AGENT_ABAQUS_CMD)"
        items = [_skipped(item_id, reason) for item_id in ITEM_IDS]
    else:
        checks = [
            check_revolve, check_fillet, check_datum_cut,
            check_unknown_method, check_unknown_keyword, check_wrong_volume,
            check_missed_cut, check_transposed_cut, check_named_op_agreement,
            check_end_to_end, check_big_bore_tolerance,
        ]
        items = []
        for check, item_id in zip(checks, ITEM_IDS):
            if args.only and item_id not in args.only:
                continue
            started = time.time()
            try:
                item = check(work)
            except Exception as exc:
                item = {"id": item_id, "status": "fail",
                        "problems": ["the check itself raised: %s: %s"
                                     % (type(exc).__name__, exc)]}
            item["seconds"] = round(time.time() - started, 1)
            items.append(item)
            print("  %-42s %s" % (item["id"], item["status"]),
                  file=sys.stderr)

    statuses = [item["status"] for item in items]
    if "fail" in statuses:
        overall = "fail"
    elif statuses and all(s == "skipped" for s in statuses):
        overall = "skipped"
    elif "skipped" in statuses:
        overall = "partial"
    else:
        overall = "pass"

    report = {
        "schema": "generic_part_check/1",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "abaqus_release": detect_abaqus_release(),
        "work_dir": str(work),
        "overall": overall,
        "items": items,
    }
    text = json.dumps(report, indent=2, ensure_ascii=False)
    print(text)
    if args.json_out is not None:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(text + "\n", encoding="utf-8")
    return 1 if overall == "fail" else 0


if __name__ == "__main__":
    sys.exit(main())
