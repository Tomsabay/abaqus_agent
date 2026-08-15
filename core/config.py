"""
core/config.py
--------------
Single source of truth for runtime configuration, read once from the
environment. Two modes:

  - dev mode (default): data lives inside the repo (artifacts/, cases/runs/),
    reload on.
  - packaged mode: activated when ABAQUS_AGENT_DATA_DIR is set (the Tauri shell
    injects it). All writable state (sessions, run roots) is redirected under
    that directory; reload off.

Both modes bind 127.0.0.1. This file used to describe dev mode as binding
0.0.0.0 -- that stopped being true when ``host()`` was changed, but
mcp_bridge.py went on hard-coding 0.0.0.0 for another two months.

Every ``ABAQUS_AGENT_*`` override funnels through here so the packaging layer
has one place to configure and callers stop reading os.environ ad hoc.

Design notes:
  - Pure functions reading os.environ live-ish: values are read at call time,
    not import time, so tests can monkeypatch env per-case (mirrors how
    workbench/store.py already behaves).
  - Nothing here imports heavy modules — safe to import from anywhere.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def is_frozen() -> bool:
    """True when running from a PyInstaller-frozen executable."""
    return getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")

# ── Environment variable names (documented in one place) ──────────────
ENV_DATA_DIR = "ABAQUS_AGENT_DATA_DIR"
ENV_PORT = "ABAQUS_AGENT_PORT"
ENV_HOST = "ABAQUS_AGENT_HOST"
ENV_DEV = "ABAQUS_AGENT_DEV"
ENV_ABAQUS_CMD = "ABAQUS_AGENT_ABAQUS_CMD"
ENV_RUN_ROOT = "ABAQUS_AGENT_RUN_ROOT"
ENV_WORKBENCH_SESSION_DIR = "ABAQUS_AGENT_WORKBENCH_SESSION_DIR"
ENV_COPILOT_SESSION_DIR = "ABAQUS_AGENT_COPILOT_SESSION_DIR"
ENV_BRIDGE_PORT = "ABAQUS_AGENT_BRIDGE_PORT"

DEFAULT_PORT = 8000
DEFAULT_BRIDGE_PORT = 8001


def _env(name: str) -> str | None:
    val = os.environ.get(name)
    return val.strip() if val and val.strip() else None


def _default_user_data_dir() -> Path:
    """Per-OS default writable location for a frozen app with no explicit dir."""
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / "AbaqusAgent"
    return Path.home() / ".local" / "share" / "AbaqusAgent"


def data_dir() -> Path | None:
    """User-data root in packaged mode; None in dev mode.

    When ABAQUS_AGENT_DATA_DIR is set, redirect all writable state there.
    Absent + frozen exe → per-OS user data dir (never write into the _MEIPASS
    temp extraction dir). Absent + not frozen → None (dev, repo-local)."""
    raw = _env(ENV_DATA_DIR)
    if raw:
        return Path(raw)
    if is_frozen():
        return _default_user_data_dir()
    return None


def is_packaged() -> bool:
    return data_dir() is not None


def is_dev() -> bool:
    """Reload/dev conveniences on. True unless packaged, or explicitly toggled.

    ABAQUS_AGENT_DEV=0 forces off (e.g. running the frozen exe in-place);
    ABAQUS_AGENT_DEV=1 forces on."""
    override = _env(ENV_DEV)
    if override is not None:
        return override not in ("0", "false", "False")
    # A frozen exe can never use the reload/import-string path — default it off
    # regardless of whether the shell remembered to set the data dir.
    if is_frozen():
        return False
    return not is_packaged()


def host() -> str:
    explicit = _env(ENV_HOST)
    if explicit:
        return explicit
    # Loopback everywhere, including dev. The server has no authentication and
    # can launch solver jobs, so binding a development checkout to every
    # interface exposes that to the whole LAN. Anyone who genuinely needs LAN
    # access sets ABAQUS_AGENT_HOST and owns that decision.
    return "127.0.0.1"


def port() -> int:
    raw = _env(ENV_PORT)
    if raw:
        try:
            return int(raw)
        except ValueError:
            pass
    return DEFAULT_PORT


def bridge_port() -> int:
    """Port for mcp_bridge.py, which runs alongside the main server."""
    raw = _env(ENV_BRIDGE_PORT)
    if raw:
        try:
            return int(raw)
        except ValueError:
            pass
    return DEFAULT_BRIDGE_PORT


def abaqus_cmd_override() -> str | None:
    """Explicit abaqus.bat full path, if configured.

    Tauri sidecars do not reliably inherit PATH on Windows, so packaged mode
    needs an explicit path here rather than relying on shutil.which."""
    return _env(ENV_ABAQUS_CMD)


def _under_data_dir(subdir: str) -> Path:
    base = data_dir()
    # In dev (base is None) this is never reached by the redirect helpers,
    # but guard anyway so a stray call falls back to repo-local.
    root = base if base is not None else REPO_ROOT / "artifacts"
    return root / subdir


def workbench_session_dir() -> Path:
    """Explicit override wins; else data_dir in packaged mode; else repo-local."""
    explicit = _env(ENV_WORKBENCH_SESSION_DIR)
    if explicit:
        return Path(explicit)
    if is_packaged():
        return _under_data_dir("workbench_sessions")
    return REPO_ROOT / "artifacts" / "workbench_sessions"


def copilot_session_dir() -> Path:
    explicit = _env(ENV_COPILOT_SESSION_DIR)
    if explicit:
        return Path(explicit)
    if is_packaged():
        return _under_data_dir("copilot_sessions")
    return REPO_ROOT / "artifacts" / "copilot_sessions"


def run_root() -> Path | None:
    """Root for case run working directories, if redirected.

    Returns None in dev mode → callers keep their spec-relative default
    (cases/<case>/runs/). Packaged mode redirects under data_dir/runs.

    NOTE: Abaqus rejects input paths > 256 chars (runner/submit_job.py), so a
    redirected run root must stay shallow. Data dir + "runs" + run_id + model
    name is the budget; do not nest deeper."""
    explicit = _env(ENV_RUN_ROOT)
    if explicit:
        return Path(explicit)
    if is_packaged():
        return _under_data_dir("runs")
    return None
