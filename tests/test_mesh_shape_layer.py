"""The mesh layer used to be hex-only, which made complex geometry unreachable.

`elemShape` defaults to HEX, and HEX on a body that has no hexes in it is
ACCEPTED by Abaqus -- it meshes nothing and raises nothing (measured; see
`_mesh_diagnosis` in the generator). So the shape a given element belongs to is
not a convenience, it is the difference between a mesh and an empty part that
looks like a mesh. These are the rules that keep it from being guessed.
"""
from __future__ import annotations

import copy

import pytest

from runner import build_v2, mesh_policy
from runner.build_v2 import SpecError

BASE = {
    "meta": {"model_name": "M", "units": "mm_MPa_t"},
    "material": {"name": "Steel", "E": 210000.0, "nu": 0.3, "density": 7.85e-9},
    "parts": [{
        "name": "Bar",
        "features": [
            {"op": "sketch", "id": "s", "plane": "XY",
             "profile": {"rect": {"corner1": [0.0, 0.0], "corner2": [10.0, 10.0]}}},
            {"op": "extrude", "sketch": "s", "depth": 100.0},
        ],
        "section": {"type": "solid", "material": "Steel"},
        "mesh": {"seed": 5.0, "element": "C3D8R"},
    }],
    "assembly": {"instances": [{"name": "Bar", "part": "Bar",
                                "translate": [0.0, 0.0, 0.0]}]},
    "steps": [{"name": "Pull", "type": "Static",
               "bcs": [{"name": "Root", "region": "Bar:face@z=min",
                        "type": "encastre"}],
               "loads": [{"name": "P", "region": "Bar:face@z=max",
                          "type": "pressure", "value": -1.0}]}],
    "outputs": {"kpis": [{"name": "U_TIP", "type": "field_min",
                          "component": "U2", "location": "whole_model"}]},
}


@pytest.fixture
def spec():
    return copy.deepcopy(BASE)


def _emit(spec):
    return build_v2.generate_script(spec)


def _refuse(spec):
    with pytest.raises(SpecError) as excinfo:
        build_v2.generate_script(spec)
    return str(excinfo.value)


def _mesh_lines(text):
    return [line.strip() for line in text.splitlines()
            if "setMeshControls" in line or "ElemType(elemCode" in line
            or "setElementType" in line]


# --- the tables ------------------------------------------------------------

def test_the_tet_table_is_derived_from_the_hex_table():
    """Not typed out twice. A family added to _COMPANION becomes tet-meshable
    in the same edit, and the two lists cannot drift apart."""
    for wedge, tet in mesh_policy._COMPANION.values():
        assert tet in mesh_policy._TET_PRIMARY
        assert wedge in mesh_policy._WEDGE_PRIMARY


def test_the_modified_tet_is_recorded_even_though_it_is_nobody_s_companion():
    """C3D10M is what Abaqus asks for under contact, and it is never the
    automatic companion of a linear family."""
    assert "C3D10M" in mesh_policy._TET_PRIMARY
    assert "C3D10M" not in [tet for _, tet in mesh_policy._COMPANION.values()]


def test_every_shape_has_at_least_one_technique():
    for shape, techniques in mesh_policy._SHAPE_TECHNIQUES.items():
        assert techniques, shape
        for technique in techniques:
            assert technique in mesh_policy._TECHNIQUE_CONSTANT


# --- shape resolution ------------------------------------------------------

def test_a_hex_brings_its_wedge_and_tet():
    shape, codes = mesh_policy._mesh_shape("Bar", "C3D8R")
    assert shape == "HEX"
    assert codes == ("C3D8R", "C3D6", "C3D4")


@pytest.mark.parametrize("element", ["C3D10", "C3D4", "DC3D10", "C3D10M"])
def test_a_tet_stands_alone(element):
    shape, codes = mesh_policy._mesh_shape("Bar", element)
    assert shape == "TET"
    assert codes == (element,)


def test_a_wedge_stands_alone():
    shape, codes = mesh_policy._mesh_shape("Bar", "C3D6")
    assert shape == "WEDGE"
    assert codes == ("C3D6",)


def test_an_unrecorded_element_is_refused_by_name(spec):
    spec["parts"][0]["mesh"]["element"] = "C3D8QQ"
    message = _refuse(spec)
    assert "'Bar'" in message and "C3D8QQ" in message
    # It has to say what IS recorded, in all three shapes, or the refusal is
    # not actionable.
    assert "C3D8R" in message and "C3D10" in message and "C3D6" in message


# --- what reaches the deck -------------------------------------------------

def test_a_tet_part_writes_elem_shape_tet(spec):
    spec["parts"][0]["mesh"]["element"] = "C3D10"
    lines = _mesh_lines(_emit(spec))
    assert any("elemShape=TET" in line for line in lines)
    assert not any("elemShape=HEX" in line for line in lines)


