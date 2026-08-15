"""The connector layer: wires, sections, and the order they have to happen in.

Hermetic — nothing here starts Abaqus. The solver evidence lives in
scripts/run_generic_connector_check.py.

Two measurements shape this file, both on Abaqus 2021, two blocks joined at
their four corners by axial springs of k = 25 and pulled with 1000 N:

    4 wires, 4 sections assigned -> U3 = 10.0019   (F/k = 10.000)
    4 wires, 3 sections assigned -> U3 = 13.3357   (F/k = 13.333)

The second job COMPLETED with no error and no warning. One missing section
assignment is a quarter of the stiffness gone, and the wire is still there in
the model tree, still drawn, still selectable.

And the ordering, also measured: assigning a section that does not exist yet
raises `ValueError: The section "Spring" does not exist in the model.` Since
`interactions:` is emitted after the assembly and SectionAssignment lives in
assembly.operations, a ConnectorSection declared there would always be too
late. Hence `model_setup:`.
"""

from __future__ import annotations

import ast
import copy
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from runner import build_v2  # noqa: E402
from runner import arg_forms
from runner import spec_base

CASE = ROOT / "cases" / "two_plate_tie" / "spec.yaml"

SECTION = [
    {"call": "ConnectorSection", "name": {"literal": "Spring"},
     "translationalType": "AXIAL", "as": "spring"},
    {"call": "setValues", "target": {"ref": "spring"},
     "behaviorOptions": [{"new": "connectorBehavior.ConnectorElasticity",
                          "behavior": "LINEAR", "components": [1],
                          "table": [[25.0]]}]},
]
WIRE_OPS = [
    {"call": "WirePolyLine",
     "points": [[{"vertex": {"instance": "Lower", "at": [0.0, 5.0, 0.0]}},
                 {"vertex": {"instance": "Upper", "at": [0.0, 5.0, 0.0]}}]],
     "mergeType": "IMPRINT", "meshable": "OFF"},
    {"call": "Set", "name": {"literal": "W0"},
     "edges": {"wire_at": [[0.0, 5.0, 0.0], [0.0, 5.0, 100.0]]}, "as": "w0"},
    {"call": "SectionAssignment", "region": {"ref": "w0"},
     "sectionName": {"literal": "Spring"}},
]


@pytest.fixture
def named_spec() -> dict:
    return yaml.safe_load(CASE.read_text(encoding="utf-8"))


@pytest.fixture
def spec(named_spec) -> dict:
    out = copy.deepcopy(named_spec)
    out["model_setup"] = copy.deepcopy(SECTION)
    out["assembly"]["operations"] = copy.deepcopy(WIRE_OPS)
    return out


def _emit(spec: dict) -> str:
    text = build_v2.generate_script(spec)
    ast.parse(text)
    return text


def _refuse(spec: dict) -> str:
    with pytest.raises(spec_base.SpecError) as caught:
        build_v2.generate_script(spec)
    return str(caught.value)


# ---------------------------------------------------------------------------
# model_setup: the ordering slot
# ---------------------------------------------------------------------------

def test_model_setup_dispatches_against_the_model(spec):
    text = _emit(spec)
    assert "_RESULTS['spring'] = _gcall(m, 'ConnectorSection'" in text
    assert "_gcall(_RESULTS['spring'], 'setValues'" in text


def test_model_setup_runs_before_the_parts(spec):
    """A SectionAssignment naming a section that does not exist yet raises."""
    text = _emit(spec)
    assert text.index("ConnectorSection") < text.index("# --- Parts")
    assert text.index("# --- Model setup") < text.index("# --- Parts")


def test_model_setup_refuses_a_selector(spec):
    spec["model_setup"].append(
        {"call": "Set", "name": {"literal": "X"},
         "faces": {"select": "Lower:face@y=max"}})
    message = _refuse(spec)
    assert "before any part or instance exists" in message


def test_model_setup_refuses_an_expect_block(spec):
    spec["model_setup"][0]["expect"] = {"gap": {"max": 1.0}}
    assert "nothing here to measure" in _refuse(spec)


def test_model_setup_needs_a_call(spec):
    spec["model_setup"].append({"name": {"literal": "X"}})
    assert "has no `call`" in _refuse(spec)


def test_model_setup_refuses_a_datum_reference(spec):
    spec["model_setup"].append(
        {"call": "X", "region": {"datum": "spring"}})
    assert "before any part" in _refuse(spec)


# ---------------------------------------------------------------------------
# The two new argument forms
# ---------------------------------------------------------------------------

