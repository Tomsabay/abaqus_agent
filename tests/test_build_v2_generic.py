"""Generic dispatch: naming the Abaqus method instead of naming a shape.

Hermetic — nothing here starts Abaqus. The real-solver evidence lives in
scripts/run_generic_part_check.py, whose ten items were run on Abaqus 2021: a
revolved flange built from seven Line calls matches pi*(30^2-4^2)*10 +
pi*(10^2-4^2)*15 to 4.5e-7, a fillet through the tuple shim matches
2*pi*r^3*(5/3 - pi/2), and four mutations each abort.

The named ops (`op: sketch` / `extrude` / `cut_extrude`) can only build shapes
somebody wrote a branch for, and Abaqus exposes 292 callables on Part and 71 on
ConstrainedSketch. Handing the method name through is safe for two measured
reasons: every way of getting a call wrong is loud (unknown method ->
AttributeError, unknown keyword -> "keyword error on <name>", wrong type ->
"found string, expecting tuple"), and what it gives up -- a schema that knows
what each op was supposed to produce -- is replaced by `expect:`, checked
against the built geometry before it is meshed.

Most of the tests below are refusals, for the same reason as in
test_build_v2.py: a deck that meshes, solves and answers a different question
is worse than a build that stops.
"""

from __future__ import annotations

import ast
import copy
import re
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from runner import build_v2  # noqa: E402
from runner import kernel_runtime
from runner import spec_base

CASE = ROOT / "cases" / "two_plate_tie" / "spec.yaml"

# A squat flange: revolve this about x = 0 and you get an annulus 4..30 wide and
# 10 tall. Small on purpose -- these tests read the emitted text, never a solver.
REVOLVE_FEATURES = [
    {"op": "sketch", "id": "profile", "entities": [
        {"call": "ConstructionLine", "point1": [0.0, 0.0], "point2": [0.0, 10.0]},
        {"call": "Line", "point1": [4.0, 0.0], "point2": [30.0, 0.0]},
        {"call": "Line", "point1": [30.0, 0.0], "point2": [30.0, 10.0]},
        {"call": "Line", "point1": [30.0, 10.0], "point2": [4.0, 10.0]},
        {"call": "Line", "point1": [4.0, 10.0], "point2": [4.0, 0.0]},
    ]},
    {"call": "BaseSolidRevolve", "sketch": {"sketch": "profile"},
     "angle": 360.0, "flipRevolveDirection": "OFF"},
]


@pytest.fixture
def named_spec() -> dict:
    return yaml.safe_load(CASE.read_text(encoding="utf-8"))


@pytest.fixture
def spec(named_spec) -> dict:
    """The shipped case with its single part rebuilt from generic calls."""
    out = copy.deepcopy(named_spec)
    part = out["parts"][0]
    part["features"] = copy.deepcopy(REVOLVE_FEATURES)
    part["expect"] = {"volume": 26389.378290154, "cells": 1, "faces": 4}
    # A part with neither a `mesh:` block nor an `expect.mesh` is refused: it
    # would reach the input file as an empty *Part with a live *Instance and
    # the job would complete without a word. These tests are about the
    # geometry that is built BEFORE meshing, so the block is kept minimal
    # rather than dropped -- the expect lines still run ahead of it, which is
    # what test_expect_is_checked_before_the_mesh pins.
    part["mesh"] = {"seed": 5.0, "element": "C3D8R"}
    out.pop("interactions", None)
    out["assembly"]["instances"] = [{"name": "Lower", "part": part["name"]}]
    for step in out["steps"]:
        step["bcs"] = [{"name": "Fix", "type": "encastre",
                        "region": "Lower:face@y=min", "expect": ">=1"}]
        step.pop("loads", None)
    return out


def _emit(spec: dict) -> str:
    text = build_v2.generate_script(spec)
    ast.parse(text)          # the kernel is Python 2.7, but syntax is syntax
    return text


def _refuse(spec: dict) -> str:
    with pytest.raises(spec_base.SpecError) as caught:
        build_v2.generate_script(spec)
    return str(caught.value)


# ---------------------------------------------------------------------------
# What it emits
# ---------------------------------------------------------------------------

def test_a_generic_call_becomes_a_dispatch(spec):
    text = _emit(spec)
    assert "_gcall(p, 'BaseSolidRevolve'" in text
    assert "'angle': 360.0" in text


