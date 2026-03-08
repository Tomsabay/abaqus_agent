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

import shutil


def get_abaqus_cmd() -> str:
    """
    Return the resolved path to the ``abaqus`` executable.

    Uses ``shutil.which`` to locate the command, which handles
    ``.bat`` / ``.cmd`` extensions on Windows via PATHEXT.

    Returns the full path string (e.g. ``C:\\...\\abaqus.bat``),
    or ``"abaqus"`` as fallback so callers still get a meaningful
    FileNotFoundError from subprocess.
    """
    resolved = shutil.which("abaqus")
    return resolved if resolved else "abaqus"
