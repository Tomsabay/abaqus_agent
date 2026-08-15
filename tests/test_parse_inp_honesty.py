"""post/parse_inp.py must render the model, a refusal, or a warned partial —
never a silently wrong or silently empty preview.

The defect this pins (P2-d #2): five of this repo's own ten solver decks
previewed as an empty model. CAE writes C3D20R connectivity (21 numbers)
across two physical lines with a trailing comma; the parser read the halves
as two garbage rows, build_surface threw, ``except Exception: continue``
swallowed it, and the workbench showed "0 part · 0 节点 · 0 单元" over a
blank viewport with SUCCESS chrome around it.

Structural refusals matter more than the join itself: a multi-*Part deck or
a translated *Instance would not render EMPTY — they would render WRONG
(parts stacked at local coordinates), which a user has no way to notice.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from post.parse_inp import parse_inp, write_parts_mesh

ROOT = Path(__file__).resolve().parent.parent
# A real CAE-written continuation-line deck, in the frozen evidence dir. That
# directory is gitignored, so it is absent on a fresh clone — the tests below
# must not depend on it or `pytest` fails for every new contributor on the
# README's very first command.
CANTILEVER_INP = ROOT / "cases" / "cantilever" / "runs" / "dd6ec1145b8de62f" / "Cantilever.inp"
needs_frozen_deck = pytest.mark.skipif(
    not CANTILEVER_INP.is_file(),
    reason="frozen run dir absent (cases/*/runs/ is gitignored)",
)

# The same shape CAE emits, written out here so the defect stays pinned on any
# checkout: a C3D20R element is 21 numbers (label + 20 nodes) split across two
# physical lines, the first ending in a comma. Reading the halves as two rows
# is what produced "0 part · 0 节点" under SUCCESS chrome.
CONTINUATION_DECK = """*Heading
** synthetic C3D20R deck - continuation lines exactly as CAE writes them
*Node
""" + "".join(
    " %d, %f, %f, %f\n" % (
        i + 1,
        float(i % 3), float((i // 3) % 3), float(i // 9),
    )
    for i in range(27)
) + """*Element, type=C3D20R, elset=BLOCK
 1,  1,  3,  9,  7, 19, 21, 27, 25,  2,  6,  8,  4, 20, 24, 26,
 22, 10, 12, 18, 16