def test_a_sketch_entity_dispatches_against_the_sketch(spec):
    text = _emit(spec)
    assert "_gcall(_sk_profile, 'ConstructionLine'" in text
    assert "_gcall(_sk_profile, 'Line'" in text


def test_an_all_caps_string_becomes_an_abaqus_symbol(spec):
    """The generated script does `from abaqusConstants import *`.

    So the bare word IS the symbol, and a word that is not one is a NameError
    naming it. Quoting it would pass the string 'OFF' into a keyword that wants
    a SymbolicConstant, which Abaqus reports far from the spec line that caused
    it.
    """
    text = _emit(spec)
    assert "'flipRevolveDirection': OFF" in text
    assert "'flipRevolveDirection': 'OFF'" not in text


def test_a_literal_forces_an_all_caps_string_through(spec):
    spec["parts"][0]["features"].append(
        {"call": "Set", "name": {"literal": "RIM"},
         "edges": {"select": "edges@all"}})
    assert "'name': 'RIM'" in _emit(spec)


def test_a_list_becomes_a_tuple(spec):
    spec["parts"][0]["features"].append(
        {"call": "DatumPointByCoordinate", "coords": [1.0, 2.0, 3.0]})
    assert "'coords': (1.0, 2.0, 3.0)" in _emit(spec)


def test_a_one_element_list_keeps_its_trailing_comma(spec):
    """`(x)` is x; `(x,)` is a tuple. Abaqus tables are nested one-tuples."""
    spec["parts"][0]["features"].append(
        {"call": "Whatever", "table": [[0.3]]})
    assert "'table': ((0.3,),)" in _emit(spec)


def test_a_selector_argument_is_resolved_and_counted(spec):
    spec["parts"][0]["features"].append(
        {"call": "Round", "radius": 2.0,
         "edgeList": {"select": "edges@r=10", "expect": "=2"}})
    text = _emit(spec)
    assert "_sel_resolve(p, 'edges', 'r', '10'" in text
    assert "'=2'" in text


def test_a_datum_is_reached_through_the_feature_it_came_from(spec):
    """A Datum* method returns a FEATURE, not the datum.

    The datum lives at part.datums[feature.id]. That indirection is in every
    CAE macro and explained by none of them, so the spec says {datum: name} and
    the generator writes the lookup.
    """
    spec["parts"][0]["features"] += [
        {"call": "DatumPlaneByPrincipalPlane", "principalPlane": "XZPLANE",
         "offset": 5.0, "as": "mid"},
        {"call": "PartitionCellByDatumPlane", "datumPlane": {"datum": "mid"},
         "cells": {"select": "cells@all"}},
    ]
    text = _emit(spec)
    assert "_RESULTS['mid'] = _gcall(p, 'DatumPlaneByPrincipalPlane'" in text
    assert "p.datums[_RESULTS['mid'].id]" in text


def test_a_generic_sketch_may_carry_a_transform(spec):
    """A sketch that will drive a cut has to be BUILT with the transform.

    Measured on Abaqus 2021: CutExtrude on a sketch made without one raises
    "Cut extrude feature failed", and there is no way to attach it afterwards.
    """
    spec["parts"][0]["features"] += [
        {"call": "DatumPlaneByPrincipalPlane", "principalPlane": "XZPLANE",
         "offset": 10.0, "as": "top"},
        {"call": "DatumAxisByPrincipalAxis", "principalAxis": "XAXIS",
         "as": "up"},
        {"call": "MakeSketchTransform", "sketchPlane": {"datum": "top"},
         "sketchUpEdge": {"datum": "up"}, "sketchPlaneSide": "SIDE1",
         "sketchOrientation": "RIGHT", "origin": [0.0, 10.0, 0.0], "as": "xf"},
        {"op": "sketch", "id": "holes", "transform": {"ref": "xf"},
         "entities": [{"call": "CircleByCenterPerimeter",
                       "center": [20.0, 0.0], "point1": [23.0, 0.0]}]},
    ]
    assert "transform=_RESULTS['xf']" in _emit(spec)


def test_the_sketch_canvas_covers_what_the_entities_draw(spec):
    line = [ln for ln in _emit(spec).splitlines() if "_sk_profile = " in ln][0]
    assert float(line.split("sheetSize=")[1].rstrip(")")) >= 30.0


