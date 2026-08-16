"""The planner prompt has to be able to describe the dialect the builder reads.

Hermetic: the claude CLI is never invoked. What is checked instead is the only
thing that can be checked without it — that the grammar the prompt teaches is
the grammar that builds.

The prompt-text assertions are the cheap half. The valuable half is
``_SCENARIOS``: hand-written v2 specs, one per scenario a user would actually
type, each pushed through the real schema AND through
``runner.build_v2.generate_script``. A prompt that teaches a key the schema
refuses, or a phrase the generator cannot compile, is worse than one that stays
silent — the model would produce it confidently and the failure would surface as
a validation error the user cannot act on. These specs are the evidence that the
rules in the prompt were read off the schema and the generator rather than
remembered.
"""

from __future__ import annotations

import ast
import copy
import json
import re
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import selectors  # noqa: E402
from runner import (
    arg_forms,
    build_v2,  # noqa: E402
    mesh_policy,
    spec_base,
)
from scripts import run_generic_mesh_check as generic_check  # noqa: E402
from tools.schema_validator import validate_spec  # noqa: E402
from workbench import planner  # noqa: E402


def _schema() -> dict:
    """The schema file itself, so an enum here is read and not remembered."""
    return json.loads((ROOT / "schema" / "spec_schema.json").read_text(encoding="utf-8"))


@pytest.fixture
def prompt(monkeypatch) -> str:
    """The rendered prompt, with the release probe stubbed.

    build_prompt calls detect_abaqus_release(), which shells out to the launcher.
    conftest hides Abaqus from PATH so it would answer None here, but stubbing it
    is what makes the substitution assertion below mean something: the point of
    that rule is that the release reaches the prompt from a measurement.
    """
    monkeypatch.setattr(planner, "detect_abaqus_release", lambda: "2021")
    return planner.build_prompt("两块板绑在一起，上面加压", None, [])


# ---------------------------------------------------------------------------
# Scenarios: what the prompt claims a spec looks like, written out and built
# ---------------------------------------------------------------------------

# Two plates tied together. The named shorthand end to end: sugar tie, one
# Static step carrying its own bcs and loads.
_TWO_PLATE_TIE = """
meta:
  abaqus_release: "2021"
  model_name: TwoPlatesTied
  units: mm_MPa_t
material:
  name: Steel
  E: 210000.0
  nu: 0.3
parts:
  - name: Half
    features:
      - {op: sketch, id: outline, plane: XY,
         profile: {rect: {corner1: [0.0, 0.0], corner2: [10.0, 5.0]}}}
      - {op: extrude, sketch: outline, depth: 100.0}
    section: {type: solid, material: Steel}
    mesh: {seed: 2.5, element: C3D8I}
assembly:
  instances:
    - {name: Lower, part: Half, translate: [0.0, 0.0, 0.0]}
    - {name: Upper, part: Half, translate: [0.0, 5.0, 0.0]}
interactions:
  - {name: MidPlane, type: tie, main: "Lower:face@y=max",
     secondary: "Upper:face@y=min", position_tolerance: 0.01}
steps:
  - name: Press
    type: Static
    bcs:
      - {name: FixLower, region: "Lower:face@z=min", type: encastre}
      - {name: FixUpper, region: "Upper:face@z=min", type: encastre}
    loads:
      - {name: Top, region: "Upper:face@y=max", type: pressure, value: 0.1}
outputs:
  kpis:
    - {name: U_TIP, type: field_min, location: whole_model, component: U2}
"""

# A cantilever modal analysis. Not expressible with the named step shorthand,
# which is Static only, so this is the dispatched form: a FrequencyStep plus a
# top-level condition naming its createStepName.
_CANTILEVER_MODAL = """
meta:
  abaqus_release: "2021"
  model_name: CantileverModes
  units: mm_MPa_t
material:
  name: Steel
  E: 210000.0
  nu: 0.3
  density: 7.85e-9
parts:
  - name: Bar
    features:
      - {op: sketch, id: outline, plane: XY,
         profile: {rect: {corner1: [0.0, 0.0], corner2: [10.0, 10.0]}}}
      - {op: extrude, sketch: outline, depth: 100.0}
    section: {type: solid, material: Steel}
    mesh: {seed: 5.0, element: C3D8I}
assembly:
  instances:
    - {name: Bar, part: Bar}
steps:
  - {call: FrequencyStep, name: {literal: Modes},
     previous: {literal: Initial}, numEigen: 5}
conditions:
  - call: EncastreBC
    name: {literal: Fix}
    createStepName: {literal: Initial}
    region: {set: "Bar:face@z=min", name: FIX, expect: "=1"}
outputs:
  field_variables: ["U"]
  kpis:
    - {name: F1, type: eigenfrequency, location: mode_1}
    - {name: F2, type: eigenfrequency, location: mode_2}
"""

