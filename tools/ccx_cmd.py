"""
ccx_cmd.py
----------
Resolve the CalculiX ``ccx`` command for subprocess calls.

Mirrors ``tools/abaqus_cmd.py``: leaf module, no intra-repo imports, env
override first, PATH second, ``None`` when absent. ``None`` genuinely means
"no CalculiX on this machine" — callers must never substitute a literal.

CalculiX is GPL. It is NEVER bundled and NEVER auto-downloaded: the user
installs it, we only locate and invoke it, exactly as with Abaqus.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess

# Same name the free-solver check harness and the course material already use
# (scripts/run_free_solver_check.py, course/materials/module2/free_solver_setup.md).
ENV_CCX_EXE = "ABAQUS_AGENT_CCX_EXE"

# Lets a caller state the version without paying for the probe (CI, packaging).
ENV_CCX_VERSION = "ABAQUS_AGENT_CCX_VERSION"

_version_cache: str | None | tuple = ()  # () = not probed yet; None = unknown


def get_ccx_cmd() -> str | None:
    """
    Return the resolved path to the ``ccx`` executable, or None when absent.

    Resolution order:
      1. ``ABAQUS_AGENT_CCX_EXE`` env (explicit full path)
      2. ``shutil.which("ccx")``
      3. None — there is no meaningful literal fallback: unlike Abaqus, a
         missing CalculiX is a normal state that must degrade, not raise.

    Deliberately does NOT probe ``~/solvers`` the way
    ``scripts/run_free_solver_check.py`` does. That script is a check harness;
    this is the product, and home-directory probing would make pytest on a
    developer box start launching real solves.
    """
    override = os.environ.get(ENV_CCX_EXE)
    if override and override.strip():
        candidate = override.strip()
        return candidate if os.path.isfile(candidate) else None
    return shutil.which("ccx")


def detect_ccx_version(timeout: float = 30.0, force: bool = False) -> str | None:
    """Return the version the *installed* ccx reports, e.g. "2.23".

    ``ccx -v`` prints "This is Version 2.23" and exits 0. Same self-reporting
    discipline as ``detect_abaqus_release``: never assert a version we did not
    read off the binary. Returns None when CalculiX is absent or unparseable;
    callers must treat that as "unknown", never as a default. Cached per process.
    """
    global _version_cache
    if not force and _version_cache != ():
        return _version_cache  # type: ignore[return-value]

    stated = os.environ.get(ENV_CCX_VERSION, "").strip()
    if stated:
        _version_cache = stated
        return stated

    exe = get_ccx_cmd()
    if not exe:
        _version_cache = None
        return None

    try:
        proc = subprocess.run(
            [exe, "-v"],
            capture_output=True, text=True, errors="replace",
            stdin=subprocess.DEVNULL, timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError):
        _version_cache = None
        return None

    match = re.search(r"Version\s+([0-9][0-9.]*)", (proc.stdout or "") + (proc.stderr or ""))
    _version_cache = match.group(1) if match else None
    return _version_cache  # type: ignore[return-value]


def reset_version_cache() -> None:
    """Drop the per-process version cache (tests, env changes)."""
    global _version_cache
    _version_cache = ()
