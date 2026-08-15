"""
solver_doctor.py
----------------
Deterministic Solver Doctor report over Abaqus log artifacts.

This module does not invoke Abaqus and does not call an LLM. It turns existing
.msg/.sta/.dat/.log files into a small JSON/Markdown evidence report that can be
attached to smoke runs, support handoffs, or user bug reports.
"""

from __future__ import annotations

import argparse
import json
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from features.autorepair.log_parser import (
    DiagnosticCategory,
    DiagnosticEvent,
    DiagnosticSeverity,
    list_diagnostic_pattern_specs,
    parse_job_diagnostics,
)

_CATEGORY_GUIDANCE: dict[DiagnosticCategory, tuple[str, str]] = {
    DiagnosticCategory.CONVERGENCE: (
        "Solver did not converge or cut increments below the minimum.",
        "Reduce initial increments, check nonlinear controls, inspect contact/material behavior, and rerun syntaxcheck before another solver attempt.",
    ),
    DiagnosticCategory.ELEMENT_DISTORTION: (
        "Elements became distorted or invalid during the solve.",
        "Refine or remesh the affected region, reduce load increments, and inspect material/contact definitions near the reported elements.",
    ),
    DiagnosticCategory.RIGID_BODY_MOTION: (
        "The model appears under-constrained or numerically singular.",
        "Audit boundary conditions, coupling constraints, reference points, and stabilization before resubmitting.",
    ),
    DiagnosticCategory.CONTACT: (
        "Contact setup produced warnings or unstable behavior.",
        "Inspect contact pairs, initial overclosure/gaps, normal behavior, and consider contact stabilization with smaller increments.",
    ),
    DiagnosticCategory.MEMORY: (
        "The solver reported insufficient memory or resource pressure.",
        "Increase memory allocation, reduce model size/output frequency, or split the analysis.",
    ),
    DiagnosticCategory.NUMERICAL: (
        "The solver reported numerical instability.",
        "Check material stiffness, constraints, mesh quality, units, and step controls.",
    ),
    DiagnosticCategory.MATERIAL: (
        "Material behavior or damage criteria triggered diagnostic warnings.",
        "Review material parameters, units, failure limits, and load magnitudes.",
    ),
    DiagnosticCategory.BOUNDARY: (
        "Boundary conditions or loads appear inconsistent.",
        "Verify load/BC regions, amplitudes, directions, and step activation.",
    ),
    DiagnosticCategory.LICENSE: (
        "Abaqus license checkout or license server access failed.",
        "Check license server reachability, token availability, DSLS/FLEXnet configuration, and retry with queue policy set intentionally.",
    ),
    DiagnosticCategory.ODB: (
        "ODB creation, opening, or version compatibility failed.",
        "Confirm the job wrote an ODB, run the upgrade helper when versions differ, and retry KPI extraction inside Abaqus Python.",
    ),
    DiagnosticCategory.PATH: (
        "A file path, working directory, or command path failed.",
        "Shorten paths, avoid special characters, verify job/input filenames, and run from a simple local work directory.",
    ),
    DiagnosticCategory.SYNTAX: (
        "The input deck contains keyword, parameter, or data syntax errors.",
        "Run Abaqus syntaxcheck, inspect the reported keyword/data line, and fix the input deck before submitting.",
    ),
    DiagnosticCategory.MESH: (
        "Mesh quality or element definition diagnostics were reported.",
        "Inspect mesh quality, element type compatibility, section assignments, and distorted/zero-volume elements.",
    ),
    DiagnosticCategory.OUTPUT: (
        "Requested output could not be produced or written.",
        "Review output requests, disk space, write permissions, and whether the requested variables exist for the step.",
    ),
    DiagnosticCategory.UNKNOWN: (
        "No known Solver Doctor pattern matched the failure.",
        "Inspect .msg/.dat/.log snippets manually and add a new diagnostic pattern if this is recurring.",
    ),
}


_SEVERITY_RANK = {
    DiagnosticSeverity.ERROR: 3,
    DiagnosticSeverity.WARNING: 2,
    DiagnosticSeverity.INFO: 1,
}


@dataclass(frozen=True)
class DoctorFinding:
    severity: str
    category: str
    message: str
    source_file: str
    line_number: int
    step: int
    increment: int
    explanation: str
    recommendation: str

    @classmethod
    def from_event(cls, event: DiagnosticEvent) -> DoctorFinding:
        explanation, recommendation = _CATEGORY_GUIDANCE.get(
            event.category,
            _CATEGORY_GUIDANCE[DiagnosticCategory.UNKNOWN],
        )
        return cls(
            severity=event.severity.value,
            category=event.category.value,
            message=event.message,
            source_file=event.source_file,
            line_number=event.line_number,
            step=event.step,
            increment=event.increment,
            explanation=explanation,
            recommendation=recommendation,
        )

    def to_dict(self) -> dict:
        return {
            "severity": self.severity,
            "category": self.category,
            "message": self.message,
            "source_file": self.source_file,
            "line_number": self.line_number,
            "step": self.step,
            "increment": self.increment,
            "explanation": self.explanation,
            "recommendation": self.recommendation,
        }


