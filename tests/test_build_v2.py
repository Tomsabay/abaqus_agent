"""The v2 assembly generator: what it emits, and what it refuses to emit.

Hermetic — nothing here starts Abaqus. The real-solver evidence lives in
cases/two_plate_tie: a 100x10x10 cantilever built as two tied 5 mm plates,
solved on Abaqus 2021, tip deflection -0.0715 mm against a hand-checkable
Euler-Bernoulli -0.0714 mm. That case is a physics check disguised as a
plumbing check: if the tie failed to bind, the halves would each carry their
own second moment and the pair would deflect four times as far.

Most of the tests below are refusals. A generator for this dialect has many
ways to emit a deck that meshes, solves, reports COMPLETED and answers a
different question than the one asked, and every one of those is worse than a
build that stops.
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
def spec() -> dict:
    return yaml.safe_load(CASE.read_text(encoding="utf-8"))


def _refuse(spec: dict) -> str:
    with pytest.raises(spec_base.SpecError) as caught:
        build_v2.generate_script(spec)
    return str(caught.value)


# ---------------------------------------------------------------------------
# What it emits
# ---------------------------------------------------------------------------

def test_the_shipped_case_generates_parseable_python(spec):
    ast.parse(build_v2.generate_script(spec))


def test_the_emitted_script_is_python_2_compatible(spec):
    """It runs in the Abaqus 2021 kernel: Python 2.7, no f-strings."""
    script = build_v2.generate_script(spec)
    assert not re.search(r"""(?<![A-Za-z0-9_])f["']""", script)
    for signature in _signatures(script):
        assert "->" not in signature, signature
        params = signature[signature.index("(") + 1:signature.rindex(")")]
        assert ":" not in params, signature


def _signatures(script: str) -> list[str]:
    """Every `def` line, with a wrapped parameter list joined back up.

    A signature that spans two lines is ordinary Python 2, so it must not slip
    past the annotation check just because the closing paren is on the next
    line -- which is how it would read as "no `(...)` here, nothing to check".
    """
    out = []
    lines = script.splitlines()
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped.startswith("def "):
            continue
        while stripped.count("(") > stripped.count(")") and i + 1 < len(lines):
            i += 1
            stripped += " " + lines[i].strip()
        assert stripped.count("(") == stripped.count(")"), stripped
        out.append(stripped)
    assert out, "the deck defines no functions at all"
    return out


def test_every_declared_instance_reaches_the_assembly(spec):
    script = build_v2.generate_script(spec)
    for inst in spec["assembly"]["instances"]:
        assert "a.Instance(name=%r" % inst["name"] in script


def test_regions_are_built_on_the_assembly_not_on_the_part(spec):
    """A part instanced twice has one set of faces.

    `Lower:face@y=max` and `Upper:face@y=max` are different faces only after
    the instance transform is applied, so a part-level set would give both
    instances the same region and tie a surface to itself.
    """
    script = build_v2.generate_script(spec)
    assert "a.Surface(name='MIDPLANE_MAIN'" in script
    assert "a.instances['Lower']" in script and "a.instances['Upper']" in script
    assert "p.Surface(" not in script


def test_every_region_goes_through_a_counted_selector(spec):
    """No Set or Surface may be built from anything but _sel_resolve.

    A single hand-written getByBoundingBox would be a region with no count
    check, which is the exact hole this layer exists to close.
    """
    script = build_v2.generate_script(spec)
    for match in re.finditer(r"a\.(?:Set|Surface)\(name=[^\n]*", script):
        assert "_sel_resolve(" in match.group(0), match.group(0)
    assert "getByBoundingBox" not in script.split("# --- end selector runtime")[1]


def test_the_tie_goes_through_the_release_compatibility_helper(spec):
    """Abaqus 2021's Constraint.Tie still wants master=/slave=.

    Measured: calling it with main= raises "TypeError: keyword error on main",
    which is how this was found. The helper tries the new names first so a deck
    generated here survives the planned 2024 upgrade.
    """
    script = build_v2.generate_script(spec)
    assert "_tie(m, 'MidPlane'" in script
    assert "m.Tie(name='MidPlane'" not in script
    assert "master=main_surface" in script and "main=main_surface" in script


