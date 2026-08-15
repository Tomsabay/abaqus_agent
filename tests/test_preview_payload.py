"""The preview payload has to carry the ASSEMBLY, not just the triangles.

Before this, preview_mesh.json held parts[] and nothing else, so the front end
could colour bodies and do nothing else with them: no model tree, and no way to
show which two faces a tie or a contact pair actually joined. That is the one
thing about an assembly a picture cannot show — a pair 0.05 apart with a 0.01
position tolerance draws exactly like a pair that bound, writes a real *Tie
card, and COMPLETES SUCCESSFULLY at 7.95x the right deflection.

Hermetic: every dump here is hand-built. Nothing starts Abaqus, and the CAE
side of the dump (runner/build_v2.py) is only checked for the part that is
pure — the region names it re-derives from the spec, against the names the
generated deck really passes to _gsurface / _gset.
"""

from __future__ import annotations

import copy
import os
import re
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from post import parse_inp as parse_inp_mod  # noqa: E402
from post.parse_inp import parts_from_instance_dump  # noqa: E402
from runner import build_v2  # noqa: E402
from runner import kernel_runtime
from runner import preview

# One unit hex, corners 1-8: bottom face 1-2-3-4, top face 5-6-7-8.
HEX = (1, 2, 3, 4, 5, 6, 7, 8)


def _hex_instance(name, z0):
    """A single-element instance sitting between z0 and z0+1."""
    nodes = []
    for label, (x, y) in enumerate([(0, 0), (1, 0), (1, 1), (0, 1)], start=1):
        nodes.append([label, float(x), float(y), float(z0)])
        nodes.append([label + 4, float(x), float(y), float(z0 + 1)])
    return {"name": name, "part": "Half",
            "nodes": sorted(nodes), "elements": [["C3D8", list(HEX)]]}


def _dump():
    """Two stacked hexes tied at z=1, in the new assembly-carrying format."""
    return {
        "format": "abaqus-agent-preview/instances",
        "assembly_dump": 1,
        "space": "assembly",
        "truncated": False,
        "instances": [_hex_instance("Lower", 0.0), _hex_instance("Upper", 1.0)],
        "surfaces": [
            # Lower's top face and Upper's bottom face: the tied pair.
            {"name": "MIDPLANE_MAIN", "instance": "Lower",
             "node_labels": [5, 6, 7, 8], "node_total": 4, "capped": False},
            {"name": "MIDPLANE_SEC", "instance": "Upper",
             "node_labels": [1, 2, 3, 4], "node_total": 4, "capped": False},
        ],
        "sets": [
            {"name": "BC_FIXLOWER", "instance": "Lower",
             "node_labels": [1, 2, 3, 4], "node_total": 4, "capped": False},
        ],
        "interactions": [
            {"name": "MidPlane", "kind": "tie", "call": "Tie",
             "surfaces": ["MIDPLANE_MAIN", "MIDPLANE_SEC"],
             "gap": 0.0, "gap_nodes": [4, 4]},
        ],
        "conditions": [
            {"name": "FixLower", "call": "EncastreBC", "step": "Initial",
             "sets": ["BC_FIXLOWER"], "surfaces": []},
        ],
        "sections": [
            {"instance": "Lower", "part": "Half",
             "sections": ["SEC_STEEL"], "materials": ["Steel"]},
            {"instance": "Upper", "part": "Half",
             "sections": ["SEC_STEEL"], "materials": ["Steel"]},
        ],
        "degraded": [],
    }


def _by_name(rows):
    return {row["name"]: row for row in rows}


def _coords(part, index):
    return tuple(part["nodes"][index * 3:index * 3 + 3])


# ---------------------------------------------------------------------------
# The overlay the viewport draws
# ---------------------------------------------------------------------------

def test_named_surface_arrives_as_facets_the_viewport_can_draw():
    """Indices into parts[i]['nodes'], not labels and not a second node array.

    Checked by reading the coordinates back: every node of every facet of the
    tied pair must sit on z=1, which is the only plane those two surfaces are
    on. An index space that was off by anything at all fails here.
    """
    data = parts_from_instance_dump(_dump())
    parts = data["parts"]
    surfaces = _by_name(data["assembly"]["surfaces"])

    for name in ("MIDPLANE_MAIN", "MIDPLANE_SEC"):
        surface = surfaces[name]
        assert surface["parts"], "%s produced no facets at all" % name
        drawn = 0
        for member in surface["parts"]:
            part = parts[member["part"]]
            assert member["facet_count"] * 3 == len(member["facets"])
            for index in member["facets"]:
                assert index < part["node_count"]
                assert _coords(part, index)[2] == pytest.approx(1.0), (
                    "%s highlighted a node off the tie plane" % name)
            drawn += member["facet_count"]
        # One quad face of one hex triangulates to exactly two triangles.
        assert drawn == 2, name


