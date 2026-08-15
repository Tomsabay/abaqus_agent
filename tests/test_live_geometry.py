"""The half-written draft has to become something drawable.

Hermetic: pure text in, dicts out. No CLI, no CAE — the point of drawing the
sketch in the browser is that nothing has to run for it to appear.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from workbench import live_geometry  # noqa: E402

_DRAFT = """===SPEC===
meta:
  abaqus_release: '2021'
  model_name: BearingHousingAssembly
  units: mm_MPa_t
material:
  name: Steel
  E: 210000.0
  nu: 0.3
parts:
- name: Housing
  features:
  - op: sketch
    id: outline
    plane: XY
    profile:
      rect:
        corner1: [0.0, 0.0]
        corner2: [80.0, 40.0]
  - op: extrude
    sketch: outline
    depth: 60.0
  - op: sketch
    id: hole
    plane: XY
    profile:
      circle:
        center: [40.0, 20.0]
        r: 12.0
  - op: cut_extrude
    sketch: hole
    depth: 60.0
  section: {type: solid, material: Steel}
- name: CoverPlate
  features:
  - op: sketch
    id: plate
    plane: XY
    profile:
      rect:
        corner1: [0.0, 0.0]
        corner2: [80.0, 10.0]
  - op: extrude
    sketch: plate
    depth: 60.0
  section: {type: solid, material: Steel}
assembly:
  instances:
  - name: housing-1
    part: Housing
    translate: [0.0, 0.0, 0.0]
  - name: cover-1
    part: CoverPlate
    translate: [0.0, 40.0, 0.0]
"""


def _payload(text: str):
    return live_geometry.preview_payload(live_geometry.partial_spec(text))


def test_a_complete_draft_draws_every_part():
    payload = _payload(_DRAFT)
    assert [p["name"] for p in payload["parts"]] == ["Housing", "CoverPlate"]
    housing = payload["parts"][0]
    assert housing["outline"] == {"kind": "rect", "corner1": [0.0, 0.0],
                                  "corner2": [80.0, 40.0]}
    assert housing["depth"] == 60.0
    assert housing["holes"] == [{"center": [40.0, 20.0], "r": 12.0,
                                 "depth": 60.0}]
    assert {i["part"]: i["translate"] for i in payload["instances"]} == {
        "Housing": [0.0, 0.0, 0.0], "CoverPlate": [0.0, 40.0, 0.0]}


@pytest.mark.parametrize("cut", range(len(_DRAFT) // 40))
def test_no_prefix_of_a_streaming_draft_ever_raises(cut):
    """Every truncation is a state the parser really sees — the text arrives a
    token at a time. A crash here would kill the worker thread mid-stream."""
    payload = _payload(_DRAFT[: cut * 40])
    assert payload is None or isinstance(payload["parts"], list)


def test_a_part_appears_as_soon_as_its_extrude_is_written():
    """The whole point: the viewport fills in DURING the draft. The first part
    has to draw while the second one is still being typed."""
    upto = _DRAFT.index("- name: CoverPlate")
    payload = _payload(_DRAFT[:upto])
    assert [p["name"] for p in payload["parts"]] == ["Housing"]
    # No assembly block yet — the part still has to be drawable, or the pane
    # stays empty for the minute it takes to write the rest.
    assert payload["instances"] == []


def test_a_sketch_with_no_extrude_yet_draws_nothing():
    """Not everything half-written is drawable, and guessing a depth would put
    a solid on screen that the spec never asked for."""
    upto = _DRAFT.index("  - op: extrude")
    assert _payload(_DRAFT[:upto]) is None


def test_values_that_are_not_numbers_yet_are_skipped_not_drawn():
    """`depth:` with nothing after it parses to None mid-stream; NaN and
    strings arrive from a model that is mid-sentence."""
    spec = yaml.safe_load(_DRAFT.split("===SPEC===")[1])
    spec["parts"][0]["features"][1]["depth"] = None
    assert live_geometry.preview_payload(spec)["parts"][0]["name"] == "CoverPlate"
    spec["parts"][0]["features"][1]["depth"] = "60 mm"
    assert live_geometry.preview_payload(spec)["parts"][0]["name"] == "CoverPlate"
    spec["parts"][0]["features"][1]["depth"] = float("inf")
    assert live_geometry.preview_payload(spec)["parts"][0]["name"] == "CoverPlate"


def test_generic_entity_parts_are_left_undrawn():
    """A generic `entities:` sketch has no recorded profile — the builder says
    so itself. Drawing an approximation of an unknown shape is worse than
    drawing nothing."""
    spec = yaml.safe_load(_DRAFT.split("===SPEC===")[1])
    spec["parts"][0]["features"] = [
        {"op": "sketch", "id": "s", "entities": [{"line": [[0, 0], [1, 1]]}]},
        {"call": "BaseSolidExtrude", "sketch": "s", "depth": 10.0},
    ]
    payload = live_geometry.preview_payload(spec)
    assert [p["name"] for p in payload["parts"]] == ["CoverPlate"]


def test_the_plan_stage_has_nothing_to_draw():
    """The design sheet is prose. It must not be mistaken for a spec."""
    sheet = "【模型名】BearingHousing\n【材料】Steel: E=210000\n- 壳体 80×40×60"
    assert _payload(sheet) is None


def test_a_v1_spec_draws_nothing_rather_than_guessing():
    """v1 says `geometry: {type: cantilever_block, L: ...}`. It is drawable in
    principle, but this module covers the v2 named ops only — and silently
    drawing the wrong dialect's numbers is the failure mode to avoid."""
    v1 = {"geometry": {"type": "cantilever_block", "L": 100.0, "W": 10.0,
                       "H": 10.0}}
    assert live_geometry.preview_payload(v1) is None
