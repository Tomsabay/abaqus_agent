"""Backend selection: Abaqus first, CalculiX fallback, demo last.

Hermetic — no solver is invoked. Availability is injected, and the two
detect_* probes are stubbed so a developer box with a real Abaqus cannot make
these pass (or fail) for the wrong reason.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core import backends
from core.backends import (
    BACKEND_ABAQUS,
    BACKEND_CALCULIX,
    BACKEND_DEMO,
    ENV_BACKEND,
    select_backend,
)


@pytest.fixture(autouse=True)
def _stub_probes(monkeypatch):
    monkeypatch.setattr(backends, "detect_abaqus_release", lambda *a, **k: "2021")
    monkeypatch.setattr(backends, "detect_ccx_version", lambda *a, **k: "2.23")
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


def test_abaqus_wins_when_both_present():
    decision = select_backend(_static_spec(), abaqus_available=True, calculix_available=True)
    assert decision.backend == BACKEND_ABAQUS
    assert decision.label == "Abaqus 2021"
    assert decision.supported


def test_calculix_used_when_abaqus_absent():
    decision = select_backend(_static_spec(), abaqus_available=False, calculix_available=True)
    assert decision.backend == BACKEND_CALCULIX
    assert decision.label == "CalculiX 2.23"
    assert decision.supported
    assert "未检测到 Abaqus" in decision.reason


def test_demo_when_no_solver_at_all():
    decision = select_backend(_static_spec(), abaqus_available=False, calculix_available=False)
    assert decision.backend == BACKEND_DEMO
    assert "CalculiX" in decision.reason


def test_env_override_forces_calculix_even_with_abaqus(monkeypatch):
    monkeypatch.setenv(ENV_BACKEND, "calculix")
    decision = select_backend(_static_spec(), abaqus_available=True, calculix_available=True)
    assert decision.backend == BACKEND_CALCULIX
    assert decision.source == "env"


def test_runner_cfg_override_beats_env(monkeypatch):
    monkeypatch.setenv(ENV_BACKEND, "calculix")
    decision = select_backend(_static_spec(), abaqus_available=True,
                              calculix_available=True, override="abaqus")
    assert decision.backend == BACKEND_ABAQUS
    assert decision.source == "runner_cfg"


def test_override_to_absent_solver_fails_loudly_not_silently_to_demo():
    """Asking for a solver that is not there must not slide into demo mode."""
    decision = select_backend(_static_spec(), abaqus_available=True,
                              calculix_available=False, override="calculix")
    assert decision.backend == BACKEND_CALCULIX
    assert not decision.supported
    assert any("ABAQUS_AGENT_CCX_EXE" in b.reason for b in decision.blockers)


def test_explicit_abaqus_when_absent_is_a_blocker():
    decision = select_backend(_static_spec(), abaqus_available=False,
                              calculix_available=True, override="abaqus")
    assert decision.backend == BACKEND_ABAQUS
    assert not decision.supported


def test_explicit_demo_is_honoured():
    decision = select_backend(_static_spec(), abaqus_available=True,
                              calculix_available=True, override="demo")
    assert decision.backend == BACKEND_DEMO
    assert decision.supported


def test_bogus_backend_value_is_refused(monkeypatch):
    monkeypatch.setenv(ENV_BACKEND, "nastran")
    decision = select_backend(_static_spec(), abaqus_available=True, calculix_available=True)
    assert not decision.supported
    assert "auto" in decision.blockers[0].reason


def test_unknown_ccx_version_blocks_rather_than_guesses(monkeypatch):
    monkeypatch.setattr(backends, "detect_ccx_version", lambda *a, **k: None)
    decision = select_backend(_static_spec(), abaqus_available=False, calculix_available=True)
    assert decision.backend == BACKEND_CALCULIX
    assert not decision.supported
    assert decision.blockers[0].feature == "calculix.version"


def test_abaqus_decision_never_carries_calculix_caveats():
    decision = select_backend(
        {"geometry": {"type": "composite_plate"},
         "analysis": {"step_type": "Dynamic_Explicit"},
         "bc_load": {"load_type": "blast_conwep"}},
        abaqus_available=True, calculix_available=True,
    )
    assert decision.backend == BACKEND_ABAQUS
    assert decision.supported, "the CalculiX matrix must never gate an Abaqus run"
