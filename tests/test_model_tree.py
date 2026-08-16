"""The model tree is what the spec says, and it may not say less than that.

Hermetic — no Abaqus, no CAE, no browser. The tree is derived from the spec
dict alone (workbench/model_tree.py), which is what makes it testable at all:
the pane it feeds has to be right while the spec is still wrong, so it cannot
depend on anything a build produces.

The property under test is the same one the engine lives by. A tree that draws
four of five parts looks exactly like a model that has four parts, and nothing
on screen tells the two apart — so every key the tree cannot read has to become
a visible row or a listed unknown, never a silent omission.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from workbench.model_tree import build_tree  # noqa: E402

CASES = ROOT / "cases"


def _spec(name: str) -> dict:
    return yaml.safe_load((CASES / name / "spec.yaml").read_text(encoding="utf-8"))


def _group(tree: dict, gid: str) -> dict:
    for group in tree["groups"]:
        if group["id"] == gid:
            return group
    return {"id": gid, "count": 0, "rows": []}


def _labels(tree: dict, gid: str) -> list[str]:
    return [row["label"] for row in _group(tree, gid)["rows"]]


# --- the shipped specs ------------------------------------------------------

@pytest.mark.parametrize("case,dialect", [
    ("two_plate_tie", "v2"),
    ("two_plate_contact", "v2"),
    ("block_friction_slide", "v2"),
    ("plate_hole_v2", "v2"),
    ("cantilever", "v2"),
    ("modal", "v2"),
    ("plate_hole", "v2"),
    ("blast_plate", "v2"),
    ("explicit_impact", "v2"),
    ("cantilever_plastic", "v2"),
    ("bearing_block", "v2"),
    ("steel_frame_blast", "deck"),
])
def test_every_shipped_spec_produces_a_tree(case, dialect):
    tree = build_tree(_spec(case))
    assert tree["dialect"] == dialect
    assert tree["groups"], "%s produced an empty tree" % case
    assert tree["unknown_keys"] == [], (
        "%s carries top-level keys the tree cannot read: %s"
        % (case, tree["unknown_keys"]))


def test_a_deck_spec_says_so_instead_of_drawing_an_empty_model():
    """Empty `零件` and `分析步` groups would read as "this model has none".

    It has a whole deck of both; the tree just cannot see inside a .inp.
    """
    tree = build_tree(_spec("steel_frame_blast"))
    assert [g["id"] for g in tree["groups"]] == ["materials", "deck", "outputs"]
    assert _labels(tree, "deck") == ["SteelFrameBlast.inp"]


def test_the_instance_count_is_the_instance_count():
    """Two instances of one part is the case that catches a tree keyed on parts."""
    tree = build_tree(_spec("two_plate_tie"))
    assert _labels(tree, "parts") == ["Half"]
    assert _labels(tree, "assembly") == ["Lower", "Upper"]


def test_an_instance_row_carries_the_key_the_viewport_uses():
    """post/parse_inp.py names a preview part after its INSTANCE, so that is
    what a row click has to send."""
    tree = build_tree(_spec("block_friction_slide"))
    rows = {r["label"]: r for r in _group(tree, "assembly")["rows"]}
    assert rows["Slider"]["instance"] == "Slider"
    assert ["零件", "Slider"] in rows["Slider"]["facts"]
    assert ["平移", "(10, 10, 10)"] in rows["Slider"]["facts"]


def test_a_contact_row_names_both_selectors():
    """The two selectors are what lets a click emphasise both bodies."""
    tree = build_tree(_spec("block_friction_slide"))
    row = _group(tree, "interactions")["rows"][0]
    assert row["kind"] == "contact"
    assert row["selectors"] == ["Base:face@y=max", "Slider:face@y=min"]
    assert ["摩擦系数", "0.3"] in row["facts"]


def test_conditions_are_filed_under_the_step_they_name():
    spec = _spec("two_plate_tie")
    tree = build_tree(spec)
    press = _group(tree, "steps")["rows"][0]
    assert press["label"] == "Press"
    assert [c["label"] for c in press["children"]] == ["FixLower", "FixUpper", "Top"]


def test_measurement_regions_show_up_beside_the_kpis():
    """plate_hole_v2's whole point is that HOOP_MAX is measured on a named
    region and not on whole_model."""
    tree = build_tree(_spec("plate_hole_v2"))
    labels = _labels(tree, "outputs")
    assert "HoleWall" in labels and "HOOP_MAX" in labels


# --- the dispatched dialect -------------------------------------------------

def _dispatched() -> dict:
    return {
        "meta": {"model_name": "D", "abaqus_release": "2021", "units": "mm_MPa_t"},
        "material": {"name": "Steel", "E": 210000.0, "nu": 0.3},
        "parts": [{"name": "Bar",
                   "features": [{"call": "BaseSolidExtrude", "sketchPlane": "X"}],
                   "expect": {"cells": 1},
                   "section": {"type": "solid", "material": "Steel"},
                   "mesh": {"seed": 5.0, "element": "C3D8I"}}],
        "assembly": {"instances": [{"name": "Bar", "part": "Bar"}]},
        "steps": [{"call": "FrequencyStep", "name": {"literal": "Modes"},
                   "previous": {"literal": "Initial"}, "numEigen": 5}],
        "conditions": [{"call": "EncastreBC", "name": {"literal": "Fix"},
                        "createStepName": {"literal": "Initial"},
                        "region": {"set": "Bar:face@z=min", "name": "FIX",
                                   "expect": "=1"}}],
        "outputs": {"kpis": [{"name": "F1", "type": "eigenfrequency",
                              "location": "mode_1"}],
                    "field_variables": ["U"]},
    }


def test_a_dispatched_step_is_labelled_by_its_literal_name():
    tree = build_tree(_dispatched())
    step = _group(tree, "steps")["rows"][0]
    assert step["label"] == "Modes"
    assert step["detail"] == "FrequencyStep"
    assert ["numEigen", "5"] in step["facts"]


def test_a_dispatched_condition_lands_in_its_step():
    """createStepName is the only thing that says where a condition acts."""
    tree = build_tree(_dispatched())
    initial = [r for r in _group(tree, "steps")["rows"] if r["label"] == "Initial"]
    assert initial, "a condition naming a step that is not in steps[] must show"
    assert initial[0]["warn"] is True
    assert [c["label"] for c in initial[0]["children"]] == ["Fix"]


def test_a_generic_part_feature_is_named_not_summarised_away():
    tree = build_tree(_dispatched())
    part = _group(tree, "parts")["rows"][0]
    assert part["detail"] == "BaseSolidExtrude"
    assert part["generic_calls"] == 1
    assert ["expect.cells", "1"] in part["facts"]


def test_field_variables_are_shown_because_they_change_the_analysis():
    tree = build_tree(_dispatched())
    assert "场输出变量" in _labels(tree, "outputs")


# --- nothing may be dropped -------------------------------------------------

def test_an_unreadable_top_level_key_is_listed():
    spec = _dispatched()
    spec["nonsense_block"] = {"a": 1}
    assert build_tree(spec)["unknown_keys"] == ["nonsense_block"]


def test_a_condition_without_a_call_becomes_a_warning_row():
    spec = _dispatched()
    spec["conditions"].append({"name": "Mystery"})
    tree = build_tree(spec)
    orphan = [r for r in _group(tree, "steps")["rows"] if r["label"] == "(未归属)"]
    assert orphan and orphan[0]["warn"] is True
    assert orphan[0]["children"][0]["detail"] == "没有 call"


def test_a_part_that_is_not_a_mapping_still_gets_a_row():
    spec = _dispatched()
    spec["parts"].append("just a string")
    rows = _group(build_tree(spec), "parts")["rows"]
    assert len(rows) == 2
    assert rows[1]["warn"] is True


def test_a_feature_with_neither_op_nor_call_is_named():
    spec = _dispatched()
    spec["parts"][0]["features"].append({"depth": 1.0})
    part = _group(build_tree(spec), "parts")["rows"][0]
    assert part["children"][-1]["detail"] == "既没有 op 也没有 call"


def test_a_broken_spec_never_raises():
    """The tree is drawn while the spec is still wrong; that is its whole job."""
    for junk in (None, "not a mapping", 42, [], {"steps": "no"},
                 {"parts": [None]}, {"parts": [{"name": "X"}], "conditions": [7]}):
        tree = build_tree(junk)
        assert isinstance(tree, dict) and "groups" in tree


def test_every_material_property_reaches_the_pane():
    """The engine refuses a material key it cannot build; the tree must not be
    the place that hides one that was accepted."""
    spec = _dispatched()
    spec["material"].update({"density": 7.85e-09, "yield": 250.0,
                             "conductivity": 45.0})
    row = _group(build_tree(spec), "materials")["rows"][0]
    keys = {k for k, _ in row["facts"]}
    assert keys == {"E", "nu", "density", "yield", "conductivity"}
