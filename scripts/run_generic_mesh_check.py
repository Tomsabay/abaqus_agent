#!/usr/bin/env python3
"""Real-solver check for the generic mesh and assembly layers.

The part layer (scripts/run_generic_part_check.py) proves a spec can name any
Abaqus modelling method and have it dispatched. This one proves the same for the
two layers on either side of it, and it does so on the one part that made both
of them necessary: a bolted bearing housing with a revolved body, two fillets,
two chamfers, eight bolt holes and a radial oil hole on a different axis.

Meshing. Measured on Abaqus 2021, that part cannot be hex-meshed by any route:

    HEX/FREE           refused, "Free Hex meshing is not supported"
    HEX/STRUCTURED     refused, "Some regions cannot be Mapped"
    HEX/SWEEP          refused, "Some regions cannot be Swept/Revolved"
    HEX/SYSTEM_ASSIGN  ACCEPTED -- and produces zero elements, raising nothing
    TET/FREE           10030 elements, nothing unmeshed, nothing failed

The fourth line is why `expect.mesh` is mandatory for a part that meshes itself
generically, and why the failure message now asks Abaqus which cells are
UNMESHABLE instead of only reporting that no elements appeared.

Assembly. `instances` positions by arithmetic; everything else in the assembly
API was unreachable. The items below drive RadialInstancePattern and check
where the eight bolts actually ended up -- against the housing's own measured
hole centroids, so passing means the bolts are IN the holes.

  1. `generic_mesh_tets_a_part_with_no_hex_route`
  2. `generic_mesh_refuses_a_silent_zero`   -- and names the UNMESHABLE cell
  3. `generic_mesh_requires_an_expect_block`
  4. `generic_mesh_asserts_the_element_count`
  5. `generic_mesh_explains_a_mixed_element_order`
  6. `generic_assembly_pattern_lands_in_the_holes`
  7. `generic_assembly_refuses_a_wrong_instance_count`
  8. `generic_assembly_refuses_a_misplaced_instance` -- runs twice: the count
     check PASSES on a bolt ring that is nowhere near the holes, which is the
     evidence that positions have to be stated.

Booleans. Parts are meshed before the assembly exists, so anything an operation
creates is born unmeshed and nothing downstream meshes it. Two shapes of that,
and the way out of both:

  9. `generic_assembly_refuses_a_cut_nothing_meshed`
 10. `generic_assembly_refuses_a_merge_nothing_instanced` -- the quieter one:
     the merged part reaches neither the assembly nor the .inp, both originals
     stay meshed and unsuppressed, and what solves is the model from before
     the merge.
 11. `generic_assembly_meshes_a_boolean_result` -- the route items 9 and 10
     name in their refusals, run end to end. Without this the other two are a
     wall rather than a door.

`expect:` on the operation itself, which used to validate and then evaporate:

 12. `generic_assembly_expect_measures_the_boolean_result` -- 20^3 minus a 6x6
     pin through it is 7280.0 in 1 cell, read off the PART (the PartInstance a
     cut returns carries partName and has no getVolume) and live without
     a.regenerate().
 13. `generic_assembly_expect_catches_a_wrong_number` -- the same run stating
     8000.0, the volume before the cut, must abort. Without it item 12 passes
     for a check that is not looking.

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

# --- the housing, and the bolt that goes through it ------------------------

R_BORE, R_HUB, R_FLANGE = 20.0, 32.0, 70.0
T_FLANGE, Y_TOP = 15.0, 90.0
FILLET_R, CHAMFER_L = 6.0, 3.0
BOLT_HOLE_R, BOLT_PCD, BOLT_N = 7.0, 55.0, 8
OIL_R, OIL_Y, OIL_FROM = 5.0, 55.0, 40.0
SHANK_R, SHANK_LEN = 6.5, 25.0

# Only the geometry that matters for the mesh: the exact volume is the part
# check's business, so this one states a band rather than restating a number
# derived somewhere else.
HOUSING_VOLUME = 337659.757738
SHANK_VOLUME = math.pi * SHANK_R ** 2 * SHANK_LEN

MESHED_ELEMENTS = 10030   # measured, seed 8.0, TET/FREE

PROFILE = [
    {"call": "ConstructionLine", "point1": [0.0, 0.0], "point2": [0.0, 10.0]},
    {"call": "Line", "point1": [R_BORE, 0.0], "point2": [R_FLANGE, 0.0]},
    {"call": "Line", "point1": [R_FLANGE, 0.0], "point2": [R_FLANGE, T_FLANGE]},
    {"call": "Line", "point1": [R_FLANGE, T_FLANGE], "point2": [R_HUB, T_FLANGE]},
    {"call": "Line", "point1": [R_HUB, T_FLANGE], "point2": [R_HUB, Y_TOP]},
    {"call": "Line", "point1": [R_HUB, Y_TOP], "point2": [R_BORE, Y_TOP]},
    {"call": "Line", "point1": [R_BORE, Y_TOP], "point2": [R_BORE, 0.0]},
]


def _bolt_circles():
    out = []
    for k in range(BOLT_N):
        angle = 2.0 * math.pi * k / BOLT_N
        cx, cy = BOLT_PCD * math.cos(angle), BOLT_PCD * math.sin(angle)
        out.append({"call": "CircleByCenterPerimeter", "center": [cx, cy],
                    "point1": [cx + BOLT_HOLE_R, cy]})
    return out


HOUSING_GEOMETRY = [
    {"op": "sketch", "id": "profile", "entities": PROFILE},
    {"call": "BaseSolidRevolve", "sketch": {"sketch": "profile"},
     "angle": 360.0, "flipRevolveDirection": "OFF"},
    {"call": "Round", "radius": FILLET_R,
     "edgeList": {"select": "edges@r=%g" % R_HUB, "expect": "=2"}},
    {"call": "Chamfer", "length": CHAMFER_L,
     "edgeList": {"select": "edges@r=%g" % R_BORE, "expect": "=2"}},
    {"call": "DatumPlaneByPrincipalPlane", "principalPlane": "XZPLANE",
     "offset": T_FLANGE, "as": "flangeFace"},
    {"call": "DatumAxisByPrincipalAxis", "principalAxis": "XAXIS", "as": "boltUp"},
    {"call": "MakeSketchTransform", "sketchPlane": {"datum": "flangeFace"},
     "sketchUpEdge": {"datum": "boltUp"}, "sketchPlaneSide": "SIDE1",
     "sketchOrientation": "RIGHT", "origin": [0.0, T_FLANGE, 0.0],
     "as": "boltXf"},
    {"op": "sketch", "id": "bolts", "transform": {"ref": "boltXf"},
     "sheet_size": 400.0, "entities": _bolt_circles()},
    {"call": "CutExtrude", "sketchPlane": {"datum": "flangeFace"},
     "sketchUpEdge": {"datum": "boltUp"}, "sketchPlaneSide": "SIDE1",
     "sketchOrientation": "RIGHT", "sketch": {"sketch": "bolts"},
     "depth": T_FLANGE, "flipExtrudeDirection": "OFF"},
    {"call": "DatumPlaneByPrincipalPlane", "principalPlane": "XYPLANE",
     "offset": OIL_FROM, "as": "oilPlane"},
    {"call": "DatumAxisByPrincipalAxis", "principalAxis": "YAXIS", "as": "oilUp"},
    {"call": "MakeSketchTransform", "sketchPlane": {"datum": "oilPlane"},
     "sketchUpEdge": {"datum": "oilUp"}, "sketchPlaneSide": "SIDE1",
     "sketchOrientation": "RIGHT", "origin": [0.0, 0.0, OIL_FROM], "as": "oilXf"},
    {"op": "sketch", "id": "oil", "transform": {"ref": "oilXf"},
     "sheet_size": 400.0,
     "entities": [{"call": "CircleByCenterPerimeter", "center": [0.0, OIL_Y],
                   "point1": [OIL_R, OIL_Y]}]},
    {"call": "CutExtrude", "sketchPlane": {"datum": "oilPlane"},
     "sketchUpEdge": {"datum": "oilUp"}, "sketchPlaneSide": "SIDE1",
     "sketchOrientation": "RIGHT", "sketch": {"sketch": "oil"},
     "depth": 2.0 * OIL_FROM, "flipExtrudeDirection": "OFF"},
]

SHANK_GEOMETRY = [
    {"op": "sketch", "id": "shank", "entities": [
        {"call": "CircleByCenterPerimeter", "center": [0.0, 0.0],
         "point1": [SHANK_R, 0.0]}]},
    {"call": "BaseSolidExtrude", "sketch": {"sketch": "shank"},
     "depth": SHANK_LEN},
]

CELLS = {"select": "cells@all"}
QUADRATIC = [
    {"new": "mesh.ElemType", "elemCode": "C3D20R", "elemLibrary": "STANDARD"},
    {"new": "mesh.ElemType", "elemCode": "C3D15", "elemLibrary": "STANDARD"},
    {"new": "mesh.ElemType", "elemCode": "C3D10", "elemLibrary": "STANDARD"},
]


def mesh_features(shape="TET", technique="FREE", seed=8.0, elem_types=None):
    """Meshing said entirely by naming Abaqus's own methods."""
    return [
        {"call": "setMeshControls", "regions": CELLS,
         "elemShape": shape, "technique": technique},
        {"call": "setElementType", "regions": [CELLS],
         "elemTypes": copy.deepcopy(elem_types or QUADRATIC)},
        {"call": "seedPart", "size": float(seed), "deviationFactor": 0.1,
         "minSizeFactor": 0.1},
        {"call": "generateMesh"},
    ]


