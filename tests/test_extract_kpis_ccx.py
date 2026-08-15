"""CalculiX .dat / .frd parsing. Fixtures are real ccx 2.23 output, trimmed.

Two traps this file exists to pin:

  * .frd data lines are FIXED WIDTH with no separator, so a negative value runs
    straight into its neighbour: ``-2.24087E-01-2.19571E-01`` is two numbers.
    ``str.split()`` gives one garbage token.
  * The shear component ORDER differs between the files — .dat is
    sxx,syy,szz,sxy,sxz,syz while .frd is SXX,SYY,SZZ,SXY,SYZ,SZX. That is
    invisible in a von Mises test (all shears get squared and summed), so it
    needs a test that distinguishes the two.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from post.extract_kpis_ccx import (
    extract_kpis_ccx,
    parse_ccx_tip_u2,
    parse_dat_blocks,
    parse_frd_block,
    von_mises,
)

DAT = """
                        S T E P       1


                                INCREMENT     1


 displacements (vx,vy,vz) for set TIP_NODES and time  0.1000000E+01

       611  2.413150E-16 -1.903958E-03  1.509169E-18

 forces (fx,fy,fz) for set FIXED_END and time  0.1000000E+01

         1 -3.000000E-01  2.500000E-01  1.000000E-02
         2  1.000000E-01  7.500000E-01 -2.000000E-02
"""

# 13-char record header then 12-char fields, exactly as ccx writes them.
FRD = """    1C
  100CL  101 1.000000000         621                     0    1           1
 -4  DISP        4    1
 -5  D1          1    2    1    0
 -5  D2          1    2    2    0
 -5  D3          1    2    3    0
 -1         1 0.00000E+00 0.00000E+00 0.00000E+00
 -1       611 2.41315E-16-1.90396E-03 1.50917E-18
 -3
  100CL  101 1.000000000         621                     0    1           1
 -4  STRESS      6    1
 -5  SXX         1    4    1    1
 -5  SYY         1    4    2    2
 -5  SZZ         1    4    3    3
 -5  SXY         1    4    1    2
 -5  SYZ         1    4    2    3
 -5  SZX         1    4    3    1
 -1         1-2.24087E-01-2.19571E-01-6.59687E-01 1.22426E-02-4.74143E-02-1.46042E-01
 -1         2-2.05360E-01-2.02694E-01-6.14142E-01 4.60952E-03-7.35141E-02-7.03829E-02
 -3
  100CL  101 1.000000000         621                     0    1           1
 -4  FORC        4    1
 -5  F1          1    2    1    0
 -5  F2          1    2    2    0
 -5  F3          1    2    3    0
 -1         1-3.00000E-01 2.50000E-01 1.00000E-02
 -3
