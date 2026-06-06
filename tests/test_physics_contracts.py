from contracts.evaluator import evaluate_contracts


def test_contracts_pass_range_direction_relative_error_and_order():
    kpis = {"U_tip_y": -2.05, "SCF": 3.02, "freq_1": 10.0, "freq_2": 22.0, "freq_3": 35.0}
    contracts = [
        {"name": "tip moves downward", "type": "direction", "kpi": "U_tip_y", "op": "<", "value": 0},
        {"name": "stress concentration range", "type": "range", "kpi": "SCF", "min": 2.5, "max": 3.5},
        {"name": "tip magnitude reference", "type": "relative_error", "kpi": "U_tip_y", "reference": -2.0, "rtol": 0.05},
        {"name": "modal order", "type": "order", "kpis": ["freq_1", "freq_2", "freq_3"], "direction": "increasing"},
    ]

    result = evaluate_contracts(kpis, contracts)

    assert result["status"] == "PASS"
    assert result["passed"]
    assert result["passed_count"] == 4
    assert result["failed_count"] == 0


def test_contracts_fail_missing_and_out_of_range_values():
    result = evaluate_contracts(
        {"SCF": 4.2},
        [
            {"name": "stress concentration range", "type": "range", "kpi": "SCF", "max": 3.5},
            {"name": "missing displacement", "type": "direction", "kpi": "U_tip_y", "op": "negative"},
        ],
    )

    assert result["status"] == "FAIL"
    assert result["failed_count"] == 2
    assert "above max" in result["checks"][0]["message"]
    assert "missing KPI" in result["checks"][1]["message"]


def test_warning_severity_does_not_fail_overall_result():
    result = evaluate_contracts(
        {"energy_error": 0.18},
        [
            {
                "name": "energy balance soft limit",
                "type": "range",
                "kpi": "energy_error",
                "max": 0.15,
                "severity": "warning",
            }
        ],
    )

    assert result["status"] == "WARNING"
    assert result["passed"]
    assert result["warning_count"] == 1


def test_relative_error_zero_reference_uses_absolute_tolerance():
    passing = evaluate_contracts(
        {"reaction_sum": 0.001},
        [{"type": "relative_error", "kpi": "reaction_sum", "reference": 0.0, "atol": 0.01}],
    )
    failing = evaluate_contracts(
        {"reaction_sum": 0.02},
        [{"type": "relative_error", "kpi": "reaction_sum", "reference": 0.0, "atol": 0.01}],
    )

    assert passing["status"] == "PASS"
    assert passing["checks"][0]["rel_error"] is None
    assert failing["status"] == "FAIL"


def test_unsupported_contract_type_is_structured_failure():
    result = evaluate_contracts({"U": -1.0}, [{"name": "unknown", "type": "unit_check"}])

    assert result["status"] == "FAIL"
    assert result["checks"][0]["name"] == "unknown"
    assert "Unsupported contract type" in result["checks"][0]["message"]
