"""
log_parser.py
-------------
Structured parser for Abaqus diagnostic files (.msg, .sta, .dat).

Extracts error events, convergence issues, and diagnostic information
into a structured format for LLM analysis.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class DiagnosticSeverity(str, Enum):
    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"


class DiagnosticCategory(str, Enum):
    CONVERGENCE = "CONVERGENCE"
    ELEMENT_DISTORTION = "ELEMENT_DISTORTION"
    CONTACT = "CONTACT"
    RIGID_BODY_MOTION = "RIGID_BODY_MOTION"
    MEMORY = "MEMORY"
    NUMERICAL = "NUMERICAL"
    MATERIAL = "MATERIAL"
    BOUNDARY = "BOUNDARY"
    UNKNOWN = "UNKNOWN"


@dataclass
class DiagnosticEvent:
    """A single diagnostic event extracted from Abaqus log files."""
    severity: DiagnosticSeverity
    category: DiagnosticCategory
    message: str
    source_file: str = ""
    line_number: int = 0
    step: int = 0
    increment: int = 0
    iteration: int = 0
    details: dict = field(default_factory=dict)


@dataclass
class ParseResult:
    """Complete parse result from all diagnostic files."""
    events: list[DiagnosticEvent] = field(default_factory=list)
    last_increment: dict = field(default_factory=dict)
    total_time: float = 0.0
    completed: bool = False
    raw_snippets: dict = field(default_factory=dict)

    @property
    def errors(self) -> list[DiagnosticEvent]:
        return [e for e in self.events if e.severity == DiagnosticSeverity.ERROR]

    @property
    def warnings(self) -> list[DiagnosticEvent]:
        return [e for e in self.events if e.severity == DiagnosticSeverity.WARNING]

    @property
    def primary_category(self) -> DiagnosticCategory:
        """Most common error category."""
        if not self.errors:
            return DiagnosticCategory.UNKNOWN
        cats = [e.category for e in self.errors]
        return max(set(cats), key=cats.count)

    def to_llm_context(self, max_chars: int = 3000) -> str:
        """Format for LLM consumption."""
        parts = []
        parts.append(f"Completed: {self.completed}")
        parts.append(f"Last increment: {self.last_increment}")
        parts.append(f"Errors ({len(self.errors)}):")
        for e in self.errors[:10]:
            parts.append(f"  [{e.category.value}] {e.message}")
        if self.warnings:
            parts.append(f"Warnings ({len(self.warnings)}):")
            for w in self.warnings[:5]:
                parts.append(f"  [{w.category.value}] {w.message}")
        for name, snippet in self.raw_snippets.items():
            parts.append(f"\n--- {name} (last 500 chars) ---")
            parts.append(snippet[-500:])
        result = "\n".join(parts)
        return result[:max_chars]


def parse_job_diagnostics(workdir: str | Path, job_name: str) -> ParseResult:
    """
    Parse all diagnostic files for a job.

    Looks for: {job_name}.msg, {job_name}.sta, {job_name}.dat, {job_name}.log
    """
    workdir = Path(workdir)
    result = ParseResult()

    # Parse .msg file (most detailed diagnostics)
    msg_path = workdir / f"{job_name}.msg"
    if msg_path.exists():
        _parse_msg(msg_path, result)

    # Parse .sta file (status/increment tracking)
    sta_path = workdir / f"{job_name}.sta"
    if sta_path.exists():
        _parse_sta(sta_path, result)

    # Parse .dat file (data check errors)
    dat_path = workdir / f"{job_name}.dat"
    if dat_path.exists():
        _parse_dat(dat_path, result)

    # Parse .log file (general execution log)
    log_path = workdir / f"{job_name}.log"
    if log_path.exists():
        content = log_path.read_text(encoding="utf-8", errors="replace")
        result.raw_snippets["log"] = content[-2000:]
        if "COMPLETED" in content:
            result.completed = True

    return result


# -----------------------------------------------------------------
# .msg parser
# -----------------------------------------------------------------

_MSG_PATTERNS = [
    (re.compile(r"(?:THE SOLUTION HAS NOT CONVERGED|NOT CONVERGED)", re.I),
     DiagnosticCategory.CONVERGENCE, DiagnosticSeverity.ERROR),
    (re.compile(r"(?:EXCESSIVE DISTORTION|DISTORTED ELEMENTS?)", re.I),
     DiagnosticCategory.ELEMENT_DISTORTION, DiagnosticSeverity.ERROR),
    (re.compile(r"(?:ZERO PIVOT|SINGULAR MATRIX|NUMERICAL SINGULARITY)", re.I),
     DiagnosticCategory.RIGID_BODY_MOTION, DiagnosticSeverity.ERROR),
    (re.compile(r"(?:CONTACT (?:OPENING|OVERCLOSURE|CHATTERING))", re.I),
     DiagnosticCategory.CONTACT, DiagnosticSeverity.WARNING),
    (re.compile(r"(?:NEGATIVE EIGENVALUE)", re.I),
     DiagnosticCategory.NUMERICAL, DiagnosticSeverity.WARNING),
    (re.compile(r"(?:MATERIAL FAILURE|DAMAGE INITIATION)", re.I),
     DiagnosticCategory.MATERIAL, DiagnosticSeverity.WARNING),
    (re.compile(r"(?:TIME INCREMENT .* LESS THAN MINIMUM)", re.I),
     DiagnosticCategory.CONVERGENCE, DiagnosticSeverity.ERROR),
    (re.compile(r"(?:CONVERGENCE TOLERANCE EXCEEDED)", re.I),
     DiagnosticCategory.CONVERGENCE, DiagnosticSeverity.WARNING),
]

_STEP_INC_PATTERN = re.compile(
    r"STEP\s+(\d+)\s+INCREMENT\s+(\d+)", re.I
)


def _parse_msg(path: Path, result: ParseResult) -> None:
    """Parse .msg file for diagnostic events."""
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return

    result.raw_snippets["msg"] = content[-2000:]

    current_step = 0
    current_inc = 0

    for line in content.splitlines():
        # Track step/increment
        m = _STEP_INC_PATTERN.search(line)
        if m:
            current_step = int(m.group(1))
            current_inc = int(m.group(2))

        # Check error patterns
        for pattern, category, severity in _MSG_PATTERNS:
            if pattern.search(line):
                result.events.append(DiagnosticEvent(
                    severity=severity,
                    category=category,
                    message=line.strip()[:200],
                    source_file=str(path.name),
                    step=current_step,
                    increment=current_inc,
                ))
                break


# -----------------------------------------------------------------
# .sta parser
# -----------------------------------------------------------------

_STA_LINE_PATTERN = re.compile(
    r"\s*(\d+)\s+(\d+)\s+(\d+)\s+([\d.E+-]+)\s+([\d.E+-]+)"
)


def _parse_sta(path: Path, result: ParseResult) -> None:
    """Parse .sta file for status tracking."""
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return

    result.raw_snippets["sta"] = content[-1000:]

    last_match = None
    for line in content.splitlines():
        m = _STA_LINE_PATTERN.search(line)
        if m:
            last_match = {
                "step": int(m.group(1)),
                "increment": int(m.group(2)),
                "attempt": int(m.group(3)),
                "step_time": m.group(4),
                "total_time": m.group(5),
            }

    if last_match:
        result.last_increment = last_match
        try:
            result.total_time = float(last_match["total_time"])
        except (ValueError, KeyError):
            pass


# -----------------------------------------------------------------
# .dat parser
# -----------------------------------------------------------------

_DAT_ERROR_PATTERNS = [
    (re.compile(r"\*\*\*ERROR", re.I), DiagnosticSeverity.ERROR),
    (re.compile(r"\*\*\*WARNING", re.I), DiagnosticSeverity.WARNING),
    (re.compile(r"(?:MEMORY LIMIT|INSUFFICIENT MEMORY)", re.I), DiagnosticSeverity.ERROR),
]


def _parse_dat(path: Path, result: ParseResult) -> None:
    """Parse .dat file for data check errors."""
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return

    result.raw_snippets["dat"] = content[-1000:]

    for line in content.splitlines():
        for pattern, severity in _DAT_ERROR_PATTERNS:
            if pattern.search(line):
                category = DiagnosticCategory.MEMORY if "MEMORY" in line.upper() else DiagnosticCategory.UNKNOWN
                result.events.append(DiagnosticEvent(
                    severity=severity,
                    category=category,
                    message=line.strip()[:200],
                    source_file=str(path.name),
                ))
                break
