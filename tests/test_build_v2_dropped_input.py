"""Nothing a spec declares may be dropped in silence.

Hermetic — nothing here starts Abaqus. The solver evidence is in
scripts/run_dropped_input_check.py and evidence/dropped_input_20260805/.

Seven things were being dropped or misreported, all found by asking the same
question of each layer: is this measured, or argued from the shape of the API?

  1. `yield:` and every thermal property. The block emitted Elastic and Density
     and ignored the rest, so a spec declaring `yield: 250` solved elastically:
     measured on Abaqus 2021, peak Mises 917.4 MPa, COMPLETED, no *Plastic card
     and nothing in the log. The v1 generator emits Plastic for the same key.
  2. A condition name reused. Abaqus REPLACES rather than adds, keeping only the
     later region and the later step, so the first step ends up with no boundary
     card at all — and the log line for the second condition reads GENERIC_OK.
  3. The field output request was the literal ('S','E','U','RF'). None of S, E
     or RF exists in a heat transfer step, so Abaqus refuses the whole request
     and writes no input file: the step layer had opened a physics the output
     block could not express.
  4. A kernel crash reported as a modelling problem.
  5. `mesh.element: DC3D8` raised a bare `KeyError: 'DC3D8'`.
  6. `target:` on a condition, a step or a part feature. It is in
     _generic_call's reserved tuple and those paths hard-coded their target, so
     `target: "banana"` generated a clean deck that solved.
  7. A named step written after a dispatched one took `previous='Initial'`,
     which inserts it BEFORE the dispatched step.
"""

from __future__ import annotations

import ast
import copy
import os
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
    mesh_policy,
    spec_base,
)

CASE = ROOT / "cases" / "two_plate_tie" / "spec.yaml"


@pytest.fixture
def spec() -> dict:
    return yaml.safe_load(CASE.read_text(encoding="utf-8"))


def _emit(spec: dict) -> str:
    text = build_v2.generate_script(spec)
    ast.parse(text)
    return text


def _refuse(spec: dict) -> str:
    with pytest.raises(spec_base.SpecError) as caught:
        build_v2.generate_script(spec)
    return str(caught.value)


def _deck(text: str) -> str:
    """The model the spec asked for, without the helper block above it."""
    marker = "\n# --- Material"
    return text[text.index(marker):] if marker in text else text


def _dispatched_step(spec: dict, name: str = "Press") -> dict:
    out = copy.deepcopy(spec)
    out["steps"] = [{"call": "StaticStep", "name": {"literal": name},
                     "previous": {"literal": "Initial"}}]
    out["conditions"] = [
        {"call": "EncastreBC", "name": {"literal": "Fix"},
         "createStepName": {"literal": "Initial"},
         "region": {"set": "%s:face@z=min"
                           % out["assembly"]["instances"][0]["name"],
                    "name": "FIX", "expect": "=1"}}]
    return out


# --- 1. material properties -------------------------------------------------

def test_yield_emits_the_plastic_card(spec):
    spec["material"]["yield"] = 250.0
    assert ("m.materials['Steel'].Plastic(table=((250.0, 0.0), (250.0, 0.1)))"
            in _emit(spec))


def test_hardening_is_a_modulus_spelled_as_v1_spells_it(spec):
    """v1 build_model.py puts the second point at yield + 0.1 * hardening.

    Copied rather than reinvented: cases/cantilever_plastic is calibrated
    against the v1 form, and a second reading of the same key would make the two
    dialects disagree about one spec.
    """
    spec["material"]["yield"] = 250.0
    spec["material"]["hardening"] = 1000.0
    assert ("m.materials['Steel'].Plastic(table=((250.0, 0.0), (350.0, 0.1)))"
            in _emit(spec))


def test_hardening_without_yield_is_refused(spec):
    spec["material"]["hardening"] = 1000.0
    assert "has nothing to harden" in _refuse(spec)


def test_thermal_properties_are_emitted(spec):
    spec["material"].update({"conductivity": 45.0, "specific_heat": 4.6e8,
                             "expansion_coeff": 1.2e-5,
                             "electrical_conductivity": 1.4e6})
    text = _emit(spec)
    for method, value in (("Conductivity", 45.0), ("SpecificHeat", 4.6e8),
                          ("Expansion", 1.2e-05),
                          ("ElectricalConductivity", 1400000.0)):
        assert ("m.materials['Steel'].%s(table=((%r,),))" % (method, value)
                in text)


