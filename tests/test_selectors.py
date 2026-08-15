"""The selector layer, and the count assertion that makes it worth having.

The failure mode this guards is not a crash. Abaqus geometry lookup is silent
when it is wrong: ``faces.getByBoundingBox(...)`` returns an empty sequence for
a plane that does not exist, ``Set(name='FIX', faces=<empty>)`` is accepted, the
job runs, and the solver reports COMPLETED with the boundary condition applied
to nothing. So the interesting tests here are the rejections.

Hermetic. The real-solver half is in scripts/run_assembly_check.py; the
mismatch path has been exercised against Abaqus 2021 and aborts the build with
no .inp written.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import selectors  # noqa: E402

# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("raw,instance,kind,axis,place", [
    ("Lower:face@z=max", "Lower", "face", "z", "max"),
    ("Upper:faces@y=min", "Upper", "face", "y", "min"),
    ("Plate:edges@x=12.5", "Plate", "edge", "x", "12.5"),
    ("Bolt-1:cells@all", "Bolt-1", "cell", None, None),
    ("face@z=0", None, "face", "z", "0"),
    ("  Lower : face @ z = max  ", "Lower", "face", "z", "max"),
])
def test_valid_selectors_parse(raw, instance, kind, axis, place):
    sel = selectors.parse(raw)
    assert (sel.instance, sel.kind, sel.axis, sel.place) == (instance, kind, axis, place)


def test_singular_and_plural_are_not_cosmetic():
    """`face` means one face and says so without an explicit expect.

    The count assertion only protects selectors that carry one, so the default
    has to be the strict reading whenever the author wrote the singular.
    """
    assert selectors.parse("Lower:face@z=max").expect == "=1"
    assert selectors.parse("Lower:faces@z=max").expect == ">=1"
    # `@all` is inherently a set, so it stays permissive even spelled singular.
    assert selectors.parse("Lower:cell@all").expect == ">=1"


def test_an_explicit_expect_always_wins():
    assert selectors.parse("Lower:face@z=max", expect=3).expect == "=3"
    assert selectors.parse("Lower:faces@r=5" .replace("r=5", "z=0"),
                           expect=">=4").expect == ">=4"
    assert selectors.parse("Lower:faces@z=0", expect="<=2").expect == "<=2"


@pytest.mark.parametrize("bad", [
    "", "   ", None, 42,
    "Lower:face",            # no query
    "Lower:face@",           # empty query
    "Lower:blob@z=max",      # unknown kind
    "Lower:face@w=max",      # no such axis
    "Lower:face@z=middle",   # not a number, min or max
    "Lower:face@z",          # no value
    "1Bad:face@z=max",       # not an identifier
])
def test_unusable_selectors_are_rejected(bad):
    with pytest.raises(selectors.SelectorError):
        selectors.parse(bad)


def test_the_rejection_message_shows_the_selector_it_could_not_read():
    """The user sees this string; it has to name the thing that is wrong."""
    with pytest.raises(selectors.SelectorError) as caught:
        selectors.parse("Lower:face@w=max")
    message = str(caught.value)
    assert "Lower:face@w=max" in message
    assert "x, y, z" in message and "r" in message


# ---------------------------------------------------------------------------
# Radius
#
# A hole's wall cannot be named by a plane: its bounding box is the whole plate
# in x and y. Measured on Abaqus 2021, face.getRadius() returns the radius of a
# cylindrical face and raises on a planar one, so a radius filter is exact --
# whereas getByBoundingCylinder was measured to return every face in the part
# once the radius is large enough, which is containment, not identity.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("raw", ["Plate:face@r=6", "Plate:face@radius=6"])
def test_r_and_radius_are_the_same_word(raw):
    sel = selectors.parse(raw)
    assert sel.axis == "r" and sel.place == "6"
    assert sel.by_radius


def test_a_radius_selector_keeps_the_singular_plural_default():
    assert selectors.parse("Plate:face@r=6").expect == "=1"
    assert selectors.parse("Plate:faces@r=6").expect == ">=1"


def test_edges_can_be_named_by_radius_too():
    """The hole rim is what a local mesh seed targets."""
    sel = selectors.parse("edges@r=6")
    assert sel.kind == "edge" and sel.attribute == "edges" and sel.by_radius


@pytest.mark.parametrize("bad,fragment", [
    ("Plate:cells@r=6", "faces and edges"),      # a cell has no radius
    ("Plate:vertex@r=6", "faces and edges"),
    ("Plate:face@r=max", "has to be the number"),
    ("Plate:face@r=min", "has to be the number"),
    ("Plate:face@r=0", "positive"),
    ("Plate:face@r=-6", "positive"),
])
def test_radius_selectors_that_could_only_match_nothing_are_rejected(bad, fragment):
    """Each of these parses cleanly and would emit a filter matching zero.

    That is not the same as an empty result at runtime: the count assertion
    would fire and blame the model, when the phrase itself was unanswerable.
    """
    with pytest.raises(selectors.SelectorError) as caught:
        selectors.parse(bad)
    assert fragment in str(caught.value), str(caught.value)


def test_a_plane_selector_is_still_a_plane_selector():
    """`r` must not leak into the axis path."""
    sel = selectors.parse("Plate:face@z=max")
    assert not sel.by_radius
    assert selectors.parse("Plate:face@x=6").axis == "x"


@pytest.mark.parametrize("bad", ["", "two", ">1.5", "=", True, ">>2"])
def test_unusable_expects_are_rejected(bad):
    with pytest.raises(selectors.SelectorError):
        selectors.normalise_expect(bad, default_plural=False)


def test_expect_true_is_rejected_rather_than_read_as_one():
    """bool is an int in Python; `expect: true` would silently mean `expect: 1`."""
    with pytest.raises(selectors.SelectorError):
        selectors.normalise_expect(True, default_plural=False)


# ---------------------------------------------------------------------------
# The count check, on both sides of the process boundary
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("count,expect,ok", [
    (1, "=1", True), (0, "=1", False), (2, "=1", False),
    (0, ">=1", False), (1, ">=1", True), (7, ">=1", True),
    (2, "<=2", True), (3, "<=2", False),
    (3, ">2", True), (2, ">2", False),
    (1, "<2", True), (2, "<2", False),
])
def test_satisfies(count, expect, ok):
    assert selectors.satisfies(count, expect) is ok


def _kernel_expect_ok():
    """Pull _sel_expect_ok out of the generated runtime and make it callable.

    The runtime is a string because it executes in the Abaqus Python 2.7
    kernel, which means its copy of the rule is never exercised by this test
    suite. Extracting and running it here is the only way the two
    implementations can be held to the same table above.
    """
    source = selectors.RUNTIME
    start = source.index("def _sel_expect_ok")
    end = source.index("def _sel_resolve")
    namespace: dict = {}
    exec(compile(source[start:end], "<runtime>", "exec"), namespace)
    return namespace["_sel_expect_ok"]


@pytest.mark.parametrize("count,expect,ok", [
    (1, "=1", True), (0, "=1", False), (2, "=1", False),
    (0, ">=1", False), (1, ">=1", True),
    (2, "<=2", True), (3, "<=2", False),
    (3, ">2", True), (1, "<2", True), (2, "<2", False),
])
def test_the_kernel_side_check_agrees_with_the_host_side_one(count, expect, ok):
    assert _kernel_expect_ok()(count, expect) is ok


# ---------------------------------------------------------------------------
# Generated code
# ---------------------------------------------------------------------------

def test_the_runtime_is_syntactically_valid():
    ast.parse(selectors.RUNTIME)


def test_the_runtime_stays_python_2_compatible():
    """It runs in the Abaqus 2021 kernel, which is Python 2.7.

    Checked on the signature lines rather than by scanning for '->' anywhere:
    the log format string contains a literal arrow ('selector -> 3 faces') and
    a blanket ban flagged it, which is the kind of false positive that gets a
    guard deleted instead of fixed.
    """
    assert not re.search(r"""(?<![A-Za-z0-9_])f["']""", selectors.RUNTIME)
    for line in selectors.RUNTIME.splitlines():
        stripped = line.strip()
        if not stripped.startswith("def "):
            continue
        assert "->" not in stripped, "return annotation: %s" % stripped
        params = stripped[stripped.index("(") + 1:stripped.rindex(")")]
        assert ":" not in params, "parameter annotation: %s" % stripped


