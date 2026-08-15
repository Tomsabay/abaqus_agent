"""Text-mode subprocess calls must never die on a byte the solver printed.

Measured defect: runner/submit_job.py used `text=True` with no explicit
codec, so Python decoded Abaqus/Explicit's output as UTF-8. On a Chinese
Windows the solver emits system-codepage bytes, and both explicit_impact and
blast_plate died with

    UnicodeDecodeError: 'utf-8' codec can't decode byte 0xd4 in position 341

The failure lands in subprocess's reader THREAD, so it surfaced as a bare
status ERROR / error_code UNKNOWN with no log file — after a real solve had
already been paid for. Two of seven shipped cases could not finish.

This is a source-level contract because reproducing it needs a non-UTF-8
system locale, which the hermetic suite does not have.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from tests.repo_sources import is_captured_artefact

ROOT = Path(__file__).resolve().parent.parent

# Modules that shell out to Abaqus, CalculiX, node or our own CLI — anything
# whose output can carry a byte outside ASCII.
#
# `evidence` was missing from this list while server.py and mcp_bridge.py both
# carried the evidence artifact code inline; moving that code into
# evidence/artifact_registry.py would have walked it straight out of this
# gate's field of view. Nothing under evidence/ shells out today, which is
# exactly when a list like this is cheap to correct.
PRODUCTION_DIRS = ("runner", "post", "core", "agent", "copilot", "doctor",
                   "evidence", "features", "reporting", "tools", "validation",
                   "workbench")
PRODUCTION_FILES = ("server.py", "mcp_server.py", "mcp_bridge.py", "cli.py")


def _production_sources() -> list[Path]:
    files: list[Path] = []
    for name in PRODUCTION_FILES:
        path = ROOT / name
        if path.is_file():
            files.append(path)
    for folder in PRODUCTION_DIRS:
        base = ROOT / folder
        if base.is_dir():
            files.extend(path for path in sorted(base.rglob("*.py"))
                         if not is_captured_artefact(path.relative_to(ROOT)))
    return files


def _text_mode_calls_without_errors(path: Path) -> list[tuple[int, str]]:
    """(lineno, callee) for every text-mode subprocess call lacking errors=."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:                      # py2.7 kernel-side helpers
        return []

    offenders = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Attribute):
            continue
        if func.attr not in ("run", "Popen", "check_output"):
            continue
        if not (isinstance(func.value, ast.Name) and func.value.id == "subprocess"):
            continue

        kwargs = {kw.arg: kw.value for kw in node.keywords if kw.arg}
        text_mode = any(
            isinstance(kwargs.get(key), ast.Constant) and kwargs[key].value is True
            for key in ("text", "universal_newlines")
        )
        if text_mode and "errors" not in kwargs:
            offenders.append((node.lineno, "subprocess." + func.attr))
    return offenders


def test_no_production_subprocess_can_die_on_a_decode_error():
    offenders = []
    for path in _production_sources():
        for lineno, callee in _text_mode_calls_without_errors(path):
            offenders.append("%s:%d %s" % (path.relative_to(ROOT).as_posix(),
                                           lineno, callee))
    assert not offenders, (
        "text-mode subprocess without errors= — one non-UTF-8 byte from the "
        "solver crashes the run in a reader thread:\n  " + "\n  ".join(offenders))


@pytest.mark.parametrize("module", [
    "runner/submit_job.py",
    "runner/syntaxcheck.py",
    "post/extract_kpis.py",
])
def test_the_solver_facing_calls_name_their_codec(module):
    """errors= alone still leaves the codec to locale luck; pin both."""
    source = (ROOT / module).read_text(encoding="utf-8")
    assert 'errors="replace"' in source, module
    assert 'encoding="utf-8"' in source, module
