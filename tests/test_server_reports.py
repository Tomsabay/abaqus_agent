"""Tests for UI report and capsule endpoints."""

from __future__ import annotations

import json
import sys
import time
import zipfile
from io import BytesIO
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent))

import server


def _client():
    return TestClient(server.app, raise_server_exceptions=False), server


def test_environment_preflight_endpoint(monkeypatch):
    client, _server = _client()

    def fake_preflight(**kwargs):
        assert kwargs["abaqus_cmd"] == "abaqus"
        assert kwargs["timeout_seconds"] == 2.0
        assert kwargs["check_release"] is False
        assert kwargs["expected_release"] == "2026"
        assert kwargs["workdir"] == "runs"
        assert kwargs["runner_cfg"] == {"cpus": 2}
        return {
            "status": "unknown",
            "platform": {"system": "Linux"},
            "abaqus": {"command": "abaqus", "release_check": {"status": "skipped"}},
            "checks": [],
        }

    monkeypatch.setattr(server, "run_environment_preflight", fake_preflight)

    res = client.post("/api/validate/env", json={
        "abaqus_cmd": "abaqus",
        "timeout_seconds": 2.0,
        "check_release": False,
        "expected_release": "2026",
        "workdir": "runs",
        "runner_cfg": {"cpus": 2},
    })

    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "unknown"
    assert "Abaqus Environment Preflight" in data["markdown"]


def test_offline_report_export_endpoints(tmp_path, monkeypatch):
    client, _server = _client()
    artifact = tmp_path / "Job.log"
    artifact.write_text("Abaqus JOB Job COMPLETED\n", encoding="utf-8")
    (tmp_path / "capsule.json").write_text(
        json.dumps({
            "run_id": "api_offline_report",
            "inputs": {"model_name": "ApiOffline"},
            "provenance": {"status": "COMPLETED", "abaqus_release": "2024"},
            "artifacts": {"Job.log": {"path": "Job.log", "sha256": "abc", "bytes": artifact.stat().st_size}},
        }),
        encoding="utf-8",
    )
    (tmp_path / "result.json").write_text(
        json.dumps({
            "run_id": "api_offline_report",
            "status": "COMPLETED",
            "kpis": {"U_tip": -0.002},
            "regression": {"comparisons": {"U_tip": {"status": "PASS"}}},
        }),
        encoding="utf-8",
    )

    res = client.post("/api/report/export", json={
        "source": str(tmp_path),
        "template": "client_summary",
    })
    assert res.status_code == 200
    data = res.json()
    assert data["summary"]["run_id"] == "api_offline_report"
    assert data["summary"]["model_name"] == "ApiOffline"
    assert data["offline_source"] == str(tmp_path)
    assert "Simulation QA Summary" in data["markdown"]

    zip_res = client.post("/api/report/export.zip", json={
        "source": str(tmp_path),
        "template": "client_summary",
    })
    assert zip_res.status_code == 200
    assert "application/zip" in zip_res.headers["content-type"]
    assert 'filename="abaqus-report-api_offline_report.zip"' in zip_res.headers["content-disposition"]
    with zipfile.ZipFile(BytesIO(zip_res.content)) as bundle:
        names = set(bundle.namelist())
        assert {"report.md", "report.html", "capsule.json", "result.json", "artifact_manifest.json"} <= names
        assert "artifacts/Job.log" in names

    monkeypatch.setattr(server, "build_offline_report_pdf", lambda *args, **kwargs: b"%PDF-1.4\noffline")
    pdf_res = client.post("/api/report/export.pdf", json={
        "source": str(tmp_path),
        "template": "client_summary",
    })
    assert pdf_res.status_code == 200
    assert "application/pdf" in pdf_res.headers["content-type"]
    assert 'filename="abaqus-report-api_offline_report.pdf"' in pdf_res.headers["content-disposition"]
    assert pdf_res.content.startswith(b"%PDF-1.4")


