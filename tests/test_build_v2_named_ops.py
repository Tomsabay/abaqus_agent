"""An op this dialect does not know is refused, not guessed at.

Found by running a spec through agent/orchestrator.py that had only ever been
run through build_v2.generate_script() directly. The schema stage refused
`op: cut` -- the vocabulary is `extrude` and `cut_extrude` -- and the generator
had accepted it, because the dispatch ended in `else: # cut_extrude`. So every
unknown op silently became a cut: a misspelt `extrudee`, a `revolve` nobody
implemented, a `cut` that reads like it should work.

It matters that the generator refuses it and not only the schema. The schema is
a separate gate; a spec handed to generate_script() directly never passes
through it, and that is how every model in artifacts/promo was built.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from runner.build_v2 import _NAMED_OPS, SpecError, generate_script  # noqa: E402


def _spec(ops: list) -> dict:
    return {
        "meta": {"abaqus_release": "2021", "model_name": "M", "units": "mm_MPa_t"},
        "material": {"name": "S", "E": 210000.0, "nu": 0.3},
        "parts": [{
            "name": "P",
            "features": ops,
            "expect": {"volume": 1000.0},
            "section": {"type": "solid", "material": "S"},
            "mesh": {"seed": 5.0},
        }],
        "assembly": {"instances": [{"name": "I", "part": "P"}]},
        "steps": [{"name": "S", "type": "Static"}],
        "outputs": {"kpis": [{"name": "M", "type": "field_max",
                              "location": "whole_model"}]},
    }


SKETCH = {"op": "sketch", "id": "s", "plane": "XY",
          "profile": {"rect": {"corner1": [0.0, 0.0], "corner2": [10.0, 10.0]}}}
HOLE = {"op": "sketch", "id": "h", "plane": "XY",
        "profile": {"circle": {"center": [5.0, 5.0], "r": 2.0}}}
EXTRUDE = {"op": "extrude", "sketch": "s", "depth": 10.0}


def test_the_vocabulary_is_the_three_named_ops():
    assert _NAMED_OPS == ("sketch", "extrude", "cut_extrude")


@pytest.mark.parametrize("op", ["cut", "revolve", "extrudee", "Extrude", ""])
def test_an_op_outside_the_vocabulary_is_refused(op):
    """`cut` is the one that was actually written, and it built a whole gear
    before anything complained. The rest are the same mistake wearing different
    clothes."""
    spec = _spec([SKETCH, EXTRUDE, HOLE, {"op": op, "sketch": "h", "depth": 10.0}])
    with pytest.raises(SpecError) as caught:
        generate_script(spec)
    message = str(caught.value)
    assert repr(op) in message
    for known in _NAMED_OPS:
        assert known in message


def test_the_refusal_points_at_the_way_out():
    """There IS a way to reach an Abaqus method this dialect has no op for, and
    a refusal that does not say so sends the reader looking for a missing
    feature instead of the generic call that already exists."""
    spec = _spec([SKETCH, EXTRUDE, HOLE, {"op": "revolve", "sketch": "h",
                                          "depth": 10.0}])
    with pytest.raises(SpecError) as caught:
        generate_script(spec)
    assert "call:" in str(caught.value)


def test_cut_extrude_itself_still_works():
    """The guard is a guard, not a narrowing: the op it was hiding still runs."""
    spec = _spec([SKETCH, EXTRUDE, HOLE,
                  {"op": "cut_extrude", "sketch": "h", "depth": 10.0}])
    spec["parts"][0]["expect"] = {
        "volume": 1000.0,
        "cylinders": [{"r": 2.0, "at": [5.0, 5.0, 5.0]}],
    }
    script = generate_script(spec)
    assert "_cut(m, p, 'P', 'h', 10.0)" in script


def test_extrude_itself_still_works():
    script = generate_script(_spec([SKETCH, EXTRUDE]))
    assert "p.BaseSolidExtrude(sketch=_sk_s, depth=10.0)" in script
