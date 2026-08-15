"""`outputs:` accepted any key and the generator read three of them.

Everything else validated and then evaporated. Measured before this file
existed: `outputs.numIntervals`, `outputs.time_points`, `outputs.paths`, and
on a KPI `time:`, `envelope:` and `nominal:` all passed `validate_spec` and
none of them reached the deck. The spec said one thing and the number
answered a different question, with nothing anywhere saying so.

Closing the object is only half the fix -- four keys that ARE honoured were
never declared (`step`, `reducer`, `invariant`, `note`), and closing without
declaring them would have refused twelve shipped cases. Both halves are
pinned here.
"""
from __future__ import annotations

import glob
import os

import pytest
import yaml

from tools.schema_validator import validate_spec

CASES = sorted(glob.glob(os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "cases", "*", "spec.yaml")))


def _case(name):
    for path in CASES:
        if os.path.basename(os.path.dirname(path)) == name:
            return yaml.safe_load(open(path, encoding="utf-8"))
    raise AssertionError("case %r not found" % name)


@pytest.fixture
def spec():
    return _case("plate_hole_v2")


# --- the keys that are honoured must stay legal -----------------------------

@pytest.mark.parametrize("path", CASES, ids=[
    os.path.basename(os.path.dirname(p)) for p in CASES])
def test_every_shipped_case_still_validates(path):
    """The four undeclared-but-honoured keys (step / reducer / invariant /
    note) are used across twelve cases. Closing the object without declaring
    them first would have refused all of them."""
    ok, errors = validate_spec(yaml.safe_load(open(path, encoding="utf-8")))
    assert ok, errors[:3]


@pytest.mark.parametrize("key,value", [
    ("step", "Push"),
    ("step", 2),
    ("frame", "first"),
    ("frame", 3),
    ("reducer", "abs_max"),
    ("invariant", "TRESCA"),
    ("note", "why this number is what it is"),
])
def test_a_key_the_extractor_honours_is_accepted(spec, key, value):
    spec["outputs"]["kpis"][0][key] = value
    ok, errors = validate_spec(spec)
    assert ok, errors[:2]


# --- the keys that were dropped must be refused -----------------------------

@pytest.mark.parametrize("key,value", [
    ("numIntervals", 200),
    ("time_points", [0.1, 0.2]),
    ("paths", ["A-B"]),
    ("history", {"variable": "U2"}),
])
def test_an_unread_outputs_key_is_refused(spec, key, value):
    spec["outputs"][key] = value
    ok, errors = validate_spec(spec)
    assert not ok
    assert key in " ".join(errors)


@pytest.mark.parametrize("key,value", [
    ("time", 0.0021),
    ("envelope", True),
    ("nominal", 100.0),
])
def test_an_unread_kpi_key_is_refused(spec, key, value):
    """`time:` was the sharpest of these: it looks like a frame selector, it
    validated, and the extractor returned the last frame regardless."""
    spec["outputs"]["kpis"][0][key] = value
    ok, errors = validate_spec(spec)
    assert not ok
    assert key in " ".join(errors)


def test_an_invariant_the_extractor_cannot_compute_is_refused(spec):
    spec["outputs"]["kpis"][0]["invariant"] = "VON_MISES"
    ok, errors = validate_spec(spec)
    assert not ok


def test_a_reducer_that_does_not_exist_is_refused(spec):
    spec["outputs"]["kpis"][0]["reducer"] = "median"
    ok, errors = validate_spec(spec)
    assert not ok


# --- the enums here have to match the code that reads them ------------------

def test_the_invariant_enum_matches_the_extractor():
    """A schema that accepts a word the extractor cannot honour is worse than
    no schema: it moves the silent drop one layer down."""
    import importlib
    extract = importlib.import_module("post.extract_kpis")
    import json
    schema_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "schema", "spec_schema.json")
    schema = json.load(open(schema_path, encoding="utf-8"))
    declared = set(schema["properties"]["outputs"]["properties"]["kpis"]
                   ["items"]["properties"]["invariant"]["enum"])
    assert declared == set(extract._INVARIANT_ATTR)


def test_the_reducer_enum_matches_the_extractor():
    import importlib
    import inspect
    extract = importlib.import_module("post.extract_kpis")
    source = inspect.getsource(extract._reduce_values)
    import json
    schema_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "schema", "spec_schema.json")
    schema = json.load(open(schema_path, encoding="utf-8"))
    declared = schema["properties"]["outputs"]["properties"]["kpis"]["items"][
        "properties"]["reducer"]["enum"]
    for reducer in declared:
        assert 'mode == "%s"' % reducer in source, reducer
