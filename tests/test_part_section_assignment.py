"""A part could not be given two materials, and trying looked like it worked.

`_one_part` appended a whole-part section assignment unconditionally, AFTER
the user's own features. So a spec that partitioned a bar and assigned an
aluminium section to one half compiled to:

    ... user's SectionAssignment(region=LEFT, sectionName=SEC_ALU)   # idx 61182
    p.Set(name='ALL', cells=p.cells)                                 # idx 62524
    p.SectionAssignment(region=p.sets['ALL'], sectionName=SEC_Bar)   # idx 62633

A later assignment over the whole part wins, so the written .inp carried one
line -- `*Solid Section, elset=ALL, material=Steel`. The aluminium elset was
there, the aluminium material was there, and nothing referenced either. The
job ran, the KPIs had numbers, and every one of them was for a steel bar.

The fallback is still emitted when the spec does not assign anything itself,
because that is the case every shipped spec is in and it must stay
byte-identical. What changed is that it steps aside when the spec has taken
responsibility -- and then a coverage check runs instead, because "the user
assigned some sections" is not the same as "every cell has one", and an
unassigned cell is an Abaqus FATAL a long way downstream.
"""
from __future__ import annotations

import copy

import pytest

from runner import build_v2

BASE = {
    "meta": {"model_name": "M", "units": "mm_MPa_t", "abaqus_release": "2021"},
    "material": {"name": "Steel", "E": 210000.0, "nu": 0.3, "density": 7.85e-9},
    "materials": [{"name": "Alu", "E": 70000.0, "nu": 0.33, "density": 2.7e-9}],
    "model_setup": [
        {"call": "HomogeneousSolidSection", "name": {"literal": "SEC_ALU"},
         "material": {"literal": "Alu"}, "thickness": None},
    ],
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
                          "component": "U3", "location": "whole_model"}]},
}

# The partition-then-assign sequence the generic layer already supports:
# name every cell, narrow by bounding box, name the narrowed set, assign to it.
_SPLIT = [
    {"call": "DatumPlaneByPrincipalPlane", "principalPlane": "XYPLANE",
     "offset": 50.0, "as": "mid"},
    {"call": "PartitionCellByDatumPlane", "datumPlane": {"datum": "mid"},
     "cells": {"select": "cells@all"}},
    {"call": "Set", "name": {"literal": "ALLC"},
     "cells": {"select": "cells@all"}, "as": "allc"},
    {"call": "getByBoundingBox", "target": {"ref": "allc", "attr": "cells"},
     "xMin": -1.0, "xMax": 11.0, "yMin": -1.0, "yMax": 11.0,
     "zMin": -1.0, "zMax": 51.0, "as": "lowcell"},
    {"call": "Set", "name": {"literal": "LOWHALF"},
     "cells": {"ref": "lowcell"}, "as": "lowset"},
    {"call": "SectionAssignment", "region": {"ref": "lowset"},
     "sectionName": {"literal": "SEC_ALU"}},
]


@pytest.fixture
def spec():
    return copy.deepcopy(BASE)


@pytest.fixture
def bimetal(spec):
    spec["parts"][0]["features"] += copy.deepcopy(_SPLIT)
    spec["parts"][0]["expect"] = {"cells": 2}
    return spec


def _emit(spec):
    return build_v2.generate_script(spec)


# --- the fallback steps aside -----------------------------------------------

def test_a_spec_that_assigns_its_own_section_keeps_it(bimetal):
    text = _emit(bimetal)
    assert "SEC_ALU" in text
    assert "p.SectionAssignment(region=p.sets['ALL']" not in text, (
        "the whole-part fallback ran after the spec's own assignment and "
        "overrode it; the bar came out entirely steel")


def test_the_named_section_is_still_defined_for_the_spec_to_use(bimetal):
    """`section:` is required by the schema, so SEC_<part> must still exist --
    it is the natural thing to assign to the OTHER half."""
    assert "m.HomogeneousSolidSection(name='SEC_Bar'" in _emit(bimetal)


