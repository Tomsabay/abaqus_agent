"""
Tests for mcp_server.py — MCP tools and resources.

Uses direct function calls (the MCP tools are just async functions)
rather than requiring a full MCP client/transport setup.
"""
import asyncio
import hashlib
import json
import sys
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


def _drain_pending_tasks() -> None:
    loop = asyncio.get_event_loop()
    pending = [task for task in asyncio.all_tasks(loop) if not task.done()]
    if not pending:
        return

    for task in pending:
        task.cancel()
    loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))


@pytest.fixture(autouse=True)
def clean_mcp_server_state():
    yield
    _drain_pending_tasks()

    from mcp_server import RUNS, _progress_queues

    RUNS.clear()
    _progress_queues.clear()


# ── Tool tests ────────────────────────────────────────────────────

class TestMCPTools:
    """Test MCP tool functions directly."""

    def test_health_check(self):
        from mcp_server import health_check
        result = asyncio.get_event_loop().run_until_complete(health_check())
        data = json.loads(result)
        assert data["status"] == "ok"
        assert "abaqus_available" in data
        assert "cases" in data
        assert data["transport"] == "mcp"

    def test_generate_spec(self):
        from mcp_server import generate_spec
        result = asyncio.get_event_loop().run_until_complete(
            generate_spec(text="简单悬臂梁分析", abaqus_release="2024")
        )
        data = json.loads(result)
        assert "spec_yaml" in data
        assert "spec_dict" in data
        assert "valid" in data
        assert data["spec_dict"]["meta"]["abaqus_release"] == "2024"

    def test_generate_spec_with_keywords(self):
        from mcp_server import generate_spec
        result = asyncio.get_event_loop().run_until_complete(
            generate_spec(text="带孔板 plate with hole", abaqus_release="2024")
        )
        data = json.loads(result)
        assert data["spec_dict"]["geometry"]["type"] == "plate_with_hole"

    def test_validate_spec_valid(self):
        from mcp_server import validate_spec_tool
        spec_path = Path(__file__).parent.parent / "cases" / "cantilever" / "spec.yaml"
        spec_yaml = spec_path.read_text()
        result = asyncio.get_event_loop().run_until_complete(
            validate_spec_tool(spec_yaml=spec_yaml)
        )
        data = json.loads(result)
        assert data["valid"] is True
        assert data["errors"] == []

    def test_validate_spec_invalid(self):
        from mcp_server import validate_spec_tool
        result = asyncio.get_event_loop().run_until_complete(
            validate_spec_tool(spec_yaml="meta:\n  model_name: Test\n")
        )
        data = json.loads(result)
        assert data["valid"] is False
        assert len(data["errors"]) > 0

    def test_validate_spec_bad_yaml(self):
        from mcp_server import validate_spec_tool
        result = asyncio.get_event_loop().run_until_complete(
            validate_spec_tool(spec_yaml="{{bad yaml::")
        )
        data = json.loads(result)
        assert data["valid"] is False
        assert any("YAML" in e or "parse" in e for e in data["errors"])

    def test_start_run(self):
        from mcp_server import RUNS, start_run
        spec_path = Path(__file__).parent.parent / "cases" / "cantilever" / "spec.yaml"
        spec_yaml = spec_path.read_text()

        result = asyncio.get_event_loop().run_until_complete(
            start_run(spec_yaml=spec_yaml)
        )
        data = json.loads(result)
        assert "run_id" in data
        assert data["status"] == "PENDING"
        assert data["run_id"] in RUNS

    def test_start_run_invalid_spec(self):
        from mcp_server import start_run
        result = asyncio.get_event_loop().run_until_complete(
            start_run(spec_yaml="meta:\n  model_name: Test\n")
        )
        data = json.loads(result)
        assert "error" in data

    def test_start_run_bad_yaml(self):
        from mcp_server import start_run
        result = asyncio.get_event_loop().run_until_complete(
            start_run(spec_yaml="{{bad")
        )
        data = json.loads(result)
        assert "error" in data

    def test_get_run_status_not_found(self):
        from mcp_server import get_run_status
        result = asyncio.get_event_loop().run_until_complete(
            get_run_status(run_id="nonexistent_id")
        )
        data = json.loads(result)
        assert "error" in data

    def test_get_run_status_existing(self):
        from mcp_server import get_run_status, start_run
        spec_path = Path(__file__).parent.parent / "cases" / "cantilever" / "spec.yaml"
        spec_yaml = spec_path.read_text()

        start_result = asyncio.get_event_loop().run_until_complete(
            start_run(spec_yaml=spec_yaml)
        )
        run_id = json.loads(start_result)["run_id"]

        result = asyncio.get_event_loop().run_until_complete(
            get_run_status(run_id=run_id)
        )
        data = json.loads(result)
        assert data["run_id"] == run_id
        assert "status" in data

    def test_environment_preflight_tool(self, monkeypatch):
        import mcp_server
        from mcp_server import environment_preflight_tool

        def fake_preflight(**kwargs):
            assert kwargs["abaqus_cmd"] == "abaqus"
            assert kwargs["timeout_seconds"] == 3.0
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

        monkeypatch.setattr(mcp_server, "run_environment_preflight", fake_preflight)

        result = asyncio.get_event_loop().run_until_complete(
            environment_preflight_tool(
                abaqus_cmd="abaqus",
                timeout_seconds=3.0,
                check_release=False,
                expected_release="2026",
                workdir="runs",
                runner_cfg_json='{"cpus": 2}',
            )
        )
        data = json.loads(result)
        assert data["status"] == "unknown"
        assert "Abaqus Environment Preflight" in data["markdown"]

    def test_offline_report_export_tool(self, tmp_path):
        from mcp_server import offline_report_export_tool

        (tmp_path / "capsule.json").write_text(
            json.dumps({
                "run_id": "mcp_offline_report",
                "inputs": {"model_name": "McpOffline"},
                "provenance": {"status": "COMPLETED", "abaqus_release": "2024"},
                "artifacts": {},
            }),
            encoding="utf-8",
        )
        (tmp_path / "result.json").write_text(
            json.dumps({
                "run_id": "mcp_offline_report",
                "status": "COMPLETED",
                "kpis": {"U_tip": -0.002},
            }),
            encoding="utf-8",
        )

        result = asyncio.get_event_loop().run_until_complete(
            offline_report_export_tool(str(tmp_path), template="client_summary")
        )
        data = json.loads(result)
        assert data["summary"]["run_id"] == "mcp_offline_report"
        assert data["offline_source"] == str(tmp_path)
        assert "Simulation QA Summary" in data["markdown"]

    def test_offline_report_pdf_export_tool(self, monkeypatch):
        import mcp_server
        from mcp_server import offline_report_pdf_export_tool

        monkeypatch.setattr(
            mcp_server,
            "build_offline_report_pdf",
            lambda source, template="standard": b"%PDF-1.4\nmcp",
        )

        result = asyncio.get_event_loop().run_until_complete(
            offline_report_pdf_export_tool("/tmp/run", template="client_summary")
        )
        data = json.loads(result)
        assert data["format"] == "pdf"
        assert data["bytes"] == len(b"%PDF-1.4\nmcp")
        assert data["content_base64"].startswith("JVBERi0xLjQK")

    def test_diagnose_logs_tool(self):
        from mcp_server import diagnose_logs_tool
        result = asyncio.get_event_loop().run_until_complete(
            diagnose_logs_tool(text="Node set FIXED_NODES has not been defined")
        )
        data = json.loads(result)
        assert data["matched"] is True
        assert data["matches"][0]["id"] == "missing_node_set"

    def test_simulation_diff_tool(self, tmp_path):
        from mcp_server import simulation_diff_tool
        baseline = tmp_path / "baseline.json"
        candidate = tmp_path / "candidate.json"
        baseline.write_text(json.dumps({"kpis": {"MISES": 100.0}}), encoding="utf-8")
        candidate.write_text(json.dumps({"kpis": {"MISES": 125.0}}), encoding="utf-8")

        result = asyncio.get_event_loop().run_until_complete(
            simulation_diff_tool(str(baseline), str(candidate), rtol=0.05, tolerances_json='{"MISES": 0.3}')
        )
        data = json.loads(result)
        assert data["passed"] is True
        assert data["summary"]["sections"]["kpis"]["PASS"] == 1
        assert "Simulation Diff Report" in data["markdown"]
        assert "Change Summary" in data["markdown"]

    def test_check_contracts_tool(self):
        from mcp_server import check_contracts_tool
        result = asyncio.get_event_loop().run_until_complete(
            check_contracts_tool(
                kpis_json=json.dumps({"U_tip": -0.002}),
                contracts_yaml="contracts:\n- name: down\n  type: direction\n  kpi: U_tip\n  direction: negative\n",
            )
        )
        data = json.loads(result)
        assert data["passed"] is True
        assert data["results"][0]["name"] == "down"

    def test_capsule_init_from_inp_tool(self, tmp_path):
        from mcp_server import capsule_init_from_inp_tool
        inp = tmp_path / "model.inp"
        out = tmp_path / "capsule"
        inp.write_text("*Heading\nmodel\n", encoding="utf-8")

        result = asyncio.get_event_loop().run_until_complete(
            capsule_init_from_inp_tool(str(inp), str(out))
        )
        data = json.loads(result)
        assert data["inputs"]["model_name"] == "model"
        assert (out / "capsule.json").exists()

    def test_case_memory_search_tool(self, tmp_path):
        from mcp_server import case_memory_search_tool
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        spec = {
            "meta": {"model_name": "McpMemoryModel", "abaqus_release": "2024"},
            "geometry": {"type": "custom_inp"},
            "material": {"name": "Steel"},
            "analysis": {"solver": "standard"},
        }
        (run_dir / "result.json").write_text(
            json.dumps({"run_id": "mcp_memory", "status": "COMPLETED", "spec": spec}),
            encoding="utf-8",
        )
        (run_dir / "capsule.json").write_text(
            json.dumps({
                "schema_version": "0.2.0-dev",
                "run_id": "mcp_memory",
                "created_at": "2026-06-02T10:00:00",
                "inputs": {"model_name": "McpMemoryModel"},
                "artifacts": {"Job.log": {"path": "Job.log", "sha256": "abc", "bytes": 10}},
                "provenance": {"status": "COMPLETED"},
                "contracts": {"passed": True, "results": [{"name": "tip_down", "passed": True}]},
            }),
            encoding="utf-8",
        )

        result = asyncio.get_event_loop().run_until_complete(
            case_memory_search_tool(
                json.dumps([str(tmp_path)]),
                query="McpMemoryModel",
                match_mode="all",
                geometry_type="custom",
                solver="standard",
                material_name="Steel",
                artifact="Job.log",
                contract="tip",
                contracts_passed="passed",
                sort_by="run_id",
                sort_order="asc",
                min_score=0.5,
            )
        )

        data = json.loads(result)
        assert data["matches"][0]["run_id"] == "mcp_memory"
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

    def test_run_benchmark(self):
        from mcp_server import run_benchmark_tool
        result = asyncio.get_event_loop().run_until_complete(
            run_benchmark_tool(dry_run=True)
        )
        data = json.loads(result)
        assert "run_id" in data
        assert "cases" in data
        assert data["dry_run"] is True
        assert len(data["cases"]) >= 4

    def test_get_features(self):
        from mcp_server import get_features
        result = asyncio.get_event_loop().run_until_complete(
            get_features()
        )
        data = json.loads(result)
        assert "features" in data
        assert "capabilities" in data
        assert len(data["features"]) >= 5
        # The licence gate is gone: no entitlement field may survive anywhere
        # in the payload.
        assert "enabled" not in json.dumps(data)
        assert "licensed" not in json.dumps(data)
        assert set(data["capabilities"]) == {
            "geometry_types", "step_types", "kpi_types", "hooks"
        }

    def test_get_offline_evidence_example_tool(self):
        from mcp_server import get_offline_evidence_example_tool
        result = asyncio.get_event_loop().run_until_complete(
            get_offline_evidence_example_tool(case_name="modal")
        )
        data = json.loads(result)
        assert data["run_id"] == "modal-example-offline"
        assert data["candidate_kpis"]["freq_2"] == 1000.0

        custom_result = asyncio.get_event_loop().run_until_complete(
            get_offline_evidence_example_tool(case_name="custom_inp_deck")
        )
        custom_data = json.loads(custom_result)
        assert custom_data["input_type"] == "custom_inp"
        assert custom_data["input_path"].endswith(".inp")

        missing = asyncio.get_event_loop().run_until_complete(
            get_offline_evidence_example_tool(case_name="missing")
        )
        assert "error" in json.loads(missing)

    def test_create_local_demo_pack_tool(self, tmp_path):
        from evidence.vault import create_vault_entry
        from mcp_server import (
            create_local_demo_pack_tool,
            verify_evidence_vault_demo_pack_bundle_tool,
            verify_local_demo_pack_bundle_tool,
        )
        result = asyncio.get_event_loop().run_until_complete(
            create_local_demo_pack_tool(out_dir=str(tmp_path))
        )
        data = json.loads(result)

        assert data["overall_status"] == "PASS"
        assert data["real_env_verified"] is False
        assert data["index"]["workflow"] == "local-demo-pack"
        assert data["index"]["manifest_path"].endswith("local-demo-pack-manifest.json")
        assert data["index"]["offline_demo_gallery"]["case_count"] == 4
        assert data["index"]["solver_doctor"]["status"] == "FAILED"
        assert data["index"]["simulation_diff"]["status"] == "FAIL"
        assert "Abaqus Agent Local Demo Pack" in data["index_markdown"]
        assert "Simulation Diff Sample" in data["index_markdown"]
        assert "Offline Simulation QA evidence bundle" in data["index_html"]
        assert "offline-demo-gallery/index.html" in data["index_html"]
        assert "simulation-diff/diff.md" in data["index_html"]
        assert Path(data["index_path"]).exists()
        assert Path(data["index_markdown_path"]).exists()
        assert Path(data["index_html_path"]).exists()
        assert Path(data["pack_zip_path"]).exists()
        with zipfile.ZipFile(data["pack_zip_path"]) as pack:
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
                "offline-demo-gallery/cantilever/evidence.json",
                "offline-demo-gallery/cantilever/evidence.md",
                "offline-demo-gallery/cantilever/evidence.html",
                "offline-demo-gallery/cantilever/capsule.json",
                "offline-demo-gallery/cantilever/cantilever-demo-bundle.zip",
                "solver-doctor/doctor.json",
                "solver-doctor/doctor.md",
                "simulation-diff/diff.json",
                "simulation-diff/diff.md",
            }.issubset(names)
            manifest = json.loads(pack.read("local-demo-pack-manifest.json"))
            assert manifest["workflow"] == "local-demo-pack"
            manifest_files = {entry["filename"]: entry for entry in manifest["files"]}
            assert "local-demo-pack-manifest.json" not in manifest_files
            assert manifest_files["index.md"]["size_bytes"] == len(pack.read("index.md"))
            assert manifest_files["index.md"]["sha256"] == hashlib.sha256(
                pack.read("index.md")
            ).hexdigest()
            assert len(manifest_files["solver-doctor/doctor.json"]["sha256"]) == 64
            assert len(
                [
                    name
                    for name in names
                    if name.startswith("offline-demo-gallery/")
                    and name.endswith("/evidence.html")
                ]
            ) == 4
            assert b"Simulation Diff Report" in pack.read("simulation-diff/diff.md")

        verify_result = asyncio.get_event_loop().run_until_complete(
            verify_local_demo_pack_bundle_tool(zip_path=data["pack_zip_path"])
        )
        verify_data = json.loads(verify_result)
        assert verify_data["workflow"] == "local-demo-pack-bundle-verify"
        assert verify_data["bundle_workflow"] == "local-demo-pack"
        assert verify_data["overall_status"] == "PASS"
        assert verify_data["checked_file_count"] == 31
        assert all(item["status"] == "PASS" for item in verify_data["files"])

        vault_root = tmp_path / "vault"
        record = create_vault_entry(
            kind="local-demo-pack",
            title="MCP Demo Pack Verify",
            files={
                "local-demo-pack.zip": Path(data["pack_zip_path"]),
                "local-demo-pack-manifest.json": Path(data["index"]["manifest_path"]),
            },
            summary={"overall_status": "PASS"},
            root=vault_root,
        )
        vault_verify_result = asyncio.get_event_loop().run_until_complete(
            verify_evidence_vault_demo_pack_bundle_tool(
                vault_id=record["vault_id"],
                vault_root=str(vault_root),
            )
        )
        vault_verify_data = json.loads(vault_verify_result)
        assert vault_verify_data["vault_id"] == record["vault_id"]
        assert vault_verify_data["filename"] == "local-demo-pack.zip"
        assert vault_verify_data["vault_root"] == str(vault_root)
        assert vault_verify_data["overall_status"] == "PASS"
        assert vault_verify_data["checked_file_count"] == 31

    def test_run_local_cli_smoke_tool(self, tmp_path):
        from mcp_server import (
            run_local_cli_smoke_tool,
            verify_evidence_vault_smoke_bundle_tool,
            verify_local_cli_smoke_bundle_tool,
        )
        result = asyncio.get_event_loop().run_until_complete(
            run_local_cli_smoke_tool(out_dir=str(tmp_path))
        )
        data = json.loads(result)

        assert data["workflow"] == "local-cli-smoke"
        assert data["overall_status"] == "PASS"
        assert data["real_env_verified"] is False
        assert data["step_count"] == 11
        assert all(step["status"] == "PASS" for step in data["steps"])
        assert data["smoke_vault_id"].startswith("local-cli-smoke-")
        assert Path(data["json_path"]).exists()
        assert Path(data["markdown_path"]).exists()
        assert Path(data["html_path"]).exists()
        assert Path(data["zip_path"]).exists()
        assert "local_cli_smoke.zip" in data["smoke_vault_files"]
        with zipfile.ZipFile(data["zip_path"]) as bundle:
            assert set(bundle.namelist()) == {
                "copied-local-demo-pack.zip",
                "local_cli_smoke.html",
                "local_cli_smoke.json",
                "local_cli_smoke_manifest.json",
                "local_cli_smoke.md",
            }
        assert "Abaqus Agent Local CLI Smoke" in data["report_markdown"]
        assert "Smoke Steps" in data["report_html"]

        verify_result = asyncio.get_event_loop().run_until_complete(
            verify_local_cli_smoke_bundle_tool(zip_path=data["zip_path"])
        )
        verify_data = json.loads(verify_result)
        assert verify_data["workflow"] == "local-cli-smoke-bundle-verify"
        assert verify_data["overall_status"] == "PASS"
        assert verify_data["checked_file_count"] == 4
        assert all(item["status"] == "PASS" for item in verify_data["files"])
        nested_verify_data = verify_data["copied_demo_pack_verification"]
        assert nested_verify_data["overall_status"] == "PASS"
        assert nested_verify_data["checked_file_count"] == 31

        vault_verify_result = asyncio.get_event_loop().run_until_complete(
            verify_evidence_vault_smoke_bundle_tool(
                vault_id=data["smoke_vault_id"],
                vault_root=data["vault_root"],
            )
        )
        vault_verify_data = json.loads(vault_verify_result)
        assert vault_verify_data["vault_id"] == data["smoke_vault_id"]
        assert vault_verify_data["filename"] == "local_cli_smoke.zip"
        assert vault_verify_data["overall_status"] == "PASS"
        assert vault_verify_data["checked_file_count"] == 4
        nested_vault_verify_data = vault_verify_data["copied_demo_pack_verification"]
        assert nested_vault_verify_data["overall_status"] == "PASS"
        assert nested_vault_verify_data["checked_file_count"] == 31

    def test_search_case_memory_tool(self, tmp_path, monkeypatch):
        from evidence.vault import create_vault_entry
        from mcp_server import search_case_memory_tool

        monkeypatch.setenv("ABAQUS_AGENT_EVIDENCE_VAULT", str(tmp_path / "vault"))
        report = tmp_path / "doctor.md"
        report.write_text("# Solver Doctor: Memory Case\n", encoding="utf-8")
        create_vault_entry(
            kind="solver-doctor",
            title="Memory Case",
            files={"doctor.md": report},
            summary={"status": "FAILED", "primary_category": "LICENSE"},
        )

        result = asyncio.get_event_loop().run_until_complete(
            search_case_memory_tool(query="license", kind="solver-doctor")
        )
        data = json.loads(result)

        assert data["workflow"] == "case-memory-vault-search"
        assert data["total"] == 1
        item = data["items"][0]
        assert item["kind"] == "solver-doctor"
        assert item["title"] == "Memory Case"
        assert item["status"] == "FAILED"
        assert item["vault_urls"]["doctor.md"].startswith("case-memory://vault/")

    def test_evidence_vault_tools(self, tmp_path, monkeypatch):
        from evidence.vault import create_vault_entry
        from mcp_server import (
            copy_evidence_vault_file_tool,
            get_evidence_vault_record_tool,
            read_evidence_vault_file_tool,
            search_evidence_vault_tool,
        )

        monkeypatch.setenv("ABAQUS_AGENT_EVIDENCE_VAULT", str(tmp_path / "vault"))
        report = tmp_path / "index.md"
        report.write_text("# Demo Pack\n", encoding="utf-8")
        record = create_vault_entry(
            kind="local-demo-pack",
            title="Vault Demo Pack",
            files={"index.md": report, "local-demo-pack.zip": report},
            summary={"overall_status": "PASS", "case_count": 4},
        )

        search_result = asyncio.get_event_loop().run_until_complete(
            search_evidence_vault_tool(
                query="local-demo-pack.zip",
                kind="local-demo-pack",
                status="PASS",
            )
        )
        search_data = json.loads(search_result)
        assert search_data["query"] == "local-demo-pack.zip"
        assert search_data["kind"] == "local-demo-pack"
        assert search_data["status"] == "pass"
        assert search_data["total"] == 1
        assert search_data["items"][0]["vault_urls"]["index.md"].startswith(
            "evidence-vault://entries/"
        )

        detail_result = asyncio.get_event_loop().run_until_complete(
            get_evidence_vault_record_tool(vault_id=record["vault_id"])
        )
        detail_data = json.loads(detail_result)
        assert detail_data["vault_id"] == record["vault_id"]
        assert detail_data["summary"]["overall_status"] == "PASS"
        assert detail_data["vault_urls"]["local-demo-pack.zip"].startswith(
            "evidence-vault://entries/"
        )

        missing_result = asyncio.get_event_loop().run_until_complete(
            get_evidence_vault_record_tool(vault_id="missing-vault")
        )
        assert "error" in json.loads(missing_result)

        read_result = asyncio.get_event_loop().run_until_complete(
            read_evidence_vault_file_tool(
                vault_id=record["vault_id"],
                filename="index.md",
                max_chars=6,
            )
        )
        read_data = json.loads(read_result)
        assert read_data["vault_url"].startswith("evidence-vault://entries/")
        assert read_data["truncated"] is True
        assert read_data["content"] == "# Demo"

        zip_result = asyncio.get_event_loop().run_until_complete(
            read_evidence_vault_file_tool(
                vault_id=record["vault_id"],
                filename="local-demo-pack.zip",
            )
        )
        zip_data = json.loads(zip_result)
        assert "Unsupported text vault file type" in zip_data["error"]

        copied_zip = tmp_path / "exports" / "local-demo-pack.zip"
        copy_result = asyncio.get_event_loop().run_until_complete(
            copy_evidence_vault_file_tool(
                vault_id=record["vault_id"],
                filename="local-demo-pack.zip",
                out_path=str(copied_zip),
            )
        )
        copy_data = json.loads(copy_result)
        assert copy_data["vault_id"] == record["vault_id"]
        assert copy_data["filename"] == "local-demo-pack.zip"
        assert copy_data["output_path"] == str(copied_zip)
        assert copied_zip.read_text(encoding="utf-8") == "# Demo Pack\n"

        unsafe_result = asyncio.get_event_loop().run_until_complete(
            read_evidence_vault_file_tool(
                vault_id=record["vault_id"],
                filename="../index.md",
            )
        )
        assert "error" in json.loads(unsafe_result)

    def test_diff_case_memory_tool(self, tmp_path, monkeypatch):
        from evidence.vault import create_vault_entry
        from mcp_server import diff_case_memory_tool

        vault_root = tmp_path / "vault"
        monkeypatch.setenv("ABAQUS_AGENT_EVIDENCE_VAULT", str(vault_root))
        first = tmp_path / "first.json"
        second = tmp_path / "second.json"
        first.write_text(
            json.dumps(
                {
                    "workflow": "offline-evidence-slice",
                    "run_id": "first",
                    "overall_status": "PASS",
                    "candidate_kpis": {"U_tip": -2.0},
                }
            ),
            encoding="utf-8",
        )
        second.write_text(
            json.dumps(
                {
                    "workflow": "offline-evidence-slice",
                    "run_id": "second",
                    "overall_status": "PASS",
                    "candidate_kpis": {"U_tip": -2.1},
                }
            ),
            encoding="utf-8",
        )
        first_record = create_vault_entry(
            kind="offline-evidence",
            title="first",
            files={"evidence.json": first},
            root=vault_root,
        )
        second_record = create_vault_entry(
            kind="offline-evidence",
            title="second",
            files={"evidence.json": second},
            root=vault_root,
        )
        nested_first_record = create_vault_entry(
            kind="offline-evidence",
            title="nested-first",
            files={"gallery/cantilever/evidence.json": first},
            root=vault_root,
        )
        nested_second_record = create_vault_entry(
            kind="offline-evidence",
            title="nested-second",
            files={"gallery/plate_hole/evidence.json": second},
            root=vault_root,
        )

        result = asyncio.get_event_loop().run_until_complete(
            diff_case_memory_tool(
                baseline_vault_id=first_record["vault_id"],
                candidate_vault_id=second_record["vault_id"],
                diff_id="mcp-case-memory-diff",
            )
        )
        data = json.loads(result)

        assert data["diff_id"] == "mcp-case-memory-diff"
        assert data["overall_status"] == "FAIL"
        assert data["vault_id"].startswith("case-memory-diff-")
        assert data["case_memory_diff"]["candidate_source"]["run_id"] == "second"
        assert "Case Memory Sources" in data["report_markdown"]

        nested_result = asyncio.get_event_loop().run_until_complete(
            diff_case_memory_tool(
                baseline_vault_id=nested_first_record["vault_id"],
                baseline_filename="gallery/cantilever/evidence.json",
                candidate_vault_id=nested_second_record["vault_id"],
                candidate_filename="gallery/plate_hole/evidence.json",
                diff_id="mcp-nested-case-memory-diff",
            )
        )
        nested_data = json.loads(nested_result)

        assert nested_data["diff_id"] == "mcp-nested-case-memory-diff"
        assert nested_data["overall_status"] == "FAIL"
        assert nested_data["case_memory_diff"]["baseline_source"]["filename"] == (
            "gallery/cantilever/evidence.json"
        )
        assert nested_data["case_memory_diff"]["candidate_source"]["filename"] == (
            "gallery/plate_hole/evidence.json"
        )

    def test_get_kpi_recipe_tool(self):
        from mcp_server import get_kpi_recipe_tool

        result = asyncio.get_event_loop().run_until_complete(
            get_kpi_recipe_tool(recipe_id="plate-hole-stress-concentration")
        )
        data = json.loads(result)
        assert data["id"] == "plate-hole-stress-concentration"
        assert data["kpi_spec"][0]["type"] == "derived_stress_concentration"
        assert data["real_env_verified"] is False

        missing = asyncio.get_event_loop().run_until_complete(
            get_kpi_recipe_tool(recipe_id="missing")
        )
        assert "error" in json.loads(missing)

    def test_run_simulation_diff_tool(self):
        from mcp_server import run_simulation_diff_tool

        result = asyncio.get_event_loop().run_until_complete(
            run_simulation_diff_tool(
                baseline_kpis={"U_tip": -2.0, "max_mises": 100.0},
                candidate_kpis={"U_tip": -2.4, "max_mises": 100.0},
                tolerances={"U_tip": {"rtol": 0.05}},
                diff_id="mcp-simdiff",
                input_metadata='{"case":"cantilever"}',
            )
        )
        data = json.loads(result)

        assert data["diff_id"] == "mcp-simdiff"
        assert data["overall_status"] == "FAIL"
        assert data["diff"]["changed_count"] == 1
        assert data["real_env_verified"] is False
        assert "Simulation Diff Report" in data["report_markdown"]
        assert Path(data["diff_path"]).exists()
        assert Path(data["report_path"]).exists()

        bad = asyncio.get_event_loop().run_until_complete(
            run_simulation_diff_tool(
                baseline_kpis={},
                candidate_kpis={},
                diff_id="../bad",
            )
        )
        assert "diff_id" in json.loads(bad)["error"]

    def test_diagnose_solver_logs_tool(self):
        from mcp_server import diagnose_solver_logs_tool
        result = asyncio.get_event_loop().run_until_complete(
            diagnose_solver_logs_tool(
                job_name="MCP-Doctor",
                msg_text="***ERROR: EXCESSIVE DISTORTION OF ELEMENTS 123\n",
                log_text="Abaqus JOB MCP-Doctor\n",
            )
        )
        data = json.loads(result)
        assert data["status"] == "FAILED"
        assert data["primary_category"] == "ELEMENT_DISTORTION"
        assert data["real_env_verified"] is False
        assert "Solver Doctor: MCP-Doctor" in data["report_markdown"]

        bad = asyncio.get_event_loop().run_until_complete(
            diagnose_solver_logs_tool(job_name="../bad", msg_text="***ERROR: x")
        )
        assert "job_name" in json.loads(bad)["error"]

    def test_get_solver_doctor_patterns_tool(self):
        from mcp_server import get_solver_doctor_patterns_tool

        result = asyncio.get_event_loop().run_until_complete(
            get_solver_doctor_patterns_tool(category="license")
        )
        data = json.loads(result)

        assert data["workflow"] == "solver-doctor-pattern-gallery"
        assert data["total"] >= 1
        assert {pattern["category"] for pattern in data["patterns"]} == {"LICENSE"}
        assert data["real_env_verified"] is False

    def test_diagnose_cae_error_tool(self):
        from mcp_server import diagnose_cae_error_tool

        result = asyncio.get_event_loop().run_until_complete(
            diagnose_cae_error_tool(
                "IOError: D:/x/Copilot_Cantilever_Job.cae: Permission denied (.lck)"
            )
        )
        data = json.loads(result)
        assert data["matched"] is True
        assert data["pattern_id"] == "stale_lock_or_readonly_cae"
        assert data["title"] == "模型数据库被锁定或无法写入"

        empty = asyncio.get_event_loop().run_until_complete(diagnose_cae_error_tool("  "))
        assert "error" in json.loads(empty)


