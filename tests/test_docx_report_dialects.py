"""The report has to describe the model it actually ran, in every dialect.

v1 (`geometry` + `analysis.step_type` + `bc_load`) was removed 2026-08-16. The
report builder read only those keys, so on a v2 run three things silently
vanished from the .docx: the geometry/mesh line, the boundary/load line, and the
分析步类型 table row. Nothing raised — every read was a guarded `.get()` — so the
document still built and simply said less than it used to, which is the failure
mode a reader cannot detect from the document itself.

The v1 reads are deliberately KEPT and pinned here too: reports are built from
archived run directories, and the spec frozen inside a pre-2026-08-16 run is
still v1. Dropping those branches would have broken the historical evidence this
repo treats as unreproducible.
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from reporting.build_docx_report import (  # noqa: E402
    RunBundle,
    _model_table,
    _spec_summary_lines,
)

V1_SPEC = {
    "meta": {"model_name": "Cantilever"},
    "geometry": {"type": "cantilever_block", "L": 100.0},
    "analysis": {"solver": "standard", "step_type": "Static"},
    "bc_load": {"fixed_face": "z=0", "load_type": "pressure", "value": 1.0},
}


def _bundle(spec: dict) -> RunBundle:
    return RunBundle(
        run_dir=".", run_id="r", model_name="M", status="COMPLETED",
        unsolved=False, kpi_notice="", kpis={}, kpi_source="",
        result={"stages": {"build_model": {"inp_path": "X.inp"}}},
        capsule={}, spec=spec, spec_path="spec.yaml", images=None,
        mesh_counts={}, dat_path=None, odb_path=None,
    )


def _line(lines: list[str], prefix: str) -> str:
    hit = [line for line in lines if line.startswith(prefix)]
    assert len(hit) == 1, "expected exactly one %r line, got %r" % (prefix, lines)
    return hit[0]


def _v2_spec() -> dict:
    return yaml.safe_load(
        (ROOT / "cases" / "plate_hole" / "spec.yaml").read_text(encoding="utf-8"))


def test_a_v2_run_reports_its_geometry_and_mesh():
    """Attributed to a part on purpose: v2 has N parts each with its own seed,
    so a bare `seed=3.0` would not say which mesh it described."""
    line = _line(_spec_summary_lines(_bundle(_v2_spec()), "2021"), "几何与网格参数：")
    assert "Plate" in line
    assert "TWO_D_PLANAR" in line
    assert "seed=3.0" in line


def test_a_v2_run_reports_its_boundary_conditions_and_loads():
    """By Abaqus call name, not a prettified label. `Pressure` acts along the
    surface normal and `SurfaceTraction` along a stated vector -- a report that
    blurred the two would describe a different analysis than the one that ran.
    """
    line = _line(_spec_summary_lines(_bundle(_v2_spec()), "2021"), "边界与荷载：")
    assert "XsymmBC" in line and "YsymmBC" in line
    # The sign is the direction; -100 is the tension this case means.
    assert "Pressure(-100.0)" in line


def test_a_v2_run_reports_its_step_type():
    rows = dict((k, v) for k, v in _model_table(_bundle(_v2_spec()))[1])
    assert rows.get("分析步类型") == "StaticStep"


def test_a_deck_run_says_the_inp_defines_the_model():
    """It has no parts and no conditions. Saying nothing would read as "no
    geometry, no loads"; the truth is that this tree cannot see inside the deck.
    """
    spec = {"meta": {}, "deck": {"file": "SteelFrameBlast.inp"}}
    line = _line(_spec_summary_lines(_bundle(spec), "2021"), "几何与网格参数：")
    assert "SteelFrameBlast.inp" in line


def test_an_archived_v1_run_still_renders_every_row():
    """The reason the v1 branches were kept rather than deleted."""
    lines = _spec_summary_lines(_bundle(V1_SPEC), "2021")
    assert "cantilever_block" in _line(lines, "几何与网格参数：")
    assert "fixed_face=z=0" in _line(lines, "边界与荷载：")
    rows = dict((k, v) for k, v in _model_table(_bundle(V1_SPEC))[1])
    assert rows.get("分析步类型") == "Static"
    assert rows.get("求解器") == "standard"


def test_the_v2_branch_does_not_hijack_an_archived_v1_run():
    """Both dialects present must never happen, but if a spec somehow carried
    `geometry` AND `parts` the archived reading wins -- the v2 branches are
    `elif`, so a v1 run can never be re-described by whatever `parts` holds.
    """
    spec = dict(V1_SPEC, parts=[{"name": "Ghost", "mesh": {"seed": 99.0}}])
    line = _line(_spec_summary_lines(_bundle(spec), "2021"), "几何与网格参数：")
    assert "cantilever_block" in line and "Ghost" not in line
