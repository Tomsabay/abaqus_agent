"""What an Explicit model needs that a Standard one does not.

Three things, all of them found by trying to put a CONWEP air blast in front of
the bolted frame, and all measured on Abaqus 2021 rather than read off a
docstring -- the docstrings were wrong twice.

1. `type: contact` compiled to SurfaceToSurfaceContactStd, which is
   Standard-only. Every contact this dialect can write was therefore unusable
   in the one solver CONWEP runs on. And the Explicit call is not the Standard
   one renamed: it takes neither `thickness` nor `adjustMethod`. Its own
   __doc__ lists `masterNoThick`/`slaveNoThick` among the REQUIRED arguments,
   and the kernel answers both spellings with a refusal
   (artifacts/promo/probe_conwep/probe_exp_kwargs.py):

       master/slave + masterNoThick/slaveNoThick   keyword error on masterNoThick
       main/secondary + mainNoThick/secondaryNoThick   keyword error on main
       master/slave + mainNoThick/secondaryNoThick     keyword error on mainNoThick
       master/slave, no NoThick at all                 OK

2. `mesh.ElemType(elemCode=C3D10M, elemLibrary=EXPLICIT)` writes
   `*Element, type=C3D4`. Read off the WRITTEN DECK, because MeshElement.type
   answers C3D4 even for an assignment that writes C3D10
   (artifacts/promo/probe_conwep/probe_tet_deck.py), same box, same seed:

       C3D10M, EXPLICIT  -> *Element, type=C3D4     96 nodes / 324 elements
       C3D10M, STANDARD  -> *Element, type=C3D10M  577 nodes / 324 elements
       C3D10,  STANDARD  -> *Element, type=C3D10   577 nodes / 324 elements

   A linear tet is several times too stiff. The job meshes, solves and looks
   ordinary, which is the failure this repo exists to refuse.

3. A tet-only element list is rejected while the region still carries the
   default HEX controls: "The Hex shape associated with the regions does not
   have a valid element type." C3D10 escapes it because Abaqus fills the empty
   hex slot from its own family; C3D10M has no family to fill it from.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from runner import build_v2, kernel_runtime, mesh_policy  # noqa: E402
from runner.v2_pairs import _contact_calls  # noqa: E402

STATIC = {"steps": [{"name": "S", "type": "Static"}]}
EXPLICIT = {"steps": [{"call": "ExplicitDynamicsStep", "name": {"literal": "B"}}]}
PAIR = {"type": "contact", "sliding": "small",
        "property": {"normal": "hard", "friction": 0.3}}


def test_the_solver_decides_which_contact_call_is_written():
    assert not build_v2._is_explicit(STATIC)
    assert build_v2._is_explicit(EXPLICIT)


def test_a_standard_model_still_writes_the_standard_pair():
    lines = "\n".join(_contact_calls("C", PAIR, "M", "S", explicit=False))
    assert "_contact(m," in lines
    assert "_contact_exp" not in lines
    assert "thickness=ON" in lines and "adjustMethod=NONE" in lines


def test_an_explicit_model_writes_the_explicit_pair_and_nothing_std_only():
    lines = "\n".join(_contact_calls("C", PAIR, "M", "S", explicit=True))
    assert "_contact_exp(m," in lines
    for std_only in ("thickness=ON", "adjustMethod", "initialClearance",
                     "datumAxis", "clearanceRegion"):
        assert std_only not in lines, std_only
    assert "mechanicalConstraint=KINEMATIC" in lines


def _helper_body(name: str) -> str:
    """The helper's code, without the comment above it -- the measurement that
    produced the code is written there, so the words being refused appear in
    the prose on purpose."""
    body = kernel_runtime.HELPERS.split("def %s(" % name, 1)[1]
    return body.split("\ndef ", 1)[0]


def test_the_explicit_pair_passes_no_nothick_in_either_spelling():
    """Both were refused by the kernel; the __doc__ that lists them as required
    is wrong, and a call written from it cannot be built."""
    lines = "\n".join(_contact_calls("C", PAIR, "M", "S", explicit=True))
    for spelling in ("masterNoThick", "slaveNoThick",
                     "mainNoThick", "secondaryNoThick"):
        assert spelling not in lines, spelling
    assert "NoThick" not in _helper_body("_contact_exp")


def test_the_contact_property_is_the_same_either_way():
    """The solver changes which pair call is written, not what the surfaces
    are supposed to do to each other."""
    std = _contact_calls("C", PAIR, "M", "S", explicit=False)
    exp = _contact_calls("C", PAIR, "M", "S", explicit=True)
    assert std[:-1] == exp[:-1]


def test_c3d10m_is_asked_for_through_the_standard_library():
    assert mesh_policy._library_for(("C3D10M",), "EXPLICIT") == "STANDARD"
    assert mesh_policy._library_for(("C3D10M",), "STANDARD") == "STANDARD"


def test_nothing_else_is_moved_off_the_explicit_library():
    """The substitution is for one measured defect, not a policy. C3D8R keeps
    EXPLICIT because that is where hourglassControl lives, and losing it was a
    5.3% error on explicit_impact."""
    for code in ("C3D8R", "C3D8I", "C3D4", "S4R", "C3D10"):
        assert mesh_policy._library_for((code,), "EXPLICIT") == "EXPLICIT", code
    assert mesh_policy._library_for(("C3D8R", "C3D6", "C3D4"), "EXPLICIT") == "EXPLICIT"


def test_a_family_less_tet_needs_its_shape_set_first():
    assert mesh_policy._shape_before_element(("C3D10M",))
    assert mesh_policy._shape_before_element(("C3D10H",))


def test_a_tet_with_a_family_keeps_the_order_the_frozen_decks_carry():
    """Reversing it everywhere is right and is a separate job: it moves eleven
    pinned deck hashes and forces twenty-seven unreproducible run directories
    to rebuild."""
    assert not mesh_policy._shape_before_element(("C3D10",))
    assert not mesh_policy._shape_before_element(("C3D8R", "C3D6", "C3D4"))


def _script(element: str, steps: list) -> str:
    spec = {
        "meta": {"abaqus_release": "2021", "model_name": "M", "units": "mm_MPa_t"},
        "material": {"name": "S", "E": 210000.0, "nu": 0.3, "density": 7.85e-9},
        "parts": [{
            "name": "P",
            "features": [
                {"op": "sketch", "id": "s", "plane": "XY",
                 "profile": {"rect": {"corner1": [0.0, 0.0], "corner2": [10.0, 10.0]}}},
                {"op": "extrude", "sketch": "s", "depth": 10.0},
            ],
            "expect": {"volume": 1000.0},
            "section": {"type": "solid", "material": "S"},
            "mesh": {"seed": 5.0, "element": element},
        }],
        "assembly": {"instances": [{"name": "I", "part": "P"}]},
        "steps": steps,
        "outputs": {"kpis": [{"name": "M", "type": "field_max",
                              "location": "whole_model"}]},
    }
    script = build_v2.generate_script(spec)
    # Only the part the spec produced. The helpers ahead of it define
    # _expect_second_order and mention setElementType, and an assertion that
    # reads them is answering about the runtime, not about this model.
    return script.split(kernel_runtime.HELPERS, 1)[1]


BLAST = [{"call": "ExplicitDynamicsStep", "name": {"literal": "B"},
          "previous": {"literal": "Initial"}, "timePeriod": 0.001}]


def test_the_emitted_deck_asks_for_c3d10m_and_checks_it_landed():
    body = _script("C3D10M", BLAST)
    assert "elemCode=C3D10M, elemLibrary=STANDARD" in body
    assert "elemLibrary=EXPLICIT" not in body
    assert "_expect_second_order(p, 'P', 'C3D10M')" in body
    assert body.index("setMeshControls") < body.index("setElementType")


def test_a_hex_explicit_part_is_untouched_and_carries_no_order_check():
    body = _script("C3D8R", BLAST)
    assert "elemCode=C3D8R, elemLibrary=EXPLICIT" in body
    assert "_expect_second_order(" not in body
    # A hex part that asked for no shape gets no controls line, so there is no
    # order to get wrong; the reordering only reaches parts that have one.
    assert "setMeshControls" not in body
    assert "setElementType" in body


def test_the_runtime_check_compares_nodes_against_elements():
    body = kernel_runtime.HELPERS.split("def _expect_second_order", 1)[1]
    body = body.split("\ndef ", 1)[0]
    assert "nodes <= elements" in body
    assert "MESH_ORDER_FAIL" in body and "raise ValueError" in body