def test_a_stated_sheet_size_wins(spec):
    spec["parts"][0]["features"][0]["sheet_size"] = 17.0
    line = [ln for ln in _emit(spec).splitlines() if "_sk_profile = " in ln][0]
    assert "sheetSize=17.0" in line


# ---------------------------------------------------------------------------
# What it refuses
# ---------------------------------------------------------------------------

def test_a_boolean_is_refused_with_the_yaml_trap_named(spec):
    """`flipRevolveDirection: off` is False by the time YAML is done."""
    spec["parts"][0]["features"][1]["flipRevolveDirection"] = False
    message = _refuse(spec)
    assert "YAML" in message and '"OFF"' in message


def test_a_selector_argument_may_not_name_an_instance(spec):
    spec["parts"][0]["features"].append(
        {"call": "Round", "radius": 2.0,
         "edgeList": {"select": "Lower:edges@r=10"}})
    assert "before it is instanced" in _refuse(spec)


def test_a_forward_reference_is_refused(spec):
    spec["parts"][0]["features"].append(
        {"call": "PartitionCellByDatumPlane", "datumPlane": {"datum": "later"},
         "cells": {"select": "cells@all"}})
    message = _refuse(spec)
    assert "later" in message and "as:" in message


def test_a_feature_cannot_refer_to_its_own_result(spec):
    spec["parts"][0]["features"].append(
        {"call": "DatumPlaneByPrincipalPlane", "principalPlane": "XZPLANE",
         "offset": {"ref": "itself"}, "as": "itself"})
    assert "itself" in _refuse(spec)


def test_two_features_cannot_bind_the_same_name(spec):
    spec["parts"][0]["features"] += [
        {"call": "DatumAxisByPrincipalAxis", "principalAxis": "XAXIS",
         "as": "up"},
        {"call": "DatumAxisByPrincipalAxis", "principalAxis": "YAXIS",
         "as": "up"},
    ]
    assert "already the name" in _refuse(spec)


def test_a_mapping_naming_nothing_known_is_refused(spec):
    spec["parts"][0]["features"].append(
        {"call": "Round", "radius": 2.0, "edgeList": {"pick": "edges@all"}})
    message = _refuse(spec)
    assert "exactly one" in message and "select" in message


def test_a_sketch_reference_to_an_undrawn_sketch_is_refused(spec):
    spec["parts"][0]["features"][1]["sketch"] = {"sketch": "nope"}
    assert "before it is drawn" in _refuse(spec)


def test_a_private_method_name_is_refused(spec):
    """Dispatch reaches whatever it is handed. `__class__` is not modelling."""
    spec["parts"][0]["features"][1]["call"] = "__class__"
    assert "public Abaqus method name" in _refuse(spec)


def test_a_keyword_that_is_not_an_identifier_is_refused(spec):
    spec["parts"][0]["features"][1]["angle deg"] = 90.0
    assert "keyword name" in _refuse(spec)


def test_a_sketch_id_that_cannot_be_a_variable_is_refused(named_spec):
    """`identifier` in the schema allows a hyphen; a variable name does not.

    `id: out-line` used to emit `_sk_out-line = ...` and die as a syntax error
    inside the CAE kernel, a long way from the spec line that caused it.
    """
    named_spec["parts"][0]["features"][0]["id"] = "out-line"
    named_spec["parts"][0]["features"][1]["sketch"] = "out-line"
    assert "variable name" in _refuse(named_spec)


def test_a_named_op_cannot_consume_a_generic_sketch(spec):
    """cut_extrude replays a recorded profile to prove the hole landed."""
    spec["parts"][0]["features"] = [
        copy.deepcopy(REVOLVE_FEATURES[0]),
        {"op": "extrude", "sketch": "profile", "depth": 5.0},
    ]
    message = _refuse(spec)
    assert "BaseSolidExtrude" in message and "recorded profile" in message


# ---------------------------------------------------------------------------
# expect: the truth layer that replaces the schema's protection
# ---------------------------------------------------------------------------

def test_a_generic_part_without_expect_is_refused(spec):
    spec["parts"][0].pop("expect")
    message = _refuse(spec)
    assert "expect" in message and "silent" in message


def test_a_named_op_part_needs_no_expect(named_spec):
    """The named ops carry their own checks, so this is not a new tax."""
    assert "expect" not in named_spec["parts"][0]
    _emit(named_spec)


