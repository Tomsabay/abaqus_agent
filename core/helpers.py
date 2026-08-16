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


def list_cases() -> list[str]:
    return [
        d.name
        for d in sorted(CASES_DIR.iterdir())
        if d.is_dir() and (d / "spec.yaml").exists()
    ]


# Step methods that integrate in time, so one frame is not the whole answer.
DYNAMIC_STEP_CALLS = ("ExplicitDynamicsStep", "ImplicitDynamicsStep")


def has_dynamic_step(spec) -> bool:
    """Does this spec run an analysis worth animating frame by frame?

    Read off `steps[].call`, which is where the v2 dialect says what the
    analysis IS. The orchestrator used to ask `analysis.step_type` for
    "Dynamic_Explicit" / "Dynamic_Implicit" instead -- a v1 field the schema
    now refuses everywhere, `analysis` being closed and `step_type` not among
    its keys. So once that dialect was removed the question was answered False
    for every spec that validates at all, and the ODB animation stopped being
    exported, in silence and for every case including the two explicit ones.

    False for a `deck` spec on purpose: its steps are inside the .inp and
    nothing here has read them. False for the named step shorthand too --
    `steps[].type` has exactly one legal value, and it is Static.
    """
    return any(isinstance(step, dict)
               and step.get("call") in DYNAMIC_STEP_CALLS
               for step in (spec or {}).get("steps") or [])


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