def test_run_report_capsule_and_artifact_endpoints(tmp_path, monkeypatch):
    client, server = _client()
    workdir = tmp_path / "run"
    workdir.mkdir()
    artifact = workdir / "Job.log"
    artifact.write_text("Abaqus JOB Job COMPLETED\n", encoding="utf-8")
    image = workdir / "mises_contour.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\n")
    capsule = {
        "schema_version": "0.2.0-dev",
        "run_id": "ui_report_001",
        "created_at": "2026-06-02T10:00:00",
        "inputs": {"model_name": "UiModel"},
        "artifacts": {
            "Job.log": {
                "path": "Job.log",
                "sha256": "abc",
                "bytes": artifact.stat().st_size,
            },
            "mises_contour.png": {
                "path": "mises_contour.png",
                "sha256": "def",
                "bytes": image.stat().st_size,
            }
        },
        "provenance": {
            "status": "COMPLETED",
            "abaqus_release": "2024",
        },
        "contracts": {
            "passed": True,
            "results": [
                {
                    "name": "tip_down",
                    "check": "operator",
                    "severity": "error",
                    "status": "PASS",
                    "passed": True,
                    "detail": "U_tip=-0.0019, expected < 0.0",
                }
            ],
        },
    }
    capsule_path = workdir / "capsule.json"
    capsule_path.write_text(json.dumps(capsule), encoding="utf-8")

    server.RUNS["ui_report_001"] = {
        "run_id": "ui_report_001",
        "status": "COMPLETED",
        "spec": {"meta": {"model_name": "UiModel", "abaqus_release": "2024"}},
        "stages": {},
        "kpis": {"U_tip": -0.0019},
        "regression": {"comparisons": {"U_tip": {"status": "PASS", "expected": -0.002}}},
        "contracts": {},
        "started_at": time.time(),
        "finished_at": time.time(),
        "capsule_path": str(capsule_path),
        "result_path": str(workdir / "result.json"),
        "workdir": str(workdir),
    }

    report_res = client.get("/api/run/ui_report_001/report")
    assert report_res.status_code == 200
    report = report_res.json()
    assert report["summary"]["run_id"] == "ui_report_001"
    assert report["artifacts"]["Job.log"]["bytes"] > 0
    assert report["image_artifacts"] == ["mises_contour.png"]
    assert report["contracts"]["results"][0]["name"] == "tip_down"
    assert report["template"] == "standard"
    assert "Abaqus Run Report" in report["markdown"]
    assert "Abaqus Run Report" in report["html"]
    assert "Physics Contracts" in report["markdown"]

    client_report_res = client.get("/api/run/ui_report_001/report?template=client_summary")
    assert client_report_res.status_code == 200
    client_report = client_report_res.json()
    assert client_report["template"] == "client_summary"
    assert "Simulation QA Summary" in client_report["markdown"]
    assert "Executive Result" in client_report["markdown"]

    markdown_res = client.get("/api/run/ui_report_001/report.md?template=client_summary")
    assert markdown_res.status_code == 200
    assert "text/markdown" in markdown_res.headers["content-type"]
    assert 'filename="abaqus-report-ui_report_001.md"' in markdown_res.headers["content-disposition"]
    assert "Simulation QA Summary" in markdown_res.text

    html_res = client.get("/api/run/ui_report_001/report.html?template=client_summary")
    assert html_res.status_code == 200
    assert "text/html" in html_res.headers["content-type"]
    assert 'filename="abaqus-report-ui_report_001.html"' in html_res.headers["content-disposition"]
    assert "Simulation QA Summary" in html_res.text
    assert "mises_contour.png" in html_res.text
    assert "data:image/png;base64," in html_res.text

    preview_res = client.get("/api/run/ui_report_001/report.html?template=client_summary&download=false")
    assert preview_res.status_code == 200
    assert "text/html" in preview_res.headers["content-type"]
    assert 'inline; filename="abaqus-report-ui_report_001.html"' in preview_res.headers["content-disposition"]

    monkeypatch.setattr(server, "render_html_to_pdf", lambda html: b"%PDF-1.4\n" + html[:8].encode())
    pdf_res = client.get("/api/run/ui_report_001/report.pdf?template=client_summary")
    assert pdf_res.status_code == 200
    assert "application/pdf" in pdf_res.headers["content-type"]
    assert 'filename="abaqus-report-ui_report_001.pdf"' in pdf_res.headers["content-disposition"]
    assert pdf_res.content.startswith(b"%PDF-1.4")

    bundle_res = client.get("/api/run/ui_report_001/report.zip?template=client_summary")
    assert bundle_res.status_code == 200
    assert "application/zip" in bundle_res.headers["content-type"]
    assert 'filename="abaqus-report-ui_report_001.zip"' in bundle_res.headers["content-disposition"]
    with zipfile.ZipFile(BytesIO(bundle_res.content)) as bundle:
        names = set(bundle.namelist())
        assert {"report.md", "report.html", "capsule.json", "artifact_manifest.json"} <= names
        assert "artifacts/Job.log" in names
        assert "artifacts/mises_contour.png" in names
        assert "Simulation QA Summary" in bundle.read("report.md").decode("utf-8")
        manifest = json.loads(bundle.read("artifact_manifest.json"))
        assert manifest["included_artifacts"][0]["name"] == "Job.log"

    capsule_res = client.get("/api/run/ui_report_001/capsule")
    assert capsule_res.status_code == 200
    assert capsule_res.json()["run_id"] == "ui_report_001"

    artifact_res = client.get("/api/run/ui_report_001/artifact/Job.log")
    assert artifact_res.status_code == 200
    assert "COMPLETED" in artifact_res.text

    bad_artifact_res = client.get("/api/run/ui_report_001/artifact/../capsule.json")
    assert bad_artifact_res.status_code in (400, 404)

    server.RUNS.pop("ui_report_001", None)


