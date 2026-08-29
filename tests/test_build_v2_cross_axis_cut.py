"""Cutting a hole ACROSS the extrusion direction.

The named `cut_extrude` only drives off the z=max face, so a bolt hole through a
column flange -- the flange normal runs along x while the column extrudes along
z -- has no named form at all. The generic path does it: a datum plane, a datum
axis, MakeSketchTransform, a sketch BUILT with that transform, then CutExtrude.

Measured on Abaqus 2021 (artifacts/promo/probe_sidecut), 100x100x200 block with
a 30 dia hole through the +x face:

  * Without `sketchUpEdge` the cut dies with "Invalid sketch up direction" --
    a datum plane does not remove the need for an up direction, it only removes
    the need to guess which EDGE supplies it.
  * volume 1929314.16529 against 2000000 - pi*15^2*100, off by 2.4e-09.
  * The hole was cut OFF-CENTRE on purpose, at sketch (30, 0). A centred hole
    proves nothing here: the documented failure is sketch x and y transposed,
    which leaves both the volume and the element count identical. With
    sketchUpEdge=ZAXIS the sketch +y is global +z and right-handedness puts
    sketch +x on global +y, so the axis midpoint is (0, 30, 100) --
    `cylinders=1 (worst off by 0 of 0.03 allowed)`.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from runner.build_v2 import generate_script  # noqa: E402


def _spec():
    return {
        "meta": {"abaqus_release": "2021", "model_name": "SideCut", "units": "mm_MPa_t"},
        "material": {"name": "Steel", "E": 210000.0, "nu": 0.3},
        "parts": [{
            "name": "Block",
            "features": [
                {"op": "sketch", "id": "base", "plane": "XY",
                 "profile": {"rect": {"corner1": [-50.0, -50.0],
                                      "corner2": [50.0, 50.0]}}},
                {"op": "extrude", "sketch": "base", "depth": 200.0},
                {"call": "DatumPlaneByPrincipalPlane", "principalPlane": "YZPLANE",
                 "offset": 50.0, "as": "dp"},
                {"call": "DatumAxisByPrincipalAxis", "principalAxis": "ZAXIS",
                 "as": "ax"},
                {"call": "MakeSketchTransform", "sketchPlane": {"datum": "dp"},
                 "sketchUpEdge": {"datum": "ax"}, "sketchPlaneSide": "SIDE1",
                 "sketchOrientation": "RIGHT", "origin": [50.0, 0.0, 100.0],
                 "as": "tf"},
                {"op": "sketch", "id": "hole", "transform": {"ref": "tf"},
                 "entities": [{"call": "CircleByCenterPerimeter",
                               "center": [30.0, 0.0], "point1": [45.0, 0.0]}]},
                {"call": "CutExtrude", "sketchPlane": {"datum": "dp"},
                 "sketchUpEdge": {"datum": "ax"}, "sketchPlaneSide": "SIDE1",
                 "sketchOrientation": "RIGHT", "sketch": {"sketch": "hole"},
                 "flipExtrudeDirection": "OFF"},
            ],
            "expect": {"volume": 1929314.17,
                       "cylinders": [{"r": 15.0, "at": [0.0, 30.0, 100.0]}]},
            "section": {"type": "solid", "material": "Steel"},
            "mesh": {"seed": 15.0, "element": "C3D10"},
        }],
        "assembly": {"instances": [{"name": "B1", "part": "Block"}]},
        "steps": [{"name": "S", "type": "Static",
                   "bcs": [{"name": "F", "region": "B1:face@z=min", "type": "encastre"}],
                   "loads": [{"name": "L", "region": "B1:face@z=max",
                              "type": "pressure", "value": 1.0}]}],
        "outputs": {"kpis": [{"name": "M", "type": "field_max",
                              "location": "whole_model"}]},
    }


def test_the_sketch_is_built_with_the_transform():
    """CutExtrude on a sketch made without one raises 'Cut extrude feature
    failed', and the transform cannot be attached afterwards."""
    script = generate_script(_spec())
    sketch_line = [ln for ln in script.splitlines()
                   if "ConstrainedSketch(" in ln and "sk_Block_hole" in ln]
    assert len(sketch_line) == 1
    assert "transform=" in sketch_line[0]


def test_transform_and_cut_are_given_the_same_up_axis():
    """The two disagreeing is how a hole lands somewhere else in silence.

    Matched against the dispatched form, `_gcall(p, '<name>', {...})`. Plain
    `MakeSketchTransform(` also appears in the runtime header, inside the named
    cut_extrude path, which is a different code path entirely.
    """
    script = generate_script(_spec())
    up = "'sketchUpEdge': p.datums[_RESULTS['ax'].id]"
    for call in ("MakeSketchTransform", "CutExtrude"):
        line = [ln for ln in script.splitlines() if "_gcall(p, %r" % call in ln]
        assert len(line) == 1, call
        assert up in line[0], call
        assert "'sketchOrientation': RIGHT" in line[0], call


def test_the_offcentre_hole_position_is_asserted():
    """A centred hole would pass with sketch x and y transposed."""
    script = generate_script(_spec())
    assert "30.0" in script
    joined = " ".join(script.split())
    assert "0.0, 30.0, 100.0" in joined or "(0.0, 30.0, 100.0)" in joined


def test_datum_results_are_bound_for_later_features():
    script = generate_script(_spec())
    assert "_RESULTS['dp']" in script or "_RESULTS[u'dp']" in script
    assert "_RESULTS['ax']" in script or "_RESULTS[u'ax']" in script