# Where the eight bolts must land: the first hole, then rotated about the y axis
# by k*45 degrees. These are the housing's own hole centroids, measured.
BOLT_NAMES = ["Bolt"] + ["Bolt-rad-%d" % k for k in range(2, BOLT_N + 1)]


def bolt_positions():
    out = []
    for k, name in enumerate(BOLT_NAMES):
        phi = math.radians(360.0 * k / BOLT_N)
        out.append({"instance": name,
                    "centroid": [BOLT_PCD * math.sin(phi), T_FLANGE / 2.0,
                                 BOLT_PCD * math.cos(phi)],
                    "tol": 0.01})
    return out


RADIAL_PATTERN = {
    "call": "RadialInstancePattern",
    "instanceList": ["Bolt"],
    "point": [0.0, 0.0, 0.0],
    "axis": [0.0, 1.0, 0.0],
    "number": BOLT_N,
    "totalAngle": 360.0,
    "creates": BOLT_NAMES[1:],
}

# Measured: the sugar translates first and rotates second, and the two do not
# commute. This pair puts the bolt in the first hole; swapping them puts it at
# (0, 67.5, 5), which is nowhere near the flange and raises nothing.
BOLT_PLACEMENT_RIGHT = {"translate": [0.0, -BOLT_PCD, -5.0],
                        "rotate": {"axis": [1.0, 0.0, 0.0],
                                   "origin": [0.0, 0.0, 0.0], "angle": -90.0}}
