"""The other planner: prompts/spec_generator.txt, behind agent/llm_planner.py.

Two planners feed this project and they are easy to confuse. `workbench/planner.py`
drives the Copilot chat and is covered by tests/test_workbench_planner_v2.py. THIS
one is the prompt the HTTP server (server.py) and the MCP server (mcp_server.py)
use for `text -> spec`, via core.spec_generator.generate_spec_async.

Hermetic: no LLM is called anywhere here, and none can be -- the point is that
the two things which can be checked without one are checked.

WHAT THE EXAMPLES ARE FOR. A prompt's worked examples are its specification as
far as the model is concerned. An example the schema refuses, or one the builder
will not compile, teaches the model to emit exactly that, and the user meets the
failure as a validation error against a spec the chat just told them was fine.
So every YAML block in the prompt is pulled out and pushed through the real
schema, and every v2 block through runner.build_v2.generate_script.

WHAT THE BOUNDARY IS FOR. generate_spec_async used to wrap the whole LLM path in
`except Exception: pass`, so a spec the model wrote and validation rejected was
replaced by a default cantilever and returned -- reported as valid, with nothing
saying the request had been dropped. Someone who asked for two plates tied
together got a cantilever. The split between `LLMPlanner.call` and
`LLMPlanner.parse` is what makes the two failures distinguishable, and the tests
at the bottom pin it in both directions.
"""

from __future__ import annotations

import asyncio
import re
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import agent.llm_planner as llm_planner  # noqa: E402
from core.spec_generator import generate_spec_async  # noqa: E402
from runner import build_v2  # noqa: E402
from runner.build_model import _is_v2  # noqa: E402
from tools.errors import AbaqusAgentError, ErrorCode  # noqa: E402
from tools.schema_validator import validate_spec  # noqa: E402

PROMPT_PATH = ROOT / "prompts" / "spec_generator.txt"


# ---------------------------------------------------------------------------
# The prompt's own examples
# ---------------------------------------------------------------------------

def _yaml_examples(text: str) -> list[tuple[int, str]]:
    """Every spec example in the prompt, with the line it starts on.

    The prompt forbids code fences in the OUTPUT, so the examples are not fenced
    either -- fencing them here would teach the model to fence its answer. A
    block therefore starts at a bare `meta:` in column 0 and runs until a
    non-empty column-0 line that is not a YAML key, which is how the prose
    headings (`## ...`, `Example — ...`) end one.
    """
    lines = text.splitlines()
    blocks: list[tuple[int, str]] = []
    i = 0
    while i < len(lines):
        if lines[i] != "meta:":
            i += 1
            continue
        j = i + 1
        while j < len(lines):
            line = lines[j]
            if (line.strip() and not line.startswith((" ", "-"))
                    and not re.match(r"^[a-z_][a-z0-9_]*:", line)):
                break
            j += 1
        blocks.append((i + 1, "\n".join(lines[i:j]).rstrip() + "\n"))
        i = j
    return blocks


@pytest.fixture(scope="module")
def examples() -> list[tuple[int, str]]:
    found = _yaml_examples(PROMPT_PATH.read_text(encoding="utf-8"))
    assert found, "the prompt lost its worked examples, or the extractor broke"
    return found


def test_the_prompt_carries_an_example_of_each_dialect(examples):
    """One example each is the minimum for the routing rule to mean anything.

    The prompt spends a paragraph on when to describe a model and when to hand
    one over. With examples of only one of them -- which is what this file used
    to hold, back when the other dialect was v1 -- that paragraph is advice the
    model has never seen carried out, and every spec comes back the same shape.
    A deck is the surviving non-v2 dialect, so it is the one that has to be
    demonstrated: `deck:` is four lines and easy to leave undocumented.
    """
    def dialect(spec: dict) -> str:
        if _is_v2(spec):
            return "v2"
        return "deck" if "deck" in spec else "neither"

    dialects = {dialect(yaml.safe_load(block)) for _line, block in examples}
    assert dialects == {"deck", "v2"}