# A plate with a hole in tension. Exercises cut_extrude, the radius selector on
# a face no plane can name, a local seed on the hole rim, and a measurement
# region that exists only to be read from.
_PLATE_HOLE_TENSION = """
meta:
  abaqus_release: "2021"
  model_name: PlateHoleTension
  units: mm_MPa_t
material:
  name: Steel
  E: 210000.0
  nu: 0.3
parts:
  - name: Plate
    features:
      - {op: sketch, id: outline, plane: XY,
         profile: {rect: {corner1: [0.0, 0.0], corner2: [60.0, 240.0]}}}
      - {op: extrude, sketch: outline, depth: 5.0}
      - {op: sketch, id: hole, plane: XY,
         profile: {circle: {center: [30.0, 120.0], r: 6.0}}}
      - {op: cut_extrude, sketch: hole, depth: 5.0}
    section: {type: solid, material: Steel}
    mesh:
      seed: 5.0
      element: C3D20R
      local_seeds:
        - {region: "edges@r=6", size: 1.2, expect: "=2"}
assembly:
  instances:
    - {name: Plate, part: Plate}
steps:
  - name: Pull
    type: Static
    bcs:
      - {name: Root, region: "Plate:face@y=min", type: encastre}
    loads:
      - {name: Tension, region: "Plate:face@y=max", type: pressure, value: -1.0}
outputs:
  regions:
    - {name: HoleWall, region: "Plate:face@r=6"}
    - {name: PulledEnd, region: "Plate:face@y=max"}
  kpis:
    - {name: HOOP_MAX, type: field_max, invariant: MISES,
       location: "REGION_HOLEWALL"}
    # On the pulled end, not on the hole wall: a KPI called FAR_FIELD reading
    # the stress concentration is the mistake the prompt spends a paragraph
    # warning about, and an example that makes it teaches it.
    - {name: FAR_FIELD, type: field_max, field_variable: S, component: S22,
       location: "REGION_PULLEDEND"}
"""

# A tip load in a second step, which is where both of the taught traps live: the
# steps have to chain `previous`, and 400 N over four corner nodes has to be
# written as -100 per node with the count declared. The tie is written as the
# dispatched call so the {surface: ...} form and expect.gap are covered too.
_TIP_LOAD_TWO_STEPS = """
meta:
  abaqus_release: "2021"
  model_name: TipLoadTwoSteps
  units: mm_MPa_t
material:
  name: Steel
  E: 210000.0
  nu: 0.3
parts:
  - name: Half
    features:
      - {op: sketch, id: outline, plane: XY,
         profile: {rect: {corner1: [0.0, 0.0], corner2: [10.0, 5.0]}}}
      - {op: extrude, sketch: outline, depth: 100.0}
    section: {type: solid, material: Steel}
    mesh: {seed: 2.5, element: C3D8I}
assembly:
  instances:
    - {name: Lower, part: Half, translate: [0.0, 0.0, 0.0]}
    - {name: Upper, part: Half, translate: [0.0, 5.0, 0.0]}
  expect:
    instances: 2
interactions:
  - call: Tie
    name: {literal: MidPlane}
    main: {surface: "Lower:face@y=max", name: BOND_MAIN, expect: "=1"}
    secondary: {surface: "Upper:face@y=min", name: BOND_SEC, expect: "=1"}
    positionToleranceMethod: SPECIFIED
    positionTolerance: 0.01
    adjust: "OFF"
    expect: {gap: {max: 0.001}}
steps:
  - {call: StaticStep, name: {literal: Hold}, previous: {literal: Initial}}
  - {call: StaticStep, name: {literal: Pull}, previous: {literal: Hold}}
conditions:
  - call: EncastreBC
    name: {literal: RootLower}
    createStepName: {literal: Initial}
    region: {set: "Lower:face@z=min", name: ROOT_LOWER, expect: "=1"}
  - call: EncastreBC
    name: {literal: RootUpper}
    createStepName: {literal: Initial}
    region: {set: "Upper:face@z=min", name: ROOT_UPPER, expect: "=1"}
  # 400 N total over the four corners of the tip face, so -100 per node.
  - call: ConcentratedForce
    name: {literal: Tip}
    createStepName: {literal: Pull}
    region: {set: "Upper:vertices@z=max", name: TIP, expect: "=4"}
    cf2: -100.0
    expect: {points: 4}
outputs:
  kpis:
    - {name: U_TIP, type: field_min, location: whole_model, component: U2}
"""

# A mesh read straight from a deck. No geometry at all: an orphan part has 0
# cells, faces, edges and vertices (measured, scripts/run_orphan_mesh_check.py),
# so `node@` is the only way left to name the ends of it. Here to prove the
# selector kinds the prompt gained are ones the builder resolves.
_ORPHAN_MESH_IMPORT = """
meta:
  abaqus_release: "2021"
  model_name: OrphanBar
  units: mm_MPa_t
material:
  name: Steel
  E: 210000.0
  nu: 0.3
parts:
  - name: Bar
    import:
      part: {call: PartFromInputFile, inputFileName: {file: bar.inp}}
    expect: {mesh: {nodes: 189, elements: 80}}
    section: {type: solid, material: Steel}
assembly:
  instances:
    - {name: B, part: Bar, translate: [0.0, 0.0, 0.0]}
steps:
  - {call: StaticStep, name: {literal: Press}, previous: {literal: Initial}}
conditions:
  - call: EncastreBC
    name: {literal: Fix}
    createStepName: {literal: Initial}
    region: {set: "B:nodes@z=min", name: FIX, expect: "=9"}
  - call: ConcentratedForce
    name: {literal: Tip}
    createStepName: {literal: Press}
    region: {set: "B:nodes@z=max", name: TIP, expect: "=9"}
    cf2: -1.0
    expect: {points: 9}
outputs:
  kpis:
    - {name: U_TIP, type: field_min, location: whole_model, component: U2}
"""

