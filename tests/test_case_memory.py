"""Tests for deterministic local case memory search."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from case_memory import CaseMemoryQuery, render_memory_markdown, search_case_memory


def _write_case(
    root: Path,
    name: str,
    *,
    model_name: str,
    geometry_type: str,
    material_name: str = "Steel",
    status: str = "COMPLETED",
    kpis: dict | None = None,
    diagnosis_id: str = "",
    input_hash: str = "",
) -> Path:
    workdir = root / name
    workdir.mkdir(parents=True)
    spec = {
        "meta": {"model_name": model_name, "abaqus_release": "2024"},
        "geometry": {"type": geometry_type},
        "material": {"name": material_name, "E": 210000, "nu": 0.3},
        "analysis": {"solver": "standard", "step_type": "Static"},
    }
    (workdir / "spec.yaml").write_text(yaml.safe_dump(spec), encoding="utf-8")
    result = {
        "run_id": name,
        "status": status,
        "spec": spec,
        "kpis": kpis or {"U_tip": -0.002},
        "contracts": {"passed": True, "results": [{"name": "tip_down", "passed": True}]},
    }
    (workdir / "result.json").write_text(json.dumps(result), encoding="utf-8")
    capsule = {
        "schema_version": "0.2.0-dev",
        "run_id": name,
        "created_at": f"2026-06-02T10:00:0{len(name)}",
        "inputs": {
            "model_name": model_name,
            "spec": "spec.yaml",
            "spec_sha256": input_hash or f"{name}-hash",
        },
        "artifacts": {"Job.log": {"path": "Job.log", "sha256": "abc", "bytes": 10}},
        "provenance": {"status": status, "abaqus_release": "2024"},
        "contracts": result["contracts"],
    }
    if diagnosis_id:
        capsule["diagnosis"] = {
            "matched": True,
            "matches": [{"id": diagnosis_id, "category": "solver", "severity": "error"}],
        }
    (workdir / "capsule.json").write_text(json.dumps(capsule), encoding="utf-8")
    return workdir


def test_case_memory_search_filters_and_ranks_text_query(tmp_path):
    _write_case(
        tmp_path,
        "run_fail",
        model_name="Cantilever",
        geometry_type="custom_inp",
        status="FAILED",
        diagnosis_id="too_many_attempts",
    )
    _write_case(tmp_path, "run_plate", model_name="PlateHole", geometry_type="plate_with_hole")

    result = search_case_memory(CaseMemoryQuery(
        roots=(tmp_path,),
        query="too_many_attempts",
        diagnosis_id="too_many_attempts",
        limit=5,
    ))

    assert result["total_indexed"] == 2
    assert result["total_matches"] == 1
    match = result["matches"][0]
    assert match["run_id"] == "run_fail"
    assert match["diagnosis_ids"] == ["too_many_attempts"]
    assert "text:too_many_attempts" in match["reasons"]


def test_case_memory_similarity_uses_inputs_and_kpis(tmp_path):
    target = _write_case(
        tmp_path,
        "target",
        model_name="Cantilever",
        geometry_type="custom_inp",
        kpis={"U_tip": -0.002, "MISES_MAX": 100.0},
        input_hash="shared-hash",
    )
    _write_case(
        tmp_path,
        "similar",
        model_name="Cantilever",
        geometry_type="custom_inp",
        kpis={"U_tip": -0.0021, "MISES_MAX": 101.0},
        input_hash="shared-hash",
    )
    _write_case(tmp_path, "different", model_name="Modal", geometry_type="modal")

    result = search_case_memory(CaseMemoryQuery(roots=(tmp_path,), similar_to=target, limit=3))

    assert result["matches"][0]["run_id"] == "similar"
    assert "same input hash" in result["matches"][0]["reasons"]
    assert "shared KPIs:MISES_MAX,U_tip" in result["matches"][0]["reasons"]
    assert "target" not in [match["run_id"] for match in result["matches"]]


def test_case_memory_text_query_filters_unrelated_completed_cases(tmp_path):
    _write_case(tmp_path, "explicit", model_name="ExplicitImpact", geometry_type="cantilever_block")
    _write_case(tmp_path, "modal", model_name="ModalBeam", geometry_type="cantilever_block")

    result = search_case_memory(CaseMemoryQuery(roots=(tmp_path,), query="ExplicitImpact"))

    assert result["total_matches"] == 1
    assert result["matches"][0]["run_id"] == "explicit"


def test_case_memory_query_matches_path_and_compact_case_name(tmp_path):
    _write_case(tmp_path, "plate_hole", model_name="StressCase", geometry_type="custom_inp")
    _write_case(tmp_path, "modal_case", model_name="ModalCase", geometry_type="modal")

    result = search_case_memory(CaseMemoryQuery(roots=(tmp_path,), query="PlateHole"))

    assert result["total_matches"] == 1
    assert result["matches"][0]["run_id"] == "plate_hole"
    assert "text:platehole" in result["matches"][0]["reasons"]


def test_case_memory_omits_artifacts_by_default_and_can_include_them(tmp_path):
    _write_case(tmp_path, "artifact_case", model_name="ArtifactModel", geometry_type="custom_inp")

    compact = search_case_memory(CaseMemoryQuery(roots=(tmp_path,), query="ArtifactModel"))
    verbose = search_case_memory(CaseMemoryQuery(
        roots=(tmp_path,),
        query="ArtifactModel",
        include_artifacts=True,
    ))

    assert "artifacts" not in compact["matches"][0]
    assert compact["matches"][0]["artifact_count"] == 1
    assert compact["matches"][0]["artifact_names"] == ["Job.log"]
    assert "artifacts" in verbose["matches"][0]


def test_case_memory_sort_and_min_score_controls(tmp_path):
    _write_case(tmp_path, "b_case", model_name="BeamB", geometry_type="custom_inp")
    _write_case(tmp_path, "a_case", model_name="BeamA", geometry_type="custom_inp")
    _write_case(tmp_path, "low", model_name="Low", geometry_type="custom_inp")

    sorted_by_run = search_case_memory(CaseMemoryQuery(
        roots=(tmp_path,),
        sort_by="run_id",
        sort_order="asc",
        limit=5,
    ))
    filtered = search_case_memory(CaseMemoryQuery(
        roots=(tmp_path,),
        query="BeamA",
        min_score=1.2,
    ))

    assert [match["run_id"] for match in sorted_by_run["matches"]] == ["a_case", "b_case", "low"]
    assert filtered["total_matches"] == 1
    assert filtered["matches"][0]["run_id"] == "a_case"
    assert filtered["query"]["sort_by"] == "score"
    assert filtered["query"]["min_score"] == 1.2


def test_case_memory_loads_spec_from_capsule_when_result_lacks_spec(tmp_path):
    workdir = _write_case(tmp_path, "capsule_only", model_name="LensModel", geometry_type="beam")
    result = json.loads((workdir / "result.json").read_text(encoding="utf-8"))
    result.pop("spec")
    (workdir / "result.json").write_text(json.dumps(result), encoding="utf-8")

    data = search_case_memory(CaseMemoryQuery(roots=(workdir,), query="beam"))

    assert data["matches"][0]["geometry_type"] == "beam"
    assert data["matches"][0]["model_name"] == "LensModel"


def test_case_memory_markdown_contains_matches(tmp_path):
    _write_case(tmp_path, "report_case", model_name="ReportModel", geometry_type="custom_inp")

    result = search_case_memory(CaseMemoryQuery(roots=(tmp_path,), query="ReportModel"))
    markdown = render_memory_markdown(result)

    assert "Case Memory Search" in markdown
    assert "report_case" in markdown
    assert "ReportModel" in markdown
