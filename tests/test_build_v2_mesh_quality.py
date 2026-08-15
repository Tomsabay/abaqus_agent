"""expect.mesh.quality: the shape of the elements, and who measured them.

Hermetic — nothing here starts Abaqus. The solver evidence lives in
scripts/run_mesh_quality_check.py.

Two measurements shape this file, both on Abaqus 2021, the same 10x10x100
C3D8I cantilever under 0.1 MPa on the top face (theory: -0.0714286 mm):

    2160 elements, 1.667 mm cubes      aspect  1.0   -0.0714527   +0.03%
    2000 elements, 0.5 x 0.5 x 20      aspect 40.0   -0.0684224   +4.21%

Both pass ANALYSIS_CHECKS with 0 failed and 0 warned. The same element budget
spent two ways, and the one that looks more refined in every count the log used
to print is the one that is a hundred times further from the answer.

And the coverage trap, on that same hex mesh:

    SHAPE_FACTOR            2160 of 2160 not applicable, 0 failed
    GEOM_DEVIATION_FACTOR    972 of 2000 not applicable, worst = 0.0

A criterion that applies to none of your elements still answers with an empty
failure list. So `naElements` has to be read, not merely fetched.
"""

from __future__ import annotations

import ast
import copy
import re
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from runner import (
    build_v2,  # noqa: E402
    spec_base,
)

CASE = ROOT / "cases" / "two_plate_tie" / "spec.yaml"


@pytest.fixture
def named_spec() -> dict:
    return yaml.safe_load(CASE.read_text(encoding="utf-8"))


@pytest.fixture
def spec(named_spec) -> dict:
    out = copy.deepcopy(named_spec)
    out["parts"][0].setdefault("expect", {})["mesh"] = {
        "quality": [{"criterion": "ASPECT_RATIO", "max": 5.0}]}
    return out


def _emit(spec: dict) -> str:
    text = build_v2.generate_script(spec)
    ast.parse(text)
    return text


def _refuse(spec: dict) -> str:
    with pytest.raises(spec_base.SpecError) as caught:
        build_v2.generate_script(spec)
    return str(caught.value)


def _quality(spec: dict, rows: list) -> dict:
    out = copy.deepcopy(spec)
    out["parts"][0]["expect"]["mesh"]["quality"] = rows
    return out


# ---------------------------------------------------------------------------
# Placement: the check has to run where the mesh already exists
# ---------------------------------------------------------------------------

def test_the_check_runs_after_the_mesh_is_made(spec):
    """A part with a declarative `mesh:` block is meshed last.

    Emitting the check alongside the geometry expectations would hand it a part
    with no elements and refuse it as MESH_EMPTY. No shipped case wrote both
    `mesh:` and `expect.mesh`, so this never fired -- and it is exactly the
    route the quality rows have to take.
    """
    text = _emit(spec)
    body = text.split("# --- Parts")[1]
    assert body.index("p.generateMesh()") < body.index("_mesh_check(p, 'Half',")


def test_a_part_meshed_by_a_generic_call_still_gets_one(named_spec):
    out = copy.deepcopy(named_spec)
    part = out["parts"][0]
    del part["mesh"]
    part["features"].append({"call": "generateMesh"})
    part["expect"] = {"volume": 5000.0, "mesh": {"elements": ">=1"}}
    text = _emit(out)
    assert "_mesh_check(p, 'Half', '>=1', None, None)" in text


def test_a_part_with_no_mesh_block_and_no_expect_is_refused(named_spec):
    """This used to assert that no check was emitted, which was true and was
    the bug: nothing meshed the part either.

    Measured on Abaqus 2021 -- a two-part deck with one part left unmeshed
    wrote this, and the job COMPLETED:

        133| *Part, name=Unmeshed
        134| *End Part
        ...
        144| *Instance, name=Unmeshed, part=Unmeshed
        146| *End Instance

    An empty part with a live instance. It contributed no mass and no
    stiffness, and nothing anywhere said so. The state is refused now rather
    than emitted without a check.
    """
    out = copy.deepcopy(named_spec)
    del out["parts"][0]["mesh"]
    with pytest.raises(spec_base.SpecError) as caught:
        _emit(out)
    message = str(caught.value)
    assert "mesh" in message and "expect" in message


def test_the_shipped_case_is_unchanged(named_spec):
    assert "_mesh_check(p, 'Half')" in _emit(named_spec)


# ---------------------------------------------------------------------------
# The rows themselves
# ---------------------------------------------------------------------------

def test_a_criterion_and_a_bound_reach_the_deck(spec):
    text = _emit(spec)
    assert ("_mesh_check(p, 'Half', None, None, "
            "({'criterion': 'ASPECT_RATIO', 'kwargs': {}, "
            "'allow_na': False, 'max': 5.0},))") in text


def test_a_threshold_is_passed_straight_through(spec):
    text = _emit(_quality(spec, [{"criterion": "ASPECT_RATIO",
                                  "threshold": 5.0, "max_failed": 0}]))
    assert "'kwargs': {'threshold': 5.0}" in text
    assert "'max_failed': 0" in text


def test_a_criterion_with_no_bound_is_refused(spec):
    """It would measure and then accept anything, which is worse than silence."""
    message = _refuse(_quality(spec, [{"criterion": "ASPECT_RATIO"}]))
    assert "states a criterion and no bound" in message