BOLT_PLACEMENT_WRONG = {"translate": [0.0, -5.0, BOLT_PCD],
                        "rotate": {"axis": [1.0, 0.0, 0.0],
                                   "origin": [0.0, 0.0, 0.0], "angle": -90.0}}


def _spec(housing_mesh=None, housing_expect=None, bolts=False,
          placement=None, operations=None, assembly_expect=None):
    parts = [{
        "name": "Housing",
        "features": copy.deepcopy(HOUSING_GEOMETRY) + copy.deepcopy(housing_mesh or []),
        "section": {"type": "solid", "material": "Steel"},
        "expect": copy.deepcopy(housing_expect if housing_expect is not None
                                else {"volume": HOUSING_VOLUME, "cells": 1}),
    }]
    instances = [{"name": "Case", "part": "Housing"}]
    if bolts:
        parts.append({
            "name": "Bolt",
            "features": copy.deepcopy(SHANK_GEOMETRY) + mesh_features(seed=5.0),
            "section": {"type": "solid", "material": "Steel"},
            "expect": {"volume": SHANK_VOLUME, "cells": 1,
                       "mesh": {"elements": ">=1"}},
        })
        entry = {"name": "Bolt", "part": "Bolt"}
        entry.update(copy.deepcopy(placement or BOLT_PLACEMENT_RIGHT))
        instances.append(entry)
    assembly = {"instances": instances}
    if operations:
        assembly["operations"] = copy.deepcopy(operations)
    if assembly_expect:
        assembly["expect"] = copy.deepcopy(assembly_expect)
    return {
        "meta": {"abaqus_release": "2021", "model_name": "GenericMeshCheck",
                 "units": "mm_MPa_t"},
        "material": {"name": "Steel", "E": 210000.0, "nu": 0.3},
        "parts": parts,
        "assembly": assembly,
        "steps": [{"name": "Step-1", "type": "Static",
                   "bcs": [{"name": "Fix", "type": "encastre",
                            "region": "Case:face@y=min", "expect": ">=1"}]}],
    }


# ---------------------------------------------------------------------------

def _build(work: Path, spec: dict) -> dict:
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


def _meshed(out: dict) -> bool:
    return out["rc"] == 0 and bool(_line(out, "MESH_OK: Housing"))


def _evidence(out: dict) -> str:
    return "\n".join([out.get("error") or "", out.get("log") or ""])


def _skipped(item_id: str, reason: str) -> dict:
    return {"id": item_id, "status": "skipped", "reason": reason}