def test_an_unknown_material_key_is_refused_not_ignored(spec):
    spec["material"]["poissons_ratio"] = 0.3
    message = _refuse(spec)
    assert "poissons_ratio" in message
    assert "conductivity" in message          # says what it does read


def test_a_key_the_schema_offers_but_this_side_cannot_build_says_why(spec):
    """`yield_stress` is in the schema. Saying "unknown key" would be wrong."""
    spec["material"]["yield_stress"] = 250.0
    message = _refuse(spec)
    assert "yield_stress" in message
    assert "write `yield`" in message


def test_fracture_energy_names_the_missing_section_type(spec):
    spec["material"]["fracture_energy"] = 0.5
    assert "cohesive section" in _refuse(spec)


# --- 2. a name that Abaqus would replace ------------------------------------

def test_two_conditions_of_one_name_are_refused(spec):
    out = _dispatched_step(spec)
    second = copy.deepcopy(out["conditions"][0])
    second["createStepName"] = {"literal": "Press"}
    out["conditions"].append(second)
    message = _refuse(out)
    assert "REPLACES" in message
    assert "condition 2" in message


def test_the_same_condition_across_steps_is_still_expressible(spec):
    """The refusal must not cost the preload-then-load shape."""
    out = _dispatched_step(spec)
    instance = out["assembly"]["instances"][0]["name"]
    out["conditions"].append(
        {"call": "DisplacementBC", "name": {"literal": "Push"},
         "createStepName": {"literal": "Press"},
         "region": {"set": "%s:face@y=max" % instance, "name": "TOP"},
         "u2": -0.5})
    out["conditions"].append(
        {"call": "setValuesInStep", "target": {"ref": "push"},
         "stepName": {"literal": "Press"}, "u2": -1.0})
    out["conditions"][1]["as"] = "push"
    assert "_gcall(_RESULTS['push'], 'setValuesInStep'" in _emit(out)


def test_a_name_this_side_cannot_read_is_left_to_the_runtime_gate():
    """The gate lives inside _gcall, so it covers every dispatched call.

    Putting it in the generated body instead would mean emitting it per call,
    and the paths that most need it are the ones whose name this side cannot
    read -- which is exactly when the host has nothing to emit against.
    """
    body = kernel_runtime._HELPERS.split("def _gcall(")[1].split("\ndef ")[0]
    assert "_expect_created(" in body


def test_the_runtime_gate_names_what_it_found(spec):
    body = kernel_runtime._HELPERS.split("def _expect_created(")[1].split("\ndef ")[0]
    assert "NAME_REPLACED" in body


def test_the_gate_only_runs_for_a_call_that_carries_a_name(spec):
    """`_gcall` on a nameless call must not pay for a registry scan."""
    body = kernel_runtime._HELPERS.split("def _gcall(")[1].split("\ndef ")[0]
    assert "if 'name' in kwargs" in body


# --- 3. the output request --------------------------------------------------

def test_the_default_request_is_unchanged(spec):
    assert ("m.fieldOutputRequests['F-Output-1'].setValues("
            "variables=('S', 'E', 'U', 'RF'))" in _emit(spec))


def test_a_heat_transfer_analysis_can_name_its_own_variables(spec):
    spec["outputs"]["field_variables"] = ["NT", "HFL"]
    assert ("m.fieldOutputRequests['F-Output-1'].setValues("
            "variables=('NT', 'HFL'))" in _emit(spec))


def test_an_empty_variable_list_is_refused(spec):
    spec["outputs"]["field_variables"] = []
    assert "at least one variable name" in _refuse(spec)


def test_a_variable_that_is_not_a_name_is_refused(spec):
    spec["outputs"]["field_variables"] = ["NT", 11]
    assert "not a variable name" in _refuse(spec)


# --- 5. element companions --------------------------------------------------

def test_a_heat_transfer_element_has_its_companions(spec):
    spec["parts"][0]["mesh"]["element"] = "DC3D8"
    text = _emit(spec)
    assert "DC3D6" in text and "DC3D4" in text


def test_an_element_with_no_companions_is_refused_by_name(spec):
    spec["parts"][0]["mesh"]["element"] = "C3D8QQ"
    message = _refuse(spec)
    assert "C3D8QQ" in message
    assert "wedge/tet companion" in message
    assert "DC3D8" in message                 # lists what it does have