def test_expect_is_checked_before_the_mesh(spec):
    """Meshing a part that is already the wrong shape wastes minutes.

    And then it passes its own mesh check, which reads as confirmation.
    """
    spec["parts"][0]["mesh"] = {"seed": 5.0, "element": "C3D8R"}
    text = _emit(spec)
    assert text.index("_expect_part(p,") < text.index("p.generateMesh()")


def test_expect_emits_every_stated_measure(spec):
    spec["parts"][0]["expect"] = {
        "volume": 100.0, "volume_tol": 0.02, "cells": 1, "faces": 6,
        "edges": 12, "vertices": 8, "cylindrical_faces": 2}
    text = _emit(spec)
    for fragment in ("'volume': 100.0", "'volume_tol': 0.02", "'cells': 1",
                     "'faces': 6", "'edges': 12", "'vertices': 8",
                     "'cylindrical_faces': 2"):
        assert fragment in text


def test_expect_cylinders_carry_a_position(spec):
    """Counts and volume cannot see a cut that landed in the wrong place.

    Measured on Abaqus 2021: one hole drilled with the sketch oriented against
    XAXIS instead of ZAXIS moved from (0, 5, 20) to (-20, 5, 0) -- 90 degrees
    away -- with volume 31447.3311 against 31447.3357, which is 1.5e-7 apart
    and therefore faceting, and faces, edges, vertices and cylindrical_faces
    all identical. On a symmetric part nothing global can tell them apart.
    """
    spec["parts"][0]["expect"]["cylinders"] = [
        {"r": 3.0, "at": [0.0, 5.0, 20.0]},
        {"r": 3.0, "at": [0.0, 5.0, -20.0], "at_tol": 0.01},
    ]
    text = _emit(spec)
    assert "(3.0, 0.0, 5.0, 20.0, %r)" % build_v2._centroid_tol(3.0) in text
    assert "(3.0, 0.0, 5.0, -20.0, 0.01)" in text


def test_the_default_centroid_tolerance_follows_the_feature(spec):
    """An absolute default is wrong at both ends of the scale.

    getCentroid() is a tessellation estimate whose error grows with the feature.
    Measured on Abaqus 2021: a through bore of r = 300 in a 900 mm plate reports
    its centroid 0.070931 from a position that is analytically exact, so the old
    fixed 0.05 refused a bore that was exactly where the spec said. At the other
    end, 0.05 on a part half a millimetre across accepts a hole a tenth of the
    part away. The real gate item is
    generic_big_bore_survives_its_own_instrument; this only pins the arithmetic.
    """
    big, small = build_v2._centroid_tol(500.0), build_v2._centroid_tol(0.05)
    assert big == 1.0                      # scales with the feature
    assert small == build_v2.CENTROID_TOL_FLOOR   # but never down to float noise
    assert big > 0.05 > small, "the old fixed 0.05 sat between these two"

    spec["parts"][0]["expect"]["cylinders"] = [{"r": 500.0, "at": [0.0, 5.0, 20.0]}]
    assert "(500.0, 0.0, 5.0, 20.0, 1.0)" in _emit(spec)


def test_the_kernel_restates_the_same_two_numbers():
    """The preamble is a literal, so the constants exist twice. Pin them.

    By value, not by spelling: 1.0e-3 and 0.001 are the same tolerance, and a
    test that only compares text would fail on a reformat and pass on a typo
    that changed the exponent.
    """
    for name, host in (("_CENTROID_TOL_FLOOR", build_v2.CENTROID_TOL_FLOOR),
                       ("_CENTROID_TOL_FACTOR", build_v2.CENTROID_TOL_FACTOR)):
        found = re.search(r"^%s = (\S+)$" % name, kernel_runtime._HELPERS, re.M)
        assert found, "%s is not defined in the kernel preamble" % name
        assert float(found.group(1)) == host


def test_expect_cylinders_alone_satisfies_the_requirement(spec):
    spec["parts"][0]["expect"] = {
        "cylinders": [{"r": 3.0, "at": [0.0, 5.0, 20.0]}]}
    _emit(spec)