@dataclass(frozen=True)
class SolverDoctorReport:
    job_name: str
    workdir: str
    status: str
    summary: str
    primary_category: str
    completed: bool
    last_increment: dict
    total_time: float
    findings: list[DoctorFinding]
    evidence_files: list[str]

    def to_dict(self) -> dict:
        return {
            "job_name": self.job_name,
            "workdir": self.workdir,
            "status": self.status,
            "summary": self.summary,
            "primary_category": self.primary_category,
            "completed": self.completed,
            "last_increment": self.last_increment,
            "total_time": self.total_time,
            "evidence_files": self.evidence_files,
            "findings": [finding.to_dict() for finding in self.findings],
        }


def diagnose_job_logs(workdir: str | Path, job_name: str) -> SolverDoctorReport:
    """Create a deterministic Solver Doctor report from existing Abaqus log files."""
    workdir_path = Path(workdir)
    parse_result = parse_job_diagnostics(workdir_path, job_name)
    findings = [DoctorFinding.from_event(event) for event in parse_result.events]
    findings.sort(
        key=lambda finding: (
            -_severity_rank(finding.severity),
            finding.source_file,
            finding.line_number,
        )
    )

    primary_category = _primary_category(findings)
    status = _status(parse_result.completed, findings)
    summary = _summary(status, primary_category, findings)
    evidence_files = [
        str(workdir_path / f"{job_name}{suffix}")
        for suffix in (".msg", ".sta", ".dat", ".log")
        if (workdir_path / f"{job_name}{suffix}").exists()
    ]

    return SolverDoctorReport(
        job_name=job_name,
        workdir=str(workdir_path),
        status=status,
        summary=summary,
        primary_category=primary_category,
        completed=parse_result.completed,
        last_increment=parse_result.last_increment,
        total_time=parse_result.total_time,
        findings=findings,
        evidence_files=evidence_files,
    )


def diagnose_log_texts(
    *,
    job_name: str,
    logs: Mapping[str, str],
    workdir: str | Path | None = None,
) -> SolverDoctorReport:
    """Create a Solver Doctor report from supplied log text snippets."""
    safe_job_name = validate_job_name(job_name)
    workdir_path = Path(workdir) if workdir is not None else Path(tempfile.mkdtemp(prefix="abaqus-agent-doctor."))
    workdir_path.mkdir(parents=True, exist_ok=True)

    wrote_any = False
    for suffix, text in logs.items():
        normalized_suffix = _normalize_log_suffix(suffix)
        if not normalized_suffix or not text:
            continue
        (workdir_path / f"{safe_job_name}{normalized_suffix}").write_text(
            text,
            encoding="utf-8",
        )
        wrote_any = True
    if not wrote_any:
        raise ValueError("At least one non-empty .msg/.dat/.sta/.log text is required")
    return diagnose_job_logs(workdir_path, safe_job_name)


def list_doctor_patterns(
    *,
    category: str = "",
    severity: str = "",
) -> dict:
    """Return the discoverable Solver Doctor diagnostic pattern catalog."""
    normalized_category = category.strip().upper()
    normalized_severity = severity.strip().upper()
    patterns = []
    for pattern in list_diagnostic_pattern_specs():
        if normalized_category and pattern["category"] != normalized_category:
            continue
        if normalized_severity and pattern["severity"] != normalized_severity:
            continue
        explanation, recommendation = _CATEGORY_GUIDANCE.get(
            DiagnosticCategory(pattern["category"]),
            _CATEGORY_GUIDANCE[DiagnosticCategory.UNKNOWN],
        )
        patterns.append(
            {
                **pattern,
                "explanation": explanation,
                "recommendation": recommendation,
                "real_env_verified": False,
            }
        )

    all_patterns = list_diagnostic_pattern_specs()
    category_counts: dict[str, int] = {}
    for pattern in all_patterns:
        category_counts[pattern["category"]] = category_counts.get(pattern["category"], 0) + 1

    categories = []
    for diagnostic_category in DiagnosticCategory:
        explanation, recommendation = _CATEGORY_GUIDANCE.get(
            diagnostic_category,
            _CATEGORY_GUIDANCE[DiagnosticCategory.UNKNOWN],
        )
        categories.append(
            {
                "category": diagnostic_category.value,
                "pattern_count": category_counts.get(diagnostic_category.value, 0),
                "explanation": explanation,
                "recommendation": recommendation,
            }
        )

    return {
        "schema_version": "1.0",
        "workflow": "solver-doctor-pattern-gallery",
        "real_env_verified": False,
        "filters": {
            "category": normalized_category,
            "severity": normalized_severity,
        },
        "categories": categories,
        "patterns": patterns,
        "total": len(patterns),
        "supported_source_files": [".msg", ".dat", ".sta", ".log"],
    }


