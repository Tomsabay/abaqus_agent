"""Generic dispatch for the two layers around the part: mesh, and assembly.

Hermetic — nothing here starts Abaqus. The solver evidence lives in
scripts/run_generic_mesh_check.py, eight items on Abaqus 2021, on a bolted
bearing housing that no hex route can mesh:

    HEX/FREE           refused, "Free Hex meshing is not supported"
    HEX/STRUCTURED     refused, "Some regions cannot be Mapped"
    HEX/SWEEP          refused, "Some regions cannot be Swept/Revolved"
    HEX/SYSTEM_ASSIGN  ACCEPTED -- zero elements, nothing raised
    TET/FREE           10030 elements, nothing unmeshed, nothing failed

The fourth line is the whole reason `expect.mesh` is mandatory when a part
meshes itself by name. The assembly half is the same argument one level up: a
pattern that produces nothing and a positioning constraint that moves nothing
both leave a model that meshes, solves and reports COMPLETED.
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
from runner import arg_forms
from runner import spec_base

CASE = ROOT / "cases" / "two_plate_tie" / "spec.yaml"

CELLS = {"select": "cells@all"}
QUADRATIC = [
    {"new": "mesh.ElemType", "elemCode": "C3D20R", "elemLibrary": "STANDARD"},
    {"new": "mesh.ElemType", "elemCode": "C3D15", "elemLibrary": "STANDARD"},
    {"new": "mesh.ElemType", "elemCode": "C3D10", "elemLibrary": "STANDARD"},
]
MESH_CALLS = [
    {"call": "setMeshControls", "regions": CELLS,
     "elemShape": "TET", "technique": "FREE"},
    {"call": "setElementType", "regions": [CELLS], "elemTypes": QUADRATIC},
    {"call": "seedPart", "size": 8.0, "deviationFactor": 0.1,
     "minSizeFactor": 0.1},
    {"call": "generateMesh"},
]


@pytest.fixture
def named_spec() -> dict:
    return yaml.safe_load(CASE.read_text(encoding="utf-8"))


@pytest.fixture
def spec(named_spec) -> dict:
    """The shipped case with its part meshed by name instead of by `mesh:`."""
    out = copy.deepcopy(named_spec)
    part = out["parts"][0]
    part.pop("mesh", None)
    part["features"] = part["features"] + copy.deepcopy(MESH_CALLS)
    part["expect"] = {"volume": 5000.0, "mesh": {"elements": ">=1"}}
    return out


def _emit(spec: dict) -> str:
    text = build_v2.generate_script(spec)
    ast.parse(text)
    return text


def _refuse(spec: dict) -> str:
    with pytest.raises(spec_base.SpecError) as caught:
        build_v2.generate_script(spec)
    return str(caught.value)


# ---------------------------------------------------------------------------
# Mesh
# ---------------------------------------------------------------------------

def test_mesh_methods_dispatch_like_any_other(spec):
    """They are Part methods, so the part layer already reached them."""
    text = _emit(spec)
    for name in ("setMeshControls", "setElementType", "seedPart", "generateMesh"):
        assert "_gcall(p, %r" % name in text


def test_an_element_type_is_constructed_not_called(spec):
    """mesh.ElemType lives in a module, on no part and no assembly.

    Without a way to build one, setElementType stays behind a hand-written
    wrapper -- which is the enumeration this layer exists to avoid.
    """
    text = _emit(spec)
    assert "_gnew('mesh', 'ElemType'" in text
    assert "'elemCode': C3D10" in text


def test_a_module_the_script_never_imports_is_refused(spec):
    spec["parts"][0]["features"][-3]["elemTypes"] = [
        {"new": "numpy.array", "object": [1.0]}]
    message = _refuse(spec)
    assert "numpy" in message and "does not" in message


def test_a_new_without_a_dotted_name_is_refused(spec):
    spec["parts"][0]["features"][-3]["elemTypes"] = [{"new": "ElemType"}]
    assert "<module>.<Class>" in _refuse(spec)


def test_the_module_list_comes_from_the_import_line(spec):
    """Retyping it would let the two drift apart silently."""
    text = _emit(spec)
    assert arg_forms._IMPORT_LINE in text
    for module in arg_forms._MODULES:
        assert module in text


def test_a_part_that_meshes_itself_needs_an_expect_mesh(spec):
    spec["parts"][0]["expect"].pop("mesh")
    message = _refuse(spec)
    assert "expect.mesh" in message and "SYSTEM_ASSIGN" in message


@pytest.mark.parametrize("call_name", [
    "generateMesh", "generateBottomUpSweptMesh", "generateMeshByOffset"])
def test_every_mesh_generator_triggers_the_requirement(spec, call_name):
    """Matched by shape, not by a list, so a new one is covered too."""
    spec["parts"][0]["features"][-1] = {"call": call_name}
    spec["parts"][0]["expect"].pop("mesh")
    assert "expect.mesh" in _refuse(spec)


def test_expect_mesh_emits_a_checked_count(spec):
    spec["parts"][0]["expect"]["mesh"] = {"elements": 10030, "max_warned": 0}
    text = _emit(spec)
    assert "_mesh_check(p, 'Half', '=10030', 0, None)" in text


def test_expect_mesh_refuses_a_measure_it_cannot_take(spec):
    spec["parts"][0]["expect"]["mesh"] = {"skewness": 0.9}
    assert "skewness" in _refuse(spec)


def test_expect_mesh_refuses_an_unreadable_count(spec):
    spec["parts"][0]["expect"]["mesh"] = {"elements": "lots"}
    assert "expect" in _refuse(spec)


def test_the_mesh_sugar_still_works_and_still_checks(named_spec):
    text = _emit(named_spec)
    assert "p.seedPart(size=2.5" in text
    assert "_mesh_check(p, 'Half')" in text


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------

@pytest.fixture
def asm_spec(named_spec) -> dict:
    out = copy.deepcopy(named_spec)
    out["assembly"]["operations"] = [{
        "call": "RadialInstancePattern",
        "instanceList": ["Lower"],
        "point": [0.0, 0.0, 0.0], "axis": [0.0, 1.0, 0.0],
        "number": 4, "totalAngle": 360.0,
        "creates": ["Lower-rad-2", "Lower-rad-3", "Lower-rad-4"],
    }]
    out["assembly"]["expect"] = {"instances": 5}
    return out


def test_an_assembly_operation_dispatches_against_the_root(asm_spec):
    text = _emit(asm_spec)
    assert "_gcall(a, 'RadialInstancePattern'" in text
    assert "'number': 4" in text


def test_an_assembly_selector_must_name_its_instance(asm_spec):
    """A part instanced twice has one set of faces.

    ``Lower:face@y=max`` and ``Upper:face@y=max`` are different faces only once
    the instance transform has been applied, so an unqualified phrase in the
    assembly cannot mean anything.
    """
    asm_spec["assembly"]["operations"].append(
        {"call": "Set", "name": {"literal": "RIM"},
         "faces": {"select": "face@y=max"}})
    message = _refuse(asm_spec)
    assert "which instance" in message


def test_an_assembly_selector_resolves_against_that_instance(asm_spec):
    asm_spec["assembly"]["operations"].append(
        {"call": "Set", "name": {"literal": "RIM"},
         "faces": {"select": "Lower:face@y=max"}})
    text = _emit(asm_spec)
    assert "_sel_resolve(a.instances['Lower'], 'faces'" in text


def test_the_set_form_refusal_does_not_send_a_seam_to_a_dead_end(asm_spec):
    """`{set:}` is unavailable here, and the advice has been wrong twice.

    First it said "this form belongs in a step or a condition" -- right for a
    part feature and wrong here, since a condition dispatches against the
    model, which has no `engineeringFeatures`, so following it arrives at an
    AttributeError. #64 replaced that with a refusal naming the attribute and
    calling the gap known.

    A known gap is still a dead end. #70 measured the way out and the message
    now names it: a PART set, which `{set:}` builds in part scope, assigned
    before `generateMesh` because a seam assigned after one leaves the node
    count untouched until something remeshes. So what this pins is that the
    refusal ROUTES -- a no with no next step is most of a bug report and none
    of a fix.
    """
    asm_spec["assembly"]["operations"].append(
        {"call": "assignSeam", "target": {"attr": "engineeringFeatures"},
         "regions": {"set": "Lower:face@y=max", "name": "SEAMFACE"}})
    message = _refuse(asm_spec)
    assert "PART" in message
    assert "generateMesh" in message
    assert "belongs in a step or a condition" not in message
    assert "known gap" not in message, (
        "it is not a gap any more, and a message that still says so sends the "
        "reader looking for a workaround that no longer needs finding")
    assert "cannot build one" not in message, (
        "#76 gave assembly operations a set registry, so that reason is now "
        "false outright. The true one is timing: part features run before "
        "generateMesh and assembly operations after it")


def test_an_instance_reference_is_only_meaningful_in_the_assembly(asm_spec):
    asm_spec["assembly"]["operations"].append(
        {"call": "translate", "instanceList": [{"instance": "Lower"}],
         "vector": [1.0, 0.0, 0.0]})
    assert "a.instances['Lower']" in _emit(asm_spec)


def test_a_part_feature_cannot_name_an_instance(spec):
    spec["parts"][0]["features"].append(
        {"call": "Set", "name": {"literal": "X"},
         "region": {"instance": "Lower"}})
    assert "before anything is instanced" in _refuse(spec)


def test_a_pattern_declares_the_instances_it_creates(asm_spec):
    """Otherwise a BC on a patterned instance cannot be told from a typo."""
    for step in asm_spec["steps"]:
        step["bcs"].append({"name": "FixRad", "type": "encastre",
                            "region": "Lower-rad-3:face@z=min"})
    _emit(asm_spec)


def test_a_bc_on_an_undeclared_instance_is_still_refused(asm_spec):
    for step in asm_spec["steps"]:
        step["bcs"].append({"name": "FixRad", "type": "encastre",
                            "region": "Lower-rad-9:face@z=min"})
    message = _refuse(asm_spec)
    assert "Lower-rad-9" in message


def test_creates_may_not_shadow_a_declared_instance(asm_spec):
    asm_spec["assembly"]["operations"][0]["creates"] = ["Upper"]
    assert "already an instance name" in _refuse(asm_spec)


def test_assembly_expect_counts_instances(asm_spec):
    assert "_expect_instances(a, 5)" in _emit(asm_spec)


def test_assembly_expect_states_where_things_land(asm_spec):
    """Positioning has no return value and raises nothing when it does nothing.

    Measured while writing the first real assembly: the sugar translates first
    and rotates second, the two do not commute, and written the other way round
    a bolt landed at (0, 67.5, 5) instead of (0, 7.5, 55) -- floating above the
    flange, every count intact, nothing raised.
    """
    asm_spec["assembly"]["expect"]["at"] = [
        {"instance": "Lower-rad-3", "centroid": [0.0, 7.5, 55.0]},
        {"instance": "Upper", "centroid": [1.0, 2.0, 3.0], "tol": 0.01},
    ]
    text = _emit(asm_spec)
    # No tol stated: an instance carries no radius and its size is not known
    # until the assembly exists, so the default is deferred to the kernel, which
    # takes it from the box it has to measure anyway.
    assert "('Lower-rad-3', 0.0, 7.5, 55.0, None)" in text
    assert "('Upper', 1.0, 2.0, 3.0, 0.01)" in text
    assert "abs(span) * _CENTROID_TOL_FACTOR" in text


@pytest.mark.parametrize("entry, fragment", [
    ({"instance": "Upper", "centroid": [0.0, 1.0]}, "three numbers"),
    ({"instance": "Upper", "centroid": [0.0, 1.0, 2.0], "tol": 0.0},
     "tol must be positive"),
])
def test_a_malformed_placement_is_refused(asm_spec, entry, fragment):
    asm_spec["assembly"]["expect"]["at"] = [entry]
    assert fragment in _refuse(asm_spec)


def test_assembly_expect_refuses_a_measure_it_cannot_take(asm_spec):
    asm_spec["assembly"]["expect"]["mass"] = 1.0
    assert "mass" in _refuse(asm_spec)


def test_the_assembly_sugar_is_untouched(named_spec):
    text = _emit(named_spec)
    assert "a.Instance(name='Lower'" in text
    assert "a.translate(instanceList=('Upper',)" in text


# ---------------------------------------------------------------------------
# What an operation leaves behind
#
# Parts are built and meshed before the assembly exists, so anything an
# operation creates is born unmeshed and nothing downstream meshes it.
# Measured on Abaqus 2021 (artifacts/probe59), two shapes of that:
#
#   InstanceFromBooleanCut  part Cut cells=1 elements=0 nodes=0, instance
#                           Cut-1 pointing at it, originals suppressed. The
#                           .inp carried *Part, name=Cut / *End Part with a
#                           live *Instance and not one *Element in the file.
#   PartFromBooleanMerge    returns a Part, adds it to m.parts, creates NO
#                           instance and suppresses nothing. a.instances is
#                           untouched, both originals stay meshed, and what
#                           solves is the model from before the merge.
#
# The second is why one check is not enough: walking a.instances cannot see a
# part that was never instanced.
# ---------------------------------------------------------------------------

def _helper_body(text: str, name: str) -> str:
    """The helper's CODE, with its docstring cut off.

    The docstring names what the code deliberately does not use, so leaving it
    in makes 'this attribute is not consulted' assertions pass on the sentence
    explaining why it is not consulted.
    """
    start = text.index("def %s(" % name)
    body = text[start:text.index("\ndef ", start + 1)]
    opened = body.index('"""')
    return body[body.index('"""', opened + 3) + 3:]