@pytest.mark.parametrize("entry, fragment", [
    ({"r": 3.0, "at": [0.0, 5.0]}, "three numbers"),
    ({"r": -1.0, "at": [0.0, 0.0, 0.0]}, "r must be positive"),
    ({"r": 3.0, "at": [0.0, 0.0, 0.0], "at_tol": 0.0}, "at_tol must be positive"),
])
def test_a_malformed_cylinder_is_refused(spec, entry, fragment):
    spec["parts"][0]["expect"]["cylinders"] = [entry]
    assert fragment in _refuse(spec)


# ---------------------------------------------------------------------------
# The schema, not just the generator
# ---------------------------------------------------------------------------
#
# The generator is reached only by specs the schema already accepted, so a
# generic spec that the schema rejects is a generic spec nobody can write.

def _validate(spec: dict):
    from tools.schema_validator import validate_spec
    return validate_spec(spec)


def test_the_schema_accepts_a_generic_spec(spec):
    ok, errors = _validate(spec)
    assert ok, errors


def test_the_schema_accepts_datums_transforms_and_cylinders(spec):
    spec["parts"][0]["features"] += [
        {"call": "DatumPlaneByPrincipalPlane", "principalPlane": "XZPLANE",
         "offset": 10.0, "as": "top"},
        {"call": "DatumAxisByPrincipalAxis", "principalAxis": "XAXIS",
         "as": "up"},
        {"call": "MakeSketchTransform", "sketchPlane": {"datum": "top"},
         "sketchUpEdge": {"datum": "up"}, "sketchPlaneSide": "SIDE1",
         "sketchOrientation": "RIGHT", "origin": [0.0, 10.0, 0.0], "as": "xf"},
        {"op": "sketch", "id": "holes", "transform": {"ref": "xf"},
         "sheet_size": 200.0,
         "entities": [{"call": "CircleByCenterPerimeter",
                       "center": [20.0, 0.0], "point1": [23.0, 0.0]}]},
        {"call": "CutExtrude", "sketchPlane": {"datum": "top"},
         "sketchUpEdge": {"datum": "up"}, "sketchPlaneSide": "SIDE1",
         "sketchOrientation": "RIGHT", "sketch": {"sketch": "holes"},
         "depth": 10.0, "flipExtrudeDirection": "OFF"},
    ]
    spec["parts"][0]["expect"]["cylinders"] = [
        {"r": 3.0, "at": [0.0, 5.0, 20.0]}]
    ok, errors = _validate(spec)
    assert ok, errors


def test_the_schema_still_accepts_the_named_dialect(named_spec):
    ok, errors = _validate(named_spec)
    assert ok, errors


def test_the_schema_refuses_a_feature_that_is_neither(spec):
    """`op` and `call` are the two doors; a feature with neither is a typo."""
    spec["parts"][0]["features"].append({"radius": 2.0})
    ok, _errors = _validate(spec)
    assert not ok


def test_the_schema_refuses_a_measure_it_cannot_check(spec):
    """expect is a closed list on purpose: an unchecked key reads as checked."""
    spec["parts"][0]["expect"]["mass"] = 1.0
    ok, _errors = _validate(spec)
    assert not ok


def test_an_empty_cylinder_list_does_not_count_as_a_measure(spec):
    """The key is there and nothing is checked -- the one state not allowed.

    The schema's minItems catches this first; this is the belt behind that
    brace, and the failure it prevents is a generic part built with no truth
    layer at all.
    """
    spec["parts"][0]["expect"] = {"cylinders": []}
    message = _refuse(spec)
    assert "expect" in message and "silent" in message


def test_a_malformed_expect_is_caught_by_validation_not_just_generation(spec):
    """validate_references and the generator have to agree about a spec."""
    spec["parts"][0]["expect"]["cylinders"] = [{"r": 3.0, "at": [0.0, 5.0]}]
    with pytest.raises(spec_base.SpecError):
        build_v2.validate_references(spec)


# ---------------------------------------------------------------------------
# `{one: ...}` -- the entity, not the sequence of one
# ---------------------------------------------------------------------------

def _ftf_spec(named_spec, movable, fixed) -> dict:
    """Two instances of the shipped part, one positioned against the other."""
    out = copy.deepcopy(named_spec)
    out.pop("interactions", None)
    part = out["parts"][0]["name"]
    out["assembly"]["instances"] = [
        {"name": "Fixed", "part": part},
        {"name": "Mover", "part": part, "translate": [40.0, 0.0, 0.0]},
    ]
    out["assembly"]["operations"] = [{
        "call": "FaceToFace",
        "movablePlane": movable, "fixedPlane": fixed,
        "flip": "OFF", "clearance": 0.0,
    }]
    for step in out["steps"]:
        step["bcs"] = [{"name": "Fix", "type": "encastre",
                        "region": "Fixed:face@y=min", "expect": ">=1"}]
        step.pop("loads", None)
    return out