def validate_job_name(job_name: str) -> str:
    safe_job_name = job_name.strip()
    if not safe_job_name:
        raise ValueError("job_name is required")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", safe_job_name):
        raise ValueError("job_name may contain only letters, numbers, dot, underscore, and dash")
    if safe_job_name in {".", ".."}:
        raise ValueError("job_name is invalid")
    return safe_job_name


def render_markdown(report: SolverDoctorReport) -> str:
    """Render a Solver Doctor report as Markdown."""
    lines = [
        f"# Solver Doctor: {report.job_name}",
        "",
        f"- Status: `{report.status}`",
        f"- Primary category: `{report.primary_category}`",
        f"- Completed: `{str(report.completed).lower()}`",
        f"- Summary: {report.summary}",
    ]
    if report.last_increment:
        lines.append(f"- Last increment: `{json.dumps(report.last_increment, sort_keys=True)}`")
    if report.evidence_files:
        lines.extend(["", "## Evidence Files"])
        lines.extend(f"- `{path}`" for path in report.evidence_files)
    lines.extend(
        [
            "",
            "## Findings",
            "",
            "| Severity | Category | Source | Message | Recommendation |",
            "|---|---|---|---|---|",
        ]
    )
    if not report.findings:
        lines.append("| INFO | UNKNOWN | - | No recognized Solver Doctor finding. | Inspect logs manually if the job failed. |")
    for finding in report.findings:
        source = finding.source_file
        if finding.line_number:
            source = f"{source}:{finding.line_number}"
        lines.append(
            "| {severity} | {category} | {source} | {message} | {recommendation} |".format(
                severity=_escape_md(finding.severity),
                category=_escape_md(finding.category),
                source=_escape_md(source),
                message=_escape_md(finding.message),
                recommendation=_escape_md(finding.recommendation),
            )
        )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Diagnose Abaqus solver log artifacts.")
    parser.add_argument("workdir", help="Directory containing <job_name>.msg/.sta/.dat/.log")
    parser.add_argument("job_name", help="Abaqus job name without extension")
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    parser.add_argument("--out", help="Optional output path")
    args = parser.parse_args(argv)

    report = diagnose_job_logs(args.workdir, args.job_name)
    if args.format == "markdown":
        output = render_markdown(report)
    else:
        output = json.dumps(report.to_dict(), indent=2, sort_keys=True)
        output += "\n"

    if args.out:
        Path(args.out).write_text(output, encoding="utf-8")
    else:
        print(output, end="")
    return 0


def _severity_rank(severity: str) -> int:
    try:
        return _SEVERITY_RANK[DiagnosticSeverity(severity)]
    except ValueError:
        return 0


def _primary_category(findings: list[DoctorFinding]) -> str:
    errors = [finding for finding in findings if finding.severity == DiagnosticSeverity.ERROR.value]
    candidates = errors or findings
    if not candidates:
        return DiagnosticCategory.UNKNOWN.value
    counts: dict[str, int] = {}
    for finding in candidates:
        counts[finding.category] = counts.get(finding.category, 0) + 1
    return max(counts, key=counts.get)


def _status(completed: bool, findings: list[DoctorFinding]) -> str:
    if any(finding.severity == DiagnosticSeverity.ERROR.value for finding in findings):
        return "FAILED"
    if any(finding.severity == DiagnosticSeverity.WARNING.value for finding in findings):
        return "WARNING"
    if completed:
        return "COMPLETED"
    return "NO_FINDINGS"


def _summary(status: str, primary_category: str, findings: list[DoctorFinding]) -> str:
    error_count = sum(finding.severity == DiagnosticSeverity.ERROR.value for finding in findings)
    warning_count = sum(finding.severity == DiagnosticSeverity.WARNING.value for finding in findings)
    if findings:
        return (
            f"Detected {error_count} error(s) and {warning_count} warning(s); "
            f"primary category is {primary_category}."
        )
    if status == "COMPLETED":
        return "Job completed and no recognized Solver Doctor patterns were found."
    return "No recognized Solver Doctor patterns were found in available log artifacts."


def _escape_md(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def _normalize_log_suffix(suffix: str) -> str:
    normalized = suffix.strip().lower()
    if not normalized:
        return ""
    if not normalized.startswith("."):
        normalized = f".{normalized}"
    if normalized not in {".msg", ".dat", ".sta", ".log"}:
        raise ValueError(f"Unsupported log suffix: {suffix}")
    return normalized


if __name__ == "__main__":
    raise SystemExit(main())