def test_the_prompt_sends_every_new_spec_to_v2():
    """Routing flipped 2026-08-16, in both planners.

    This is the prompt the HTTP and MCP servers use, so it is the one an outside
    agent (dsh, Codex, any MCP client) reaches. It used to send the four built-in
    shapes to v1. A measured run showed the cost: v1's `pressure` carries no
    direction, so "100 N downward" came back as an equivalent 0.25 MPa pressure,
    which Abaqus applies along the face normal -- bending became axial
    compression, the job finished COMPLETED, and the stress read 0.47 MPa where
    the planner's own prediction said 15 MPa.

    The advice to "stay in v1 while editing a v1 spec" went with the dialect on
    the same day: the schema refuses those keys outright now, so a model that
    followed it would write a spec that cannot validate. What replaces it is an
    instruction to SAY SO — a rewrite offered is better than a silent one, which
    would change the spec's run id and void whatever baseline it is graded
    against.
    """
    prompt = PROMPT_PATH.read_text(encoding="utf-8")
    assert "for every spec that describes a model. No exceptions" in prompt
    assert "never write those keys" in prompt
    assert "offer to rewrite it in v2" in prompt
    assert "0.47 MPa" in prompt and "15 MPa" in prompt


def test_every_example_in_the_prompt_passes_the_real_schema(examples):
    for line, block in examples:
        valid, errors = validate_spec(yaml.safe_load(block))
        assert valid, "prompt line %d: %s" % (line, errors)


def test_every_v2_example_in_the_prompt_builds(examples):
    """The check the schema cannot make.

    Everything the builder learned to refuse across #45-#71 passes the schema:
    a generic feature call with no `expect:`, an import that states no count, a
    seam nothing checks. An example carrying one of those is a mistake the model
    would copy.
    """
    for line, block in examples:
        spec = yaml.safe_load(block)
        if _is_v2(spec):
            build_v2.generate_script(spec)   # SpecError names the prompt's bug


def test_the_release_in_the_examples_is_the_one_this_machine_has(examples):
    """2024 was written here and this machine runs 2021.

    Not cosmetic: `meta.abaqus_release` is a year enum, it feeds the run_id hash,
    and the prompt is the only place the model learns what to write. It is a
    fallback -- core/pipeline.py detects the release at run time -- and the
    prompt has to say so rather than let the number pass for a measurement.
    """
    for line, block in examples:
        release = yaml.safe_load(block)["meta"]["abaqus_release"]
        assert release == "2021", "prompt line %d states %r" % (line, release)
    text = PROMPT_PATH.read_text(encoding="utf-8")
    assert "detects the release from the installed Abaqus at run time" in text


def test_the_kpi_types_the_prompt_teaches_are_the_ones_the_schema_has():
    """Read from the schema, not remembered.

    Both directions: a type the schema gained and the prompt never learned is a
    KPI nobody can ask for, and one the prompt teaches and the schema refuses is
    a spec the user watches fail for a reason the chat called fine.
    """
    import json
    schema = json.loads(
        (ROOT / "schema" / "spec_schema.json").read_text(encoding="utf-8"))
    kpi = (schema["properties"]["outputs"]["properties"]["kpis"]["items"]
           ["properties"]["type"]["enum"])
    text = PROMPT_PATH.read_text(encoding="utf-8")

    section = text.split("### KPI types")[1].split("\n##")[0]
    # The indented lines are the list itself, pipe-separated. Read that rather
    # than every word in the paragraph, so the prose around it can be reworded.
    listed = " ".join(line for line in section.splitlines()
                      if line.startswith("  ") and line.strip())
    taught = {word for word in re.split(r"[|\s]+", listed) if word}
    assert taught == set(kpi), (
        "prompt teaches %s the schema refuses; schema has %s the prompt omits"
        % (sorted(taught - set(kpi)), sorted(set(kpi) - taught)))


# ---------------------------------------------------------------------------
# The dry build inside parse()
# ---------------------------------------------------------------------------

