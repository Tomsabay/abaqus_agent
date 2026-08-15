"""Helpers for recording validation evidence in the project matrix."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path


@dataclass(frozen=True)
class ValidationEvidenceEntry:
    """One row of the validation evidence matrix."""

    date: str
    environment: str
    abaqus: str
    workflow: str
    result: str
    evidence: str


def build_validation_evidence_entry(
    *,
    environment: str,
    abaqus: str,
    workflow: str,
    result: str,
    evidence: str,
    entry_date: str = "",
) -> ValidationEvidenceEntry:
    """Build a normalized validation evidence row."""
    return ValidationEvidenceEntry(
        date=entry_date or date.today().isoformat(),
        environment=_required(environment, "environment"),
        abaqus=_required(abaqus, "abaqus"),
        workflow=_required(workflow, "workflow"),
        result=_required(result, "result"),
        evidence=_required(evidence, "evidence"),
    )


def render_validation_matrix_row(entry: ValidationEvidenceEntry) -> str:
    """Render a Markdown table row for a validation matrix."""
    cells = [
        entry.date,
        entry.environment,
        entry.abaqus,
        entry.workflow,
        entry.result,
        entry.evidence,
    ]
    return "| " + " | ".join(_escape_cell(cell) for cell in cells) + " |"


def append_validation_matrix_entry(matrix_path: str | Path, entry: ValidationEvidenceEntry) -> dict[str, str]:
    """Append an evidence row to the Current Evidence table."""
    path = Path(matrix_path)
    text = path.read_text(encoding="utf-8")
    row = render_validation_matrix_row(entry)
    updated = insert_validation_matrix_row(text, row)
    path.write_text(updated, encoding="utf-8")
    return {"matrix_path": str(path), "row": row}


def insert_validation_matrix_row(markdown: str, row: str) -> str:
    """Insert a rendered evidence row after the Current Evidence table body."""
    lines = markdown.splitlines()
    table_start = _find_current_evidence_table(lines)
    insert_at = table_start
    while insert_at < len(lines) and lines[insert_at].startswith("|"):
        insert_at += 1
    lines.insert(insert_at, row)
    return "\n".join(lines) + ("\n" if markdown.endswith("\n") else "")


def _find_current_evidence_table(lines: list[str]) -> int:
    in_section = False
    for idx, line in enumerate(lines):
        if line.strip() == "## Current Evidence":
            in_section = True
            continue
        if in_section and line.startswith("| Date | Environment |"):
            if idx + 2 >= len(lines) or not lines[idx + 1].startswith("|---"):
                raise ValueError("Current Evidence table separator not found")
            return idx + 2
    raise ValueError("Current Evidence table not found")


def _escape_cell(value: str) -> str:
    text = " ".join(str(value).split())
    return text.replace("|", "\\|")


def _required(value: str, name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{name} is required")
    return text
