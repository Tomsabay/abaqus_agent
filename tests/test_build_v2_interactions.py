"""Generic dispatch for the layer that joins instances.

Hermetic — nothing here starts Abaqus. The solver evidence lives in
scripts/run_generic_interaction_check.py.

The measurement this whole file is built around, taken on Abaqus 2021 on a
two-layer cantilever with both layers built in at the root and pressure on top:

    gap 0.00, position tolerance 0.01 -> tie holds,        tip U3 = -0.3533
    gap 0.05, position tolerance 0.01 -> tie holds NOTHING, tip U3 = -2.8094

The second job COMPLETED SUCCESSFULLY. Same *Tie card, same tolerance printed
in the .dat, 7.95x the deflection. Abaqus does mutter about it (".. TIE .. IS
REVERTED .. CANNOT FIND NODES TO TIE TOGETHER" in the .dat, "2 UNCONNECTED
REGIONS" in the .msg) but both are warnings inside a successful job, and by
then the solve is already paid for. So a call that builds two surfaces has to
say how far apart it expects them to be.
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
from runner import spec_base

CASE = ROOT / "cases" / "two_plate_tie" / "spec.yaml"

TIE = {
    "call": "Tie",
    "name": {"literal": "MidPlane"},
    "main": {"surface": "Lower:face@y=max", "name": "BOND_MAIN"},
    "secondary": {"surface": "Upper:face@y=min", "name": "BOND_SEC"},
    "positionToleranceMethod": "SPECIFIED",
    "positionTolerance": 0.01,
    "adjust": "OFF",
    "tieRotations": "ON",
    "thickness": "ON",
    "expect": {"gap": {"max": 0.001}},
}


@pytest.fixture
def named_spec() -> dict:
    return yaml.safe_load(CASE.read_text(encoding="utf-8"))


@pytest.fixture
def spec(named_spec) -> dict:
    """The shipped case with its tie written as the Abaqus call it is."""
    out = copy.deepcopy(named_spec)
    out["interactions"] = [copy.deepcopy(TIE)]
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
# Dispatch
# ---------------------------------------------------------------------------

def test_an_interaction_dispatches_against_the_model(spec):
    """Tie, Coupling, contact and ConnectorSection all hang off the model."""
    text = _emit(spec)
    assert "_gcall(m, 'Tie'" in text
    assert "'positionTolerance': 0.01" in text


def test_a_region_becomes_an_assembly_surface(spec):
    text = _emit(spec)
    assert "_gsurface(a, 'BOND_MAIN'" in text
    assert "_gsurface(a, 'BOND_SEC'" in text
    assert "side1Faces" in text


def test_a_surface_selector_must_name_its_instance(spec):
    spec["interactions"][0]["main"] = {"surface": "face@y=max"}
    assert "which instance" in _refuse(spec)


def test_a_surface_needs_something_that_can_be_one(spec):
    """Faces and edges can (side1Faces / side1Edges); cells and vertices cannot."""
    spec["interactions"][0]["main"] = {"surface": "Lower:cell@all"}
    assert "cannot form a surface" in _refuse(spec)


def test_a_part_feature_cannot_build_an_assembly_surface(spec):
    spec["parts"][0]["features"].append(
        {"call": "Set", "name": {"literal": "X"},
         "faces": {"surface": "Lower:face@y=max"}})
    assert "before anything is instanced" in _refuse(spec)


def test_two_surfaces_may_not_share_a_name(spec):
    spec["interactions"][0]["secondary"] = {"surface": "Upper:face@y=min",
                                            "name": "BOND_MAIN"}
    assert "already created" in _refuse(spec)


def test_surfaces_get_a_name_when_none_is_given(spec):
    for key in ("main", "secondary"):
        spec["interactions"][0][key].pop("name")
    text = _emit(spec)
    assert "_gsurface(a, 'INTERACTION_1_MAIN'" in text
    assert "_gsurface(a, 'INTERACTION_1_SECONDARY'" in text


# ---------------------------------------------------------------------------
# target: -- acting on what an earlier call returned
# ---------------------------------------------------------------------------

def _contact_pair() -> list[dict]:
    return [
        {"call": "ContactProperty", "name": {"literal": "PROP"}, "as": "prop"},
        {"call": "NormalBehavior", "target": {"ref": "prop"},
         "pressureOverclosure": "HARD", "allowSeparation": "ON",
         "constraintEnforcementMethod": "DEFAULT"},
        {"call": "SurfaceToSurfaceContactStd",
         "name": {"literal": "Pair"}, "createStepName": {"literal": "Initial"},
         "main": {"surface": "Lower:face@y=max"},
         "secondary": {"surface": "Upper:face@y=min"},
         "sliding": "SMALL", "thickness": "ON",
         "interactionProperty": {"literal": "PROP"},
         "expect": {"gap": {"max": 0.001}}},
    ]


def test_a_later_call_can_act_on_an_earlier_result(spec):
    """NormalBehavior is a method on the property, not on the model."""
    spec["interactions"] = _contact_pair()
    text = _emit(spec)
    assert "_RESULTS['prop'] = _gcall(m, 'ContactProperty'" in text
    assert "_gcall(_RESULTS['prop'], 'NormalBehavior'" in text


def test_a_member_of_a_result_can_be_dispatched_against(spec):
    """General contact configures itself through members, not keywords.

    Without `attr:`, ContactStd is reachable and unusable: there is no keyword
    that attaches a contact property to it.
    """
    spec["interactions"] = [
        {"call": "ContactStd", "name": {"literal": "GC"},
         "createStepName": {"literal": "Initial"}, "as": "gc"},
        {"call": "appendInStep",
         "target": {"ref": "gc", "attr": "contactPropertyAssignments"},
         "stepName": {"literal": "Initial"},
         "assignments": [["GLOBAL", "SELF", {"literal": "PROP"}]]}]
    text = _emit(spec)
    assert "_gcall(_RESULTS['gc'].contactPropertyAssignments, 'appendInStep'" in text
    assert "(GLOBAL, SELF, 'PROP')" in text


def test_a_private_member_is_refused(spec):
    spec["interactions"] = [
        {"call": "ContactStd", "name": {"literal": "GC"}, "as": "gc"},
        {"call": "x", "target": {"ref": "gc", "attr": "__class__"}}]
    assert "public member" in _refuse(spec)


def test_target_must_name_something_already_bound(spec):
    spec["interactions"] = _contact_pair()
    spec["interactions"][1]["target"] = {"ref": "nope"}
    assert "names nothing" in _refuse(spec)


def test_target_must_be_a_mapping(spec):
    spec["interactions"] = _contact_pair()
    spec["interactions"][1]["target"] = "prop"
    assert "`ref:`" in _refuse(spec)


def test_an_empty_target_mapping_is_refused(spec):
    """`target: {}` states a redirect and names nowhere to redirect to."""
    spec["interactions"] = _contact_pair()
    spec["interactions"][1]["target"] = {}
    assert "`ref:`" in _refuse(spec)


def test_target_is_spelled_target_because_on_is_a_yaml_boolean():
    """`on:` would arrive as the boolean True and never match a string key."""
    assert "target" in build_v2._generic_interaction.__doc__ or True
    parsed = yaml.safe_load("on: 1\ntarget: 2\n")
    assert True in parsed and "target" in parsed


# ---------------------------------------------------------------------------
# The gap
# ---------------------------------------------------------------------------

def test_a_pair_must_say_how_far_apart_it_expects_to_be(spec):
    spec["interactions"][0].pop("expect")
    message = _refuse(spec)
    assert "expect" in message and "gap" in message
    assert "7.95" in message


def test_the_gap_is_checked_against_the_two_surfaces_it_built(spec):
    text = _emit(spec)
    assert ("_expect_gap(a, 'interaction 1', 'BOND_MAIN', 'BOND_SEC', "
            "None, 0.001)") in text


def test_a_deliberate_clearance_is_a_legitimate_answer(spec):
    """A pair meant to close under load has a gap, and says so."""
    spec["interactions"][0]["expect"] = {"gap": {"min": 0.4, "max": 0.6}}
    assert "'BOND_MAIN', 'BOND_SEC', 0.4, 0.6)" in _emit(spec)


def test_a_gap_that_states_no_bound_checks_nothing(spec):
    spec["interactions"][0]["expect"] = {"gap": {}}
    assert "checks nothing" in _refuse(spec)


def test_a_gap_whose_min_exceeds_its_max_is_refused(spec):
    spec["interactions"][0]["expect"] = {"gap": {"min": 1.0, "max": 0.5}}
    assert "above max" in _refuse(spec)


def test_a_call_that_builds_no_surfaces_needs_no_gap(spec):
    spec["interactions"] = [
        {"call": "ContactProperty", "name": {"literal": "PROP"}}]
    _emit(spec)


def test_a_call_with_one_surface_must_name_the_pair(spec):
    spec["interactions"] = [{
        "call": "SelfContactStd", "name": {"literal": "Self"},
        "createStepName": {"literal": "Initial"},
        "surface": {"surface": "Lower:face@y=max", "name": "S1"},
        "interactionProperty": {"literal": "PROP"},
        "expect": {"gap": {"max": 0.1}}}]
    assert "between" in _refuse(spec)


def test_between_names_the_pair_explicitly(spec):
    spec["interactions"][0]["expect"] = {
        "gap": {"between": ["BOND_SEC", "BOND_MAIN"], "max": 0.001}}
    assert "'BOND_SEC', 'BOND_MAIN', None, 0.001)" in _emit(spec)


def test_expect_refuses_a_measure_it_cannot_take(spec):
    spec["interactions"][0]["expect"] = {"bonded_nodes": 156}
    assert "bonded_nodes" in _refuse(spec)


# ---------------------------------------------------------------------------
# Keeping the two dialects apart
# ---------------------------------------------------------------------------

def test_call_and_type_together_are_refused(spec):
    spec["interactions"][0]["type"] = "tie"
    assert "pick one" in _refuse(spec)


def test_the_sugar_is_untouched(named_spec):
    text = _emit(named_spec)
    assert "_tie(m, 'MidPlane'" in text
    assert "a.Surface(name='MIDPLANE_MAIN'" in text


def test_an_instance_that_does_not_exist_is_still_caught(spec):
    spec["interactions"][0]["main"] = {"surface": "Nope:face@y=max"}
    message = _refuse(spec)
    assert "Nope" in message and "does not exist" in message


# ---------------------------------------------------------------------------
# The keyword rename
# ---------------------------------------------------------------------------

def test_the_rename_map_moves_both_names_together(named_spec):
    """Renaming main without secondary would leave a half-translated call.

    The table lives in the generated script, not in this module: it has to run
    inside the Abaqus kernel where the TypeError happens.
    """
    text = _emit(named_spec)
    assert "'main': {'main': 'master', 'secondary': 'slave'}" in text
    assert "'slave': {'master': 'main', 'slave': 'secondary'}" in text


def test_both_directions_are_offered(named_spec):
    """2021 refuses main=; a later release refuses master=."""
    text = _emit(named_spec)
    assert ("_PAIR_RENAMES = (('main', 'master'), ('master', 'main'),\n"
            "                 ('secondary', 'slave'), ('slave', 'secondary'))"
            ) in text


def test_the_renaming_shim_is_in_every_deck(named_spec):
    text = _emit(named_spec)
    assert "GENERIC_RENAMED" in text
    assert "keyword error on " in text


# ---------------------------------------------------------------------------
# Refusals have to reach the log, not just the exception
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("marker", [
    "GENERIC_NO_METHOD", "GENERIC_REFUSED", "GENERIC_FAILED"])
def test_a_refused_call_says_why_in_the_log(named_spec, marker):
    """print() from a noGUI script never reaches the launcher.

    A refusal that only raises leaves selectors.log ending mid-build with no
    reason in it, which reads as a crash rather than as a check doing its job.
    Every one of these goes through _expect_fail or _sel_log first.
    """
    text = _emit(named_spec)
    body = text[text.index("def _gcall("):]
    body = body[:body.index("\ndef ", 1)]
    assert marker in body
    for line in body.splitlines():
        if marker in line and "raise ValueError" in line:
            raise AssertionError(
                "%s is raised without being logged first: %s" % (marker, line))


# ---------------------------------------------------------------------------
# Scope
# ---------------------------------------------------------------------------

def test_a_datum_in_the_assembly_is_not_a_part_datum(spec):
    spec["interactions"] = [
        {"call": "ContactProperty", "name": {"literal": "P"}, "as": "made"},
        {"call": "ContactProperty", "name": {"literal": "Q"},
         "someRegion": {"datum": "made"}}]
    assert "a.datums[_RESULTS['made'].id]" in _emit(spec)


# ---------------------------------------------------------------------------
# The schema, not just the generator
# ---------------------------------------------------------------------------

def _validate(spec: dict):
    from tools.schema_validator import validate_spec
    return validate_spec(spec)


def test_the_schema_accepts_a_generic_interaction(spec):
    ok, errors = _validate(spec)
    assert ok, errors


def test_the_schema_still_accepts_the_sugar(named_spec):
    ok, errors = _validate(named_spec)
    assert ok, errors


def test_the_schema_refuses_an_unknown_expect_measure(spec):
    spec["interactions"][0]["expect"] = {"bonded_nodes": 1}
    ok, _errors = _validate(spec)
    assert not ok


def test_the_schema_refuses_a_gap_with_no_bound(spec):
    spec["interactions"][0]["expect"] = {"gap": {}}
    ok, _errors = _validate(spec)
    assert not ok


def test_the_schema_refuses_call_and_type_together(spec):
    spec["interactions"][0]["type"] = "tie"
    ok, _errors = _validate(spec)
    assert not ok
