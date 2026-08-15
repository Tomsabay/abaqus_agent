"""Steps and conditions as dispatched Abaqus calls, and the two gates on them.

Hermetic — nothing here starts Abaqus. The solver evidence lives in
scripts/run_generic_load_check.py.

Three measurements shape this file, all on Abaqus 2021, the 10x10x100 C3D8I
cantilever encastred at z = 0:

  1. `cf2=-100` on a set of the four tip corners: tip -0.7584553, total reaction
     400 N, job COMPLETED, no warning. The same call with -25 on the same four
     nodes: -0.1896138, which is P L^3 / (3 E I) for P = 100 N to 0.45%. The
     magnitude is written PER NODE, so the number in the spec is not the load
     unless the set holds exactly one node.

  2. A ConcentratedForce on a FACE-based set is refused by CAE at submit
     ("contains invalid geometry or mesh components for the load type"). This
     pipeline never asks CAE: the deck calls writeInput(consistencyChecking=OFF)
     and the card comes out as `*Cload / TIP, 2, -100.` against a four-node
     Nset. So the check cannot live at generation time, and cannot rely on
     CAE's own guard either — it reads the input file back.

  3. Two StaticSteps that both declare `previous: 'Initial'` are BOTH accepted,
     and the second is inserted BEFORE the first: m.steps comes out
     ('Initial', 'Two', 'One'), the .inp agrees, and the job COMPLETES. A
     preload-then-load analysis written in the obvious order runs backwards and
     nothing says so.
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
    kernel_runtime,
    spec_base,
)

CASE = ROOT / "cases" / "two_plate_tie" / "spec.yaml"


@pytest.fixture
def named_spec() -> dict:
    """A shipped spec: named steps, named loads, no dispatch anywhere."""
    return yaml.safe_load(CASE.read_text(encoding="utf-8"))


@pytest.fixture
def spec(named_spec) -> dict:
    """The same model with the step and both conditions dispatched."""
    out = copy.deepcopy(named_spec)
    instance = out["assembly"]["instances"][0]["name"]
    out["steps"] = [{"call": "StaticStep", "name": {"literal": "Press"},
                     "previous": {"literal": "Initial"}}]
    out["conditions"] = [
        {"call": "EncastreBC", "name": {"literal": "Fix"},
         "createStepName": {"literal": "Initial"},
         "region": {"set": "%s:face@z=min" % instance, "name": "FIX",
                    "expect": "=1"}},
        {"call": "Pressure", "name": {"literal": "Top"},
         "createStepName": {"literal": "Press"},
         "region": {"surface": "%s:face@y=max" % instance, "name": "TOP",
                    "expect": "=1"},
         "magnitude": 0.1},
    ]
    return out


def _emit(spec: dict) -> str:
    text = build_v2.generate_script(spec)
    ast.parse(text)
    return text


def _refuse(spec: dict) -> str:
    with pytest.raises(spec_base.SpecError) as caught:
        build_v2.generate_script(spec)
    return str(caught.value)


def _force(spec: dict, **extra) -> dict:
    """Replace the pressure with a concentrated force on the tip corners."""
    out = copy.deepcopy(spec)
    instance = out["assembly"]["instances"][0]["name"]
    entry = {"call": "ConcentratedForce", "name": {"literal": "Tip"},
             "createStepName": {"literal": "Press"},
             "region": {"set": "%s:vertex@z=max" % instance, "name": "TIP",
                        "expect": "=4"},
             "cf2": -25.0}
    entry.update(extra)
    out["conditions"][1] = entry
    return out


def _deck(text: str) -> str:
    """The model the spec asked for, without the helper block above it.

    Every gate is DEFINED in the preamble of every deck, so searching the whole
    file for `_expect_steps(` finds the definition and says nothing about
    whether this spec is guarded. The distinction matters in both directions:
    one of these tests exists to prove a deck does NOT carry an assertion.
    """
    marker = "\n# --- Material"
    return text[text.index(marker):] if marker in text else text


def _helper(name: str) -> str:
    """One runtime helper's source, out of the block every deck carries."""
    body = kernel_runtime._HELPERS.split("def %s(" % name)[1]
    return body.split("\ndef ")[0]


def _body(text: str, marker: str) -> str:
    """The generated line carrying `marker`, wrapped continuations joined."""
    lines = _deck(text).splitlines()
    for i, line in enumerate(lines):
        if marker in line:
            out = [line]
            while out[-1].rstrip().endswith(("(", ",")) and i + len(out) < len(lines):
                out.append(lines[i + len(out)])
            return " ".join(part.strip() for part in out)
    return ""


# ---------------------------------------------------------------------------
# A step is a call like any other
# ---------------------------------------------------------------------------

def test_a_dispatched_step_becomes_the_method_it_names(spec):
    assert "_gcall(m, 'StaticStep'" in _emit(spec)