# --- mesh items ------------------------------------------------------------

def check_tet(work: Path) -> dict:
    out = _build(work / "mesh_tet", _spec(
        housing_mesh=mesh_features(),
        housing_expect={"volume": HOUSING_VOLUME, "cells": 1,
                        "mesh": {"elements": "=%d" % MESHED_ELEMENTS,
                                 "max_warned": 0}}))
    problems = []
    if not _meshed(out):
        problems.append("did not mesh: %s" % _evidence(out)[-700:])
    return {
        "id": "generic_mesh_tets_a_part_with_no_hex_route",
        "status": "pass" if not problems else "fail",
        "mesh_line": _line(out, "MESH_OK: Housing"),
        "expected_elements": MESHED_ELEMENTS,
        "note": "every hex route on this part either refuses outright or is "
                "accepted and meshes nothing; TET/FREE meshes it completely. "
                "setMeshControls, setElementType, seedPart and generateMesh are "
                "all named by the spec, and mesh.ElemType is built with {new:}.",
        "problems": problems,
    }


def check_silent_zero(work: Path) -> dict:
    """HEX/SYSTEM_ASSIGN: accepted by Abaqus, meshes nothing, raises nothing."""
    out = _build(work / "mesh_silent", _spec(
        housing_mesh=mesh_features(shape="HEX", technique="SYSTEM_ASSIGN",
                                   elem_types=[
                                       {"new": "mesh.ElemType",
                                        "elemCode": c,
                                        "elemLibrary": "STANDARD"}
                                       for c in ("C3D20R", "C3D15", "C3D10")]),
        housing_expect={"volume": HOUSING_VOLUME, "cells": 1,
                        "mesh": {"elements": ">=1"}}))
    evidence = _evidence(out)
    problems = []
    if _meshed(out):
        problems.append("a part that meshed to nothing was accepted")
    elif "MESH_EMPTY" not in evidence:
        problems.append("aborted, but not on the empty-mesh check: %s"
                        % evidence[-500:])
    elif "UNMESHABLE" not in evidence:
        problems.append(
            "aborted without saying why. getMeshControl(TECHNIQUE) answers "
            "UNMESHABLE for a cell that cannot be meshed under the current "
            "controls, and a message that only says 'no elements' describes "
            "the symptom: %s" % evidence[-500:])
    return {
        "id": "generic_mesh_refuses_a_silent_zero",
        "status": "pass" if not problems else "fail",
        "mutation": "TET/FREE -> HEX/SYSTEM_ASSIGN",
        "aborted": not _meshed(out),
        "names_the_unmeshable_cell": "UNMESHABLE" in evidence,
        "note": "Abaqus ACCEPTS this combination on a shape with no hexes, "
                "generates zero elements and returns without complaint.",
        "problems": problems,
    }


def check_requires_expect(work: Path) -> dict:
    spec = _spec(housing_mesh=mesh_features(),
                 housing_expect={"volume": HOUSING_VOLUME, "cells": 1})
    out = _build(work / "mesh_no_expect", spec)
    evidence = _evidence(out)
    problems = []
    if _meshed(out):
        problems.append("a generically meshed part with no expect.mesh built")
    elif "expect.mesh" not in evidence:
        problems.append("refused without naming expect.mesh: %s" % evidence[-400:])
    return {
        "id": "generic_mesh_requires_an_expect_block",
        "status": "pass" if not problems else "fail",
        "refused_at": "generation" if out["rc"] is None else "cae",
        "note": "nothing else checks a mesh built by generic call, so the "
                "truth block is not optional.",
        "problems": problems,
    }


def check_element_count(work: Path) -> dict:
    out = _build(work / "mesh_wrong_count", _spec(
        housing_mesh=mesh_features(),
        housing_expect={"volume": HOUSING_VOLUME, "cells": 1,
                        "mesh": {"elements": ">=%d" % (MESHED_ELEMENTS * 10)}}))
    evidence = _evidence(out)
    problems = []
    if _meshed(out):
        problems.append("a mesh ten times coarser than stated was accepted")
    elif "MESH_COUNT" not in evidence:
        problems.append("aborted, but not on the count: %s" % evidence[-400:])
    return {
        "id": "generic_mesh_asserts_the_element_count",
        "status": "pass" if not problems else "fail",
        "mutation": "expect.mesh.elements >= 10x what the seed produces",
        "aborted": not _meshed(out),
        "note": "a mesh far coarser than intended still solves and still "
                "reports COMPLETED.",
        "problems": problems,
    }