def test_named_set_arrives_as_node_indices():
    data = parts_from_instance_dump(_dump())
    parts = data["parts"]
    fix = _by_name(data["assembly"]["sets"])["BC_FIXLOWER"]

    assert fix["instance"] == "Lower"
    assert fix["node_count"] == 4
    found = []
    for member in fix["parts"]:
        part = parts[member["part"]]
        for index in member["nodes"]:
            found.append(_coords(part, index))
    assert len(found) == 4
    assert all(point[2] == pytest.approx(0.0) for point in found), (
        "the encastre set is the bottom face; z=0 for all four corners")


def test_interaction_row_carries_the_pair_and_the_measured_gap():
    data = parts_from_instance_dump(_dump())
    row = _by_name(data["assembly"]["interactions"])["MidPlane"]

    assert row["kind"] == "tie"
    assert row["call"] == "Tie"
    assert row["surfaces"] == ["MIDPLANE_MAIN", "MIDPLANE_SEC"]
    # 0.0 is a measurement and None is the absence of one. They are not the
    # same fact and must not collapse into each other.
    assert row["gap"] == 0.0
    assert row["gap"] is not None
    assert row["gap_nodes"] == [4, 4]


def test_gap_is_carried_through_untouched_even_when_it_is_a_loose_bound():
    """The number is an upper bound, not the separation, and it is not rounded
    or clamped on the way out.

    Real figures from cases/bearing_block's dump: BoreTie joins
    Housing:face@r=12 to Bushing:face@r=12 -- the same cylinder -- under a
    position tolerance of 0.05, and reads 2.389 because _surface_gap is
    node-to-node and the two sides carry 418 and 1628 nodes. Rounding that
    towards zero to make it look right would be inventing a measurement; the
    caller has to be told it is a bound instead.
    """
    raw = _dump()
    raw["interactions"][0]["gap"] = 2.389394354835365
    raw["interactions"][0]["gap_nodes"] = [418, 1628]

    row = parts_from_instance_dump(raw)["assembly"]["interactions"][0]
    assert row["gap"] == 2.389394354835365
    assert row["gap_nodes"] == [418, 1628]


def test_unmeasured_gap_stays_none_rather_than_reading_as_zero():
    raw = _dump()
    raw["interactions"][0]["gap"] = None
    raw["interactions"][0]["gap_nodes"] = None

    row = parts_from_instance_dump(raw)["assembly"]["interactions"][0]
    assert row["gap"] is None
    assert row["gap_nodes"] is None


def test_condition_row_carries_call_step_and_region():
    data = parts_from_instance_dump(_dump())
    row = _by_name(data["assembly"]["conditions"])["FixLower"]

    assert row["call"] == "EncastreBC"
    assert row["step"] == "Initial"
    assert row["sets"] == ["BC_FIXLOWER"]
    assert row["surfaces"] == []


def test_counts_block_carries_mesh_and_section_per_part():
    data = parts_from_instance_dump(_dump())
    counts = _by_name(data["assembly"]["counts"])

    assert set(counts) == {"Lower", "Upper"}
    for name, row in counts.items():
        assert row["nodes"] == 8
        assert row["elements"] == 1
        assert row["element_type"] == "C3D8"
        assert row["abaqus_part"] == "Half"
        assert row["sections"] == ["SEC_STEEL"]
        assert row["materials"] == ["Steel"]
        # The index the tree clicks through to, into the parts[] it already has.
        assert data["parts"][row["part"]]["name"] == name


