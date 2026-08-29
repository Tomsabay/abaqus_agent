"""The polygon profile: rolled sections, which rect and circle cannot draw.

An I-shape and a T-shape are the whole vocabulary of a steel frame, and neither
is a rectangle or a circle. Measured on Abaqus 2021 with the T-stub below
(200x12 flange, 10 thick web to y=100, extruded 150): the eight lines close into
a face, `EXPECT_OK: TStub volume=492000.0 (want 492000.0, off by 0.0)`, and it
meshes as hex -- `MESH_OK: TStub nodes=700 elems=312 warnings=0 aspect=1.26`.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from runner.build_v2 import generate_script  # noqa: E402
from runner.v2_profiles import (  # noqa: E402
    _polygon_edges,
    _profile_data,
    _sheet_size,
)
from tools.errors import AbaqusAgentError  # noqa: E402

T_STUB = [[-100.0, 0.0], [100.0, 0.0], [100.0, 12.0], [5.0, 12.0],
          [5.0, 100.0], [-5.0, 100.0], [-5.0, 12.0], [-100.0, 12.0]]


def _spec(points):
    return {
        "meta": {"abaqus_release": "2021", "model_name": "Poly", "units": "mm_MPa_t"},
        "material": {"name": "Steel", "E": 210000.0, "nu": 0.3},
        "parts": [{
            "name": "P",
            "features": [
                {"op": "sketch", "id": "sec", "plane": "XY",
                 "profile": {"polygon": {"points": points}}},
                {"op": "extrude", "sketch": "sec", "depth": 150.0},
            ],
            "section": {"type": "solid", "material": "Steel"},
            "mesh": {"seed": 12.0, "element": "C3D8I"},
        }],
        "assembly": {"instances": [{"name": "I1", "part": "P"}]},
        "steps": [{"name": "S", "type": "Static",
                   "bcs": [{"name": "F", "region": "I1:face@z=min", "type": "encastre"}],
                   "loads": [{"name": "L", "region": "I1:face@y=max",
                              "type": "pressure", "value": 1.0}]}],
        "outputs": {"kpis": [{"name": "U", "type": "field_min",
                              "location": "whole_model", "component": "U2"}]},
    }


def test_polygon_closes_the_loop_itself():
    """N points produce N lines, and the last one returns to the first."""
    edges = _polygon_edges({"polygon": {"points": T_STUB}})
    assert len(edges) == len(T_STUB)
    assert edges[-1][1] == tuple(T_STUB[0])


def test_every_declared_point_is_drawn_once():
    script = generate_script(_spec(T_STUB))
    drawn = [ln for ln in script.splitlines() if ".Line(point1=" in ln]
    assert len(drawn) == 8
    # the web tip is the point a mis-ordered polygon loses first
    assert any("(5.0, 100.0)" in ln for ln in drawn)
    assert any("(-5.0, 100.0)" in ln for ln in drawn)


def test_repeated_closing_point_is_refused():
    """Repeating the first point to 'close' the loop draws a zero-length line.

    Abaqus accepts that call, so the sketch quietly ends up one usable edge
    short and the failure surfaces later, on the extrude, naming the wrong
    thing.
    """
    with pytest.raises(AbaqusAgentError, match="repeats the first"):
        _polygon_edges({"polygon": {"points": T_STUB + [T_STUB[0]]}})


def test_duplicate_adjacent_points_are_refused():
    with pytest.raises(AbaqusAgentError, match="zero-length line"):
        _polygon_edges({"polygon": {"points": [[0.0, 0.0], [0.0, 0.0], [10.0, 10.0]]}})


def test_sheet_size_spans_the_bounding_box():
    # 200 wide vs 100 tall -> the width governs
    assert _sheet_size({"polygon": {"points": T_STUB}}) == pytest.approx(800.0)


def test_profile_data_leaves_circles_empty_so_a_cut_refuses_itself():
    """_cut() reads 'circles' and refuses when it is empty.

    A polygonal cut cannot verify itself -- the check looks for the cylindrical
    face the cut should have left -- so the recorded data must not pretend
    otherwise.
    """
    data = _profile_data({"polygon": {"points": T_STUB}})
    assert "'circles': ()" in data
    assert "'poly': ((-100.0, 0.0)" in data


def test_cut_extrude_with_a_polygon_is_refused_at_spec_time():
    spec = _spec(T_STUB)
    spec["parts"][0]["features"].append(
        {"op": "cut_extrude", "sketch": "sec", "depth": 5.0})
    with pytest.raises(AbaqusAgentError):
        generate_script(spec)
