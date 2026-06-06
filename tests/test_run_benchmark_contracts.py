import json

import agent.orchestrator as orchestrator_module
import run_benchmark


class FakeOrchestrator:
    def __init__(self, **kwargs):
        self.kwargs = kwargs

    def run(self):
        return {
            "status": "COMPLETED",
            "stages": {"extract_kpis": {"ok": True}},
            "kpis": {"U_tip": -2.04},
            "regression": {"passed": True, "comparisons": {}},
        }


def test_run_case_adds_contract_results_from_expected_json(tmp_path, monkeypatch):
    spec = tmp_path / "spec.yaml"
    expected = tmp_path / "expected.json"
    spec.write_text("fixture: true\n", encoding="utf-8")
    expected.write_text(
        json.dumps({"kpis": {"U_tip": {"value": -2.0, "rtol": 0.05, "atol": 0.0}}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(run_benchmark, "validate_spec", lambda _path: (True, []))
    monkeypatch.setattr(orchestrator_module, "AbaqusOrchestrator", FakeOrchestrator)

    result = run_benchmark.run_case(
        {
            "name": "cantilever",
            "spec": spec,
            "expected": expected,
            "runner_cfg": None,
        }
    )

    assert result["status"] == "COMPLETED"
    assert result["contracts"]["status"] == "PASS"
    assert result["contracts"]["checks"][0]["name"] == "U_tip reference tolerance"


def test_run_case_records_contract_error_without_failing_completed_run(tmp_path, monkeypatch):
    spec = tmp_path / "spec.yaml"
    expected = tmp_path / "expected.json"
    spec.write_text("fixture: true\n", encoding="utf-8")
    expected.write_text(json.dumps({"contracts": {"bad": "shape"}}), encoding="utf-8")
    monkeypatch.setattr(run_benchmark, "validate_spec", lambda _path: (True, []))
    monkeypatch.setattr(orchestrator_module, "AbaqusOrchestrator", FakeOrchestrator)

    result = run_benchmark.run_case(
        {
            "name": "cantilever",
            "spec": spec,
            "expected": expected,
            "runner_cfg": None,
        }
    )

    assert result["status"] == "COMPLETED"
    assert result["contracts"]["status"] == "ERROR"
    assert result["contracts"]["passed"] is False
    assert "contracts must be a list" in result["contracts"]["error"]