def _quadratic_dump():
    """One C3D20R element, which has 20 nodes and renders 8 of them.

    post/export_odb_mesh.element_faces builds its faces from CORNER nodes only
    ("midside ignored"), so build_surface never emits the twelve midside nodes
    and parts[]['node_count'] comes back 8. A model tree taking its node figure
    from there reports 8 nodes carrying 1 element, for a part Abaqus would
    report 20 nodes for. Same shape as the C3D20R decks this repo ships, where
    the ratio measured on their cached preview_raw.json is 498 of 2117.
    """
    corners = [(0, 0, 0), (2, 0, 0), (2, 2, 0), (0, 2, 0),
               (0, 0, 2), (2, 0, 2), (2, 2, 2), (0, 2, 2)]
    # Midside nodes: the four bottom edges, the four top edges, then the four
    # verticals -- the C3D20 ordering, though only the corners are read here.
    edges = [(0, 1), (1, 2), (2, 3), (3, 0),
             (4, 5), (5, 6), (6, 7), (7, 4),
             (0, 4), (1, 5), (2, 6), (3, 7)]
    nodes = [[i + 1, float(x), float(y), float(z)]
             for i, (x, y, z) in enumerate(corners)]
    for offset, (a, b) in enumerate(edges):
        mid = [(corners[a][axis] + corners[b][axis]) / 2.0 for axis in range(3)]
        nodes.append([offset + 9] + [float(v) for v in mid])
    return {
        "format": "abaqus-agent-preview/instances", "assembly_dump": 1,
        "space": "assembly", "truncated": False,
        "instances": [{"name": "Blk", "part": "Blk",
                       "nodes": nodes,
                       "elements": [["C3D20R", list(range(1, 21))]]}],
        "surfaces": [],
        # Every node of the element, which is what a.Set(cells=...) reports.
        "sets": [{"name": "REGION_ALL", "instance": "Blk",
                  "node_labels": list(range(1, 21)), "node_total": 20,
                  "capped": False}],
        "interactions": [], "conditions": [],
        "sections": [{"instance": "Blk", "part": "Blk",
                      "sections": ["S"], "materials": ["Steel"]}],
        "degraded": [],
    }


def test_counts_report_the_models_node_figure_not_the_render_one():
    """20 nodes is what the part has; 8 is how many of them get drawn."""
    data = parts_from_instance_dump(_quadratic_dump())
    row = data["assembly"]["counts"][0]

    assert data["parts"][0]["node_count"] == 8, (
        "the render figure is unchanged — parts[] is not being touched")
    assert row["nodes"] == 20
    assert row["elements"] == 1
    # And the per-part figures add up to the model total in the same payload.
    assert sum(item["nodes"] for item in data["assembly"]["counts"]) \
        == data["node_count"] == 20


def test_a_region_the_preview_can_only_partly_light_says_so():
    """A set of all 20 nodes lights the 8 corners. Silent, that reads as a
    selector that picked up a quarter of what the spec asked for."""
    data = parts_from_instance_dump(_quadratic_dump())
    region = data["assembly"]["sets"][0]

    assert region["node_count"] == 20
    assert region["drawn_nodes"] == 8
    assert any("drawn_nodes" in line for line in data["assembly"]["degraded"]), \
        data["assembly"]["degraded"]


def test_a_region_the_preview_lights_completely_is_not_complained_about():
    """The hex case: every node of every region is on the render mesh."""
    data = parts_from_instance_dump(_dump())

    for region in data["assembly"]["surfaces"] + data["assembly"]["sets"]:
        assert region["drawn_nodes"] == region["node_count"], region
    assert data["assembly"]["degraded"] == []


def test_parts_shape_the_front_end_renders_is_untouched():
    """parts[] is what ships today; the assembly block is added ALONGSIDE it."""
    data = parts_from_instance_dump(_dump())

    assert data["part_count"] == 2
    assert data["node_count"] == 16
    assert data["element_count"] == 2
    for part in data["parts"]:
        assert set(part) == {"name", "family", "element_type", "nodes", "tris",
                             "node_count", "tri_count", "element_count",
                             "color", "instance", "part"}
        assert part["tri_count"] == 12


# ---------------------------------------------------------------------------
# The old format is still on disk
# ---------------------------------------------------------------------------

def test_old_format_dump_still_renders_and_says_it_carries_no_assembly():
    """Run directories built before this key exists are regenerated without CAE
    (runner/build_model.py rebuilds preview_mesh.json from a cached
    preview_raw.json), so the old shape has to keep working. `assembly: None`
    says the dump never carried one — an empty list would claim the model has
    no surfaces, which is a different and false statement."""
    old = {"format": "abaqus-agent-preview/instances", "space": "assembly",
           "truncated": False,
           "instances": [_hex_instance("Lower", 0.0), _hex_instance("Upper", 1.0)]}

    data = parts_from_instance_dump(old)
    assert data["parse_ok"] is True, data["problems"]
    assert data["part_count"] == 2
    assert data["element_count"] == 2
    assert data["assembly"] is None


def test_format_string_names_the_new_schema():
    assert parts_from_instance_dump(_dump())["format"] == "abaqus-agent-mesh/3-assembly"


# ---------------------------------------------------------------------------
# What it could not collect, it says
# ---------------------------------------------------------------------------