# A seam: one face split into two, on a part set, before the mesh. The whole
# construct is unreachable without `{set:}` resolving in part scope, and it is
# silent when wrong — hence expect.seams.
_SEAM_ON_A_PART = """
meta:
  abaqus_release: "2021"
  model_name: SeamedBlock
  units: mm_MPa_t
material:
  name: Steel
  E: 210000.0
  nu: 0.3
parts:
  - name: Blk
    features:
      - {op: sketch, id: o, plane: XY,
         profile: {rect: {corner1: [0.0, 0.0], corner2: [10.0, 10.0]}}}
      - {op: extrude, sketch: o, depth: 10.0}
      - {call: DatumPlaneByPrincipalPlane, principalPlane: XYPLANE,
         offset: 5.0, as: mid}
      - {call: PartitionCellByDatumPlane, datumPlane: {datum: mid},
         cells: {select: "cell@all"}}
      - call: assignSeam
        target: {attr: engineeringFeatures}
        regions: {set: "face@z=5", name: SEAMFACE, expect: "=1"}
    expect:
      volume: 1000.0
      cells: 2
      seams: [{set: SEAMFACE, duplicated: 9}]
    section: {type: solid, material: Steel}
    mesh: {seed: 5.0, element: C3D8I}
assembly:
  instances:
    - {name: B, part: Blk, translate: [0.0, 0.0, 0.0]}
steps:
  - {call: StaticStep, name: {literal: Pull}, previous: {literal: Initial}}
conditions:
  - call: EncastreBC
    name: {literal: Fix}
    createStepName: {literal: Initial}
    region: {set: "B:face@y=min", name: FIX, expect: "=2"}
  - call: Pressure
    name: {literal: Top}
    createStepName: {literal: Pull}
    region: {surface: "B:face@y=max", name: TOP, expect: "=2"}
    magnitude: -0.1
outputs:
  kpis:
    - {name: U_TOP, type: field_max, location: whole_model, component: U2}
"""

# A shape opened from a CAD file. The other import route: `open:` then
# PartFromGeometryFile, and a geometry expect rather than a mesh one.
_GEOMETRY_IMPORT = """
meta:
  abaqus_release: "2021"
  model_name: ImportedBracket
  units: mm_MPa_t
material:
  name: Steel
  E: 210000.0
  nu: 0.3
parts:
  - name: Bracket
    import:
      open: {call: openStep, fileName: {file: bracket.stp}, scaleFromFile: "OFF"}
      part: {call: PartFromGeometryFile, dimensionality: THREE_D,
             type: DEFORMABLE_BODY}
    expect: {volume: 10000.0, cells: 1}
    section: {type: solid, material: Steel}
    mesh: {seed: 5.0, element: C3D8R}
assembly:
  instances:
    - {name: Br, part: Bracket, translate: [0.0, 0.0, 0.0]}
steps:
  - {call: StaticStep, name: {literal: Press}, previous: {literal: Initial}}
conditions:
  - call: EncastreBC
    name: {literal: Fix}
    createStepName: {literal: Initial}
    region: {set: "Br:face@z=min", name: FIX, expect: "=1"}
outputs:
  kpis:
    - {name: U_MIN, type: field_min, location: whole_model, component: U2}
"""

_SCENARIOS = {
    "two plates tied together": _TWO_PLATE_TIE,
    "a cantilever modal analysis": _CANTILEVER_MODAL,
    "a plate with a hole in tension": _PLATE_HOLE_TENSION,
    "a tip load applied in a second step": _TIP_LOAD_TWO_STEPS,
    "a mesh imported from a deck": _ORPHAN_MESH_IMPORT,
    "a seam assigned on a part": _SEAM_ON_A_PART,
    "a shape imported from a step file": _GEOMETRY_IMPORT,
}


@pytest.fixture(scope="session")
def spec_dir(tmp_path_factory) -> Path:
    """A directory holding the files the import scenarios name.

    `{file:}` is resolved against the spec's own directory and a path that does
    not exist is refused there, before Abaqus is started. Nothing here reads the
    CONTENTS -- the generator only embeds the resolved path -- so these are
    placeholders and say so. What the files really contain is proved against the
    solver by scripts/run_orphan_mesh_check.py, which exports a bar from CAE and
    reads it back.
    """
    directory = tmp_path_factory.mktemp("spec")
    (directory / "bar.inp").write_text(
        "** placeholder: existence is all the generator checks\n",
        encoding="utf-8")
    (directory / "bracket.stp").write_text(
        "ISO-10303-21;\n", encoding="utf-8")
    return directory


@pytest.fixture(params=sorted(_SCENARIOS), ids=lambda key: key)
def scenario(request) -> dict:
    return yaml.safe_load(_SCENARIOS[request.param])


def test_the_kpi_types_this_prompt_teaches_are_the_ones_the_schema_has():
    """Read from the schema, not remembered — the same guard the other prompt
    got in #29, which this one did not.

    It was already two behind when it was written: `eigenvalue` and
    `derived_stress_concentration` were in the schema and absent here, so
    buckling and SCF were unreachable from the chat with every test green. Both
    directions matter — a type the prompt teaches and the schema refuses is a
    spec the user watches fail for a reason the chat called fine.
    """
    schema = json.loads(
        (ROOT / "schema" / "spec_schema.json").read_text(encoding="utf-8"))
    published = (schema["properties"]["outputs"]["properties"]["kpis"]["items"]
                 ["properties"]["type"]["enum"])

    section = planner._PROMPT_TEMPLATE.split("type 只能用这几种：")[1]
    # The indented pipe-separated lines are the list; the prose under them is
    # free to be reworded.
    listed = " ".join(line for line in section.splitlines()
                      if line.startswith("     ") and line.strip())
    taught = {word for word in re.split(r"[|\s]+", listed) if word}
    assert taught == set(published), (
        "prompt teaches %s the schema refuses; schema has %s the prompt omits"
        % (sorted(taught - set(published)), sorted(set(published) - taught)))


