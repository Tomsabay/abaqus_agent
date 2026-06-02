"""
Tests for mcp_bridge.py — HTTP/SSE bridge to MCP server.

These tests verify the bridge endpoint routing and request/response models.
Since the bridge spawns mcp_server.py as a subprocess, these tests mock
the MCPConnection to avoid subprocess dependencies.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))



class MockMCPConnection:
    """Mock MCP connection that returns predefined responses."""

    def __init__(self):
        self._initialized = True
        self.calls = []

    async def start(self):
        pass

    async def stop(self):
        pass

    async def call_tool(self, tool_name: str, arguments: dict) -> dict:
        self.calls.append((tool_name, arguments))
        if tool_name == "health_check":
            return {
                "status": "ok",
                "abaqus_available": False,
                "cases": ["cantilever", "plate_hole", "modal", "explicit_impact"],
                "version": "0.1.0",
                "transport": "mcp",
            }
        elif tool_name == "generate_spec":
            return {
                "spec_yaml": "meta:\n  model_name: Test\n",
                "spec_dict": {"meta": {"model_name": "Test"}},
                "valid": True,
                "errors": [],
                "missing_questions": [],
            }
        elif tool_name == "validate_spec_tool":
            spec_yaml = arguments.get("spec_yaml", "")
            valid = "meta:" in spec_yaml and "geometry:" in spec_yaml
            return {"valid": valid, "errors": [] if valid else ["Missing fields"]}
        elif tool_name == "start_run":
            return {"run_id": "mock_run_001", "status": "PENDING"}
        elif tool_name == "get_run_status":
            run_id = arguments.get("run_id", "")
            if run_id == "nonexistent":
                return {"error": f"Run {run_id} not found"}
            return {
                "run_id": run_id,
                "status": "COMPLETED",
                "progress_pct": 100,
                "stages": {},
                "kpis": {},
                "elapsed": 5.0,
            }
        elif tool_name == "diagnose_logs_tool":
            return {
                "matched": True,
                "matches": [{
                    "id": "missing_node_set",
                    "category": "model_setup",
                    "severity": "error",
                    "evidence": "Node set FIXED_NODES has not been defined",
                    "suggestion": "Verify node set names.",
                }],
            }
        elif tool_name == "simulation_diff_tool":
            return {
                "passed": False,
                "baseline": {"run_id": "base"},
                "candidate": {"run_id": "candidate"},
                "sections": {"kpis": {"changes": [{"name": "MISES", "status": "WARNING"}]}},
                "markdown": "# Simulation Diff Report",
            }
        elif tool_name == "case_memory_search_tool":
            return {
                "total_indexed": 1,
                "total_matches": 1,
                "matches": [{"run_id": "bridge_memory", "model_name": "BridgeMemoryModel"}],
                "markdown": "# Case Memory Search",
            }
        elif tool_name == "environment_preflight_tool":
            return {
                "status": "ready",
                "abaqus": {
                    "resolved_path": "C:\\SIMULIA\\Commands\\abaqus.BAT",
                    "release_check": {"status": "pass", "version": "2021"},
                },
                "markdown": "# Abaqus Environment Preflight",
            }
        elif tool_name == "offline_report_export_tool":
            return {
                "summary": {"run_id": "bridge_offline_report", "model_name": "BridgeOffline"},
                "offline_source": arguments.get("source"),
                "markdown": "# Simulation QA Summary",
                "html": "<!doctype html>",
            }
        elif tool_name == "run_benchmark_tool":
            return {
                "run_id": "bench_mock01",
                "cases": ["cantilever", "plate_hole"],
                "dry_run": arguments.get("dry_run", True),
            }
        elif tool_name == "get_premium_features":
            return {
                "features": {
                    "coupled_analysis": {"display_name": "Multi-physics Coupling", "enabled": False},
                },
                "capabilities": {},
            }
        elif tool_name == "activate_premium":
            key = arguments.get("license_key", "")
            if key.startswith("dev-"):
                return {"valid": True, "features": ["coupled_analysis"]}
            return {"valid": False, "error": "Invalid key"}
        return {}

    async def read_resource(self, uri: str) -> dict:
        if uri == "benchmark://cases":
            return {
                "cases": [
                    {"name": "cantilever", "spec": {}, "expected": {}},
                    {"name": "plate_hole", "spec": {}, "expected": {}},
                ],
                "total": 2,
            }
        elif uri == "premium://features":
            return {"features": {}, "capabilities": {}}
        return {}


@pytest.fixture
def mock_bridge():
    """Provide bridge app with mocked MCP connection."""
    import mcp_bridge
    original_conn = mcp_bridge.mcp_conn
    mcp_bridge.mcp_conn = MockMCPConnection()
    yield mcp_bridge
    mcp_bridge.mcp_conn = original_conn


class TestBridgeEndpoints:
    """Test bridge HTTP endpoints with mocked MCP connection."""

    def _client(self, mock_bridge):
        from fastapi.testclient import TestClient
        return TestClient(mock_bridge.app, raise_server_exceptions=False)

    def test_root(self, mock_bridge):
        client = self._client(mock_bridge)
        res = client.get("/")
        assert res.status_code == 200

    def test_health(self, mock_bridge):
        client = self._client(mock_bridge)
        res = client.get("/mcp/health")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "ok"
        assert data["transport"] == "mcp"

    def test_generate_spec(self, mock_bridge):
        client = self._client(mock_bridge)
        res = client.post("/mcp/api/spec/generate", json={
            "text": "simple beam analysis",
            "abaqus_release": "2024",
        })
        assert res.status_code == 200
        data = res.json()
        assert "spec_yaml" in data
        assert data["valid"] is True

    def test_validate_spec_valid(self, mock_bridge):
        client = self._client(mock_bridge)
        res = client.post("/mcp/api/spec/validate", json={
            "spec_yaml": "meta:\n  model_name: Test\ngeometry:\n  type: box\n",
        })
        assert res.status_code == 200
        data = res.json()
        assert data["valid"] is True

    def test_validate_spec_invalid(self, mock_bridge):
        client = self._client(mock_bridge)
        res = client.post("/mcp/api/spec/validate", json={
            "spec_yaml": "incomplete: spec\n",
        })
        assert res.status_code == 200
        data = res.json()
        assert data["valid"] is False

    def test_start_run(self, mock_bridge):
        client = self._client(mock_bridge)
        res = client.post("/mcp/api/run/start", json={
            "spec_yaml": "meta:\n  model_name: Test\n",
        })
        assert res.status_code == 200
        data = res.json()
        assert data["run_id"] == "mock_run_001"
        assert data["status"] == "PENDING"

    def test_get_run_status(self, mock_bridge):
        client = self._client(mock_bridge)
        res = client.get("/mcp/api/run/mock_run_001")
        assert res.status_code == 200
        data = res.json()
        assert data["run_id"] == "mock_run_001"
        assert data["status"] == "COMPLETED"

    def test_get_run_status_not_found(self, mock_bridge):
        client = self._client(mock_bridge)
        res = client.get("/mcp/api/run/nonexistent")
        assert res.status_code == 200
        data = res.json()
        assert "error" in data

    def test_doctor_endpoint(self, mock_bridge):
        client = self._client(mock_bridge)
        res = client.post("/mcp/api/doctor", json={
            "text": "Node set FIXED_NODES has not been defined",
        })
        assert res.status_code == 200
        data = res.json()
        assert data["matched"] is True
        assert data["matches"][0]["id"] == "missing_node_set"

    def test_diff_endpoint(self, mock_bridge):
        client = self._client(mock_bridge)
        res = client.post("/mcp/api/diff", json={
            "baseline": "/tmp/base",
            "candidate": "/tmp/candidate",
            "tolerances": {"MISES": 0.3},
        })
        assert res.status_code == 200
        data = res.json()
        assert data["passed"] is False
        assert "Simulation Diff Report" in data["markdown"]
        tool_name, arguments = mock_bridge.mcp_conn.calls[-1]
        assert tool_name == "simulation_diff_tool"
        assert arguments["tolerances_json"] == '{"MISES": 0.3}'

    def test_memory_search_endpoint(self, mock_bridge):
        client = self._client(mock_bridge)
        res = client.post("/mcp/api/memory/search", json={
            "roots": ["/tmp/runs"],
            "query": "BridgeMemoryModel",
            "match_mode": "all",
            "artifact": "Job.log",
            "contract": "tip",
            "contracts_passed": "passed",
            "sort_by": "run_id",
            "sort_order": "asc",
            "min_score": 0.5,
        })
        assert res.status_code == 200
        data = res.json()
        assert data["matches"][0]["run_id"] == "bridge_memory"
        assert "Case Memory Search" in data["markdown"]
        tool_name, arguments = mock_bridge.mcp_conn.calls[-1]
        assert tool_name == "case_memory_search_tool"
        assert arguments["match_mode"] == "all"
        assert arguments["artifact"] == "Job.log"
        assert arguments["contract"] == "tip"
        assert arguments["contracts_passed"] == "passed"
        assert arguments["sort_by"] == "run_id"
        assert arguments["sort_order"] == "asc"
        assert arguments["min_score"] == 0.5

    def test_environment_preflight_endpoint(self, mock_bridge):
        client = self._client(mock_bridge)
        res = client.post("/mcp/api/validate/env", json={
            "abaqus_cmd": "abaqus",
            "timeout_seconds": 2.0,
            "check_release": False,
            "expected_release": "2026",
            "workdir": "runs",
            "runner_cfg": {"cpus": 2},
        })
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "ready"
        assert "Abaqus Environment Preflight" in data["markdown"]
        tool_name, arguments = mock_bridge.mcp_conn.calls[-1]
        assert tool_name == "environment_preflight_tool"
        assert arguments["abaqus_cmd"] == "abaqus"
        assert arguments["timeout_seconds"] == 2.0
        assert arguments["check_release"] is False
        assert arguments["expected_release"] == "2026"
        assert arguments["workdir"] == "runs"
        assert json.loads(arguments["runner_cfg_json"]) == {"cpus": 2}

    def test_offline_report_export_endpoint(self, mock_bridge):
        client = self._client(mock_bridge)
        res = client.post("/mcp/api/report/export", json={
            "source": "/tmp/run",
            "template": "client_summary",
        })
        assert res.status_code == 200
        data = res.json()
        assert data["summary"]["run_id"] == "bridge_offline_report"
        assert data["offline_source"] == "/tmp/run"
        assert "Simulation QA Summary" in data["markdown"]
        tool_name, arguments = mock_bridge.mcp_conn.calls[-1]
        assert tool_name == "offline_report_export_tool"
        assert arguments["source"] == "/tmp/run"
        assert arguments["template"] == "client_summary"

    def test_offline_report_export_bundle_endpoint(self, mock_bridge, tmp_path):
        artifact = tmp_path / "Job.log"
        artifact.write_text("Abaqus JOB Job COMPLETED\n", encoding="utf-8")
        (tmp_path / "capsule.json").write_text(
            json.dumps({
                "run_id": "bridge_zip_report",
                "inputs": {"model_name": "BridgeZip"},
                "provenance": {"status": "COMPLETED", "abaqus_release": "2024"},
                "artifacts": {"Job.log": {"path": "Job.log", "sha256": "abc", "bytes": artifact.stat().st_size}},
            }),
            encoding="utf-8",
        )
        (tmp_path / "result.json").write_text(
            json.dumps({"run_id": "bridge_zip_report", "status": "COMPLETED", "kpis": {}}),
            encoding="utf-8",
        )

        client = self._client(mock_bridge)
        res = client.post("/mcp/api/report/export.zip", json={
            "source": str(tmp_path),
            "template": "client_summary",
        })
        assert res.status_code == 200
        assert "application/zip" in res.headers["content-type"]
        assert 'filename="abaqus-report-bridge_zip_report.zip"' in res.headers["content-disposition"]

    def test_offline_report_export_pdf_endpoint(self, mock_bridge, tmp_path, monkeypatch):
        artifact = tmp_path / "Job.log"
        artifact.write_text("Abaqus JOB Job COMPLETED\n", encoding="utf-8")
        (tmp_path / "capsule.json").write_text(
            json.dumps({
                "run_id": "bridge_pdf_report",
                "inputs": {"model_name": "BridgePdf"},
                "provenance": {"status": "COMPLETED", "abaqus_release": "2024"},
                "artifacts": {"Job.log": {"path": "Job.log", "sha256": "abc", "bytes": artifact.stat().st_size}},
            }),
            encoding="utf-8",
        )
        (tmp_path / "result.json").write_text(
            json.dumps({"run_id": "bridge_pdf_report", "status": "COMPLETED", "kpis": {}}),
            encoding="utf-8",
        )
        monkeypatch.setattr(mock_bridge, "build_offline_report_pdf", lambda *args, **kwargs: b"%PDF-1.4\nbridge")

        client = self._client(mock_bridge)
        res = client.post("/mcp/api/report/export.pdf", json={
            "source": str(tmp_path),
            "template": "client_summary",
        })
        assert res.status_code == 200
        assert "application/pdf" in res.headers["content-type"]
        assert 'filename="abaqus-report-bridge_pdf_report.pdf"' in res.headers["content-disposition"]
        assert res.content.startswith(b"%PDF-1.4")

    def test_get_benchmark(self, mock_bridge):
        client = self._client(mock_bridge)
        res = client.get("/mcp/api/benchmark")
        assert res.status_code == 200
        data = res.json()
        assert "cases" in data
        assert data["total"] == 2

    def test_run_benchmark(self, mock_bridge):
        client = self._client(mock_bridge)
        res = client.post("/mcp/api/benchmark/run?dry_run=true")
        assert res.status_code == 200
        data = res.json()
        assert data["dry_run"] is True
        assert "run_id" in data

    def test_get_premium_features(self, mock_bridge):
        client = self._client(mock_bridge)
        res = client.get("/mcp/api/premium/features")
        assert res.status_code == 200
        data = res.json()
        assert "features" in data

    def test_activate_premium_valid(self, mock_bridge):
        client = self._client(mock_bridge)
        res = client.post("/mcp/api/premium/activate?license_key=dev-test")
        assert res.status_code == 200
        data = res.json()
        assert data["valid"] is True

    def test_activate_premium_invalid(self, mock_bridge):
        client = self._client(mock_bridge)
        res = client.post("/mcp/api/premium/activate?license_key=bad-key")
        assert res.status_code == 200
        data = res.json()
        assert data["valid"] is False


class TestBridgeSSEStream:
    """Test SSE streaming endpoint."""

    def test_stream_returns_sse(self, mock_bridge):
        """Verify the SSE endpoint returns event-stream content type."""
        client = self._client(mock_bridge)
        # The mock returns COMPLETED immediately, so the stream should emit and close
        with client.stream("GET", "/mcp/api/run/test_run/stream") as response:
            assert response.status_code == 200
            assert "text/event-stream" in response.headers.get("content-type", "")
            # Read at least one event
            events = []
            for line in response.iter_lines():
                if line.startswith("data:"):
                    events.append(json.loads(line[5:].strip()))
                    if len(events) >= 2:
                        break
            assert len(events) >= 1
            # Should get the status update and then done
            assert events[0].get("status") == "COMPLETED"

    def _client(self, mock_bridge):
        from fastapi.testclient import TestClient
        return TestClient(mock_bridge.app, raise_server_exceptions=False)


class TestBridgeRequestModels:
    """Test that bridge request models match the original API."""

    def test_generate_spec_request_defaults(self):
        from mcp_bridge import GenerateSpecRequest
        req = GenerateSpecRequest(text="test")
        assert req.abaqus_release == "2024"
        assert req.llm_backend == "template"
        assert req.anthropic_key == ""
        assert req.openai_key == ""

    def test_validate_spec_request(self):
        from mcp_bridge import ValidateSpecRequest
        req = ValidateSpecRequest(spec_yaml="test: yaml")
        assert req.spec_yaml == "test: yaml"

    def test_start_run_request_defaults(self):
        from mcp_bridge import StartRunRequest
        req = StartRunRequest(spec_yaml="meta: test")
        assert req.runner_cfg == {}

    def test_doctor_request_defaults(self):
        from mcp_bridge import DoctorRequest
        req = DoctorRequest()
        assert req.paths == []
        assert req.text == ""