def test_missing_section_is_named_in_degraded_rather_than_dropped():
    raw = _dump()
    raw["sections"] = [entry for entry in raw["sections"]
                       if entry["instance"] != "Upper"]

    data = parts_from_instance_dump(raw)
    counts = _by_name(data["assembly"]["counts"])
    assert counts["Upper"]["sections"] == []
    assert counts["Upper"]["nodes"] == 8, "the mesh figures are still known"

    degraded = data["assembly"]["degraded"]
    assert any("Upper" in line and "截面" in line for line in degraded), degraded
    assert not any("Lower" in line and "截面" in line for line in degraded), (
        "the part that DID report a section must not be complained about")


def test_section_without_a_material_is_named_too():
    raw = _dump()
    raw["sections"][0]["materials"] = []

    degraded = parts_from_instance_dump(raw)["assembly"]["degraded"]
    assert any("Lower" in line and "材料" in line for line in degraded), degraded


def test_surface_on_an_instance_with_no_mesh_is_named():
    raw = _dump()
    raw["surfaces"].append({"name": "GHOST", "instance": "Nowhere",
                            "node_labels": [1], "node_total": 1,
                            "capped": False})

    data = parts_from_instance_dump(raw)
    ghost = _by_name(data["assembly"]["surfaces"])["GHOST"]
    assert ghost["parts"] == []
    assert any("GHOST" in line for line in data["assembly"]["degraded"])


def test_interaction_naming_a_surface_the_dump_lacks_is_named():
    raw = _dump()
    raw["interactions"][0]["surfaces"] = ["MIDPLANE_MAIN", "TYPO_SEC"]

    data = parts_from_instance_dump(raw)
    row = data["assembly"]["interactions"][0]
    assert row["surfaces"] == ["MIDPLANE_MAIN"]
    assert any("TYPO_SEC" in line for line in data["assembly"]["degraded"])


def test_kernel_side_degraded_lines_survive_into_the_payload():
    raw = _dump()
    raw["degraded"] = ["集合 WHOLE 横跨多个实例，预览按单个实例画，所以不画它"]

    degraded = parts_from_instance_dump(raw)["assembly"]["degraded"]
    assert "集合 WHOLE 横跨多个实例，预览按单个实例画，所以不画它" in degraded


def test_facet_cap_reports_itself(monkeypatch):
    """A capped highlight must never read as a complete one."""
    monkeypatch.setattr(parse_inp_mod, "MAX_FACETS_PER_SURFACE", 1)

    data = parts_from_instance_dump(_dump())
    surface = _by_name(data["assembly"]["surfaces"])["MIDPLANE_MAIN"]
    assert surface["capped"] is True
    assert surface["parts"][0]["facet_count"] == 1
    assert any("MIDPLANE_MAIN" in line for line in data["assembly"]["degraded"])


def test_truncated_dump_keeps_the_tree_and_says_the_mesh_is_gone():
    """No geometry does not mean no model: the names, the pair and the gap are
    still true and are still worth showing."""
    raw = _dump()
    raw["truncated"] = True
    raw["element_cap"] = 200000
    raw["instances"] = []

    data = parts_from_instance_dump(raw)
    assert data["parse_ok"] is False
    assert data["parts"] == []
    assert data["assembly"]["interactions"][0]["gap"] == 0.0
    assert data["assembly"]["conditions"][0]["name"] == "FixLower"
    assert any("没有可渲染的网格" in line
               for line in data["assembly"]["degraded"])


# ---------------------------------------------------------------------------
# The CAE side: names re-derived from the spec must be the deck's own names
# ---------------------------------------------------------------------------

CASE = ROOT / "cases" / "two_plate_tie" / "spec.yaml"


@pytest.fixture
def spec() -> dict:
    return yaml.safe_load(CASE.read_text(encoding="utf-8"))


def _deck_regions(script: str) -> tuple:
    return (re.findall(r"_gsurface\(a, '([A-Z0-9_]+)'", script),
            re.findall(r"_gset\(a, '([A-Z0-9_]+)'", script),
            re.findall(r"a\.Surface\(name='([A-Z0-9_]+)'", script),
            re.findall(r"a\.Set\(name='([A-Z0-9_]+)'", script))


