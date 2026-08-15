"""A mapping argument may name one form; the keys beside it must mean something.

`_arg_mapping` has always asserted that exactly one of the eleven forms is
present. What it did not check is the OTHER keys. Only three forms
(select/surface/set) carried a hand-written sibling check, so the remaining
eight accepted anything and dropped it without a word.

The reachable trap is `{ref: x, attr: y}`. `target: {ref:, attr:}` is a
documented, supported form -- it calls a method ON the object a previous call
bound -- so writing the same pair in an argument position is the obvious
thing to try. It compiled to the bare `_RESULTS['x']` and the `attr` vanished,
which is a different object than the one the spec named.

The three hand-written checks are replaced by one table so a form added later
cannot quietly arrive without a rule.
"""
from __future__ import annotations

import pytest

from runner import arg_forms
from runner.build_v2 import SpecError


def _compile(value, *, scope="part", results=None, sketches=None,
             surfaces=None, sets=None):
    return arg_forms._arg_mapping(
        "op 1", "region", value,
        sketches if sketches is not None else {},
        results if results is not None else set(),
        scope=scope, surfaces=surfaces, sets=sets)


def _refuse(value, **kwargs):
    with pytest.raises(SpecError) as excinfo:
        _compile(value, **kwargs)
    return str(excinfo.value)


# --- the table covers every form -------------------------------------------

def test_every_arg_form_has_a_sibling_rule():
    """`new` is the deliberate exception: its siblings ARE the constructor's
    keyword arguments. Every other form must be in the table, or a form added
    later silently inherits accept-anything."""
    covered = set(arg_forms._ARG_SIBLINGS) | {"new"}
    assert covered == set(arg_forms._ARG_FORMS)


def test_the_new_form_still_takes_its_constructor_arguments():
    text = _compile({"new": "mesh.ElemType", "elemCode": "C3D8R",
                     "elemLibrary": "STANDARD"})
    assert "ElemType" in text and "C3D8R" in text


# --- the eight that used to accept anything ---------------------------------

def test_ref_with_attr_is_refused_and_points_at_target():
    """The one a user actually reaches: `target: {ref:, attr:}` is supported,
    so the same pair in an argument position looks legal. It used to compile
    to the bare object."""
    message = _refuse({"ref": "seat", "attr": "cells"}, results={"seat"})
    assert "attr" in message
    assert "target" in message, (
        "the refusal must say where `attr` IS legal, or it reads as "
        "'attributes are not supported'")


def test_datum_with_a_junk_sibling_is_refused():
    message = _refuse({"datum": "mid", "index": 3}, results={"mid"},
                      scope="assembly")
    assert "index" in message and "datum" in message


def test_literal_with_a_junk_sibling_is_refused():
    assert "unit" in _refuse({"literal": "RIM", "unit": "mm"})


def test_sketch_with_a_junk_sibling_is_refused():
    message = _refuse({"sketch": "outline", "flip": True},
                      sketches={"outline": object()})
    assert "flip" in message


def test_instance_with_a_junk_sibling_is_refused():
    message = _refuse({"instance": "Bolt", "attr": "cells"}, scope="assembly")
    assert "attr" in message


def test_vertex_with_a_junk_sibling_is_refused():
    message = _refuse(
        {"vertex": {"instance": "Bar", "at": [0.0, 0.0, 0.0]}, "expect": 2},
        scope="assembly")
    assert "expect" in message


def test_wire_at_with_a_junk_sibling_is_refused():
    message = _refuse(
        {"wire_at": [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]], "expect": 1},
        scope="assembly")
    assert "expect" in message


# --- the three that already checked must keep checking ----------------------

def test_select_still_refuses_a_junk_sibling():
    message = _refuse({"select": "faces@all", "pick": 2})
    assert "pick" in message and "select" in message


def test_select_still_accepts_expect():
    text = _compile({"select": "faces@all", "expect": "=1"})
    assert "_sel_resolve" in text


def test_surface_still_refuses_a_junk_sibling():
    message = _refuse({"surface": "Bar:face@z=max", "side": 1},
                      scope="assembly", surfaces=[])
    assert "side" in message


def test_set_still_refuses_a_junk_sibling():
    message = _refuse({"set": "Bar:face@z=max", "kind": "node"},
                      scope="assembly", sets=[])
    assert "kind" in message


# --- the pre-existing one-form rule is untouched ----------------------------

def test_two_forms_at_once_are_still_refused():
    message = _refuse({"select": "faces@all", "literal": "X"})
    assert "exactly one" in message
