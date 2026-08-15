"""
abaqus_cmd.py
-------------
Resolve the Abaqus command for subprocess calls.

On Windows, Abaqus is typically installed as a .bat file (e.g. abaqus.bat).
``shutil.which("abaqus")`` finds it via PATHEXT, but
``subprocess.run(["abaqus", ...])`` raises FileNotFoundError because
subprocess does not consult PATHEXT when resolving the executable.

This module provides ``get_abaqus_cmd()`` which resolves the full path
once, so subprocess calls work on all platforms.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess

# Env override checked first — a Tauri sidecar on Windows does not reliably
# inherit the user's PATH, so the packaged app configures the full abaqus.bat
# path here. Read directly (not via core.config) to keep this a leaf module
# with no intra-repo imports.
ENV_ABAQUS_CMD = "ABAQUS_AGENT_ABAQUS_CMD"

# Lets a caller state the release without paying for the probe (CI, packaging).
ENV_ABAQUS_RELEASE = "ABAQUS_AGENT_ABAQUS_RELEASE"

_release_cache: str | None | tuple = ()  # () = not probed yet; None = unknown


def get_abaqus_cmd() -> str:
    """
    Return the resolved path to the ``abaqus`` executable.

    Resolution order:
      1. ``ABAQUS_AGENT_ABAQUS_CMD`` env (explicit full path, packaged mode)
      2. ``shutil.which("abaqus")`` — handles ``.bat`` / ``.cmd`` via PATHEXT
      3. literal ``"abaqus"`` fallback so callers still get a meaningful
         FileNotFoundError from subprocess.
    """
    override = os.environ.get(ENV_ABAQUS_CMD)
    if override and override.strip():
        return override.strip()
    resolved = shutil.which("abaqus")
    return resolved if resolved else "abaqus"


def detect_abaqus_release(timeout: float = 90.0, force: bool = False) -> str | None:
    """Return the release the *installed* solver actually reports, e.g. "2021".

    Never trust a release number carried in a spec: it is user-supplied metadata
    that nothing validates, so it drifts from the machine and then gets printed
    next to real solver output. On this repo it had drifted to "2024" while the
    box runs 2021 — visible side by side in a screen recording.

    Returns None when Abaqus is absent or unparseable; callers must treat that as
    "unknown", never as a default year. Result is cached for the process.
    """
    global _release_cache
    if not force and _release_cache != ():
        return _release_cache  # type: ignore[return-value]

    stated = os.environ.get(ENV_ABAQUS_RELEASE, "").strip()
    if stated:
        _release_cache = stated
        return stated

    try:
        proc = subprocess.run(
            [get_abaqus_cmd(), "information=release"],
            capture_output=True, text=True, errors="replace",
            stdin=subprocess.DEVNULL, timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError):
        _release_cache = None
        return None

    # The banner prints e.g. "Abaqus 2021" or "Abaqus 2024 HF4".
    match = re.search(r"\bAbaqus\s+(\d{4})\b", (proc.stdout or "") + (proc.stderr or ""))
    _release_cache = match.group(1) if match else None
    return _release_cache  # type: ignore[return-value]
