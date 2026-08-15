"""The CalculiX capability matrix: every refusal is explicit and explained.

The point of these tests is not that the numbers are right — it is that
nothing can be silently approximated. Each spec enum value must resolve to a
verdict, and every refusal must come with a plain-language reason naming the
spec field, because "拒绝" is a product feature here, not an error path.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.backends import calculix_capability

REPO_ROOT = Path(__file__).parent.parent
SCHEMA = json.loads((REPO_ROOT / "schema" / "spec_schema.json").read_text(encoding="utf-8"))


def _base_spec() -> dict:
    return {
        "meta": {"model_name": "M"},
        "geometry": {"type": "cantilever_block", "L": 100.0, "W": 10.0, "H": 10.0,
                     "seed_size": 5.0},
        "material": {"name": "Steel", "E": 210000.0, "nu": 0.3},
        "analysis": {"solver": "standard", "step_type": "Static"},
        "bc_load": {"load_type": "concentrated_force", "value": -1.0, "direction": 2},
        "outputs": {"kpis": [{"name": "U_tip", "type": "nodal_displacement",
                              "location": "tip_center", "component": "U2"}]},
    }


def test_the_reference_cantilever_spec_is_supported():
    blockers, caveats = calculix_capability(_base_spec())
    assert blockers == []
    assert caveats == []


@pytest.mark.parametrize("geo_type", sorted(
    set(SCHEMA["properties"]["geometry"]["properties"]["type"]["enum"])
    - {"cantilever_block", "custom_inp"}
))
def test_every_unsupported_geometry_is_refused_with_a_reason(geo_type):
    spec = _base_spec()
    spec["geometry"]["type"] = geo_type
    blockers, _ = calculix_capability(spec)
    reasons = [b.reason for b in blockers if b.feature == "geometry.type"]
    assert reasons, f"{geo_type} must be refused, not silently approximated"
    assert len(reasons[0]) > 20, "a refusal must explain itself, not just say no"


@pytest.mark.parametrize("step_type", sorted(
    set(SCHEMA["properties"]["analysis"]["properties"]["step_type"]["enum"]) - {"Static"}
))
def test_every_unverified_step_type_is_refused(step_type):
    spec = _base_spec()
    spec["analysis"]["step_type"] = step_type
    blockers, _ = calculix_capability(spec)
    assert any(b.feature == "analysis.step_type" for b in blockers)


@pytest.mark.parametrize("load_type", sorted(
    set(SCHEMA["properties"]["bc_load"]["properties"]["load_type"]["enum"])
    - {"concentrated_force"}
))
def test_every_unverified_load_type_is_refused(load_type):
    spec = _base_spec()
    spec["bc_load"]["load_type"] = load_type
    blockers, _ = calculix_capability(spec)
    assert any(b.feature == "bc_load.load_type" for b in blockers)


def test_blast_conwep_refusal_names_the_silent_failure_mode():
    """The one combination ccx runs to exit 0 with every displacement zero."""
    spec = _base_spec()
    spec["bc_load"]["load_type"] = "blast_conwep"
    blockers, _ = calculix_capability(spec)
    reason = next(b.reason for b in blockers if b.feature == "bc_load.load_type")
    assert "CONWEP" in reason
    assert "静默" in reason and "0" in reason


def test_nlgeom_is_refused_not_silently_linearised():
    spec = _base_spec()
    spec["analysis"]["nlgeom"] = True
    blockers, _ = calculix_capability(spec)
    assert any(b.feature == "analysis.nlgeom" for b in blockers)


def test_adaptive_mesh_and_mpi_are_refused():
    spec = _base_spec()
    spec["analysis"]["adaptive_mesh"] = {"enabled": True}
    spec["analysis"]["mp_mode"] = "mpi"
    blockers, _ = calculix_capability(spec)
    features = {b.feature for b in blockers}
    assert "analysis.adaptive_mesh.enabled" in features
    assert "analysis.mp_mode" in features


def test_parametric_sweep_is_refused():
    spec = _base_spec()
    spec["parametric"] = {"parameters": [{"name": "L", "values": [1, 2]}]}
    blockers, _ = calculix_capability(spec)
    assert any(b.feature == "parametric.parameters" for b in blockers)


@pytest.mark.parametrize("kpi_type", ["eigenfrequency", "history_output_max"])
def test_unsupported_kpi_types_are_refused(kpi_type):
    spec = _base_spec()
    spec["outputs"]["kpis"] = [{"name": "K", "type": kpi_type}]
    blockers, _ = calculix_capability(spec)
    assert any(b.feature.startswith("outputs.kpis[K]") for b in blockers)


def test_stress_kpi_runs_but_carries_a_caveat():
    """Mises is not refused — it is emitted with its definition attached."""
    spec = _base_spec()
    spec["outputs"]["kpis"].append({"name": "MISES_MAX", "type": "field_max",
                                    "location": "whole_model"})
    blockers, caveats = calculix_capability(spec)
    assert blockers == []
    assert any(c.feature == "outputs.kpis[MISES_MAX].type" for c in caveats)
    assert all(c.kind == "caveat" for c in caveats)


def test_plastic_material_is_refused_until_verified():
    spec = _base_spec()
    spec["material"]["yield"] = 250.0
    blockers, _ = calculix_capability(spec)
    assert any(b.feature == "material.yield" for b in blockers)


def test_repo_case_specs_all_get_an_explicit_verdict():
    """No case may fall through the matrix without a decision either way."""
    cases = sorted((REPO_ROOT / "cases").glob("*/spec.yaml"))
    assert cases, "no case specs found"
    supported, refused = [], []
    for path in cases:
        spec = yaml.safe_load(path.read_text(encoding="utf-8"))
        blockers, _ = calculix_capability(spec)
        (refused if blockers else supported).append(path.parent.name)
        for blocker in blockers:
            assert blocker.feature and blocker.reason
    # cantilever is the verified reference; everything else needs a reason.
    assert "cantilever" in supported
    assert refused, "the matrix that refuses nothing is not a matrix"


# ── the v2 assembly dialect ────────────────────────────────────────────────

V2_CASES = ("two_plate_tie", "two_plate_contact", "block_friction_slide")


@pytest.mark.parametrize("case", V2_CASES)
def test_the_assembly_dialect_is_refused_by_name(case):
    """It was already refused, but for the wrong reason.

    A v2 spec has no `geometry` block, so the geometry check reported
    "geometry.type = None" — which reads as a malformed spec and sends the
    author to fix a field that was never there. The refusal has to name the
    dialect.
    """
    spec = yaml.safe_load(
        (REPO_ROOT / "cases" / case / "spec.yaml").read_text(encoding="utf-8"))
    blockers, _ = calculix_capability(spec)
    features = {b.feature for b in blockers}
    assert "parts" in features, features
    assert "geometry.type" not in features, (
        "the misleading refusal is still there: %s" % features)


def test_the_assembly_refusal_says_what_is_missing():
    spec = yaml.safe_load(
        (REPO_ROOT / "cases" / "two_plate_tie" / "spec.yaml").read_text(encoding="utf-8"))
    blockers, _ = calculix_capability(spec)
    reason = next(b.reason for b in blockers if b.feature == "parts")
    assert "网格" in reason and "CalculiX" in reason
    assert len(reason) > 40


def test_frd_sourced_kpi_at_a_named_location_is_blocked_before_the_solve():
    """Refuse-before-run, not refuse-at-extraction.

    field_max / derived_stress_concentration read the .frd, whose field blocks
    are whole-model only. Letting the run start would burn a real solve and
    fail at the last stage; the capability matrix must catch it up front.
    (post/extract_kpis_ccx.py keeps the same guard as belt-and-braces.)
    """
    spec = _base_spec()
    spec["outputs"]["kpis"].append(
        {"name": "MISES_EDGE", "type": "field_max", "location": "hole_edge_set"})
    blockers, _ = calculix_capability(spec)
    assert any("MISES_EDGE" in b.feature and "location" in b.feature
               for b in blockers), [b.feature for b in blockers]


def test_frd_sourced_kpi_at_whole_model_stays_supported():
    spec = _base_spec()
    spec["outputs"]["kpis"].append(
        {"name": "MISES_MAX", "type": "field_max", "location": "whole_model"})
    blockers, caveats = calculix_capability(spec)
    assert blockers == []
    assert any("MISES_MAX" in c.feature for c in caveats)  # the averaging caveat stays


# ── the public capability table must match the code ─────────────────────────

def test_roadmap_kpi_row_matches_the_matrix():
    """docs/ROADMAP.md is a public promise. It listed `field min/max` and
    `derived stress concentration` as plainly Supported, with no mention that
    the last two are refused the moment a KPI names a location — because
    CalculiX's .frd field blocks are whole-model only.

    Getting this wrong the other way is just as bad: field_min, nodal
    displacement and reaction_force_max read from ccx's .dat via *NODE PRINT
    and DO honour a named set, so a blanket 'whole model only' would
    undersell them.
    """
    from pathlib import Path

    from core.backends import calculix_capability

    def blocked(kind: str, location: str) -> bool:
        spec = {
            "meta": {"model_name": "m", "abaqus_release": "2021"},
            "geometry": {"type": "cantilever_block", "L": 100.0, "W": 10.0, "H": 10.0},
            "material": {"name": "S", "E": 210000.0, "nu": 0.3},
            "analysis": {"step_type": "Static"},
            "bc_load": {"fixed_face": "z=0", "load_type": "concentrated_force",
                        "value": -1.0, "direction": 2},
            "outputs": {"kpis": [{"name": "K", "type": kind, "location": location}]},
        }
        blockers, _ = calculix_capability(spec)
        return bool([x for x in blockers if "kpis" in x.feature])

    whole_model_only = {"field_max", "derived_stress_concentration"}
    set_addressable = {"field_min", "nodal_displacement", "reaction_force_max"}

    for kind in whole_model_only:
        assert not blocked(kind, "whole_model"), kind
        assert blocked(kind, "tip_set"), (
            "%s must be refused at a named location (.frd is whole-model)" % kind)
    for kind in set_addressable:
        assert not blocked(kind, "whole_model"), kind
        assert not blocked(kind, "tip_set"), (
            "%s reads ccx .dat via *NODE PRINT and does honour a set" % kind)

    roadmap = (Path(__file__).resolve().parent.parent
               / "docs" / "ROADMAP.md").read_text(encoding="utf-8")
    kpi_row = [ln for ln in roadmap.splitlines()
               if ln.startswith("| KPIs")]
    assert kpi_row, "ROADMAP lost its KPI row"
    row = kpi_row[0].lower()
    assert "whole model only" in row, (
        "the row must say which KPIs cannot take a named location")
    for kind in set_addressable:
        token = kind.replace("_", " ").replace("reaction force max", "reaction force")
        assert token.split()[0] in row, "%s dropped from the public table" % kind