def test_a_step_type_the_enumerated_block_never_had(spec):
    """The reason the layer exists: Static was the only word it knew."""
    out = copy.deepcopy(spec)
    out["steps"] = [{"call": "FrequencyStep", "name": {"literal": "Modes"},
                     "previous": {"literal": "Initial"}, "numEigen": 5}]
    out["conditions"] = [out["conditions"][0]]
    text = _emit(out)
    assert "_gcall(m, 'FrequencyStep'" in text
    assert "'numEigen': 5" in text


def test_the_named_shorthand_still_generates_what_it_did(named_spec):
    assert "m.StaticStep(name=" in _emit(named_spec)


def test_a_step_cannot_be_both_forms_at_once(spec):
    out = copy.deepcopy(spec)
    out["steps"][0]["type"] = "Static"
    assert "pick one" in _refuse(out)


@pytest.mark.parametrize("key", ["bcs", "loads"])
def test_a_dispatched_step_cannot_carry_its_own_conditions(spec, key):
    out = copy.deepcopy(spec)
    out["steps"][0][key] = []
    message = _refuse(out)
    assert "conditions:" in message and key in message


def test_expect_on_a_step_has_nothing_to_measure(spec):
    out = copy.deepcopy(spec)
    out["steps"][0]["expect"] = {"points": 1}
    assert "nothing to measure" in _refuse(out)


def test_a_step_needs_a_name_this_side_can_read(spec):
    """Not decoration: the order check compares against it."""
    out = copy.deepcopy(spec)
    instance = out["assembly"]["instances"][0]["name"]
    out["steps"][0]["name"] = {"select": "%s:face@z=min" % instance}
    assert "order it runs in" in _refuse(out)


def test_an_all_caps_argument_is_a_symbol_not_a_string(spec):
    out = copy.deepcopy(spec)
    out["steps"][0]["matrixStorage"] = "UNSYMMETRIC"
    assert "'matrixStorage': UNSYMMETRIC" in _emit(out)


# ---------------------------------------------------------------------------
# Step order — measured, not assumed
# ---------------------------------------------------------------------------

def test_the_order_the_spec_wrote_is_asserted(spec):
    out = copy.deepcopy(spec)
    out["steps"].append({"call": "StaticStep", "name": {"literal": "Release"},
                         "previous": {"literal": "Press"}})
    assert "_expect_steps(m, ('Press', 'Release'))" in _emit(out)


def test_the_named_shorthand_gets_no_order_assertion(named_spec):
    """It chains `previous` itself, so its order cannot come out wrong."""
    assert "_expect_steps(" not in _deck(_emit(named_spec))


def test_the_two_steps_that_both_follow_initial_are_still_emitted(spec):
    """Refusing them here would be guessing. They are checked at run time.

    Both really are legal Abaqus; what is not legal is the spec's belief about
    which one runs first. That belief is only checkable against m.steps.
    """
    out = copy.deepcopy(spec)
    out["steps"] = [{"call": "StaticStep", "name": {"literal": "One"},
                     "previous": {"literal": "Initial"}},
                    {"call": "StaticStep", "name": {"literal": "Two"},
                     "previous": {"literal": "Initial"}}]
    text = _emit(out)
    assert text.count("_gcall(m, 'StaticStep'") == 2
    assert "_expect_steps(m, ('One', 'Two'))" in text


def test_the_order_assertion_logs_before_it_raises():
    """print() from a noGUI script never reaches the launcher.

    A refusal that only prints is a refusal nobody sees; the launcher returns 0
    either way. Every gate here logs to selectors.log first.
    """
    body = _helper("_expect_steps")
    assert "_expect_fail(" in body and "print(" not in body


# ---------------------------------------------------------------------------
# Conditions: BCs, loads and fields in one block, because Abaqus has one
# ---------------------------------------------------------------------------

def test_a_condition_becomes_the_method_it_names(spec):
    text = _emit(spec)
    assert "_gcall(m, 'EncastreBC'" in text
    assert "_gcall(m, 'Pressure'" in text


def test_a_condition_without_a_call_says_what_a_call_looks_like(spec):
    out = copy.deepcopy(spec)
    out["conditions"][0] = {"type": "encastre", "region": "Plate:face@z=min"}
    message = _refuse(out)
    assert "no `call`" in message and "EncastreBC" in message


def test_conditions_are_emitted_after_every_step(spec):
    """So `createStepName:` can name any step, not only earlier ones."""
    text = _emit(spec)
    assert text.index("_gcall(m, 'StaticStep'") < text.index("_gcall(m, 'EncastreBC'")


def test_a_spec_with_no_conditions_block_gains_no_empty_section(named_spec):
    assert "# --- Conditions" not in _emit(named_spec)


