"""Tests for the v0.2 Simulation QA / DevOps kernel."""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from unittest.mock import patch

import yaml

sys.path.insert(0, str(Path(__file__).parent.parent))

from capsule.schema import validate_capsule
from capsule.store import hash_file, init_from_inp, load_capsule
from contracts.evaluator import evaluate_contracts
from doctor.diagnosis import diagnose_logs, load_patterns
from simdiff.kpi_diff import diff_kpis, render_markdown
from simdiff.run_diff import diff_runs, render_run_markdown


def test_custom_inp_build_copies_input_without_abaqus(tmp_path):
    source_inp = tmp_path / "source.inp"
    source_inp.write_text("*Heading\ncustom input\n", encoding="utf-8")
    spec = {
        "meta": {"abaqus_release": "2024", "model_name": "CustomModel"},
        "geometry": {"type": "custom_inp", "inp_path": "source.inp"},
        "material": {"name": "Steel", "E": 210000, "nu": 0.3},
        "analysis": {"solver": "standard", "step_type": "Static"},
        "bc_load": {},
        "outputs": {"kpis": [{"name": "U_tip", "type": "nodal_displacement"}]},
    }
    spec_path = tmp_path / "spec.yaml"
    spec_path.write_text(yaml.safe_dump(spec), encoding="utf-8")

    build_model_module = importlib.import_module("runner.build_model")
    with patch.object(build_model_module, "_run_cae_nougui") as run_cae:
        result = build_model_module.build_model(spec_path, tmp_path / "run")

    run_cae.assert_not_called()
    assert result["custom_inp"] is True
    assert result["inp_path"].read_text(encoding="utf-8") == "*Heading\ncustom input\n"
    assert result["source_inp_path"] == source_inp.resolve()


def test_capsule_init_from_inp_records_hash_and_manifest(tmp_path):
    inp = tmp_path / "beam.inp"
    inp.write_text("*Heading\nbeam\n", encoding="utf-8")

    capsule = init_from_inp(inp, tmp_path / "capsule", metadata={"abaqus_release": "2024"})
    valid, errors = validate_capsule(capsule)

    assert valid, errors
    assert capsule["inputs"]["model_name"] == "beam"
    assert capsule["inputs"]["inp_sha256"] == hash_file(inp)
    assert (tmp_path / "capsule" / "capsule.json").exists()
    assert load_capsule(tmp_path / "capsule")["run_id"] == capsule["run_id"]


def test_physics_contracts_evaluate_range_direction_error_and_order():
    kpis = {"U_tip": {"value": -0.002, "unit": "mm"}, "SCF": 3.1, "freq_1": 210, "freq_2": 416}
    contracts = [
        {"name": "deflects_down", "check": "operator", "kpi": "U_tip", "operator": "<", "value": 0.0},
        {"name": "scf_range", "type": "range", "kpi": "SCF", "min": 2.5, "max": 3.5},
        {"name": "tip_baseline", "type": "relative_error", "kpi": "U_tip", "expected": -0.0021, "rtol": 0.1},
        {"name": "freq_order", "type": "order", "kpis": ["freq_1", "freq_2"]},
    ]

    result = evaluate_contracts(contracts, kpis)

    assert result["passed"] is True
    assert all(item["passed"] for item in result["results"])
    assert result["results"][0]["status"] == "PASS"
    assert result["results"][0]["actual"] == -0.002


def test_physics_contracts_warning_failure_is_non_blocking():
    result = evaluate_contracts(
        [{"name": "wide_mises", "check": "range", "kpi": "MISES_MAX", "max": 0.5, "severity": "warning"}],
        {"MISES_MAX": 0.65},
    )

    assert result["passed"] is True
    assert result["results"][0]["passed"] is False
    assert result["results"][0]["status"] == "WARNING"


def test_simdiff_flags_large_kpi_change_and_renders_markdown():
    result = diff_kpis(
        {"U_tip": -0.002, "MISES": 100.0},
        {"U_tip": -0.00202, "MISES": 125.0},
        tolerances={"MISES": 0.1},
    )

    mises = next(c for c in result["changes"] if c["name"] == "MISES")
    assert result["passed"] is False
    assert mises["status"] == "WARNING"
    assert mises["rtol"] == 0.1
    assert "MISES" in render_markdown(result)
    assert "rtol" in render_markdown(result)


def test_simdiff_uses_per_kpi_tolerances():
    result = diff_runs(
        {"run_id": "base", "kpis": {"MISES": 100.0, "U_tip": -0.002}},
        {"run_id": "candidate", "kpis": {"MISES": 125.0, "U_tip": -0.0022}},
        default_rtol=0.05,
        tolerances={"MISES": 0.3},
    )

    mises = next(c for c in result["sections"]["kpis"]["changes"] if c["name"] == "MISES")
    u_tip = next(c for c in result["sections"]["kpis"]["changes"] if c["name"] == "U_tip")
    assert mises["status"] == "PASS"
    assert mises["rtol"] == 0.3
    assert u_tip["status"] == "WARNING"
    assert result["summary"]["sections"]["kpis"]["PASS"] == 1
    assert result["summary"]["sections"]["kpis"]["WARNING"] == 1