def test_a_stated_position_tolerance_reaches_the_tie(spec):
    """Abaqus only WARNS about nodes outside the tie tolerance.

    A pair that does not actually bind still solves, so the tolerance has to
    survive from the spec into the deck or the warning is the only evidence.
    """
    script = build_v2.generate_script(spec)
    assert "positionToleranceMethod=SPECIFIED" in script
    assert "positionTolerance=0.01" in script


def test_boundary_conditions_are_created_in_the_initial_step(spec):
    """A BC that starts at Step-1 leaves Initial unrestrained.

    Abaqus reports that as a numerical singularity, which reads like a mesh or
    material problem rather than the missing restraint it is.
    """
    script = build_v2.generate_script(spec)
    for name in ("FixLower", "FixUpper"):
        assert "m.EncastreBC(name=%r, createStepName='Initial'" % name in script


def test_pressure_keeps_its_sign(spec):
    """Positive pressure acts INTO the surface; the sign is the direction.

    An abs() at this point once turned plate_with_hole's tension into
    compression, and Mises being magnitude-only meant the contour still looked
    right.
    """
    spec["steps"][0]["loads"][0]["value"] = -0.25
    assert "magnitude=-0.25" in build_v2.generate_script(spec)


def test_steps_chain_in_order(spec):
    """`previous` is what makes preload-then-load mean anything."""
    spec["steps"].append({"name": "Second", "type": "Static", "bcs": [], "loads": []})
    script = build_v2.generate_script(spec)
    assert "m.StaticStep(name='Press', previous='Initial'" in script
    assert "m.StaticStep(name='Second', previous='Press'" in script


def test_an_empty_mesh_is_caught_in_the_kernel(spec):
    """generateMesh() does not raise when it produces nothing."""
    script = build_v2.generate_script(spec)
    assert "MESH_EMPTY" in script


# ---------------------------------------------------------------------------
# Cutting a hole
#
# Every fact asserted here was measured on Abaqus 2021 (see the probe results
# quoted in docs/ASSEMBLY_MODELING.md section 9). The three that matter:
# CutExtrude without a sketch transform raises; findAt returns a SEQUENCE and
# face.getEdges() returns INDICES, so the old code could never have run; and
# the wrong sketchUpEdge either cuts nothing or transposes x and y, in both
# cases without raising.
# ---------------------------------------------------------------------------

HOLE_CASE = ROOT / "cases" / "plate_hole_v2" / "spec.yaml"


@pytest.fixture
def hole_spec() -> dict:
    return yaml.safe_load(HOLE_CASE.read_text(encoding="utf-8"))


def test_the_hole_case_generates_parseable_python(hole_spec):
    ast.parse(build_v2.generate_script(hole_spec))


def test_a_cut_goes_through_the_checked_helper(hole_spec):
    script = build_v2.generate_script(hole_spec)
    assert "_cut(m, p, 'Plate', 'hole', 5.0)" in script
    # The formulation that never worked. findAt hands back a GeomSequence, and
    # passing it as sketchPlane raised AttributeError on the first real run.
    assert "p.CutExtrude(sketchPlane=_cut_face" not in script
    assert "_sk_origin" not in script


def test_the_cut_helper_uses_a_sketch_transform(hole_spec):
    """Without one, CutExtrude answers "Cut extrude feature failed"."""
    script = build_v2.generate_script(hole_spec)
    assert "MakeSketchTransform" in script
    assert "sketchOrientation=RIGHT" in script


def test_the_cut_helper_checks_where_the_hole_ended_up(hole_spec):
    """Volume alone cannot decide this.

    A cut that misses leaves the volume untouched; a transposed one leaves it
    EXACTLY right. Only the position separates them.
    """
    script = build_v2.generate_script(hole_spec)
    assert "def _cut_missing" in script
    assert "getCentroid" in script and "getRadius" in script
    assert "CUT_FAILED" in script