@pytest.mark.parametrize("element", sorted(mesh_policy._COMPANION))
def test_every_companion_pair_is_the_same_family_size(element):
    """A hex, its wedge and its tet. Second order pairs with second order.

    The names do not follow a rule -- DC3D8's wedge is DC3D6, C3D8RT's is C3D6T
    and not C3D6RT -- so the table is looked up, not derived. What can be
    checked is that nobody paired a 20-node brick with a 6-node wedge.
    """
    wedge, tet = mesh_policy._COMPANION[element]
    second_order = "20" in element
    assert ("15" in wedge) is second_order
    assert ("10" in tet) is second_order


# --- 6. target ---------------------------------------------------------------

def test_a_target_that_is_not_a_ref_is_refused_on_a_condition(spec):
    out = _dispatched_step(spec)
    out["conditions"][0]["target"] = "banana"
    assert "`target:` must name a `ref:`" in _refuse(out)


def test_a_target_naming_nothing_bound_says_what_is_bound(spec):
    out = _dispatched_step(spec)
    out["conditions"][0]["target"] = {"ref": "nowhere"}
    message = _refuse(out)
    assert "names nothing an earlier call bound" in message


def test_a_target_on_a_step_is_read(spec):
    out = _dispatched_step(spec)
    out["steps"][0]["target"] = "banana"
    assert "`target:` must name a `ref:`" in _refuse(out)


def test_a_target_on_a_part_feature_is_read(spec):
    out = copy.deepcopy(spec)
    out["parts"][0]["features"].append({"call": "Set", "target": "banana",
                                        "name": "X"})
    out["parts"][0]["expect"] = {"cells": 1}
    assert "`target:` must name a `ref:`" in _refuse(out)


def test_the_schema_declares_target_once_for_every_dispatch_path():
    """It used to be spelled inline on the interaction branch only, so the
    other four paths neither documented it nor typed it."""
    import json
    schema = json.loads((ROOT / "schema" / "spec_schema.json")
                        .read_text(encoding="utf-8"))
    ref = {"$ref": "#/definitions/dispatch_target"}
    assert "dispatch_target" in schema["definitions"]
    assert schema["definitions"]["generic_call"]["properties"]["target"] == ref
    assert (schema["properties"]["interactions"]["items"]["oneOf"][1]
            ["properties"]["target"] == ref)


def test_the_schema_types_the_target_object():
    import json

    import jsonschema
    schema = json.loads((ROOT / "schema" / "spec_schema.json")
                        .read_text(encoding="utf-8"))
    target = dict(schema["definitions"]["dispatch_target"])
    target["definitions"] = schema["definitions"]
    jsonschema.validate({"ref": "tip"}, target)
    jsonschema.validate({"ref": "tip", "attr": "includedPairs"}, target)
    # attr alone is the route to keywordBlock and engineeringFeatures, which
    # are members of the model and the assembly rather than results of a call,
    # so nothing can bind them with `as:` and no `ref:` can name them.
    jsonschema.validate({"attr": "keywordBlock"}, target)
    for bad in ("banana", {}, {"attr": "_private"},
                {"ref": "tip", "nonsense": 1}):
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(bad, target)


def test_a_part_feature_still_dispatches_on_the_part_by_default(spec):
    """The default target changed from a literal to an argument; `p` stays `p`."""
    out = copy.deepcopy(spec)
    out["parts"][0]["features"].append({"call": "Set",
                                        "name": {"literal": "ALL"}})
    out["parts"][0]["expect"] = {"cells": 1}
    assert "_gcall(p, 'Set', {'name': 'ALL'}" in _deck(_emit(out))


# --- 7. the two step forms mixed --------------------------------------------

def test_a_named_step_chains_onto_a_dispatched_one(spec):
    out = _dispatched_step(spec, "One")
    out["steps"].append({"name": "Two", "loads": [], "bcs": []})
    text = _deck(_emit(out))
    assert "m.StaticStep(name='Two', previous='One'" in text


def test_the_order_gate_still_covers_the_mixed_form(spec):
    out = _dispatched_step(spec, "One")
    out["steps"].append({"name": "Two", "loads": [], "bcs": []})
    assert "_expect_steps(m, ('One', 'Two'))" in _deck(_emit(out))


