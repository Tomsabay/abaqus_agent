"""
core/helpers.py
---------------
Utility functions shared between server.py and mcp_server.py.
"""
from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

CASES_DIR = Path(__file__).parent.parent / "cases"


def check_abaqus() -> bool:
    return shutil.which("abaqus") is not None


def list_cases() -> list[str]:
    return [
        d.name
        for d in sorted(CASES_DIR.iterdir())
        if d.is_dir() and (d / "spec.yaml").exists()
    ]


def make_run_id(spec_yaml: str) -> str:
    return hashlib.sha256(spec_yaml.encode()).hexdigest()[:16]
