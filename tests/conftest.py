"""Shared pytest configuration.

The suite is designed to be hermetic: it must pass on machines without Abaqus,
and real-solver verification goes through the e2e orchestrator and the
``--require-real`` smoke harness instead of pytest. On machines where Abaqus
IS installed (e.g. the Windows dev box), hide it from PATH and the command
override env vars so tests — and every subprocess they spawn — exercise the
same no-Abaqus code paths as CI, instead of silently launching real solver
runs and consuming license tokens.
"""

import os
import shutil

from tools.abaqus_cmd import ENV_ABAQUS_CMD, ENV_ABAQUS_RELEASE
from tools.abaqus_command import ABAQUS_COMMAND_ENV_KEYS

# The CalculiX fallback backend gets the same treatment. Without this, the day
# ccx lands on this box's PATH the demo-mode assertions in
# tests/test_core_pipeline.py flip to real CalculiX solves and the suite stops
# being hermetic — silently, because those solves would pass.
#
# ABAQUS_COMMAND_ENV_KEYS covers only the three legacy names
# (ABAQUS_EXECUTABLE / ABAQUS_COMMAND / ABAQUS_PATH). ABAQUS_AGENT_ABAQUS_CMD
# is the override this project actually documents — `core.helpers.check_abaqus`
# and `tools.abaqus_cmd.get_abaqus_cmd` both read it first — and it was not on
# any list here, so a developer who followed the project's own instructions
# for pointing at a specific install had a suite that launched real solves.
#
# The two CCX keys stay on the list after the CalculiX backend was removed
# (2026-08-15). Nothing reads them now, and clearing an unread variable costs
# nothing — but a developer box that still has them set from that fortnight
# should not be the reason a future reintroduction goes unnoticed here.
_SOLVER_ENV_KEYS = (
    ENV_ABAQUS_CMD,
    ENV_ABAQUS_RELEASE,
    "ABAQUS_AGENT_CCX_EXE",
    "ABAQUS_AGENT_CCX_VERSION",
    "ABAQUS_AGENT_SOLVER_ROOT",
    "ABAQUS_AGENT_SOLVER_BACKEND",
)


def _hide_real_solvers() -> None:
    for key in tuple(ABAQUS_COMMAND_ENV_KEYS) + _SOLVER_ENV_KEYS:
        os.environ.pop(key, None)
    parts = os.environ.get("PATH", "").split(os.pathsep)
    kept = [
        p for p in parts
        if p
        and shutil.which("abaqus", path=p) is None
        and shutil.which("ccx", path=p) is None
    ]
    os.environ["PATH"] = os.pathsep.join(kept)


_hide_real_solvers()