def test_the_crack_kpi_is_taught_with_the_recipe_that_builds_it():
    """This used to assert the OPPOSITE, and that is the point of writing it down.

    Until #76 the prompt had to say "怎么建裂缝没验证过" — the dialect could not
    author a ContourIntegral, and naming the KPI without saying so would have
    turned the closed list into an invitation to invent a crack. It can now, so
    the disclaimer is gone and this asserts the recipe is here instead. A KPI
    the prompt names and does not show how to feed is the failure either way.
    """
    text = planner._PROMPT_TEMPLATE + planner._V2_DIALECT
    assert "contour_integral_j" in text
    assert "没验证过" not in text.split("contour_integral_j", 1)[1][:400], (
        "the prompt still says the crack cannot be built, which stopped being "
        "true when scripts/run_crack_check.py started proving the authoring")
    for marker in ("dimensionality: TWO_D_PLANAR", "assignSeam",
                   "ContourIntegral", "edge@box=", "crackFront",
                   "duplicated: 20"):
        assert marker in text, marker


def test_the_crack_recipe_in_the_prompt_actually_builds():
    """The guard that makes the recipe above a fact rather than a paragraph.

    Everything the builder learned to refuse passes the schema — a generic call
    with no `expect:`, a seam nothing checks. An example carrying one of those
    is a mistake the model would copy verbatim.
    """
    text = planner._V2_DIALECT
    block = [b for b in _YAML_BLOCK_RE.findall(text) if "ContourIntegral" in b]
    assert len(block) == 1, "the crack example is gone, or there are now two"
    fragment = yaml.safe_load(block[0])
    # A fragment, not a whole spec: the prompt shows the parts/assembly/
    # conditions that matter and leaves the boilerplate out. Filled in here so
    # the generator sees a real spec.
    spec = {
        "meta": {"abaqus_release": "2021", "model_name": "SEN",
                 "units": "mm_MPa_t", "description": "d",
                 "missing_questions": []},
        "material": {"name": "Steel", "E": 210000.0, "nu": 0.3},
        "steps": [{"name": "Pull", "type": "Static",
                   "bcs": [{"name": "FixY", "type": "displacement", "u2": 0.0,
                            "region": "P:vertex@box=50,-50,0,50,-50,0"}],
                   "loads": [{"name": "Top", "type": "pressure",
                              "value": -100.0,
                              "region": "P:edges@y=max"}]}],
        "outputs": {"kpis": [{"name": "J_TIP", "type": "contour_integral_j",
                              "location": "Crack"}]},
    }
    spec.update(fragment)
    valid, errors = validate_spec(spec)
    assert valid, errors
    build_v2.generate_script(spec)          # SpecError names the prompt's bug


def test_every_scenario_spec_passes_the_real_schema(scenario):
    valid, errors = validate_spec(scenario)
    assert valid, errors


def test_every_scenario_spec_is_the_v2_dialect(scenario):
    """`parts` is the discriminator both the schema and the builder branch on."""
    assert "parts" in scenario
    assert "geometry" not in scenario
    assert "bc_load" not in scenario
    assert "step_type" not in (scenario.get("analysis") or {})


def test_every_scenario_spec_generates_a_deck(scenario, spec_dir):
    """The real check: a spec written to the prompt's rules has to build.

    ast.parse rather than a substring match — the generator emits Python for the
    Abaqus kernel, and a phrase it compiles into a syntax error is a phrase the
    prompt must not teach.
    """
    ast.parse(build_v2.generate_script(scenario, spec_dir))


def test_the_two_traps_are_honoured_by_the_specs_that_carry_them():
    """The traps the prompt teaches, asserted on the specs that demonstrate them.

    Both are silent in Abaqus: a per-node magnitude nobody divided completes with
    four times the load, and two steps that both say `previous: Initial` run in
    reverse and complete as well. So the specs shipped here as the worked example
    have to actually get them right.
    """
    spec = yaml.safe_load(_TIP_LOAD_TWO_STEPS)

    force = [c for c in spec["conditions"] if c["call"] == "ConcentratedForce"][0]
    assert force["expect"]["points"] == 4
    assert force["cf2"] == pytest.approx(-400.0 / 4)

    names = [step["name"]["literal"] for step in spec["steps"]]
    previous = [step["previous"]["literal"] for step in spec["steps"]]
    assert previous[0] == "Initial"
    assert previous[1:] == names[:-1], (
        "each dispatched step after the first must name the one before it; "
        "two steps both on Initial come out in reverse order")


def _mutate(source: str, edit) -> dict:
    spec = yaml.safe_load(source)
    edit(spec)
    return spec


def _drop_gap(spec):
    del spec["interactions"][0]["expect"]


def _bare_boolean(spec):
    spec["interactions"][0]["adjust"] = False