def test_simdiff_compares_run_dirs_kpis_contracts_and_specs(tmp_path):
    base = tmp_path / "base"
    cand = tmp_path / "candidate"
    base.mkdir()
    cand.mkdir()
    (base / "result.json").write_text(
        json.dumps({
            "run_id": "base",
            "status": "COMPLETED",
            "kpis": {"U_tip": -0.002, "MISES_MAX": 0.6},
            "contracts": {"results": [{"name": "tip_down", "status": "PASS"}]},
        }),
        encoding="utf-8",
    )
    (cand / "result.json").write_text(
        json.dumps({
            "run_id": "candidate",
            "status": "COMPLETED",
            "kpis": {"U_tip": -0.0022, "MISES_MAX": 0.65},
            "contracts": {"results": [{"name": "tip_down", "status": "PASS"}]},
        }),
        encoding="utf-8",
    )
    (base / "spec.yaml").write_text(yaml.safe_dump({"bc_load": {"value": -1.0}}), encoding="utf-8")
    (cand / "spec.yaml").write_text(yaml.safe_dump({"bc_load": {"value": -1.1}}), encoding="utf-8")

    result = diff_runs(base, cand, default_rtol=0.05)

    assert result["passed"] is False
    assert result["baseline"]["run_id"] == "base"
    assert result["summary"]["total_changes"] >= 4
    assert result["summary"]["warning_changes"] >= 2
    assert result["summary"]["sections"]["kpis"]["WARNING"] == 2
    assert result["summary"]["sections"]["spec"]["WARNING"] == 1
    assert any(c["name"] == "U_tip" and c["status"] == "WARNING" for c in result["sections"]["kpis"]["changes"])
    assert any(c["path"] == "bc_load.value" for c in result["sections"]["spec"]["changes"])
    markdown = render_run_markdown(result)
    assert "Simulation Diff Report" in markdown
    assert "Change Summary" in markdown
    assert "| kpis |" in markdown


def test_simdiff_loads_specs_from_result_paths(tmp_path):
    spec_base = tmp_path / "spec_base.yaml"
    spec_candidate = tmp_path / "spec_candidate.yaml"
    spec_base.write_text(yaml.safe_dump({"bc_load": {"value": -1.0}}), encoding="utf-8")
    spec_candidate.write_text(yaml.safe_dump({"bc_load": {"value": -1.1}}), encoding="utf-8")

    base = tmp_path / "base_run"
    cand = tmp_path / "candidate_run"
    base.mkdir()
    cand.mkdir()
    (base / "result.json").write_text(
        json.dumps({"run_id": "base", "spec_path": str(spec_base), "kpis": {"U_tip": -0.002}}),
        encoding="utf-8",
    )
    (cand / "result.json").write_text(
        json.dumps({"run_id": "candidate", "spec_path": str(spec_candidate), "kpis": {"U_tip": -0.0022}}),
        encoding="utf-8",
    )

    result = diff_runs(base, cand)

    assert any(
        change["path"] == "bc_load.value" and change["before"] == -1.0 and change["after"] == -1.1
        for change in result["sections"]["spec"]["changes"]
    )


def test_simdiff_loads_relative_specs_from_capsule_inputs(tmp_path):
    base = tmp_path / "base_capsule"
    cand = tmp_path / "candidate_capsule"
    base.mkdir()
    cand.mkdir()
    (base / "spec.yaml").write_text(yaml.safe_dump({"bc_load": {"value": -1.0}}), encoding="utf-8")
    (cand / "spec.yaml").write_text(yaml.safe_dump({"bc_load": {"value": -1.1}}), encoding="utf-8")
    (base / "capsule.json").write_text(
        json.dumps({"run_id": "base", "inputs": {"spec": "spec.yaml"}, "artifacts": {}}),
        encoding="utf-8",
    )
    (cand / "capsule.json").write_text(
        json.dumps({"run_id": "candidate", "inputs": {"spec": "spec.yaml"}, "artifacts": {}}),
        encoding="utf-8",
    )

    result = diff_runs(base, cand)

    assert any(change["path"] == "bc_load.value" for change in result["sections"]["spec"]["changes"])


def test_solver_doctor_matches_common_patterns(tmp_path):
    msg = tmp_path / "job.msg"
    msg.write_text(
        "Abaqus Error: Too many attempts made for this increment\n"
        "License checkout failed for abaqus\n",
        encoding="utf-8",
    )

    result = diagnose_logs(paths=[msg])
    ids = {match["id"] for match in result["matches"]}

    assert result["matched"] is True
    assert "too_many_attempts" in ids
    assert "license_unavailable" in ids


def test_solver_doctor_pattern_library_covers_mvp_threshold():
    patterns = load_patterns()

    assert len(patterns) >= 30
    assert len({pattern["id"] for pattern in patterns}) == len(patterns)
    assert {"id", "category", "regex", "suggestion"} <= set(patterns[0])


def test_solver_doctor_matches_expanded_abaqus_patterns():
    result = diagnose_logs(
        text=(
            "THE MAXIMUM NUMBER OF INCREMENTS HAS BEEN EXCEEDED\n"
            "Node set FIXED_NODES has not been defined\n"
            "Abaqus Error: The lock file Job-1.lck exists\n"
            "Traceback (most recent call last):\n"
            "NameError: name 'mdbx' is not defined\n"
        )
    )
    ids = {match["id"] for match in result["matches"]}

    assert {
        "maximum_increments_exceeded",
        "missing_node_set",
        "lock_file_exists",
        "python_script_error",
    } <= ids


def test_capsule_json_is_machine_readable(tmp_path):
    inp = tmp_path / "plate.inp"
    inp.write_text("*Heading\nplate\n", encoding="utf-8")
    capsule = init_from_inp(inp, tmp_path / "capsule")

    raw = json.loads((tmp_path / "capsule" / "capsule.json").read_text(encoding="utf-8"))

    assert raw["run_id"] == capsule["run_id"]
    assert raw["schema_version"].startswith("0.2")