def _ftf_line(text: str) -> str:
    for line in text.splitlines():
        if line.strip().startswith("_gcall(a, 'FaceToFace'"):
            return line.strip()
    raise AssertionError("no FaceToFace dispatch in the emitted deck")


def test_select_still_compiles_to_a_sequence(named_spec):
    """The premise. `{select:}` cannot feed a method that wants one Face.

    core/selectors.py returns whatever getByBoundingBox produced and there is
    no path in it that returns an element, so a positioning constraint written
    with `{select:}` is handed a GeomSequence however few entities it names.
    Spelled the one way an operation still accepts, to show that even then it
    is the sequence that goes through.
    """
    text = _emit(_ftf_spec(named_spec,
                           {"select": "Mover:faces@x=min", "expect": "=1"},
                           {"one": "Fixed:face@x=max"}))
    line = _ftf_line(text)
    assert "_sel_resolve(a.instances['Mover']" in line
    assert "_gone(_sel_resolve(a.instances['Mover']" not in line


def test_one_passes_the_entity_itself(named_spec):
    text = _emit(_ftf_spec(named_spec, {"one": "Mover:face@x=min"},
                           {"one": "Fixed:face@x=max"}))
    line = _ftf_line(text)
    assert "_gone(_sel_resolve(a.instances['Mover']" in line
    assert "'assembly operation 1 movablePlane'" in line


def test_one_forces_the_count_assertion(named_spec):
    """Not read off the spec: exactly one is what the form means."""
    line = _ftf_line(_emit(_ftf_spec(named_spec, {"one": "Mover:face@x=min"},
                                     {"one": "Fixed:face@x=max"})))
    assert line.count("'=1'") == 2


def test_one_refuses_an_expect_beside_it(named_spec):
    message = _refuse(_ftf_spec(
        named_spec, {"one": "Mover:face@x=min", "expect": "=1"},
        {"one": "Fixed:face@x=max"}))
    assert "expect" in message and "one" in message


def test_one_in_the_assembly_must_say_which_instance(named_spec):
    message = _refuse(_ftf_spec(named_spec, {"one": "face@x=min"},
                                {"one": "Fixed:face@x=max"}))
    assert "which instance" in message


def test_one_on_a_part_feature_may_not_name_an_instance(spec):
    spec["parts"][0]["features"].append(
        {"call": "Round", "radius": 1.0, "edgeList": {"one": "Lower:edge@x=max"}})
    message = _refuse(spec)
    assert "names an instance" in message


def test_a_mistyped_instance_under_one_is_caught_before_the_deck(named_spec):
    """The fail-open the form would otherwise introduce.

    _nested_selectors walks a literal tuple of form names. Measured before the
    `one` entry was added: this spec passed validate_references, and the bad
    instance name became a KeyError inside the generated file -- the exact
    failure that walk exists to prevent.
    """
    bad = _ftf_spec(named_spec, {"one": "Typo:face@x=min"},
                    {"one": "Fixed:face@x=max"})
    with pytest.raises(spec_base.SpecError) as caught:
        build_v2.validate_references(bad)
    assert "Typo" in str(caught.value)


def test_the_helper_refuses_rather_than_taking_the_first(spec):
    """_gone is the belt behind _sel_resolve's brace."""
    body = _emit(spec)
    start = body.index("def _gone(")
    end = body.index("def _gvertex(")
    helper = body[start:end]
    assert "ONE_NOT_SINGLE" in helper
    assert "_expect_fail(" in helper
    assert "return found[0]" in helper


# ---------------------------------------------------------------------------
# `expect:` on a part feature -- refused, not dropped
# ---------------------------------------------------------------------------