@pytest.mark.parametrize("name", [None, "", {"ref": "bound_elsewhere"}, 3])
def test_a_dispatched_step_needs_a_name_this_side_can_read(name):
    """Both callers of it -- the order gate and the chain -- need the name.

    Tested on the function rather than through a spec, because a `{ref: ...}`
    naming nothing bound is refused earlier, by the argument compiler, and a
    `{ref: ...}` that IS bound would need a whole model built around it to say
    one thing about the step layer.
    """
    entry = {"call": "StaticStep"}
    if name is not None:
        entry["name"] = name
    with pytest.raises(spec_base.SpecError) as caught:
        build_v2._generic_step_name(0, entry)
    assert "a step needs a `name:` this side can read" in str(caught.value)


def test_a_dispatched_step_name_is_read_through_literal():
    assert build_v2._generic_step_name(
        0, {"call": "StaticStep", "name": {"literal": "Press"}}) == "Press"


def test_an_all_named_deck_carries_no_order_gate(spec):
    """The named form chains itself, so the line would be noise in every
    shipped deck."""
    assert "_expect_steps(m," not in _deck(_emit(spec))


# --- 6b. attr without ref: keywordBlock and engineeringFeatures --------------

def test_attr_alone_dispatches_against_the_default_object(spec):
    """`m.keywordBlock` is not the result of any call, so `as:` cannot bind it.

    Which was the whole gap: `target:` required a `ref:`, and the two members
    that hang off the model and the assembly and are returned by nothing --
    keywordBlock and engineeringFeatures -- had no route from a spec at all.
    """
    out = _dispatched_step(spec)
    out["conditions"].append(
        {"call": "synchVersions", "target": {"attr": "keywordBlock"},
         "storeNodesAndElements": {"literal": "OFF"}})
    assert "_gcall(m.keywordBlock, 'synchVersions'" in _emit(out)


def test_attr_alone_on_an_assembly_operation_targets_the_assembly(spec):
    """The default object differs per block; attr-only follows it.

    Demonstrated with `ContourIntegral` rather than `assignSeam`, which used to
    stand in here: a seam on the assembly is refused outright since #76, on
    timing grounds -- it has to be assigned before `generateMesh` and assembly
    operations run after. ContourIntegral is the call this member is actually
    for on the assembly side.
    """
    out = copy.deepcopy(spec)
    out["assembly"]["operations"] = [
        {"call": "ContourIntegral", "target": {"attr": "engineeringFeatures"},
         "name": {"literal": "Crack"},
         "crackFront": {"set": "Lower:vertex@box=0,0,0,0,0,0", "name": "TIP",
                        "expect": "=1"},
         "crackTip": {"named_set": "TIP"}}]
    assert "_gcall(a.engineeringFeatures, 'ContourIntegral'" in _emit(out)


def test_a_private_attr_is_still_refused(spec):
    out = _dispatched_step(spec)
    out["conditions"].append({"call": "x", "target": {"attr": "_secret"}})
    assert "not a public member name" in _refuse(out)


def test_an_empty_attr_is_refused_rather_than_emitted(spec):
    """`target: {attr: }` is a YAML null and slips past both shape checks.

    The key is present, so the "name a ref or an attr" check passes; the value
    is None, so the identifier check is skipped. What came out was
    `_gcall(m.None, ...)` -- a SyntaxError in the generated script, reported
    with neither the spec line nor the key in it.
    """
    out = _dispatched_step(spec)
    out["conditions"].append({"call": "insert", "target": {"attr": None}})
    assert "has no member name" in _refuse(out)


def test_a_keyword_insert_is_checked_against_the_written_deck(spec):
    """The generator reads the deck back to see whether the card arrived.

    Measured on Abaqus 2021, `position` names a block of
    keywordBlock.sieBlocks and the text goes after it: insert(21), the end of
    *Elastic, datachecks with 0 errors, and insert(100000) raises IndexError
    rather than landing nowhere quietly. The read-back has never caught a
    missing card -- see the *Conflicts test below for the failure it did catch.
    """
    out = _dispatched_step(spec)
    out["conditions"].append(
        {"call": "synchVersions", "target": {"attr": "keywordBlock"},
         "storeNodesAndElements": {"literal": "OFF"}})
    out["conditions"].append(
        {"call": "insert", "target": {"attr": "keywordBlock"},
         "position": 3, "text": "*Damping, alpha=0.5"})
    text = _emit(out)
    assert "_expect_keywords(workdir + '/' + MODEL + '.inp'" in text
    assert "*Damping, alpha=0.5" in text
    assert "KEYWORD_NOT_WRITTEN" in text


