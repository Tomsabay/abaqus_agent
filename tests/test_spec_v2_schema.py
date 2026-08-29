"""spec v2 (parts / assembly / interactions / steps) must not disturb v1.

Two things are being pinned here, and the second is the expensive one.

1. The v1 dialect validates exactly as before. Every spec under cases/ is a
   working v1 spec and must stay valid without being touched.

2. run_id does not move. ``_run_id`` hashes the spec DICT, not the YAML text
   (runner/build_model.py), so it is not enough that the .yaml files are
   unedited — nothing in the load path may insert a default for a v2 field
   either. Measured: giving cantilever's absent ``parts`` a ``None`` default
   moves its run_id from dd6ec1145b8de62f to b059c89add495d08, which retires
   every frozen baseline in the repo and orphans run directories that cannot be
   regenerated.

Hermetic: no solver, no Abaqus.
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from runner.build_model import _load_spec, _run_id  # noqa: E402
from tools.schema_validator import _manual_validate, validate_spec  # noqa: E402

SCHEMA = json.loads((ROOT / "schema" / "spec_schema.json").read_text(encoding="utf-8"))
CASE_SPECS = sorted((ROOT / "cases").glob("*/spec.yaml"))

# The vertical slice this dialect exists for: two plates, tied, one step.
V2_SPEC_YAML = """
meta:
  abaqus_release: "2021"
  model_name: TwoPlateTie
  units: mm_MPa_t
  description: Two plates tied face-to-face, pressed from above

material:
  name: Steel
  E: 210000.0
  nu: 0.3

parts:
  - name: Plate
    features:
      - op: sketch
        id: outline
        plane: XY
        profile:
          rect: { corner1: [0.0, 0.0], corner2: [100.0, 60.0] }
      - op: extrude
        sketch: outline
        depth: 10.0
    section: { type: solid, material: Steel }
    mesh: { seed: 10.0, element: C3D8R }

assembly:
  instances:
    - { name: Lower, part: Plate, translate: [0.0, 0.0, 0.0] }
    - { name: Upper, part: Plate, translate: [0.0, 0.0, 10.0] }

interactions:
  - name: PlateTie
    type: tie
    main: "Lower:face@z=max"
    secondary: "Upper:face@z=min"
    main_expect: 1
    secondary_expect: 1

steps:
  - name: Press
    type: Static
    bcs:
      - { name: Fix, region: "Lower:face@x=min", type: encastre, expect: 1 }
    loads:
      - { name: Push, region: "Upper:face@z=max", type: pressure, value: 2.0, expect: 1 }

outputs:
  kpis:
    - name: U_MAX
      type: field_max
      location: whole_model
      component: U3