def test_a_recorded_profile_is_keyed_by_part_as_well_as_by_id(hole_spec):
    """Sketch ids are unique within a part, not across parts.

    Two parts each with a sketch called 'hole' would share one entry. Emission
    order makes that harmless today, which is exactly why it needs a test: the
    day a feature moves, the wrong circle gets cut without a word.
    """
    hole_spec["parts"].append({
        "name": "Second",
        "features": [
            {"op": "sketch", "id": "outline", "plane": "XY",
             "profile": {"rect": {"corner1": [0.0, 0.0], "corner2": [10.0, 10.0]}}},
            {"op": "extrude", "sketch": "outline", "depth": 5.0},
            {"op": "sketch", "id": "hole", "plane": "XY",
             "profile": {"circle": {"center": [5.0, 5.0], "r": 2.0}}},
            {"op": "cut_extrude", "sketch": "hole", "depth": 5.0},
        ],
        "section": {"type": "solid", "material": "Steel"},
        "mesh": {"seed": 2.0, "element": "C3D8I"},
    })
    hole_spec["assembly"]["instances"].append(
        {"name": "Second", "part": "Second", "translate": [0.0, 0.0, 0.0]})
    script = build_v2.generate_script(hole_spec)
    assert "_SKETCHES[('Plate', 'hole')]" in script
    assert "_SKETCHES[('Second', 'hole')]" in script
    assert "_cut(m, p, 'Second', 'hole', 5.0)" in script


def test_the_cut_helper_rolls_back_a_failed_attempt(hole_spec):
    """It tries orientations; a rejected one must not leave geometry behind."""
    script = build_v2.generate_script(hole_spec)
    assert "def _cut_rollback" in script
    assert "deleteFeatures" in script


def test_the_cut_plane_is_found_by_a_counted_selector(hole_spec):
    """findAt returns the nearest face and never raises, so a coordinate that
    lands inside a previously cut hole would pick the cylinder."""
    script = build_v2.generate_script(hole_spec)
    assert "_sel_resolve(p, 'faces', 'z', 'max', '=1'" in script


@pytest.mark.parametrize("plane", ["XZ", "YZ"])
def test_a_sketch_plane_the_generator_cannot_honour_is_refused(hole_spec, plane):
    """This validated and was then ignored outright.

    The generator never read `plane`, so a spec asking for YZ produced a
    byte-identical script: a part on XY that meshed, solved and looked fine.
    """
    hole_spec["parts"][0]["features"][0]["plane"] = plane
    message = _refuse(hole_spec)
    assert plane in message and "XY" in message


def test_the_only_plane_the_schema_offers_is_the_one_that_is_built():
    """The schema is the first gate, and it used to offer all three."""
    import json
    schema = json.loads(
        (ROOT / "schema" / "spec_schema.json").read_text(encoding="utf-8"))
    for variant in schema["definitions"]["feature"]["oneOf"]:
        plane = variant.get("properties", {}).get("plane")
        if plane is not None:
            assert plane["enum"] == ["XY"], plane["enum"]


def test_a_rectangular_cut_is_refused(hole_spec):
    """Only a circular cut leaves a curved face to check afterwards.

    Running an unchecked cut is the silent case: same volume, same element
    count, no error.
    """
    hole_spec["parts"][0]["features"].append(
        {"op": "sketch", "id": "slot", "plane": "XY",
         "profile": {"rect": {"corner1": [1.0, 1.0], "corner2": [2.0, 2.0]}}})
    hole_spec["parts"][0]["features"].append(
        {"op": "cut_extrude", "sketch": "slot", "depth": 5.0})
    message = _refuse(hole_spec)
    assert "rectangle" in message and "silent" in message


# ---------------------------------------------------------------------------
# Local mesh seeding
# ---------------------------------------------------------------------------

def test_a_local_seed_reaches_the_deck(hole_spec):
    script = build_v2.generate_script(hole_spec)
    assert "p.seedEdgeBySize(edges=_sel_resolve(p, 'edges', 'r', '6'" in script
    assert "size=1.2" in script
    assert "constraint=FINER" in script


def test_a_local_seed_goes_through_a_counted_selector(hole_spec):
    """Seeding an empty edge set is silent: the mesh still generates, at the
    coarse size, and the stress concentration comes back low and plausible."""
    script = build_v2.generate_script(hole_spec)
    seed_line = [line for line in script.splitlines() if "seedEdgeBySize" in line]
    assert seed_line and "_sel_resolve" in seed_line[0]
    assert "'=2'" in seed_line[0], "the shipped expect must survive"


def test_a_local_seed_naming_an_instance_is_refused(hole_spec):
    """Seeds are applied to the part, before it is instanced."""
    hole_spec["parts"][0]["mesh"]["local_seeds"][0]["region"] = "Plate:edges@r=6"
    message = _refuse(hole_spec)
    assert "instance" in message