# Schema-valid and refused by the builder: a part with a generic `call:` feature
# and no `expect:` block. This is the whole reason parse() dry-builds -- the
# schema has no way to know that a datum plane the model added leaves nothing
# behind to check.
_NO_EXPECT = """
meta: {abaqus_release: "2021", model_name: NoExpect, units: mm_MPa_t}
material: {name: Steel, E: 210000.0, nu: 0.3}
parts:
  - name: Blk
    features:
      - {op: sketch, id: o, plane: XY,
         profile: {rect: {corner1: [0.0, 0.0], corner2: [10.0, 10.0]}}}
      - {op: extrude, sketch: o, depth: 20.0}
      - {call: DatumPlaneByPrincipalPlane, principalPlane: XYPLANE,
         offset: 10.0, as: mid}
    section: {type: solid, material: Steel}
    mesh: {seed: 5.0, element: C3D8I}
assembly:
  instances: [{name: B, part: Blk}]
steps:
  - {call: StaticStep, name: {literal: One}, previous: {literal: Initial}}
conditions:
  - {call: EncastreBC, name: {literal: Fix}, createStepName: {literal: Initial},
     region: {set: "B:face@z=min", name: FIX, expect: "=1"}}
outputs:
  kpis: [{name: U_TIP, type: field_min, location: whole_model, component: U2}]
"""

_RELATIVE_FILE = """
meta: {abaqus_release: "2021", model_name: Imported, units: mm_MPa_t}
material: {name: Steel, E: 210000.0, nu: 0.3}
parts:
  - name: Bar
    import:
      part: {call: PartFromInputFile, inputFileName: {file: bar.inp}}
    expect: {mesh: {nodes: 189, elements: 80}}
    section: {type: solid, material: Steel}
assembly:
  instances: [{name: B, part: Bar}]
steps:
  - {call: StaticStep, name: {literal: One}, previous: {literal: Initial}}
conditions:
  - {call: EncastreBC, name: {literal: Fix}, createStepName: {literal: Initial},
     region: {set: "B:nodes@z=min", name: FIX, expect: "=9"}}
outputs:
  kpis: [{name: U_TIP, type: field_min, location: whole_model, component: U2}]
"""


# A finished .inp handed over as it stands. Schema-valid, and carries no `parts:`
# for the v2 generator to work on.
_DECK = """
meta: {abaqus_release: "2021", model_name: Handover, units: mm_MPa_t}
deck: {file: frame.inp}
material: {name: Steel, E: 210000.0, nu: 0.3}
outputs:
  kpis: [{name: U_TIP, type: field_min, location: whole_model, component: U2}]
"""


def _planner() -> llm_planner.LLMPlanner:
    """A planner with no backend resolved -- only parse() is exercised."""
    return llm_planner.LLMPlanner(backend="template")


def test_the_no_expect_spec_really_is_schema_valid():
    """The premise of the test below. If the schema ever grows a rule that
    catches this, the dry build is no longer what is being demonstrated and this
    file has to find another counterexample rather than quietly prove nothing.
    """
    valid, errors = validate_spec(yaml.safe_load(_NO_EXPECT))
    assert valid, errors


def test_parse_refuses_a_spec_the_schema_passes_and_the_builder_will_not_build():
    with pytest.raises(AbaqusAgentError) as caught:
        _planner().parse(_NO_EXPECT)
    assert caught.value.code is ErrorCode.SPEC_INVALID
    # The builder's own words, which name the part and the missing key. A
    # generic "invalid spec" here would be a worse answer than the traceback.
    assert "expect:" in str(caught.value)
    assert "Blk" in str(caught.value)


def test_parse_accepts_a_spec_that_builds():
    spec, missing = _planner().parse(_RELATIVE_FILE.replace(
        "{file: bar.inp}", "{file: bar.inp}"))
    assert _is_v2(spec)
    assert missing, "a spec that could not be dry-built has to say so"


def test_a_relative_file_path_is_declared_undecidable_rather_than_refused():
    """`{file:}` resolves against the spec FILE's directory and this spec has
    never been written to one. Refusing it would reject a correct spec; building
    without it would claim a check that never ran. So it says which."""
    spec, missing = _planner().parse(_RELATIVE_FILE)
    assert any("没落盘" in note for note in missing)
    assert spec["parts"][0]["import"]["part"]["inputFileName"] == {"file": "bar.inp"}