def test_run_diff_endpoint_compares_two_runs():
    client, server = _client()
    server.RUNS["diff_base"] = {
        "run_id": "diff_base",
        "status": "COMPLETED",
        "spec": {"bc_load": {"value": -1.0}},
        "kpis": {"U_tip": -0.002},
        "contracts": {"results": [{"name": "tip_down", "status": "PASS"}]},
        "started_at": time.time(),
    }
    server.RUNS["diff_candidate"] = {
        "run_id": "diff_candidate",
        "status": "COMPLETED",
        "spec": {"bc_load": {"value": -1.1}},
        "kpis": {"U_tip": -0.0023},
        "contracts": {"results": [{"name": "tip_down", "status": "PASS"}]},
        "started_at": time.time(),
    }

    res = client.get("/api/run/diff_base/diff/diff_candidate?rtol=0.05")

    assert res.status_code == 200
    data = res.json()
    assert data["baseline"]["run_id"] == "diff_base"
    assert data["candidate"]["run_id"] == "diff_candidate"
    assert data["summary"]["sections"]["kpis"]["WARNING"] == 1
    assert data["sections"]["kpis"]["changes"][0]["status"] == "WARNING"
    assert "Simulation Diff Report" in data["markdown"]
    assert "Change Summary" in data["markdown"]

    tuned_res = client.get(
        "/api/run/diff_base/diff/diff_candidate?rtol=0.05"
        "&tolerances_json=%7B%22U_tip%22%3A%200.2%7D"
    )
    assert tuned_res.status_code == 200
    tuned = tuned_res.json()
    assert tuned["summary"]["sections"]["kpis"]["PASS"] == 1
    assert tuned["summary"]["sections"]["kpis"]["WARNING"] == 0

    md_res = client.get("/api/run/diff_base/diff/diff_candidate/diff.md?rtol=0.05")
    assert md_res.status_code == 200
    assert "text/markdown" in md_res.headers["content-type"]
    assert 'filename="abaqus-diff-diff_base-vs-diff_candidate.md"' in md_res.headers["content-disposition"]
    assert "Simulation Diff Report" in md_res.text
    assert "Change Summary" in md_res.text

    server.RUNS.pop("diff_base", None)
    server.RUNS.pop("diff_candidate", None)


def test_post_diff_endpoint_accepts_per_kpi_tolerances(tmp_path):
    client, _server = _client()
    baseline = tmp_path / "baseline.json"
    candidate = tmp_path / "candidate.json"
    baseline.write_text(json.dumps({"kpis": {"MISES": 100.0, "U_tip": -0.002}}), encoding="utf-8")
    candidate.write_text(json.dumps({"kpis": {"MISES": 125.0, "U_tip": -0.0022}}), encoding="utf-8")

    res = client.post("/api/diff", json={
        "baseline": str(baseline),
        "candidate": str(candidate),
        "rtol": 0.05,
        "tolerances": {"MISES": 0.3},
    })

    assert res.status_code == 200
    data = res.json()
    assert data["summary"]["sections"]["kpis"]["PASS"] == 1
    assert data["summary"]["sections"]["kpis"]["WARNING"] == 1