@pytest.mark.parametrize("region", ["faces@r=6", "cells@all", "vertices@all"])
def test_a_local_seed_on_something_that_is_not_an_edge_is_refused(hole_spec, region):
    """Abaqus seeds edges. A face has no seed of its own, so this would be a
    silently ignored line in the spec."""
    hole_spec["parts"][0]["mesh"]["local_seeds"][0]["region"] = region
    hole_spec["parts"][0]["mesh"]["local_seeds"][0].pop("expect", None)
    message = _refuse(hole_spec)
    assert "edge" in message


def test_the_mesh_is_checked_rather_than_merely_counted(hole_spec):
    """len(elements) == 0 only catches "nothing at all".

    A partially meshed part and a mesh full of failing elements both solve.
    """
    script = build_v2.generate_script(hole_spec)
    assert "_mesh_check(p, 'Plate')" in script
    assert "getUnmeshedRegions" in script
    assert "verifyMeshQuality" in script
    assert "MESH_INCOMPLETE" in script and "MESH_BAD" in script


def test_a_meshing_technique_is_carried_through(hole_spec):
    hole_spec["parts"][0]["mesh"]["technique"] = "sweep"
    assert "technique=SWEEP" in build_v2.generate_script(hole_spec)


# ---------------------------------------------------------------------------
# Measurement regions
# ---------------------------------------------------------------------------

def test_a_measurement_region_becomes_a_named_set(hole_spec):
    script = build_v2.generate_script(hole_spec)
    assert "a.Set(name='REGION_HOLEWALL'" in script
    assert "a.Set(name='REGION_PULLEDEND'" in script


def test_the_hole_wall_is_named_by_radius_not_by_a_plane(hole_spec):
    """No plane can name it: the hole's bounding box is the whole plate."""
    script = build_v2.generate_script(hole_spec)
    line = [ln for ln in script.splitlines() if "REGION_HOLEWALL" in ln][0]
    assert "'r', '6'" in line


def test_a_measurement_region_selector_is_validated_up_front(hole_spec):
    """Not at the solver. validate_references walks every selector in the spec,
    and a region that names a missing instance must be caught there."""
    hole_spec["outputs"]["regions"][0]["region"] = "Nope:face@r=6"
    message = _refuse(hole_spec)
    assert "Nope" in message


def test_two_measurement_regions_cannot_share_a_name(hole_spec):
    hole_spec["outputs"]["regions"].append(
        {"name": "HoleWall", "region": "Plate:face@y=min"})
    assert "HoleWall" in _refuse(hole_spec)


# ---------------------------------------------------------------------------
# Contact
# ---------------------------------------------------------------------------

CONTACT_CASE = ROOT / "cases" / "two_plate_contact" / "spec.yaml"
FRICTION_CASE = ROOT / "cases" / "block_friction_slide" / "spec.yaml"


@pytest.fixture
def contact_spec() -> dict:
    return yaml.safe_load(CONTACT_CASE.read_text(encoding="utf-8"))


def test_frictionless_is_stated_rather_than_left_to_the_default(contact_spec):
    """Abaqus assumes frictionless when no tangential behaviour is defined.

    Emitting nothing would produce the same analysis and a deck in which
    "frictionless on purpose" is indistinguishable from "nobody thought about
    friction" — different models, one file.
    """
    script = build_v2.generate_script(contact_spec)
    assert "TangentialBehavior(formulation=FRICTIONLESS)" in script
    assert "PENALTY" not in script


def test_a_friction_coefficient_reaches_the_deck(contact_spec):
    contact_spec["interactions"][0]["property"]["friction"] = 0.3
    script = build_v2.generate_script(contact_spec)
    assert "formulation=PENALTY" in script
    assert "table=((0.3, ),)" in script
    assert "FRICTIONLESS" not in script


def test_contact_goes_through_the_release_compatibility_helper(contact_spec):
    script = build_v2.generate_script(contact_spec)
    assert "_contact(m, 'MidPlane'" in script
    assert "m.SurfaceToSurfaceContactStd(name=" not in script
    assert "master=main_surface" in script and "main=main_surface" in script


