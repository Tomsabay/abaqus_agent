"""
Tests for mcp_server.py — MCP tools and resources.

Uses direct function calls (the MCP tools are just async functions)
rather than requiring a full MCP client/transport setup.
"""
import asyncio
import json
import time
import pytest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

import yaml


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
        from mcp_server import start_run, RUNS
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
        from mcp_server import start_run, get_run_status, RUNS
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
        from mcp_server import subscribe_progress, unsubscribe_progress, _broadcast_progress
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
        from mcp_server import start_run, get_run_status, subscribe_progress, unsubscribe_progress, RUNS

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
