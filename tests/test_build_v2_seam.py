"""Seams: the part set that makes one possible, and the check that it did anything.

Two things were measured on Abaqus 2021 (artifacts/probe_seam2) and this file
pins that both of them reached the source.

WHERE IT LIVES. #64 stopped at "assignSeam requires a Set and an assembly
operation cannot build one", on the hope that the part route was different. It
is not -- `p.engineeringFeatures.assignSeam` answers a raw sequence with the
same `regions; found GeomSequence, expecting Set`. What was missing was a PART
set, which is a different object from an assembly set, and `{set:}` refused to
build one because it assumed every set lives on the assembly.

Part scope is also the right scope rather than merely the one that works. Part
features run before `generateMesh`, so the seam is assigned to an unmeshed
part; assigned afterwards it takes effect only when something remeshes.

HOW IT FAILS. One 10 x 10 x 10 block partitioned at mid-height, seed 5:

    no seam                     27 nodes
    seam on the INTERIOR face   36 nodes
    seam on the top face        27 nodes   <- assignSeam returned, no error
    seam on the bottom face     27 nodes   <- assignSeam returned, no error

A face not shared by two cells cannot be separated and Abaqus does not say so.
So a part that assigns a seam must state what it should come to, and the count
is checked in the kernel after the mesh: the seam's set holds both copies, 18
nodes at 9 positions where an unseamed face gives 9 at 9.

Those numbers are produced by scripts/run_seam_check.py against the real
solver. Nothing here runs Abaqus; this file pins the emission and the
refusals, and the gate is what keeps the numbers true.
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from runner import (
    build_v2,  # noqa: E402
    spec_base,
)

SEAM = {"call": "assignSeam", "target": {"attr": "engineeringFeatures"},
        "regions": {"set": "face@z=5", "name": "SEAMFACE", "expect": "=1"}}


def _part(*extra_features, **overrides) -> dict:
    part = {
        "name": "Blk",
        "features": [
            {"op": "sketch", "id": "o", "plane": "XY",
             "profile": {"rect": {"corner1": [0.0, 0.0],
                                  "corner2": [10.0, 10.0]}}},
            {"op": "extrude", "sketch": "o", "depth": 10.0},
            {"call": "DatumPlaneByPrincipalPlane",
             "principalPlane": "XYPLANE", "offset": 5.0, "as": "mid"},
            {"call": "PartitionCellByDatumPlane",
             "datumPlane": {"datum": "mid"},
             "cells": {"select": "cell@all"}},
        ] + list(extra_features),
        "expect": {"volume": 1000.0, "cells": 2},
        "section": {"type": "solid", "material": "Steel"},
        "mesh": {"seed": 5.0, "element": "C3D8I", "technique": "structured"},
    }
    part.update(overrides)
    return part


def _spec(part: dict) -> dict:
    return {
        "meta": {"abaqus_release": "2021", "model_name": "SeamTest",
                 "units": "mm_MPa_t"},
        "material": {"name": "Steel", "E": 210000.0, "nu": 0.3,
                     "density": 7.85e-9},
        "parts": [part],
        "assembly": {"instances": [{"name": "B", "part": "Blk",
                                    "translate": [0.0, 0.0, 0.0]}]},
        "steps": [{"call": "StaticStep", "name": {"literal": "One"},
                   "previous": {"literal": "Initial"}}],
        "conditions": [
            {"call": "EncastreBC", "name": {"literal": "Fix"},
             "createStepName": {"literal": "Initial"},
             "region": {"set": "B:face@z=min", "name": "FIX",
                        "expect": "=1"}}],
        "outputs": {"kpis": [{"name": "U", "type": "field_min",
                              "location": "whole_model", "component": "U2"}]},
    }


def _seamed(duplicated=9, **seam_overrides) -> dict:
    seam = copy.deepcopy(SEAM)
    seam.update(seam_overrides)
    part = _part(seam)
    part["expect"]["seams"] = [{"set": "SEAMFACE", "duplicated": duplicated}]
    return _spec(part)


def _emit(spec: dict) -> str:
    return build_v2.generate_script(spec)


def _refuse(spec: dict) -> str:
    with pytest.raises(spec_base.SpecError) as excinfo:
        build_v2.generate_script(spec)
    return str(excinfo.value)


def _at(text: str, needle: str) -> int:
    """The one emitted line carrying `needle`, or -1.

    Counted rather than found: every needle below also appears in the helper
    prose that ships in the same script, and a test that matched a docstring
    would be checking the order of two comments.
    """
    hits = [i for i, line in enumerate(text.splitlines()) if needle in line]
    assert len(hits) <= 1, "%r appears %d times" % (needle, len(hits))
    return hits[0] if hits else -1


# --- the part set ---------------------------------------------------------

def test_a_set_in_a_part_feature_is_built_on_the_part():
    """`p`, not `a`. The whole reason a seam could not be written before."""
    text = _emit(_seamed())
    line = [ln for ln in text.splitlines() if "'assignSeam'" in ln][0]
    assert "_gset(p, 'SEAMFACE'" in line
    assert "_gset(a," not in line
    assert "'regions': _gset(" in line, (
        "the set has to be the argument itself; one built beside the call and "
        "not handed to it is the silent shape this layer exists to avoid")


def test_the_part_set_resolves_against_the_part():
    text = _emit(_seamed())
    line = [ln for ln in text.splitlines() if "'assignSeam'" in ln][0]
    assert "_sel_resolve(p, 'faces'" in line, (
        "a part set resolves on the part; resolving on the assembly would "
        "pick faces off an instance that does not exist yet")


def test_a_part_set_naming_an_instance_is_refused():
    """Instances do not exist when part features run."""
    message = _refuse(_seamed(regions={"set": "B:face@z=5", "name": "SEAMFACE",
                                       "expect": "=1"}))
    assert "names an instance" in message
    assert "face@z=5" in message, "the message has to show what to write instead"


def test_a_part_set_name_abaqus_cannot_use_is_refused():
    message = _refuse(_seamed(regions={"set": "face@z=5", "name": "seam face!",
                                       "expect": "=1"}))
    assert "cannot use" in message


# --- ordering -------------------------------------------------------------

def test_the_seam_is_assigned_before_the_mesh_and_checked_after():
    """The half of this the ledger flagged as unmeasured.

    Measured: a seam assigned after `generateMesh` leaves 27 nodes until
    something remeshes, and 36 after. Part features run before the mesh, so
    writing a seam there removes the question instead of answering it.
    """
    text = _emit(_seamed())
    seam = _at(text, "'assignSeam'")
    mesh = _at(text, "p.generateMesh()")
    check = _at(text, "_expect_seam(p, '")
    assert -1 not in (seam, mesh, check)
    assert seam < mesh, "a seam after the mesh does nothing until a remesh"
    assert mesh < check, "and nothing to check before there is a mesh"


def test_the_check_carries_the_set_and_the_count():
    text = _emit(_seamed(duplicated=9))
    assert "_expect_seam(p, 'SEAMFACE', 9, \"part 'Blk' feature 5\")" in text


# --- what has to be stated ------------------------------------------------

def test_a_seam_with_no_expect_is_refused():
    """Mandatory, and for the same reason an import must state its volume.

    A hollow shell looks like a solid; a seam that did nothing looks like a
    seam that worked.
    """
    part = _part(copy.deepcopy(SEAM))
    message = _refuse(_spec(part))
    assert "expect.seams" in message
    assert "27 nodes before and 27 after" in message, (
        "the refusal has to carry the measurement, or it reads as a house "
        "rule rather than as a reason")


def test_the_expect_entry_needs_both_keys():
    part = _part(copy.deepcopy(SEAM))
    part["expect"]["seams"] = [{"set": "SEAMFACE"}]
    assert "duplicated" in _refuse(_spec(part))


def test_expect_seams_must_be_a_list():
    part = _part(copy.deepcopy(SEAM))
    part["expect"]["seams"] = {"set": "SEAMFACE", "duplicated": 9}
    assert "must be a list" in _refuse(_spec(part))


def test_a_seam_the_expect_does_not_mention_is_refused():
    part = _part(copy.deepcopy(SEAM))
    part["expect"]["seams"] = [{"set": "OTHER", "duplicated": 9}]
    message = _refuse(_spec(part))
    assert "does not mention it" in message
    assert "OTHER" in message, "and it has to say what WAS stated"


def test_an_expect_naming_a_seam_nobody_assigns_is_refused():
    """The other direction, which is how a renamed set goes unnoticed.

    Found by this test: `_seam_check_lines` returned early when the part had
    no `assignSeam`, so a part stating expect.seams and assigning none built
    clean and checked nothing -- the #46 shape, a gate installed and never
    locked. Both directions refuse now: a seam with no expectation, and an
    expectation with no seam.
    """
    part = _part()
    part["expect"]["seams"] = [{"set": "SEAMFACE", "duplicated": 9}]
    assert "no feature assigns a seam" in _refuse(_spec(part))


def test_a_part_with_neither_a_seam_nor_an_expect_is_untouched():
    """The refusal above must not make an ordinary part harder to write."""
    text = _emit(_spec(_part()))
    assert "_expect_seam(p, '" not in text, (
        "no seam, no check -- the helper still ships, but nothing calls it")


@pytest.mark.parametrize("duplicated", [0, -1, "9", 9.0, True, None])
def test_duplicated_must_be_a_positive_whole_count(duplicated):
    """Zero is the failure itself, so it cannot be a legal expectation.

    A seam that duplicates no positions is exactly the silent no-op measured
    on the exterior face, and `duplicated: 0` would be a spec asking for it.
    """
    part = _part(copy.deepcopy(SEAM))
    part["expect"]["seams"] = [{"set": "SEAMFACE", "duplicated": duplicated}]
    message = _refuse(_spec(part))
    assert "duplicated" in message


# --- the forms that cannot reach it ---------------------------------------

def test_a_raw_sequence_is_refused_with_abaqus_own_complaint():
    """`{select:}` produces a GeomSequence and assignSeam will not take one."""
    message = _refuse(_seamed(regions={"select": "face@z=5", "expect": "=1"}))
    assert "expecting Set" in message
    assert "regions: {set: ...}" in message, "and it has to say what to write"


def test_a_seam_set_needs_an_explicit_name():
    """A derived name would make the spec and the check agree by accident."""
    message = _refuse(_seamed(regions={"set": "face@z=5", "expect": "=1"}))
    assert "explicit `name:`" in message


def test_an_assembly_operation_seam_points_at_the_part():
    """The old dead end, now with an exit.

    A refusal with no next step is most of a bug report and none of a fix, so
    this pins that the message routes rather than just declines.
    """
    spec = _spec(_part())
    spec["assembly"]["operations"] = [
        {"call": "assignSeam", "target": {"attr": "engineeringFeatures"},
         "regions": {"set": "B:face@z=5", "name": "SEAMFACE", "expect": "=1"}}]
    message = _refuse(spec)
    assert "PART" in message
    assert "generateMesh" in message and "features:" in message, (
        "the route has to say why AND where, or the next person tries the "
        "assembly again with different words")
    assert "cannot build one" not in message, (
        "that was the reason until #76 and it was never true of Abaqus -- an "
        "assembly operation can build a set now. The reason is TIMING, and a "
        "refusal that gives a reason which is no longer the reason sends the "
        "reader after the wrong workaround")


def test_the_assembly_seam_refusal_survives_a_set_registry():
    """The regression #76 nearly shipped, pinned as its own case.

    When assembly operations gained a set registry, the seam refusal -- which
    lived inside `{set:}` handling -- simply stopped firing, and the build went
    through to Abaqus, which accepts a seam assigned after the mesh and changes
    nothing. So the refusal is now taken on `call` before any argument is
    looked at, and this asserts BOTH argument forms are stopped: `{select:}`
    used to be caught only by Abaqus complaining about a tuple, which was
    never a check this repository owned.
    """
    for regions in ({"set": "B:face@z=5", "name": "SEAMFACE", "expect": "=1"},
                    {"select": "B:face@z=5", "expect": "=1"}):
        spec = _spec(_part())
        spec["assembly"]["operations"] = [
            {"call": "assignSeam", "target": {"attr": "engineeringFeatures"},
             "regions": regions}]
        assert "PART" in _refuse(spec)


# --- the kernel side ------------------------------------------------------

def test_the_kernel_helper_ships_with_the_script():
    text = _emit(_seamed())
    assert "def _expect_seam(p, set_name, wanted, label):" in text


@pytest.mark.parametrize("token", ["SEAM_OK", "SEAM_NO_SET", "SEAM_NO_NODES",
                                   "SEAM_NOT_SEPARATED"])
def test_every_seam_outcome_has_a_distinct_token(token):
    """The gate reads these by name, so they are an interface."""
    assert token in _emit(_seamed())


def test_the_failure_token_is_not_a_prefix_of_the_success_token():
    """Learned the hard way in #66: `_line(out, 'SELECTOR')` matched
    `SELECTOR_OK` and a gate spent a run reporting a success line as a
    refusal."""
    for token in ("SEAM_NO_SET", "SEAM_NO_NODES", "SEAM_NOT_SEPARATED"):
        assert not token.startswith("SEAM_OK")
        assert not "SEAM_OK".startswith(token)
