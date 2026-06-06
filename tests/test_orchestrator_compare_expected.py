import json

from agent.orchestrator import AbaqusOrchestrator


def _orchestrator_with_expected(tmp_path, expected):
    expected_path = tmp_path / "expected.json"
    expected_path.write_text(json.dumps(expected), encoding="utf-8")
    progress = []
    orchestrator = AbaqusOrchestrator(
        spec_dict={
            "meta": {"model_name": "compare_fixture"},
            "analysis": {"type": "static"},
            "outputs": {"kpis": []},
        },
        workdir=tmp_path,
        expected_path=expected_path,
        on_progress=lambda stage, data: progress.append((stage, data)),
    )
    return orchestrator, progress


def test_stage_compare_passes_values_within_relative_tolerance(tmp_path):
    orchestrator, progress = _orchestrator_with_expected(
        tmp_path,
        {"kpis": {"U_tip": {"value": -2.0, "rtol": 0.05, "atol": 0.0}}},
    )

    orchestrator._stage_compare({"U_tip": -2.04})

    comparison = orchestrator.result["regression"]["comparisons"]["U_tip"]
    assert orchestrator.result["regression"]["passed"] is True
    assert comparison == {
        "status": "PASS",
        "expected": -2.0,
        "actual": -2.04,
        "rel_err": 0.02,
        "abs_err": 0.04,
        "rtol": 0.05,
        "atol": 0.0,
    }
    assert progress[-1] == (
        "compare_kpis",
        {"passed": True, "details": {"U_tip": comparison}},
    )


def test_stage_compare_fails_values_outside_tolerance(tmp_path):
    orchestrator, progress = _orchestrator_with_expected(
        tmp_path,
        {"kpis": {"max_mises": {"value": 100.0, "rtol": 0.05, "atol": 1.0}}},
    )

    orchestrator._stage_compare({"max_mises": 107.0})

    comparison = orchestrator.result["regression"]["comparisons"]["max_mises"]
    assert orchestrator.result["regression"]["passed"] is False
    assert comparison["status"] == "FAIL"
    assert comparison["expected"] == 100.0
    assert comparison["actual"] == 107.0
    assert comparison["rel_err"] == 0.07
    assert comparison["abs_err"] == 7.0
    assert progress[-1][0] == "compare_kpis"
    assert progress[-1][1]["passed"] is False


def test_stage_compare_marks_missing_and_zero_expected_info(tmp_path):
    orchestrator, progress = _orchestrator_with_expected(
        tmp_path,
        {
            "kpis": {
                "missing_kpi": {"value": 1.0},
                "zero_reference": {"value": 0.0},
            }
        },
    )

    orchestrator._stage_compare({"zero_reference": 0.25})

    comparisons = orchestrator.result["regression"]["comparisons"]
    assert orchestrator.result["regression"]["passed"] is False
    assert comparisons["missing_kpi"] == {
        "status": "MISSING",
        "expected": 1.0,
        "actual": None,
    }
    assert comparisons["zero_reference"] == {
        "status": "INFO",
        "expected": 0.0,
        "actual": 0.25,
    }
    assert progress[-1] == (
        "compare_kpis",
        {"passed": False, "details": comparisons},
    )
