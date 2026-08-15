"""Placing an instance where the assembly actually put it.

Before this, post/parse_inp.py refused any deck whose *Instance carried a data
row, because it read every coordinate flat and would otherwise have stacked
both instances on top of each other. Refusing beat drawing a wrong model — but
it meant the 3D preview was blank for every assembly, which is the headline
feature.

The rule being pinned here is the composition order, and it was measured rather
than assumed:

    rotate-then-translate   max node error = 2.0e+01
    translate-then-rotate   max node error = 5.1e-08

against coordinates Abaqus CAE itself reported for a probe instance translated
(20, 0, 0) and turned 90 degrees about Z. The wrong order agrees with the right
one whenever the translation runs parallel to the rotation axis, which covers
most real assemblies — so it would have shipped, looked correct everywhere
anyone checked, and misplaced a part the first time someone rotated about an
offset axis.

Hermetic: the fixtures are a real .inp Abaqus wrote and a JSON of the
coordinates CAE reported for it. Nothing here starts a solver.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from post.parse_inp import (  # noqa: E402
    _rotate_point,
    parse_inp,
    parts_from_instance_dump,
    place_nodes,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"
ROTATED_INP = FIXTURES / "assembly_rotated.inp"
CAE_NODES = FIXTURES / "assembly_rotated_cae_nodes.json"

# CAE wrote the probe's angle as 89.9999992730282 degrees and its axis endpoint
# as 1.00000001268805, so its own round trip costs ~5e-8. Anything at that
# scale is Abaqus rounding; anything larger is us.
CAE_ROUNDTRIP_TOL = 1e-6


@pytest.fixture(scope="module")
def cae_truth() -> dict:
    data = json.loads(CAE_NODES.read_text(encoding="utf-8"))
    return {name: {int(n[0]): (n[1], n[2], n[3]) for n in nodes}
            for name, nodes in data["instances"].items()}


# ---------------------------------------------------------------------------
# The rotation itself
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("point,a,b,deg,want", [
    ((1, 0, 0), (0, 0, 0), (0, 0, 1), 90, (0, 1, 0)),
    ((1, 0, 0), (0, 0, 0), (0, 0, 1), -90, (0, -1, 0)),
    ((1, 0, 0), (0, 0, 0), (0, 0, 1), 180, (-1, 0, 0)),
    ((0, 1, 0), (0, 0, 0), (1, 0, 0), 90, (0, 0, 1)),
    # About an axis that misses the origin: the offset is the whole point.
    ((11, 0, 0), (10, 0, 0), (10, 0, 1), 90, (10, 1, 0)),
    # A degenerate axis must not divide by zero; leaving the point alone is
    # the only answer that cannot be wrong.
    ((3, 4, 5), (1, 1, 1), (1, 1, 1), 90, (3, 4, 5)),
])
def test_rodrigues_rotation(point, a, b, deg, want):
    got = _rotate_point(point, a, b, deg)
    assert got == pytest.approx(want, abs=1e-12)


def test_translation_is_applied_before_rotation():
    """Hand-checkable, and the two orders are nowhere near each other.

    Local (1,0,0), translate (10,0,0), then 90 degrees about Z through (10,0,0):
      translate first -> (11,0,0), offset (1,0,0), turned (0,1) -> (10,1,0)
      rotate first    -> offset (-9,0,0), turned (0,-9) -> (10,-9,0), +t -> (20,-9,0)
    """
    placed = place_nodes({1: (1.0, 0.0, 0.0)},
                         translate=(10.0, 0.0, 0.0),
                         rotate=(10.0, 0.0, 0.0, 10.0, 0.0, 1.0, 90.0))
    assert placed[1] == pytest.approx((10.0, 1.0, 0.0), abs=1e-12)


def test_no_placement_data_leaves_coordinates_alone():
    local = {1: (1.0, 2.0, 3.0)}
    assert place_nodes(local, None, None) == local
    assert place_nodes(local, None, None) is not local, "must not alias the input"


# ---------------------------------------------------------------------------
# Against what CAE actually reported
# ---------------------------------------------------------------------------

def test_the_parser_reproduces_caes_own_coordinates(cae_truth):
    """The load-bearing test. Expected values come from CAE, not from us."""
    result = parse_inp(ROTATED_INP)
    assert result["parse_ok"], result["problems"]

    by_instance = {p["instance"]: p for p in result["parts"]}
    assert set(by_instance) == set(cae_truth)

    for name, truth in cae_truth.items():
        drawn = by_instance[name]["nodes"]
        # build_surface renumbers, so compare the point CLOUD rather than
        # trying to match label order.
        got = sorted(zip(drawn[0::3], drawn[1::3], drawn[2::3]))
        want = sorted(truth.values())
        assert len(got) == len(want), name
        for g, w in zip(got, want):
            assert g == pytest.approx(w, abs=CAE_ROUNDTRIP_TOL), name


def test_the_rotated_instance_really_did_move(cae_truth):
    """Guard the guard: a no-op transform would pass the test above trivially
    if the fixture happened to be identity."""
    plain = sorted(cae_truth["Plain"].values())
    moved = sorted(cae_truth["Moved"].values())
    assert plain != moved
    assert max(p[0] for p in plain) == pytest.approx(4.0, abs=1e-6)
    assert max(p[0] for p in moved) == pytest.approx(0.0, abs=1e-6), (
        "a 90-degree turn should have swung the bar off the +X axis")


# ---------------------------------------------------------------------------
# The two producers of this format must agree
# ---------------------------------------------------------------------------

def test_both_producers_agree_on_the_same_deck(cae_truth):
    """parse_inp (text) and parts_from_instance_dump (CAE) are two answers to
    one question. They ship together, so they are held together."""
    dump = {
        "format": "abaqus-agent-preview/instances",
        "space": "assembly",
        "truncated": False,
        "instances": [],
    }
    # Rebuild the dump payload from the CAE ground truth plus the fixture's
    # own connectivity, so this compares the PLACEMENT paths and nothing else.
    text_result = parse_inp(ROTATED_INP)
    connectivity = _fixture_connectivity()
    for name, truth in cae_truth.items():
        dump["instances"].append({
            "name": name, "part": "Bar",
            "nodes": [[lbl, x, y, z] for lbl, (x, y, z) in sorted(truth.items())],
            "elements": connectivity,
        })

    dump_result = parts_from_instance_dump(dump)
    assert dump_result["parse_ok"], dump_result["problems"]
    assert dump_result["part_count"] == text_result["part_count"]
    assert dump_result["node_count"] == text_result["node_count"]
    assert dump_result["element_count"] == text_result["element_count"]

    text_parts = {p["instance"]: p for p in text_result["parts"]}
    dump_parts = {p["instance"]: p for p in dump_result["parts"]}
    for name in text_parts:
        a, b = text_parts[name]["nodes"], dump_parts[name]["nodes"]
        assert len(a) == len(b), name
        for x, y in zip(a, b):
            assert x == pytest.approx(y, abs=CAE_ROUNDTRIP_TOL), name


def _fixture_connectivity():
    """The element rows of the fixture's single *Part, as (type, [labels])."""
    rows = []
    lines = ROTATED_INP.read_text(encoding="utf-8").splitlines()
    inside = False
    el_type = ""
    for line in lines:
        stripped = line.strip()
        if stripped.lower().startswith("*element"):
            inside = True
            el_type = stripped.split("type=")[-1].split(",")[0].strip()
            continue
        if inside:
            if stripped.startswith("*"):
                break
            rows.append([el_type, [int(c) for c in stripped.split(",")[1:] if c.strip()]])
    return rows


