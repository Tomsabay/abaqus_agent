import json

import pytest
import yaml

from contracts.evaluator import evaluate_contracts
from contracts.io import contracts_from_expected, load_contracts


def test_contracts_from_expected_converts_kpi_references():
    contracts = contracts_from_expected(
        {
            "kpis": {
                "U_tip": {
                    "value": -2.0,
                    "rtol": 0.1,
                    "atol": 0.01,
                    "unit": "mm",
                    "note": "fixture",
                }
            }
        }
    )

    assert contracts == [
        {
            "name": "U_tip reference tolerance",
            "type": "relative_error",
            "kpi": "U_tip",
            "reference": -2.0,
            "rtol": 0.1,
            "atol": 0.01,
            "unit": "mm",
            "note": "fixture",
        }
    ]
    assert evaluate_contracts({"U_tip": -2.05}, contracts)["status"] == "PASS"


def test_load_contracts_accepts_yaml_contract_object(tmp_path):
    path = tmp_path / "contracts.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "contracts": [
                    {"name": "tip down", "type": "direction", "kpi": "U_tip", "op": "negative"},
                    {"name": "SCF range", "type": "range", "kpi": "SCF", "min": 2.5, "max": 3.5},
                ]
            }
        ),
        encoding="utf-8",
    )

    contracts = load_contracts(path)

    assert len(contracts) == 2
    assert evaluate_contracts({"U_tip": -1.0, "SCF": 3.0}, contracts)["status"] == "PASS"


def test_load_contracts_accepts_json_list(tmp_path):
    path = tmp_path / "contracts.json"
    path.write_text(
        json.dumps([{"name": "mode order", "type": "order", "kpis": ["f1", "f2"]}]),
        encoding="utf-8",
    )

    assert load_contracts(path) == [{"name": "mode order", "type": "order", "kpis": ["f1", "f2"]}]


def test_load_contracts_accepts_legacy_expected_json(tmp_path):
    path = tmp_path / "expected.json"
    path.write_text(
        json.dumps({"kpis": {"max_mises": {"value": 100.0, "rtol": 0.2}}}),
        encoding="utf-8",
    )

    contracts = load_contracts(path)

    assert contracts[0]["type"] == "relative_error"
    assert evaluate_contracts({"max_mises": 110.0}, contracts)["status"] == "PASS"


def test_load_contracts_rejects_invalid_shapes(tmp_path):
    invalid_contracts = tmp_path / "invalid.yaml"
    invalid_contracts.write_text(yaml.safe_dump({"contracts": {"bad": "shape"}}), encoding="utf-8")
    missing_type = tmp_path / "missing_type.json"
    missing_type.write_text(json.dumps([{"name": "bad"}]), encoding="utf-8")

    with pytest.raises(ValueError, match="contracts must be a list"):
        load_contracts(invalid_contracts)
    with pytest.raises(ValueError, match="type"):
        load_contracts(missing_type)
