from pathlib import Path

import pytest

from contracts.evaluator import evaluate_contracts
from contracts.io import load_contracts
from evidence.offline import collect_evidence_from_files

EXAMPLE_KPIS = {
    "cantilever": {"U_tip": -0.0019039579201489687, "MISES_MAX": 0.6528551578521729},
    "plate_hole": {"MISES_HOLE_EDGE": 300.0, "U_X_MAX": 0.048},
    "modal": {"freq_1": 0.0, "freq_2": 1000.0},
    "explicit_impact": {"RF_Z_MAX": 1000.0, "U_Z_MIN": -2.0},
}


def test_example_contract_files_load_and_pass_reference_kpis():
    root = Path(__file__).resolve().parents[1] / "examples" / "contracts"

    for case_name, kpis in EXAMPLE_KPIS.items():
        contracts = load_contracts(root / f"{case_name}.yaml")
        result = evaluate_contracts(kpis, contracts)

        assert contracts
        assert result["status"] == "PASS", case_name


@pytest.mark.parametrize("case_name", sorted(EXAMPLE_KPIS))
def test_example_kpi_files_run_offline_evidence_slice(case_name, tmp_path):
    root = Path(__file__).resolve().parents[1]

    evidence = collect_evidence_from_files(
        baseline_kpis_path=root / "examples" / "kpis" / f"{case_name}_baseline.json",
        candidate_kpis_path=root / "examples" / "kpis" / f"{case_name}_candidate.json",
        contracts_path=root / "examples" / "contracts" / f"{case_name}.yaml",
        out_dir=tmp_path / case_name,
        run_id=f"{case_name}-example-gallery",
        extra_inputs=[root / "cases" / case_name / "spec.yaml"],
    )

    assert evidence["overall_status"] == "PASS"
    assert evidence["contracts"]["status"] == "PASS"
    assert evidence["diff"]["status"] == "PASS"
    assert evidence["capsule"]["input_count"] >= 4
