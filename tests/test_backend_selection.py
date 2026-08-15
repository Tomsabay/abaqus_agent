"""Backend selection: there is one backend, and it either resolves or refuses.

The CalculiX fallback and the demo walkthrough both used to be decided here and
both were removed 2026-08-15. What is left has to answer one question honestly:
can this machine solve, and if not, does the user get a sentence that tells them
what to do? The failure this file guards against is the one the fallback made
easy — a visitor who cannot solve anything still being shown something that
looks like a run.

Hermetic — no solver is invoked. Availability is injected and the release probe
is stubbed, so a developer box with a real Abaqus cannot make these pass (or
fail) for the wrong reason.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core import backends
from core.backends import (
    BACKEND_ABAQUS,
    ENV_BACKEND,
    refusal_messages,
    select_backend,
)


@pytest.fixture(autouse=True)
def _stub_probes(monkeypatch):
    monkeypatch.setattr(backends, "detect_abaqus_release", lambda *a, **k: "2021")
    monkeypatch.delenv(ENV_BACKEND, raising=False)


def _static_spec() -> dict:
    return {
        "meta": {"model_name": "Cantilever"},
        "geometry": {"type": "cantilever_block", "L": 100.0, "W": 10.0, "H": 10.0,
                     "seed_size": 5.0},
        "material": {"name": "Steel", "E": 210000.0, "nu": 0.3},
        "analysis": {"solver": "standard", "step_type": "Static", "cpus": 1},
        "bc_load": {"load_type": "concentrated_force", "value": -1.0, "direction": 2},
        "outputs": {"kpis": [{"name": "U_tip", "type": "nodal_displacement",
                              "location": "tip_center", "component": "U2"}]},
    }


# --- the solver is there ----------------------------------------------------

def test_abaqus_present_is_chosen_and_carries_its_release():
    d = select_backend(_static_spec(), abaqus_available=True)

    assert d.backend == BACKEND_ABAQUS
    assert d.supported
    assert d.version == "2021"
    assert d.label == "Abaqus 2021"
    assert d.blockers == ()


def test_the_spec_does_not_change_the_answer():
    """Nothing about the model is a reason to pick a different solver any more.

    The capability matrix that used to read the spec belonged to the fallback.
    With one backend, availability is the whole decision, and a spec-dependent
    answer here would mean something is quietly gating features again.
    """
    plain = select_backend(_static_spec(), abaqus_available=True)
    exotic = select_backend(
        {"parts": [{"name": "P"}], "analysis": {"step_type": "Frequency"}},
        abaqus_available=True)

    assert (exotic.backend, exotic.supported) == (plain.backend, plain.supported)


# --- the solver is not there ------------------------------------------------

def test_no_abaqus_is_refused_not_downgraded():
    d = select_backend(_static_spec(), abaqus_available=False)

    assert d.backend == BACKEND_ABAQUS, "there is nothing else to fall back to"
    assert not d.supported
    assert d.blockers, "a refusal with no blocker cannot be rendered anywhere"


def test_the_refusal_names_the_variable_that_fixes_it():
    """A refusal that does not say what to do is a dead end.

    This is the entire user-facing consequence of removing the fallback: the
    visitor without Abaqus now gets one sentence, so that sentence has to carry
    the actionable part.
    """
    d = select_backend(_static_spec(), abaqus_available=False)
    lines = refusal_messages(d)

    assert lines
    assert any("ABAQUS_AGENT_ABAQUS_CMD" in line for line in lines), lines
    assert any("PATH" in line for line in lines), lines


def test_the_refusal_reads_in_english_too():
    d = select_backend(_static_spec(), abaqus_available=False)

    en = " ".join(refusal_messages(d, lang="en"))
    assert "Abaqus not found" in en
    assert "ABAQUS_AGENT_ABAQUS_CMD" in en


# --- the override -----------------------------------------------------------

def test_explicitly_asking_for_abaqus_when_it_is_missing_still_refuses():
    d = select_backend(_static_spec(), abaqus_available=False,
                       override="abaqus")

    assert not d.supported
    assert d.source == "runner_cfg"


@pytest.mark.parametrize("value", ["calculix", "ccx", "demo", "banana"])
def test_any_other_backend_name_is_refused_by_name(value):
    """`calculix` and `demo` were valid settings until 2026-08-15.

    A machine that still carries the old environment variable must be told the
    setting is gone, not silently given Abaqus — the run would be correct but
    the operator would keep believing a fallback exists.
    """
    d = select_backend(_static_spec(), abaqus_available=True, override=value)

    assert not d.supported
    assert value in " ".join(refusal_messages(d))


def test_the_env_var_is_read_when_no_override_is_passed(monkeypatch):
    monkeypatch.setenv(ENV_BACKEND, "calculix")
    d = select_backend(_static_spec(), abaqus_available=True)

    assert not d.supported
    assert d.source == "env"


@pytest.mark.parametrize("value", ["auto", "AUTO", " auto ", ""])
def test_auto_and_blank_mean_just_use_abaqus(monkeypatch, value):
    monkeypatch.setenv(ENV_BACKEND, value)
    d = select_backend(_static_spec(), abaqus_available=True)

    assert d.supported
    assert d.backend == BACKEND_ABAQUS


# ── what the orchestrator and the CLI do with that decision ──────────────────

def test_the_orchestrator_refuses_with_a_result_not_an_exception(monkeypatch):
    """Every other way this pipeline fails arrives as a result dict with an
    `error`. The refusal briefly raised instead, and the CLI printed a Python
    traceback at the one person the whole change was for: somebody who does not
    have Abaqus and needs to be told so in a sentence.
    """
    import yaml

    from agent.orchestrator import AbaqusOrchestrator
    from tools.errors import ErrorCode

    monkeypatch.setattr("core.helpers.check_abaqus", lambda: False)
    spec = yaml.safe_load(
        (Path(__file__).parent.parent / "cases" / "cantilever" / "spec.yaml")
        .read_text(encoding="utf-8"))

    result = AbaqusOrchestrator(spec_dict=spec).run()

    assert result["status"] == "FAILED"
    assert result["error"]["error_code"] == ErrorCode.ABAQUS_NOT_FOUND.value
    assert result["kpis"] == {}
    assert "ABAQUS_AGENT_ABAQUS_CMD" in result["kpi_notice"]
    # A refusal is not evidence: it must not leave a capsule or a result file
    # behind in the case's runs/ cache.
    assert "capsule_path" not in result
    assert "result_path" not in result


def test_the_cli_exits_nonzero_on_a_refusal():
    """Measured through the real command line, because the failure this guards
    is what reaches a terminal: `agent/orchestrator.py` used to let the error
    escape as a traceback, and a caller scripting it saw a stack, not a
    reason."""
    import os
    import subprocess

    root = Path(__file__).parent.parent
    proc = subprocess.run(
        [sys.executable, "agent/orchestrator.py", "cases/cantilever/spec.yaml"],
        cwd=str(root), capture_output=True, text=True, encoding="utf-8",
        errors="replace", stdin=subprocess.DEVNULL, timeout=300,
        env={**os.environ, "ABAQUS_AGENT_ABAQUS_CMD": r"C:\__no_abaqus__\abaqus.bat"},
    )

    assert proc.returncode == 2, proc.stdout[-2000:]
    assert "Traceback" not in proc.stderr, proc.stderr[-2000:]
    assert "ABAQUS_AGENT_ABAQUS_CMD" in proc.stdout