def test_memory_search_endpoint(tmp_path):
    client, _server = _client()
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    spec = {
        "meta": {"model_name": "ApiMemoryModel", "abaqus_release": "2024"},
        "geometry": {"type": "custom_inp"},
        "material": {"name": "Steel"},
        "analysis": {"solver": "standard"},
    }
    (run_dir / "result.json").write_text(json.dumps({"run_id": "api_memory", "status": "COMPLETED", "spec": spec}), encoding="utf-8")
    (run_dir / "capsule.json").write_text(
        json.dumps({
            "schema_version": "0.2.0-dev",
            "run_id": "api_memory",
            "created_at": "2026-06-02T10:00:00",
            "inputs": {"model_name": "ApiMemoryModel"},
            "artifacts": {"Job.log": {"path": "Job.log", "sha256": "abc", "bytes": 10}},
            "provenance": {"status": "COMPLETED"},
            "contracts": {"passed": True, "results": [{"name": "tip_down", "passed": True}]},
        }),
        encoding="utf-8",
    )

    res = client.post("/api/memory/search", json={
        "roots": [str(tmp_path)],
        "query": "ApiMemoryModel",
        "match_mode": "all",
        "geometry_type": "custom",
        "solver": "standard",
        "material_name": "Steel",
        "artifact": "Job.log",
        "contract": "tip",
        "contracts_passed": "passed",
        "sort_by": "run_id",
        "sort_order": "asc",
        "min_score": 0.5,
    })

    assert res.status_code == 200
    data = res.json()
    assert data["matches"][0]["run_id"] == "api_memory"
    assert data["query"]["match_mode"] == "all"
    assert data["query"]["geometry_type"] == "custom"
    assert data["query"]["solver"] == "standard"
    assert data["query"]["material_name"] == "Steel"
    assert data["query"]["artifact"] == "Job.log"
    assert data["query"]["contract"] == "tip"
    assert data["query"]["contracts_passed"] == "passed"
    assert data["query"]["sort_by"] == "run_id"
    assert data["query"]["sort_order"] == "asc"
    assert data["query"]["min_score"] == 0.5
    assert "Case Memory Search" in data["markdown"]


# ── the report must carry the caveats the run carried ───────────────────────

def _unsolved_run() -> dict:
    """A run the way core/pipeline.py leaves one when no solver was found.

    Whether it is unsolved is read off the backend decision, not off a flag
    the run sets for itself: the flag was `demo_mode`, set by a walkthrough
    that finished COMPLETED, so neither the flag nor the status told the
    renderer the truth.
    """
    return {
        "run_id": "unsolved-report",
        "status": "FAILED",
        "spec": {"meta": {"model_name": "Beam", "abaqus_release": "2021"}},
        "kpis": {},
        "backend": {"backend": "abaqus", "supported": False,
                    "blockers": [{"feature": "ABAQUS_AGENT_SOLVER_BACKEND",
                                  "value": "abaqus", "reason": "未检测到 Abaqus"}]},
        "kpi_notice": "未检测到 Abaqus，本次没有求解",
        "limitations": ["85 tie nodes were silently left unconstrained"],
        "kpis_missing": [{"name": "U_tip", "reason": "no odb was produced"}],
    }


def test_an_unsolved_run_cannot_export_a_report_that_looks_real():
    """The report outlives the session; it gets mailed to someone who never
    saw the screen. _build_run_report used to drop the flag entirely, and the
    renderer's status fallback did not catch it either -- so a run in which
    nothing was solved exported markdown, HTML and PDF with no marking
    anywhere."""
    from reporting.templates import NO_SOLVE_BANNER

    report = server._build_run_report(_unsolved_run())

    assert report["unsolved"] is True
    assert NO_SOLVE_BANNER in report["markdown"]
    assert NO_SOLVE_BANNER in report["html"]


def test_a_run_that_reached_the_solver_is_not_marked_unsolved():
    """The other direction: a job that ran and aborted has a solver behind it
    and a .msg file to read. Marking it "no solve" would send the reader to
    the wrong problem."""
    run = dict(_unsolved_run(), status="FAILED",
               backend={"backend": "abaqus", "supported": True,
                        "label": "Abaqus 2021"})

    report = server._build_run_report(run)

    assert report["unsolved"] is False


def test_the_report_carries_the_limitations_the_run_recorded():
    """"85 tie nodes were silently left unconstrained" is the whole reason
    the limitations channel exists. It reached the screen and not the file."""
    report = server._build_run_report(_unsolved_run())

    assert report["limitations"] == [
        "85 tie nodes were silently left unconstrained"]
    assert "tie nodes" in report["markdown"]
    assert "tie nodes" in report["html"]


def test_the_report_names_the_kpis_that_were_asked_for_and_not_produced():
    """Without the denominator, a report showing 2 KPIs looks complete when 5
    were requested."""
    run = dict(_unsolved_run(), kpis={"MISES_MAX": {"value": 1.0}},
               backend={"backend": "abaqus", "supported": True})

    report = server._build_run_report(run)

    assert [e["name"] for e in report["kpis_missing"]] == ["U_tip"]
    assert "U_tip" in report["markdown"]
