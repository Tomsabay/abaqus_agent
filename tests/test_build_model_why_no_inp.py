"""A missing .inp has to say what stopped the build.

Hermetic — nothing here starts Abaqus. The real crash is item 7 of
scripts/run_dropped_input_check.py: a dispatched `FluidPipeSection` with a
step-scoped region takes ABQcaeK.exe down with EXCEPTION_ACCESS_VIOLATION.

That is not a Python exception, so no gate in the generated deck can catch it,
and the launcher returns 0 as it always does. The only signal is the file that
is not there — and the message for that used to be ".inp not generated after CAE
run, check the log", with an empty snippet and a suggestion to simplify the
geometry, which is advice for a different problem.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from runner.build_model import _why_no_inp  # noqa: E402


def test_a_kernel_crash_is_named_as_one(tmp_path):
    (tmp_path / "build_model_script.log").write_text(
        "Abaqus License Manager checked out\n"
        "EXCEPTION_ACCESS_VIOLATION at pc=0x00007ffc\n", encoding="utf-8")
    why, _ = _why_no_inp(tmp_path)
    assert "EXCEPTION_ACCESS_VIOLATION" in why
    assert "not a bad spec value" in why


def test_the_crash_is_found_in_fort_7_as_well(tmp_path):
    """The kernel sometimes writes it there and nowhere else."""
    (tmp_path / "fort.7").write_text("EXCEPTION_ACCESS_VIOLATION\n",
                                     encoding="utf-8")
    why, _ = _why_no_inp(tmp_path)
    assert "EXCEPTION_ACCESS_VIOLATION" in why


def test_it_says_what_was_being_built_when_it_stopped(tmp_path):
    (tmp_path / "selectors.log").write_text(
        "GENERIC_OK: condition 1 EncastreBC\n"
        "GENERIC_START: condition 2 FluidPipeSection\n", encoding="utf-8")
    why, snippet = _why_no_inp(tmp_path)
    assert "FluidPipeSection" in why
    assert "selectors.log stops after" in snippet


def test_the_last_abaqus_error_line_reaches_the_snippet(tmp_path):
    (tmp_path / "build_model_script.log").write_text(
        "starting\nKeywordError: unknown keyword tractionType\n",
        encoding="utf-8")
    _, snippet = _why_no_inp(tmp_path)
    assert "tractionType" in snippet


def test_an_empty_workdir_still_says_something_actionable(tmp_path):
    """No crash marker and no refusal: the deck ran to the end and wrote
    nothing, which is a different problem and has to read as one."""
    why, snippet = _why_no_inp(tmp_path)
    assert "ran to the end without writing the file" in why
    assert snippet == ""