def check_mixed_order(work: Path) -> dict:
    mixed = [{"new": "mesh.ElemType", "elemCode": c, "elemLibrary": "STANDARD"}
             for c in ("C3D8R", "C3D6", "C3D10")]
    out = _build(work / "mesh_mixed_order", _spec(
        housing_mesh=mesh_features(elem_types=mixed),
        housing_expect={"volume": HOUSING_VOLUME, "cells": 1,
                        "mesh": {"elements": ">=1"}}))
    evidence = _evidence(out)
    problems = []
    if _meshed(out):
        problems.append("a mixed-order element triple was accepted")
    elif "mix orders" not in evidence:
        problems.append(
            "aborted, but with Abaqus's own message alone. 'Default args are "
            "not fully supported' names neither the argument nor the reason: %s"
            % evidence[-400:])
    return {
        "id": "generic_mesh_explains_a_mixed_element_order",
        "status": "pass" if not problems else "fail",
        "mutation": "C3D20R/C3D15/C3D10 -> C3D8R/C3D6/C3D10",
        "aborted": not _meshed(out),
        "note": "linear hex with quadratic tet. Abaqus says 'Default args are "
                "not fully supported', which is useless on its own.",
        "problems": problems,
    }


# --- assembly items --------------------------------------------------------

def check_pattern(work: Path) -> dict:
    out = _build(work / "asm_pattern", _spec(
        housing_mesh=mesh_features(),
        housing_expect={"volume": HOUSING_VOLUME, "cells": 1,
                        "mesh": {"elements": ">=1"}},
        bolts=True, operations=[RADIAL_PATTERN],
        assembly_expect={"instances": BOLT_N + 1, "at": bolt_positions()}))
    problems = []
    # Each bolt by name. A prefix match would also catch the Bolt PART's own
    # volume line, which is a different check entirely.
    placed = [name for name in BOLT_NAMES
              if ("EXPECT_OK: %s at (" % name) in out["log"]]
    if out["rc"] != 0 or len(placed) != BOLT_N:
        missing = [n for n in BOLT_NAMES if n not in placed]
        problems.append("placed %d of %d bolts (missing %s): %s"
                        % (len(placed), BOLT_N, missing or "none",
                           _evidence(out)[-700:]))
    return {
        "id": "generic_assembly_pattern_lands_in_the_holes",
        "status": "pass" if not problems else "fail",
        "identity": "bolt k sits at (55*sin(45k), 7.5, 55*cos(45k)) -- the "
                    "housing's own measured hole centroids",
        "bolts_placed": len(placed),
        "tolerance_mm": 0.01,
        "note": "one instance and one RadialInstancePattern. The positions are "
                "not read back from the model, they are the hole centres the "
                "part check measured independently.",
        "problems": problems,
    }


def check_instance_count(work: Path) -> dict:
    out = _build(work / "asm_count", _spec(
        housing_mesh=mesh_features(),
        housing_expect={"volume": HOUSING_VOLUME, "cells": 1,
                        "mesh": {"elements": ">=1"}},
        bolts=True, operations=[RADIAL_PATTERN],
        assembly_expect={"instances": BOLT_N + 5}))
    evidence = _evidence(out)
    problems = []
    if out["rc"] == 0 and "EXPECT_INSTANCES" not in evidence:
        problems.append("a wrong instance count was accepted: %s"
                        % evidence[-400:])
    return {
        "id": "generic_assembly_refuses_a_wrong_instance_count",
        "status": "pass" if not problems else "fail",
        "mutation": "expect.instances 9 -> 13",
        "note": "a pattern that quietly produced nothing would leave one bolt "
                "instead of eight, and a stiffness wrong by a factor nobody "
                "would question.",
        "problems": problems,
    }