def test_a_spec_with_no_operations_gains_no_ghost_check(named_spec):
    """Every shipped case is in this state and must keep the deck it has.

    With no operations nothing can create a part after the parts block, so the
    check would have nothing to say -- and five frozen model sections would
    each gain two lines to say it.
    """
    text = _emit(named_spec)
    # The helper is DEFINED in every deck -- it lives in the shared preamble
    # with the rest of them, which costs no model section. What must be absent
    # is the pair of emitted lines that call it.
    assert "_asm_parts_before = set(m.parts.keys())" not in text
    assert "_expect_asm_meshed(m, a, _asm_parts_before)" not in text


def test_operations_bring_the_snapshot_and_the_check(asm_spec):
    text = _emit(asm_spec)
    body = text.split("# --- Assembly")[1]
    assert body.index("_asm_parts_before = set(m.parts.keys())") \
        < body.index("_gcall(a, 'RadialInstancePattern'") \
        < body.index("_expect_asm_meshed(m, a, _asm_parts_before)")


def test_the_snapshot_is_taken_before_the_operations_or_it_says_nothing(
        asm_spec):
    """Telling a part an operation created from one the spec declared is only
    possible if something looked first."""
    text = _emit(asm_spec)
    assert "_asm_parts_before = set(m.parts.keys())" in text