def test_contact_is_created_in_the_initial_step(contact_spec):
    """Contact that only begins at Step-1 leaves the pair free before it."""
    script = build_v2.generate_script(contact_spec)
    assert "createStepName='Initial', sliding=" in script


@pytest.mark.parametrize("sliding,expected", [("small", "SMALL"), ("finite", "FINITE")])
def test_the_sliding_formulation_is_carried_through(contact_spec, sliding, expected):
    contact_spec["interactions"][0]["sliding"] = sliding
    assert "sliding=%s" % expected in build_v2.generate_script(contact_spec)


def test_separation_can_be_switched_off(contact_spec):
    contact_spec["interactions"][0]["property"]["allow_separation"] = False
    assert "allowSeparation=OFF" in build_v2.generate_script(contact_spec)


def test_a_tie_carrying_contact_settings_is_refused(spec):
    """A tie has no friction and no normal behaviour.

    Accepting the block and dropping it would give a model that ignores
    settings the author plainly meant, and still solves.
    """
    spec["interactions"][0]["property"] = {"friction": 0.4}
    message = _refuse(spec)
    assert "tie" in message and "friction" in message


# ---------------------------------------------------------------------------
# Multiple steps
# ---------------------------------------------------------------------------

@pytest.fixture
def friction_spec() -> dict:
    return yaml.safe_load(FRICTION_CASE.read_text(encoding="utf-8"))


def test_a_bc_repeated_across_steps_becomes_one_bc_that_changes(friction_spec):
    """Hold it, then move it — the shape of every preload-then-load analysis.

    Abaqus names are unique model-wide, so a second DisplacementBC of the same
    name replaces the first rather than adding to it.
    """
    script = build_v2.generate_script(friction_spec)
    assert script.count("m.DisplacementBC(name='HoldZ'") == 1
    assert ("m.boundaryConditions['HoldZ'].setValuesInStep(stepName='Slide', u3=1.0)"
            in script)


def test_setvaluesinstep_names_only_the_components_that_change(friction_spec):
    """UNSET is rejected there outright: "Invalid propagation status for 'u1'".

    In setValuesInStep an omitted component means "keep what the previous step
    gave it", so the omission is the instruction.
    """
    script = build_v2.generate_script(friction_spec)
    assert "setValuesInStep(stepName='Slide', u1=UNSET" not in script
    for line in script.splitlines():
        if "setValuesInStep" in line:
            assert "UNSET" not in line, line


def test_a_repeated_bc_on_a_different_region_is_refused(friction_spec):
    """The region is fixed when the condition is created; only values change.

    Silently applying the new value to the original region is a model nobody
    wrote, and it solves.
    """
    friction_spec["steps"][1]["bcs"][0]["region"] = "Slider:face@z=max"
    message = _refuse(friction_spec)
    assert "HoldZ" in message and "region" in message


def test_a_repeated_restraint_is_refused(friction_spec):
    """encastre has no values to change, so a repeat can only be a mistake."""
    friction_spec["steps"][1]["bcs"].append(
        {"name": "Ground", "region": "Base:face@y=min", "type": "encastre"})
    message = _refuse(friction_spec)
    assert "Ground" in message


def test_a_repeated_load_changes_its_magnitude(friction_spec):
    friction_spec["steps"][1].setdefault("loads", []).append(
        {"name": "Press", "region": "Slider:face@y=max",
         "type": "pressure", "value": 2.0})
    script = build_v2.generate_script(friction_spec)
    assert script.count("m.Pressure(name='Press'") == 1
    assert "m.loads['Press'].setValuesInStep(stepName='Slide', magnitude=2.0)" in script


def test_region_sets_are_named_after_the_condition_not_the_step(friction_spec):
    """A KPI location has to be predictable from the spec.

    Naming sets <STEP>_<NAME> meant a condition that spans two steps had a set
    named after only the first, which is not something a spec author can guess.
    """
    script = build_v2.generate_script(friction_spec)
    assert "a.Set(name='BC_HOLDZ'" in script
    assert "a.Surface(name='LOAD_PRESS'" in script
    assert "CLAMP_HOLDZ" not in script and "SLIDE_HOLDZ" not in script