def check_misplaced(work: Path) -> dict:
    """The translate/rotate order trap, and what each check can see of it.

    Run twice on purpose, the same shape as the transposed-cut item in the part
    check. The first states only the instance count and MUST pass, because the
    bolts being 60 mm from where they belong changes no count. That pass is the
    evidence that positions have to be stated.
    """
    blind = _build(work / "asm_blind", _spec(
        housing_mesh=mesh_features(),
        housing_expect={"volume": HOUSING_VOLUME, "cells": 1,
                        "mesh": {"elements": ">=1"}},
        bolts=True, placement=BOLT_PLACEMENT_WRONG, operations=[RADIAL_PATTERN],
        assembly_expect={"instances": BOLT_N + 1}))
    seeing = _build(work / "asm_seeing", _spec(
        housing_mesh=mesh_features(),
        housing_expect={"volume": HOUSING_VOLUME, "cells": 1,
                        "mesh": {"elements": ">=1"}},
        bolts=True, placement=BOLT_PLACEMENT_WRONG, operations=[RADIAL_PATTERN],
        assembly_expect={"instances": BOLT_N + 1, "at": bolt_positions()}))

    blind_ok = blind["rc"] == 0 and "EXPECT_OK: assembly instances" in blind["log"]
    problems = []
    if not blind_ok:
        problems.append(
            "the count-only build did NOT pass on misplaced bolts. That is "
            "this item's premise: if counts can see a placement error then "
            "expect.at is unnecessary and the reasoning needs rewriting: %s"
            % _evidence(blind)[-500:])
    if "EXPECT_PLACED" not in _evidence(seeing):
        problems.append("expect.at did not catch bolts 60 mm out of place: %s"
                        % _evidence(seeing)[-500:])
    return {
        "id": "generic_assembly_refuses_a_misplaced_instance",
        "status": "pass" if not problems else "fail",
        "mutation": "translate/rotate written in the other order",
        "count_check_passed": blind_ok,
        "position_check_aborted": "EXPECT_PLACED" in _evidence(seeing),
        "note": "the sugar translates first and rotates second; the two do not "
                "commute. Written the other way round the bolt lands at "
                "(0, 67.5, 5) instead of (0, 7.5, 55) -- floating in space "
                "above the flange, with nothing raised and every count intact. "
                "This was a real mistake made while writing the demo, not an "
                "invented one.",
        "problems": problems,
    }


# --- boolean items ---------------------------------------------------------
#
# Two plain boxes rather than the housing: these items are about what an
# operation leaves behind, and a 64-element cube says it in seconds.

def _box_part(name, x, y, z, seed):
    return {
        "name": name,
        "features": [
            {"op": "sketch", "id": "s", "plane": "XY",
             "profile": {"rect": {"corner1": [0.0, 0.0], "corner2": [x, y]}}},
            {"op": "extrude", "sketch": "s", "depth": z},
        ],
        "section": {"type": "solid", "material": "Steel"},
        "mesh": {"seed": seed, "element": "C3D8R"},
    }


CUT_OP = [{"call": "InstanceFromBooleanCut", "name": {"literal": "Cut"},
           "instanceToBeCut": {"instance": "Blk"},
           "cuttingInstances": [{"instance": "Pn"}],
           "originalInstances": "SUPPRESS",
           "creates": ["Cut-1"], "as": "cutinst"}]

# The way out, exactly as the ASSEMBLY_UNMESHED message states it. The cut body
# has to be made independent first: the mesh of a dependent instance lives on
# its part, and nothing here can seed a part from assembly scope.
REPAIR_OPS = CUT_OP + [
    {"call": "makeIndependent", "instances": [{"instance": "Cut-1"}]},
    {"call": "setMeshControls", "regions": {"select": "Cut-1:cells@all"},
     "elemShape": "TET", "technique": "FREE"},
    {"call": "seedPartInstance", "regions": [{"instance": "Cut-1"}],
     "size": 4.0},
    {"call": "generateMesh", "regions": [{"instance": "Cut-1"}]},
]

MERGE_OP = [{"call": "PartFromBooleanMerge", "name": {"literal": "Bonded"},
             "instances": [{"instance": "Blk"}, {"instance": "Pn"}]}]


def _repair_with_expect(expect):
    """REPAIR_OPS with `expect:` on the cut, which is what makes the result."""
    ops = copy.deepcopy(REPAIR_OPS)
    ops[0]["expect"] = copy.deepcopy(expect)
    return ops


def _boolean_spec(operations, bc_region):
    return {
        "meta": {"abaqus_release": "2021", "model_name": "GenericBoolean",
                 "units": "mm_MPa_t"},
        "material": {"name": "Steel", "E": 210000.0, "nu": 0.3,
                     "density": 7.85e-9},
        "parts": [_box_part("Block", 20.0, 20.0, 20.0, 5.0),
                  _box_part("Pin", 6.0, 6.0, 40.0, 3.0)],
        "assembly": {
            "instances": [
                {"name": "Blk", "part": "Block"},
                {"name": "Pn", "part": "Pin", "translate": [7.0, 7.0, -10.0]},
            ],
            "operations": copy.deepcopy(operations),
        },
        "steps": [{"name": "Step-1", "type": "Static",
                   "bcs": [{"name": "Fix", "type": "encastre",
                            "region": bc_region, "expect": ">=1"}]}],
    }