def test_the_named_section_is_defined_before_the_features_that_use_it(bimetal):
    """Measured on Abaqus 2021: with the definition left where it was, a
    feature saying `sectionName: SEC_Bar` died with 'The section "SEC_Bar"
    does not exist in the model.' -- so "we still define it for you" was an
    empty promise."""
    text = _emit(bimetal)
    assert (text.index("m.HomogeneousSolidSection(name='SEC_Bar'")
            < text.index("PartitionCellByDatumPlane"))


def test_the_all_set_is_not_created_when_the_spec_assigns_its_own(bimetal):
    """An 'ALL' set that nothing references is a loaded gun: the next edit
    that adds a fallback assignment silently re-covers the whole part."""
    assert "p.Set(name='ALL', cells=p.cells)" not in _emit(bimetal)


# --- and stays put otherwise ------------------------------------------------

def test_a_spec_that_assigns_nothing_still_gets_the_whole_part_fallback(spec):
    """Every shipped case is in this state and must stay byte-identical."""
    text = _emit(spec)
    assert "p.Set(name='ALL', cells=p.cells)" in text
    assert "p.SectionAssignment(region=p.sets['ALL'], sectionName='SEC_Bar'" in text


def test_the_fallback_path_emits_no_coverage_call(spec):
    """Nothing to check: the fallback covers every cell by construction.

    The helper is DEFINED in every deck -- it lives in the shared preamble
    with the rest of them -- but it must not be called here, or five frozen
    model sections would each gain a line.
    """
    assert "_expect_sections(p, 'Bar')" not in _emit(spec)


# --- partial coverage is caught ---------------------------------------------

def test_the_user_assigned_path_emits_a_coverage_check(bimetal):
    """Assigning SOME sections is not assigning all of them. Without this an
    uncovered cell reaches the solver, which says '***ERROR: n elements have
    missing property definitions' and stops -- loud, but a whole build and a
    whole submit later, and it names elements rather than the spec."""
    assert "_expect_sections(p, 'Bar')" in _emit(bimetal)


def test_the_coverage_check_runs_after_the_features(bimetal):
    text = _emit(bimetal)
    assert text.index("SEC_ALU'") < text.index("_expect_sections(p, 'Bar')")


def test_the_coverage_helper_is_defined_in_the_deck(bimetal):
    assert "def _expect_sections(" in _emit(bimetal)


# --- the shell bypass must keep working -------------------------------------

def test_a_shell_part_that_assigns_its_own_section_loses_the_empty_all_set(spec):
    """On a shell part p.cells is empty, so the old fallback made an empty Set
    and assigned a solid section to nothing -- a no-op that left no trace in
    the .inp, which is the only reason the shell bypass worked at all. Now it
    is simply not emitted."""
    part = spec["parts"][0]
    part["features"] = [
        {"op": "sketch", "id": "s", "plane": "XY",
         "profile": {"rect": {"corner1": [0.0, 0.0], "corner2": [100.0, 50.0]}}},
        {"call": "BaseShell", "sketch": {"sketch": "s"}},
        {"call": "SectionAssignment", "region": {"select": "faces@all"},
         "sectionName": {"literal": "SHELLSEC"}},
        {"call": "setElementType", "regions": {"select": "faces@all"},
         "elemTypes": [{"new": "mesh.ElemType", "elemCode": "S4R",
                        "elemLibrary": "STANDARD"}]},
        {"call": "seedPart", "size": 10.0},
        {"call": "generateMesh"},
    ]
    part.pop("mesh", None)
    part["expect"] = {"faces": 1, "mesh": {"elements": 50}}
    spec["model_setup"] = [
        {"call": "HomogeneousShellSection", "name": {"literal": "SHELLSEC"},
         "material": {"literal": "Steel"}, "thickness": 2.0},
    ]

    text = _emit(spec)

    assert "p.Set(name='ALL', cells=p.cells)" not in text
    assert "SHELLSEC" in text