def test_max_failed_without_a_threshold_is_refused(spec):
    """Abaqus flags nothing until a threshold says what counts as bad."""
    message = _refuse(_quality(spec, [{"criterion": "ASPECT_RATIO",
                                       "max_failed": 0}]))
    assert "only flags any once a `threshold:`" in message


def test_the_criterion_must_look_like_a_constant(spec):
    message = _refuse(_quality(spec, [{"criterion": "aspect_ratio",
                                       "max": 5.0}]))
    assert "is not an abaqusConstants symbol" in message


def test_an_empty_quality_list_is_refused(spec):
    assert "non-empty list" in _refuse(_quality(spec, []))


def test_a_bound_must_be_a_number(spec):
    assert "must be a number" in _refuse(
        _quality(spec, [{"criterion": "ASPECT_RATIO", "max": True}]))


def test_a_passthrough_keyword_must_be_scalar(spec):
    message = _refuse(_quality(spec, [{"criterion": "ASPECT_RATIO", "max": 5.0,
                                       "threshold": {"select": "x"}}]))
    assert "passed straight to verifyMeshQuality" in message


def test_an_all_caps_passthrough_becomes_a_symbol(spec):
    text = _emit(_quality(spec, [{"criterion": "ASPECT_RATIO", "max": 5.0,
                                  "elemShape": "HEX"}]))
    assert "'elemShape': HEX" in text


def test_allow_na_reaches_the_deck(spec):
    text = _emit(_quality(spec, [{"criterion": "GEOM_DEVIATION_FACTOR",
                                  "max": 0.2, "allow_na": True}]))
    assert "'allow_na': True" in text


def test_several_criteria_are_kept_in_order(spec):
    text = _emit(_quality(spec, [{"criterion": "ASPECT_RATIO", "max": 5.0},
                                 {"criterion": "SMALL_ANGLE", "min": 30.0}]))
    assert text.index("'ASPECT_RATIO'") < text.index("'SMALL_ANGLE'")


def test_quality_is_not_smuggled_past_the_unknown_key_check(spec):
    spec["parts"][0]["expect"]["mesh"]["shape"] = 1
    assert "not something the mesh check measures" in _refuse(spec)


# ---------------------------------------------------------------------------
# The runtime side, asserted on the emitted helper text
# ---------------------------------------------------------------------------

def test_coverage_is_refused_by_default(spec):
    """A criterion that applies to no element still answers `failed: []`."""
    text = _emit(spec)
    assert "QUALITY_NOT_APPLICABLE" in text
    assert "if na and not row.get('allow_na')" in text


def test_the_element_shape_is_logged_whether_or_not_it_was_asked_for(
        named_spec):
    """'elems=2000 warnings=0' reads like the better of two meshes."""
    text = _emit(named_spec)
    assert "_mesh_worst(p, 'ASPECT_RATIO')" in text
    assert "aspect=%.3g" in text


def test_a_criterion_that_measured_nothing_at_all_is_refused(named_spec):
    """ANALYSIS_CHECKS runs always, so its own coverage matters too."""
    assert "MESH_UNCHECKED" in _emit(named_spec)


@pytest.mark.parametrize("marker", [
    "QUALITY_UNKNOWN", "QUALITY_REFUSED", "QUALITY_WORSE", "QUALITY_FAILED",
    "QUALITY_NOT_APPLICABLE", "QUALITY_NO_WORST", "QUALITY_NO_COUNT",
    "MESH_UNCHECKED",
])
def test_every_refusal_is_logged_before_it_is_raised(spec, marker):
    """A raise with no log leaves selectors.log ending mid-build, no reason.

    That shape of bug has now been fixed twice — once in _mesh_check and once
    in _gcall — so it gets a test rather than a third fixing.
    """
    text = _emit(spec)
    assert re.search(r"_expect_fail\(\s*'%s" % marker, text), marker


def test_the_deck_names_no_list_of_valid_criteria(spec):
    """Abaqus enumerates them in its own error; a copy here would go stale."""
    text = _emit(spec)
    assert "LARGE_ANGLE_TRI_FACE" not in text


# ---------------------------------------------------------------------------
# The schema
# ---------------------------------------------------------------------------

def _validate(spec: dict):
    from tools.schema_validator import validate_spec
    return validate_spec(spec)


def test_the_schema_accepts_a_quality_block(spec):
    ok, errors = _validate(spec)
    assert ok, errors


def test_the_schema_accepts_a_passthrough_keyword(spec):
    ok, errors = _validate(_quality(spec, [{"criterion": "ASPECT_RATIO",
                                            "threshold": 5.0,
                                            "max_failed": 0}]))
    assert ok, errors


def test_the_schema_refuses_a_lowercase_criterion(spec):
    ok, _errors = _validate(_quality(spec, [{"criterion": "aspect_ratio",
                                             "max": 5.0}]))
    assert not ok


def test_the_schema_requires_a_criterion(spec):
    ok, _errors = _validate(_quality(spec, [{"max": 5.0}]))
    assert not ok


def test_the_schema_refuses_an_empty_quality_list(spec):
    ok, _errors = _validate(_quality(spec, []))
    assert not ok
