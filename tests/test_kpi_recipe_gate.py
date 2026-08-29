"""The KPI recipe is refused BEFORE the solve, in the extractor's own words.

Round 4 of the full-flow audit (2026-08-18): the first spec deepseek-v4-pro
ever wrote for this product said `component: Mises` -- the plausible spelling,
since MISES is what an engineer calls the number. It passed the schema, passed
the dry build, and would have been refused by post/extract_kpis.py only after
a ~26-minute real solve. These tests pin the gate that moves that refusal
into validate_spec itself -- the one chokepoint every entrance shares
(planner parse, workbench accept, orchestrator _stage_validate, REST /
MCP validate endpoints) -- and pin that the gate speaks the extractor's
message, not a paraphrase.

Hermetic: no Abaqus, no network. The extractor module imports only stdlib at
module level, which is what lets its tables be the single source of truth.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.llm_planner import LLMPlanner  # noqa: E402
from odb_lens.recipe import validate_recipe  # noqa: E402
from tools.errors import AbaqusAgentError  # noqa: E402
from tools.schema_validator import validate_spec  # noqa: E402


def _spec_with_kpi(kpi: dict) -> dict:
    """The template-fallback spec, which is schema-valid v2, with one KPI."""
    spec, _ = LLMPlanner(backend="template").generate("测试悬臂梁")
    spec["meta"]["abaqus_release"] = "2021"
    spec["meta"]["missing_questions"] = []
    spec["outputs"]["kpis"] = [kpi]
    return spec


# ---------------------------------------------------------------------------
# validate_recipe: the shared table-backed checks
# ---------------------------------------------------------------------------

def test_component_mises_is_refused_and_points_at_invariant():
    ok, errors = validate_recipe([
        {"name": "S_MISES_MAX", "type": "field_max",
         "location": "whole_model", "component": "Mises"}])
    assert not ok
    assert "invariant, not a component" in errors[0]
    assert "invariant: MISES" in errors[0]


def test_unknown_component_is_refused_not_defaulted():
    ok, errors = validate_recipe([
        {"name": "S_SHEAR", "type": "field_max",
         "location": "whole_model", "component": "S12"}])
    assert not ok
    assert "S12" in errors[0]


def test_component_and_invariant_together_are_refused():
    ok, errors = validate_recipe([
        {"name": "S_MAX", "type": "field_max", "location": "whole_model",
         "component": "S11", "invariant": "MISES"}])
    assert not ok
    assert "both" in errors[0]


def test_unknown_invariant_is_refused():
    ok, errors = validate_recipe([
        {"name": "S_MAG", "type": "field_max",
         "location": "whole_model", "invariant": "MAGNITUDE"}])
    assert not ok
    assert "MAGNITUDE" in errors[0]


def test_valid_component_and_valid_invariant_still_pass():
    ok, errors = validate_recipe([
        {"name": "U_TIP", "type": "field_min",
         "location": "whole_model", "component": "U2"},
        {"name": "S_MISES", "type": "field_max",
         "location": "whole_model", "invariant": "MISES"}])
    assert ok, errors


# ---------------------------------------------------------------------------
# validate_spec: the chokepoint every entrance shares
# ---------------------------------------------------------------------------

def test_validate_spec_reports_the_extractors_refusal():
    spec = _spec_with_kpi({"name": "S_MISES_MAX", "type": "field_max",
                           "location": "whole_model", "component": "Mises"})
    valid, errors = validate_spec(spec)
    assert not valid
    assert any("invariant, not a component" in e for e in errors)
    assert any(e.startswith("outputs.kpis:") for e in errors)


def test_validate_spec_still_passes_a_clean_recipe():
    spec = _spec_with_kpi({"name": "U_TIP", "type": "field_min",
                           "location": "whole_model", "component": "U2"})
    valid, errors = validate_spec(spec)
    assert valid, errors


# ---------------------------------------------------------------------------
# llm_planner.parse: the refusal reaches the planner's caller at plan time
# ---------------------------------------------------------------------------

def test_planner_parse_refuses_bad_component_before_any_build():
    spec = _spec_with_kpi({"name": "S_MISES_MAX", "type": "field_max",
                           "location": "whole_model", "component": "Mises"})
    raw = yaml.dump(spec, allow_unicode=True, sort_keys=False)
    with pytest.raises(AbaqusAgentError) as exc:
        LLMPlanner(backend="template").parse(raw)
    assert "invariant, not a component" in str(exc.value)


def test_planner_parse_still_accepts_a_clean_spec():
    spec = _spec_with_kpi({"name": "U_TIP", "type": "field_min",
                           "location": "whole_model", "component": "U2"})
    raw = yaml.dump(spec, allow_unicode=True, sort_keys=False)
    parsed, _missing = LLMPlanner(backend="template").parse(raw)
    assert parsed["outputs"]["kpis"][0]["name"] == "U_TIP"


# ---------------------------------------------------------------------------
# orchestrator._stage_validate: the refusal lands before build, not after solve
# ---------------------------------------------------------------------------

def test_stage_validate_refuses_bad_component_pre_build():
    from agent.orchestrator import AbaqusOrchestrator
    spec = _spec_with_kpi({"name": "S_MISES_MAX", "type": "field_max",
                           "location": "whole_model", "component": "Mises"})
    orch = AbaqusOrchestrator(spec_dict=spec)
    with pytest.raises(AbaqusAgentError) as exc:
        orch._stage_validate()
    assert "invariant, not a component" in str(exc.value)


def test_stage_validate_passes_a_clean_recipe():
    from agent.orchestrator import AbaqusOrchestrator
    spec = _spec_with_kpi({"name": "U_TIP", "type": "field_min",
                           "location": "whole_model", "component": "U2"})
    orch = AbaqusOrchestrator(spec_dict=spec)
    orch._stage_validate()
    assert orch.result["stages"]["validate_spec"]["valid"] is True
