"""@-mentions: tree rows resolve to spec fragments, and nothing else does.

The rule under test: the resolver has NO grammar of its own. A mention is a
tree row id, resolution is "find the row the tree drew, read the path the tree
stamped on it, fetch that path" — so what can be mentioned is exactly what can
be seen, and the tree and the chat cannot drift apart.

Fail-closed is the other half. A ref the tree did not draw, a diagnostic row
with no path, a selector the build parser refuses — each raises SelectionError
with the offending thing NAMED, and the chat endpoint turns that into a 400.
An unresolved mention passed through to the LLM would have it edit an object
that is not in the spec, confidently, which is the one outcome this repository
exists to refuse.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from workbench import planner  # noqa: E402
from workbench.model_tree import build_tree  # noqa: E402
from workbench.selection import SelectionError, prompt_section, resolve_refs  # noqa: E402

V2 = {
    "meta": {"abaqus_release": "2021", "model_name": "TwoPlates",
             "units": "mm_MPa_t", "description": "d", "missing_questions": []},
    "material": {"name": "Steel", "E": 210000.0, "nu": 0.3},
    "parts": [
        {"name": "Lower",
         "features": [
             {"op": "sketch", "id": "o", "plane": "XY",
              "profile": {"rect": {"corner1": [0, 0], "corner2": [100, 50]}}},
             {"op": "extrude", "sketch": "o", "depth": 10},
         ],
         "section": {"type": "solid", "material": "Steel"},
         "mesh": {"seed": 5.0, "element": "C3D8I"}},
        {"name": "Upper",
         "features": [
             {"op": "sketch", "id": "o", "plane": "XY",
              "profile": {"rect": {"corner1": [0, 0], "corner2": [100, 50]}}},
             {"op": "extrude", "sketch": "o", "depth": 10},
         ],
         "section": {"type": "solid", "material": "Steel"},
         "mesh": {"seed": 5.0, "element": "C3D8I"}},
    ],
    "assembly": {"instances": [
        {"name": "L", "part": "Lower", "translate": [0.0, 0.0, 0.0]},
        {"name": "U", "part": "Upper", "translate": [0.0, 0.0, 10.0]},
    ]},
    "interactions": [{"name": "Bond", "type": "tie",
                      "main": "L:face@z=max", "secondary": "U:face@z=min"}],
    "steps": [{"name": "Press", "type": "Static",
               "bcs": [{"name": "Fix", "region": "L:face@z=min",
                        "type": "encastre"}],
               "loads": [{"name": "Top", "region": "U:face@z=max",
                          "type": "pressure", "value": 1.0}]}],
    "outputs": {"kpis": [{"name": "U_MAX", "type": "field_max",
                          "location": "whole_model", "component": "U3"}]},
}


def _one(ref: str) -> dict:
    return resolve_refs(V2, [{"ref": ref}])[0]


# ── every visible row kind resolves ─────────────────────────────────────────

def test_a_part_resolves_to_its_own_fragment():
    got = _one("part:Upper")
    assert got["path"] == "parts[1]"
    assert "name: Upper" in got["fragment"]
    assert "Lower" not in got["fragment"], "the fragment is the entry, not the list"


def test_an_instance_a_step_a_kpi_and_an_interaction_resolve():
    assert _one("inst:U")["path"] == "assembly.instances[1]"
    assert _one("step:Press")["path"] == "steps[0]"
    assert _one("kpi:U_MAX")["path"] == "outputs.kpis[0]"
    got = _one("inter:Bond")
    assert got["path"] == "interactions[0]"
    assert "tie" in got["fragment"]


def test_a_bc_and_a_load_resolve_below_their_step():
    assert _one("step:Press:bc:0")["path"] == "steps[0].bcs[0]"
    got = _one("step:Press:load:0")
    assert got["path"] == "steps[0].loads[0]"
    assert "pressure" in got["fragment"]


def test_a_material_resolves_for_both_spellings():
    assert _one("material:Steel")["path"] == "material"
    listed = dict(V2)
    listed.pop("material")
    listed = {**listed, "materials": [{"name": "Steel", "E": 1.0, "nu": 0.3},
                                      {"name": "Alu", "E": 2.0, "nu": 0.3}]}
    got = resolve_refs(listed, [{"ref": "material:Alu"}])[0]
    assert got["path"] == "materials[1]"


def test_a_v1_mention_fails_closed_now_that_the_tree_draws_no_v1_rows():
    """This was `test_v1_rows_resolve_too`, and its subject is gone.

    v1 was removed 2026-08-16, so the tree no longer stamps `geometry`,
    `bc_load` or `step:v1` on anything. The property that matters is the one
    this file exists for: a mention the tree did not draw must RAISE, naming the
    ref, rather than resolving to whatever else happens to live at that path.
    A saved chat that still carries an old @-mention is exactly how a stale ref
    reaches the resolver, so this is a live path, not a hypothetical.
    """
    v1 = {"meta": {"abaqus_release": "2021", "model_name": "Beam",
                   "units": "mm_MPa_t"},
          "material": {"name": "Steel", "E": 210000.0, "nu": 0.3},
          "geometry": {"type": "cantilever_block", "L": 100, "W": 10, "H": 10,
                       "seed_size": 2.5},
          "analysis": {"solver": "standard", "step_type": "Static"},
          "bc_load": {"fixed_face": "z=0", "load_face": "z=L",
                      "load_type": "pressure", "value": -1.0, "direction": 2},
          "outputs": {"kpis": [{"name": "U_tip", "type": "nodal_displacement",
                                "location": "tip_center"}]}}
    for ref in ("geometry", "bc_load", "step:v1"):
        with pytest.raises(SelectionError) as exc_info:
            resolve_refs(v1, [{"ref": ref}])
        assert ref in str(exc_info.value), (
            "the refusal has to name the offending ref, or the user cannot tell "
            "which mention went stale")


def test_a_deck_row_resolves():
    """The deck dialect draws exactly one mentionable row, and it has to work:
    it is the only handle a user has on a spec whose model is a whole .inp.
    """
    spec = {"meta": {"abaqus_release": "2021", "model_name": "Frame",
                     "units": "mm_MPa_t"},
            "material": {"name": "Steel", "E": 210000.0, "nu": 0.3},
            "deck": {"file": "SteelFrameBlast.inp"},
            "outputs": {"kpis": [{"name": "U", "type": "field_max"}]}}
    got = resolve_refs(spec, [{"ref": "deck"}])[0]
    assert got["path"] == "deck"
    assert "SteelFrameBlast.inp" in got["fragment"]


def test_every_row_the_tree_stamps_a_path_on_actually_resolves():
    """The tree is the grammar, so the guarantee has to hold for ALL of it."""
    tree = build_tree(V2)
    count = 0
    for g in tree["groups"]:
        stack = list(g["rows"])
        while stack:
            row = stack.pop()
            stack.extend(row.get("children") or [])
            if row.get("path"):
                got = resolve_refs(V2, [{"ref": row["id"]}])[0]
                assert got["path"] == row["path"], row["id"]
                count += 1
    assert count >= 10, "the v2 tree should expose at least ten mentionable rows"


# ── refusals, each naming the offender ──────────────────────────────────────

def test_a_ref_the_tree_never_drew_is_refused_by_name():
    with pytest.raises(SelectionError) as err:
        resolve_refs(V2, [{"ref": "part:Ghost", "label": "Ghost"}])
    assert "part:Ghost" in str(err.value)


def test_a_renamed_part_stops_resolving():
    """The rename case is the whole reason resolution happens at SEND time."""
    renamed = yaml.safe_load(yaml.dump(V2))
    renamed["parts"][1]["name"] = "Top"
    with pytest.raises(SelectionError):
        resolve_refs(renamed, [{"ref": "part:Upper"}])
    assert resolve_refs(renamed, [{"ref": "part:Top"}])[0]["path"] == "parts[1]"


def test_a_diagnostic_row_cannot_be_mentioned():
    broken = yaml.safe_load(yaml.dump(V2))
    broken["conditions"] = [{"name": "NoCall"}]  # a row, but a warning row
    tree = build_tree(broken)
    step_group = next(g for g in tree["groups"] if g["id"] == "steps")
    orphan = next((r for r in step_group["rows"] if r["id"] == "step:orphans"), None)
    assert orphan is not None and not orphan.get("path")
    with pytest.raises(SelectionError) as err:
        resolve_refs(broken, [{"ref": "step:orphans"}])
    assert "诊断" in str(err.value)


def test_no_spec_means_no_mentions():
    with pytest.raises(SelectionError) as err:
        resolve_refs(None, [{"ref": "part:Upper"}])
    assert "先让助手生成" in str(err.value)


def test_the_ref_count_is_capped():
    refs = [{"ref": "part:Upper"}] * 9
    with pytest.raises(SelectionError) as err:
        resolve_refs(V2, refs)
    assert "8" in str(err.value)


# ── the viewport's selector kind ────────────────────────────────────────────

def test_a_viewport_selector_is_validated_by_the_build_parser():
    got = resolve_refs(V2, [{"kind": "selector",
                             "selector": "U:face@box=0,0,10,100,50,10",
                             "note": "命中 1 个面"}])[0]
    assert got["kind"] == "selector"
    assert got["instance"] == "U"


def test_a_selector_the_build_would_refuse_is_refused_here():
    with pytest.raises(SelectionError) as err:
        resolve_refs(V2, [{"kind": "selector",
                           "selector": "U:face@box=1,2,3"}])  # three numbers
    assert "box" in str(err.value)


# ── the prompt section ──────────────────────────────────────────────────────

def test_the_prompt_carries_fragment_and_label():
    resolved = resolve_refs(V2, [{"ref": "part:Upper"},
                                 {"kind": "selector",
                                  "selector": "U:face@box=0,0,10,100,50,10",
                                  "note": "命中 1 个面，包围盒实测"}])
    section = prompt_section(resolved)
    assert "@Upper" in section
    assert "parts[1]" in section
    assert "name: Upper" in section
    assert "U:face@box=0,0,10,100,50,10" in section
    assert "命中 1 个面" in section
    assert "不要改写它的数字" in section


def test_no_selection_leaves_the_prompt_exactly_as_it_was():
    """Byte-for-byte: the feature must not perturb every existing prompt."""
    with_none = planner.build_prompt("加个孔", None, [])
    with_empty = planner.build_prompt("加个孔", None, [], selection=[])
    assert with_none == with_empty
    assert "用户选中" not in with_none


def test_the_selection_section_sits_before_the_instruction():
    resolved = resolve_refs(V2, [{"ref": "part:Upper"}])
    prompt = planner.build_prompt("把它加厚", yaml.dump(V2), [], resolved)
    assert "## 用户选中" in prompt
    assert prompt.index("## 用户选中") < prompt.index("## 用户指令")
    assert "name: Upper" in prompt


def test_a_fragment_with_braces_cannot_break_the_template():
    spec = yaml.safe_load(yaml.dump(V2))
    spec["parts"][0]["features"].append(
        {"call": "Set", "name": {"literal": "X{0}"},
         "faces": {"select": "face@all"}})
    resolved = resolve_refs(spec, [{"ref": "part:Lower"}])
    prompt = planner.build_prompt("改它", yaml.dump(spec), [], resolved)
    assert "X{0}" in prompt


def test_an_oversized_fragment_says_it_was_truncated():
    spec = yaml.safe_load(yaml.dump(V2))
    spec["parts"][0]["features"] = [
        {"op": "sketch", "id": "s%d" % i, "plane": "XY",
         "profile": {"rect": {"corner1": [0, 0], "corner2": [i + 1, 1]}}}
        for i in range(120)
    ]
    got = resolve_refs(spec, [{"ref": "part:Lower"}])[0]
    assert "已截断" in got["fragment"]
