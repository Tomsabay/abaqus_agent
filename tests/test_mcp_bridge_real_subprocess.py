"""HTTP-to-MCP bridge smoke tests with a real MCP subprocess.

The regular bridge tests mock ``MCPConnection``. This file verifies that the
FastAPI bridge can start its real connection to ``mcp_server.py`` and route
requests through that subprocess.
"""

from __future__ import annotations

import hashlib
import json
import zipfile
from io import BytesIO
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def bridge_with_real_subprocess(monkeypatch, tmp_path):
    import mcp_bridge

    monkeypatch.setenv("ABAQUS_AGENT_EVIDENCE_VAULT", str(tmp_path / "bridge-vault"))
    original_conn = mcp_bridge.mcp_conn
    mcp_bridge.mcp_conn = mcp_bridge.MCPConnection()
    mcp_bridge.EVIDENCE_ARTIFACTS.clear()
    mcp_bridge.EVIDENCE_ARTIFACT_SEQUENCE = 0
    mcp_bridge.DEMO_GALLERY_ARTIFACTS.clear()
    try:
        yield mcp_bridge
    finally:
        mcp_bridge.EVIDENCE_ARTIFACTS.clear()
        mcp_bridge.EVIDENCE_ARTIFACT_SEQUENCE = 0
        mcp_bridge.DEMO_GALLERY_ARTIFACTS.clear()
        mcp_bridge.mcp_conn = original_conn


