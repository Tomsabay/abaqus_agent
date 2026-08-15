"""The control point a Coupling, a RigidBody and an MPC each need.

Nothing in this dialect could produce one. Measured on Abaqus 2021
(artifacts/probe_rp), the round trip is three objects deep and none of them is
nameable from a spec:

    a.ReferencePoint(point=...)     -> a Feature, not a point
    a.referencePoints[feature.id]   -> the ReferencePoint
    a.Set(referencePoints=(rp,))    -> the Region a constraint actually takes

and the deck names the set: `*Coupling, constraint name=Cpl, ref node=RP,
surface=TIPFACE`.

Two misuses were measured and both are LOUD, so nothing here refuses them: a
coupling onto a surface with zero faces dies with 6 fatal errors, and one whose
control point is a face set dies with 74. Neither reaches a wrong answer.

The one that is quiet is the position. Same bar, same 100 N on the reference
point, only the point moved, read two ways because the reference point is
itself a node and the two readings come apart (beam theory -0.19047619):

                               whole model      tip face only
    (5, 5, 100) centre of      -0.18944125      -0.18944125     0.5% out
                the tip face
    (5, 5, 150) 50 mm past     -0.61471903      -0.33120051     223% / 74%
                the end

The second row reported 0 errors, 0 warnings and COMPLETED, and note which
column a spec gets: `location: whole_model` is answered about the reference
point, a node that is not part of the structure. It is not refused -- an offset
control point is also how a moment is applied, and the deliberate one and the
mistaken one look identical from here -- so the form offers `{at:}` to remove
the arithmetic and the kernel logs the position either way.

Both rows are measured by scripts/run_reference_point_check.py rather than by
anything here, which is the point: this file pins that the numbers reached the
source, and the gate is what keeps them true.
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from runner import (
    build_v2,  # noqa: E402
    kernel_runtime,
    spec_base,
)

CASE = ROOT / "cases" / "two_plate_tie" / "spec.yaml"


@pytest.fixture
def spec() -> dict:
    return yaml.safe_load(CASE.read_text(encoding="utf-8"))


def _coupling(**overrides) -> dict:
    call = {
        "call": "Coupling",
        "name": {"literal": "Cpl"},
        "controlPoint": {"reference_point": [5.0, 5.0, 100.0],
                         "name": "RP_TIP"},
        "surface": {"surface": "Lower:face@z=max", "name": "TOPFACE",
                    "expect": "=1"},
        "influenceRadius": "WHOLE_SURFACE",
        "couplingType": "KINEMATIC",
        "u1": "ON", "u2": "ON", "u3": "ON",
    }
    call.update(overrides)
    return call


def _with(spec: dict, call: dict, block: str = "conditions") -> dict:
    out = copy.deepcopy(spec)
    out[block] = list(out.get(block) or []) + [call]
    return out


def _emit(spec: dict) -> str:
    return build_v2.generate_script(spec)


def _refuse(spec: dict) -> str:
    with pytest.raises(spec_base.SpecError) as excinfo:
        build_v2.generate_script(spec)
    return str(excinfo.value)


def _line(text: str, needle: str) -> str:
    for line in text.splitlines():
        if needle in line and not line.startswith("def "):
            return line
    return ""


# --- the form -------------------------------------------------------------

def test_three_numbers_become_a_named_set_over_one_reference_point(spec):
    line = _line(_emit(_with(spec, _coupling())), "_grp(a, 'RP_TIP'")
    assert "_grp(a, 'RP_TIP', (5.0, 5.0, 100.0), 'condition" in line
    assert "'controlPoint': _grp(" in line, (
        "the set has to be the argument itself -- a reference point created "
        "beside the call and not handed to it is the silent shape this layer "
        "exists to avoid")


def test_the_set_name_is_what_the_deck_carries(spec):
    """`ref node=` names the set, so the name is not bookkeeping.

    Measured: `*Coupling, constraint name=Cpl, ref node=RP, surface=TIPFACE`.
    """
    text = _emit(_with(spec, _coupling(
        controlPoint={"reference_point": [1.0, 2.0, 3.0], "name": "HUB"})))
    assert "_grp(a, 'HUB'" in text


def test_a_name_is_derived_when_none_is_given(spec):
    text = _emit(_with(spec, _coupling(
        controlPoint={"reference_point": [1.0, 2.0, 3.0]})))
    assert "_grp(a, 'CONDITION_1_CONTROLPOINT'" in text


def test_at_a_selector_places_it_without_arithmetic(spec):
    """The form that makes the silent error unreachable for the common case."""
    text = _emit(_with(spec, _coupling(
        controlPoint={"reference_point": {"at": "Lower:face@z=max"},
                      "name": "RP_MID"})))
    line = _line(text, "_grp(a, 'RP_MID'")
    assert "_rp_centroid(" in line
    assert "_gone(" in line, "the centroid needs one entity, not a sequence"
    assert "'=1'" in line, "which is the existing count assertion, not a new one"


def test_the_at_selector_must_name_its_instance(spec):
    message = _refuse(_with(spec, _coupling(
        controlPoint={"reference_point": {"at": "face@z=max"}})))
    assert "which instance" in message


def test_at_is_the_only_key_the_mapping_form_takes(spec):
    message = _refuse(_with(spec, _coupling(
        controlPoint={"reference_point": {"at": "Lower:face@z=max",
                                          "tol": 0.1}})))
    assert "Give three numbers" in message


def test_two_numbers_are_refused(spec):
    message = _refuse(_with(spec, _coupling(
        controlPoint={"reference_point": [1.0, 2.0]})))
    assert "must be three numbers" in message


def test_expect_beside_it_is_refused(spec):
    """The count is fixed at one by the form; an `expect` either repeats or
    contradicts it, exactly as with `{one:}`."""
    message = _refuse(_with(spec, _coupling(
        controlPoint={"reference_point": [1.0, 2.0, 3.0], "expect": "=1"})))
    assert "only `name` belongs there" in message


def test_two_reference_points_cannot_share_a_name(spec):
    message = _refuse(_with(spec, _coupling(
        controlPoint={"reference_point": [1.0, 2.0, 3.0], "name": "RP"},
        surface={"set": "Lower:face@z=max", "name": "RP", "expect": "=1"})))
    assert "already created" in message


def test_a_part_feature_cannot_make_one(spec):
    """A reference point is created on the assembly, which does not exist yet
    while a part is being shaped."""
    out = copy.deepcopy(spec)
    out["parts"][0]["features"].append(
        {"call": "Something", "point": {"reference_point": [0.0, 0.0, 0.0]}})
    assert "belongs in an interaction, a step or a condition" in _refuse(out)


# --- naming it back -------------------------------------------------------
#
# The asymmetry that forced a second form. Every other region form re-finds its
# region by geometry, so two calls on the same face just write the selector
# twice. A reference point cannot be re-found -- it is on no face and no edge
# -- so without `{named_set:}` a coupling could be created and then never
# loaded, and loading the control point is the only reason to create one.

def _force(**overrides) -> dict:
    call = {"call": "ConcentratedForce", "name": {"literal": "Tip"},
            "createStepName": {"literal": "Load"},
            "region": {"named_set": "RP_TIP"}, "cf2": -100.0}
    call.update(overrides)
    return call


def test_a_later_call_can_act_on_the_point_an_earlier_one_made(spec):
    out = _with(_with(spec, _coupling()), _force())
    line = _line(_emit(out), "ConcentratedForce")
    assert "'region': _gnamed(a, 'RP_TIP', 'condition 2')" in line


def test_the_name_is_folded_the_same_way_both_ends(spec):
    """`{set:}` and `{reference_point:}` both upper-case what they store, so a
    spec writing `name: rp` there and `named_set: rp` here has to land on the
    same set rather than on a missing one."""
    out = _with(_with(spec, _coupling(
        controlPoint={"reference_point": [5.0, 5.0, 100.0], "name": "rp"})),
        _force(region={"named_set": "rp"}))
    text = _emit(out)
    assert "_grp(a, 'RP'" in text
    assert "_gnamed(a, 'RP'" in text


def test_an_empty_name_is_refused(spec):
    for bad in ("", "   ", 7, None):
        message = _refuse(_with(spec, _force(region={"named_set": bad})))
        assert "must name a set as a string" in message


def test_a_name_abaqus_cannot_use_is_refused(spec):
    assert "which Abaqus cannot use" in _refuse(
        _with(spec, _force(region={"named_set": "not a name"})))


def test_nothing_else_belongs_beside_it(spec):
    """An `expect:` here would be asserting a count on somebody else's call."""
    message = _refuse(_with(spec, _force(
        region={"named_set": "RP_TIP", "expect": "=1"})))
    assert "nothing else belongs there" in message


