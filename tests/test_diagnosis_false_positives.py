"""A diagnosis card that fires on every successful run is not a diagnosis.

Two defects that shipped together and both read as "something went wrong" on
runs where nothing did:

  * every Abaqus/Standard .msg ends with a tally block, and one of its lines
    is "0  ANALYSIS WARNINGS ARE NEGATIVE EIGENVALUE MESSAGES". The pattern
    table matched the bare phrase, so every clean Standard run raised a
    NUMERICAL warning quoting a line that says the count is zero -- 326 of
    those lines across this repo's archived runs, every one of them zero;
  * `warnings` arrives as a count from one stage and as a list of texts from
    five others, and the stage-log formatter only handled the count. A list
    rendered with its Python repr on screen, and an empty list rendered as
    "⚠ [] warnings".

Hermetic: builds the log files it parses.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import re  # noqa: E402

from core.pipeline import _warning_lines  # noqa: E402
from features.autorepair import log_parser  # noqa: E402
from features.autorepair.log_parser import (  # noqa: E402
    DiagnosticCategory,
    DiagnosticSeverity,
    LogPattern,
    list_diagnostic_pattern_specs,
    parse_job_diagnostics,
)

# Verbatim from artifacts/runs_archive/.../BearingBlock.msg, including spacing.
TALLY_BLOCK = """
                       0  WARNING MESSAGES DURING ANALYSIS
                       0  ANALYSIS WARNINGS ARE NUMERICAL PROBLEM MESSAGES
                       0  ANALYSIS WARNINGS ARE NEGATIVE EIGENVALUE MESSAGES
                       0  ERROR MESSAGES
"""

REAL_WARNING = " ***WARNING: THE SYSTEM MATRIX HAS 2 NEGATIVE EIGENVALUES.\n"


def _numerical(tmp_path: Path, msg: str) -> list:
    (tmp_path / "J.msg").write_text(msg, encoding="utf-8")
    result = parse_job_diagnostics(tmp_path, "J")
    return [e for e in result.events if e.category.value.upper() == "NUMERICAL"]


def test_a_clean_run_reports_no_negative_eigenvalue_problem(tmp_path):
    assert _numerical(tmp_path, TALLY_BLOCK) == []


def test_the_real_per_increment_warning_still_fires(tmp_path):
    """The fix must not buy silence by suppressing the genuine warning. There
    are 740 of these in the archived runs."""
    events = _numerical(tmp_path, " STEP 1 INCREMENT 3\n" + REAL_WARNING + TALLY_BLOCK)

    assert len(events) == 1
    assert "2 NEGATIVE EIGENVALUES" in events[0].message
    assert events[0].step == 1 and events[0].increment == 3


def test_a_nonzero_tally_is_still_a_finding(tmp_path):
    events = _numerical(
        tmp_path, "                       7  ANALYSIS WARNINGS ARE NEGATIVE EIGENVALUE MESSAGES\n")

    assert len(events) == 1


def test_the_other_zero_valued_eigenvalue_lines_are_quiet_too(tmp_path):
    """Two more shapes Abaqus writes, both carrying their own count."""
    quiet = ("NUMBER OF NEGATIVE EIGENVALUES     0\n"
             "NUMBER OF NEGATIVE EIGENVALUES NOT ASSOCIATED WITH "
             "LAGRANGE MULTIPLIERS     0\n")

    assert _numerical(tmp_path, quiet) == []
    assert len(_numerical(tmp_path, "NUMBER OF NEGATIVE EIGENVALUES     4\n")) == 1


def test_a_conditional_pattern_says_so_in_the_public_catalogue():
    """/api/doctor exposes this list. A pattern that only fires under a
    condition reads as always-on unless the catalogue says otherwise."""
    conditional = [s for s in list_diagnostic_pattern_specs() if "only_when" in s]

    assert conditional, "no pattern advertises its condition"
    assert all("zero" in s["only_when"] for s in conditional)


def test_a_pattern_id_does_not_move_when_a_pattern_is_added(monkeypatch):
    """The ids were row numbers -- "msg-10-license". Adding the two counted
    eigenvalue patterns above it renamed it to "msg-12-license" and broke the
    offline smoke gate, which names it. The gate was right to fail: the
    Pattern Gallery and three shipped documents name patterns by id too."""
    before = {s["id"] for s in list_diagnostic_pattern_specs()}

    monkeypatch.setattr(log_parser, "_MSG_PATTERNS", [
        LogPattern("brand-new-first-row", re.compile(r"NOTHING MATCHES THIS"),
                   DiagnosticCategory.UNKNOWN, DiagnosticSeverity.INFO),
        *log_parser._MSG_PATTERNS,
    ])
    after = {s["id"] for s in list_diagnostic_pattern_specs()}

    assert after - before == {"msg-brand-new-first-row"}
    assert not before - after, "an existing pattern was renamed by the insert"


def test_every_pattern_id_is_unique():
    ids = [s["id"] for s in list_diagnostic_pattern_specs()]

    assert len(ids) == len(set(ids))
    assert "msg-license" in ids and "dat-license" in ids


# ── the stage log line ──────────────────────────────────────────────────────

def test_an_empty_warning_list_produces_no_line():
    """It used to produce "⚠ [] warnings" -- a warning that there were none."""
    assert _warning_lines([]) == []
    assert _warning_lines(0) == []
    assert _warning_lines(None) == []


def test_a_list_of_warnings_becomes_one_line_each():
    lines = _warning_lines(["85 tie nodes were left unconstrained",
                            "C3D8R hourglassing risk"])

    assert [line["text"] for line in lines] == [
        "⚠ 85 tie nodes were left unconstrained",
        "⚠ C3D8R hourglassing risk",
    ]
    assert all(line["level"] == "warn" for line in lines)
    # The defect was the repr reaching the screen.
    assert not any("[" in line["text"] for line in lines)


def test_a_count_still_reads_as_a_count():
    assert [line["text"] for line in _warning_lines(3)] == ["⚠ 3 warnings"]


def test_an_unexpected_shape_is_shown_rather_than_swallowed():
    assert [line["text"] for line in _warning_lines("disk full")] == ["⚠ disk full"]