# ── Resource tests ────────────────────────────────────────────────

class TestMCPResources:
    """Test MCP resource functions directly."""

    def test_benchmark_cases_resource(self):
        from mcp_server import get_benchmark_cases
        result = asyncio.get_event_loop().run_until_complete(
            get_benchmark_cases()
        )
        data = json.loads(result)
        assert "cases" in data
        assert "total" in data
        assert data["total"] >= 4
        case_names = [c["name"] for c in data["cases"]]
        assert "cantilever" in case_names
        assert "plate_hole" in case_names

    def test_features_resource(self):
        from mcp_server import get_features_resource
        result = asyncio.get_event_loop().run_until_complete(
            get_features_resource()
        )
        data = json.loads(result)
        assert "features" in data
        assert "capabilities" in data
        assert "enabled" not in json.dumps(data)

    def test_offline_evidence_examples_resource(self):
        from mcp_server import get_offline_evidence_examples_resource
        result = asyncio.get_event_loop().run_until_complete(
            get_offline_evidence_examples_resource()
        )
        data = json.loads(result)
        assert {
            "cantilever",
            "custom_inp_deck",
            "explicit_impact",
            "modal",
            "plate_hole",
        }.issubset({case["case"] for case in data["cases"]})

    def test_kpi_recipes_resource(self):
        from mcp_server import get_kpi_recipes_resource

        result = asyncio.get_event_loop().run_until_complete(get_kpi_recipes_resource())
        data = json.loads(result)

        assert data["workflow"] == "kpi-recipe-gallery"
        assert "field_max" in data["supported_kpi_types"]
        assert {"cantilever", "plate_hole", "modal", "explicit_impact"}.issubset(
            {item["case"] for item in data["items"]}
        )

    def test_simulation_diff_example_resource(self):
        from mcp_server import get_simulation_diff_example_resource

        result = asyncio.get_event_loop().run_until_complete(
            get_simulation_diff_example_resource()
        )
        data = json.loads(result)

        assert data["diff_id"] == "cantilever-simdiff-example"
        assert "U_tip_y" in data["baseline_kpis"]
        assert data["tolerances"]["U_tip_y"]["rtol"] == 0.05
        assert data["real_env_verified"] is False

    def test_solver_doctor_patterns_resource(self):
        from mcp_server import get_solver_doctor_patterns_resource

        result = asyncio.get_event_loop().run_until_complete(
            get_solver_doctor_patterns_resource()
        )
        data = json.loads(result)

        assert data["workflow"] == "solver-doctor-pattern-gallery"
        assert data["total"] >= 20
        assert any(pattern["category"] == "CONVERGENCE" for pattern in data["patterns"])

    def test_case_memory_resource(self, tmp_path, monkeypatch):
        from evidence.vault import create_vault_entry
        from mcp_server import get_case_memory_resource

        monkeypatch.setenv("ABAQUS_AGENT_EVIDENCE_VAULT", str(tmp_path / "vault"))
        index = tmp_path / "index.md"
        index.write_text("# Demo Gallery\n", encoding="utf-8")
        create_vault_entry(
            kind="demo-gallery",
            title="Gallery Memory",
            files={"index.md": index},
            summary={"overall_status": "PASS", "case_count": 4},
        )

        result = asyncio.get_event_loop().run_until_complete(get_case_memory_resource())
        data = json.loads(result)

        assert data["workflow"] == "case-memory-vault-search"
        assert data["total"] == 1
        assert data["items"][0]["kind"] == "demo-gallery"

    def test_evidence_vault_resource(self, tmp_path, monkeypatch):
        from evidence.vault import create_vault_entry
        from mcp_server import get_evidence_vault_resource

        monkeypatch.setenv("ABAQUS_AGENT_EVIDENCE_VAULT", str(tmp_path / "vault"))
        index = tmp_path / "index.md"
        index.write_text("# Demo Pack\n", encoding="utf-8")
        create_vault_entry(
            kind="local-demo-pack",
            title="Vault Resource Pack",
            files={"index.md": index},
            summary={"overall_status": "PASS"},
        )

        result = asyncio.get_event_loop().run_until_complete(get_evidence_vault_resource())
        data = json.loads(result)

        assert data["total"] == 1
        assert data["items"][0]["kind"] == "local-demo-pack"
        assert data["items"][0]["vault_urls"]["index.md"].startswith(
            "evidence-vault://entries/"
        )