"""


def _write_continuation_deck(tmp_path: Path) -> Path:
    deck = tmp_path / "continuation.inp"
    deck.write_text(CONTINUATION_DECK, encoding="utf-8")
    return deck


def test_continuation_line_element_is_reassembled(tmp_path):
    """Self-contained twin of the frozen-deck test: runs on a fresh clone."""
    data = parse_inp(_write_continuation_deck(tmp_path))

    assert data["parse_ok"] is True, data["problems"]
    assert data["part_count"] == 1
    assert data["element_count"] == 1, (
        "the two physical lines of one C3D20R must join into ONE element, "
        "not read as two garbage rows")
    # node_count is nodes actually referenced, not nodes defined: all 20 of
    # the element's entries resolved, across the line break.
    assert data["node_count"] == 20
    # The surface only extracts if the full connectivity survived the join.
    assert data["render_triangle_count"] > 0


@needs_frozen_deck
def test_continuation_line_deck_is_not_an_empty_success():
    data = parse_inp(CANTILEVER_INP)

    assert data["parse_ok"] is True, data["problems"]
    assert data["part_count"] >= 1
    assert data["node_count"] > 0
    assert data["element_count"] > 0
    # C3D20R only renders if all 20 nodes of each element resolved — the
    # surface extraction is the proof the join reassembled full connectivity.
    assert data["render_triangle_count"] > 0


@needs_frozen_deck
def test_all_repo_decks_now_parse_or_say_why():
    """No deck in the repo may yield parts=0 with parse_ok True."""
    for inp in sorted(ROOT.glob("cases/*/runs/*/*.inp")):
        if "syntaxcheck" in inp.name:
            continue
        data = parse_inp(inp)
        if data["part_count"] == 0:
            assert data["parse_ok"] is False and data["problems"], (
                "%s: empty preview with no explanation" % inp)


def test_multi_part_local_label_collision_is_refused(tmp_path):
    deck = tmp_path / "two_parts.inp"
    deck.write_text(
        "*Part, name=A\n"
        "*Node\n"
        " 1, 0., 0., 0.\n 2, 1., 0., 0.\n 3, 1., 1., 0.\n 4, 0., 1., 0.\n"
        "*Element, type=S4R, elset=EA\n"
        " 1, 1, 2, 3, 4\n"
        "*End Part\n"
        "*Part, name=B\n"
        "*Node\n"
        " 1, 0., 0., 5.\n 2, 1., 0., 5.\n 3, 1., 1., 5.\n 4, 0., 1., 5.\n"
        "*Element, type=S4R, elset=EB\n"
        " 1, 1, 2, 3, 4\n"
        "*End Part\n",
        encoding="utf-8")

    data = parse_inp(deck)

    assert data["parse_ok"] is False
    assert any("*Part" in p for p in data["problems"])
    # Refusing means refusing: no wrong-geometry parts may leak out for a
    # consumer that forgets to check parse_ok.
    assert data["parts"] == []


def test_instance_translation_is_applied_not_ignored(tmp_path):
    """This used to be a refusal, and the refusal was the right call at the
    time: reading the coordinates flat would have drawn the part 2000 mm from
    where it belongs. It is now placed instead, and the placement rule is
    measured against CAE's own coordinates in tests/test_parse_inp_assembly.py.

    Still a honesty test, just a stricter one — the number below is what makes
    the difference between placing and ignoring visible.
    """
    deck = tmp_path / "translated.inp"
    deck.write_text(
        "*Part, name=P\n"
        "*Node\n"
        " 1, 0., 0., 0.\n 2, 1., 0., 0.\n 3, 1., 1., 0.\n 4, 0., 1., 0.\n"
        "*Element, type=S4R, elset=E\n"
        " 1, 1, 2, 3, 4\n"
        "*End Part\n"
        "*Assembly, name=A\n"
        "*Instance, name=P-1, part=P\n"
        " 0., 0., 2000.\n"
        "*End Instance\n"
        "*End Assembly\n",
        encoding="utf-8")

    data = parse_inp(deck)

    assert data["parse_ok"] is True, data["problems"]
    assert data["part_count"] == 1
    assert data["parts"][0]["instance"] == "P-1"
    zs = data["parts"][0]["nodes"][2::3]
    assert min(zs) == pytest.approx(2000.0) and max(zs) == pytest.approx(2000.0), (
        "the instance was drawn at its part-local z, not where the assembly "
        "puts it")
    assert data["bbox"][0][2] == pytest.approx(2000.0)


def test_identity_instance_stays_renderable(tmp_path):
    """The benign single-part CAE shape (plate_hole layout) must keep working."""
    deck = tmp_path / "identity.inp"
    deck.write_text(
        "*Part, name=P\n"
        "*Node\n"
        " 1, 0., 0., 0.\n 2, 1., 0., 0.\n 3, 1., 1., 0.\n 4, 0., 1., 0.\n"
        "*Element, type=S4R, elset=E\n"
        " 1, 1, 2, 3, 4\n"
        "*End Part\n"
        "*Assembly, name=A\n"
        "*Instance, name=P-1, part=P\n"
        "*End Instance\n"
        "*End Assembly\n",
        encoding="utf-8")

    data = parse_inp(deck)

    assert data["parse_ok"] is True, data["problems"]
    assert data["part_count"] == 1


def test_dropped_element_family_is_reported_not_silent(tmp_path):
    deck = tmp_path / "mixed.inp"
    deck.write_text(
        "*Node\n"
        " 1, 0., 0., 0.\n 2, 1., 0., 0.\n 3, 1., 1., 0.\n 4, 0., 1., 0.\n"
        " 5, 0., 0., 1.\n 6, 1., 0., 1.\n 7, 1., 1., 1.\n 8, 0., 1., 1.\n"
        "*Element, type=C3D8, elset=BLOCK\n"
        " 1, 1, 2, 3, 4, 5, 6, 7, 8\n"
        "*Element, type=CONN3D2, elset=CONNECTORS\n"
        " 2, 1, 5\n",
        encoding="utf-8")

    data = parse_inp(deck)

    assert data["part_count"] == 1          # the solid renders
    assert data["parse_ok"] is True          # a warned partial is still a render
    joined = " ".join(data["problems"])
    assert "CONNECTORS" in joined and "CONN3D2" in joined, (
        "the dropped block must be named, or a partial render reads as complete")


def test_garbage_deck_refuses_with_a_reason(tmp_path):
    deck = tmp_path / "garbage.inp"
    deck.write_text("this is not an abaqus deck at all\n1,2,3\n", encoding="utf-8")

    data = parse_inp(deck)   # must not raise: callers run mid-pipeline

    assert data["parse_ok"] is False
    assert data["parts"] == []
    assert data["problems"]


def test_unresolved_node_references_are_counted(tmp_path):
    deck = tmp_path / "dangling.inp"
    deck.write_text(
        "*Node\n"
        " 1, 0., 0., 0.\n 2, 1., 0., 0.\n 3, 1., 1., 0.\n 4, 0., 1., 0.\n"
        "*Element, type=S4R, elset=E\n"
        " 1, 1, 2, 3, 4\n"
        " 2, 1, 2, 3, 99\n",   # node 99 does not exist
        encoding="utf-8")

    data = parse_inp(deck)

    assert data["part_count"] == 1
    assert any("99" in p or "1/2" in p or "节点" in p for p in data["problems"]), (
        "an element silently dropped for a dangling node ref renders a "
        "partial model that reads as complete")


def test_write_parts_mesh_round_trips_honesty_fields(tmp_path):
    out = tmp_path / "mesh.json"
    write_parts_mesh(_write_continuation_deck(tmp_path), out)
    data = json.loads(out.read_text(encoding="utf-8"))

    assert "parse_ok" in data and "problems" in data
