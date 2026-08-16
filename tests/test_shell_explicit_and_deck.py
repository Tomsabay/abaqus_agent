"""Three things a v2 spec could not say, each of which v1 could.

They were found by porting the seven frozen v1 cases to v2, which is what
porting is for: the dialect looked complete until something had to be written in
it. Every measurement quoted here was taken while doing that.

  1. The element LIBRARY was the constant "STANDARD" -- so an explicit step got
     Standard-library elements and no section controls, and the reaction force
     came out 5.3% off with the job reporting COMPLETED.
  2. A SHELL section could not be written at all, so a plate was unbuildable.
  3. A finished .inp could only be handed over through v1's
     `geometry: {type: custom_inp}`, which dragged `analysis` and `bc_load`
     along as required siblings that nothing read.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from core.element_risk import spec_hourglass_findings
from runner import build_v2
from runner.build_model import _is_deck
from runner.build_v2 import SpecError, _element_library
from tools.schema_validator import validate_spec

ROOT = Path(__file__).resolve().parents[1]

SOLID = {
    "meta": {"abaqus_release": "2021", "model_name": "M", "units": "mm_MPa_t"},
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
    "steps": [{"call": "StaticStep", "name": {"literal": "Step-1"},
               "previous": {"literal": "Initial"}}],
    "outputs": {"kpis": [{"name": "U", "type": "field_min",
                          "component": "U2", "location": "whole_model"}]},
}

EXPLICIT_STEP = {"call": "ExplicitDynamicsStep", "name": {"literal": "Step-1"},
                 "previous": {"literal": "Initial"}, "timePeriod": 1.0e-4}


@pytest.fixture
def solid():
    return copy.deepcopy(SOLID)


def _elem_lines(text):
    return [line.strip() for line in text.splitlines() if "ElemType(elemCode" in line]


# --- 1. the element library ------------------------------------------------

def test_a_standard_step_still_gets_standard_elements(solid):
    assert _element_library(solid) == "STANDARD"
    for line in _elem_lines(build_v2.generate_script(solid)):
        assert "elemLibrary=STANDARD" in line


def test_an_explicit_step_gets_explicit_elements(solid):
    """The constant this replaces was a silent 5.3%.

    Measured on Abaqus 2021 with the deck ported from cases/explicit_impact: the
    STANDARD-library build wrote `*Element, type=C3D8R` -- the same line as the
    frozen v1 deck -- and NO `*Section Controls`, because hourglassControl is
    only reachable on the EXPLICIT library. The job completed with no error and
    reported 33501 N of reaction against the frozen 31817 N, on a case whose own
    tolerance is 5%.
    """
    solid["steps"] = [copy.deepcopy(EXPLICIT_STEP)]
    assert _element_library(solid) == "EXPLICIT"
    lines = _elem_lines(build_v2.generate_script(solid))
    assert lines
    for line in lines:
        assert "elemLibrary=EXPLICIT" in line


def test_the_explicit_step_list_is_looked_up_not_pattern_matched(solid):
    """TempDisplacementDynamicsStep is Explicit and does not say so in its name."""
    solid["steps"] = [{"call": "TempDisplacementDynamicsStep",
                       "name": {"literal": "Step-1"},
                       "previous": {"literal": "Initial"}, "timePeriod": 1.0}]
    assert _element_library(solid) == "EXPLICIT"


# --- hourglass control -----------------------------------------------------

def test_hourglass_control_goes_only_on_the_element_the_spec_named(solid):
    solid["steps"] = [copy.deepcopy(EXPLICIT_STEP)]
    solid["parts"][0]["mesh"]["hourglass_control"] = "ENHANCED"
    lines = _elem_lines(build_v2.generate_script(solid))
    # C3D8R, then the wedge and the tet a free mesh falls back on. Those two are
    # fully integrated; asking Abaqus to control hourglassing they cannot have
    # is at best noise and at worst a refusal from inside the kernel.
    assert "hourglassControl=ENHANCED" in lines[0]
    for line in lines[1:]:
        assert "hourglassControl" not in line


def test_hourglass_control_is_absent_unless_asked_for(solid):
    assert all("hourglassControl" not in line
               for line in _elem_lines(build_v2.generate_script(solid)))


def test_an_explicit_reduced_element_with_hourglass_control_is_not_warned_about(solid):
    """The one form core/element_risk.FIX actually recommends."""
    solid["steps"] = [copy.deepcopy(EXPLICIT_STEP)]
    assert spec_hourglass_findings(solid), "C3D8R alone must still be flagged"
    solid["parts"][0]["mesh"]["hourglass_control"] = "ENHANCED"
    assert spec_hourglass_findings(solid) == []


def test_hourglass_control_does_not_excuse_a_reduced_element_under_standard(solid):
    """The 92x measurement is a STATIC bending case.

    Nothing here has measured ENHANCED rescuing one, so the warning stands.
    Waving it through on the strength of a keyword would be exactly the
    unmeasured claim this module exists to avoid.
    """
    solid["parts"][0]["mesh"]["hourglass_control"] = "ENHANCED"
    assert spec_hourglass_findings(solid)


# --- 2. shells -------------------------------------------------------------

def _shell(spec):
    part = spec["parts"][0]
    part["features"] = [
        {"op": "sketch", "id": "s", "plane": "XY",
         "profile": {"rect": {"corner1": [0.0, 0.0], "corner2": [2000.0, 2000.0]}}},
        {"call": "BaseShell", "sketch": {"sketch": "s"}},
    ]
    part["section"] = {"type": "shell", "material": "Steel", "thickness": 25.0}
    part["mesh"] = {"seed": 100.0, "element": "S4R"}
    part["expect"] = {"area": 4000000.0, "faces": 1}
    return spec


def test_a_shell_part_acts_on_faces_not_cells(solid):
    """`Set(cells=p.cells)` on a body with no cells builds a set of ZERO cells
    and assigns a section to nothing, without raising. That is why the body
    attribute is decided once rather than assumed to follow dimensionality."""
    text = build_v2.generate_script(_shell(solid))
    assert "p.Set(name='ALL', faces=p.faces)" in text
    assert "p.Set(name='ALL', cells=p.cells)" not in text
    assert "p.setElementType(regions=(p.faces,)" in text


def test_a_shell_section_is_a_shell_section(solid):
    text = build_v2.generate_script(_shell(solid))
    assert "m.HomogeneousShellSection(" in text
    assert "thickness=25.0" in text
    assert "integrationRule=SIMPSON, numIntPts=5)" in text
    assert "HomogeneousSolidSection" not in text.split("# --- Parts")[1]


def test_a_shell_may_state_its_own_integration_points(solid):
    spec = _shell(solid)
    spec["parts"][0]["section"]["integration_points"] = 9
    assert "numIntPts=9)" in build_v2.generate_script(spec)


def test_a_shell_without_a_thickness_is_refused(solid):
    spec = _shell(solid)
    del spec["parts"][0]["section"]["thickness"]
    with pytest.raises(SpecError) as excinfo:
        build_v2.generate_script(spec)
    assert "thickness" in str(excinfo.value)


def test_a_shell_meshed_with_a_solid_element_is_refused(solid):
    """A shell has faces and no cells; a hex element would mesh nothing quietly."""
    spec = _shell(solid)
    spec["parts"][0]["mesh"]["element"] = "C3D8R"
    with pytest.raises(SpecError) as excinfo:
        build_v2.generate_script(spec)
    assert "shell" in str(excinfo.value)


def test_an_axisymmetric_shell_is_refused_rather_than_built_wrong(solid):
    spec = _shell(solid)
    spec["parts"][0]["dimensionality"] = "AXISYMMETRIC"
    with pytest.raises(SpecError) as excinfo:
        build_v2.generate_script(spec)
    assert "SAX1" in str(excinfo.value)


def test_a_solid_three_d_section_still_refuses_a_thickness(solid):
    solid["parts"][0]["section"]["thickness"] = 5.0
    with pytest.raises(SpecError):
        build_v2.generate_script(solid)


def test_the_shell_schema_accepts_the_ported_plate():
    ok, errors = validate_spec(_shell(copy.deepcopy(SOLID)))
    assert ok, errors


# --- 3. a deck handed over as it is ----------------------------------------

DECK = {
    "meta": {"abaqus_release": "2021", "model_name": "M", "units": "mm_MPa_t"},
    "material": {"name": "Steel", "E": 210000.0, "nu": 0.3},
    "deck": {"file": "frame.inp"},
    "outputs": {"kpis": [{"name": "PEEQ_MAX", "type": "field_max",
                          "field_variable": "PEEQ", "location": "whole_model"}]},
}


def test_a_deck_spec_needs_no_parts_no_steps_and_no_bc_load():
    ok, errors = validate_spec(copy.deepcopy(DECK))
    assert ok, errors


@pytest.mark.parametrize("key, value", [
    ("parts", []),
    ("assembly", {"instances": []}),
    ("steps", []),
    ("geometry", {"type": "cantilever_block", "L": 1.0, "W": 1.0, "H": 1.0}),
    ("bc_load", {"fixed_face": "z=0", "load_type": "pressure", "value": -1.0}),
])
def test_a_deck_that_also_describes_the_model_is_refused(key, value):
    """Not ignored. The deck already carries its own steps and loads, so a spec
    that states them too gives its reader a description that need not match what
    ran -- and a load written in a spec but absent from the deck is exactly the
    kind of disagreement nobody would see."""
    spec = copy.deepcopy(DECK)
    spec[key] = value
    ok, _ = validate_spec(spec)
    assert not ok


def test_a_deck_is_recognised_by_the_deck_key_and_nothing_else():
    """`geometry: {type: custom_inp}` used to route here too. It cannot any
    more: the schema refuses `geometry` outright, so such a spec dies at
    validation and never reaches build_model. Keeping the branch alive would
    have been unreachable code with a test standing guard over it."""
    assert _is_deck(copy.deepcopy(DECK))
    assert not _is_deck({"geometry": {"type": "custom_inp", "inp_path": "f.inp"}})
    assert not _is_deck(copy.deepcopy(SOLID))


def test_the_deck_path_is_hashed_by_content_in_the_schema_text():
    """The one thing about `deck:` a reader has to be told, because getting it
    wrong is silent: the deck path alone is not the cache key."""
    schema = json.loads((ROOT / "schema" / "spec_schema.json").read_text(
        encoding="utf-8"))
    described = schema["properties"]["deck"]["properties"]["file"]["description"]
    assert "CONTENTS are hashed" in described