def _rect_cut(spec):
    spec["parts"][0]["features"][2]["profile"] = {
        "rect": {"corner1": [1.0, 1.0], "corner2": [2.0, 2.0]}}


def _tie_with_property(spec):
    spec["interactions"][0]["property"] = {"friction": 0.3}


def _selector_without_instance(spec):
    spec["steps"][0]["bcs"][0]["region"] = "face@z=min"


@pytest.mark.parametrize("source, edit, expected", [
    (_TIP_LOAD_TWO_STEPS, _drop_gap, "expect: {gap"),
    (_TIP_LOAD_TWO_STEPS, _bare_boolean, "on/off/yes/no"),
    (_PLATE_HOLE_TENSION, _rect_cut, "Only circular cuts"),
    (_TWO_PLATE_TIE, _tie_with_property, "A tie is a constraint"),
    (_TWO_PLATE_TIE, _selector_without_instance, "does not say which instance"),
], ids=["two surfaces without a gap", "a bare YAML boolean",
        "cut_extrude on a rectangle", "a tie carrying contact property",
        "a selector with no instance"])
def test_the_refusals_the_prompt_promises_really_refuse(source, edit, expected):
    """Each of these is a "会被拒" line in the prompt.

    A prompt that threatens a refusal the generator does not make teaches the
    model to avoid something harmless; one that promises a refusal that does
    happen is teaching it the shape of the grammar. Only the second is worth the
    words, so the claims are checked rather than asserted.
    """
    with pytest.raises(spec_base.SpecError) as caught:
        build_v2.generate_script(_mutate(source, edit))
    assert expected in str(caught.value)


def test_the_step_order_trap_cannot_be_caught_before_the_run():
    """Why the prompt has to teach the chaining instead of leaving it to a gate.

    Two steps that both declare `previous: Initial` generate a perfectly good
    deck — Abaqus accepts both and inserts the second BEFORE the first, and the
    job completes with the analysis run backwards. Nothing on this side can see
    it, so the only defence is the spec being written right and the run-time
    assertion below.
    """
    def both_on_initial(spec):
        spec["steps"][1]["previous"] = {"literal": "Initial"}

    script = build_v2.generate_script(_mutate(_TIP_LOAD_TWO_STEPS, both_on_initial))
    assert "_expect_steps(m, ('Hold', 'Pull'))" in script


def test_the_generated_deck_asserts_the_step_order():
    """Chaining `previous` correctly is not enough on its own — the run-time
    assertion has to be in the deck, because the reversal it catches leaves a
    job that completes."""
    script = build_v2.generate_script(yaml.safe_load(_TIP_LOAD_TWO_STEPS))
    assert "_expect_steps(m, ('Hold', 'Pull'))" in script


# ---------------------------------------------------------------------------
# The prompt itself
# ---------------------------------------------------------------------------

# Every v2 construct the prompt is required to teach, with a phrase that can
# only appear if it was taught rather than mentioned in passing.
_V2_CONSTRUCTS = [
    "parts:",
    "op: sketch",
    "op: extrude",
    "op: cut_extrude",
    "profile: {rect:",
    "profile: {circle:",
    "section: {type: solid",
    "local_seeds",
    "assembly:",
    "instances:",
    "translate:",
    "rotate:",
    "operations:",
    "creates:",
    "interactions:",
    "type: tie",
    "type: contact",
    "call: Tie",
    "call: SurfaceToSurfaceContactStd",
    "call: ContactProperty",
    "position_tolerance",
    "expect: {gap:",
    "steps:",
    "type: Static",
    "call: StaticStep",
    "call: FrequencyStep",
    "HeatTransferStep",
    "previous:",
    "conditions:",
    "createStepName",
    "call: EncastreBC",
    "call: ConcentratedForce",
    "call: Pressure",
    "outputs:",
    "regions:",
    "REGION_",
    "field_variables",
    "expect: {points:",
    "{literal:",
    "{surface:",
    "{set:",
    "{select:",
    "{ref:",
    "{sketch:",
    "{new:",
    "as:",
    "target:",
    "cylinders:",
    "expect: {mesh:",
]


@pytest.mark.parametrize("construct", _V2_CONSTRUCTS)
def test_prompt_teaches_the_v2_construct(prompt, construct):
    assert construct in prompt


_SELECTOR_PHRASES = [
    "Lower:face@y=max",
    "Bar:vertices@z=max",
    "Plate:face@r=6",
    'expect: "=1"',
]


@pytest.mark.parametrize("phrase", _SELECTOR_PHRASES)
def test_prompt_teaches_the_selector_grammar(prompt, phrase):
    assert phrase in prompt


def test_the_enums_the_prompt_teaches_are_the_enums_the_schema_has(prompt):
    """The lists in the prompt are typed by hand; these are read from the file.

    Both directions matter. A value the schema gained and the prompt never
    learned is a capability nobody can reach; a value the prompt teaches and the
    schema refuses is a spec the user watches fail validation for a reason the
    chat just told them was fine.
    """
    schema = _schema()
    mesh = schema["definitions"]["part_mesh"]["properties"]
    step = schema["properties"]["steps"]["items"]["oneOf"][0]["properties"]

    for value in mesh["technique"]["enum"]:
        assert value in prompt
    for value in step["bcs"]["items"]["properties"]["type"]["enum"]:
        assert value in prompt
    for value in step["loads"]["items"]["properties"]["type"]["enum"]:
        assert value in prompt
    assert mesh["element"]["default"] in prompt

    # Elements are not an enum: _COMPANION is the authority, because what can be
    # meshed is what the generator can pair with a wedge and a tet. So the check
    # is that every code the prompt names is one of those — an element it taught
    # and the builder refuses is a spec the chat promised would work.
    for code in set(re.findall(r"\b(?:DC3D|C3D|Q3D)\d+[A-Z]*\b", prompt)):
        assert code in mesh_policy._COMPANION, "%s has no recorded companion" % code