def test_the_friction_case_reads_its_own_reaction_out_of_a_named_set(friction_spec):
    """The KPI locations must match the sets the generator actually creates.

    Getting this wrong is not a crash: post/extract_kpis.py raises on an
    unknown location, but only after a full solve.
    """
    script = build_v2.generate_script(friction_spec)
    for kpi in friction_spec["outputs"]["kpis"]:
        location = kpi.get("location", "")
        if location and location.isupper():
            assert "name=%r" % location in script, (
                "KPI %r reads set %r, which the deck never creates"
                % (kpi["name"], location))


# ---------------------------------------------------------------------------
# What it refuses
# ---------------------------------------------------------------------------

def test_an_instance_of_an_undeclared_part_is_refused(spec):
    spec["assembly"]["instances"][0]["part"] = "Ghost"
    message = _refuse(spec)
    assert "Ghost" in message and "Half" in message


def test_an_undefined_material_is_refused(spec):
    spec["parts"][0]["section"]["material"] = "Unobtainium"
    message = _refuse(spec)
    assert "Unobtainium" in message and "Steel" in message


def test_duplicate_part_and_instance_names_are_refused(spec):
    duplicated = copy.deepcopy(spec)
    duplicated["parts"].append(copy.deepcopy(duplicated["parts"][0]))
    assert "name" in _refuse(duplicated)

    duplicated = copy.deepcopy(spec)
    duplicated["assembly"]["instances"][1]["name"] = "Lower"
    assert "Lower" in _refuse(duplicated)


def test_a_selector_that_names_no_instance_is_refused(spec):
    """With two instances, an unqualified `face@z=min` means both or neither.

    Guessing would put the restraint on one of them and the model would solve.
    """
    spec["steps"][0]["bcs"][0]["region"] = "face@z=min"
    message = _refuse(spec)
    assert "which instance" in message


def test_a_selector_naming_an_unknown_instance_is_refused(spec):
    spec["steps"][0]["bcs"][0]["region"] = "Middle:face@z=min"
    message = _refuse(spec)
    assert "Middle" in message and "Lower" in message and "Upper" in message


def test_a_cell_selector_cannot_carry_a_pressure(spec):
    spec["steps"][0]["loads"][0]["region"] = "Upper:cells@all"
    assert "surface" in _refuse(spec)


def test_a_part_that_never_extrudes_is_refused(spec):
    """A part with no volume meshes to nothing and section-assigns to nothing."""
    spec["parts"][0]["features"] = [spec["parts"][0]["features"][0]]
    assert "no volume" in _refuse(spec)


def test_cutting_with_a_sketch_that_was_never_drawn_is_refused(spec):
    spec["parts"][0]["features"].append(
        {"op": "cut_extrude", "sketch": "nosuch", "depth": 1.0})
    message = _refuse(spec)
    assert "nosuch" in message and "outline" in message


def test_a_second_base_extrude_is_refused(spec):
    """BaseSolidExtrude replaces the solid rather than adding to it.

    Silently discarding the first one gives a part that is a different shape
    from the one the spec describes, and meshes perfectly well.
    """
    spec["parts"][0]["features"].append(
        {"op": "extrude", "sketch": "outline", "depth": 5.0})
    assert "base solid" in _refuse(spec)


def test_a_reused_sketch_id_is_refused(spec):
    spec["parts"][0]["features"].insert(1, {
        "op": "sketch", "id": "outline", "plane": "XY",
        "profile": {"circle": {"center": [1.0, 1.0], "r": 0.5}}})
    assert "twice" in _refuse(spec)


def test_a_concentrated_force_without_a_direction_is_refused(spec):
    spec["steps"][0]["loads"][0] = {
        "name": "Tip", "region": "Upper:face@z=max",
        "type": "concentrated_force", "value": -1.0}
    assert "direction" in _refuse(spec)


def test_a_displacement_bc_prescribing_nothing_is_refused(spec):
    """A DisplacementBC with every component UNSET restrains nothing.

    Abaqus accepts it, so the model solves as if the BC had not been written.
    """
    spec["steps"][0]["bcs"][0] = {
        "name": "Nothing", "region": "Lower:face@z=min", "type": "displacement"}
    assert "no-op" in _refuse(spec)


def test_an_unreadable_selector_is_refused_with_its_location(spec):
    spec["steps"][0]["bcs"][0]["region"] = "Lower:face@w=min"
    message = _refuse(spec)
    assert "FixLower" in message, "the message must say which BC is wrong"
    assert "Lower:face@w=min" in message