def test_an_absolute_file_path_is_dry_built(tmp_path):
    deck = tmp_path / "bar.inp"
    deck.write_text("** placeholder\n", encoding="utf-8")
    text = _RELATIVE_FILE.replace("bar.inp", str(deck).replace("\\", "/"))
    spec, missing = _planner().parse(text)
    assert missing == [], missing


def test_a_deck_spec_is_not_dry_built():
    """`_is_v2` means "has parts:", and a deck spec has none — it hands over a
    finished .inp and describes nothing. Running the v2 generator over one would
    refuse every correct deck spec there is for a missing `parts:` block, so the
    dry build has to skip it, silently and by design.

    This used to be pinned with a v1 spec (cases/cantilever/spec.yaml, back when
    it was one). That dialect is gone; deck is the surviving non-v2 one, and it
    reaches the same branch.
    """
    deck = yaml.safe_load(_DECK)
    assert not _is_v2(deck)
    assert llm_planner._dry_build_notes(deck) == []


# ---------------------------------------------------------------------------
# The fallback boundary in core/spec_generator.py
# ---------------------------------------------------------------------------

def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)
    finally:
        loop.close()
        asyncio.set_event_loop(asyncio.new_event_loop())


def test_a_backend_that_never_answered_falls_back_to_the_template(monkeypatch):
    """No key, no package, no network: the model said nothing, and a template is
    a fair answer to that."""
    real = llm_planner.LLMPlanner

    class Unreachable(real):
        def call(self, text):
            raise RuntimeError("openai package not installed")

        def parse(self, raw):
            raise AssertionError("must not be reached")

    monkeypatch.setattr(llm_planner, "LLMPlanner", Unreachable)
    spec, _missing = _run(generate_spec_async("两块板绑在一起", "2021", "openai"))
    # v2, like every other spec written from scratch. The template is the one
    # spec nobody reviews before it runs, so it may not be the frozen dialect.
    assert "geometry" not in spec and "bc_load" not in spec
    assert [part["name"] for part in spec["parts"]] == ["Beam"]
    assert spec["meta"]["missing_questions"], (
        "a template answer has to say what it guessed at")


def test_an_answer_the_builder_refuses_is_not_replaced_by_a_cantilever(monkeypatch):
    """The regression this file exists for.

    Before the split, this returned the default cantilever and server.py
    reported it `valid: true`. The user asked for two tied plates and got a
    cantilever, with nothing anywhere saying their request had been dropped.
    """
    real = llm_planner.LLMPlanner

    class Answered(real):
        def __init__(self, backend): pass

        def call(self, text):
            return _NO_EXPECT

    monkeypatch.setattr(llm_planner, "LLMPlanner", Answered)
    with pytest.raises(AbaqusAgentError) as caught:
        _run(generate_spec_async("一个分区的块", "2021", "openai"))
    assert caught.value.code is ErrorCode.SPEC_INVALID


def test_an_answer_that_is_not_yaml_is_not_replaced_either(monkeypatch):
    real = llm_planner.LLMPlanner

    class Babbled(real):
        def __init__(self, backend): pass

        def call(self, text):
            return "Sure! Here is your spec:\n```yaml\nmeta: {: :}\n```"

    monkeypatch.setattr(llm_planner, "LLMPlanner", Babbled)
    with pytest.raises(AbaqusAgentError):
        _run(generate_spec_async("悬臂梁", "2021", "openai"))


def test_the_key_is_restored_even_when_parse_refuses(monkeypatch):
    """The env restore used to sit inside the swallowed block. It has to survive
    the refusal now that the refusal propagates."""
    import os
    real = llm_planner.LLMPlanner

    class Answered(real):
        def __init__(self, backend): pass

        def call(self, text):
            assert os.environ["OPENAI_API_KEY"] == "temporary-key"
            return _NO_EXPECT

    monkeypatch.setenv("OPENAI_API_KEY", "original-key")
    monkeypatch.setattr(llm_planner, "LLMPlanner", Answered)
    with pytest.raises(AbaqusAgentError):
        _run(generate_spec_async("x", "2021", "openai", openai_key="temporary-key"))
    assert os.environ["OPENAI_API_KEY"] == "original-key"
