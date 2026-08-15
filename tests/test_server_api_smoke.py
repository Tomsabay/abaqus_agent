"""FastAPI REST/SSE smoke tests for ``server.py``.

These tests exercise local API endpoints through FastAPI TestClient without
requiring an Abaqus executable or starting a real solver job.
"""

from __future__ import annotations

import hashlib
import json
import time
import zipfile
from io import BytesIO
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def server_app(monkeypatch, tmp_path):
    import server

    monkeypatch.setenv("ABAQUS_AGENT_EVIDENCE_VAULT", str(tmp_path / "vault"))
    original_runs = dict(server.RUNS)
    server.RUNS.clear()
    # EVIDENCE.clear() and not three statements: the artifact counter used to
    # be a module-level int here, so `server.EVIDENCE_ARTIFACT_SEQUENCE = 0`
    # reset it. It lives in the registry now, and that assignment would just
    # bind a name nothing reads -- a reset that silently stopped resetting.
    server.EVIDENCE.clear()
    try:
        yield server
    finally:
        server.RUNS.clear()
        server.RUNS.update(original_runs)
        server.EVIDENCE.clear()


def test_api_health_spec_and_benchmark_smoke(server_app) -> None:
    client = TestClient(server_app.app, raise_server_exceptions=False)
    req_a = server_app.StartRunRequest(spec_yaml="meta: test")
    req_b = server_app.StartRunRequest(spec_yaml="meta: test")
    req_a.runner_cfg["cpus"] = 2
    assert req_b.runner_cfg == {}

    health = client.get("/health")
    assert health.status_code == 200
    health_data = health.json()
    assert health_data["status"] == "ok"
    assert "abaqus_available" in health_data
    assert "cantilever" in health_data["cases"]

    generated = client.post(
        "/api/spec/generate",
        json={"text": "simple cantilever beam", "abaqus_release": "2024"},
    )
    assert generated.status_code == 200
    generated_data = generated.json()
    assert generated_data["valid"] is True
    assert "spec_yaml" in generated_data
    assert generated_data["spec_dict"]["meta"]["abaqus_release"] == "2024"

    spec_yaml = (ROOT / "cases" / "cantilever" / "spec.yaml").read_text(
        encoding="utf-8"
    )
    validation = client.post("/api/spec/validate", json={"spec_yaml": spec_yaml})
    assert validation.status_code == 200
    assert validation.json() == {"valid": True, "errors": []}

    benchmark = client.get("/api/benchmark")
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

    benchmark_run = client.post("/api/benchmark/run?dry_run=true")
    assert benchmark_run.status_code == 200
    benchmark_run_data = benchmark_run.json()
    assert benchmark_run_data["dry_run"] is True
    assert benchmark_run_data["run_id"].startswith("bench_")
    assert expected_cases.issubset(set(benchmark_run_data["cases"]))
    assert benchmark_run_data["run_id"] in server_app.RUNS


def test_api_sse_stream_for_completed_run(server_app) -> None:
    client = TestClient(server_app.app, raise_server_exceptions=False)
    run_id = "api_smoke_completed"
    server_app.RUNS[run_id] = {
        "run_id": run_id,
        "status": "COMPLETED",
        "spec": {},
        "runner_cfg": {},
        "stages": {"validate": {"status": "COMPLETED"}},
        "kpis": {"U_tip": -0.002},
        "started_at": time.time(),
        "finished_at": time.time(),
        "progress_pct": 100,
    }

    with client.stream("GET", f"/api/run/{run_id}/stream") as response:
        assert response.status_code == 200
        assert "text/event-stream" in response.headers.get("content-type", "")

        events = []
        for line in response.iter_lines():
            if line.startswith("data:"):
                events.append(json.loads(line[5:].strip()))
            if len(events) >= 2:
                break

    assert events[0]["run_id"] == run_id
    assert events[0]["status"] == "COMPLETED"
    assert events[0]["progress_pct"] == 100
    assert events[1] == {"event": "done"}

    spec_yaml = (ROOT / "cases" / "cantilever" / "spec.yaml").read_text(
        encoding="utf-8"
    )
    started = client.post(
        "/api/run/start",
        json={"spec_yaml": spec_yaml, "runner_cfg": {}},
    )
    assert started.status_code == 200
    started_data = started.json()
    started_run_id = started_data["run_id"]
    assert started_data["status"] == "PENDING"
    assert started_run_id in server_app.RUNS

    streamed = []
    with client.stream("GET", f"/api/run/{started_run_id}/stream") as response:
        assert response.status_code == 200
        assert "text/event-stream" in response.headers.get("content-type", "")
        for line in response.iter_lines():
            if not line.startswith("data:"):
                continue
            payload = json.loads(line[5:].strip())
            streamed.append(payload)
            if payload.get("event") == "done":
                break

    assert any(event.get("run_id") == started_run_id for event in streamed)
    assert any(event.get("status") in {"RUNNING", "COMPLETED"} for event in streamed)
    assert streamed[-1] == {"event": "done"}


