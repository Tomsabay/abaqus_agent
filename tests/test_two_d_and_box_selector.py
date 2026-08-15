"""The 2D layer, the box selector, and the assembly set they were needed for.

#76. `scripts/run_crack_check.py` used to carry an item called
`spec_authoring_unproven`: the extractor could refuse a bad crack, but nothing
could WRITE one from a spec. TWO things were missing, and neither was a limit
of Abaqus:

  1. **A part could only be THREE_D.** `m.Part(dimensionality=THREE_D)` was
     written into the generator, and everything downstream acted on `p.cells`.
     A contour integral is normally done on a plane-strain plate.
  2. **No selector could name ONE of two.** Partition the crack tip off and the
     y=0 line becomes two edges; a plane names both, `@all` names both, and
     between them there was nothing. This is the same gap recorded against
     `cell@<plane>` when that form was refused for matching nothing.

A third change landed with them and is deliberately NOT on that list, because
the difference between "shipped alongside" and "was in the way" is exactly the
kind of claim this repository keeps catching itself making. **An assembly
operation could not build a Set**, and the refusal read "an assembly operation
cannot build one" — true of the generator, not of Abaqus. It can now. But
measured afterwards (artifacts/probe_ci_tuple_solve), writing crackFront and
crackTip as `{select:}`, which compiles to a tuple, returns the same J to every
digit: the set form buys a NAME that `{named_set:}` can reuse, not the
capability. What genuinely changed with it is the `assignSeam` refusal on the
assembly, whose reason is now timing rather than scope.

Measured end to end on Abaqus 2021: the dialect-authored SEN plate returned
J = 2.503265619277954 against the gate's own CAE script at 2.503265619277954 —
the same number to every digit, which is what says the dialect expresses the
same model rather than a similar one.

WHY THE 2D BRANCH IS NOT COSMETIC. `Set(cells=p.cells)` on a planar part builds
a set of ZERO cells and assigns a section to nothing, without raising — the
same silent-zero shape as the IGES shell and the orphan mesh. And elemShape
defaults to HEX, so a planar part handed a hex element meshes nothing and says
nothing. Both are refused here instead.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import selectors  # noqa: E402
from runner import (
    build_v2,  # noqa: E402
    kernel_runtime,
    spec_base,
)

# --- the box selector ------------------------------------------------------

def test_a_box_parses_into_six_numbers():
    sel = selectors.parse("P:edge@box=0,0,0,10,0,0", "=1")
    assert sel.kind == "edge"
    assert sel.by_box
    assert [float(v) for v in sel.place.split(",")] == [0, 0, 0, 10, 0, 0]
    assert sel.expect == "=1"


def test_the_emitted_call_carries_the_box_verbatim():
    text = selectors.resolve_expression(
        selectors.parse("P:vertex@box=10,0,0,10,0,0", "=1"),
        "a.instances['P']")
    assert "'box'" in text and "10.0,0.0,0.0,10.0,0.0,0.0" in text


@pytest.mark.parametrize("raw,fragment", [
    ("edge@box=0,0,0", "it takes six"),
    ("edge@box=0,0,0,1,1", "it takes six"),
    ("edge@box=10,0,0,0,1,1", "xMin=10.0 above xMax=0.0"),
    ("edge@box=0,10,0,1,0,1", "yMin=10.0 above yMax=0.0"),
])
def test_a_box_that_could_only_match_nothing_is_refused(raw, fragment):
    """An inverted box returns an empty sequence and Abaqus does not object.

    That is the failure this whole module exists to stop, so it is caught at
    parse time rather than left to the count assertion at run time.
    """
    with pytest.raises(selectors.SelectorError) as err:
        selectors.parse(raw)
    assert fragment in str(err.value)


def test_min_and_max_are_not_box_words():
    """They locate a plane. A box is the corners you mean, not an extent."""
    with pytest.raises(selectors.SelectorError) as err:
        selectors.parse("edge@box=min,0,0,max,1,1")
    assert "cannot read the selector" in str(err.value)


@pytest.mark.parametrize("kind", ["cell", "element"])
def test_the_volume_kinds_take_a_box_even_though_they_refuse_a_plane(kind):
    """The measurement that produced the plane refusal said so in the same
    breath: `cell@x=min` matched 0 of 2, and *a box containing the whole cell
    matched 1*. Wholly-inside is exactly what a box is for."""
    sel = selectors.parse("%s@box=0,0,0,10,10,10" % kind)
    assert sel.by_box
    assert kind in selectors.PLANE_REFUSED           # still refused on a plane


@pytest.mark.parametrize("kind", ["cell", "element"])
def test_the_plane_refusal_points_at_the_box_form(kind):
    """The refusal used to end at "name it by its faces", which does not answer
    "which of the two cells". Now it does."""
    assert "box=" in selectors.PLANE_REFUSED[kind]


def test_the_box_runtime_pads_and_says_by_how_much():
    """An entity exactly on a corner is a coin flip without a pad, and a pad
    nobody can see is slack. It goes in the selector log."""
    assert "axis == 'box'" in selectors.RUNTIME
    assert "pad=%s" in selectors.RUNTIME


# --- the 2D part layer -----------------------------------------------------

def _part(dimensionality=None, element="C3D8I", thickness=None, extra=None):
    part = {
        "name": "P",
        "features": [
            {"op": "sketch", "id": "o", "plane": "XY",
             "profile": {"rect": {"corner1": [0.0, 0.0], "corner2": [10.0, 10.0]}}},
            {"op": "extrude", "sketch": "o", "depth": 20.0},
        ],
        "section": {"type": "solid", "material": "Steel"},
        "mesh": {"seed": 5.0, "element": element},
    }
    if dimensionality is not None:
        part["dimensionality"] = dimensionality
    if thickness is not None:
        part["section"]["thickness"] = thickness
    if extra:
        part.update(extra)
    return part


def _spec(part):
    return {
        "meta": {"abaqus_release": "2021", "model_name": "M",
                 "units": "mm_MPa_t", "description": "d",
                 "missing_questions": []},
        "material": {"name": "Steel", "E": 210000.0, "nu": 0.3},
        "parts": [part],
        "assembly": {"instances": [{"name": "I", "part": "P",
                                    "translate": [0.0, 0.0, 0.0]}]},
        "steps": [{"name": "S", "type": "Static",
                   "bcs": [{"name": "F", "region": "I:face@z=min",
                            "type": "encastre"}],
                   "loads": []}],
        "outputs": {"kpis": [{"name": "U", "type": "field_min",
                              "location": "whole_model", "component": "U2"}]},
    }


def _script(part):
    return build_v2.generate_script(_spec(part), spec_dir=str(ROOT))


def test_a_three_d_part_is_unchanged():
    """Every shipped case is on this path and five frozen decks are compared
    against HEAD, so the default must emit exactly what it always did."""
    text = _script(_part())
    assert "dimensionality=THREE_D" in text
    assert "p.Set(name='ALL', cells=p.cells)" in text
    assert "p.setElementType(regions=(p.cells,)" in text


def test_a_planar_part_acts_on_faces_everywhere():
    part = _part(dimensionality="TWO_D_PLANAR", element="CPE8", thickness=1.0)
    text = _script(part)
    assert "dimensionality=TWO_D_PLANAR" in text
    assert "p.Set(name='ALL', faces=p.faces)" in text
    assert "p.setElementType(regions=(p.faces,)" in text
    assert "p.cells" not in text.split("# --- Parts")[1].split("# --- Assembly")[0]


def test_the_planar_companion_is_a_triangle_not_a_wedge():
    """A free quad mesh leaves triangles behind, exactly as a hex leaves
    wedges. CPE8 pairs with CPE6M and not CPE6 — Abaqus's own crack examples
    use the modified one, and nothing in the name says so."""
    text = _script(_part(dimensionality="TWO_D_PLANAR", element="CPE8",
                         thickness=1.0))
    assert "elemCode=CPE8" in text
    assert "elemCode=CPE6M" in text
    # On the emitted CALL, not on the whole script: the generator's own
    # comments quote C3D6 while explaining the 3D companion table.
    emitted = text.split("p.setElementType(", 1)[1].split("))", 1)[0]
    assert "C3D6M" not in emitted and "C3D" not in emitted


def test_a_planar_part_may_not_be_meshed_with_a_solid_element():
    """Abaqus does not refuse this pairing. elemShape defaults to HEX and a
    shape a body has none of meshes nothing without raising."""
    with pytest.raises(spec_base.SpecError) as err:
        _script(_part(dimensionality="TWO_D_PLANAR", element="C3D8I",
                      thickness=1.0))
    assert "TWO_D_PLANAR" in str(err.value)
    assert "QUAD or TRI" in str(err.value)


def test_a_three_d_part_may_not_be_meshed_with_a_planar_element():
    with pytest.raises(spec_base.SpecError) as err:
        _script(_part(element="CPE8"))
    assert "THREE_D" in str(err.value)
    assert "HEX or TET or WEDGE" in str(err.value)


def test_an_unknown_dimensionality_is_refused_by_name():
    with pytest.raises(spec_base.SpecError) as err:
        _script(_part(dimensionality="TWO_D", element="CPE8", thickness=1.0))
    assert "TWO_D" in str(err.value)
    assert "TWO_D_PLANAR" in str(err.value)


def test_axisymmetric_is_planar_in_the_sense_that_matters():
    text = _script(_part(dimensionality="AXISYMMETRIC", element="CAX4",
                         thickness=None))
    assert "dimensionality=AXISYMMETRIC" in text
    assert "p.Set(name='ALL', faces=p.faces)" in text


def test_a_planar_section_carries_its_thickness():
    text = _script(_part(dimensionality="TWO_D_PLANAR", element="CPE8",
                         thickness=2.5))
    assert "thickness=2.5" in text


def test_a_planar_section_without_a_thickness_still_builds():
    """Abaqus assumes 1.0. That is a real default, not a silent failure, so it
    is allowed — but the schema says out loud what the assumption is."""
    text = _script(_part(dimensionality="TWO_D_PLANAR", element="CPE8"))
    assert "thickness=None" in text


def test_a_thickness_on_a_solid_part_is_refused():
    """On a 3D body the geometry IS the thickness, so the key can only mean the
    author thinks it is doing something it is not."""
    with pytest.raises(spec_base.SpecError) as err:
        _script(_part(thickness=2.0))
    assert "THREE_D" in str(err.value)


def test_area_is_the_2d_truth_layer_and_volume_is_not():
    """`getVolume()` on a planar part answers 0.0 without raising."""
    part = _part(dimensionality="TWO_D_PLANAR", element="CPE8", thickness=1.0)
    part["expect"] = {"area": 100.0, "faces": 1}
    text = _script(part)
    assert "'area': 100.0" in text
    # The kernel-side check is py2.7 text; it lives in runner/kernel_runtime.py
    # since that module was split out. Assert against the emitted deck as well
    # as the source, so this keeps meaning something if the text moves again.
    assert "p.getArea(p.faces)" in kernel_runtime.HELPERS
    assert "p.getArea(p.faces)" in text


def test_area_is_in_the_schema_and_so_is_dimensionality():
    import json

    schema = json.loads((ROOT / "schema" / "spec_schema.json")
                        .read_text(encoding="utf-8"))
    part = schema["properties"]["parts"]["items"]["properties"]
    assert part["dimensionality"]["enum"] == ["THREE_D", "TWO_D_PLANAR",
                                              "AXISYMMETRIC"]
    assert "thickness" in part["section"]["properties"]
    expect = schema["definitions"]["part_expect"]["properties"]
    assert "area" in expect and "area_tol" in expect


# --- the assembly set ------------------------------------------------------

def test_an_assembly_operation_can_build_a_set():
    """A crack front is an assembly set. This used to be refused outright."""
    spec = _spec(_part())
    spec["assembly"]["operations"] = [{
        "call": "ContourIntegral",
        "target": {"attr": "engineeringFeatures"},
        "name": {"literal": "Crack"},
        "crackFront": {"set": "I:vertex@box=0,0,0,0,0,0", "name": "TIP",
                       "expect": "=1"},
        "crackTip": {"named_set": "TIP"},
    }]
    text = build_v2.generate_script(spec, spec_dir=str(ROOT))
    assert "a.engineeringFeatures" in text
    assert "_gset(a, 'TIP'" in text
    assert "_gnamed(a, 'TIP'" in text


def test_a_generic_step_still_cannot_build_a_set():
    """Not an oversight. A step is made before any region exists to put in one,
    and the refusal now says which dispatch points DO keep a registry."""
    spec = _spec(_part())
    spec["steps"] = [{"call": "StaticStep", "name": {"literal": "One"},
                      "previous": {"literal": "Initial"},
                      "region": {"set": "I:face@z=min", "name": "X"}}]
    with pytest.raises(spec_base.SpecError) as err:
        build_v2.generate_script(spec, spec_dir=str(ROOT))
    assert "keeps no set registry" in str(err.value)
    assert "assembly.operations" in str(err.value)


# --- the gate that used to say this was unproven ---------------------------

def test_the_crack_gate_no_longer_claims_the_authoring_is_unproven():
    """It was a trip-wire on purpose: "no shipped case authors one, which is
    what makes that disclaimer accurate". The disclaimer is now false, so it
    had to be replaced by the measurement rather than deleted."""
    gate = (ROOT / "scripts" / "run_crack_check.py").read_text(encoding="utf-8")
    assert "spec_authoring_unproven" not in gate
    assert "spec_authored_j_matches_the_scripted_baseline" in gate
    assert "spec_authored_without_a_seam_is_still_refused" in gate, (
        "the positive criterion alone would pass a build where reaching J "
        "through the dialect skipped the truth layer")
    assert "TWO_D_PLANAR" in gate and "edge@box=" in gate


# --- the emitted runtime, actually run -------------------------------------
#
# Everything above is a claim about text. The box branch lives inside
# `selectors.RUNTIME`, which only ever executes inside abaqus python, so a
# mutation that deleted its padding passed every text assertion here. These
# exec the real branch against fakes instead, because the shipped crack recipe
# writes `vertex@box=10,0,0,10,0,0` -- a box of ZERO volume sitting exactly on
# a coordinate -- and without padding that is a float coin flip.

class _FakeSeq(list):
    """A geometry sequence: a box query and a bounding box, nothing else."""

    def __init__(self, items, low=(0.0, 0.0, 0.0), high=(1.0, 1.0, 1.0)):
        list.__init__(self, items)
        self._low, self._high = low, high
        self.last_query = None

    def getBoundingBox(self):
        return {"low": self._low, "high": self._high}

    def getByBoundingBox(self, **kwargs):
        self.last_query = kwargs
        hit = [item for item in self
               if kwargs["xMin"] <= item[0] <= kwargs["xMax"]
               and kwargs["yMin"] <= item[1] <= kwargs["yMax"]
               and kwargs["zMin"] <= item[2] <= kwargs["zMax"]]
        return _FakeSeq(hit, self._low, self._high)


class _FakeOwner:
    def __init__(self, seq):
        self.vertices = seq
        self.cells = seq


def _runtime():
    namespace: dict = {}
    exec(compile(selectors.RUNTIME, "<runtime>", "exec"), namespace)
    return namespace


def test_a_zero_volume_box_on_an_exact_coordinate_still_matches():
    """The shipped crack recipe's `vertex@box=10,0,0,10,0,0`, run.

    A crack tip is named by the coordinate the author already typed into the
    partition, so the box that names it has no volume at all. Unpadded, whether
    `10.0 <= 10.0` survives the arithmetic that produced the vertex is not
    something a spec author can reason about.
    """
    seq = _FakeSeq([(10.0, 0.0, 0.0), (0.0, 0.0, 0.0), (50.0, 50.0, 0.0)],
                   low=(0.0, -50.0, 0.0), high=(50.0, 50.0, 0.0))
    found = _runtime()["_sel_resolve"](
        _FakeOwner(seq), "vertices", "box", "10.0,0.0,0.0,10.0,0.0,0.0",
        "=1", "P:vertex@box=10,0,0,10,0,0", 1.0e-4)
    assert len(found) == 1
    pad = seq.last_query["xMax"] - 10.0
    assert pad > 0.0, (
        "the box went to getByBoundingBox unpadded. A zero-volume box on an "
        "exact coordinate is a float coin flip, and this form exists to be "
        "written against coordinates the author already knows")
    assert seq.last_query["xMin"] == 10.0 - pad, "padding has to go both ways"


def test_the_pad_scales_with_the_model_rather_than_being_a_constant():
    """Same doctrine as the plane form: a 5000 mm part is not a 5 mm part."""
    resolve = _runtime()["_sel_resolve"]
    pads = []
    for span in (50.0, 5000.0):
        seq = _FakeSeq([(0.0, 0.0, 0.0)], low=(0.0, 0.0, 0.0),
                       high=(span, span, span))
        resolve(_FakeOwner(seq), "vertices", "box", "0,0,0,0,0,0", "=1",
                "P:vertex@box=0,0,0,0,0,0", 1.0e-4)
        pads.append(seq.last_query["xMax"])
    assert pads[1] > pads[0], (
        "the tolerance did not follow the model's size, so it is either far "
        "too loose on a small part or far too tight on a big one"
    )


def test_the_count_assertion_still_fires_through_the_box_branch():
    """Padding is not slack: a box that swallows two entities has to die."""
    seq = _FakeSeq([(10.0, 0.0, 0.0), (11.0, 0.0, 0.0)],
                   low=(0.0, 0.0, 0.0), high=(50.0, 50.0, 50.0))
    with pytest.raises(Exception) as excinfo:
        _runtime()["_sel_resolve"](
            _FakeOwner(seq), "vertices", "box", "9.0,-1.0,-1.0,12.0,1.0,1.0",
            "=1", "P:vertex@box=9,-1,-1,12,1,1", 1.0e-4)
    assert "P:vertex@box=9,-1,-1,12,1,1" in str(excinfo.value)
