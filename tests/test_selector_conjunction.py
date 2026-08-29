"""`&` and `at=`: naming ONE bolt hole out of a bolt group.

Neither existed, and between them a spec could not describe a bolted joint at
all. Measured on Abaqus 2021 (artifacts/promo/probe_frame_c, a 25-instance
self-centering frame with 16 M20 bolts through 24 real holes):

  * `ColL:faces@r=10.0` matched **4 faces** -- every hole in the flange. That is
    what a bolt group is, so radius alone can never name one of them, and a tie
    written that way welds one bolt to four holes without complaint.
  * A plane cannot narrow it. `getByBoundingBox` means WHOLLY INSIDE, and the
    wall of a 20 dia hole spans 20 along every axis, so `face@y=1400` matches
    the wall at y=1400 zero times at any tolerance below the 50 mm bolt pitch.
  * `ColL:face@r=10&at=92,1400,-25` matched **1 face**, and all 32 bolt ties in
    that model resolved to exactly one face each:
        SELECTOR_OK: ColL:face@r=10&at=92,1400,-25 -> 1 faces
                     radius=10.0 & at=(92.0, 1400.0, -25.0) tol=0.18
        SELECTOR_OK: BCULa:face@r=10&at=100,1400,-25 -> 1 faces
                     radius=10.0 & at=(100.0, 1400.0, -25.0) tol=0.0052
    The two tolerances differ because each is a fraction of its OWN instance's
    span -- 1800 mm of column against 52 mm of bolt.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import selectors  # noqa: E402


def test_an_and_selector_keeps_every_term_in_order():
    sel = selectors.parse("ColL:face@r=10&at=92,1400,-25")
    assert sel.instance == "ColL" and sel.kind == "face"
    assert sel.terms == (("r", "10"), ("at", "92.0,1400.0,-25.0"))
    assert sel.by_radius


def test_a_singular_and_selector_still_expects_exactly_one():
    """The whole point: four holes matched, one wanted."""
    assert selectors.parse("ColL:face@r=10&at=92,1400,-25").expect == "=1"
    assert selectors.parse("ColL:faces@r=10&at=92,1400,-25").expect == ">=1"


def test_axis_and_place_still_read_the_first_term():
    """Callers that predate `&` -- workbench/selection.py, build_v2 -- read
    these, and a one-term selector is still the common case."""
    sel = selectors.parse("Lower:face@z=max")
    assert (sel.axis, sel.place) == ("z", "max")
    assert selectors.parse("face@r=10&at=1,2,3").axis == "r"


def test_one_term_emits_exactly_what_it_emitted_before_and_is_pinned():
    """tests/test_frozen_model_sections.py hashes the emitted model text for the
    five shipped cases. Routing every selector through the new call would move
    all five hashes to say nothing had changed about what they build."""
    sel = selectors.parse("Lower:face@z=max")
    assert selectors.resolve_expression(sel, "a.instances['Lower']") == (
        "_sel_resolve(a.instances['Lower'], 'faces', 'z', 'max', '=1', "
        "'Lower:face@z=max', 0.0001)")


def test_two_terms_emit_the_and_call_with_both():
    sel = selectors.parse("ColL:face@r=10&at=92,1400,-25")
    emitted = selectors.resolve_expression(sel, "a.instances['ColL']")
    assert emitted.startswith("_sel_resolve_and(a.instances['ColL'], 'faces', ")
    assert "('r', '10')" in emitted
    assert "('at', '92.0,1400.0,-25.0')" in emitted
    assert emitted.endswith("'=1', 'ColL:face@r=10&at=92,1400,-25', 0.0001)")


def test_at_takes_three_numbers_and_normalises_them():
    assert selectors.parse("face@at=1,2,3").terms == (("at", "1.0,2.0,3.0"),)
    assert selectors.parse("face@at= -25 , 1.4e3,0 ").terms == (
        ("at", "-25.0,1400.0,0.0"),)


@pytest.mark.parametrize("raw,fragment", [
    ("face@r=10&", "empty term"),
    ("face@&r=10", "empty term"),
    ("face@all&y=max", "ANDs 'all' with something else"),
    ("face@y=1&y=2", "gives 'y' twice"),
    ("face@at=1,2,3&at=4,5,6", "gives 'at' twice"),
    ("face@r=10&q=3", "expected an axis"),
    ("face@at=1,2", "it takes three"),
    ("face@at=1,2,3,4", "it takes three"),
    ("face@at=1,2,max", "is not a term"),
])
def test_combinations_that_could_only_match_nothing_are_refused(raw, fragment):
    """Refused at parse time, not left to the count assertion. The two read
    differently: a count mismatch says the model is not what you thought, and
    this says the phrase could not have matched whatever the model is."""
    with pytest.raises(selectors.SelectorError) as err:
        selectors.parse(raw)
    assert fragment in str(err.value)


def test_a_term_that_cannot_be_read_names_the_term_and_the_selector():
    with pytest.raises(selectors.SelectorError) as err:
        selectors.parse("face@r=10&nonsense")
    message = str(err.value)
    assert "cannot read the selector 'face@r=10&nonsense'" in message
    assert "'nonsense' is not a term" in message
    assert "at=0,0,0" in message, "the new form belongs in the list of forms"


def test_the_runtime_intersects_by_index_not_by_object():
    """Abaqus hands back a NEW wrapper each time a sequence is sliced, so
    `set(seq_a) & set(seq_b)` comes back empty even when the same face is in
    both. The index is the stable name."""
    body = selectors.RUNTIME.split("def _sel_resolve_and", 1)[1]
    body = body.split("\ndef ", 1)[0]
    assert "item.index" in body
    assert "keep & ids" in body


def test_at_uses_the_bounding_box_midpoint_and_not_getcentroid():
    """getCentroid() is an estimate off the facetted display geometry, and it is
    the wrong quantity anyway -- the centroid of a half-cylinder is not on its
    axis, and the axis is where a bolt hole is.

    The docstring is dropped before looking, because it names getCentroid in
    order to say why the code does not call it.
    """
    body = selectors.RUNTIME.split("def _sel_centred_at", 1)[1]
    body = body.split("\ndef ", 1)[0].split('"""')[2]
    assert "getCentroid" not in body
    assert "getBoundingBox" in body
    assert "seq[i:i + 1]" in body, "a slice carries getBoundingBox; an item may not"


def test_the_runtime_is_python_2_7_for_the_abaqus_kernel():
    """No `->` in this list: it is not annotation-only, and the runtime writes
    'SELECTOR_OK: %s -> %d' into the log a spec author reads."""
    for banned in ("f'", 'f"', ":=", "pathlib", "nonlocal "):
        assert banned not in selectors.RUNTIME, banned
