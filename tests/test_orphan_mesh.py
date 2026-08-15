"""A part read out of a deck: `node@`, `element@`, and what has to be stated.

#65 imported STEP, IGES and SAT and stopped at orphan meshes, noting that the
real gap was the selector layer rather than the import branch. That was half
right, and the half it got wrong is the half worth writing down.

WHAT AN ORPHAN PART IS. Measured on Abaqus 2021 (artifacts/probe_orphan),
`m.PartFromInputFile` on a deck holding one meshed bar returns

    189 nodes, 80 elements, 0 cells, 0 faces, 0 edges, 0 vertices

and DROPS the sets and surfaces the file carried -- 3 `*Nset`, 4 `*Elset` and
1 `*Surface` in, `sets: []` and `surfaces: []` out. So every selector this
dialect had resolved against an empty sequence, and `Set(faces=<empty>)` is
accepted in silence.

WHY `element@` IS NOT `node@`. `getByBoundingBox` on elements means WHOLLY
INSIDE. On that bar the tolerance band this dialect emits -- the model span x
1e-6 -- matched 0 of 80 elements at z=min, while a band one element thick
matched the 4 of that layer. A plane is a surface and an element is a volume,
so the plane form is refused for elements and carries that measurement. A node
is a point: the same band matched the 9 on the plane.

TWO SILENT ZEROS, both of which decide a rule here:

    p.getVolume()                       -> 0.0, no exception
    p.Set(name='ALL', cells=p.cells)    -> a set holding 0 cells, no exception
    p.SectionAssignment(that set)       -> assigned to 0 cells, no exception

The first is why an import must state what came back and why a mesh import
states nodes/elements rather than volume/cells. The second is why the orphan
route builds its 'ALL' set from elements instead -- the default path would have
produced a part with no section and said nothing.

Numbers are produced by scripts/run_orphan_mesh_check.py against the real
solver, including the end-to-end one: that imported bar solves to -0.18946819
against P L^3 / 3EI = -0.19047619, 0.53% out. Nothing here runs Abaqus.
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import selectors  # noqa: E402
from runner import build_v2  # noqa: E402
from runner import spec_base


# --- the selector grammar --------------------------------------------------

@pytest.mark.parametrize("raw,attribute", [
    ("node@z=min", "nodes"),
    ("nodes@all", "nodes"),
    ("I:node@x=0", "nodes"),
    ("element@all", "elements"),
    ("elements@all", "elements"),
])
def test_mesh_kinds_parse_to_the_abaqus_sequence(raw, attribute):
    assert selectors.parse(raw).attribute == attribute


def test_singular_and_plural_still_set_the_default_count():
    """Unchanged rule, and worth pinning because a plane of NODES is many.

    `node@z=min` means exactly one and a root plane has nine, so the singular
    form fails loudly with the count in the message. That is the intended
    reading: write `nodes@z=min` for a plane, `node@` for a single point.
    """
    assert selectors.parse("node@z=min").expect == "=1"
    assert selectors.parse("nodes@z=min").expect == ">=1"


@pytest.mark.parametrize("raw", ["element@z=min", "elements@x=0",
                                 "I:element@y=max"])
def test_an_element_on_a_plane_is_refused(raw):
    with pytest.raises(selectors.SelectorError) as excinfo:
        selectors.parse(raw)
    message = str(excinfo.value)
    assert "wholly inside" in message
    assert "0 of 80" in message, (
        "the refusal has to carry the measurement, or it reads as a "
        "restriction somebody chose rather than a fact about Abaqus")
    assert "element@all" in message and "node@z=min" in message, (
        "and it has to offer the two forms that do work")


@pytest.mark.parametrize("raw", ["node@r=5", "element@r=5"])
def test_mesh_kinds_have_no_radius(raw):
    with pytest.raises(selectors.SelectorError) as excinfo:
        selectors.parse(raw)
    assert "only faces and edges" in str(excinfo.value)


def test_neither_mesh_kind_can_be_a_surface():
    """A tie and a contact pair need faces, and an orphan part has none."""
    for kind in ("node", "element"):
        assert selectors.KINDS[kind][1] is None


def test_the_bounding_box_chain_ends_at_nodes():
    """`min` and `max` need a box, and an orphan part has geometry for none.

    Measured: each EMPTY geometry sequence answers getBoundingBox() with a
    reversed degenerate box -- low (0,0,0), high (-1,-1,-1) -- rather than
    raising, which the runtime's high > low guard already rejects. So nodes can
    be appended without changing what a part with geometry resolves to.
    """
    body = selectors.RUNTIME.split("def _sel_bbox", 1)[1]
    loop = body.split("for source in (", 1)[1].split("):", 1)[0]
    assert "'nodes'" in loop, "an orphan part has a box only its nodes know"
    assert loop.index("'cells'") < loop.index("'nodes'"), (
        "a part with geometry has to keep answering from its cells")
    assert "'elements'" not in loop, (
        "elements would answer the same box as nodes and cost a second call")


# --- the import branch -----------------------------------------------------

def _part(**overrides) -> dict:
    part = {
        "name": "Bar",
        "import": {"part": {"call": "PartFromInputFile",
                            "inputFileName": {"file": "bar.inp"}}},
        "expect": {"mesh": {"nodes": 189, "elements": 80}},
        "section": {"type": "solid", "material": "Steel"},
    }
    part.update(overrides)
    return part


def _spec(part: dict) -> dict:
    return {
        "meta": {"abaqus_release": "2021", "model_name": "M",
                 "units": "mm_MPa_t"},
        "material": {"name": "Steel", "E": 210000.0, "nu": 0.3,
                     "density": 7.85e-9},
        "parts": [part],
        "assembly": {"instances": [{"name": "B", "part": "Bar",
                                    "translate": [0.0, 0.0, 0.0]}]},
        "steps": [{"call": "StaticStep", "name": {"literal": "One"},
                   "previous": {"literal": "Initial"}}],
        "conditions": [
            {"call": "EncastreBC", "name": {"literal": "Fix"},
             "createStepName": {"literal": "Initial"},
             "region": {"set": "B:nodes@z=min", "name": "ROOTN",
                        "expect": "=9"}}],
        "outputs": {"kpis": [{"name": "U", "type": "field_min",
                              "location": "whole_model", "component": "U2"}]},
    }


def _emit(spec: dict, tmp_path=None) -> str:
    """Generated with a directory where `{file:}` can find the deck."""
    if tmp_path is not None:
        (tmp_path / "bar.inp").write_text("*Heading\n", encoding="utf-8")
    return build_v2.generate_script(
        spec, spec_dir=str(tmp_path) if tmp_path else None)


def _refuse(spec: dict, tmp_path=None) -> str:
    if tmp_path is not None:
        (tmp_path / "bar.inp").write_text("*Heading\n", encoding="utf-8")
    with pytest.raises(spec_base.SpecError) as excinfo:
        build_v2.generate_script(
            spec, spec_dir=str(tmp_path) if tmp_path else None)
    return str(excinfo.value)


def test_an_import_with_no_opener_dispatches_one_call_on_the_model(tmp_path):
    text = _emit(_spec(_part()), tmp_path)
    assert "_before_import = list(m.parts.keys())" in text
    assert "_gcall(m, 'PartFromInputFile'" in text
    assert "p = _gimported(m, 'Bar', _before_import" in text


def test_the_part_is_picked_up_by_diffing_the_model(tmp_path):
    """Not by the call's return value, and not by a name the spec guessed.

    Measured: the method takes no `name`, and the deck's name arrives
    upper-cased. Diffing the model's parts works whatever the method returns.
    """
    text = _emit(_spec(_part()), tmp_path)
    before = text.index("_before_import = list(m.parts.keys())")
    call = text.index("_gcall(m, 'PartFromInputFile'")
    pick = text.index("p = _gimported(m, 'Bar', _before_import")
    assert before < call < pick


def test_the_orphan_section_is_assigned_to_elements(tmp_path):
    """The measured silent zero, and the reason this branch exists."""
    text = _emit(_spec(_part()), tmp_path)
    assert "p.Set(name='ALL', elements=p.elements)" in text
    assert "p.Set(name='ALL', cells=p.cells)" not in text


def test_a_geometry_part_still_takes_the_cells_path():
    """The frozen decks are compared byte-for-byte, so this cannot drift."""
    spec = _spec({
        "name": "Bar",
        "features": [{"op": "sketch", "id": "o", "plane": "XY",
                      "profile": {"rect": {"corner1": [0.0, 0.0],
                                           "corner2": [10.0, 10.0]}}},
                     {"op": "extrude", "sketch": "o", "depth": 100.0}],
        "section": {"type": "solid", "material": "Steel"},
        "mesh": {"seed": 5.0, "element": "C3D8I"},
    })
    text = build_v2.generate_script(spec)
    assert "p.Set(name='ALL', cells=p.cells)" in text
    assert "p.Set(name='ALL', elements=p.elements)" not in text


def test_a_mesh_import_may_not_carry_a_mesh_block(tmp_path):
    message = _refuse(_spec(_part(mesh={"seed": 5.0, "element": "C3D8I"})),
                      tmp_path)
    assert "nothing to seed" in message
    assert "0 cells" in message, "and it should say what it measured"


def test_an_import_stating_nothing_is_refused(tmp_path):
    message = _refuse(_spec(_part(expect={"faces": 6})), tmp_path)
    assert "expect.volume" in message and "expect.mesh.nodes" in message
    assert "SAME 6 faces" in message, (
        "`faces: 6` is exactly what an author reaches for, and the reason it "
        "is not enough is measured -- the IGES shell has the solid's faces")


def test_a_name_on_the_import_call_is_refused(tmp_path):
    part = _part()
    part["import"]["part"]["name"] = "Bar"
    message = _refuse(_spec(part), tmp_path)
    assert "does not take one" in message
    assert "changeKey" in message


def test_an_import_without_open_needs_a_call(tmp_path):
    part = _part()
    part["import"]["part"] = {"inputFileName": {"file": "bar.inp"}}
    message = _refuse(_spec(part), tmp_path)
    assert "must be a call mapping" in message
    assert "PartFromInputFile" in message, "the message should show the shape"


def test_the_geometry_route_is_untouched(tmp_path):
    """`open:` still means PartFromGeometryFile, and still demands a volume."""
    (tmp_path / "bar.step").write_text("ISO-10303-21;\n", encoding="utf-8")
    part = {
        "name": "Bar",
        "import": {"open": {"call": "openStep",
                            "fileName": {"file": "bar.step"}}},
        "expect": {"volume": 10000.0},
        "section": {"type": "solid", "material": "Steel"},
        "mesh": {"seed": 5.0, "element": "C3D8I"},
    }
    text = build_v2.generate_script(_spec(part), spec_dir=str(tmp_path))
    assert "'PartFromGeometryFile'" in text
    # The helper always ships and its own `def` line contains `_gimported(m,`,
    # so the needle has to be the assignment the orphan route emits.
    assert "p = _gimported(m," not in text
    assert "p.Set(name='ALL', cells=p.cells)" in text


# --- the mesh count check --------------------------------------------------

def test_expect_mesh_takes_a_node_count(tmp_path):
    text = _emit(_spec(_part()), tmp_path)
    assert "_mesh_check(p, 'Bar', '=80', None, None, nodes_expect='=189')"         in text


def test_expect_mesh_nodes_accepts_a_comparison(tmp_path):
    text = _emit(_spec(_part(expect={"mesh": {"nodes": ">=100"}})), tmp_path)
    assert "nodes_expect='>=100'" in text


def test_a_part_that_states_no_node_count_emits_the_line_it_always_did():
    """The frozen decks are compared byte for byte, so a new argument cannot
    be spent on parts that did not ask for it."""
    spec = _spec({
        "name": "Bar",
        "features": [{"op": "sketch", "id": "o", "plane": "XY",
                      "profile": {"rect": {"corner1": [0.0, 0.0],
                                           "corner2": [10.0, 10.0]}}},
                     {"op": "extrude", "sketch": "o", "depth": 100.0}],
        "expect": {"mesh": {"elements": 80}},
        "section": {"type": "solid", "material": "Steel"},
        "mesh": {"seed": 5.0, "element": "C3D8I"},
    })
    text = build_v2.generate_script(spec)
    assert "_mesh_check(p, 'Bar', '=80', None, None)" in text
    assert "nodes_expect" not in text.split("def _mesh_check", 1)[-1]         .split("_mesh_check(p,", 1)[-1]


def test_an_unknown_mesh_expect_key_is_still_refused(tmp_path):
    message = _refuse(
        _spec(_part(expect={"mesh": {"nodes": 189, "nodez": 189}})), tmp_path)
    assert "not something the mesh check measures" in message


def test_a_mesh_expect_that_only_bounds_the_mesh_is_refused(tmp_path):
    """Found by the test above: `expect.mesh` with only `max_warned` in it
    used to fall through to the generic message, which reported "Stated:
    mesh" and read as though the block had been thrown away."""
    message = _refuse(_spec(_part(expect={"mesh": {"max_warned": 0}})),
                      tmp_path)
    assert "bounds a mesh without saying what came out of the file" in message
    assert "max_warned" in message


def test_the_kernel_helpers_ship(tmp_path):
    text = _emit(_spec(_part()), tmp_path)
    assert "def _gimported(m, want, before, label):" in text
    for token in ("IMPORT_OK", "IMPORT_PART_COUNT", "IMPORT_NAME_TAKEN",
                  "MESH_NODES"):
        assert token in text


def test_the_import_tokens_are_not_prefixes_of_each_other():
    """A gate reads these by name, and #66 lost a run to `SELECTOR` matching
    `SELECTOR_OK`."""
    tokens = ("IMPORT_OK", "IMPORT_PART_COUNT", "IMPORT_NAME_TAKEN")
    for a in tokens:
        for b in tokens:
            if a is not b:
                assert not a.startswith(b) and not b.startswith(a)