def test_the_check_asks_the_instance_and_never_the_part(asm_spec):
    """Measured both ways round: a dependent instance reports its part's count
    (8 = 8, before and after a.regenerate), and an independent one meshed at
    assembly level reports 739 while its part still reads 0. Asking the
    instance is right in both; asking the part is wrong in one.
    """
    body = _helper_body(_emit(asm_spec), "_expect_asm_meshed")
    assert "len(a.instances[n].elements) == 0" in body
    assert "m.parts[" not in body


def test_suppression_is_read_off_the_feature(asm_spec):
    """A cut leaves the instances it consumed in a.instances. Measured:
    excludedFromSimulation was False on all three instances afterwards,
    including the two the cut had suppressed, so it cannot be the test -- it
    would false-refuse every working cut twice over.
    """
    body = _helper_body(_emit(asm_spec), "_expect_asm_meshed")
    assert "a.features[name].isSuppressed()" in body
    assert "excludedFromSimulation" not in body


def test_the_orphan_half_walks_the_model_not_the_assembly(asm_spec):
    """PartFromBooleanMerge never reaches a.instances, so the instance walk
    alone leaves the quieter of the two failures untouched."""
    body = _helper_body(_emit(asm_spec), "_expect_asm_meshed")
    assert "sorted(m.parts.keys())" in body
    assert "p not in before" in body


