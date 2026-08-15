"""Rebuilding a declared material in model_setup erases it. Refused, and checked.

MEASURED ON ABAQUS 2021 (artifacts/probe_material). A material carrying
Elastic, Plastic and Density, handed a second `m.Material(name=...)` under the
same name:

    before   elastic True   plastic True   density True
    after    elastic False  plastic False  density False   -- nothing raised

Not only the Elastic: the `yield` and the `density` the spec declared are gone
too. That is the 917 MPa failure `_materials` was written to prevent, arriving
through a different door -- and the block order guarantees the rebuild wins,
because `_materials` is emitted before `_model_setup`.

WHY ANYONE WROTE THAT SPEC. `material:` is a closed key set. Hyperelastic, an
anisotropic LAMINA elastic, a multi-point hardening curve, a
temperature-dependent property -- none of them can be spelled there, and until
now the ONLY route was to re-declare the material in `model_setup`. So the
refusal alone would close the door and leave nothing behind it. It has to come
with the route, and the route is measured too: the same probe put
`Hyperelastic` on an existing material and found its `Elastic` still there
afterwards, and LAMINA, a four-point hardening curve and a
temperature-dependent expansion all succeeded the same way.

TWO LAYERS, ON PURPOSE. The generation-time refusal knows one method name,
`Material`, because that is the one measured to do this. The runtime check
knows none: it asks the model whether every declared material still carries
what it was given, so a call that clears one by a route nobody has measured is
caught as well. A refusal with a name list would have been a guess about
Abaqus's API; the survival check is a statement about our own spec.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from runner import build_v2  # noqa: E402
from runner.build_v2 import SpecError  # noqa: E402

BASE = """
meta: {abaqus_release: "2021", model_name: M, units: mm_MPa_t}
material: {name: Steel, E: 210000.0, nu: 0.3, density: 7.85e-9, yield: 250.0}
parts:
  - name: Blk
    features:
      - call: ConstrainedSketch
        as: sk
        name: sk
        sheetSize: 40.0
      - {call: rectangle, target: {ref: sk}, point1: [0.0, 0.0], point2: [10.0, 10.0]}
      - {call: BaseSolidExtrude, sketch: {ref: sk}, depth: 10.0}
    section: {type: solid, material: Steel}
    expect: {volume: 1000.0, cells: 1}
    mesh: {seed: 5.0, element: C3D8I}
assembly:
  instances:
    - {part: Blk, name: b1}
steps:
  - {name: S1, call: StaticStep, previous: Initial}
outputs:
  kpis: [{name: U, type: nodal_displacement, location: whole_model, component: U2}]