def test_the_set_is_built_inline_in_the_call_that_needs_it(spec):
    """Once, as the region argument — not built here and looked up there."""
    assert _deck(_emit(spec)).count("_gset(a, 'FIX'") == 1


def test_the_set_is_passed_by_name_not_rebuilt(spec):
    assert "'region': _gset(a, 'FIX'" in _body(_emit(spec), "_gcall(m, 'EncastreBC'")


def test_a_surface_region_still_works_in_a_condition(spec):
    assert "_gsurface(a, 'TOP'" in _emit(spec)


def test_a_set_selector_must_say_which_instance(spec):
    out = copy.deepcopy(spec)
    out["conditions"][0]["region"] = {"set": "face@z=min", "name": "FIX"}
    assert "which instance" in _refuse(out)


def test_a_set_carries_only_expect_and_name(spec):
    out = copy.deepcopy(spec)
    out["conditions"][0]["region"]["side"] = "SIDE1"
    message = _refuse(out)
    assert "side" in message and "only `expect` and `name`" in message


def test_two_sets_of_the_same_name_in_one_call_are_refused(spec):
    out = copy.deepcopy(spec)
    instance = out["assembly"]["instances"][0]["name"]
    out["conditions"][0]["localCsys"] = {"set": "%s:face@z=max" % instance,
                                         "name": "FIX"}
    assert "already created" in _refuse(out)


def test_a_set_name_abaqus_cannot_use_is_refused(spec):
    out = copy.deepcopy(spec)
    out["conditions"][0]["region"]["name"] = "fix-me"
    assert "cannot use" in _refuse(out)


def test_a_set_in_a_part_feature_is_built_on_the_part(named_spec):
    """Parts have sets of their own, and #70 is what put them there.

    This used to be refused with "belongs in a step or a condition", on the
    belief that a set needed an assembly to hang on. Measured on Abaqus 2021
    (artifacts/probe_seam2), a part set is `p.Set(...)`, it is a different
    object from an assembly set, and it is the only thing
    `engineeringFeatures.assignSeam` will accept -- so the refusal was closing
    the one route that works.

    The distinction that remains is `{select:}` versus `{set:}`, which is
    about what the called method takes, not about where the call lives.
    """
    out = copy.deepcopy(named_spec)
    out["parts"][0]["features"].append(
        {"call": "Round", "radius": 1.0,
         "edgeList": {"set": "edge@z=max", "name": "R"}})
    # A generic call in a part demands an `expect:` block, which is a separate
    # gate and not the one under test here.
    out["parts"][0]["expect"] = {"cells": 1}
    line = [ln for ln in _emit(out).splitlines() if "'Round'" in ln][0]
    assert "_gset(p, 'R'" in line
    assert "_gset(a," not in line


def test_a_part_set_naming_an_instance_says_what_to_write(named_spec):
    """The other half: instances do not exist while part features run."""
    out = copy.deepcopy(named_spec)
    out["parts"][0]["features"].append(
        {"call": "Round", "radius": 1.0,
         "edgeList": {"set": "Plate:edge@z=max", "name": "R"}})
    message = _refuse(out)
    assert "names an instance" in message
    assert "'edge@z=max'" in message, (
        "a refusal that does not show the corrected string makes the reader "
        "guess which half to delete")


# ---------------------------------------------------------------------------
# expect.points — the count checked in CAE, before the job is written
# ---------------------------------------------------------------------------

def test_a_stated_point_count_is_checked_against_the_set(spec):
    text = _emit(_force(spec, expect={"points": 4}))
    assert "_expect_points(a, 'TIP', 4, 'condition 2')" in text


def test_a_condition_may_leave_the_count_unstated(spec):
    """Deliberately optional. Which calls write a per-node card is Abaqus's
    business, so the requirement is enforced against the .inp instead."""
    assert "_expect_points(" not in _deck(_emit(_force(spec)))


@pytest.mark.parametrize("bad", [0, -1, 1.5, "4", True, None])
def test_a_point_count_must_be_a_whole_number_of_nodes(spec, bad):
    """True included on purpose: bool is an int, and `points: yes` is YAML."""
    assert "whole number" in _refuse(_force(spec, expect={"points": bad}))


def test_expect_takes_points_and_nothing_else(spec):
    out = _force(spec, expect={"points": 4, "nodes": 4})
    assert "and nothing else" in _refuse(out)


def test_an_empty_expect_is_refused(spec):
    assert "is empty" in _refuse(_force(spec, expect={}))


def test_a_point_count_with_no_set_to_count_is_refused(spec):
    """Gravity has no region at all, so there is nothing for `points` to mean."""
    out = copy.deepcopy(spec)
    out["conditions"][1] = {"call": "Gravity", "name": {"literal": "G"},
                            "createStepName": {"literal": "Press"},
                            "comp2": -9810.0, "expect": {"points": 1}}
    assert "it builds none" in _refuse(out)


