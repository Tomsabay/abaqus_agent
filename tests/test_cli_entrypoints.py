from __future__ import annotations

import importlib
from pathlib import Path

import pytest

try:
    import tomllib
except ModuleNotFoundError:
    tomllib = pytest.importorskip("tomli")

ROOT = Path(__file__).resolve().parent.parent


def test_no_server_cli_entrypoints_are_configured_and_importable():
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    scripts = pyproject["project"]["scripts"]
    expected = {
        "abaqus-agent-case-memory": "scripts.inspect_case_memory:main",
        "abaqus-agent-doctor-patterns": "scripts.inspect_solver_doctor_patterns:main",
        "abaqus-agent-kpi-recipes": "scripts.inspect_kpi_recipes:main",
        "abaqus-agent-local-cli-smoke": "scripts.run_local_cli_smoke:main",
        "abaqus-agent-vault": "scripts.inspect_evidence_vault:main",
        "abaqus-agent-verify-local-demo-pack": "scripts.verify_local_demo_pack_bundle:main",
        "abaqus-agent-verify-local-cli-smoke": "scripts.verify_local_cli_smoke_bundle:main",
    }

    for command, target in expected.items():
        assert scripts[command] == target
        module_name, function_name = target.split(":")
        module = importlib.import_module(module_name)
        assert callable(getattr(module, function_name))

    assert "scripts" in pyproject["tool"]["hatch"]["build"]["targets"]["wheel"]["packages"]
