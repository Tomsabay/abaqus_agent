"""Tests for report template rendering."""

from __future__ import annotations

import io
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


NO_SOLVE_TEXT = "未求解 · 无数值结果"


def test_unsolved_run_report_marks_first_screen(tmp_path):
    """G2 criterion 4: every export channel (md/html/zip) must carry the
    no-solve banner on its first screen when the run produced no numbers."""
    (tmp_path / "result.json").write_text(
        json.dumps({
            "run_id": "unsolved_run",
            "status": "FAILED",
            "unsolved": True,
            "kpi_notice": "未检测到 Abaqus，无法求解；用 ABAQUS_AGENT_ABAQUS_CMD 指向它",
            "kpis": {},
            "regression": {},
            "contracts": {},
        }, ensure_ascii=False),
        encoding="utf-8",
    )

    for template in available_templates():
        report = build_offline_run_report(tmp_path, template=template)
        md_first_screen = "\n".join(report["markdown"].splitlines()[:5])
        assert NO_SOLVE_TEXT in md_first_screen
        # First screen of the HTML document = the hero section.
        hero = report["html"].split("</section>")[0]
        assert NO_SOLVE_TEXT in hero
        # These reports must not carry a numeric KPI value.
        assert report["kpis"] == {}

    bundle = build_offline_report_bundle(tmp_path)
    with zipfile.ZipFile(io.BytesIO(bundle)) as zf:
        assert NO_SOLVE_TEXT in zf.read("report.md").decode("utf-8")
        assert NO_SOLVE_TEXT in zf.read("report.html").decode("utf-8")


def test_a_solved_run_report_carries_no_such_banner():
    """A real solve must render without any no-solve marker."""
    for template in available_templates():
        text = render_run_report_markdown(_report(), template=template)
        assert NO_SOLVE_TEXT not in text
        assert "演示数据" not in text
    html = render_run_report_html(_report())
    assert NO_SOLVE_TEXT not in html
    assert "演示数据" not in html


def test_abaqus_report_cover_keeps_its_release_row():
    from reporting.templates import render_run_report_html, render_run_report_markdown

    report = {
        "summary": {"run_id": "r1", "status": "COMPLETED", "model_name": "Cantilever",
                    "abaqus_release": "2021", "solver_backend": "abaqus"},
        "kpis": {}, "regression": {}, "contracts": {}, "stages": {},
        "capsule": {}, "artifacts": {}, "image_artifacts": [],
    }
    assert "2021" in render_run_report_html(report)
    assert "- Abaqus: `2021`" in render_run_report_markdown(report)


# ── offline export: the cover must name the solver that actually ran ────────
# build_offline_run_report never handed the template solver_backend, so the
# archived report asserted a solver it had not read — the class of defect that
# makes a report unciteable, whatever the backend happens to be.

def _write_run_dir(tmp_path, provenance, spec_release="2021"):
    (tmp_path / "capsule.json").write_text(json.dumps({
        "run_id": "r-offline",
        "provenance": provenance,
        "artifacts": {},
    }), encoding="utf-8")
    (tmp_path / "result.json").write_text(json.dumps({
        "run_id": "r-offline",
        "status": "COMPLETED",
        "spec": {"meta": {"model_name": "Cantilever", "abaqus_release": spec_release}},
        "kpis": {"U_tip": -0.001903958},
    }), encoding="utf-8")
    return tmp_path


def test_offline_export_of_an_abaqus_run_keeps_its_release(tmp_path):
    from reporting.export import build_offline_run_report

    run_dir = _write_run_dir(tmp_path, {
        "status": "COMPLETED",
        "solver_backend": "abaqus",
        "abaqus_release": "2021",
    })

    report = build_offline_run_report(run_dir)

    assert report["summary"]["solver_backend"] == "abaqus"
    assert report["summary"]["abaqus_release"] == "2021"
    assert "- Abaqus: `2021`" in report["markdown"]


def test_offline_export_of_a_pre_backend_run_stays_silent(tmp_path):
    """Runs archived before the backend was recorded must not be assumed
    Abaqus — but they still carry a release the spec asserted, so the row
    stays, it just is not attributed to a backend we cannot prove."""
    from reporting.export import build_offline_run_report

    run_dir = _write_run_dir(tmp_path, {"status": "COMPLETED"})

    report = build_offline_run_report(run_dir)

    assert report["summary"]["solver_backend"] is None
    assert report["summary"]["solver_label"] is None


# ── the verdict on top of the comparisons ────────────────────────────
#
# Two things the delivery report used to get wrong, both measured 2026-08-09.
# It derived `Regression` purely from the per-KPI comparison statuses, so
# `regression.passed = False` -- the field _block_regression_on_integrity sets
# when a model's constraints did not all take effect -- was invisible and the
# report printed `PASS`. And a run that compared nothing at all rendered
# identically to a run with no regression section, because both produced "-".


def _integrity_blocked_report() -> dict:
    report = _report()
    # Comparisons stay green on purpose: equilibrium holds however the load
    # gets carried. Only the verdict on top of them is withdrawn.
    report["regression"] = {
        "passed": False,
        "comparisons": {"U_tip": {"status": "PASS"}},
        "blocked_by_integrity": {
            "count": 85,
            "findings": ["dat.unconstrained_nodes"],
            "note": "85 个节点上的约束没有生效",
        },
    }
    return report


def test_an_integrity_blocked_run_does_not_render_regression_pass():
    from reporting.templates import _regression_status

    assert _regression_status(_integrity_blocked_report()) == "FAIL"
    text = render_run_report_markdown(_integrity_blocked_report(),
                                      template="engineering_delivery")
    assert "- KPI regression: `FAIL`" in text
    assert "- Delivery verdict: `REVIEW`" in text


def _ungraded_report() -> dict:
    report = _report()
    report["regression"] = {
        "passed": None, "comparisons": {},
        "not_compared_reason": "本次运行没有提供 expected.json 基准，未做任何数值比对",
    }
    report["contracts"] = {
        "passed": None, "results": [],
        "not_checked_reason": "没有加载到任何 physics contract，本次运行未做契约检查",
    }
    return report


def test_a_run_that_graded_nothing_says_not_graded_and_says_why():
    text = render_run_report_markdown(_ungraded_report(),
                                      template="engineering_delivery")

    assert "- KPI regression: `NOT GRADED`" in text
    assert "- Physics contracts: `NOT GRADED`" in text
    # The verdict must not survive an ungraded run.
    assert "- Delivery verdict: `REVIEW`" in text
    # And the reason has to be somewhere a reader will meet it, not only in
    # the JSON: the contract section used to be omitted entirely.
    assert "expected.json" in text
    assert "没有加载到任何 physics contract" in text


def test_not_graded_is_amber_not_red_in_the_html():
    from reporting.templates import _status_class

    assert _status_class("NOT GRADED") == "warn"
    html = render_run_report_html(_ungraded_report(),
                                  template="engineering_delivery")
    assert "NOT GRADED" in html


def test_a_graded_clean_run_still_reports_pass():
    """The guard against over-correcting: a real comparison that held must
    still read PASS, and the delivery verdict must still be reachable."""
    text = render_run_report_markdown(_report(), template="engineering_delivery")
    assert "- KPI regression: `PASS`" in text
    assert "- Physics contracts: `PASS`" in text
    assert "- Delivery verdict: `PASS`" in text