def test_a_point_count_with_two_sets_does_not_say_which(spec):
    out = _force(spec, expect={"points": 4})
    instance = out["assembly"]["instances"][0]["name"]
    out["conditions"][1]["localCsys"] = {"set": "%s:face@z=max" % instance,
                                         "name": "OTHER"}
    assert "does not say which one" in _refuse(out)


# ---------------------------------------------------------------------------
# _expect_cload — the input file Abaqus actually wrote
# ---------------------------------------------------------------------------

def test_every_deck_reads_its_cload_cards_back(spec, named_spec):
    for candidate in (spec, named_spec):
        assert "_expect_cload(a, workdir + '/' + MODEL + '.inp'" in _emit(candidate)


def test_a_deck_that_states_nothing_still_carries_the_check(named_spec):
    """The empty mapping IS the case that catches an unstated *Cload."""
    assert "_expect_cload(a, workdir + '/' + MODEL + '.inp', {})" in _emit(named_spec)


def test_a_stated_count_reaches_the_job_block(spec):
    text = _emit(_force(spec, expect={"points": 4}))
    assert "_expect_cload(a, workdir + '/' + MODEL + '.inp', {'TIP': 4})" in text


def test_the_stated_mapping_is_ordered_so_the_deck_is_stable(spec):
    """Two runs of the same spec must produce the same file, byte for byte."""
    out = _force(spec, expect={"points": 4})
    instance = out["assembly"]["instances"][0]["name"]
    out["conditions"].append(
        {"call": "ConcentratedForce", "name": {"literal": "Base"},
         "createStepName": {"literal": "Press"},
         "region": {"set": "%s:vertex@z=min" % instance, "name": "ANCHOR",
                    "expect": "=4"},
         "cf1": 1.0, "expect": {"points": 4}})
    assert "{'ANCHOR': 4, 'TIP': 4}" in _emit(out)


def test_the_check_runs_after_the_input_file_is_written(spec):
    text = _deck(_emit(spec))
    assert (text.index("writeInput(consistencyChecking=OFF)")
            < text.index("_expect_cload(a, workdir")
            < text.index("INP_WRITTEN"))


def test_the_refusal_removes_the_input_file(spec):
    """A caller that tests for the .inp must not read a refusal as a build."""
    body = _helper("_expect_cload")
    assert body.index("os.remove(inp_path)") < body.index("CLOAD_PER_NODE")


def test_the_cload_refusal_logs_before_it_raises():
    body = _helper("_expect_cload")
    assert "_expect_fail(" in body and "print(" not in body


@pytest.mark.parametrize("marker", ["CLOAD_PER_NODE", "POINTS_MISMATCH",
                                    "STEP_ORDER", "SET_DUPLICATE"])
def test_each_refusal_names_itself_in_the_log(marker):
    assert re.search(r"_expect_fail\(\s*'%s" % marker, kernel_runtime._HELPERS)


def test_the_node_count_is_logged_whether_or_not_it_was_asked_for():
    """It is the difference between 100 N and 400 N; it is never not worth it."""
    assert "SET_OK: %s %s (%s, %d node(s))" in kernel_runtime._HELPERS


# ---------------------------------------------------------------------------
# The named shorthand has the same hazard and gets the same gate
# ---------------------------------------------------------------------------

def test_the_named_load_can_state_its_point_count(named_spec):
    out = copy.deepcopy(named_spec)
    load = out["steps"][0]["loads"][0]
    load.update({"type": "concentrated_force", "direction": 2, "value": -25.0,
                 "points": 4})
    load.pop("expect", None)
    text = _emit(out)
    assert "'LOAD_%s': 4" % str(load.get("name", "Load-1")).upper() in text


@pytest.mark.parametrize("bad", [0, -1, 1.5, True])
def test_the_named_loads_point_count_is_checked_too(named_spec, bad):
    out = copy.deepcopy(named_spec)
    load = out["steps"][0]["loads"][0]
    load.update({"type": "concentrated_force", "direction": 2, "value": -25.0,
                 "points": bad})
    load.pop("expect", None)
    assert "whole number" in _refuse(out)


# ---------------------------------------------------------------------------
# The generated script still has to run under the 2.7 kernel
# ---------------------------------------------------------------------------

def test_the_emitted_deck_is_python_2_compatible(spec):
    """The Abaqus 2021 kernel is Python 2.7 and neither of these parses there."""
    text = _emit(_force(spec, expect={"points": 4}))
    # Not a bare "f'" search: `name='Half'` ends in one.
    found = re.search(r"(?<![A-Za-z0-9_])f['\"]", text)
    assert not found, "f-string in generated code: %s" % (found and found.group())
    for line in text.splitlines():
        if line.startswith("def ") and "->" in line:
            pytest.fail("annotation in generated code: %s" % line)