def test_bridge_routes_to_real_mcp_subprocess(bridge_with_real_subprocess) -> None:
    with TestClient(
        bridge_with_real_subprocess.app,
        raise_server_exceptions=False,
    ) as client:
        health = client.get("/mcp/health")
        assert health.status_code == 200
        health_data = health.json()
        assert health_data["status"] == "ok"
        assert health_data["transport"] == "mcp"
        assert "cantilever" in health_data["cases"]

        spec_yaml = (ROOT / "cases" / "cantilever" / "spec.yaml").read_text(
            encoding="utf-8"
        )
        validation = client.post(
            "/mcp/api/spec/validate",
            json={"spec_yaml": spec_yaml},
        )
        assert validation.status_code == 200
        assert validation.json() == {"valid": True, "errors": []}

        benchmark = client.get("/mcp/api/benchmark")
        assert benchmark.status_code == 200
        benchmark_data = benchmark.json()
        assert benchmark_data["total"] >= 4
        expected_cases = {
            "cantilever",
            "plate_hole",
            "modal",
            "explicit_impact",
        }
        assert expected_cases.issubset({case["name"] for case in benchmark_data["cases"]})

        benchmark_run = client.post("/mcp/api/benchmark/run?dry_run=true")
        assert benchmark_run.status_code == 200
        benchmark_run_data = benchmark_run.json()
        assert benchmark_run_data["dry_run"] is True
        assert benchmark_run_data["run_id"].startswith("bench_")
        assert expected_cases.issubset(set(benchmark_run_data["cases"]))

        examples = client.get("/mcp/api/evidence/examples")
        assert examples.status_code == 200
        example_cases = {item["case"] for item in examples.json()["cases"]}
        assert {
            "cantilever",
            "custom_inp_deck",
            "explicit_impact",
            "modal",
            "plate_hole",
        }.issubset(example_cases)
        custom_summary = next(item for item in examples.json()["cases"] if item["case"] == "custom_inp_deck")
        assert custom_summary["input_type"] == "custom_inp"
        plate_example = client.get("/mcp/api/evidence/examples/plate_hole")
        assert plate_example.status_code == 200
        plate_data = plate_example.json()
        assert plate_data["run_id"] == "plate_hole-example-offline"
        assert plate_data["candidate_kpis"]["MISES_HOLE_EDGE"] == 300.0
        assert plate_data["contracts"][0]["kpi"] == "MISES_HOLE_EDGE"
        custom_example = client.get("/mcp/api/evidence/examples/custom_inp_deck")
        assert custom_example.status_code == 200
        custom_data = custom_example.json()
        assert custom_data["input_type"] == "custom_inp"
        assert custom_data["input_path"].endswith(".inp")

        recipes = client.get("/mcp/api/kpi-recipes")
        assert recipes.status_code == 200
        recipe_data = recipes.json()
        assert recipe_data["workflow"] == "kpi-recipe-gallery"
        assert "eigenfrequency" in recipe_data["supported_kpi_types"]
        assert {"cantilever", "plate_hole", "modal", "explicit_impact"}.issubset(
            {item["case"] for item in recipe_data["items"]}
        )
        displacement_recipes = client.get(
            "/mcp/api/kpi-recipes",
            params={"kpi_type": "nodal_displacement"},
        )
        assert displacement_recipes.status_code == 200
        assert any(
            item["id"] == "cantilever-tip-displacement"
            for item in displacement_recipes.json()["items"]
        )
        modal_recipe = client.get("/mcp/api/kpi-recipes/modal-first-three-frequencies")
        assert modal_recipe.status_code == 200
        assert modal_recipe.json()["kpi_spec"][0]["type"] == "eigenfrequency"

        simdiff = client.post(
            "/mcp/api/simdiff/kpis",
            json={
                "diff_id": "bridge-simdiff-cantilever",
                "baseline_kpis": {"U_tip": -2.0, "max_mises": 100.0},
                "candidate_kpis": {"U_tip": -2.4, "max_mises": 100.0},
                "tolerances": {"U_tip": {"rtol": 0.05}},
                "input_metadata": {"case": "cantilever"},
            },
        )
        assert simdiff.status_code == 200
        simdiff_data = simdiff.json()
        assert simdiff_data["diff_id"] == "bridge-simdiff-cantilever"
        assert simdiff_data["overall_status"] == "FAIL"
        assert simdiff_data["diff"]["changed_count"] == 1
        assert simdiff_data["vault_id"].startswith("simulation-diff-")
        assert simdiff_data["vault_urls"]["diff.md"].startswith("/mcp/api/evidence/vault/")
        assert "Simulation Diff Report" in simdiff_data["report_markdown"]

        simdiff_vault_report = client.get(simdiff_data["vault_urls"]["diff.md"])
        assert simdiff_vault_report.status_code == 200
        assert "supplied KPI JSON values" in simdiff_vault_report.text

        demo_gallery = client.post("/mcp/api/evidence/demo-gallery")
        assert demo_gallery.status_code == 200
        demo_gallery_data = demo_gallery.json()
        assert demo_gallery_data["overall_status"] == "PASS"
        assert demo_gallery_data["case_count"] == 4
        assert demo_gallery_data["artifact_id"].startswith("demo-gallery-")
        assert demo_gallery_data["artifact_urls"]["index_json"].startswith(
            "/mcp/api/evidence/demo-gallery/"
        )
        assert demo_gallery_data["artifact_urls"]["index_html"].endswith("/index.html")
        assert demo_gallery_data["artifact_urls"]["gallery_zip"].endswith(
            "/offline-demo-gallery.zip"
        )
        assert demo_gallery_data["vault_id"].startswith("demo-gallery-")
        assert demo_gallery_data["vault_urls"]["index.html"].endswith("/index.html")
        assert demo_gallery_data["vault_urls"]["offline-demo-gallery.zip"].endswith(
            "/offline-demo-gallery.zip"
        )
        assert "Offline Demo Gallery" in demo_gallery_data["index_markdown"]
        assert "Abaqus Agent Offline Demo Gallery" in demo_gallery_data["index_html"]
        assert demo_gallery_data["index_html_url"] == demo_gallery_data["vault_urls"]["index.html"]

        demo_index = client.get(demo_gallery_data["artifact_urls"]["index_json"])
        assert demo_index.status_code == 200
        assert demo_index.json()["workflow"] == "offline-demo-gallery"

        demo_html = client.get(demo_gallery_data["artifact_urls"]["index_html"])
        assert demo_html.status_code == 200
        assert "text/html" in demo_html.headers["content-type"]
        assert "does not invoke Abaqus" in demo_html.text

        demo_zip = client.get(demo_gallery_data["artifact_urls"]["gallery_zip"])
        assert demo_zip.status_code == 200
        assert demo_zip.headers["content-type"] == "application/zip"
        with zipfile.ZipFile(BytesIO(demo_zip.content)) as gallery_bundle:
            assert {
                "gallery_manifest.json",
                "index.html",
                "index.json",
                "index.md",
                "explicit_impact/evidence.json",
                "explicit_impact/evidence.html",
                "explicit_impact/evidence.md",
                "explicit_impact/capsule.json",
                "explicit_impact/explicit_impact-demo-bundle.zip",
                "cases/explicit_impact/evidence.json",
                "cases/explicit_impact/evidence.html",
                "cases/explicit_impact/evidence.md",
                "cases/explicit_impact/capsule.json",
                "cases/explicit_impact/explicit_impact-demo-bundle.zip",
            }.issubset(set(gallery_bundle.namelist()))
            gallery_manifest = json.loads(gallery_bundle.read("gallery_manifest.json"))
            assert gallery_manifest["workflow"] == "offline-demo-gallery"
            assert gallery_manifest["case_count"] == 4

        demo_vault_zip = client.get(demo_gallery_data["vault_urls"]["offline-demo-gallery.zip"])
        assert demo_vault_zip.status_code == 200
        assert demo_vault_zip.headers["content-type"] == "application/zip"

        demo_vault_html = client.get(demo_gallery_data["vault_urls"]["index.html"])
        assert demo_vault_html.status_code == 200
        assert "text/html" in demo_vault_html.headers["content-type"]

        demo_pack = client.post("/mcp/api/evidence/demo-pack")
        assert demo_pack.status_code == 200
        demo_pack_data = demo_pack.json()
        assert demo_pack_data["overall_status"] == "PASS"
        assert demo_pack_data["real_env_verified"] is False
        assert demo_pack_data["vault_id"].startswith("local-demo-pack-")
        assert demo_pack_data["pack_zip_url"] == demo_pack_data["vault_urls"]["local-demo-pack.zip"]
        assert demo_pack_data["index"]["workflow"] == "local-demo-pack"
        assert demo_pack_data["index"]["offline_demo_gallery"]["case_count"] == 4
        assert demo_pack_data["index"]["solver_doctor"]["status"] == "FAILED"
        assert demo_pack_data["index"]["simulation_diff"]["status"] == "FAIL"
        assert demo_pack_data["index"]["simulation_diff"]["changed_count"] == 1
        assert "Abaqus Agent Local Demo Pack" in demo_pack_data["index_markdown"]
        assert "Simulation Diff Sample" in demo_pack_data["index_markdown"]
        assert "Abaqus Agent Local Demo Pack" in demo_pack_data["index_html"]
        assert "offline-demo-gallery/index.html" in demo_pack_data["index_html"]
        assert "simulation-diff/diff.md" in demo_pack_data["index_html"]
        assert demo_pack_data["index_html_url"] == demo_pack_data["vault_urls"]["index.html"]
        assert demo_pack_data["vault_urls"]["offline-demo-gallery/index.html"].endswith(
            "/offline-demo-gallery/index.html"
        )
        assert demo_pack_data["vault_urls"][
            "offline-demo-gallery/explicit_impact/evidence.html"
        ].endswith("/offline-demo-gallery/explicit_impact/evidence.html")
        assert demo_pack_data["vault_urls"]["simulation-diff/diff.md"].endswith(
            "/simulation-diff/diff.md"
        )

        demo_pack_html = client.get(demo_pack_data["index_html_url"])
        assert demo_pack_html.status_code == 200
        assert demo_pack_html.headers["content-type"] == "text/html; charset=utf-8"
        assert "Offline Simulation QA evidence bundle" in demo_pack_html.text
        assert "Simulation Diff Sample" in demo_pack_html.text

        demo_pack_gallery_html = client.get(
            demo_pack_data["vault_urls"]["offline-demo-gallery/index.html"]
        )
        assert demo_pack_gallery_html.status_code == 200
        assert "text/html" in demo_pack_gallery_html.headers["content-type"]
        assert "Abaqus Agent Offline Demo Gallery" in demo_pack_gallery_html.text

        demo_pack_case_html = client.get(
            demo_pack_data["vault_urls"]["offline-demo-gallery/explicit_impact/evidence.html"]
        )
        assert demo_pack_case_html.status_code == 200
        assert "text/html" in demo_pack_case_html.headers["content-type"]
        assert "Offline Evidence Slice Report" in demo_pack_case_html.text

        unsafe_vault_path = client.get(
            f"/mcp/api/evidence/vault/{demo_pack_data['vault_id']}/../index.html"
        )
        assert unsafe_vault_path.status_code == 400

        demo_pack_zip = client.get(demo_pack_data["pack_zip_url"])
        assert demo_pack_zip.status_code == 200
        assert demo_pack_zip.headers["content-type"] == "application/zip"
        with zipfile.ZipFile(BytesIO(demo_pack_zip.content)) as pack:
            names = set(pack.namelist())
            assert {
                "index.json",
                "index.md",
                "index.html",
                "local-demo-pack-manifest.json",
                "offline-demo-gallery/index.json",
                "offline-demo-gallery/index.md",
                "offline-demo-gallery/index.html",
                "offline-demo-gallery/offline-demo-gallery.zip",
                "offline-demo-gallery/explicit_impact/evidence.json",
                "offline-demo-gallery/explicit_impact/evidence.md",
                "offline-demo-gallery/explicit_impact/evidence.html",
                "offline-demo-gallery/explicit_impact/capsule.json",
                "offline-demo-gallery/explicit_impact/explicit_impact-demo-bundle.zip",
                "solver-doctor/doctor.json",
                "solver-doctor/doctor.md",
                "simulation-diff/diff.json",
                "simulation-diff/diff.md",
            }.issubset(names)
            manifest = json.loads(pack.read("local-demo-pack-manifest.json"))
            assert manifest["workflow"] == "local-demo-pack"
            manifest_files = {entry["filename"]: entry for entry in manifest["files"]}
            assert "local-demo-pack-manifest.json" not in manifest_files
            assert manifest_files["index.html"]["size_bytes"] == len(pack.read("index.html"))
            assert manifest_files["index.html"]["sha256"] == hashlib.sha256(
                pack.read("index.html")
            ).hexdigest()
            assert len(manifest_files["offline-demo-gallery/explicit_impact/evidence.html"]["sha256"]) == 64
            assert len(
                [
                    name
                    for name in names
                    if name.startswith("offline-demo-gallery/")
                    and name.endswith("/evidence.html")
                ]
            ) == 4
            assert b"Simulation Diff Report" in pack.read("simulation-diff/diff.md")

        verified_demo_pack = client.post(
            f"/mcp/api/evidence/vault/{demo_pack_data['vault_id']}/verify-demo-pack"
        )
        assert verified_demo_pack.status_code == 200
        verified_demo_pack_data = verified_demo_pack.json()
        assert verified_demo_pack_data["workflow"] == "local-demo-pack-bundle-verify"
        assert verified_demo_pack_data["vault_id"] == demo_pack_data["vault_id"]
        assert verified_demo_pack_data["filename"] == "local-demo-pack.zip"
        assert verified_demo_pack_data["overall_status"] == "PASS"
        assert verified_demo_pack_data["checked_file_count"] == 31
        assert all(item["status"] == "PASS" for item in verified_demo_pack_data["files"])

        local_cli_smoke = client.post("/mcp/api/evidence/local-cli-smoke")
        assert local_cli_smoke.status_code == 200
        local_cli_smoke_data = local_cli_smoke.json()
        assert local_cli_smoke_data["workflow"] == "local-cli-smoke"
        assert local_cli_smoke_data["overall_status"] == "PASS"
        assert local_cli_smoke_data["real_env_verified"] is False
        assert local_cli_smoke_data["step_count"] == 11
        assert all(step["status"] == "PASS" for step in local_cli_smoke_data["steps"])
        assert local_cli_smoke_data["smoke_vault_id"].startswith("local-cli-smoke-")
        assert Path(local_cli_smoke_data["json_path"]).exists()
        assert Path(local_cli_smoke_data["markdown_path"]).exists()
        assert Path(local_cli_smoke_data["html_path"]).exists()
        assert Path(local_cli_smoke_data["zip_path"]).exists()
        assert "local_cli_smoke.zip" in local_cli_smoke_data["smoke_vault_files"]
        with zipfile.ZipFile(local_cli_smoke_data["zip_path"]) as smoke_bundle:
            assert set(smoke_bundle.namelist()) == {
                "copied-local-demo-pack.zip",
                "local_cli_smoke.html",
                "local_cli_smoke.json",
                "local_cli_smoke_manifest.json",
                "local_cli_smoke.md",
            }
        assert "Abaqus Agent Local CLI Smoke" in local_cli_smoke_data["report_markdown"]
        assert "Smoke Steps" in local_cli_smoke_data["report_html"]

        verified_smoke = client.post(
            f"/mcp/api/evidence/vault/{local_cli_smoke_data['smoke_vault_id']}/verify-smoke",
            json={"vault_root": local_cli_smoke_data["vault_root"]},
        )
        assert verified_smoke.status_code == 200
        verified_smoke_data = verified_smoke.json()
        assert verified_smoke_data["workflow"] == "local-cli-smoke-bundle-verify"
        assert verified_smoke_data["overall_status"] == "PASS"
        assert verified_smoke_data["vault_id"] == local_cli_smoke_data["smoke_vault_id"]
        assert verified_smoke_data["filename"] == "local_cli_smoke.zip"
        assert verified_smoke_data["checked_file_count"] == 4
        nested_verified_smoke_data = verified_smoke_data["copied_demo_pack_verification"]
        assert nested_verified_smoke_data["overall_status"] == "PASS"
        assert nested_verified_smoke_data["checked_file_count"] == 31

        doctor = client.post(
            "/mcp/api/doctor/diagnose",
            json={
                "job_name": "Bridge-Doctor",
                "msg_text": "***ERROR: EXCESSIVE DISTORTION OF ELEMENTS 123\n",
                "log_text": "Abaqus JOB Bridge-Doctor\n",
            },
        )
        assert doctor.status_code == 200
        doctor_data = doctor.json()
        assert doctor_data["job_name"] == "Bridge-Doctor"
        assert doctor_data["status"] == "FAILED"
        assert doctor_data["primary_category"] == "ELEMENT_DISTORTION"
        assert doctor_data["real_env_verified"] is False
        assert doctor_data["vault_id"].startswith("solver-doctor-")
        assert doctor_data["vault_urls"]["doctor.md"].endswith("/doctor.md")
        assert "Solver Doctor: Bridge-Doctor" in doctor_data["report_markdown"]
        assert doctor_data["report"]["findings"][0]["category"] == "ELEMENT_DISTORTION"

        doctor_vault_report = client.get(doctor_data["vault_urls"]["doctor.md"])
        assert doctor_vault_report.status_code == 200
        assert "Solver Doctor: Bridge-Doctor" in doctor_vault_report.text

        doctor_patterns = client.get(
            "/mcp/api/doctor/patterns",
            params={"severity": "ERROR"},
        )
        assert doctor_patterns.status_code == 200
        doctor_pattern_data = doctor_patterns.json()
        assert doctor_pattern_data["workflow"] == "solver-doctor-pattern-gallery"
        assert doctor_pattern_data["total"] >= 1
        assert all(
            pattern["severity"] == "ERROR"
            for pattern in doctor_pattern_data["patterns"]
        )

        bad_doctor = client.post(
            "/mcp/api/doctor/diagnose",
            json={"job_name": "Bridge/Bad", "msg_text": "***ERROR: x"},
        )
        assert bad_doctor.status_code == 400
        assert "job_name" in bad_doctor.json()["detail"]

        baseline = json.loads(
            (ROOT / "examples" / "kpis" / "cantilever_baseline.json").read_text(
                encoding="utf-8"
            )
        )["kpis"]
        candidate = json.loads(
            (ROOT / "examples" / "kpis" / "cantilever_candidate.json").read_text(
                encoding="utf-8"
            )
        )["kpis"]
        contracts = yaml.safe_load(
            (ROOT / "examples" / "contracts" / "cantilever.yaml").read_text(
                encoding="utf-8"
            )
        )["contracts"]
        offline_evidence = client.post(
            "/mcp/api/evidence/offline",
            json={
                "baseline_kpis": baseline,
                "candidate_kpis": candidate,
                "contracts": contracts,
                "run_id": "bridge-offline-cantilever",
                "input_path": str(ROOT / "cases" / "cantilever" / "spec.yaml"),
                "input_metadata": {"case": "cantilever"},
            },
        )
        assert offline_evidence.status_code == 200
        offline_data = offline_evidence.json()
        assert offline_data["overall_status"] == "PASS"
        assert offline_data["contracts"]["status"] == "PASS"
        assert offline_data["diff"]["status"] == "PASS"
        assert "Verdict Summary" in offline_data["report_markdown"]
        assert Path(offline_data["capsule"]["manifest_path"]).exists()
        assert offline_data["artifact_id"].startswith("bridge-offline-cantilever-")
        assert offline_data["vault_id"].startswith("offline-evidence-")
        assert offline_data["vault_urls"]["evidence.html"].endswith("/evidence.html")
        assert offline_data["vault_urls"]["bundle.zip"].endswith("/bundle.zip")
        assert offline_data["artifact_urls"]["evidence_json"].startswith(
            "/mcp/api/evidence/artifacts/"
        )
        assert offline_data["artifact_urls"]["report_html"].endswith("/evidence.html")

        bridge_report = client.get(offline_data["artifact_urls"]["report_markdown"])
        assert bridge_report.status_code == 200
        assert "Verdict Summary" in bridge_report.text

        bridge_html = client.get(offline_data["artifact_urls"]["report_html"])
        assert bridge_html.status_code == 200
        assert bridge_html.headers["content-type"] == "text/html; charset=utf-8"
        assert "Abaqus Agent Offline Evidence Slice Report" in bridge_html.text

        bridge_capsule = client.get(offline_data["artifact_urls"]["capsule_manifest"])
        assert bridge_capsule.status_code == 200
        assert bridge_capsule.json()["metadata"]["evidence_source"] == "supplied-kpi-json"

        bridge_bundle = client.get(offline_data["artifact_urls"]["bundle_zip"])
        assert bridge_bundle.status_code == 200
        assert bridge_bundle.headers["content-type"] == "application/zip"
        with zipfile.ZipFile(BytesIO(bridge_bundle.content)) as bundle:
            assert set(bundle.namelist()) == {
                "bundle_manifest.json",
                "capsule.json",
                "evidence.json",
                "evidence.html",
                "evidence.md",
            }
            bundle_manifest = json.loads(bundle.read("bundle_manifest.json"))
            assert bundle_manifest["artifact_id"] == offline_data["artifact_id"]
            assert bundle_manifest["run_id"] == "bridge-offline-cantilever"
            assert b"Offline Evidence Slice Report" in bundle.read("evidence.html")

        bridge_vault_bundle = client.get(offline_data["vault_urls"]["bundle.zip"])
        assert bridge_vault_bundle.status_code == 200
        assert bridge_vault_bundle.headers["content-type"] == "application/zip"

        recent = client.get("/mcp/api/evidence/artifacts")
        assert recent.status_code == 200
        recent_data = recent.json()
        assert recent_data["total"] == 1
        recent_item = recent_data["items"][0]
        assert recent_item["artifact_id"] == offline_data["artifact_id"]
        assert recent_item["run_id"] == "bridge-offline-cantilever"
        assert recent_item["overall_status"] == "PASS"
        assert recent_item["artifact_urls"]["bundle_zip"] == offline_data["artifact_urls"]["bundle_zip"]

        second_offline = client.post(
            "/mcp/api/evidence/offline",
            json={
                "baseline_kpis": baseline,
                "candidate_kpis": candidate,
                "contracts": contracts,
                "run_id": "bridge-offline-cantilever-second",
            },
        )
        assert second_offline.status_code == 200
        second_offline_data = second_offline.json()
        recent = client.get("/mcp/api/evidence/artifacts")
        assert recent.json()["items"][0]["artifact_id"] == second_offline_data["artifact_id"]

        memory_diff = client.post(
            "/mcp/api/case-memory/diff",
            json={
                "baseline_vault_id": offline_data["vault_id"],
                "candidate_vault_id": second_offline_data["vault_id"],
                "diff_id": "bridge-case-memory-diff",
            },
        )
        assert memory_diff.status_code == 200
        memory_diff_data = memory_diff.json()
        assert memory_diff_data["diff_id"] == "bridge-case-memory-diff"
        assert memory_diff_data["overall_status"] == "PASS"
        assert memory_diff_data["case_memory_diff"]["baseline_vault_id"] == offline_data["vault_id"]
        assert memory_diff_data["vault_id"].startswith("case-memory-diff-")
        assert memory_diff_data["vault_urls"]["diff.md"].startswith("/mcp/api/evidence/vault/")
        assert "Case Memory Sources" in memory_diff_data["report_markdown"]

        memory_diff_report = client.get(memory_diff_data["vault_urls"]["diff.md"])
        assert memory_diff_report.status_code == 200
        assert "Case Memory Sources" in memory_diff_report.text

        nested_memory_diff = client.post(
            "/mcp/api/case-memory/diff",
            json={
                "baseline_vault_id": demo_pack_data["vault_id"],
                "baseline_filename": "offline-demo-gallery/cantilever/evidence.json",
                "candidate_vault_id": demo_pack_data["vault_id"],
                "candidate_filename": "offline-demo-gallery/explicit_impact/evidence.json",
                "diff_id": "bridge-nested-case-memory-diff",
            },
        )
        assert nested_memory_diff.status_code == 200
        nested_memory_diff_data = nested_memory_diff.json()
        assert nested_memory_diff_data["diff_id"] == "bridge-nested-case-memory-diff"
        assert nested_memory_diff_data["case_memory_diff"]["baseline_source"]["filename"] == (
            "offline-demo-gallery/cantilever/evidence.json"
        )
        assert nested_memory_diff_data["case_memory_diff"]["candidate_source"]["filename"] == (
            "offline-demo-gallery/explicit_impact/evidence.json"
        )

        vault = client.get("/mcp/api/evidence/vault")
        assert vault.status_code == 200
        vault_data = vault.json()
        assert vault_data["total"] >= 5
        kinds = {item["kind"] for item in vault_data["items"]}
        assert {"demo-gallery", "offline-evidence", "solver-doctor", "local-demo-pack"}.issubset(kinds)

        filtered_vault = client.get(
            "/mcp/api/evidence/vault",
            params={"query": "doctor", "kind": "solver-doctor", "status": "FAILED"},
        )
        assert filtered_vault.status_code == 200
        filtered_vault_data = filtered_vault.json()
        assert filtered_vault_data["query"] == "doctor"
        assert filtered_vault_data["kind"] == "solver-doctor"
        assert filtered_vault_data["status"] == "failed"
        assert filtered_vault_data["total"] >= 1
        assert all(item["kind"] == "solver-doctor" for item in filtered_vault_data["items"])
        vault_detail_id = filtered_vault_data["items"][0]["vault_id"]
        vault_detail = client.get(f"/mcp/api/evidence/vault/{vault_detail_id}")
        assert vault_detail.status_code == 200
        vault_detail_data = vault_detail.json()
        assert vault_detail_data["vault_id"] == vault_detail_id
        assert vault_detail_data["vault_urls"]["doctor.md"].startswith("/mcp/api/evidence/vault/")

        missing_vault_detail = client.get("/mcp/api/evidence/vault/missing-vault")
        assert missing_vault_detail.status_code == 404

        passing_pack_vault = client.get(
            "/mcp/api/evidence/vault",
            params={"kind": "local-demo-pack", "status": "PASS"},
        )
        assert passing_pack_vault.status_code == 200
        passing_pack_vault_data = passing_pack_vault.json()
        assert passing_pack_vault_data["total"] >= 1
        assert all(item["kind"] == "local-demo-pack" for item in passing_pack_vault_data["items"])

        filename_vault = client.get(
            "/mcp/api/evidence/vault",
            params={"query": "local-demo-pack.zip"},
        )
        assert filename_vault.status_code == 200
        filename_vault_data = filename_vault.json()
        assert filename_vault_data["total"] >= 1
        assert any(item["kind"] == "local-demo-pack" for item in filename_vault_data["items"])

        case_memory = client.get("/mcp/api/case-memory", params={"query": "doctor"})
        assert case_memory.status_code == 200
        case_memory_data = case_memory.json()
        assert case_memory_data["workflow"] == "case-memory-vault-search"
        memory_items = case_memory_data["items"]
        assert any(item["kind"] == "solver-doctor" for item in memory_items)
        doctor_memory = next(item for item in memory_items if item["kind"] == "solver-doctor")
        assert doctor_memory["status"] == "FAILED"
        assert "doctor.md" in doctor_memory["files"]
        assert doctor_memory["vault_urls"]["doctor.md"].startswith("/mcp/api/evidence/vault/")

        invalid_offline = client.post(
            "/mcp/api/evidence/offline",
            json={
                "baseline_kpis": baseline,
                "candidate_kpis": candidate,
                "contracts": contracts,
                "run_id": "../bad",
            },
        )
        assert invalid_offline.status_code == 400
        assert "run_id" in invalid_offline.json()["detail"]

        premium_features = client.get("/mcp/api/premium/features")
        assert premium_features.status_code == 200
        premium_data = premium_features.json()
        assert set(premium_data["features"]) >= {"coupling", "parametric"}
        assert "capabilities" in premium_data

        empty_activation = client.post("/mcp/api/premium/activate")
        assert empty_activation.status_code == 200
        assert empty_activation.json() == {
            "valid": False,
            "error": "No license key provided",
        }

        dev_activation = client.post(
            "/mcp/api/premium/activate",
            params={"license_key": "dev-bridge-smoke"},
        )
        assert dev_activation.status_code == 200
        activated = dev_activation.json()
        assert activated["valid"] is True
        assert set(activated["features"]) == set(premium_data["features"])

        started = client.post(
            "/mcp/api/run/start",
            json={"spec_yaml": spec_yaml, "runner_cfg": {}},
        )
        assert started.status_code == 200
        run_id = started.json()["run_id"]

        events = []
        with client.stream("GET", f"/mcp/api/run/{run_id}/stream") as stream:
            assert stream.status_code == 200
            assert "text/event-stream" in stream.headers.get("content-type", "")
            for line in stream.iter_lines():
                if not line.startswith("data:"):
                    continue
                payload = json.loads(line[5:].strip())
                events.append(payload)
                if payload.get("event") == "done":
                    break

        assert any(event.get("run_id") == run_id for event in events)
        assert any(event.get("status") in {"RUNNING", "COMPLETED"} for event in events)
        assert events[-1] == {"event": "done"}
