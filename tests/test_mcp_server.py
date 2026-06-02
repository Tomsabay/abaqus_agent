"""
Tests for mcp_server.py — MCP tools and resources.

Uses direct function calls (the MCP tools are just async functions)
rather than requiring a full MCP client/transport setup.
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))



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

    def test_get_premium_features(self):
        from mcp_server import get_premium_features
        result = asyncio.get_event_loop().run_until_complete(
            get_premium_features()
        )
        data = json.loads(result)
        assert "features" in data
        # Premium module should be importable
        assert len(data["features"]) >= 5

    def test_activate_premium_dev_key(self):
        from mcp_server import activate_premium
        result = asyncio.get_event_loop().run_until_complete(
            activate_premium(license_key="dev-test-key")
        )
        data = json.loads(result)
        assert data["valid"] is True
        assert len(data["features"]) >= 5

        # Reset after test
        from premium.licensing import feature_gate
        feature_gate.reset()

    def test_activate_premium_empty_key(self):
        from mcp_server import activate_premium
        result = asyncio.get_event_loop().run_until_complete(
            activate_premium(license_key="")
        )
        data = json.loads(result)
        assert data["valid"] is False

    def test_activate_premium_invalid_key(self):
        from mcp_server import activate_premium
        result = asyncio.get_event_loop().run_until_complete(
            activate_premium(license_key="invalid-key-xyz")
        )
        data = json.loads(result)
        assert data["valid"] is False

        from premium.licensing import feature_gate
        feature_gate.reset()


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

    def test_premium_features_resource(self):
        from mcp_server import get_premium_features_resource
        result = asyncio.get_event_loop().run_until_complete(
            get_premium_features_resource()
        )
        data = json.loads(result)
        assert "features" in data


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