"""


def _spec(**extra):
    spec = yaml.safe_load(BASE)
    spec.update(extra)
    return spec


def test_rebuilding_a_declared_material_is_refused():
    spec = _spec(model_setup=[{"call": "Material", "name": "Steel"}])
    with pytest.raises(SpecError) as caught:
        build_v2.generate_script(spec)
    message = str(caught.value)
    assert "Steel" in message
    # The measurement, not a house rule.
    assert "elastic" in message and "density" in message
    # And the route out, which is the whole reason anyone wrote this spec.
    assert "ref: Steel" in message


def test_a_material_with_a_name_of_its_own_is_allowed():
    """The refusal is about erasing a declaration, not about model_setup."""
    spec = _spec(model_setup=[{"call": "Material", "name": "Rubber"}])
    text = build_v2.generate_script(spec)
    assert "'Rubber'" in text
    ast.parse(text)


def test_a_declared_material_is_reachable_by_ref_without_any_earlier_call():
    """`material:` binds no `as:`, so before this there was no way in."""
    spec = _spec(model_setup=[{
        "call": "Hyperelastic", "target": {"ref": "Steel"},
        "materialType": "ISOTROPIC", "type": "NEO_HOOKE",
        "table": [[0.5, 0.0]]}])
    text = build_v2.generate_script(spec)
    assert "_gcall(m.materials['Steel'], 'Hyperelastic'" in text
    ast.parse(text)


def test_the_ref_route_compiles_to_the_object_not_to_a_results_lookup():
    """`_RESULTS['Steel']` would be a KeyError at run time: nothing binds it."""
    spec = _spec(model_setup=[{
        "call": "Density", "target": {"ref": "Steel"}, "table": [[1.0]]}])
    text = build_v2.generate_script(spec)
    assert "_RESULTS['Steel']" not in text


def test_a_ref_to_nothing_still_fails_and_now_lists_the_materials():
    spec = _spec(model_setup=[{"call": "Density", "target": {"ref": "Nope"},
                               "table": [[1.0]]}])
    with pytest.raises(SpecError) as caught:
        build_v2.generate_script(spec)
    message = str(caught.value)
    assert "Nope" in message
    assert "Steel" in message, (
        "the refusal has to say what IS reachable, or the next guess is blind")


def test_an_alias_may_not_shadow_a_declared_material():
    """`as:` is checked before the material names, so a colliding alias would
    quietly redirect every later `ref:` to whatever that line built."""
    spec = _spec(model_setup=[
        {"call": "ContactProperty", "name": "Steel", "as": "Steel"},
        {"call": "Density", "target": {"ref": "Steel"}, "table": [[1.0]]}])
    with pytest.raises(SpecError) as caught:
        build_v2.generate_script(spec)
    assert "as: Steel" in str(caught.value)


def test_the_material_route_is_offered_where_it_was_measured_and_not_elsewhere():
    """A constitutive model has to reach the material before a section uses it.

    `model_setup` runs before the parts; `steps` runs long after the section
    assignment, and whether a property added there takes effect is not
    measured. So the form is refused there rather than offered and hoped for.
    """
    spec = _spec()
    spec["steps"] = [{"name": "Load", "call": "StaticStep",
                      "previous": "Initial"},
                     {"name": "Two", "call": "Density",
                      "target": {"ref": "Steel"}, "table": [[1.0]]}]
    with pytest.raises(SpecError) as caught:
        build_v2.generate_script(spec)
    assert "names nothing an earlier call bound" in str(caught.value)


@pytest.mark.parametrize("block, entry", [
    ("interactions", {"call": "Material", "name": "Steel"}),
    ("conditions", {"call": "Material", "name": "Steel"}),
])
def test_the_other_blocks_that_dispatch_onto_the_model_refuse_it_too(block, entry):
    """Guarding model_setup alone would leave three doors open.

    `interactions`, `steps` and `conditions` reach `m` the same way, so the
    same line erases a material from any of them -- on a failure whose whole
    character is that it is silent.
    """
    spec = _spec(**{block: [entry]})
    with pytest.raises(SpecError) as caught:
        build_v2.generate_script(spec)
    assert "ERASES it" in str(caught.value)


def test_the_step_block_refuses_it_too():
    spec = _spec()
    spec["steps"] = spec["steps"] + [{"call": "Material", "name": "Steel"}]
    with pytest.raises(SpecError) as caught:
        build_v2.generate_script(spec)
    assert "ERASES it" in str(caught.value)


def test_outside_model_setup_the_message_says_to_move_the_line():
    """`target: {ref:}` is offered in model_setup only, so pointing at it from
    a step would be pointing at something that does not work there."""
    spec = _spec(interactions=[{"call": "Material", "name": "Steel"}])
    with pytest.raises(SpecError) as caught:
        build_v2.generate_script(spec)
    assert "put it in `model_setup:`" in str(caught.value)

    inside = _spec(model_setup=[{"call": "Material", "name": "Steel"}])
    with pytest.raises(SpecError) as caught:
        build_v2.generate_script(inside)
    assert "call INTO the existing material" in str(caught.value)


def test_the_survival_check_is_emitted_and_names_what_was_declared():
    spec = _spec(model_setup=[{"call": "ContactProperty", "name": "IP"}])
    text = build_v2.generate_script(spec)
    assert "MATERIAL_ERASED" in text
    # Exactly what this spec declared: E/nu -> elastic, density, yield ->
    # plastic. Not a fixed list.
    assert "('Steel', ['elastic', 'density', 'plastic'])" in text
    ast.parse(text)


def test_the_survival_check_tracks_the_spec_rather_than_a_fixed_list():
    spec = _spec(model_setup=[{"call": "ContactProperty", "name": "IP"}])
    spec["material"] = {"name": "Al", "E": 70000.0, "nu": 0.33}
    spec["parts"][0]["section"]["material"] = "Al"
    text = build_v2.generate_script(spec)
    # No density and no yield were declared, so neither is asserted on. The
    # list is read off this spec, not off a table of every property the
    # dialect knows -- checking for a `density` this material never had would
    # fail every correct model.
    assert "('Al', ['elastic'])" in text
    assert "('Al', ['elastic', " not in text


def test_a_spec_without_model_setup_emits_nothing_new():
    """The frozen decks depend on this; tests/test_frozen_model_sections is the
    other half of it."""
    text = build_v2.generate_script(_spec())
    assert "MATERIAL_ERASED" not in text
    assert "# --- Model setup" not in text


def test_every_declared_material_is_covered_not_just_the_first():
    spec = _spec(model_setup=[{"call": "ContactProperty", "name": "IP"}])
    spec["materials"] = [{"name": "Al", "E": 70000.0, "nu": 0.33,
                          "density": 2.7e-9}]
    text = build_v2.generate_script(spec)
    assert "('Steel', ['elastic', 'density', 'plastic'])" in text
    assert "('Al', ['elastic', 'density'])" in text


def test_the_generated_check_actually_catches_an_erased_material():
    """Run the emitted lines against a stand-in model, both ways.

    The assertions above are about text. This one executes it, because a check
    that is emitted and does not fire is the failure mode the whole file is
    about.
    """
    spec = _spec(model_setup=[{"call": "ContactProperty", "name": "IP"}])
    text = build_v2.generate_script(spec)
    body = text.split("# --- Model setup")[1].split("# --- Parts")[0]
    lines = body.splitlines()
    start = next(i for i, ln in enumerate(lines) if ln.startswith("for _mat_name"))
    block = "\n".join(lines[start:])

    class Mat:
        def __init__(self, **kw):
            for k, v in kw.items():
                setattr(self, k, v)

    class Model:
        def __init__(self, mats):
            self.materials = mats

    logged = []
    failed = []

    def _expect_fail(msg):
        failed.append(msg)
        raise ValueError(msg)

    intact = Model({"Steel": Mat(elastic=1, density=1, plastic=1)})
    env = {"m": intact, "_expect_fail": _expect_fail,
           "_sel_log": logged.append}
    exec(compile(block, "<survival>", "exec"), env)
    assert not failed
    assert logged and "MATERIAL_SURVIVED" in logged[0]

    wiped = Model({"Steel": Mat(elastic=None, density=None, plastic=None)})
    env = {"m": wiped, "_expect_fail": _expect_fail, "_sel_log": logged.append}
    with pytest.raises(ValueError):
        exec(compile(block, "<survival>", "exec"), env)
    assert "MATERIAL_ERASED" in failed[0]
    assert "elastic" in failed[0] and "density" in failed[0]

    removed = Model({})
    env = {"m": removed, "_expect_fail": _expect_fail, "_sel_log": logged.append}
    with pytest.raises(ValueError):
        exec(compile(block, "<survival>", "exec"), env)
    assert "not in the model" in failed[-1]