def check_boolean_cut_unmeshed(work: Path) -> dict:
    out = _build(work / "bool_cut", _boolean_spec(CUT_OP, "Cut-1:face@z=min"))
    evidence = _evidence(out)
    problems = []
    if "ASSEMBLY_UNMESHED" not in evidence:
        problems.append("a cut nothing meshed was accepted: %s"
                        % evidence[-700:])
    if "Cut-1" not in _line(out, "ASSEMBLY_UNMESHED"):
        problems.append("the refusal did not name the instance: %s"
                        % _line(out, "ASSEMBLY_UNMESHED")[:300])
    return {
        "id": "generic_assembly_refuses_a_cut_nothing_meshed",
        "status": "pass" if not problems else "fail",
        "mutation": "InstanceFromBooleanCut with nothing meshing the result",
        "aborted": "ASSEMBLY_UNMESHED" in evidence,
        "note": "measured: the cut part comes out cells=1 elements=0 nodes=0, "
                "and before this check the .inp carried *Part, name=Cut / "
                "*End Part with a live *Instance and not one *Element in the "
                "file, with the job completing.",
        "problems": problems,
    }


def check_boolean_merge_uninstanced(work: Path) -> dict:
    out = _build(work / "bool_merge", _boolean_spec(MERGE_OP, "Blk:face@z=min"))
    evidence = _evidence(out)
    problems = []
    if "PART_NOT_INSTANCED" not in evidence:
        problems.append("a merge nothing instanced was accepted: %s"
                        % evidence[-700:])
    if "Bonded" not in _line(out, "PART_NOT_INSTANCED"):
        problems.append("the refusal did not name the part: %s"
                        % _line(out, "PART_NOT_INSTANCED")[:300])
    return {
        "id": "generic_assembly_refuses_a_merge_nothing_instanced",
        "status": "pass" if not problems else "fail",
        "mutation": "PartFromBooleanMerge with no instance of the result",
        "aborted": "PART_NOT_INSTANCED" in evidence,
        "note": "quieter than the cut, and worse: measured, "
                "PartFromBooleanMerge returns a Part, adds it to m.parts, "
                "creates no instance and suppresses nothing -- a.instances is "
                "untouched and both originals stay meshed. Every count and "
                "every position still agrees; what solves is the model from "
                "before the merge, which for two halves meant to be one solid "
                "is a different answer, not a missing one.",
        "problems": problems,
    }


def check_boolean_repair(work: Path) -> dict:
    """The door the other two items' refusals point at. Without it they are a
    wall, and a refusal with no way out is its own kind of wrong answer."""
    out = _build(work / "bool_repair",
                 _boolean_spec(REPAIR_OPS, "Cut-1:face@z=min"))
    evidence = _evidence(out)
    inp = work / "bool_repair" / "GenericBoolean.inp"
    body = inp.read_text(encoding="utf-8", errors="replace") if inp.exists() else ""
    element_lines = 0
    inside = False
    for line in body.splitlines():
        if line.upper().startswith("*ELEMENT, TYPE="):
            inside = True
            continue
        if inside:
            if line.startswith("*"):
                break
            element_lines += 1
    sectioned = any("*Solid Section" in line for line in body.splitlines())

    problems = []
    if out["rc"] != 0 or "ASSEMBLY_MESH_OK" not in evidence:
        problems.append("the repaired cut did not pass the check it is meant "
                        "to satisfy: %s" % evidence[-700:])
    if element_lines < 100:
        problems.append("the written .inp carries %d element lines"
                        % element_lines)
    if not sectioned:
        problems.append("the written .inp carries no *Solid Section, so the "
                        "cut body would have no material")
    return {
        "id": "generic_assembly_meshes_a_boolean_result",
        "status": "pass" if not problems else "fail",
        "identity": "the instance carries the mesh, not the part",
        "elements_written": element_lines,
        "section_written": sectioned,
        "note": "makeIndependent then setMeshControls + seedPartInstance + "
                "generateMesh. The .inp keeps an empty *Part, name=Cut -- for "
                "an independent instance that is correct, the nodes and "
                "elements are written inside the *Instance block, which is "
                "why this layer asks the instance for its element count and "
                "never the part. The *Solid Section is inherited from the "
                "body that was cut.",
        "problems": problems,
    }


