"""What this repo's services expose, and what the suite is allowed to touch.

Three separate things that all failed the same way -- a default nobody looked
at again after the surrounding rule changed:

  * ``core.config.host()`` returns loopback because the server has no
    authentication and can launch solver jobs. ``mcp_bridge.py`` -- which
    proxies the same tools -- went on hard-coding ``0.0.0.0`` and
    ``allow_origins=["*"]``.
  * ``tests/conftest.py`` hides real solvers so the suite stays hermetic, but
    the list it hid was the three legacy names only. ``ABAQUS_AGENT_ABAQUS_CMD``
    is the override this project's own instructions tell you to set, and with
    it set, ``test_run_pipeline_async`` -- the test that asserts DEMO mode --
    launched a real 60-second Abaqus solve and failed. Measured 2026-08-09:
    60.38s / 1 failed with the old conftest, 9.46s / 19 passed with the fix.
"""

from __future__ import annotations

import ast
import importlib
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


# ── the bridge binds where the server binds ──────────────────────────


def _tree(name: str) -> ast.Module:
    """Parsed source, not an import: importing mcp_bridge spawns the MCP
    subprocess, and grepping the text matches the comments that explain the
    defect as readily as the defect itself."""
    return ast.parse((ROOT / name).read_text(encoding="utf-8"))


def _calls(tree: ast.Module, attr: str) -> list[ast.Call]:
    return [n for n in ast.walk(tree)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
            and n.func.attr == attr]


def _kwarg(call: ast.Call, name: str):
    return next((kw.value for kw in call.keywords if kw.arg == name), None)


def test_the_bridge_does_not_hard_code_a_wildcard_bind():
    runs = _calls(_tree("mcp_bridge.py"), "run")
    uvicorn_runs = [c for c in runs
                    if isinstance(c.func.value, ast.Name)
                    and c.func.value.id == "uvicorn"]
    assert uvicorn_runs, "mcp_bridge.py no longer serves itself"
    for call in uvicorn_runs:
        host = _kwarg(call, "host")
        assert not isinstance(host, ast.Constant), (
            "the bridge proxies the same job-submitting tools as the server, "
            "which binds loopback for that reason; got a literal %r"
            % getattr(host, "value", host))


def test_the_bridge_port_is_configurable_like_the_server_port():
    import core.config as config

    importlib.reload(config)
    try:
        assert config.bridge_port() == config.DEFAULT_BRIDGE_PORT
        os.environ[config.ENV_BRIDGE_PORT] = "9123"
        assert config.bridge_port() == 9123
        os.environ[config.ENV_BRIDGE_PORT] = "not-a-port"
        assert config.bridge_port() == config.DEFAULT_BRIDGE_PORT
    finally:
        os.environ.pop(config.ENV_BRIDGE_PORT, None)
        importlib.reload(config)


def test_cross_origin_access_is_opt_in_on_both_services():
    """A wildcard origin on an unauthenticated service that can launch solver
    jobs means any page open in the browser can drive it."""
    for name in ("server.py", "mcp_bridge.py"):
        tree = _tree(name)
        for call in _calls(tree, "add_middleware"):
            origins = _kwarg(call, "allow_origins")
            if origins is None:
                continue
            literal = [e.value for e in getattr(origins, "elts", [])
                       if isinstance(e, ast.Constant)]
            assert "*" not in literal, "%s allows every origin" % name
        assert "ABAQUS_AGENT_CORS_ORIGINS" in (ROOT / name).read_text(
            encoding="utf-8"), name


# ── the suite cannot reach a real solver ─────────────────────────────


def test_the_documented_abaqus_override_is_hidden_from_the_suite():
    """conftest pops it at import.

    This one only bites on a machine where the variable is actually exported
    -- which is the machine that matters, and is exactly how the hole was
    found. The list-membership test below is the half that fires everywhere.
    """
    from tools.abaqus_cmd import ENV_ABAQUS_CMD

    assert os.environ.get(ENV_ABAQUS_CMD) is None, (
        "%s survived conftest: the suite can reach a real solver" % ENV_ABAQUS_CMD)


def test_every_solver_override_this_repo_reads_is_on_the_hidden_list():
    """The list is only correct if it covers what the code actually reads.
    Both halves are enumerated here so adding a new override to one without
    the other is a test failure, not a silent hole."""
    import tests.conftest as conftest
    from tools.abaqus_command import ABAQUS_COMMAND_ENV_KEYS

    hidden = set(ABAQUS_COMMAND_ENV_KEYS) | set(conftest._SOLVER_ENV_KEYS)
    for key in ("ABAQUS_AGENT_ABAQUS_CMD", "ABAQUS_AGENT_ABAQUS_RELEASE",
                "ABAQUS_AGENT_CCX_EXE", "ABAQUS_AGENT_SOLVER_BACKEND"):
        assert key in hidden, key
        assert os.environ.get(key) is None, key