def test_shorthand_region_names_match_the_deck(spec):
    """The shipped tie case: every name the tree offers exists in the deck."""
    script = build_v2.generate_script(spec)
    gsurfaces, gsets, surfaces, sets = _deck_regions(script)
    built = set(gsurfaces) | set(gsets) | set(surfaces) | set(sets)

    facts = preview._preview_assembly_facts(spec)
    claimed = set()
    for row in facts["interactions"]:
        claimed.update(row["surfaces"])
    for row in facts["conditions"]:
        claimed.update(row["sets"])
        claimed.update(row["surfaces"])

    assert claimed, "the tie case declares regions; none were derived"
    assert claimed <= built, sorted(claimed - built)
    assert facts["degraded"] == []


def test_dispatched_region_names_match_the_deck(spec):
    """The same tie written as the Abaqus call it is, with the surface names
    left to default — which is where a re-derivation of `_arg_surface`'s naming
    rule would drift first."""
    dispatched = copy.deepcopy(spec)
    dispatched["interactions"] = [{
        "call": "Tie", "name": {"literal": "MidPlane"},
        "main": {"surface": "Lower:face@y=max"},
        "secondary": {"surface": "Upper:face@y=min"},
        "positionToleranceMethod": "SPECIFIED", "positionTolerance": 0.01,
        "adjust": "OFF", "tieRotations": "ON", "thickness": "ON",
        "expect": {"gap": {"max": 0.001}},
    }]
    script = build_v2.generate_script(dispatched)
    gsurfaces = _deck_regions(script)[0]

    row = preview._preview_assembly_facts(dispatched)["interactions"][0]
    assert row["name"] == "MidPlane"
    assert row["kind"] == "Tie"
    assert row["surfaces"] == gsurfaces
    assert len(row["surfaces"]) == 2


def test_step_shorthand_conditions_are_not_left_out(spec):
    """Every BC in every case this repo ships is written in `steps[].bcs`. Left
    out, the tree would show the tie case as having no boundary conditions."""
    facts = preview._preview_assembly_facts(spec)
    rows = _by_name(facts["conditions"])

    assert set(rows) == {"FixLower", "FixUpper", "Top"}
    assert rows["FixLower"]["call"] == "EncastreBC"
    assert rows["FixLower"]["step"] == "Initial"
    assert rows["FixLower"]["sets"] == ["BC_FIXLOWER"]
    # A pressure is applied to a SURFACE, a concentrated force to a SET.
    assert rows["Top"]["call"] == "Pressure"
    assert rows["Top"]["surfaces"] == ["LOAD_TOP"]
    assert rows["Top"]["sets"] == []


def test_a_condition_repeated_in_a_later_step_is_one_row(spec):
    """Abaqus keeps ONE object whose values change; two rows would claim two."""
    two_step = copy.deepcopy(spec)
    two_step["steps"][0]["bcs"] = [
        {"name": "Push", "region": "Upper:face@z=max", "type": "displacement",
         "u2": 0.0}]
    two_step["steps"].append({"name": "Second", "type": "Static",
                              "bcs": [{"name": "Push",
                                       "region": "Upper:face@z=max",
                                       "type": "displacement", "u2": -1.0}]})

    rows = preview._preview_assembly_facts(two_step)["conditions"]
    assert [row["name"] for row in rows].count("Push") == 1


# ---------------------------------------------------------------------------
# The CAE side, actually run
# ---------------------------------------------------------------------------
#
# The dump is a string until Abaqus executes it, and this venv is not Abaqus, so
# without these it ships unrun. Stand-ins carry only the members the dump asks
# for; they are not a model of CAE, they are what a wrong attribute name would
# fail against. What this cannot catch is a member Abaqus spells differently
# than the stand-in does — for that, the dump degrades instead of guessing, and
# the second test below is the proof that it does.

class _FakeNode:
    def __init__(self, label, xyz, instance):
        self.label = label
        self.coordinates = xyz
        if instance is not None:
            self.instanceName = instance


class _FakeElement:
    def __init__(self, el_type, connectivity):
        self.type = el_type
        self.connectivity = connectivity


class _FakeThing:
    def __init__(self, **members):
        self.__dict__.update(members)


