"""First-order reduced-integration elements have to say so. (#72)

THE MEASUREMENT. The same imported 10x10x100 bar, the same seed, the same load;
only the element code differs:

    C3D8I  tip  -0.189446    0.54% from the closed form
    C3D8R  tip -17.237131    90.5x the closed form

and the C3D8R job reported COMPLETED with nothing on screen. Refining the seed
to 5 mm left it 1.3x off. One string in `mesh.element` is the lowest-effort way
in this engine to get an answer that is confidently, enormously wrong — and
when the key is omitted, `C3D8R` is what the spec gets by DEFAULT.

WHAT WAS DECIDED. 2026-08-07, user's call: 警告并写进报告 — warn and put it in
the report. Not refuse. So these tests assert the warning exists AND that
nothing about the verdict changed; a build that starts refusing C3D8R fails
here, because reduced integration is the correct element under explicit
dynamics with enhanced hourglass control and on a model with no bending.

THE CLASSIFIER IS A RULE, NOT A LIST. `hourglass_verdict` reads Abaqus's naming
grammar — `<family><nodes><modifiers>`, `R` = reduced, node count vs the
family's first-order ceiling — so an element nobody has typed into this repo
classifies correctly if its family is known. The third verdict, `unreadable`,
is the honest one: `B31R` carries an `R` but its digits are not a node count
(`B31` = beam, 3D, order 1), so any rule read off them would be invented.
Silence from this module must mean "no reduced integration", never "we could
not tell".
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.orchestrator import AbaqusOrchestrator  # noqa: E402
from core.element_risk import (  # noqa: E402
    CLEAR,
    RISK,
    UNREADABLE,
    hourglass_verdict,
    limitation_entries,
    parse_element_code,
    spec_hourglass_findings,
)
from reporting import templates  # noqa: E402

# --- the grammar -----------------------------------------------------------

def test_the_node_count_is_the_last_digit_run_not_the_first():
    """`C3D8R` must not parse as family "C", 3 nodes. The "3D" is the family."""
    assert parse_element_code("C3D8R") == {"family": "C3D", "nodes": 8, "mods": "R"}
    assert parse_element_code("C3D20RT") == {"family": "C3D", "nodes": 20,
                                             "mods": "RT"}


@pytest.mark.parametrize("code", [
    "C3D8R",     # the measured one
    "C3D8RT",    # same element, coupled temperature-displacement
    "CPE4R", "CPS4R", "CAX4R",   # 2D continuum, first-order quad
    "S4R", "M3D4R",              # shell and membrane
    "SC8R",      # continuum shell: a hex, so its first-order ceiling is 8
])
def test_first_order_reduced_elements_are_flagged(code):
    verdict = hourglass_verdict(code)
    assert verdict["verdict"] == RISK, verdict
    for number in ("90.5", "92.1", "1.34"):
        assert number in verdict["why"], (
            "the warning has to carry the measurements, including the second "
            "reproduction and the mesh that makes the difference — advice "
            "without a number reads as boilerplate and gets ignored")


@pytest.mark.parametrize("code", [
    "C3D8I", "C3D8", "C3D10", "C3D20",   # no R at all
    "C3D20R", "C3D20RT",                 # second-order reduced: the safe ones
    "S8R",                               # second-order shell
    "CPE8R", "CAX8R",                    # second-order 2D continuum
    "T3D2",                              # truss, no R
])
def test_elements_that_do_not_hourglass_are_left_alone(code):
    assert hourglass_verdict(code)["verdict"] == CLEAR, code


@pytest.mark.parametrize("code", ["B31R", "B21R", "nonsense", "", "12345"])
def test_what_cannot_be_classified_is_not_called_safe(code):
    """`unreadable` is a distinct answer from `clear`, and this is why.

    In `B31` the digits mean "3D, order 1", not a node count. A rule applied to
    them would produce a confident answer about an element it did not
    understand — the exact failure mode this repository exists to avoid.
    """
    assert hourglass_verdict(code)["verdict"] == UNREADABLE, code


def test_the_second_order_boundary_is_per_family_not_global():
    """`C3D8` is first-order and `CPE8` is second-order. Same digit."""
    assert hourglass_verdict("C3D8R")["verdict"] == RISK
    assert hourglass_verdict("CPE8R")["verdict"] == CLEAR


def test_the_longest_family_prefix_wins():
    """`SC8R` is a continuum shell (hex, ceiling 8), not an `S` shell."""
    assert hourglass_verdict("SC8R")["verdict"] == RISK
    assert hourglass_verdict("S8R")["verdict"] == CLEAR


# --- the spec walker -------------------------------------------------------

def _spec(mesh: dict | None) -> dict:
    part = {"name": "Bar", "section": {"type": "solid", "material": "Steel"}}
    if mesh is not None:
        part["mesh"] = mesh
    return {"parts": [part]}


def test_a_declared_risky_element_is_found_and_located():
    findings = spec_hourglass_findings(_spec({"seed": 5.0, "element": "C3D8R"}))
    assert len(findings) == 1
    assert findings[0]["element"] == "C3D8R"
    assert findings[0]["where"] == "parts[Bar].mesh.element"
    assert findings[0]["from_default"] is False


def test_the_default_element_is_reported_as_a_default():
    """The highest-value case: saying nothing is what gets you the 90x answer."""
    findings = spec_hourglass_findings(_spec({"seed": 5.0}))
    assert len(findings) == 1
    assert findings[0]["from_default"] is True
    entry = limitation_entries(findings)[0]
    assert "默认值" in entry["reason"], (
        "a reader who did not type C3D8R needs to be told they got it anyway")


def test_the_default_matches_what_the_generator_actually_uses():
    """A drift guard, not a restatement.

    `core/element_risk` names the default so it can warn about it; if the
    generator ever changes it, the warning would name an element the deck does
    not contain. Read out of both places rather than typed twice.

    The constant lives in runner/mesh_policy.py; the read of it stayed in
    runner/build_v2.py, which is the point of the split -- the table is a fact
    about Abaqus, the read is a step in compiling a spec.
    """
    from runner import mesh_policy

    source = (ROOT / "runner" / "build_v2.py").read_text(encoding="utf-8")
    assert 'mesh_spec.get("element", DEFAULT_MESH_ELEMENT)' in source, (
        "the generator stopped reading the named constant, so the warning and "
        "the deck can now disagree about what a spec with no element: gets")
    assert hourglass_verdict(mesh_policy.DEFAULT_MESH_ELEMENT)["verdict"] == RISK, (
        "the default is no longer hourglass-prone. Good — but this test and "
        "the warning it guards are now about nothing, and the frozen decks "
        "built from specs that omit element: have all changed")


def test_a_part_with_no_mesh_block_is_not_walked():
    """It is refused elsewhere, loudly. Warning about it here would be noise."""
    assert spec_hourglass_findings(_spec(None)) == []


def test_a_v1_spec_produces_nothing():
    """v1 has no element key, and build_model's own choices are correct.

    Standard gets C3D20R; Explicit gets C3D8R with `hourglassControl=ENHANCED`,
    which is the textbook right way to use a reduced element. Warning on it
    would teach the reader to ignore this channel.
    """
    v1 = yaml.safe_load((ROOT / "cases" / "cantilever" / "spec.yaml")
                        .read_text(encoding="utf-8"))
    assert spec_hourglass_findings(v1) == []
    build_model = (ROOT / "runner" / "build_model.py").read_text(encoding="utf-8")
    assert "hourglassControl=_C.ENHANCED" in build_model, (
        "the explicit path stopped asking for enhanced hourglass control, so "
        "v1 now has the very problem this file says it does not")


def test_no_shipped_case_trips_the_warning():
    """The noise check, and the reason this could ship without re-grading.

    Every v2 case names its element explicitly and none of them names a
    first-order reduced one, so no shipped run gains a limitation and no
    verdict or run_id moves. If a case is ever added that does, this fails and
    the choice gets made deliberately instead of arriving as a surprise in a
    frozen baseline.
    """
    tripped = {}
    for spec_path in sorted((ROOT / "cases").glob("*/spec.yaml")):
        spec = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
        findings = spec_hourglass_findings(spec)
        if findings:
            tripped[spec_path.parent.name] = [f["element"] for f in findings]
    assert tripped == {}, tripped


# --- the orchestrator ------------------------------------------------------

def _bare(result: dict, spec: dict) -> AbaqusOrchestrator:
    orch = AbaqusOrchestrator.__new__(AbaqusOrchestrator)
    orch.result = result
    orch.spec = spec
    orch.on_progress = lambda *a, **k: None
    return orch


def test_the_warning_reaches_the_top_level_and_the_limitations_channel():
    orch = _bare({}, _spec({"seed": 5.0, "element": "C3D8R"}))
    orch._record_mesh_risks()

    assert [f["element"] for f in orch.result["mesh_risks"]] == ["C3D8R"]
    entry = orch.result["limitations"][0]
    assert entry["kind"] == "hourglass_risk"
    assert entry["value"] == "C3D8R"
    assert "90.5" in entry["reason"]


def test_running_it_twice_does_not_duplicate_the_entry():
    """The retry loop calls `_stage_validate` once per attempt."""
    orch = _bare({}, _spec({"seed": 5.0, "element": "C3D8R"}))
    orch._record_mesh_risks()
    orch._record_mesh_risks()
    assert len(orch.result["limitations"]) == 1


def test_a_repaired_spec_replaces_the_old_finding_rather_than_adding_to_it():
    orch = _bare({}, _spec({"seed": 5.0, "element": "C3D8R"}))
    orch._record_mesh_risks()
    orch.spec = _spec({"seed": 5.0, "element": "C3D8I"})
    orch._record_mesh_risks()
    assert orch.result["mesh_risks"] == []
    assert orch.result["limitations"] == []


def test_it_does_not_erase_limitations_from_another_source():
    """CalculiX caveats are already in this list before validation runs."""
    orch = _bare(
        {"limitations": [{"feature": "element", "value": "C3D8I",
                          "reason": "CalculiX 没有这个单元"},
                         "a .dat integrity finding, written as a bare string"]},
        _spec({"seed": 5.0, "element": "C3D8R"}))
    orch._record_mesh_risks()
    orch._record_mesh_risks()

    kinds = [e.get("kind") if isinstance(e, dict) else "str"
             for e in orch.result["limitations"]]
    assert kinds == [None, "str", "hourglass_risk"]


def test_validate_actually_calls_it():
    """The helper can be perfect and never run. Nothing else here would notice."""
    source = (ROOT / "agent" / "orchestrator.py").read_text(encoding="utf-8")
    body = source.split("def _stage_validate", 1)[1].split("\n    def ", 1)[0]
    assert "self._record_mesh_risks()" in body


def test_the_calculix_backend_gets_the_same_warning():
    """It subclasses the run loop, so the check must reach it unchanged."""
    from agent.ccx_orchestrator import CalculiXOrchestrator

    assert CalculiXOrchestrator._record_mesh_risks is \
        AbaqusOrchestrator._record_mesh_risks
    ccx = (ROOT / "agent" / "ccx_orchestrator.py").read_text(encoding="utf-8")
    assert "def _stage_validate" not in ccx, (
        "CalculiX now overrides validation, so it may no longer run the mesh "
        "risk check the parent wires in")


def test_the_verdict_is_not_touched():
    """#72 as decided: warn, do not refuse.

    Read off the source because the point is a negative — no exception type,
    no status assignment, no refusal anywhere on this path.
    """
    source = (ROOT / "agent" / "orchestrator.py").read_text(encoding="utf-8")
    body = source.split("def _record_mesh_risks", 1)[1].split("\n    def ", 1)[0]
    for forbidden in ("raise ", "status", "REFUSED", "FAILED"):
        assert forbidden not in body, forbidden


# --- the report ------------------------------------------------------------

def _report(limitations: list) -> dict:
    return {
        "summary": {"run_id": "r1", "status": "COMPLETED", "model_name": "M"},
        "kpis": {"U": 1.0}, "kpis_missing": [], "limitations": limitations,
        "regression": {}, "contracts": {}, "artifacts": {},
    }


def test_the_report_carries_the_warning():
    entry = limitation_entries(
        spec_hourglass_findings(_spec({"seed": 5.0, "element": "C3D8R"})))
    html = templates.render_run_report_html(_report(entry))
    assert "Known Limitations" in html
    assert "C3D8R" in html
    assert "90.5" in html


def test_every_markdown_template_carries_it():
    entry = limitation_entries(
        spec_hourglass_findings(_spec({"seed": 5.0, "element": "C3D8R"})))
    for template in ("standard", "client_summary", "engineering_delivery"):
        text = templates.render_run_report_markdown(_report(entry),
                                                    template=template)
        assert "## Known Limitations" in text, template
        assert "C3D8R" in text, template


def test_a_bare_string_limitation_reaches_the_report_too():
    """The shape `runner/dat_warnings.limitation_lines()` writes.

    It is the shape the workbench used to render as a blank card, and the one
    the report did not carry at all — an archived report is what gets sent to
    somebody who was not in the room.
    """
    text = templates.render_run_report_markdown(
        _report(["Tie 约束有 85 个节点没绑上（85 处）"]))
    assert "85 个节点没绑上" in text


def test_the_field_survives_every_hop_from_result_json_to_the_report():
    """The renderer can be right and receive nothing.

    `build_offline_run_report` and `load_offline_run` each copy an explicit
    list of keys out of `result.json`; a field added to one end and not the
    other is invisible in precisely the way this task is about. Same for the
    live path through `core/pipeline` and the session records.
    """
    for rel, marker in (
        ("reporting/export.py", '"limitations": run.get("limitations", [])'),
        ("reporting/export.py", '"limitations": result.get("limitations", [])'),
        ("core/pipeline.py", 'run["mesh_risks"] = result.get("mesh_risks", [])'),
        ("core/pipeline.py", '"mesh_risks": run.get("mesh_risks", [])'),
        ("workbench/routes.py", '"mesh_risks"'),
    ):
        assert marker in (ROOT / rel).read_text(encoding="utf-8"), (rel, marker)


@pytest.mark.parametrize("rel", ["workbench/planner_dialect.py",
                                 "prompts/spec_generator.txt"])
def test_both_planners_are_told_not_to_reach_for_the_risky_default(rel):
    """Warning after the fact is the second-best place to fix this.

    The best place is the spec that gets written. Both prompts used to offer
    `element: C3D8R` first — the workbench dialect doc (now
    workbench/planner_dialect.py) listed it as the head of "the usual four"
    and used it in its import example, which is the very model the 90x was
    measured on.
    """
    import re

    text = (ROOT / rel).read_text(encoding="utf-8")
    assert "92" in text, "%s does not carry the measured factor" % rel
    lowered = text.lower()
    assert ("两层" in text or "two elements" in lowered), (
        "%s does not say what actually fixes it — the number of elements "
        "through the thickness, not the seed" % rel)

    # The sharp half. An LLM copies the examples, not the prose: every
    # `element:` written in either prompt must classify CLEAR. This is checked
    # with the same classifier the engine warns with, so it cannot go stale.
    written = re.findall(r"element:\s*([A-Z][A-Z0-9]*)", text)
    assert written, "%s stopped showing any element at all" % rel
    risky = sorted({code for code in written
                    if hourglass_verdict(code)["verdict"] == RISK})
    assert risky == [], (
        "%s shows %s in an example. The prose warning does not undo an example "
        "— the example is the thing that gets copied." % (rel, risky))


def test_the_gate_and_the_warning_quote_the_same_experiment():
    """Both name the numbers; neither may drift from the other.

    The gate re-measures the ratio on every harness run. If someone loosens
    its floor or changes its mesh, the warning text would keep quoting numbers
    nothing produces any more.
    """
    from core.element_risk import MEASURED

    gate = (ROOT / "scripts" / "run_hourglass_warning_check.py").read_text(
        encoding="utf-8")
    assert "SEED = 10.0" in gate, (
        "the gate stopped using one element through the thickness, which is "
        "the condition the ~92x number belongs to")
    assert "MIN_RATIO = 10.0" in gate
    for number in ("-0.7126152", "-65.66674", "-0.9517219"):
        assert number in gate, number
    assert "0.7126152" in MEASURED and "65.66674" in MEASURED


def test_a_clean_run_gets_no_limitations_section():
    text = templates.render_run_report_markdown(_report([]))
    assert "Known Limitations" not in text


def test_the_section_survives_a_pipe_in_the_reason():
    text = templates.render_run_report_markdown(
        _report([{"feature": "f", "value": "v", "reason": "a|b|c"}]))
    row = [ln for ln in text.splitlines() if ln.startswith("| f |")][0]
    assert row.count("|") == 4
