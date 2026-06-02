"""Tests for UI report and capsule endpoints."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent))

import server


def _client():
    return TestClient(server.app, raise_server_exceptions=False), server


def test_run_report_capsule_and_artifact_endpoints(tmp_path):
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
    assert "Abaqus Run Report" in report["markdown"]
    assert "Physics Contracts" in report["markdown"]

    capsule_res = client.get("/api/run/ui_report_001/capsule")
    assert capsule_res.status_code == 200
    assert capsule_res.json()["run_id"] == "ui_report_001"

    artifact_res = client.get("/api/run/ui_report_001/artifact/Job.log")
    assert artifact_res.status_code == 200
    assert "COMPLETED" in artifact_res.text

    bad_artifact_res = client.get("/api/run/ui_report_001/artifact/../capsule.json")
    assert bad_artifact_res.status_code in (400, 404)

    server.RUNS.pop("ui_report_001", None)