def test_expect_on_a_feature_is_refused_not_dropped(spec):
    """It validated, generated a full deck, and the number was nowhere in it.

    schema/spec_schema.json's generic_call ends additionalProperties:true and
    _generic_call's reserved tuple skips `expect`, so a measure stated on a
    feature reached neither the deck nor validate_references. `expect:` is
    honoured on an interaction and a condition and refused on model_setup and
    a step; silently dropping it here read as a fourth behaviour.
    """
    spec["parts"][0]["features"][-1]["expect"] = {"volume": 424242.0}
    message = _refuse(spec)
    assert "feature" in message and "nothing to measure" in message
    assert "part" in message and "expect" in message


def test_the_part_keeps_its_own_expect(spec):
    """The refusal above must not close the door it points at."""
    text = _emit(spec)
    assert "_expect_part(" in text
    assert "26389.378290154" in text


def _guard_lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines()
            if line.strip().startswith("_expect_recorded(")]


def test_a_singular_select_inside_an_operation_arms_a_run_time_guard(named_spec):
    """The silent no-op, caught where it can be told apart from a working call.

    Measured on Abaqus 2021 (artifacts/probe_position_seq/probe_out.txt):
    FaceToFace / ParallelFace / EdgeToEdge / CoincidentPoint handed the
    sequence `{select:}` compiles to all return None, add nothing to
    a.features, grow no repository and leave the instance where it was, before
    and after a.regenerate(). Handed the entity itself they return a named
    Feature and move it 40.0 / 10.0 / 30.0 / 30.0 mm.
    """
    text = _emit(_ftf_spec(named_spec, {"select": "Mover:face@x=min"},
                           {"one": "Fixed:face@x=max"}))
    guards = _guard_lines(text)
    assert guards, "a sequence-of-one argument must arm the guard"
    assert "'movablePlane'" in guards[0]


def test_the_guard_reads_the_return_value_not_whether_anything_changed(spec):
    """makeIndependent and seedPartInstance change nothing and are correct.

    Measured in the same probe run: both return OK with registry_delta=NONE,
    features_added=NONE and moved=NO -- and they are the documented way to
    mesh a boolean result. A rule about change would refuse the escape hatch.
    """
    text = _emit(spec)
    start = text.index("def _expect_recorded(")
    end = text.index("def _gone(")
    helper = text[start:end]
    assert "if result is not None:" in helper
    assert "CALL_RECORDED_NOTHING" in helper
    assert "_expect_fail(" in helper


def test_saying_you_meant_a_sequence_disarms_the_guard(named_spec):
    """The way out is to say it, which is also what makes it readable."""
    text = _emit(_ftf_spec(named_spec,
                           {"select": "Mover:faces@x=min", "expect": "=1"},
                           {"one": "Fixed:face@x=max"}))
    assert _guard_lines(text) == []


def test_a_plural_select_does_not_arm_the_guard(named_spec):
    """False-refusal budget. The shipped repair route selects `cells@all`."""
    from core import selectors

    assert selectors.parse("Cut-1:cells@all").expect == ">=1"
    text = _emit(_ftf_spec(named_spec, {"select": "Mover:faces@all"},
                           {"one": "Fixed:face@x=max"}))
    assert _guard_lines(text) == []


def test_one_does_not_arm_the_guard(named_spec):
    """It cannot fire on the correct spelling: there is no sequence left."""
    text = _emit(_ftf_spec(named_spec, {"one": "Mover:face@x=min"},
                           {"one": "Fixed:face@x=max"}))
    assert _guard_lines(text) == []


def test_a_set_built_from_one_face_is_guarded_but_not_refused(named_spec):
    """The measured false refusal that killed the generation-time version.

    `a.Set(faces=<sequence of one>)` is exactly right, and a rule scoped to
    the operations block refused it. The guard is still emitted -- the shape
    is the same -- and Set returns a Set object, so it never fires.
    """
    spec = _ftf_spec(named_spec, {"one": "Mover:face@x=min"},
                     {"one": "Fixed:face@x=max"})
    spec["assembly"]["operations"].append(
        {"call": "Set", "name": {"literal": "RIM"},
         "faces": {"select": "Fixed:face@y=max"}})
    guards = _guard_lines(_emit(spec))
    assert len(guards) == 1 and "'faces'" in guards[0]


def test_an_alias_is_guarded_through_the_results_dict(named_spec):
    """A bound name must not be shadowed by the temporary the guard needs."""
    spec = _ftf_spec(named_spec, {"one": "Mover:face@x=min"},
                     {"one": "Fixed:face@x=max"})
    spec["assembly"]["operations"].append(
        {"call": "Set", "as": "rim", "name": {"literal": "RIM"},
         "faces": {"select": "Fixed:face@y=max"}})
    assert "_expect_recorded(_RESULTS['rim']" in _emit(spec)