"""


# ── .dat ────────────────────────────────────────────────────────────────────

def test_dat_displacement_block_is_keyed_by_original_node_id():
    blocks = parse_dat_blocks(
        DAT, __import__("post.extract_kpis_ccx", fromlist=["_"])._DAT_DISP_RE)
    assert set(blocks) == {"TIP_NODES"}
    assert blocks["TIP_NODES"][611][1] == pytest.approx(-1.903958e-3)


def test_parse_ccx_tip_u2_reads_the_second_component():
    assert parse_ccx_tip_u2(DAT, 611) == pytest.approx(-1.903958e-3)
    assert parse_ccx_tip_u2(DAT, 999) is None
    assert parse_ccx_tip_u2("nothing here", 611) is None


# ── .frd fixed width ────────────────────────────────────────────────────────

def test_frd_disp_block_parses_run_together_negative_values():
    disp = parse_frd_block(FRD, "DISP")
    assert disp[611] == pytest.approx([2.41315e-16, -1.90396e-03, 1.50917e-18])


def test_frd_stress_line_yields_six_components_not_a_split_mess():
    """`str.split()` on this line gives 4 tokens; fixed-width gives the right 6."""
    line = " -1         1-2.24087E-01-2.19571E-01-6.59687E-01 1.22426E-02-4.74143E-02-1.46042E-01"
    assert len(line.split()) < 7, "fixture must actually contain the run-together case"
    stress = parse_frd_block(FRD, "STRESS")
    assert len(stress[1]) == 6
    assert stress[1][0] == pytest.approx(-2.24087e-01)
    assert stress[1][5] == pytest.approx(-1.46042e-01)


def test_frd_blocks_do_not_bleed_into_each_other():
    assert set(parse_frd_block(FRD, "FORC")) == {1}
    assert parse_frd_block(FRD, "FORC")[1] == pytest.approx([-0.3, 0.25, 0.01])
    assert parse_frd_block(FRD, "NOSUCH") == {}


# ── von Mises and the shear-order trap ──────────────────────────────────────

def test_von_mises_matches_the_closed_form():
    comps = [100.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    assert von_mises(comps) == pytest.approx(100.0)
    assert von_mises([0.0, 0.0, 0.0, 50.0, 0.0, 0.0]) == pytest.approx(50.0 * math.sqrt(3))


def test_shear_order_differs_between_dat_and_frd():
    """Same six numbers, different files, different physical meaning."""
    from post.extract_kpis_ccx import _DAT_STRESS_ORDER, _FRD_STRESS_ORDER

    assert _FRD_STRESS_ORDER != _DAT_STRESS_ORDER
    assert _FRD_STRESS_ORDER[4] == "SYZ" and _DAT_STRESS_ORDER[4] == "SXZ"
    # Mises cannot see the difference — that is exactly why it needs its own test.
    comps = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]
    assert von_mises(comps, _FRD_STRESS_ORDER) == pytest.approx(
        von_mises(comps, _DAT_STRESS_ORDER))


def test_von_mises_refuses_an_incomplete_component_set():
    from post.extract_kpis_ccx import CcxResultError

    with pytest.raises(CcxResultError):
        von_mises([1.0, 2.0, 3.0])


# ── end-to-end extraction ───────────────────────────────────────────────────

def _write_job(tmp_path: Path) -> Path:
    (tmp_path / "Job.dat").write_text(DAT, encoding="utf-8")
    (tmp_path / "Job.frd").write_text(FRD, encoding="utf-8")
    return tmp_path


def test_displacement_kpi_comes_from_the_dat_and_is_abaqus_equivalent(tmp_path):
    _write_job(tmp_path)
    out = extract_kpis_ccx("Job", tmp_path, [
        {"name": "U_tip", "type": "nodal_displacement", "location": "tip_center",
         "component": "U2"},
    ])
    assert out["kpis"]["U_tip"] == pytest.approx(-1.903958e-3)
    assert out["kpi_provenance"]["U_tip"]["abaqus_equivalent"] is True
    assert out["kpi_provenance"]["U_tip"]["source"] == "ccx.dat"
    assert out["errors"] == []


def test_mises_kpi_is_tagged_as_not_abaqus_equivalent(tmp_path):
    _write_job(tmp_path)
    out = extract_kpis_ccx("Job", tmp_path, [
        {"name": "MISES_MAX", "type": "field_max", "location": "whole_model"},
    ])
    prov = out["kpi_provenance"]["MISES_MAX"]
    assert prov["abaqus_equivalent"] is False
    assert prov["definition"] == "nodal_averaged"
    assert "Abaqus" in prov["note"]


def test_reaction_force_uses_the_dat_forces_block(tmp_path):
    _write_job(tmp_path)
    out = extract_kpis_ccx("Job", tmp_path, [
        {"name": "RF", "type": "reaction_force_max", "location": "fixed_face",
         "component": "RF2"},
    ])
    assert out["kpis"]["RF"] == pytest.approx(0.75)


def test_unsupported_kpi_yields_no_value_and_an_explicit_reason(tmp_path):
    """Never a 0.0 placeholder — the ODB extractor's empty-list default is a trap."""
    _write_job(tmp_path)
    out = extract_kpis_ccx("Job", tmp_path, [
        {"name": "ALLPD", "type": "history_output_max", "variable": "ALLPD"},
    ])
    assert "ALLPD" not in out["kpis"]
    assert any("ALLPD" in e for e in out["errors"])


def test_missing_result_files_produce_no_kpis_at_all(tmp_path):
    out = extract_kpis_ccx("Nothing", tmp_path, [
        {"name": "U_tip", "type": "nodal_displacement", "location": "tip_center"},
    ])
    assert out["kpis"] == {}
    assert out["errors"]


def test_requesting_a_set_the_deck_never_printed_is_an_error_not_a_guess(tmp_path):
    _write_job(tmp_path)
    out = extract_kpis_ccx("Job", tmp_path, [
        {"name": "U_hole", "type": "nodal_displacement", "location": "hole_edge"},
    ])
    assert "U_hole" not in out["kpis"]
    assert any("HOLE_EDGE" in e for e in out["errors"])


def test_mises_at_a_named_location_is_refused_not_whole_model(tmp_path):
    """The .frd STRESS block is whole-model only; a narrower ask must refuse.

    Before this guard, MISES at hole_edge_set, at whole_model, and at a set
    that does not exist all returned the identical global max — verified
    during the P2-d recon.
    """
    _write_job(tmp_path)
    out = extract_kpis_ccx("Job", tmp_path, [
        {"name": "MISES_HOLE_EDGE", "type": "field_max", "location": "hole_edge_set"},
    ])
    assert "MISES_HOLE_EDGE" not in out["kpis"]
    joined = " ".join(out["errors"])
    assert "location" in joined and "hole_edge_set" in joined, (
        "the refusal must name the spec field so the user can fix it")


def test_mises_whole_model_and_empty_location_still_extract(tmp_path):
    _write_job(tmp_path)
    out = extract_kpis_ccx("Job", tmp_path, [
        {"name": "M1", "type": "field_max", "location": "whole_model"},
        {"name": "M2", "type": "field_max"},
    ])
    assert "M1" in out["kpis"] and "M2" in out["kpis"]
    assert out["kpis"]["M1"] == out["kpis"]["M2"]


def test_component_field_max_at_a_named_location_is_refused(tmp_path):
    """Non-mises field_max reads .frd DISP/FORC — whole-model by the same route."""
    _write_job(tmp_path)
    out = extract_kpis_ccx("Job", tmp_path, [
        {"name": "U1_TOP", "type": "field_max", "component": "U1",
         "location": "top_face"},
    ])
    assert "U1_TOP" not in out["kpis"]
    assert any("top_face" in e for e in out["errors"])
