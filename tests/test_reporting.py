"""Tests for report template rendering."""

from __future__ import annotations

import json
import zipfile

import reporting.export as report_export_mod
from reporting import (
    available_templates,
    build_offline_report_bundle,
    build_offline_run_report,
    export_offline_run_report,
    render_run_report_html,
    render_run_report_markdown,
)


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


def test_available_templates_includes_delivery_template():
    assert available_templates() == ["standard", "client_summary", "engineering_delivery"]


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


def test_engineering_delivery_report_template():
    text = render_run_report_markdown(_report(), template="engineering_delivery")

    assert "Engineering Delivery Report" in text
    assert "Acceptance Snapshot" in text
    assert "Delivery verdict: `PASS`" in text
    assert "Traceability" in text
    assert "Delivery Manifest" in text
    assert "| Artifact payload | PASS | 1 artifacts, 42 B recorded |" in text
    assert "| Bundle contents | PASS | report.md, report.html, artifact_manifest.json, result.json |" in text
    assert "Evidence Checklist" in text
    assert "| KPI regression | PASS | PASS: 1 |" in text
    assert "| Physics contracts | PASS | 1 passed, 0 failed |" in text
    assert "Artifact Inventory" in text

    missing_contracts = _report()
    missing_contracts["contracts"] = {}
    review_text = render_run_report_markdown(missing_contracts, template="engineering_delivery")
    assert "Delivery verdict: `REVIEW`" in review_text
    assert "| Physics contracts | REVIEW | No Physics Contract results reported |" in review_text


def test_run_report_html_template_is_standalone_and_escaped():
    report = _report()
    report["summary"]["model_name"] = "Beam <bad>"
    report["markdown"] = render_run_report_markdown(report)

    html = render_run_report_html(report)

    assert "<!doctype html>" in html
    assert "Abaqus Run Report" in html
    assert "KPI / Regression" in html
    assert "Evidence Checklist" in html
    assert "Physics Contracts" in html
    assert "Beam &lt;bad&gt;" in html
    assert "U_tip" in html

    delivery_html = render_run_report_html(report, template="engineering_delivery")
    assert "Engineering Delivery Report" in delivery_html
    assert "Delivery Verdict" in delivery_html
    assert "Delivery Manifest" in delivery_html
    assert "Artifact payload" in delivery_html
    assert "KPI regression" in delivery_html


def test_offline_report_export_from_run_directory(tmp_path, monkeypatch):
    artifact = tmp_path / "Job.log"
    artifact.write_text("Abaqus JOB Job COMPLETED\n", encoding="utf-8")
    image = tmp_path / "mises_contour.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\n")
    (tmp_path / "capsule.json").write_text(
        json.dumps({
            "run_id": "offline_report",
            "inputs": {"model_name": "OfflineModel"},
            "provenance": {"status": "COMPLETED", "abaqus_release": "2024"},
            "artifacts": {
                "Job.log": {"path": "Job.log", "bytes": artifact.stat().st_size, "sha256": "abc"},
                "mises_contour.png": {"path": "mises_contour.png", "bytes": image.stat().st_size, "sha256": "def"},
            },
        }),
        encoding="utf-8",
    )
    (tmp_path / "result.json").write_text(
        json.dumps({
            "run_id": "offline_report",
            "status": "COMPLETED",
            "kpis": {"U_tip": -0.002},
            "regression": {"comparisons": {"U_tip": {"status": "PASS"}}},
        }),
        encoding="utf-8",
    )

    report = build_offline_run_report(tmp_path, template="client_summary", embed_images=True)
    assert report["summary"]["model_name"] == "OfflineModel"
    assert "Simulation QA Summary" in report["markdown"]
    assert "data:image/png;base64," in report["html"]

    delivery_report = build_offline_run_report(tmp_path, template="engineering_delivery")
    assert "Engineering Delivery Report" in delivery_report["markdown"]
    assert "Acceptance Snapshot" in delivery_report["markdown"]

    bundle = build_offline_report_bundle(tmp_path, template="client_summary")
    bundle_path = tmp_path / "report.zip"
    bundle_path.write_bytes(bundle)
    with zipfile.ZipFile(bundle_path) as zf:
        names = set(zf.namelist())
        assert {"report.md", "report.html", "capsule.json", "result.json", "artifact_manifest.json"} <= names
        assert "artifacts/Job.log" in names

    html_out = tmp_path / "report.html"
    result = export_offline_run_report(tmp_path / "capsule.json", html_out, template="client_summary")
    assert result["format"] == "html"
    assert html_out.exists()
    assert "Simulation QA Summary" in html_out.read_text(encoding="utf-8")

    monkeypatch.setattr(report_export_mod, "render_html_to_pdf", lambda html: b"%PDF-1.4\n" + html[:16].encode())
    pdf_out = tmp_path / "report.pdf"
    pdf_result = export_offline_run_report(tmp_path, pdf_out, template="client_summary")
    assert pdf_result["format"] == "pdf"
    assert pdf_out.read_bytes().startswith(b"%PDF-1.4")
