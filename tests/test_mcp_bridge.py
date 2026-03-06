"""
Tests for mcp_bridge.py — HTTP/SSE bridge to MCP server.

These tests verify the bridge endpoint routing and request/response models.
Since the bridge spawns mcp_server.py as a subprocess, these tests mock
the MCPConnection to avoid subprocess dependencies.
"""
import asyncio
import json
import time
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

import yaml


class MockMCPConnection:
    """Mock MCP connection that returns predefined responses."""

    def __init__(self):
        self._initialized = True

    async def start(self):
        pass

    async def stop(self):
        pass

    async def call_tool(self, tool_name: str, arguments: dict) -> dict:
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