# ---------------------------------------------------------------------------
# Node counting across instances of one part
# ---------------------------------------------------------------------------

def test_instances_of_one_part_do_not_share_a_node_budget(cae_truth):
    """Node labels are LOCAL to a part, so both instances number from 1.

    Counting them in one global set reports a two-body assembly as having half
    the nodes it has — a number the user reads off the model tree.
    """
    result = parse_inp(ROTATED_INP)
    per_instance = sum(len(v) for v in cae_truth.values())
    assert result["node_count"] == per_instance
    assert len(cae_truth["Plain"]) == len(cae_truth["Moved"])
    assert result["node_count"] == 2 * len(cae_truth["Plain"])


# ---------------------------------------------------------------------------
# Refusals that survive
# ---------------------------------------------------------------------------

def test_an_instance_of_a_missing_part_is_refused(tmp_path):
    deck = tmp_path / "broken.inp"
    deck.write_text(ROTATED_INP.read_text(encoding="utf-8")
                    .replace("part=Bar\n*End Instance", "part=Ghost\n*End Instance", 1),
                    encoding="utf-8")
    result = parse_inp(deck)
    assert not result["parse_ok"]
    assert result["parts"] == [], "a refusal must withhold the geometry too"
    assert any("Ghost" in p for p in result["problems"]), result["problems"]


def test_parts_with_no_instances_are_refused(tmp_path):
    text = ROTATED_INP.read_text(encoding="utf-8")
    start = text.index("*Assembly")
    deck = tmp_path / "no_assembly.inp"
    deck.write_text(text[:start], encoding="utf-8")
    result = parse_inp(deck)
    assert not result["parse_ok"]
    assert result["parts"] == []
    assert any("*Instance" in p for p in result["problems"]), result["problems"]


def test_an_orphan_mesh_inside_an_instance_is_refused(tmp_path):
    """Nodes declared on the instance are numbered in assembly space already.

    Mixing them with part-local numbering picks the wrong nodes silently, so
    this stays a refusal until it is built and verified.
    """
    text = ROTATED_INP.read_text(encoding="utf-8").replace(
        "*Instance, name=Plain, part=Bar\n",
        "*Instance, name=Plain, part=Bar\n*Node\n9001, 0., 0., 0.\n", 1)
    deck = tmp_path / "orphan.inp"
    deck.write_text(text, encoding="utf-8")
    result = parse_inp(deck)
    assert not result["parse_ok"]
    assert any("孤立网格" in p for p in result["problems"]), result["problems"]


def test_a_truncated_dump_is_reported_rather_than_half_drawn():
    result = parts_from_instance_dump({
        "format": "abaqus-agent-preview/instances",
        "truncated": True, "element_cap": 200000, "instances": []})
    assert not result["parse_ok"]
    assert result["parts"] == []
    assert any("上限" in p for p in result["problems"]), result["problems"]