def _fake_assembly(instance_names=True):
    """Two unit hexes stacked at z=1, tied across the shared plane."""
    instances = {}
    for name, z0 in (("Lower", 0.0), ("Upper", 1.0)):
        nodes = []
        for level, z in ((0, z0), (4, z0 + 1.0)):
            for i, (x, y) in enumerate([(0, 0), (1, 0), (1, 1), (0, 1)]):
                nodes.append(_FakeNode(level + i + 1, (float(x), float(y), z),
                                       name if instance_names else None))
        instances[name] = _FakeThing(
            partName="Half", nodes=nodes,
            elements=[_FakeElement("C3D8", list(range(8)))])
    lower, upper = instances["Lower"], instances["Upper"]
    assembly = _FakeThing(
        instances=instances,
        surfaces={"MIDPLANE_MAIN": _FakeThing(nodes=lower.nodes[4:8]),
                  "MIDPLANE_SEC": _FakeThing(nodes=upper.nodes[0:4]),
                  "LOAD_TOP": _FakeThing(nodes=upper.nodes[4:8])},
        sets={"BC_FIXLOWER": _FakeThing(nodes=lower.nodes[0:4]),
              "BC_FIXUPPER": _FakeThing(nodes=upper.nodes[0:4])})
    model = _FakeThing(
        parts={"Half": _FakeThing(
            sectionAssignments=[_FakeThing(sectionName="SEC_STEEL")])},
        sections={"SEC_STEEL": _FakeThing(material="Steel")})
    return assembly, model


class _NoNodes:
    """A region that will not answer — the failure the dump must survive."""

    @property
    def nodes(self):
        raise AttributeError("nodes")


def _run_emitted_dump(spec, workdir, instance_names=True, mutate=None):
    """Execute the dump the deck carries, and read back what it wrote."""
    import json

    script = build_v2.generate_script(spec)
    region = script[script.index("# --- Preview dump"):
                    script.index("# --- Write the job")]
    # The real gap routine, lifted out of the helper block the same deck
    # carries, so the number in the payload is the measurement and not a stub.
    helpers = kernel_runtime._HELPERS
    start = helpers.index("def _surface_gap(a,")
    gap_source = helpers[start:helpers.index("\ndef ", start)]

    assembly, model = _fake_assembly(instance_names)
    if mutate is not None:
        mutate(assembly, model)
    namespace = {"os": os, "workdir": str(workdir), "a": assembly, "m": model}
    exec(compile(gap_source, "<helpers>", "exec"), namespace)
    exec(compile(region, "<preview_dump>", "exec"), namespace)
    return json.loads((Path(workdir) / "preview_raw.json").read_text(
        encoding="utf-8"))


def test_emitted_dump_runs_and_carries_the_assembly(spec, tmp_path):
    raw = _run_emitted_dump(spec, tmp_path)

    assert raw["format"] == "abaqus-agent-preview/instances", (
        "runner/build_model.py routes this file on an exact string match")
    assert raw["assembly_dump"] == 1
    assert raw["degraded"] == []

    surfaces = _by_name(raw["surfaces"])
    assert surfaces["MIDPLANE_MAIN"]["instance"] == "Lower"
    assert surfaces["MIDPLANE_MAIN"]["node_labels"] == [5, 6, 7, 8]
    assert surfaces["MIDPLANE_SEC"]["instance"] == "Upper"
    assert _by_name(raw["sets"])["BC_FIXLOWER"]["node_labels"] == [1, 2, 3, 4]

    tie = raw["interactions"][0]
    assert tie["surfaces"] == ["MIDPLANE_MAIN", "MIDPLANE_SEC"]
    assert tie["gap"] == pytest.approx(0.0), "the two faces are coincident"
    assert tie["gap_nodes"] == [4, 4]
    assert _by_name(raw["conditions"])["Top"]["surfaces"] == ["LOAD_TOP"]
    assert raw["sections"][0]["sections"] == ["SEC_STEEL"]
    assert raw["sections"][0]["materials"] == ["Steel"]

    # And the whole way through to what the viewport gets.
    mesh = parts_from_instance_dump(raw)
    assert mesh["part_count"] == 2
    assert _by_name(mesh["assembly"]["surfaces"])["MIDPLANE_MAIN"]["parts"]


def test_emitted_dump_refuses_to_guess_an_owner_it_cannot_read(spec, tmp_path):
    """A node that will not say which instance it is on is the case that has to
    degrade rather than pick one. Two instances of one part both number their
    nodes from 1, so the label fallback finds two candidates and must refuse:
    a highlight on the wrong plate is worse than no highlight."""
    raw = _run_emitted_dump(spec, tmp_path, instance_names=False)

    for entry in raw["surfaces"] + raw["sets"]:
        assert entry["instance"] == "", entry
    assert len(raw["degraded"]) == len(raw["surfaces"]) + len(raw["sets"])
    assert all("认不出属于哪个实例" in line for line in raw["degraded"])
    # Names, calls and the measured gap are unaffected: what could be collected
    # still is.
    assert raw["interactions"][0]["gap"] == pytest.approx(0.0)