def test_a_part_feature_cannot_name_an_assembly_set(spec):
    out = copy.deepcopy(spec)
    out["parts"][0]["features"].append(
        {"call": "Something", "region": {"named_set": "RP_TIP"}})
    assert "belongs in an interaction, a step or a condition" in _refuse(out)


def test_the_kernel_is_where_a_missing_name_is_caught():
    """Not an oversight -- the set registry is built per call, so no stage on
    the generator side can see across two of them. The kernel is holding the
    assembly and can answer with the names that are actually there."""
    assert "NAMED_SET_MISSING" in kernel_runtime._HELPERS
    assert "sorted(a.sets.keys())" in kernel_runtime._HELPERS


def test_a_surface_by_that_name_gets_its_own_answer():
    """Reachable and confusing: `{surface:}` and `{set:}` both take a `name:`,
    so the same string can exist as a surface while the set does not."""
    assert "NAMED_SET_IS_A_SURFACE" in kernel_runtime._HELPERS
    assert "a surface is faces and a set is nodes" in kernel_runtime._HELPERS.lower()


# --- what the kernel does with it -----------------------------------------

def test_the_helper_refuses_a_set_that_is_not_exactly_one_point():
    assert "REFERENCE_POINT_NOT_ONE" in kernel_runtime._HELPERS
    assert "each control exactly" in kernel_runtime._HELPERS