def check_boolean_expect_measures_the_result(work: Path) -> dict:
    """`expect:` on the operation, checked against what the boolean produced.

    The cut is 20x20x20 minus a 6x6 pin straight through: 8000 - 6*6*20 = 7280.
    Measured on Abaqus 2021 (artifacts/probe_asm_op_expect) at exactly that,
    live without a.regenerate(), and read off the PART -- the PartInstance the
    cut returns carries partName but no getVolume.
    """
    out = _build(work / "bool_expect",
                 _boolean_spec(_repair_with_expect({"volume": 7280.0,
                                                    "cells": 1}),
                               "Cut-1:face@z=min"))
    evidence = _evidence(out)
    problems = []
    if "ASM_EXPECT_OK" not in evidence:
        problems.append("a stated volume and cell count that are both right "
                        "did not pass: %s" % evidence[-700:])
    ok_line = _line(out, "ASM_EXPECT_OK")
    if "volume=7280.0" not in ok_line:
        problems.append("the check did not report the volume it measured: %s"
                        % ok_line[:300])
    return {
        "id": "generic_assembly_expect_measures_the_boolean_result",
        "status": "pass" if not problems else "fail",
        "identity": "20^3 block minus a 6x6 pin through it = 7280.0, 1 cell",
        "measured": ok_line[:200],
        "note": "before this, `expect:` on an operation passed jsonschema, "
                "passed validate_references, generated an 84 KB deck and "
                "appeared nowhere in it",
        "problems": problems,
    }


def check_boolean_expect_catches_a_wrong_number(work: Path) -> dict:
    """The same run with the uncut volume stated. Must abort.

    Without this, the item above passes for a check that is not looking. 8000.0
    is the volume the block had BEFORE the cut, which is the number a cut that
    did nothing would produce.
    """
    out = _build(work / "bool_expect_wrong",
                 _boolean_spec(_repair_with_expect({"volume": 8000.0,
                                                    "cells": 1}),
                               "Cut-1:face@z=min"))
    evidence = _evidence(out)
    inp = work / "bool_expect_wrong" / "GenericBoolean.inp"
    problems = []
    if "ASM_EXPECT_VOLUME" not in evidence:
        problems.append("the uncut volume was accepted: %s" % evidence[-700:])
    if inp.exists():
        problems.append("an .inp was written for a body whose volume the spec "
                        "gets wrong by 9%")
    refusal = _line(out, "ASM_EXPECT_VOLUME")
    if "7280.0" not in refusal or "8000.0" not in refusal:
        problems.append("the refusal does not carry both numbers: %s"
                        % refusal[:300])
    return {
        "id": "generic_assembly_expect_catches_a_wrong_number",
        "status": "pass" if not problems else "fail",
        "mutation": "expect.volume 7280.0 -> 8000.0, the volume before the cut",
        "aborted": "ASM_EXPECT_VOLUME" in evidence,
        "refusal_line": refusal[:300],
        "problems": problems,
    }


CHECKS = [
    check_tet, check_silent_zero, check_requires_expect, check_element_count,
    check_mixed_order, check_pattern, check_instance_count, check_misplaced,
    check_boolean_cut_unmeshed, check_boolean_merge_uninstanced,
    check_boolean_repair, check_boolean_expect_measures_the_result,
    check_boolean_expect_catches_a_wrong_number,
]
ITEM_IDS = [
    "generic_mesh_tets_a_part_with_no_hex_route",
    "generic_mesh_refuses_a_silent_zero",
    "generic_mesh_requires_an_expect_block",
    "generic_mesh_asserts_the_element_count",
    "generic_mesh_explains_a_mixed_element_order",
    "generic_assembly_pattern_lands_in_the_holes",
    "generic_assembly_refuses_a_wrong_instance_count",
    "generic_assembly_refuses_a_misplaced_instance",
    "generic_assembly_refuses_a_cut_nothing_meshed",
    "generic_assembly_refuses_a_merge_nothing_instanced",
    "generic_assembly_meshes_a_boolean_result",
    "generic_assembly_expect_measures_the_boolean_result",
    "generic_assembly_expect_catches_a_wrong_number",
]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Real Abaqus check for the generic mesh and assembly layers.")
    parser.add_argument("--json-out", type=Path, default=None)
    parser.add_argument("--work-dir", type=Path, default=None)
    parser.add_argument("--only", action="append", default=None)
    args = parser.parse_args(argv)

    work = args.work_dir or Path(tempfile.mkdtemp(prefix="generic_mesh_"))
    work.mkdir(parents=True, exist_ok=True)

    if not check_abaqus():
        items = [_skipped(i, "Abaqus not found (set ABAQUS_AGENT_ABAQUS_CMD)")
                 for i in ITEM_IDS]
    else:
        items = []
        for check, item_id in zip(CHECKS, ITEM_IDS):
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
            print("  %-48s %s" % (item["id"], item["status"]), file=sys.stderr)

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
        "schema": "generic_mesh_check/1",
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