def test_the_material_keys_the_prompt_teaches_are_the_ones_that_emit(prompt):
    """A material key that validates and emits nothing is the silent drop this
    dialect exists to refuse, so the prompt's list is checked against the
    generator's, not against the schema's — the schema is the wider of the two.
    """
    for key in build_v2._MATERIAL_KNOWN - {"name"}:
        assert key in prompt

    # `yield_stress` is offered by the schema and refused by the generator, so
    # the prompt has to name it as the wrong spelling rather than stay quiet.
    assert "yield_stress" in prompt
    for key in set(build_v2._MATERIAL_UNBUILDABLE) - {"yield_stress"}:
        assert key not in prompt, "%s cannot be built and must not be taught" % key


def test_the_pattern_example_carries_the_measured_bolt_positions(prompt):
    """`assembly.expect.at` in the prompt against where the bolts were measured.

    The centroid there is checked with tol 0.01 at build time, so a coordinate
    lifted from a different ring size does not read as approximate — it aborts a
    correct assembly. scripts/run_generic_mesh_check.py holds the measurement
    (the housing's own hole centres, item 6), which is what this compares to.
    """
    # Two blocks carry `operations:` since the crack recipe arrived; this one
    # is the instance pattern, named by the call it demonstrates.
    block = [b for b in _YAML_BLOCK_RE.findall(prompt)
             if "operations:" in b and "InstancePattern" in b]
    assert len(block) == 1
    assembly = yaml.safe_load(block[0])["assembly"]

    pattern = assembly["operations"][0]
    assert pattern["number"] == generic_check.BOLT_N
    assert pattern["creates"] == generic_check.BOLT_NAMES[1:]

    measured = {entry["instance"]: entry for entry in generic_check.bolt_positions()}
    for stated in assembly["expect"]["at"]:
        want = measured[stated["instance"]]["centroid"]
        assert stated["centroid"] == pytest.approx(want, abs=stated["tol"])

    # The count is the other half: every instance the spec listed, plus every
    # one the pattern creates. A pattern that silently produced nothing leaves
    # the listed instances behind and no error.
    assert assembly["expect"]["instances"] == (
        len(assembly["instances"]) + len(pattern["creates"]))


def test_prompt_says_why_the_counts_are_mandatory(prompt):
    """Not just the syntax. A count nobody understands the reason for is a count
    the model will drop the first time it is inconvenient."""
    assert "COMPLETED" in prompt
    assert "数量断言" in prompt


def test_prompt_teaches_the_all_caps_symbol_rule_and_its_escape(prompt):
    assert "abaqusConstants" in prompt
    assert "{literal: RIM}" in prompt
    assert '"ON"' in prompt and '"OFF"' in prompt


def test_prompt_teaches_the_per_node_load_trap(prompt):
    """A ConcentratedForce magnitude is written once per node, so the spec has to
    declare the count and divide. Measured: 400 N against the 100 N written."""
    assert "每节点" in prompt
    assert "400 N" in prompt
    assert "expect: {points: 4}" in prompt


def test_prompt_teaches_the_reversed_step_order_trap(prompt):
    assert "previous: Initial" in prompt
    assert "第二步的 previous 必须写第一步的名字" in prompt


def test_prompt_teaches_the_deck_dialect_and_its_one_prohibition(prompt):
    """`deck:` is four lines, which is exactly why it needs saying.

    The prohibition is the part that matters: a deck already carries its own
    parts, steps and loads, so a spec that also states them describes a model
    that never ran. It is refused rather than ignored, and the prompt has to
    say so or the model will helpfully fill the blocks in.
    """
    for rule in ("deck.file", "parts / assembly / steps / conditions / interactions",
                 "拒绝而不是忽略"):
        assert rule in prompt


def test_prompt_routes_between_the_dialects(prompt):
    assert "不许混写" in prompt


def test_prompt_sends_every_new_spec_to_v2(prompt):
    """Routing flipped 2026-08-16. It used to send the simple shapes to v1, and
    a measured run showed what that costs: v1's load enum has no direction on
    `pressure`, so a request for 100 N downward came back as an "equivalent"
    0.25 MPa pressure, which Abaqus applies along the face normal — bending
    became axial compression, the job finished COMPLETED, and the stress read
    0.47 MPa against the 15 MPa the planner itself had predicted.

    The dialect itself went the same day. What the prompt must now say about a
    spec that still carries those keys is NOT "keep editing it in place" — the
    schema refuses them, so that advice produces a spec that cannot validate —
    but "say so and offer to rewrite it". Rewriting silently would change the
    spec's run id and void whatever baseline it is graded against, which is why
    the offer has to be explicit rather than assumed."""
    assert "描述模型一律用 v2（parts:），没有例外" in prompt
    assert "任何时候都不要写它们" in prompt
    assert "提出改写成 v2，不要默默改" in prompt
    # The reason travels with the rule; a rule with no measurement behind it is
    # the first thing a later edit trims.
    assert "0.47" in prompt and "15 MPa" in prompt