def test_a_wire_endpoint_is_a_counted_vertex_of_an_instance(spec):
    """Bare coordinates are accepted by Abaqus and attach to nothing.

    Measured: the solver then says "CONNECTOR ELEMENT 1 (ASSEMBLY) NODE NUMBERS
    CANNOT BE BOTH ZERO". Nothing at build time distinguishes the two, so the
    spec cannot write the coordinate form.
    """
    text = _emit(spec)
    assert "_gvertex(a, 'Lower', (0.0, 5.0, 0.0)" in text
    assert "_gvertex(a, 'Upper', (0.0, 5.0, 0.0)" in text


def test_a_vertex_is_meaningless_outside_the_assembly(spec):
    spec["parts"][0]["features"].append(
        {"call": "Set", "name": {"literal": "X"},
         "vertices": {"vertex": {"instance": "Lower", "at": [0.0, 0.0, 0.0]}}})
    assert "only exists in the assembly" in _refuse(spec)


@pytest.mark.parametrize("body", [
    {"instance": "Lower"},
    {"at": [0.0, 0.0, 0.0]},
    {"instance": "Lower", "at": [0.0, 0.0]},
    "Lower",
])
def test_a_malformed_vertex_is_refused(spec, body):
    spec["assembly"]["operations"][0]["points"] = [[{"vertex": body},
                                                    {"vertex": body}]]
    _refuse(spec)


def test_a_wire_is_found_between_the_points_that_made_it(spec):
    """Wire edges are on the assembly, not on any instance."""
    text = _emit(spec)
    assert "_gwire(a, (0.0, 5.0, 0.0), (0.0, 5.0, 100.0)" in text


def test_a_wire_of_zero_length_is_refused(spec):
    spec["assembly"]["operations"][1]["edges"] = {
        "wire_at": [[0.0, 5.0, 0.0], [0.0, 5.0, 0.0]]}
    assert "same point twice" in _refuse(spec)


def test_a_wire_is_meaningless_in_a_part(spec):
    spec["parts"][0]["features"].append(
        {"call": "Set", "name": {"literal": "X"},
         "edges": {"wire_at": [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]]}})
    assert "lives on the assembly" in _refuse(spec)


# ---------------------------------------------------------------------------
# The module the deck did not import
# ---------------------------------------------------------------------------

def test_the_elasticity_module_is_imported(spec):
    assert "connectorBehavior" in arg_forms._IMPORT_LINE
    assert "connectorBehavior" in arg_forms._MODULES
    text = _emit(spec)
    assert "_gnew('connectorBehavior', 'ConnectorElasticity'" in text


def test_the_runtime_module_table_is_generated_not_retyped(spec):
    """Spelled twice they drift, and the drift is a KeyError in the kernel."""
    text = _emit(spec)
    for name in arg_forms._MODULES:
        assert "%r: %s" % (name, name) in text


# ---------------------------------------------------------------------------
# The check
# ---------------------------------------------------------------------------

def test_every_wire_is_checked_for_a_section(spec):
    assert "_expect_connectors(m, a, None)" in _emit(spec)


def test_the_wire_count_can_be_stated(spec):
    spec["assembly"]["expect"] = {"wires": 4}
    assert "_expect_connectors(m, a, 4)" in _emit(spec)


def test_a_spec_with_no_assembly_operations_gets_no_wire_check(named_spec):
    """Only WirePolyLine makes assembly edges, and it is an operation.

    This is also what keeps the four shipped cases generating what they did.
    """
    text = _emit(named_spec)
    assert "_expect_connectors" not in text.split("# --- Assembly")[1]


def test_the_check_refuses_a_measure_it_cannot_take(spec):
    spec["assembly"]["expect"] = {"wires": 1, "torque": 5.0}
    assert "torque" in _refuse(spec)


# ---------------------------------------------------------------------------
# The schema, not just the generator
# ---------------------------------------------------------------------------

def _validate(spec: dict):
    from tools.schema_validator import validate_spec
    return validate_spec(spec)


def test_the_schema_accepts_the_connector_spec(spec):
    ok, errors = _validate(spec)
    assert ok, errors


def test_the_schema_accepts_a_wire_count(spec):
    spec["assembly"]["expect"] = {"wires": 4}
    ok, errors = _validate(spec)
    assert ok, errors


def test_the_schema_refuses_a_negative_wire_count(spec):
    spec["assembly"]["expect"] = {"wires": -1}
    ok, _errors = _validate(spec)
    assert not ok


def test_the_schema_requires_a_call_in_model_setup(spec):
    spec["model_setup"] = [{"name": {"literal": "X"}}]
    ok, _errors = _validate(spec)
    assert not ok
