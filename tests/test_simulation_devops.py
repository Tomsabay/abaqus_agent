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
from doctor.diagnosis import diagnose_logs
from simdiff.kpi_diff import diff_kpis, render_markdown


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
    kpis = {"U_tip": -0.002, "SCF": 3.1, "freq_1": 210, "freq_2": 416}
    contracts = [
        {"name": "deflects_down", "type": "direction", "kpi": "U_tip", "direction": "negative"},
        {"name": "scf_range", "type": "range", "kpi": "SCF", "min": 2.5, "max": 3.5},
        {"name": "tip_baseline", "type": "relative_error", "kpi": "U_tip", "expected": -0.0021, "rtol": 0.1},
        {"name": "freq_order", "type": "order", "kpis": ["freq_1", "freq_2"]},
    ]

    result = evaluate_contracts(contracts, kpis)

    assert result["passed"] is True
    assert all(item["passed"] for item in result["results"])


def test_simdiff_flags_large_kpi_change_and_renders_markdown():
    result = diff_kpis(
        {"U_tip": -0.002, "MISES": 100.0},
        {"U_tip": -0.00202, "MISES": 125.0},
        tolerances={"MISES": 0.1},
    )

    mises = next(c for c in result["changes"] if c["name"] == "MISES")
    assert result["passed"] is False
    assert mises["status"] == "WARNING"
    assert "MISES" in render_markdown(result)


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


def test_capsule_json_is_machine_readable(tmp_path):
    inp = tmp_path / "plate.inp"
    inp.write_text("*Heading\nplate\n", encoding="utf-8")
    capsule = init_from_inp(inp, tmp_path / "capsule")

    raw = json.loads((tmp_path / "capsule" / "capsule.json").read_text(encoding="utf-8"))

    assert raw["run_id"] == capsule["run_id"]
    assert raw["schema_version"].startswith("0.2")