# ── Progress notification tests ───────────────────────────────────

class TestMCPProgress:
    """Test the progress notification mechanism."""

    def test_subscribe_unsubscribe(self):
        from mcp_server import subscribe_progress, unsubscribe_progress
        q = subscribe_progress("test_run")
        assert q is not None
        unsubscribe_progress("test_run", q)

    def test_broadcast_progress(self):
        from mcp_server import _broadcast_progress, subscribe_progress, unsubscribe_progress
        q = subscribe_progress("test_broadcast")
        asyncio.get_event_loop().run_until_complete(
            _broadcast_progress("test_broadcast", {"status": "RUNNING", "progress_pct": 50})
        )
        msg = asyncio.get_event_loop().run_until_complete(
            asyncio.wait_for(q.get(), timeout=1.0)
        )
        assert msg["status"] == "RUNNING"
        assert msg["progress_pct"] == 50
        unsubscribe_progress("test_broadcast", q)

    def test_full_run_with_progress(self):
        """Start a run, collect progress events, verify completion."""
        from mcp_server import (
            start_run,
            subscribe_progress,
            unsubscribe_progress,
        )

        spec_path = Path(__file__).parent.parent / "cases" / "cantilever" / "spec.yaml"
        spec_yaml = spec_path.read_text()

        # Get the run_id that will be generated
        from core.helpers import make_run_id
        run_id = make_run_id(spec_yaml)

        # Subscribe before starting
        q = subscribe_progress(run_id)

        # Start the run
        loop = asyncio.get_event_loop()
        start_result = loop.run_until_complete(start_run(spec_yaml=spec_yaml))
        data = json.loads(start_result)
        assert data["run_id"] == run_id

        # Collect progress events until done
        events = []
        try:
            while True:
                evt = loop.run_until_complete(
                    asyncio.wait_for(q.get(), timeout=30.0)
                )
                events.append(evt)
                if evt.get("status") in ("COMPLETED", "FAILED"):
                    break
        except asyncio.TimeoutError:
            pass

        unsubscribe_progress(run_id, q)

        # Verify we got progress updates
        assert len(events) > 0
        # Final event should be COMPLETED
        assert events[-1]["status"] == "COMPLETED"