def test_resolve_expression_is_valid_python_and_carries_the_whole_selector():
    sel = selectors.parse("Upper:face@y=min", expect=2)
    call = selectors.resolve_expression(sel, "a.instances['Upper']")
    ast.parse(call)
    assert "a.instances['Upper']" in call
    assert "'faces'" in call and "'y'" in call and "'min'" in call
    assert "'=2'" in call
    # The raw text travels with the call so the failure message can quote the
    # selector the way the author wrote it, not a reconstruction of it.
    assert "'Upper:face@y=min'" in call


def test_the_mismatch_message_names_the_selector_and_both_counts():
    """This string is the entire user-facing value of the layer."""
    body = selectors.RUNTIME
    marker = body[body.index("SELECTOR_MISMATCH"):body.index("_sel_log(message)")]
    for token in ("%s matched %d %s, expected %s", "label", "count", "attribute"):
        assert token in marker, marker


def test_a_cell_selector_cannot_become_a_surface():
    """Surfaces need faces or edges; cells and vertices have no side1 keyword."""
    assert selectors.parse("Lower:face@z=max").surface_kwarg == "side1Faces"
    assert selectors.parse("Lower:edges@z=max").surface_kwarg == "side1Edges"
    assert selectors.parse("Lower:cells@all").surface_kwarg is None
    assert selectors.parse("Lower:vertices@all").surface_kwarg is None