def test_a_tet_part_writes_the_control_even_with_no_technique_asked(spec):
    """The one case that must never be skipped: with no setMeshControls call
    the shape stays at its HEX default, and a HEX control on a body with no
    hexes meshes nothing and raises nothing."""
    spec["parts"][0]["mesh"]["element"] = "C3D10"
    spec["parts"][0]["mesh"].pop("technique", None)
    assert "p.setMeshControls(regions=p.cells, elemShape=TET, technique=FREE)" \
        in _emit(spec)


def test_a_hex_part_with_no_technique_still_writes_no_control(spec):
    """The pre-existing decks in this repo depend on it: adding a control here
    would change four frozen model sections.

    Scoped to the model section -- the deck minus the shared preamble -- for
    the same reason the frozen baselines are: the preamble carries the helper
    definitions, and one of their refusal messages names setMeshControls as
    the way to mesh a part an assembly operation created.
    """
    spec["parts"][0]["mesh"].pop("technique", None)
    text = _emit(spec)
    assert "setMeshControls" not in text[text.index("# --- Materials"):]


def test_a_single_element_tuple_keeps_its_comma(spec):
    """Without it the kernel says 'elemTypes; found ElemType, expecting tuple'
    -- loud, but only reachable once a single-shape element exists."""
    spec["parts"][0]["mesh"]["element"] = "C3D10"
    text = _emit(spec)
    assert "mesh.ElemType(elemCode=C3D10, elemLibrary=STANDARD),))" in text


def test_a_hex_triple_does_not_gain_a_trailing_comma(spec):
    text = _emit(spec)
    assert "mesh.ElemType(elemCode=C3D4, elemLibrary=STANDARD)))" in text


# --- technique compatibility ------------------------------------------------

@pytest.mark.parametrize("technique", ["structured", "sweep"])
def test_a_tet_under_a_hex_technique_is_refused_here(spec, technique):
    """Abaqus refuses it too, but from inside the kernel, where the message
    names neither the part nor the spec key."""
    spec["parts"][0]["mesh"]["element"] = "C3D10"
    spec["parts"][0]["mesh"]["technique"] = technique
    message = _refuse(spec)
    assert "'Bar'" in message
    assert "tet" in message and technique in message
    assert "'free'" in message


def test_a_hex_keeps_every_technique_it_had(spec):
    for technique, constant in (("structured", "STRUCTURED"),
                                ("sweep", "SWEEP"), ("free", "FREE")):
        spec["parts"][0]["mesh"]["technique"] = technique
        assert "elemShape=HEX, technique=%s" % constant in _emit(spec)


# --- the part that is never meshed at all -----------------------------------
#
# `mesh:` is an optional key and the generator branched `if mesh_spec: ...
# elif expect.mesh: ...` with no else. A part in neither state got no
# seedPart, no generateMesh and no check. Measured on Abaqus 2021 -- a
# two-part deck with one part left unmeshed wrote this, and the job COMPLETED:
#
#     133| *Part, name=Unmeshed
#     134| *End Part
#     ...
#     144| *Instance, name=Unmeshed, part=Unmeshed
#     146| *End Instance
#
# An empty part with a live instance, contributing no mass and no stiffness,
# with nothing anywhere saying so. Of every silent failure found in this layer
# it has the lowest trigger: leave out one optional block.


def test_a_part_with_neither_a_mesh_block_nor_an_expect_is_refused(spec):
    spec["parts"][0].pop("mesh", None)
    message = _refuse(spec)
    assert "'Bar'" in message
    # Actionable: it has to say both ways out, or the reader deletes the part.
    assert "mesh" in message and "expect" in message


def test_a_part_meshed_by_a_generic_call_is_accepted_on_its_expect(spec):
    """The shell bypass is in exactly this state and must keep working: no
    `mesh:` block, the mesh made by dispatched calls, `expect.mesh` stating
    what it should come to."""
    part = spec["parts"][0]
    part.pop("mesh", None)
    part["features"] += [
        {"call": "seedPart", "size": 5.0},
        {"call": "generateMesh"},
    ]
    part["expect"] = {"cells": 1, "mesh": {"elements": ">=8"}}
    assert "_mesh_check(" in _emit(spec)


def test_a_generic_mesh_call_without_an_expect_is_still_refused(spec):
    """Pre-existing rule, pinned here because the new one sits next to it and
    must not swallow it: a generic call that meshes needs expect.mesh."""
    part = spec["parts"][0]
    part.pop("mesh", None)
    part["features"] += [{"call": "generateMesh"}]
    part["expect"] = {"cells": 1}
    assert "expect.mesh" in _refuse(spec)


def test_a_wedge_under_free_is_refused_because_it_was_never_measured(spec):
    """Not a claim that Abaqus rejects it -- a statement that this repository
    has never proved it on a solver, and an unproved combination is refused
    rather than shipped as supported."""
    spec["parts"][0]["mesh"]["element"] = "C3D6"
    spec["parts"][0]["mesh"]["technique"] = "free"
    assert "'sweep'" in _refuse(spec)