"""


@pytest.fixture(scope="module")
def v2_spec() -> dict:
    return yaml.safe_load(V2_SPEC_YAML)


def _reject(spec: dict) -> list[str]:
    ok, errors = validate_spec(spec)
    assert not ok, "expected rejection, got a pass"
    return errors


def _accept(spec: dict) -> None:
    ok, errors = validate_spec(spec)
    assert ok, errors


# ---------------------------------------------------------------------------
# 1. every shipped case, and the hashes they are graded under
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("spec_path", CASE_SPECS, ids=lambda p: p.parent.name)
def test_every_shipped_case_still_validates(spec_path):
    ok, errors = validate_spec(spec_path)
    assert ok, "%s: %s" % (spec_path.parent.name, errors)


# Recomputed once, on 2026-08-16, when the seven v1 cases were replaced by v2
# twins that reproduce their frozen KPIs (four of them to the last digit). Every
# id below moved that day and none may move again without the same evidence.
# The runs made under the OLD ids are unreproducible and are kept in
# artifacts/runs_archive/; see docs/ENV_TRUTH.md 2026-08-16.
FROZEN_RUN_IDS = {
    "bearing_block": "640f2b9d2756528c",
    "blast_plate": "9fb0cd56c29eed40",
    "block_friction_slide": "7fccf9a3e3b81e2a",
    "cantilever": "c3607454a98d91af",
    "cantilever_plastic": "8aa3c913b89aac1c",
    "explicit_impact": "20aee0b43cf2060a",
    "modal": "7bd85393d229b652",
    "plate_hole": "29584892c1b437cb",
    "plate_hole_v2": "bbdfa6c6959208e7",
    "steel_frame_blast": "3471985902835e46",
    "two_plate_contact": "26e184bdcbcd4044",
    "two_plate_tie": "d8ecc5f4eb25d554",
}


@pytest.mark.parametrize("spec_path", CASE_SPECS, ids=lambda p: p.parent.name)
def test_every_shipped_case_keeps_its_run_id(spec_path):
    """The numbers that retire the most evidence if they move.

    run_id = sha256(spec), so a single edited character retires that case's
    baseline: the run directory it names can never be regenerated. Pinning all
    twelve rather than one means a case cannot drift in unnoticed either.
    """
    name = spec_path.parent.name
    assert name in FROZEN_RUN_IDS, (
        "%s is a new case with no pinned run id. Add it — a case whose hash "
        "nobody pinned is a case whose baseline can move in silence." % name)
    assert _run_id(_load_spec(spec_path)) == FROZEN_RUN_IDS[name]


def test_defaulting_a_key_would_in_fact_move_the_hash():
    """Guard the guard: prove the mechanism above is worth guarding.

    A default of None counts as present to json.dumps and therefore to the
    hash. If _run_id ever stopped being sensitive to added keys, the pins above
    would still pass while protecting nothing.
    """
    spec = _load_spec(ROOT / "cases" / "cantilever" / "spec.yaml")
    polluted = dict(spec)
    polluted["some_key_no_loader_writes"] = None
    assert _run_id(polluted) != _run_id(spec)


# ---------------------------------------------------------------------------
# 2. v2 accepts what it should
# ---------------------------------------------------------------------------

def test_the_two_plate_tie_spec_validates(v2_spec):
    ok, errors = validate_spec(v2_spec)
    assert ok, errors


def test_v2_does_not_need_geometry_analysis_or_bc_load(v2_spec):
    assert not {"geometry", "analysis", "bc_load"} & set(v2_spec)


def test_v2_may_carry_analysis_for_job_settings_only(v2_spec):
    spec = copy.deepcopy(v2_spec)
    spec["analysis"] = {"solver": "standard", "cpus": 4}
    ok, errors = validate_spec(spec)
    assert ok, errors


# ---------------------------------------------------------------------------
# 3. v2 rejects what it should
# ---------------------------------------------------------------------------

def test_mixing_the_two_dialects_is_rejected(v2_spec):
    """Both blocks present would leave the winner up to the builder.

    Whichever it picked, the other one's contents would be silently dropped —
    and a dropped `interactions` block is a missing tie in a model that still
    solves and still reports COMPLETED.
    """
    spec = copy.deepcopy(v2_spec)
    spec["geometry"] = {"type": "cantilever_block", "L": 100.0, "W": 10.0, "H": 10.0}
    _reject(spec)

    spec = copy.deepcopy(v2_spec)
    spec["bc_load"] = {"fixed_face": "z=0", "load_type": "pressure", "value": 1.0}
    _reject(spec)


def test_v2_forbids_analysis_step_type(v2_spec):
    """Two places to name the step type is two places to disagree."""
    spec = copy.deepcopy(v2_spec)
    spec["analysis"] = {"solver": "standard", "step_type": "Frequency"}
    _reject(spec)


@pytest.mark.parametrize("drop", ["assembly", "steps"])
def test_parts_without_the_rest_of_the_dialect_is_rejected(v2_spec, drop):
    spec = {k: v for k, v in copy.deepcopy(v2_spec).items() if k != drop}
    errors = _reject(spec)
    assert any(drop in e for e in errors), errors


def test_an_instance_naming_no_part_is_still_caught_somewhere(v2_spec):
    """Cross-references are the builder's job, not the schema's.

    Pinned so that when the builder starts checking it, this test is the place
    that says where the check lives — rather than the gap being rediscovered by
    a model that meshes an instance of nothing.
    """
    spec = copy.deepcopy(v2_spec)
    spec["assembly"]["instances"][0]["part"] = "NoSuchPart"
    ok, _ = validate_spec(spec)
    assert ok, ("the schema unexpectedly grew a cross-reference check — good, "
                "but update this test and the builder to match")


@pytest.mark.parametrize("bad", ["", "  ", "1Plate", "Plate name", "Plate.1"])
def test_names_that_would_break_a_deck_line_are_rejected(v2_spec, bad):
    spec = copy.deepcopy(v2_spec)
    spec["parts"][0]["name"] = bad
    _reject(spec)


@pytest.mark.parametrize("bad", ["", "   "])
def test_an_empty_selector_is_rejected(v2_spec, bad):
    spec = copy.deepcopy(v2_spec)
    spec["steps"][0]["bcs"][0]["region"] = bad
    _reject(spec)


def test_an_unimplemented_feature_op_is_rejected(v2_spec):
    """The op enum is a capability claim, so it may only list what builds.

    revolve/fillet/chamfer are in the design doc and not in the schema; the
    order is deliberate. Accepting an op the generator ignores produces a part
    that meshes, solves, and is the wrong shape.
    """
    spec = copy.deepcopy(v2_spec)
    spec["parts"][0]["features"].append({"op": "revolve", "sketch": "outline", "angle": 90})
    _reject(spec)


def test_an_unimplemented_step_type_is_rejected(v2_spec):
    spec = copy.deepcopy(v2_spec)
    spec["steps"][0]["type"] = "Dynamic_Explicit"
    _reject(spec)


def test_an_unimplemented_interaction_type_is_rejected(v2_spec):
    """`contact` used to be the example here. It is implemented now, so the
    test moved to the next one that is not — an enum that accepts a word the
    generator cannot honour is worse than no enum."""
    spec = copy.deepcopy(v2_spec)
    spec["interactions"][0]["type"] = "general_contact"
    _reject(spec)


def test_a_contact_interaction_with_a_property_block_validates(v2_spec):
    spec = copy.deepcopy(v2_spec)
    spec["interactions"][0]["type"] = "contact"
    spec["interactions"][0]["sliding"] = "finite"
    spec["interactions"][0]["property"] = {
        "normal": "hard", "friction": 0.3, "allow_separation": True}
    _accept(spec)


def test_a_negative_friction_coefficient_is_rejected(v2_spec):
    spec = copy.deepcopy(v2_spec)
    spec["interactions"][0]["type"] = "contact"
    spec["interactions"][0]["property"] = {"friction": -0.3}
    _reject(spec)


def test_an_unverified_normal_behaviour_is_rejected(v2_spec):
    """Only HARD is implemented. `softened` would otherwise reach the
    generator, which would emit hard contact anyway."""
    spec = copy.deepcopy(v2_spec)
    spec["interactions"][0]["type"] = "contact"
    spec["interactions"][0]["property"] = {"normal": "softened"}
    _reject(spec)


def test_a_misspelled_sliding_formulation_is_rejected(v2_spec):
    spec = copy.deepcopy(v2_spec)
    spec["interactions"][0]["type"] = "contact"
    spec["interactions"][0]["sliding"] = "large"   # the word is `finite`
    _reject(spec)


def test_a_typo_inside_the_property_block_is_rejected_not_ignored(v2_spec):
    """`frction: 0.3` must not validate into a frictionless model."""
    spec = copy.deepcopy(v2_spec)
    spec["interactions"][0]["type"] = "contact"
    spec["interactions"][0]["property"] = {"frction": 0.3}
    _reject(spec)


# ---------------------------------------------------------------------------
# Part shaping, local seeds, measurement regions
# ---------------------------------------------------------------------------

HOLE_SPEC = ROOT / "cases" / "plate_hole_v2" / "spec.yaml"


@pytest.fixture
def hole_spec() -> dict:
    return yaml.safe_load(HOLE_SPEC.read_text(encoding="utf-8"))


def test_the_plate_with_hole_spec_validates(hole_spec):
    _accept(hole_spec)


def test_a_typo_in_a_local_seed_is_rejected_not_ignored(hole_spec):
    """`sizee: 1.2` must not validate into a part with no refinement at all."""
    seed = hole_spec["parts"][0]["mesh"]["local_seeds"][0]
    seed["sizee"] = seed.pop("size")
    _reject(hole_spec)


def test_a_zero_local_seed_is_rejected(hole_spec):
    hole_spec["parts"][0]["mesh"]["local_seeds"][0]["size"] = 0.0
    _reject(hole_spec)


@pytest.mark.parametrize("technique", ["free", "sweep", "structured"])
def test_the_implemented_mesh_techniques_validate(hole_spec, technique):
    hole_spec["parts"][0]["mesh"]["technique"] = technique
    _accept(hole_spec)


def test_an_unimplemented_mesh_technique_is_rejected(hole_spec):
    hole_spec["parts"][0]["mesh"]["technique"] = "bottom_up"
    _reject(hole_spec)


def test_a_measurement_region_needs_both_a_name_and_a_selector(hole_spec):
    hole_spec["outputs"]["regions"].append({"name": "Nameless"})
    _reject(hole_spec)


def test_a_typo_in_a_measurement_region_is_rejected(hole_spec):
    hole_spec["outputs"]["regions"][0]["selector"] = "Plate:face@r=6"
    _reject(hole_spec)


def test_measurement_regions_are_optional(hole_spec):
    """They are new. Every spec written before them must still validate."""
    hole_spec["outputs"].pop("regions")
    hole_spec["outputs"]["kpis"] = [
        {"name": "MISES_MAX", "type": "field_max", "location": "whole_model"}]
    _accept(hole_spec)


def test_a_typo_in_a_v2_block_is_rejected_not_ignored(v2_spec):
    spec = copy.deepcopy(v2_spec)
    spec["steps"][0]["loads"][0]["magnitude"] = 5.0   # meant `value`
    _reject(spec)


# ---------------------------------------------------------------------------
# 3b. A rejection has to name the key
# ---------------------------------------------------------------------------
# Measured 2026-08-18: a planner spelled a contact's friction
# `friction_coefficient: 0.15` instead of `property: {friction: 0.15}`. The
# whole feedback it got was "{...the entire interaction...} is not valid under
# any of the given schemas", which names neither the key nor the spelling.

def test_a_oneof_rejection_names_the_offending_key(v2_spec):
    spec = copy.deepcopy(v2_spec)
    spec["interactions"][0]["friction_coefficient"] = 0.15
    errors = _reject(spec)
    joined = " | ".join(errors)
    assert "friction_coefficient" in joined
    assert "is not valid under any of the given schemas" not in joined


def test_a_oneof_rejection_says_where(v2_spec):
    """The index, not just the complaint: one of ten interactions is wrong."""
    spec = copy.deepcopy(v2_spec)
    spec["interactions"][0]["friction_coefficient"] = 0.15
    assert any(e.startswith("interactions.0:") for e in _reject(spec))


def test_the_path_is_not_repeated(v2_spec):
    """A sub-error already carries its parent's path; adding it again read as
    `interactions.0.interactions.0`, a deeper item that does not exist."""
    spec = copy.deepcopy(v2_spec)
    spec["interactions"][0]["friction_coefficient"] = 0.15
    for e in _reject(spec):
        assert "interactions.0.interactions" not in e


def test_a_missing_required_key_still_names_the_item(v2_spec):
    spec = copy.deepcopy(v2_spec)
    del spec["interactions"][0]["secondary"]
    errors = _reject(spec)
    assert any("interactions.0" in e and "secondary" in e for e in errors)


# ---------------------------------------------------------------------------
# 4. The no-jsonschema fallback must agree with the schema
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("spec_path", CASE_SPECS, ids=lambda p: p.parent.name)
def test_fallback_accepts_every_shipped_case(spec_path):
    """Every dialect, not just the one this fallback was first written for.

    It knew v1 and then v2; a `deck:` spec went to the v1 branch and was
    rejected for "missing geometry" — on machines without jsonschema only,
    which is the worst place for a validator to disagree with its own schema.
    """
    ok, errors = _manual_validate(yaml.safe_load(spec_path.read_text(encoding="utf-8")))
    assert ok, errors


def test_the_fallback_refuses_a_deck_that_also_describes_a_model():
    ok, errors = _manual_validate({
        "meta": {"abaqus_release": "2021", "model_name": "M"},
        "material": {"name": "S", "E": 1.0, "nu": 0.3},
        "outputs": {"kpis": [{"name": "k", "type": "field_max"}]},
        "deck": {"file": "m.inp"},
        "steps": [],
    })
    assert not ok
    assert any("deck" in e for e in errors), errors


def test_fallback_accepts_v2_and_rejects_the_mixed_dialect(v2_spec):
    """Without this the fallback rejects every v2 spec for 'missing geometry'
    on any machine where jsonschema is not installed."""
    ok, errors = _manual_validate(copy.deepcopy(v2_spec))
    assert ok, errors

    mixed = copy.deepcopy(v2_spec)
    mixed["geometry"] = {"type": "cantilever_block"}
    ok, errors = _manual_validate(mixed)
    assert not ok and any("geometry" in e for e in errors), errors


def test_a_whole_v1_spec_is_refused_by_the_fallback_too():
    """The fallback used to REQUIRE v1's keys in its final else branch, which
    meant a complete v1 spec passed here and was refused by the real schema.

    That is the one disagreement that costs something. jsonschema is installed
    on this machine, so the divergence would have shipped invisibly and only
    appeared where jsonschema is absent -- and it would appear as a v1 spec
    getting all the way to the builder before failing, instead of being told at
    the door that the dialect is gone.
    """
    v1 = {
        "meta": {"abaqus_release": "2021", "model_name": "M"},
        "geometry": {"type": "cantilever_block", "L": 100.0, "W": 10.0, "H": 10.0},
        "material": {"name": "S", "E": 210000.0, "nu": 0.3},
        "analysis": {"solver": "standard", "step_type": "Static"},
        "bc_load": {"fixed_face": "z=0", "load_type": "pressure", "value": 1.0},
        "outputs": {"kpis": [{"name": "k", "type": "field_max"}]},
    }
    schema_ok, _ = validate_spec(copy.deepcopy(v1))
    fallback_ok, fallback_errors = _manual_validate(copy.deepcopy(v1))
    assert not schema_ok, "the schema must refuse v1"
    assert not fallback_ok, (
        "the fallback accepted a v1 spec the schema refuses; on a machine "
        "without jsonschema this dialect would appear to still work")
    assert any("declares no model" in e for e in fallback_errors), fallback_errors


# ---------------------------------------------------------------------------
# 5. The selector grammar lives in exactly one place
# ---------------------------------------------------------------------------

def test_a_v2_spec_reaches_the_v2_generator(tmp_path, v2_spec):
    """_write_cae_script must branch on the dialect, not fall into v1.

    Without the branch a v2 spec dies on KeyError: 'geometry' inside the v1
    generator — an internal traceback for a file the validator just called
    valid.
    """
    from runner.build_model import _write_cae_script

    script = tmp_path / "build_model_script.py"
    _write_cae_script(yaml.safe_load(V2_SPEC_YAML), script, tmp_path)
    text = script.read_text(encoding="utf-8")

    assert "build_v2.py" in text, "the v1 generator answered a v2 spec"
    assert "Part-1" not in text, "v2 must not emit v1's hardcoded part name"


def test_no_field_name_is_a_yaml_1_1_boolean():
    """`on:` cannot be a key. PyYAML is YAML 1.1.

    This field was called `on` for about ten minutes. PyYAML parses bare
    on/off/yes/no as booleans in KEY position too, so
    ``yaml.safe_load('- { on: x, yes: z }')`` returns ``[{True: 'z'}]`` — the
    two keys collapse onto one and `on: x` is gone without a word. The schema
    then rejects the spec for a missing property that is right there in the
    file, which is a maddening thing to debug and a worse thing to hand a user.
    """
    reserved = {"y", "yes", "n", "no", "true", "false", "on", "off"}

    def walk(node, path="#"):
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "properties" and isinstance(value, dict):
                    for name in value:
                        assert name.lower() not in reserved, (
                            "%s/properties/%s is a YAML 1.1 boolean literal; "
                            "PyYAML will turn it into a bool key" % (path, name))
                walk(value, "%s/%s" % (path, key))
        elif isinstance(node, list):
            for i, item in enumerate(node):
                walk(item, "%s/%d" % (path, i))

    walk(SCHEMA)

    # And prove the hazard is real rather than folklore.
    assert yaml.safe_load("{on: x, yes: z}") == {True: "z"}


def test_the_schema_does_not_restate_the_selector_grammar():
    """A grammar written twice drifts, and the half that drifts stops rejecting.

    core/selectors.py is authoritative; this file may only reject the empty and
    whitespace-only cases.
    """
    pattern = SCHEMA["definitions"]["selector"]["pattern"]
    for token in ("face", "edge", "cell", "@", "nearest", "min", "max"):
        assert token not in pattern, (
            "the selector pattern started encoding the grammar (%r in %r)"
            % (token, pattern))
