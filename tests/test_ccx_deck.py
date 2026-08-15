"""Mesh generation and Abaqus->CalculiX deck translation. No solver involved."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from runner.ccx_deck import (
    build_ccx_deck,
    result_request_block,
    translate_abaqus_inp,
    write_ccx_deck,
)
from runner.ccx_mesh import build_mesh, cantilever_block_mesh

GEO = {"type": "cantilever_block", "L": 100.0, "W": 10.0, "H": 10.0, "seed_size": 5.0}

# The real Abaqus/CAE shape, trimmed: assembly wrappers, an instance-prefixed
# set reference, the ENCASTRE named BC, and the *Output block ccx ignores.
ASSEMBLY_DECK = """*Heading
** Job name: Cantilever
*Preprint, echo=NO, model=NO
**
*Part, name=Part-1
*Node
1, 0., 0., 0.
2, 1., 0., 0.
*Element, type=C3D20R
1, 1, 2
*Nset, nset=FIXED_END
1,
*Nset, nset=TIP_NODES
2,
*Elset, elset=_LOAD_SURF_S3, internal
1,
*Solid Section, elset=ALL, material=Steel
1.,
*End Part
*Assembly, name=Assembly
*Instance, name=Part-1-1, part=Part-1
*End Instance
*End Assembly
*Material, name=Steel
*Elastic
210000., 0.3
*Boundary
Part-1-1.FIXED_END, ENCASTRE
*Step, name=Step-1, nlgeom=NO
Static analysis
*Static
0.1, 1., 1e-05, 1.
*Cload
Part-1-1.TIP_NODES, 2, -1.
*Restart, write, frequency=0
*Output, field
*Node Output
RF, U
*Element Output, directions=YES
E, S
*End Step
"""


# ── mesher ──────────────────────────────────────────────────────────────────

def test_cantilever_mesh_matches_the_cae_discretisation():
    """Seed 5.0 on 100x10x10 = 20x2x2 C3D20R, the counts the frozen run has."""
    mesh = cantilever_block_mesh(GEO)
    assert mesh.element_type == "C3D20R"
    assert mesh.element_count == 80
    assert mesh.node_count == 621


def test_every_element_has_twenty_distinct_nodes():
    mesh = cantilever_block_mesh(GEO)
    for eid, conn in mesh.elements:
        assert len(conn) == 20, eid
        assert len(set(conn)) == 20, eid


def test_named_sets_cover_the_faces_the_kpi_layer_asks_for():
    mesh = cantilever_block_mesh(GEO)
    assert set(mesh.node_sets) >= {"ALL", "FIXED_END", "LOAD_END", "TIP_NODES"}
    coords = {nid: (x, y, z) for nid, x, y, z in mesh.nodes}
    assert all(coords[n][2] == pytest.approx(0.0) for n in mesh.node_sets["FIXED_END"])
    assert all(coords[n][2] == pytest.approx(100.0) for n in mesh.node_sets["LOAD_END"])
    assert len(mesh.node_sets["TIP_NODES"]) == 1
    tip = coords[mesh.node_sets["TIP_NODES"][0]]
    assert tip == pytest.approx((5.0, 5.0, 100.0))


def test_node_numbering_is_ours_so_kpis_must_go_through_sets():
    """CAE calls the tip node 65; we do not. Hard-coding an id would be a bug."""
    mesh = cantilever_block_mesh(GEO)
    assert mesh.node_sets["TIP_NODES"][0] != 65


def test_unsupported_geometry_raises_rather_than_guessing():
    with pytest.raises(ValueError, match="cantilever_block"):
        build_mesh({"geometry": {"type": "plate_with_hole"}})


# ── translation ─────────────────────────────────────────────────────────────

def test_translation_removes_assembly_wrappers():
    flat, _ = translate_abaqus_inp(ASSEMBLY_DECK)
    lowered = flat.lower()
    for card in ("*part", "*assembly", "*instance", "*preprint", "*output", "*restart"):
        assert card not in lowered, card


def test_translation_strips_the_instance_prefix():
    flat, notes = translate_abaqus_inp(ASSEMBLY_DECK)
    assert "Part-1-1." not in flat
    assert "FIXED_END, 1, 3" in flat
    assert "TIP_NODES, 2, -1." in flat
    assert any("instance" in n or "前缀" in n for n in notes)


def test_translation_rewrites_encastre_to_explicit_dofs():
    flat, notes = translate_abaqus_inp(ASSEMBLY_DECK)
    assert "ENCASTRE" not in flat.upper()
    assert any("ENCASTRE" in n for n in notes)


def test_translation_drops_output_data_lines_not_just_headers():
    flat, _ = translate_abaqus_inp(ASSEMBLY_DECK)
    assert "RF, U" not in flat
    assert "E, S" not in flat


def test_translation_keeps_the_physics_cards():
    flat, _ = translate_abaqus_inp(ASSEMBLY_DECK)
    for card in ("*Node", "*Element", "*Material", "*Elastic", "*Static", "*Cload",
                 "*Solid Section"):
        assert card in flat, card


def test_translation_notes_are_plain_language_for_the_console():
    _, notes = translate_abaqus_inp(ASSEMBLY_DECK)
    assert notes and all(len(n) > 10 for n in notes)


# ── result requests ─────────────────────────────────────────────────────────

def test_result_request_block_asks_in_calculix_dialect():
    """Without this the .dat comes back 0 bytes: ccx ignores Abaqus *Output."""
    block = result_request_block([
        {"name": "U_tip", "type": "nodal_displacement", "location": "tip_center"},
        {"name": "MISES_MAX", "type": "field_max", "location": "whole_model"},
    ])
    assert "*NODE PRINT, NSET=TIP_NODES" in block
    assert "*EL FILE" in block
    assert "*NODE FILE" in block


def test_reaction_force_kpi_requests_rf():
    block = result_request_block([
        {"name": "RF", "type": "reaction_force_max", "location": "fixed_face"},
    ])
    assert "*NODE PRINT, NSET=FIXED_END" in block
    assert "RF" in block


# ── full generated deck ─────────────────────────────────────────────────────

def _spec() -> dict:
    return {
        "meta": {"model_name": "Cantilever"},
        "geometry": dict(GEO),
        "material": {"name": "Steel", "E": 210000.0, "nu": 0.3},
        "analysis": {"step_type": "Static"},
        "bc_load": {"load_type": "concentrated_force", "value": -1.0, "direction": 2},
        "outputs": {"kpis": []},
    }


def test_generated_deck_is_flat_and_self_contained():
    mesh = cantilever_block_mesh(GEO)
    deck = build_ccx_deck(_spec(), mesh, [
        {"name": "U_tip", "type": "nodal_displacement", "location": "tip_center"},
    ])
    assert "*PART" not in deck.upper()
    assert "*NODE, NSET=NALL" in deck
    assert "*ELEMENT, TYPE=C3D20R" in deck
    assert "*BOUNDARY" in deck and "FIXED_END, 1, 3" in deck
    assert "*CLOAD" in deck and "TIP_NODES, 2, -1.0" in deck
    assert deck.rstrip().endswith("*END STEP")


def test_write_ccx_deck_reports_the_mesh_it_built(tmp_path):
    inp, notes = write_ccx_deck(_spec(), tmp_path, [
        {"name": "U_tip", "type": "nodal_displacement", "location": "tip_center"},
    ])
    assert inp.name == "Cantilever.inp"
    assert any("621" in n and "80" in n for n in notes)


def test_write_ccx_deck_translates_a_custom_inp(tmp_path):
    src = tmp_path / "source.inp"
    src.write_text(ASSEMBLY_DECK, encoding="utf-8")
    out_dir = tmp_path / "run"
    inp, notes = write_ccx_deck(_spec(), out_dir, [
        {"name": "U_tip", "type": "nodal_displacement", "location": "tip_center"},
    ], source_inp=src)
    text = inp.read_text(encoding="utf-8")
    assert "*NODE PRINT, NSET=TIP_NODES" in text
    assert text.index("*NODE PRINT") < text.index("*End Step")
    assert any("注入" in n for n in notes)
