"""Tests for validation matrix evidence recording."""

from __future__ import annotations

from validation.matrix import (
    append_validation_matrix_entry,
    build_validation_evidence_entry,
    insert_validation_matrix_row,
    render_validation_matrix_row,
)

MATRIX = """# Validation Matrix

## Current Evidence

| Date | Environment | Abaqus | Case / Workflow | Result | Evidence |
|---|---|---|---|---|---|
| 2026-06-01 | Existing | Not installed | tests | PASS | old |

## Public Case Coverage
"""


def test_render_validation_matrix_row_escapes_cells():
    entry = build_validation_evidence_entry(
        entry_date="2026-06-02",
        environment="Linux | runner",
        abaqus="Abaqus 2026",
        workflow="syntaxcheck",
        result="PASS",
        evidence="line one\nline two",
    )

    row = render_validation_matrix_row(entry)

    assert row == "| 2026-06-02 | Linux \\| runner | Abaqus 2026 | syntaxcheck | PASS | line one line two |"


def test_insert_validation_matrix_row_before_next_section():
    row = "| 2026-06-02 | macOS | Not installed | dry-run | PASS | 5 / 5 |"

    updated = insert_validation_matrix_row(MATRIX, row)

    assert "| 2026-06-01 | Existing | Not installed | tests | PASS | old |\n" + row in updated
    assert row + "\n\n## Public Case Coverage" in updated


def test_append_validation_matrix_entry(tmp_path):
    matrix = tmp_path / "VALIDATION_MATRIX.md"
    matrix.write_text(MATRIX, encoding="utf-8")
    entry = build_validation_evidence_entry(
        entry_date="2026-06-02",
        environment="Windows",
        abaqus="Abaqus 2021",
        workflow="cantilever",
        result="PASS",
        evidence="status=COMPLETED",
    )

    result = append_validation_matrix_entry(matrix, entry)

    assert result["matrix_path"] == str(matrix)
    assert result["row"] in matrix.read_text(encoding="utf-8")