def test_api_offline_evidence_slice_smoke(server_app) -> None:
    client = TestClient(server_app.app, raise_server_exceptions=False)
    examples = client.get("/api/evidence/examples")
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
    assert custom_summary["input_path"] == "examples/inp/custom_cantilever.inp"
    modal_example = client.get("/api/evidence/examples/modal")
    assert modal_example.status_code == 200
    modal_data = modal_example.json()
    assert modal_data["run_id"] == "modal-example-offline"
    assert modal_data["candidate_kpis"]["freq_2"] == 1000.0
    assert modal_data["contracts"][2]["type"] == "order"
    custom_example = client.get("/api/evidence/examples/custom_inp_deck")
    assert custom_example.status_code == 200
    custom_data = custom_example.json()
    assert custom_data["run_id"] == "custom-inp-deck-example-offline"
    assert custom_data["input_type"] == "custom_inp"
    assert custom_data["input_path"].endswith(".inp")
    missing_example = client.get("/api/evidence/examples/nope")
    assert missing_example.status_code == 404

    recipes = client.get("/api/kpi-recipes")
    assert recipes.status_code == 200
    recipe_data = recipes.json()
    assert recipe_data["workflow"] == "kpi-recipe-gallery"
    assert {
        "nodal_displacement",
        "field_max",
        "field_min",
        "reaction_force_max",
        "eigenfrequency",
        "derived_stress_concentration",
    }.issubset(set(recipe_data["supported_kpi_types"]))
    assert {"cantilever", "plate_hole", "modal", "explicit_impact"}.issubset(
        {item["case"] for item in recipe_data["items"]}
    )
    modal_recipes = client.get("/api/kpi-recipes", params={"case": "modal"})
    assert modal_recipes.status_code == 200
    assert modal_recipes.json()["items"][0]["id"] == "modal-first-three-frequencies"
    plate_recipe = client.get("/api/kpi-recipes/plate-hole-max-mises")
    assert plate_recipe.status_code == 200
    assert plate_recipe.json()["kpi_spec"][0]["type"] == "field_max"
    missing_recipe = client.get("/api/kpi-recipes/missing")
    assert missing_recipe.status_code == 404

    demo_gallery = client.post("/api/evidence/demo-gallery")
    assert demo_gallery.status_code == 200
    demo_gallery_data = demo_gallery.json()
    assert demo_gallery_data["overall_status"] == "PASS"
    assert demo_gallery_data["case_count"] == 4
    assert demo_gallery_data["artifact_id"].startswith("demo-gallery-")
    assert demo_gallery_data["artifact_urls"]["index_json"].startswith(
        "/api/evidence/demo-gallery/"
    )
    assert demo_gallery_data["artifact_urls"]["index_markdown"].endswith("/index.md")
    assert demo_gallery_data["artifact_urls"]["index_html"].endswith("/index.html")
    assert demo_gallery_data["artifact_urls"]["gallery_zip"].endswith(
        "/offline-demo-gallery.zip"
    )
    assert demo_gallery_data["vault_id"].startswith("demo-gallery-")
    assert demo_gallery_data["vault_urls"]["index.html"].endswith("/index.html")
    assert demo_gallery_data["vault_urls"]["offline-demo-gallery.zip"].endswith(
        "/offline-demo-gallery.zip"
    )
    assert demo_gallery_data["index"]["gallery_zip_path"].endswith(
        "offline-demo-gallery.zip"
    )
    assert "Offline Demo Gallery" in demo_gallery_data["index_markdown"]
    assert "Abaqus Agent Offline Demo Gallery" in demo_gallery_data["index_html"]
    assert demo_gallery_data["index_html_url"] == demo_gallery_data["vault_urls"]["index.html"]
    assert {item["case"] for item in demo_gallery_data["cases"]} == {
        "cantilever",
        "explicit_impact",
        "modal",
        "plate_hole",
    }

    demo_index = client.get(demo_gallery_data["artifact_urls"]["index_json"])
    assert demo_index.status_code == 200
    assert demo_index.json()["workflow"] == "offline-demo-gallery"

    demo_report = client.get(demo_gallery_data["artifact_urls"]["index_markdown"])
    assert demo_report.status_code == 200
    assert "text/markdown" in demo_report.headers["content-type"]
    assert "Real Abaqus execution: `not verified`" in demo_report.text

    demo_html = client.get(demo_gallery_data["artifact_urls"]["index_html"])
    assert demo_html.status_code == 200
    assert "text/html" in demo_html.headers["content-type"]
    assert "Abaqus Agent Offline Demo Gallery" in demo_html.text
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
            "modal/evidence.json",
            "modal/evidence.html",
            "modal/evidence.md",
            "modal/capsule.json",
            "modal/modal-demo-bundle.zip",
            "cases/modal/evidence.json",
            "cases/modal/evidence.html",
            "cases/modal/evidence.md",
            "cases/modal/capsule.json",
            "cases/modal/modal-demo-bundle.zip",
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

    demo_pack = client.post("/api/evidence/demo-pack")
    assert demo_pack.status_code == 200
    demo_pack_data = demo_pack.json()
    assert demo_pack_data["overall_status"] == "PASS"
    assert demo_pack_data["real_env_verified"] is False
    assert demo_pack_data["vault_id"].startswith("local-demo-pack-")
    assert demo_pack_data["pack_zip_url"] == demo_pack_data["vault_urls"]["local-demo-pack.zip"]
    assert demo_pack_data["index"]["workflow"] == "local-demo-pack"
    assert demo_pack_data["index"]["manifest_path"].endswith("local-demo-pack-manifest.json")
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
    assert demo_pack_data["vault_urls"]["offline-demo-gallery/plate_hole/evidence.html"].endswith(
        "/offline-demo-gallery/plate_hole/evidence.html"
    )
    assert demo_pack_data["vault_urls"]["solver-doctor/doctor.md"].endswith(
        "/solver-doctor/doctor.md"
    )
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
        demo_pack_data["vault_urls"]["offline-demo-gallery/plate_hole/evidence.html"]
    )
    assert demo_pack_case_html.status_code == 200
    assert "text/html" in demo_pack_case_html.headers["content-type"]
    assert "Offline Evidence Slice Report" in demo_pack_case_html.text

    demo_pack_doctor_report = client.get(
        demo_pack_data["vault_urls"]["solver-doctor/doctor.md"]
    )
    assert demo_pack_doctor_report.status_code == 200
    assert "Solver Doctor" in demo_pack_doctor_report.text

    unsafe_vault_path = client.get(
        f"/api/evidence/vault/{demo_pack_data['vault_id']}/../index.html"
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
            "offline-demo-gallery/modal/evidence.json",
            "offline-demo-gallery/modal/evidence.md",
            "offline-demo-gallery/modal/evidence.html",
            "offline-demo-gallery/modal/capsule.json",
            "offline-demo-gallery/modal/modal-demo-bundle.zip",
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
        assert len(manifest_files["offline-demo-gallery/offline-demo-gallery.zip"]["sha256"]) == 64
        assert len(
            [
                name
                for name in names
                if name.startswith("offline-demo-gallery/")
                and name.endswith("/evidence.html")
            ]
        ) == 4
        assert b"Simulation Diff Report" in pack.read("simulation-diff/diff.md")

    demo_pack_verify = client.post(
        f"/api/evidence/vault/{demo_pack_data['vault_id']}/verify-demo-pack"
    )
    assert demo_pack_verify.status_code == 200
    demo_pack_verify_data = demo_pack_verify.json()
    assert demo_pack_verify_data["workflow"] == "local-demo-pack-bundle-verify"
    assert demo_pack_verify_data["vault_id"] == demo_pack_data["vault_id"]
    assert demo_pack_verify_data["filename"] == "local-demo-pack.zip"
    assert demo_pack_verify_data["overall_status"] == "PASS"
    assert demo_pack_verify_data["checked_file_count"] == 31
    assert all(item["status"] == "PASS" for item in demo_pack_verify_data["files"])

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

    response = client.post(
        "/api/evidence/offline",
        json={
            "baseline_kpis": baseline,
            "candidate_kpis": candidate,
            "contracts": contracts,
            "run_id": "api-offline-cantilever",
            "input_path": str(ROOT / "cases" / "cantilever" / "spec.yaml"),
            "input_metadata": {"case": "cantilever"},
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["run_id"] == "api-offline-cantilever"
    assert data["overall_status"] == "PASS"
    assert data["real_env_verified"] is False
    assert data["contracts"]["status"] == "PASS"
    assert data["diff"]["status"] == "PASS"
    assert "Offline Evidence Slice" in data["report_markdown"]
    assert "does not invoke Abaqus" in data["report_markdown"]
    assert data["artifact_id"].startswith("api-offline-cantilever-")
    assert data["artifact_urls"]["evidence_json"].startswith("/api/evidence/artifacts/")
    assert data["artifact_urls"]["report_markdown"].endswith("/evidence.md")
    assert data["artifact_urls"]["report_html"].endswith("/evidence.html")
    assert data["artifact_urls"]["capsule_manifest"].endswith("/capsule.json")
    assert data["artifact_urls"]["bundle_zip"].endswith("/bundle.zip")
    assert data["vault_id"].startswith("offline-evidence-")
    assert data["vault_urls"]["evidence.html"].endswith("/evidence.html")
    assert data["vault_urls"]["bundle.zip"].endswith("/bundle.zip")
    assert Path(data["evidence_path"]).exists()
    assert Path(data["report_path"]).exists()
    assert Path(data["html_path"]).exists()
    assert Path(data["capsule"]["manifest_path"]).exists()
    assert data["capsule"]["input_count"] >= 5

    evidence_artifact = client.get(data["artifact_urls"]["evidence_json"])
    assert evidence_artifact.status_code == 200
    assert evidence_artifact.json()["overall_status"] == "PASS"

    report_artifact = client.get(data["artifact_urls"]["report_markdown"])
    assert report_artifact.status_code == 200
    assert "text/markdown" in report_artifact.headers["content-type"]
    assert "Verdict Summary" in report_artifact.text

    html_artifact = client.get(data["artifact_urls"]["report_html"])
    assert html_artifact.status_code == 200
    assert html_artifact.headers["content-type"] == "text/html; charset=utf-8"
    assert "Abaqus Agent Offline Evidence Slice Report" in html_artifact.text
    assert "does not invoke Abaqus" in html_artifact.text

    capsule_artifact = client.get(data["artifact_urls"]["capsule_manifest"])
    assert capsule_artifact.status_code == 200
    assert capsule_artifact.json()["metadata"]["evidence_level"] == "offline"

    bundle_artifact = client.get(data["artifact_urls"]["bundle_zip"])
    assert bundle_artifact.status_code == 200
    assert bundle_artifact.headers["content-type"] == "application/zip"
    with zipfile.ZipFile(BytesIO(bundle_artifact.content)) as bundle:
        assert set(bundle.namelist()) == {
            "bundle_manifest.json",
            "capsule.json",
            "evidence.json",
            "evidence.html",
            "evidence.md",
        }
        bundle_manifest = json.loads(bundle.read("bundle_manifest.json"))
        assert bundle_manifest["artifact_id"] == data["artifact_id"]
        assert bundle_manifest["run_id"] == "api-offline-cantilever"
        assert b"Verdict Summary" in bundle.read("evidence.md")
        assert b"Offline Evidence Slice Report" in bundle.read("evidence.html")

    vault_report = client.get(data["vault_urls"]["evidence.md"])
    assert vault_report.status_code == 200
    assert "Verdict Summary" in vault_report.text

    vault_html = client.get(data["vault_urls"]["evidence.html"])
    assert vault_html.status_code == 200
    assert "Offline Evidence Slice Report" in vault_html.text

    recent = client.get("/api/evidence/artifacts")
    assert recent.status_code == 200
    recent_data = recent.json()
    assert recent_data["total"] == 1
    recent_item = recent_data["items"][0]
    assert recent_item["artifact_id"] == data["artifact_id"]
    assert recent_item["run_id"] == "api-offline-cantilever"
    assert recent_item["overall_status"] == "PASS"
    assert recent_item["contracts"]["status"] == "PASS"
    assert recent_item["diff"]["status"] == "PASS"
    assert recent_item["artifact_urls"]["bundle_zip"] == data["artifact_urls"]["bundle_zip"]

    second = client.post(
        "/api/evidence/offline",
        json={
            "baseline_kpis": baseline,
            "candidate_kpis": candidate,
            "contracts": contracts,
            "run_id": "api-offline-cantilever-second",
        },
    )
    assert second.status_code == 200
    second_data = second.json()
    recent = client.get("/api/evidence/artifacts")
    assert recent.json()["items"][0]["artifact_id"] == second_data["artifact_id"]

    memory_diff = client.post(
        "/api/case-memory/diff",
        json={
            "baseline_vault_id": data["vault_id"],
            "candidate_vault_id": second_data["vault_id"],
            "diff_id": "api-case-memory-diff",
        },
    )
    assert memory_diff.status_code == 200
    memory_diff_data = memory_diff.json()
    assert memory_diff_data["diff_id"] == "api-case-memory-diff"
    assert memory_diff_data["overall_status"] == "PASS"
    assert memory_diff_data["real_env_verified"] is False
    assert memory_diff_data["case_memory_diff"]["baseline_vault_id"] == data["vault_id"]
    assert memory_diff_data["vault_id"].startswith("case-memory-diff-")
    assert memory_diff_data["vault_urls"]["diff.md"].endswith("/diff.md")
    assert "Case Memory Sources" in memory_diff_data["report_markdown"]

    memory_diff_report = client.get(memory_diff_data["vault_urls"]["diff.md"])
    assert memory_diff_report.status_code == 200
    assert "Case Memory Sources" in memory_diff_report.text

    nested_memory_diff = client.post(
        "/api/case-memory/diff",
        json={
            "baseline_vault_id": demo_pack_data["vault_id"],
            "baseline_filename": "offline-demo-gallery/cantilever/evidence.json",
            "candidate_vault_id": demo_pack_data["vault_id"],
            "candidate_filename": "offline-demo-gallery/plate_hole/evidence.json",
            "diff_id": "api-nested-case-memory-diff",
        },
    )
    assert nested_memory_diff.status_code == 200
    nested_memory_diff_data = nested_memory_diff.json()
    assert nested_memory_diff_data["diff_id"] == "api-nested-case-memory-diff"
    assert nested_memory_diff_data["case_memory_diff"]["baseline_source"]["filename"] == (
        "offline-demo-gallery/cantilever/evidence.json"
    )
    assert nested_memory_diff_data["case_memory_diff"]["candidate_source"]["filename"] == (
        "offline-demo-gallery/plate_hole/evidence.json"
    )

    unsafe_nested_memory_diff = client.post(
        "/api/case-memory/diff",
        json={
            "baseline_vault_id": demo_pack_data["vault_id"],
            "baseline_filename": "../evidence.json",
            "candidate_vault_id": demo_pack_data["vault_id"],
            "candidate_filename": "offline-demo-gallery/plate_hole/evidence.json",
            "diff_id": "api-unsafe-nested-case-memory-diff",
        },
    )
    assert unsafe_nested_memory_diff.status_code == 400

    missing_memory_diff = client.post(
        "/api/case-memory/diff",
        json={
            "baseline_vault_id": "missing",
            "candidate_vault_id": second_data["vault_id"],
            "diff_id": "missing-case-memory-diff",
        },
    )
    assert missing_memory_diff.status_code == 404

    missing_artifact = client.get("/api/evidence/artifacts/missing/evidence.json")
    assert missing_artifact.status_code == 404

    invalid = client.post(
        "/api/evidence/offline",
        json={
            "baseline_kpis": baseline,
            "candidate_kpis": candidate,
            "contracts": contracts,
            "run_id": "../bad",
        },
    )
    assert invalid.status_code == 400
    assert "run_id" in invalid.json()["detail"]

    vault = client.get("/api/evidence/vault")
    assert vault.status_code == 200
    vault_data = vault.json()
    assert vault_data["total"] >= 4
    kinds = {item["kind"] for item in vault_data["items"]}
    assert {"demo-gallery", "offline-evidence", "local-demo-pack"}.issubset(kinds)

    filtered_vault = client.get(
        "/api/evidence/vault",
        params={"query": "demo", "kind": "local-demo-pack", "status": "PASS"},
    )
    assert filtered_vault.status_code == 200
    filtered_vault_data = filtered_vault.json()
    assert filtered_vault_data["query"] == "demo"
    assert filtered_vault_data["kind"] == "local-demo-pack"
    assert filtered_vault_data["status"] == "pass"
    assert filtered_vault_data["total"] >= 1
    assert all(item["kind"] == "local-demo-pack" for item in filtered_vault_data["items"])
    assert all(item["summary"]["overall_status"] == "PASS" for item in filtered_vault_data["items"])
    vault_detail_id = filtered_vault_data["items"][0]["vault_id"]
    vault_detail = client.get(f"/api/evidence/vault/{vault_detail_id}")
    assert vault_detail.status_code == 200
    vault_detail_data = vault_detail.json()
    assert vault_detail_data["vault_id"] == vault_detail_id
    assert vault_detail_data["vault_urls"]["index.html"].startswith("/api/evidence/vault/")

    missing_vault_detail = client.get("/api/evidence/vault/missing-vault")
    assert missing_vault_detail.status_code == 404

    failing_diff_vault = client.get(
        "/api/evidence/vault",
        params={"kind": "case-memory-diff", "status": "FAIL"},
    )
    assert failing_diff_vault.status_code == 200
    failing_diff_vault_data = failing_diff_vault.json()
    assert failing_diff_vault_data["total"] >= 1
    assert all(item["kind"] == "case-memory-diff" for item in failing_diff_vault_data["items"])

    filename_vault = client.get("/api/evidence/vault", params={"query": "local-demo-pack.zip"})
    assert filename_vault.status_code == 200
    assert filename_vault.json()["total"] >= 1
    assert any(item["kind"] == "local-demo-pack" for item in filename_vault.json()["items"])

    case_memory = client.get("/api/case-memory", params={"query": "demo", "limit": 10})
    assert case_memory.status_code == 200
    case_memory_data = case_memory.json()
    assert case_memory_data["workflow"] == "case-memory-vault-search"
    memory_items = case_memory_data["items"]
    assert any(item["kind"] == "local-demo-pack" for item in memory_items)
    demo_memory = next(item for item in memory_items if item["kind"] == "local-demo-pack")
    assert demo_memory["status"] == "PASS"
    assert "index.html" in demo_memory["files"]
    assert demo_memory["vault_urls"]["index.html"].startswith("/api/evidence/vault/")

    local_pack_memory = client.get(
        "/api/case-memory",
        params={"kind": "local-demo-pack", "status": "PASS"},
    )
    assert local_pack_memory.status_code == 200
    assert local_pack_memory.json()["total"] >= 1

    local_cli_smoke = client.post("/api/evidence/local-cli-smoke")
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
    assert local_cli_smoke_data["smoke_vault_urls"]["local_cli_smoke.html"].startswith(
        f"/api/evidence/vault/{local_cli_smoke_data['smoke_vault_id']}/"
    )
    assert local_cli_smoke_data["smoke_vault_urls"]["local_cli_smoke.zip"].endswith(
        "/local_cli_smoke.zip"
    )
    assert "Abaqus Agent Local CLI Smoke" in local_cli_smoke_data["report_markdown"]
    assert "Smoke Steps" in local_cli_smoke_data["report_html"]

    smoke_html = client.get(
        local_cli_smoke_data["smoke_vault_urls"]["local_cli_smoke.html"]
    )
    assert smoke_html.status_code == 200
    assert "Abaqus Agent Local CLI Smoke" in smoke_html.text
    smoke_zip = client.get(
        local_cli_smoke_data["smoke_vault_urls"]["local_cli_smoke.zip"]
    )
    assert smoke_zip.status_code == 200
    assert smoke_zip.headers["content-type"] == "application/zip"
    with zipfile.ZipFile(BytesIO(smoke_zip.content)) as smoke_bundle:
        assert set(smoke_bundle.namelist()) == {
            "copied-local-demo-pack.zip",
            "local_cli_smoke.html",
            "local_cli_smoke.json",
            "local_cli_smoke_manifest.json",
            "local_cli_smoke.md",
        }

    smoke_verify = client.post(
        f"/api/evidence/vault/{local_cli_smoke_data['smoke_vault_id']}/verify-smoke"
    )
    assert smoke_verify.status_code == 200
    smoke_verify_data = smoke_verify.json()
    assert smoke_verify_data["workflow"] == "local-cli-smoke-bundle-verify"
    assert smoke_verify_data["overall_status"] == "PASS"
    assert smoke_verify_data["vault_id"] == local_cli_smoke_data["smoke_vault_id"]
    assert smoke_verify_data["filename"] == "local_cli_smoke.zip"
    assert smoke_verify_data["checked_file_count"] == 4
    nested_smoke_demo_pack = smoke_verify_data["copied_demo_pack_verification"]
    assert nested_smoke_demo_pack["overall_status"] == "PASS"
    assert nested_smoke_demo_pack["checked_file_count"] == 31

    smoke_vault = client.get(
        "/api/evidence/vault",
        params={"query": "local_cli_smoke.html", "kind": "local-cli-smoke", "status": "PASS"},
    )
    assert smoke_vault.status_code == 200
    smoke_vault_data = smoke_vault.json()
    assert smoke_vault_data["total"] == 1
    assert smoke_vault_data["items"][0]["vault_id"] == local_cli_smoke_data["smoke_vault_id"]

    smoke_memory = client.get(
        "/api/case-memory",
        params={"query": "local_cli_smoke.html", "kind": "local-cli-smoke", "status": "PASS"},
    )
    assert smoke_memory.status_code == 200
    assert smoke_memory.json()["total"] == 1


def test_api_simulation_diff_persists_vault_artifacts(server_app) -> None:
    client = TestClient(server_app.app, raise_server_exceptions=False)

    response = client.post(
        "/api/simdiff/kpis",
        json={
            "diff_id": "api-simdiff-cantilever",
            "baseline_kpis": {"U_tip": -2.0, "max_mises": 100.0},
            "candidate_kpis": {"U_tip": -2.4, "max_mises": 100.0, "new_only": 1.0},
            "tolerances": {"U_tip": {"rtol": 0.05}},
            "input_metadata": {"case": "cantilever"},
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["diff_id"] == "api-simdiff-cantilever"
    assert data["overall_status"] == "FAIL"
    assert data["real_env_verified"] is False
    assert data["diff"]["changed_count"] == 1
    assert data["diff"]["added_count"] == 1
    assert "Abaqus Agent Simulation Diff Report" in data["report_markdown"]
    assert "does not invoke Abaqus" in data["report_markdown"]
    assert Path(data["diff_path"]).exists()
    assert Path(data["report_path"]).exists()
    assert data["vault_id"].startswith("simulation-diff-")
    assert data["vault_urls"]["diff.md"].endswith("/diff.md")

    vault_report = client.get(data["vault_urls"]["diff.md"])
    assert vault_report.status_code == 200
    assert "Simulation Diff Report" in vault_report.text

    vault_json = client.get(data["vault_urls"]["diff.json"])
    assert vault_json.status_code == 200
    assert vault_json.json()["workflow"] == "simulation-diff-kpi"

    case_memory = client.get("/api/case-memory", params={"kind": "simulation-diff"})
    assert case_memory.status_code == 200
    assert case_memory.json()["items"][0]["status"] == "FAIL"

    invalid = client.post(
        "/api/simdiff/kpis",
        json={
            "diff_id": "../bad",
            "baseline_kpis": {},
            "candidate_kpis": {},
        },
    )
    assert invalid.status_code == 400
    assert "diff_id" in invalid.json()["detail"]


def test_api_solver_doctor_diagnoses_supplied_log_text(server_app) -> None:
    client = TestClient(server_app.app, raise_server_exceptions=False)

    patterns = client.get("/api/doctor/patterns", params={"category": "license"})
    assert patterns.status_code == 200
    pattern_data = patterns.json()
    assert pattern_data["workflow"] == "solver-doctor-pattern-gallery"
    assert pattern_data["real_env_verified"] is False
    assert pattern_data["total"] >= 1
    assert {pattern["category"] for pattern in pattern_data["patterns"]} == {"LICENSE"}
    assert any(category["category"] == "CONVERGENCE" for category in pattern_data["categories"])

    response = client.post(
        "/api/doctor/diagnose",
        json={
            "job_name": "Job-Doctor",
            "msg_text": "\n".join(
                [
                    "STEP     1  INCREMENT     5",
                    "***ERROR: THE SOLUTION HAS NOT CONVERGED",
                    "***WARNING: ZERO PIVOT DETECTED AT DOF 3 NODE 100",
                ]
            ),
            "dat_text": "***ERROR: License checkout failed\n",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["job_name"] == "Job-Doctor"
    assert data["status"] == "FAILED"
    assert data["primary_category"] in {"CONVERGENCE", "LICENSE", "RIGID_BODY_MOTION"}
    assert data["finding_count"] >= 2
    assert data["real_env_verified"] is False
    assert data["vault_id"].startswith("solver-doctor-")
    assert data["vault_urls"]["doctor.md"].endswith("/doctor.md")
    assert "Solver Doctor: Job-Doctor" in data["report_markdown"]
    categories = {finding["category"] for finding in data["report"]["findings"]}
    assert {"CONVERGENCE", "LICENSE"}.issubset(categories)

    vault_markdown = client.get(data["vault_urls"]["doctor.md"])
    assert vault_markdown.status_code == 200
    assert "Solver Doctor: Job-Doctor" in vault_markdown.text

    invalid = client.post(
        "/api/doctor/diagnose",
        json={"job_name": "../bad", "msg_text": "***ERROR: x"},
    )
    assert invalid.status_code == 400
    assert "job_name" in invalid.json()["detail"]


def test_api_feature_endpoints_smoke(server_app) -> None:
    client = TestClient(server_app.app, raise_server_exceptions=False)

    features = client.get("/api/features")
    assert features.status_code == 200
    features_data = features.json()
    assert "features" in features_data
    assert "capabilities" in features_data
    assert "coupling" in features_data["features"]
    assert features_data["features"]["coupling"] == {
        "display_name": "Multi-Physics Coupling"
    }
    # The licence gate is gone: no entitlement field may survive in the payload.
    assert "enabled" not in json.dumps(features_data)
    assert "licensed" not in json.dumps(features_data)

    # The activation endpoint is deleted outright, not stubbed to always-true.
    assert client.post("/api/features/activate").status_code == 404
    assert client.get("/api/premium/features").status_code == 404