def test_the_helper_logs_the_position(spec):
    """Not a refusal -- a record.

    An offset control point is how a moment is applied, so the deliberate one
    and the mistaken one are indistinguishable here. What the log can do is
    make "which point was it?" answerable without a re-run.
    """
    assert "REFERENCE_POINT_OK" in kernel_runtime._HELPERS
    assert "at (%.6g, %.6g, %.6g)" in kernel_runtime._HELPERS


def test_the_measured_counterexample_is_written_down():
    """The wrong answer is the reason `{at:}` exists, so it lives in the source.

    A design decision whose evidence is only in a chat log is a decision
    nobody can re-check. Both columns, because they are different numbers
    about the same run and the one a spec actually receives is the worse of
    the two -- a source note carrying only -0.33120051 would understate what
    `location: whole_model` hands back.
    """
    assert "-0.33120051" in kernel_runtime._HELPERS
    assert "-0.61471903" in kernel_runtime._HELPERS
    assert "0 errors, 0 warnings and COMPLETED" in kernel_runtime._HELPERS


def test_the_centroid_is_labelled_an_estimate():
    """getCentroid() is a tessellation estimate, measured at 0.070931 mm off
    on a bore of r = 300 elsewhere in this file. Placing a point is a modelling
    decision rather than a measurement, so it is used -- and said."""
    assert "TESSELLATION ESTIMATE" in kernel_runtime._HELPERS


# --- the shipped decks must not move --------------------------------------

def test_a_spec_with_no_reference_point_emits_none(spec):
    assert "_grp(a," not in _emit(spec).split("# --- Materials")[1]