def test_prompt_forbids_step_type_in_v2(prompt):
    """The schema refuses it: steps[].type already says it, and two places to say
    one thing is two places to disagree."""
    assert "绝对不许写 step_type" in prompt


def test_prompt_keeps_the_measured_release_and_the_arithmetic_rule(prompt):
    assert '"2021"' in prompt
    assert "不要自己编版本号" in prompt
    assert "科学计数法" in prompt


def test_prompt_keeps_the_two_section_output_contract(prompt):
    assert planner._SPEC_MARK in prompt
    assert planner._REPLY_MARK in prompt
    assert prompt.index(planner._SPEC_MARK) < prompt.index(planner._REPLY_MARK)


def test_prompt_carries_the_context_it_is_given(monkeypatch):
    monkeypatch.setattr(planner, "detect_abaqus_release", lambda: "2021")
    built = planner.build_prompt(
        "载荷改成 20N",
        "meta:\n  model_name: Old\n",
        [{"role": "user", "text": "建个悬臂梁"}],
    )
    assert "载荷改成 20N" in built
    assert "model_name: Old" in built
    assert "建个悬臂梁" in built


@pytest.mark.parametrize("detected", ["2021", None], ids=["measured", "unmeasured"])
def test_the_release_the_prompt_names_is_one_the_schema_accepts(monkeypatch, detected):
    """Whatever the probe answers, the prompt has to name a release that validates.

    meta.abaqus_release is an enum of years, read here out of the schema file
    rather than restated. "unknown" is not in it, so telling the model to write
    that word costs two claude calls and ends in PlannerError with no proposal —
    the probe failing is not a reason to stop answering.
    """
    monkeypatch.setattr(planner, "detect_abaqus_release", lambda: detected)
    built = planner.build_prompt("悬臂梁", None, [])

    years = _schema()["properties"]["meta"]["properties"]["abaqus_release"]["enum"]
    named = re.search(r'meta\.abaqus_release 一律填 "([^"]+)"', built)
    assert named, "the release rule lost its value"
    assert named.group(1) in years


def test_an_unmeasured_release_is_declared_instead_of_asserted(monkeypatch):
    """The fallback is honest about being one.

    A year the probe never returned must not read as a measurement — the reply
    has to say so, and the open question has to reach the user.
    """
    monkeypatch.setattr(planner, "detect_abaqus_release", lambda: None)
    built = planner.build_prompt("悬臂梁", None, [])
    assert planner._FALLBACK_RELEASE in built
    assert "不是实测值" in built
    assert "missing_questions" in built

    monkeypatch.setattr(planner, "detect_abaqus_release", lambda: "2021")
    assert "不是实测值" not in planner.build_prompt("悬臂梁", None, [])


_YAML_BLOCK_RE = re.compile(r"```yaml\n(.*?)```", re.DOTALL)


def test_every_yaml_example_in_the_prompt_parses(prompt):
    """The examples are the specification as far as the model is concerned.

    An example that does not even load is a rule taught wrong, and this is also
    the guard on the reason _V2_DIALECT is kept out of the format template: a
    stray brace there would show up here as a parse failure rather than as a
    silently mangled prompt.
    """
    blocks = _YAML_BLOCK_RE.findall(prompt)
    assert len(blocks) >= 8, "the v2 section lost its worked examples"
    for block in blocks:
        yaml.safe_load(block)


# ---------------------------------------------------------------------------
# Drift: the prompt against the builder, in both directions
# ---------------------------------------------------------------------------
#
# These exist because the prompt had already fallen behind once. Between #64
# and #74 the builder gained five capability layers -- part-scope sets and
# seams, geometry and orphan-mesh import, node@/element@ selectors,
# reference points, and four more argument forms -- and the prompt learned none
# of them. Nothing failed: every existing test still passed, because they all
# asked "is what the prompt teaches true?" and none asked "is what the builder
# does taught?". A capability the planner cannot name is a capability the user
# cannot reach, and it is invisible from inside the prompt.


def test_every_argument_form_the_builder_resolves_is_taught(prompt):
    """`arg_forms._ARG_FORMS` is the authority; the prompt's list is typed by hand.

    Read from the tuple rather than compared to a list written out here, so a
    form added to the generator fails this until someone teaches it.
    """
    for form in arg_forms._ARG_FORMS:
        assert "{%s:" % form in prompt, (
            "%s resolves in the builder and the prompt never names it" % form)


def test_the_prompt_states_how_many_argument_forms_there_are(prompt):
    """The count, not just the entries.

    A list can gain an entry and stay plausible; a number that no longer matches
    is what makes the omission visible. This is the assertion that would have
    caught the four forms #74 found missing from the schema description.
    """
    stated = re.search(r"这\s*(\d+)\s*种形式", prompt)
    assert stated, "the prompt no longer says how many argument forms there are"
    assert int(stated.group(1)) == len(arg_forms._ARG_FORMS)


def test_every_selector_kind_the_parser_accepts_is_taught(prompt):
    """Same shape, for `core.selectors.KINDS`.

    node and element were added for orphan meshes, where they are the ONLY
    kinds that resolve: such a part has no cells, faces, edges or vertices at
    all. A planner that cannot write `node@` cannot put a boundary condition on
    an imported mesh.
    """
    kinds = _selector_kind_line(prompt)
    for kind in selectors.KINDS:
        assert kind in kinds, (
            "%s@ parses and the prompt's kind list omits it" % kind)