def test_an_unmeshed_region_says_so_rather_than_reading_as_empty(spec, tmp_path):
    """A surface with no nodes is a real state — a part that has not been
    meshed gives exactly this — and it is not the same fact as a surface that
    could not be attributed to an instance."""
    def mutate(assembly, model):
        assembly.surfaces["NOT_MESHED"] = _FakeThing(nodes=[])

    raw = _run_emitted_dump(spec, tmp_path, mutate=mutate)
    entry = _by_name(raw["surfaces"])["NOT_MESHED"]
    assert entry["node_labels"] == []
    assert entry["instance"] == ""
    assert any("NOT_MESHED" in line and "一个节点都没有" in line
               for line in raw["degraded"]), raw["degraded"]


def test_a_region_that_will_not_answer_is_named_and_the_rest_survives(spec, tmp_path):
    def mutate(assembly, model):
        assembly.sets["BROKEN"] = _NoNodes()

    raw = _run_emitted_dump(spec, tmp_path, mutate=mutate)
    assert "BROKEN" not in _by_name(raw["sets"])
    assert any("BROKEN" in line for line in raw["degraded"]), raw["degraded"]
    # Everything that could be collected still was.
    assert _by_name(raw["sets"])["BC_FIXLOWER"]["instance"] == "Lower"
    assert raw["interactions"][0]["gap"] == pytest.approx(0.0)


def test_region_count_cap_reports_itself(spec, tmp_path):
    def mutate(assembly, model):
        spare = assembly.instances["Lower"].nodes[0:1]
        for i in range(preview.PREVIEW_REGION_CAP + 5):
            assembly.sets["FILLER_%03d" % i] = _FakeThing(nodes=spare)

    raw = _run_emitted_dump(spec, tmp_path, mutate=mutate)
    assert len(raw["sets"]) == preview.PREVIEW_REGION_CAP
    assert any("预览只收了前" in line for line in raw["degraded"])


def test_a_missing_section_degrades_without_losing_the_rest(spec, tmp_path):
    def mutate(assembly, model):
        del model.parts["Half"]

    raw = _run_emitted_dump(spec, tmp_path, mutate=mutate)
    assert [row["sections"] for row in raw["sections"]] == [[], []]
    assert len([line for line in raw["degraded"] if "截面" in line]) == 2
    assert raw["instances"][0]["elements"], "the mesh is untouched by this"


def test_the_dump_is_valid_python_for_the_27_kernel(spec):
    """The generated text runs in Abaqus's own interpreter, which this venv is
    not. Syntax is all that can be checked here; the py2-only constructs are
    kept out by hand."""
    import ast

    script = build_v2.generate_script(spec)
    ast.parse(script)
    region = script[script.index("# --- Preview dump"):]
    # An f-string and an annotation are syntax errors in 2.7; `d.keys()[0]` is
    # a TypeError in 3.x. All three read as fine to this venv's compiler.
    for banned in (r"\bf['\"]", r"\)\s*->", r"\.keys\(\)\[", r"\bpathlib\b"):
        assert not re.search(banned, region), banned


# ---------------------------------------------------------------------------
# Geometric faces: the viewport's face-level pick (#79)
# ---------------------------------------------------------------------------

class _FakeFace:
    """One CAE face, probed the way the dump probes: raising IS the answer."""

    def __init__(self, nodes, normal=None, radius=None, area=None,
                 broken=False):
        self._nodes = nodes
        self._normal = normal
        self._radius = radius
        self._area = area
        self._broken = broken

    def getNodes(self):
        if self._broken:
            raise RuntimeError("face cannot answer")
        return self._nodes

    def getRadius(self):
        if self._radius is None:
            raise RuntimeError("Face is not cylindrical")
        return self._radius

    def getNormal(self):
        if self._normal is None:
            raise RuntimeError("not planar")
        return self._normal

    def getSize(self, printResults=True):
        if self._area is None:
            raise RuntimeError("no size")
        return self._area


class _FakeFaceSeq:
    """Indexing gives a face; slicing gives the thing getBoundingBox lives on,
    the same split the real FaceArray has."""

    def __init__(self, faces):
        self._faces = faces

    def __len__(self):
        return len(self._faces)

    def __getitem__(self, key):
        if isinstance(key, slice):
            return _FakeFaceSlice(self._faces[key])
        return self._faces[key]


class _FakeFaceSlice:
    def getBoundingBox(self):
        coords = [n.coordinates for f in self._faces for n in f._nodes]
        return {"low": tuple(min(c[i] for c in coords) for i in range(3)),
                "high": tuple(max(c[i] for c in coords) for i in range(3))}

    def __init__(self, faces):
        self._faces = faces