@pytest.mark.parametrize("marker", ["ASSEMBLY_UNMESHED", "PART_NOT_INSTANCED"])
def test_every_refusal_is_logged_before_it_is_raised(asm_spec, marker):
    """A raise with no log leaves selectors.log ending mid-build, no reason."""
    text = _emit(asm_spec)
    assert re.search(r"_expect_fail\(\s*'%s" % marker, text), marker


# ---------------------------------------------------------------------------
# The schema, not just the generator
# ---------------------------------------------------------------------------

def _validate(spec: dict):
    from tools.schema_validator import validate_spec
    return validate_spec(spec)


def test_the_schema_accepts_a_generically_meshed_part(spec):
    ok, errors = _validate(spec)
    assert ok, errors


def test_the_schema_accepts_assembly_operations_and_expect(asm_spec):
    asm_spec["assembly"]["expect"]["at"] = [
        {"instance": "Lower-rad-2", "centroid": [0.0, 0.0, 0.0]}]
    ok, errors = _validate(asm_spec)
    assert ok, errors


def test_the_schema_refuses_an_unknown_mesh_measure(spec):
    spec["parts"][0]["expect"]["mesh"] = {"skewness": 0.9}
    ok, _errors = _validate(spec)
    assert not ok


def test_the_schema_refuses_an_unknown_assembly_measure(asm_spec):
    asm_spec["assembly"]["expect"]["mass"] = 1.0
    ok, _errors = _validate(asm_spec)
    assert not ok