# ---------------------------------------------------------------------------
# `expect:` on an assembly operation -- honoured, where a feature's is refused
# ---------------------------------------------------------------------------

def _cut_spec(named_spec, expect=None):
    """An InstanceFromBooleanCut, optionally carrying a measure."""
    out = copy.deepcopy(named_spec)
    out.pop("interactions", None)
    part = out["parts"][0]["name"]
    op = {"call": "InstanceFromBooleanCut", "name": {"literal": "Cut"},
          "instanceToBeCut": {"instance": "Blk"},
          "cuttingInstances": [{"instance": "Pn"}],
          "originalInstances": "SUPPRESS", "creates": ["Cut-1"]}
    if expect is not None:
        op["expect"] = copy.deepcopy(expect)
    out["assembly"]["instances"] = [
        {"name": "Blk", "part": part},
        {"name": "Pn", "part": part, "translate": [7.0, 7.0, -10.0]},
    ]
    out["assembly"]["operations"] = [op]
    out["assembly"].pop("expect", None)
    for step in out["steps"]:
        step["bcs"] = [{"name": "Fix", "type": "encastre",
                        "region": "Cut-1:face@z=min", "expect": ">=1"}]
        step.pop("loads", None)
    return out


def _asm_op_lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines()
            if line.strip().startswith("_expect_asm_op(")]


def test_an_operation_expect_reaches_the_deck(named_spec):
    """It used to validate, generate an 84 KB deck, and appear in none of it."""
    text = _emit(_cut_spec(named_spec, {"volume": 7280.0, "cells": 1}))
    lines = _asm_op_lines(text)
    assert lines and "7280.0" in lines[0] and lines[0].endswith(", 1))")


def test_an_operation_without_expect_emits_nothing_extra(named_spec):
    assert _asm_op_lines(_emit(_cut_spec(named_spec))) == []


def test_the_volume_tolerance_defaults_to_the_part_layer_s(named_spec):
    """One name for the number, so the two layers cannot drift apart."""
    from runner.build_v2 import DEFAULT_VOLUME_TOL

    line = _asm_op_lines(_emit(_cut_spec(named_spec, {"volume": 7280.0})))[0]
    assert repr(DEFAULT_VOLUME_TOL) in line


def test_an_operation_expect_refuses_a_measure_it_cannot_take(named_spec):
    message = _refuse(_cut_spec(named_spec, {"mass": 1.0}))
    assert "volume" in message and "cells" in message
    assert "reads as checked" in message


def test_an_operation_expect_that_states_nothing_is_refused(named_spec):
    message = _refuse(_cut_spec(named_spec, {}))
    assert "checks nothing" in message


def test_a_tolerance_without_a_number_is_refused(named_spec):
    message = _refuse(_cut_spec(named_spec, {"volume_tol": 0.01}))
    assert "volume_tol" in message and "nobody stated" in message


def test_the_schema_accepts_an_operation_expect(named_spec):
    ok, errors = _validate(_cut_spec(named_spec, {"volume": 7280.0, "cells": 1}))
    assert ok, errors


def test_the_schema_refuses_a_measure_the_operation_cannot_take(named_spec):
    ok, _errors = _validate(_cut_spec(named_spec, {"mass": 1.0}))
    assert not ok


def test_the_check_reads_the_part_not_the_instance(spec):
    """Measured: the PartInstance a cut returns has no getVolume at all.

    artifacts/probe_asm_op_expect -- InstanceFromBooleanCut returns a
    PartInstance carrying partName='Cut' and NO getVolume; PartFromBooleanMerge
    returns a Part carrying getVolume and no partName. So the partName branch
    has to come first, and volume has to be read off m.parts[partName].
    """
    text = _emit(spec)
    start = text.index("def _expect_asm_op(")
    end = text.index("def _expect_recorded(")
    helper = text[start:end]
    assert helper.index("hasattr(obj, 'partName')") < helper.index("hasattr(obj, 'getVolume')")
    assert "m.parts[obj.partName]" in helper
    assert "ASM_EXPECT_UNMEASURABLE" in helper