def test_a_multi_line_insert_is_checked_line_by_line(spec):
    out = _dispatched_step(spec)
    out["conditions"].append(
        {"call": "insert", "target": {"attr": "keywordBlock"},
         "position": 3, "text": ["*Damping, alpha=0.5", "", "*Restart, write"]})
    text = _emit(out)
    # The blank line carries no claim and is not checked; the other two are,
    # each under its own label so a failure names the line.
    assert "keywordBlock line 1" in text
    assert "keywordBlock line 3" in text
    assert "keywordBlock line 2" not in text


def _run_expect_keywords(tmp_path, deck, wanted):
    """Execute the real helper over a deck on disk, the way the kernel does.

    Text assertions cannot tell a check that fires from one that is merely
    spelled correctly, and this guard exists because of a case where the deck
    was in the file and the file was worthless.
    """
    source = kernel_runtime._HELPERS.split("def _expect_keywords(")[1]
    source = "def _expect_keywords(" + source.split("\ndef ")[0]
    logged = []

    def fail(message):
        logged.append(message)
        raise ValueError(message)

    namespace = {"os": os, "_sel_log": logged.append, "_expect_fail": fail}
    exec(compile(source, "<helpers>", "exec"), namespace)
    inp = tmp_path / "deck.inp"
    inp.write_text(deck, encoding="utf-8")
    raised = None
    try:
        namespace["_expect_keywords"](str(inp), wanted)
    except ValueError as exc:
        raised = str(exc)
    return {"raised": raised, "log": logged, "left_behind": inp.exists()}


def test_a_conflict_block_is_refused_even_though_the_card_arrived(tmp_path):
    """The card in the deck, and the deck fatally unreadable.

    Measured on Abaqus 2021 with one spec and one card, the position apart:
    insert after block 21 (the end of *Elastic) datachecks with 0 errors;
    insert after block 3, inside the generated *Element table, makes CAE wrap
    the edit in a *Conflicts block, and the input file processor reports 4
    FATAL ERRORS and terminates. The read-back logged KEYWORD_OK over it and
    the build reported success, so this is the verified counterexample the
    keyword layer was missing -- not the missing card it was written for.
    """
    deck = ("*Element, type=C3D8I\n*Conflicts, Generated keywords\n"
            " 1, 23, 24\n*Conflicts, User edited keywords\n"
            "*Damping, alpha=0.5\n*Conflicts, End of conflict block\n")
    out = _run_expect_keywords(tmp_path, deck,
                               (("condition 3 line 1", "*Damping, alpha=0.5"),))
    assert "KEYWORD_CONFLICT_BLOCK" in (out["raised"] or "")
    assert any("KEYWORD_OK" in line for line in out["log"]), (
        "the card is present, so the read-back must still say so -- the "
        "conflict is a second, separate finding about the same deck")
    assert not out["left_behind"], (
        "a refused build must not leave an input file a caller can mistake "
        "for a good one")


def test_a_clean_deck_carrying_the_card_is_accepted(tmp_path):
    """The other side of the same guard: no *Conflicts, no refusal."""
    deck = ("*Material, name=Steel\n*Density\n7.85e-09,\n*Elastic\n"
            "210000., 0.3\n*Damping, alpha=0.5\n")
    out = _run_expect_keywords(tmp_path, deck,
                               (("condition 3 line 1", "*Damping, alpha=0.5"),))
    assert out["raised"] is None
    assert out["left_behind"]


def test_a_deck_without_the_card_is_refused_and_removed(tmp_path):
    """The read-back's own no. No real spec has produced this; the gate item
    makes it by hand, and here it is made by hand too."""
    out = _run_expect_keywords(tmp_path, "*Material, name=Steel\n*Elastic\n",
                               (("condition 3 line 1", "*Damping, alpha=0.5"),))
    assert "KEYWORD_NOT_WRITTEN" in (out["raised"] or "")
    assert not out["left_behind"]


def test_a_spec_with_no_keyword_insert_emits_no_keyword_check(spec):
    """Four shipped cases must keep generating byte-identical decks.

    Scoped to the model section: the helper itself lives in the preamble and is
    always there, the same way _expect_cload is.
    """
    assert "_expect_keywords(" not in _deck(_emit(_dispatched_step(spec)))