def test_emitted_dump_measures_geometric_faces(spec, tmp_path):
    """The CAE-side string really collects bbox/normal/radius per face."""
    def mutate(assembly, model):
        lower = assembly.instances["Lower"]
        lower.faces = _FakeFaceSeq([
            _FakeFace(lower.nodes[4:8], normal=(0.0, 0.0, 1.0), area=1.0),
            _FakeFace(lower.nodes[0:4], radius=12.0),
        ])

    raw = _run_emitted_dump(spec, tmp_path, mutate=mutate)
    lower_row = next(r for r in raw["instances"] if r["name"] == "Lower")
    upper_row = next(r for r in raw["instances"] if r["name"] == "Upper")
    assert upper_row["faces"] == [], "no faces attribute -> no rows, no crash"

    faces = lower_row["faces"]
    assert [f["face"] for f in faces] == [0, 1]
    top = faces[0]
    assert top["node_labels"] == [5, 6, 7, 8]
    assert top["bbox"] == [[0.0, 0.0, 1.0], [1.0, 1.0, 1.0]]
    assert top["normal"] == [0.0, 0.0, 1.0]
    assert top["area"] == 1.0
    assert "radius" not in top, "getRadius raised, so the face has none"
    bore = faces[1]
    assert bore["radius"] == 12.0
    assert "normal" not in bore
    assert lower_row["faces_dropped"] == 0


def test_a_face_that_cannot_answer_is_dropped_and_counted(spec, tmp_path):
    def mutate(assembly, model):
        lower = assembly.instances["Lower"]
        lower.faces = _FakeFaceSeq([
            _FakeFace(None, broken=True),
            _FakeFace(lower.nodes[4:8], normal=(0.0, 0.0, 1.0)),
        ])

    raw = _run_emitted_dump(spec, tmp_path, mutate=mutate)
    lower_row = next(r for r in raw["instances"] if r["name"] == "Lower")
    assert [f["face"] for f in lower_row["faces"]] == [1]
    assert lower_row["faces_dropped"] == 1


def _lower_top_face_dump():
    """The JSON-level dump with Lower's top face as a geometric face."""
    raw = _dump()
    raw["instances"][0]["faces"] = [
        {"face": 5, "node_labels": [5, 6, 7, 8], "node_total": 4,
         "capped": False, "bbox": [[0.0, 0.0, 1.0], [1.0, 1.0, 1.0]],
         "normal": [0.0, 0.0, 1.0], "area": 1.0},
    ]
    raw["instances"][0]["faces_dropped"] = 0
    return raw


def test_pick_faces_map_to_the_triangles_of_their_face():
    """tri INDICES into the part's own tris — the number a raycast hit carries.

    Verified by reading coordinates back: every corner of every mapped
    triangle must sit at z=1, the plane the face is on, and the top face of a
    hex is exactly two exterior triangles.
    """
    data = parts_from_instance_dump(_lower_top_face_dump())
    picks = data["assembly"]["pick_faces"]
    assert len(picks) == 1
    pick = picks[0]
    assert pick["instance"] == "Lower"
    assert pick["face"] == 5
    assert pick["bbox"] == [[0.0, 0.0, 1.0], [1.0, 1.0, 1.0]]
    assert pick["normal"] == [0.0, 0.0, 1.0]

    assert len(pick["parts"]) == 1
    entry = pick["parts"][0]
    part = data["parts"][entry["part"]]
    assert part["instance"] == "Lower"
    assert len(entry["tris"]) == 2
    for tri in entry["tris"]:
        for corner in part["tris"][tri * 3:tri * 3 + 3]:
            assert _coords(part, corner)[2] == pytest.approx(1.0)


def test_a_face_without_a_bbox_cannot_be_picked_and_says_so():
    raw = _lower_top_face_dump()
    del raw["instances"][0]["faces"][0]["bbox"]

    data = parts_from_instance_dump(raw)
    assert data["assembly"]["pick_faces"] == []
    assert any("点不中" in line for line in data["assembly"]["degraded"])


def test_dump_reported_dropped_faces_surface_in_degraded():
    raw = _lower_top_face_dump()
    raw["instances"][0]["faces_dropped"] = 3

    degraded = parts_from_instance_dump(raw)["assembly"]["degraded"]
    assert any("3 个几何面" in line and "Lower" in line for line in degraded)


def test_old_dumps_without_faces_have_no_pick_faces():
    data = parts_from_instance_dump(_dump())
    assert data["assembly"]["pick_faces"] == []
    assert not any("几何面" in line for line in data["assembly"]["degraded"])