def test_the_radius_filter_asks_the_entity_rather_than_its_bounding_box():
    """getRadius() raising IS the "is this curved" test.

    dir(face) on Abaqus 2021 has no predicate for it, and the alternative --
    getByBoundingCylinder -- was measured to return all 7 faces of a plate once
    the radius is large enough. A generated filter built on containment would
    match the whole part and still satisfy `>=1`.
    """
    body = selectors.RUNTIME
    assert "_sel_by_radius" in body
    assert "getRadius()" in body
    assert "getByBoundingCylinder" not in body


def test_the_radius_filter_builds_an_abaqus_sequence_not_a_python_list():
    """Set(faces=[...]) wants a geometry sequence; slice-concatenation is how
    one is built from chosen indices."""
    body = selectors.RUNTIME
    chunk = body[body.index("def _sel_by_radius"):body.index("def _sel_expect_ok")]
    assert "seq[i:i + 1]" in chunk
    assert "seq[0:0]" in chunk, "an empty result must still be a sequence"


def test_the_bounding_box_is_never_hand_rolled_from_vertex_coordinates():
    """The extremes of a curved solid are not at its vertices.

    Measured on a flange revolved to an outer radius of 30: the vertex-derived
    box came back x 4..30, z 0..0 against a true extent of x -30..30,
    z -30..30. Every part shipped before this was an extruded box, where every
    extreme IS a vertex, so nothing caught it -- and a part only has to acquire
    one curved face for `face@x=max` to start resolving against a plane that is
    not the part's.

    Also measured: a PART has no getBoundingBox() at all (AttributeError), so
    on a part this code never took its first branch even once.
    """
    body = selectors.RUNTIME
    chunk = body[body.index("def _sel_bbox"):body.index("def _sel_by_radius")]
    assert "getBoundingBox()" in chunk
    assert "v.pointOn" not in chunk, "the vertex loop is back"
    assert "min(xs)" not in chunk
    # cells / faces / edges each carry the real box; vertices repeats the wrong
    # answer, so it must come after them.
    order = [chunk.index("'%s'" % name) for name in ("cells", "faces", "edges")]
    assert order == sorted(order), "geometry sequences must be tried in order"
    assert chunk.index("'vertices'") > max(order), "vertices must be last"


def test_the_tolerance_scales_with_the_model():
    """A fixed length is wrong at both ends of the size range.

    0.01 mm is float noise on a bridge and a real feature on a MEMS part, so
    the plane tolerance is a fraction of the model span.
    """
    assert 0 < selectors.DEFAULT_SCALE_TOL < 1e-3
    assert re.search(r"span\s*\*\s*scale_tol", selectors.RUNTIME)


@pytest.mark.parametrize("raw", ["cell@x=min", "cells@y=0", "Blk:cell@z=max"])
def test_a_cell_on_a_plane_is_refused(raw):
    """Same shape as the element refusal, and it was still on offer.

    A cell is a volume for exactly the reason an element is, so
    `getByBoundingBox` on it means wholly inside and a plane matches nothing.
    Measured on Abaqus 2021 (artifacts/probe_cell) on a plate partitioned into
    two cells at x=10:

        cell@x=min, the band this dialect emits    0 of 2
        cell@x=min, a band 100x tighter            0 of 2
        a box containing the whole first cell      1
        face@x=min, the SAME band as row one       1

    The last two rows are why this is a refusal and not a wider tolerance: the
    band is not too thin -- it catches the face lying in that plane -- and the
    box that does catch the cell is one containing all of it.
    """
    with pytest.raises(selectors.SelectorError) as excinfo:
        selectors.parse(raw)
    message = str(excinfo.value)
    assert "wholly inside" in message
    assert "0 of 2" in message, (
        "the refusal has to carry the measurement, or it reads as a "
        "restriction somebody chose rather than a fact about Abaqus")
    assert "cell@all" in message and "face" in message, (
        "and it has to offer what does work")


def test_the_cell_forms_that_still_work_are_untouched():
    """`@all` is the whole point of leaving the kind in the grammar."""
    assert selectors.parse("cell@all").attribute == "cells"
    assert selectors.parse("Bolt-1:cells@all").expect == ">=1"
