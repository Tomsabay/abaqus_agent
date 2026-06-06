from run_benchmark import generate_report


def test_generate_report_summarizes_pipeline_and_regression_counts():
    report = generate_report(
        [
            {
                "case": "cantilever",
                "status": "COMPLETED",
                "elapsed_seconds": 1.24,
                "kpis": {"U_tip": -2.04, "max_mises": 107.0},
                "regression": {
                    "passed": True,
                    "comparisons": {
                        "U_tip": {
                            "expected": -2.0,
                            "actual": -2.04,
                            "rel_err": 0.02,
                            "status": "PASS",
                        }
                    },
                },
            },
            {
                "case": "plate_hole",
                "status": "ERROR",
                "elapsed_seconds": 0.5,
                "kpis": {},
                "regression": {"passed": False},
                "error": {
                    "message": "solver unavailable",
                    "error_code": "ABAQUS_NOT_FOUND",
                    "suggestion": "Install Abaqus or use dry-run.",
                },
            },
        ]
    )

    assert "# Abaqus Agent Benchmark Report" in report
    assert "| Total cases | 2 |" in report
    assert "| Pipeline passed | 1 / 2 |" in report
    assert "| Regression passed | 1 / 2 |" in report
    assert "| Failed / Error | 1 |" in report
    assert "| cantilever | COMPLETED | 1.2s | U_tip=-2.04, max_mises=107 | PASS |" in report
    assert "| plate_hole | ERROR | 0.5s | - | FAIL |" in report


def test_generate_report_renders_kpi_comparisons_and_error_details():
    report = generate_report(
        [
            {
                "case": "modal",
                "status": "COMPLETED",
                "elapsed_seconds": 2.0,
                "kpis": {"freq_1": 48.0},
                "regression": {
                    "passed": False,
                    "comparisons": {
                        "freq_1": {
                            "expected": 50.0,
                            "actual": 48.0,
                            "rel_err": 0.04,
                            "status": "FAIL",
                        }
                    },
                },
            },
            {
                "case": "explicit_impact",
                "status": "SPEC_INVALID",
                "elapsed_seconds": 0.0,
                "kpis": {},
                "regression": {},
                "error": {
                    "message": "missing outputs",
                    "error_code": "SPEC_INVALID",
                    "suggestion": "Add at least one KPI.",
                },
            },
        ]
    )

    assert "### modal" in report
    assert "| KPI | Expected | Actual | Rel Err | Status |" in report
    assert "| freq_1 | 50.0 | 48.0 | 4.0% | FAIL |" in report
    assert "**explicit_impact**: missing outputs (code: SPEC_INVALID)" in report
    assert "  - Suggestion: Add at least one KPI." in report


def test_generate_report_renders_physics_contract_results():
    report = generate_report(
        [
            {
                "case": "cantilever",
                "status": "COMPLETED",
                "elapsed_seconds": 1.0,
                "kpis": {"U_tip": -2.04},
                "regression": {},
                "contracts": {
                    "status": "WARNING",
                    "checks": [
                        {
                            "name": "tip moves downward",
                            "status": "PASS",
                            "message": "U_tip=-2.04 satisfies < 0.0",
                        },
                        {
                            "name": "energy balance",
                            "status": "WARNING",
                            "message": "energy_error=0.18 is above max 0.15",
                        },
                    ],
                },
            }
        ]
    )

    assert "## Physics Contracts" in report
    assert "### cantilever" in report
    assert "Overall: WARNING" in report
    assert "| Contract | Status | Message |" in report
    assert "| tip moves downward | PASS | U_tip=-2.04 satisfies < 0.0 |" in report
    assert "| energy balance | WARNING | energy_error=0.18 is above max 0.15 |" in report
