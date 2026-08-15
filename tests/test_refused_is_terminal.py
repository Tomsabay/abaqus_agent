"""REFUSED must be a terminal run status on both sides of the wire.

agent/ccx_orchestrator.py sets ``status: REFUSED`` when the chosen backend
looks at a spec and declines to solve it. That status was originally missing
from both terminal-state lists, which had two consequences a unit test would
never have caught but a browser check did:

  * the workbench treated the run as still in flight forever — the progress bar
    stayed up, ``finishWatch`` never fired, and the run stayed "active" so the
    UI would not move on;
  * ``_enrich_runs`` gates result persistence on the same list, so a refused
    run's outcome was never written into the session record.

Pinned here in both places because the two lists have to agree and nothing else
forces them to.
"""

from __future__ import annotations

import re
from pathlib import Path

from tests.frontend_sources import workbench_text

ROOT = Path(__file__).resolve().parent.parent
TERMINAL_STATES = {"COMPLETED", "FAILED", "ABORTED", "ERROR", "REFUSED"}


def test_backend_terminal_states_include_refused() -> None:
    from workbench.routes import _TERMINAL_RUN_STATES

    assert set(_TERMINAL_RUN_STATES) == TERMINAL_STATES


def test_frontend_terminal_states_match_backend() -> None:
    text = workbench_text()
    match = re.search(r"const TERMINAL = \[(.*?)\];", text, re.S)
    assert match, "frontend/workbench.html no longer declares `const TERMINAL`"
    states = set(re.findall(r"'([A-Z_]+)'", match.group(1)))

    assert states == TERMINAL_STATES, (
        "frontend TERMINAL and workbench.routes._TERMINAL_RUN_STATES must agree; "
        "a status in one but not the other leaves runs half-finished"
    )


def test_refused_status_has_a_status_dot_style() -> None:
    """Every terminal status the sidebar can show needs a dot colour."""
    text = workbench_text()
    styled = set(re.findall(r"\.run-dot\.([A-Z_]+)", text))

    missing = TERMINAL_STATES - styled
    assert not missing, f"terminal statuses with no .run-dot style: {sorted(missing)}"


def test_ccx_orchestrator_still_emits_refused() -> None:
    """If this ever changes, the lists above are pinning a dead string."""
    text = (ROOT / "agent" / "ccx_orchestrator.py").read_text(encoding="utf-8")
    assert '"status": "REFUSED"' in text
