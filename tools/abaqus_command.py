"""Resolve the Abaqus command in a way that works on Windows and POSIX."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

ABAQUS_COMMAND_ENV_KEYS = (
    "ABAQUS_EXECUTABLE",
    "ABAQUS_COMMAND",
    "ABAQUS_PATH",
)


def get_abaqus_command() -> str:
    """Return the configured Abaqus command path/name.

    When no command can be resolved, return the legacy command name so callers
    keep their existing subprocess FileNotFoundError handling paths.
    """
    for key in ABAQUS_COMMAND_ENV_KEYS:
        value = os.environ.get(key)
        if value:
            expanded = Path(value).expanduser()
            if expanded.exists():
                return str(expanded)
            found = shutil.which(value)
            if found:
                return found

    for candidate in ("abaqus", "abaqus.bat"):
        found = shutil.which(candidate)
        if found:
            return found

    return "abaqus"