def _selector_kind_line(prompt: str) -> str:
    line = [ln for ln in prompt.splitlines() if ln.strip().startswith("kind")]
    assert len(line) == 1, "the selector grammar block moved"
    return line[0]


def test_the_kind_that_refuses_a_plane_is_taught_as_refusing_one(prompt):
    """`element@x=0` is refused, and the prompt has to say so and say what to use.

    Measured (scripts/run_orphan_mesh_check.py): getByBoundingBox on elements is
    wholly-inside, so a zero-thickness plane matches 0 of 80 while a band one
    element thick matches the 4 of that layer. A planner that writes
    `element@z=min` meets a refusal; one that was never told writes it.
    """
    for kind in selectors.PLANE_REFUSED:
        assert "`%s@` 只收 `@all`" % kind in prompt
    assert "nodes@" in prompt, "the refusal has to name the way round it"


def test_the_seam_expect_the_prompt_teaches_is_the_shape_the_builder_requires():
    """The seam example's expect keys, checked by mutation rather than by eye.

    `{set:, duplicated:}` was written `{name:, positions:}` on the first draft
    here and the generator refused it. That refusal is the only reason this is
    right, so it is pinned: dropping either key has to keep refusing.
    """
    spec = yaml.safe_load(_SEAM_ON_A_PART)
    stated = spec["parts"][0]["expect"]["seams"]
    assert stated == [{"set": "SEAMFACE", "duplicated": 9}]

    # The set named is the one the assignSeam call builds, not a free-floating
    # name -- a seam checked against a set nobody made is not checked.
    seam = [f for f in spec["parts"][0]["features"]
            if f.get("call") == "assignSeam"][0]
    assert seam["regions"]["name"] == stated[0]["set"]

    for drop in ("set", "duplicated"):
        broken = copy.deepcopy(spec)
        del broken["parts"][0]["expect"]["seams"][0][drop]
        with pytest.raises(spec_base.SpecError) as caught:
            build_v2.generate_script(broken)
        assert "expect.seams" in str(caught.value)


def test_an_imported_part_that_states_nothing_is_refused(spec_dir):
    """The rule the prompt gives for imports, asserted against the builder.

    Both scenarios carry an expect. What makes that a rule rather than a habit
    is that removing it refuses -- measured on Abaqus 2021, IGES returns 0 cells
    and volume 0.0 without raising, so an import nobody checked is an empty part
    that meshes, solves and reports.
    """
    for text in (_ORPHAN_MESH_IMPORT, _GEOMETRY_IMPORT):
        spec = yaml.safe_load(text)
        ast.parse(build_v2.generate_script(spec, spec_dir))

        stripped = copy.deepcopy(spec)
        del stripped["parts"][0]["expect"]
        with pytest.raises(spec_base.SpecError) as caught:
            build_v2.generate_script(stripped, spec_dir)
        assert "expect" in str(caught.value)


def test_prompt_teaches_the_import_route_and_why_it_needs_a_count(prompt):
    assert "import:" in prompt
    assert "PartFromInputFile" in prompt and "PartFromGeometryFile" in prompt
    assert "expect: {mesh: {nodes:" in prompt or "nodes:" in prompt
    # The measurement is the argument. Without it the count reads as ceremony
    # and gets dropped the first time it is inconvenient.
    assert "IGES" in prompt


def test_prompt_does_not_teach_a_crack(prompt):
    """Cracks are unmeasured here (#75), including what their truth layer would
    be. Silence is the honest state: a planner taught `XFEMCrack` would emit it
    confidently and nothing downstream would know whether it did anything."""
    assert "XFEMCrack" not in prompt or "还没测过" in prompt


_ASSEMBLY_ONLY_FORMS = {
    "instance": {"instance": "Bolt"},
    "vertex": {"vertex": {"instance": "Bar", "at": [0.0, 0.0, 0.0]}},
    "wire_at": {"wire_at": [[0.0, 0.0, 0.0], [0.0, 0.0, 10.0]]},
    "reference_point": {"reference_point": [0.0, 0.0, 100.0]},
}


@pytest.mark.parametrize("form", sorted(_ASSEMBLY_ONLY_FORMS))
def test_the_forms_the_prompt_calls_assembly_only_really_are(form):
    """The prompt states this; the builder is what makes it true.

    A part feature runs before anything is instanced, so all four have nothing
    to resolve against there. Stated in the prompt rather than left to the
    refusal because the model would otherwise write them in `parts:` -- they
    read like part-level constructs.
    """
    value = _ASSEMBLY_ONLY_FORMS[form]
    with pytest.raises(spec_base.SpecError):
        arg_forms._arg_expr("part 'P' feature[0]", "region", value,
                           {}, set(), scope="part")

    # And they resolve in the assembly, so this is a scope rule and not a ban.
    arg_forms._arg_expr("interaction 'I'", "region", value, {}, set(),
                       scope="assembly", surfaces=[], sets=[])


def test_the_prompt_names_all_four_as_assembly_only(prompt):
    line = [ln for ln in prompt.splitlines() if "只能写在装配域" in ln]
    assert len(line) == 1
    for form in _ASSEMBLY_ONLY_FORMS:
        assert "{%s:" % form in line[0]
