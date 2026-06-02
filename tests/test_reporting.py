"""Tests for report template rendering."""

from __future__ import annotations

from reporting import available_templates, render_run_report_html, render_run_report_markdown


def _report() -> dict:
    return {
        "summary": {
            "run_id": "run_001",
            "status": "COMPLETED",
            "model_name": "Beam",
            "abaqus_release": "2024",
            "capsule_path": "/tmp/capsule.json",
        },
        "kpis": {"U_tip": {"value": -0.002, "unit": "mm"}},
        "regression": {"comparisons": {"U_tip": {"status": "PASS"}}},
        "contracts": {
            "passed": True,
            "results": [{
                "name": "tip_down",
                "type": "direction",
                "severity": "error",
                "status": "PASS",
                "detail": "U_tip is negative",
            }],
        },
        "artifacts": {"Job.log": {"bytes": 42}},
        "diagnosis": {},
    }


def test_available_templates_includes_standard_and_client_summary():
    assert available_templates() == ["standard", "client_summary"]


def test_standard_run_report_template():
    text = render_run_report_markdown(_report(), template="standard")

    assert "Abaqus Run Report" in text
    assert "Physics Contracts" in text
    assert "U_tip" in text


def test_client_summary_report_template():
    text = render_run_report_markdown(_report(), template="client_summary")

    assert "Simulation QA Summary" in text
    assert "Executive Result" in text
    assert "Physics contracts: `PASS`" in text


def test_run_report_html_template_is_standalone_and_escaped():
    report = _report()
    report["summary"]["model_name"] = "Beam <bad>"
    report["markdown"] = render_run_report_markdown(report)

    html = render_run_report_html(report)

    assert "<!doctype html>" in html
    assert "Abaqus Run Report" in html
    assert "KPI / Regression" in html
    assert "Physics Contracts" in html
    assert "Beam &lt;bad&gt;" in html
    assert "U_tip" in html
