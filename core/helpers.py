"""
core/helpers.py
---------------
Utility functions shared between server.py and mcp_server.py.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
from pathlib import Path

import yaml

from tools.abaqus_cmd import ENV_ABAQUS_CMD

CASES_DIR = Path(__file__).parent.parent / "cases"


def check_abaqus() -> bool:
    # Honor the explicit path override (packaged mode) before PATH lookup, so
    # availability detection matches what get_abaqus_cmd() will actually run.
    override = os.environ.get(ENV_ABAQUS_CMD)
    if override and override.strip():
        return Path(override.strip()).exists()
    return shutil.which("abaqus") is not None


def check_calculix() -> bool:
    """CalculiX (ccx) availability — the fallback backend.

    Env override first, then PATH, same policy as check_abaqus. Never probes
    ~/solvers: that is a check-harness convenience, and doing it here would make
    pytest on a developer box start launching real solves.
    """
    from tools.ccx_cmd import get_ccx_cmd
    return get_ccx_cmd() is not None


def list_cases() -> list[str]:
    return [
        d.name
        for d in sorted(CASES_DIR.iterdir())
        if d.is_dir() and (d / "spec.yaml").exists()
    ]


def run_id_for_spec(spec) -> str:
    """The one definition of a run's identity: a hash of its parsed content.

    Everything that needs a run id calls this. runner/build_model.py names the
    run directory with it, so the id the API hands back is the directory the
    evidence is actually in.
    """
    payload = json.dumps(spec, sort_keys=True, default=str).encode()
    return hashlib.sha256(payload).hexdigest()[:16]


def make_run_id(spec_yaml: str) -> str:
    """A run id from spec source text.

    Parsed first, deliberately. This used to hash the raw text, which meant
    the id `POST /api/run/start` and MCP `start_run` reported was never the
    directory under cases/<case>/runs/ -- measured on the shipped cantilever:
    API `64f474736b4b2019`, disk `dd6ec1145b8de62f`. Anyone who copied the id
    off the workbench to go find the evidence found nothing.

    A side effect, and the right one: two spec files that differ only in
    comments, key order or quoting are the same run, because they describe the
    same model.
    """
    try:
        spec = yaml.safe_load(spec_yaml)
    except yaml.YAMLError:
        # Unparseable: hash the text so this still returns an id. The spec
        # validator is what should report the syntax error, not this.
        return hashlib.sha256(spec_yaml.encode()).hexdigest()[:16]
    return run_id_for_spec(spec)
