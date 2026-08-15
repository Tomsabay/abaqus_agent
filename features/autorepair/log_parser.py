"""
log_parser.py
-------------
Structured parser for Abaqus diagnostic files (.msg, .sta, .dat).

Extracts error events, convergence issues, and diagnostic information
into a structured format for LLM analysis.
"""

from __future__ import annotations

import re
from collections.abc import Callable
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
    LICENSE = "LICENSE"
    ODB = "ODB"
    PATH = "PATH"
    SYNTAX = "SYNTAX"
    MESH = "MESH"
    OUTPUT = "OUTPUT"
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

def _nonzero_count(match: "re.Match") -> bool:
    """Gate: report only when the number the pattern captured is not zero.

    Abaqus writes several diagnostic lines that name a phenomenon and then say
    how much of it happened. "0 of them" is not a finding.
    """
    try:
        return int(match.group("count")) != 0
    except (IndexError, ValueError, TypeError):
        return True  # unreadable count: report it rather than swallow it


_NONZERO_REASON = "the count it captures is not zero"


@dataclass(frozen=True)
class LogPattern:
    """One line shape the log parsers recognise.

    `slug` is the identity, and it is written down rather than derived from
    the row's position in the table, because the position moves. The
    catalogue used to number rows as it emitted them -- `msg-10-license` --
    so inserting the two counted negative-eigenvalue shapes below renamed
    every pattern after them. The Pattern Gallery, the offline smoke gate and
    three shipped documents all name patterns by id.

    `gate` exists because some lines name a phenomenon and then say how much
    of it happened; matching the phrase is not the same as finding a problem.
    A gate that refuses lets the line fall through to the patterns below
    rather than ending its search.
    """

    slug: str
    regex: "re.Pattern"
    category: DiagnosticCategory
    severity: DiagnosticSeverity
    gate: "Callable[[re.Match], bool] | None" = None
    gate_reason: str = ""

    def hit(self, line: str) -> bool:
        match = self.regex.search(line)
        if match is None:
            return False
        return self.gate is None or self.gate(match)


_MSG_PATTERNS = [
    LogPattern("not-converged",
               re.compile(r"(?:THE SOLUTION HAS NOT CONVERGED|NOT CONVERGED)", re.I),
               DiagnosticCategory.CONVERGENCE, DiagnosticSeverity.ERROR),
    LogPattern("too-many-attempts",
               re.compile(r"(?:TOO MANY ATTEMPTS MADE FOR THIS INCREMENT)", re.I),
               DiagnosticCategory.CONVERGENCE, DiagnosticSeverity.ERROR),
    LogPattern("excessive-distortion",
               re.compile(r"(?:EXCESSIVE DISTORTION|DISTORTED ELEMENTS?)", re.I),
               DiagnosticCategory.ELEMENT_DISTORTION, DiagnosticSeverity.ERROR),
    LogPattern("zero-or-negative-volume",
               re.compile(r"(?:ZERO|NEGATIVE) (?:ELEMENT )?VOLUME", re.I),
               DiagnosticCategory.MESH, DiagnosticSeverity.ERROR),
    LogPattern("zero-pivot",
               re.compile(r"(?:ZERO PIVOT|SINGULAR MATRIX|NUMERICAL SINGULARITY)", re.I),
               DiagnosticCategory.RIGID_BODY_MOTION, DiagnosticSeverity.ERROR),
    LogPattern("contact-instability",
               re.compile(r"(?:CONTACT (?:OPENING|OVERCLOSURE|CHATTERING))", re.I),
               DiagnosticCategory.CONTACT, DiagnosticSeverity.WARNING),
    # Negative eigenvalues appear on four line shapes and three of them carry
    # their own count. Matching the bare phrase raised a NUMERICAL warning on
    # every successful Abaqus/Standard run, because every .msg ends with a
    # tally block whose line reads
    #     0  ANALYSIS WARNINGS ARE NEGATIVE EIGENVALUE MESSAGES
    # -- 326 of those in this repo's archived runs, every one of them zero,
    # and the diagnosis card quoted the line verbatim while claiming a
    # problem. So: read the count, report only when it is not zero. The
    # genuine per-increment warning (740 in the archive) still fires. The
    # fourth shape, "NEGATIVE EIGENVALUES MEAN THAT THE SYSTEM MATRIX IS
    # NOT...", is the explanatory sentence Abaqus prints under the warning,
    # and is deliberately not a pattern of its own.
    LogPattern("system-matrix-negative-eigenvalues",
               re.compile(r"THE SYSTEM MATRIX HAS\s+(?P<count>\d+)\s+NEGATIVE EIGENVALUES?", re.I),
               DiagnosticCategory.NUMERICAL, DiagnosticSeverity.WARNING,
               _nonzero_count, _NONZERO_REASON),
    LogPattern("negative-eigenvalue-tally",
               re.compile(r"(?P<count>\d+)\s+ANALYSIS WARNINGS ARE NEGATIVE EIGENVALUE MESSAGES", re.I),
               DiagnosticCategory.NUMERICAL, DiagnosticSeverity.WARNING,
               _nonzero_count, _NONZERO_REASON),
    LogPattern("negative-eigenvalue-count",
               re.compile(r"NUMBER OF NEGATIVE EIGENVALUES[^\d]*(?P<count>\d+)", re.I),
               DiagnosticCategory.NUMERICAL, DiagnosticSeverity.WARNING,
               _nonzero_count, _NONZERO_REASON),
    LogPattern("material-failure",
               re.compile(r"(?:MATERIAL FAILURE|DAMAGE INITIATION)", re.I),
               DiagnosticCategory.MATERIAL, DiagnosticSeverity.WARNING),
    LogPattern("over-specified-boundary",
               re.compile(r"(?:BOUNDARY CONDITIONS? ARE OVER-?SPECIFIED|UNKNOWN NODE SET)", re.I),
               DiagnosticCategory.BOUNDARY, DiagnosticSeverity.ERROR),
    LogPattern("license",
               re.compile(r"(?:LICENSE CHECKOUT FAILED|LICENSE SERVER|NO LICENSE|TOKEN)", re.I),
               DiagnosticCategory.LICENSE, DiagnosticSeverity.ERROR),
    LogPattern("odb-unreadable",
               re.compile(r"(?:DATABASE WAS CREATED BY A NEWER RELEASE|ODB.*VERSION|CANNOT OPEN.*ODB)", re.I),
               DiagnosticCategory.ODB, DiagnosticSeverity.ERROR),
    LogPattern("path-not-found",
               re.compile(r"(?:PATH TOO LONG|CANNOT FIND THE PATH|NO SUCH FILE|FILE NOT FOUND)", re.I),
               DiagnosticCategory.PATH, DiagnosticSeverity.ERROR),
    LogPattern("keyword-error",
               re.compile(r"(?:UNKNOWN KEYWORD|INVALID KEYWORD|ERROR IN KEYWORD|Abaqus/Analysis exited with errors)", re.I),
               DiagnosticCategory.SYNTAX, DiagnosticSeverity.ERROR),
    LogPattern("output-not-written",
               re.compile(r"(?:OUTPUT REQUEST.*NOT AVAILABLE|OUTPUT DATABASE.*NOT WRITTEN)", re.I),
               DiagnosticCategory.OUTPUT, DiagnosticSeverity.WARNING),
    LogPattern("increment-below-minimum",
               re.compile(r"(?:TIME INCREMENT .* LESS THAN MINIMUM)", re.I),
               DiagnosticCategory.CONVERGENCE, DiagnosticSeverity.ERROR),
    LogPattern("tolerance-exceeded",
               re.compile(r"(?:CONVERGENCE TOLERANCE EXCEEDED)", re.I),
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

    for line_number, line in enumerate(content.splitlines(), start=1):
        # Track step/increment
        m = _STEP_INC_PATTERN.search(line)
        if m:
            current_step = int(m.group(1))
            current_inc = int(m.group(2))

        # Check error patterns
        for entry in _MSG_PATTERNS:
            if not entry.hit(line):
                continue
            result.events.append(DiagnosticEvent(
                severity=entry.severity,
                category=entry.category,
                message=line.strip()[:200],
                source_file=str(path.name),
                line_number=line_number,
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
    # "MEMORY LIMIT" alone matches the informational paragraph every .dat
    # contains; require actual exhaustion wording so healthy jobs don't get
    # a spurious MEMORY error finding.
    LogPattern("memory-exhausted",
               re.compile(r"(?:INSUFFICIENT MEMORY|OUT OF MEMORY|MEMORY LIMIT.{0,40}EXCEEDED|EXCEED.{0,40}MEMORY LIMIT)", re.I),
               DiagnosticCategory.MEMORY, DiagnosticSeverity.ERROR),
    LogPattern("license",
               re.compile(r"(?:LICENSE CHECKOUT FAILED|LICENSE SERVER|NO LICENSE|TOKEN)", re.I),
               DiagnosticCategory.LICENSE, DiagnosticSeverity.ERROR),
    LogPattern("keyword-error",
               re.compile(r"(?:UNKNOWN KEYWORD|INVALID KEYWORD|ERROR IN KEYWORD)", re.I),
               DiagnosticCategory.SYNTAX, DiagnosticSeverity.ERROR),
    LogPattern("path-not-found",
               re.compile(r"(?:PATH TOO LONG|CANNOT FIND THE PATH|NO SUCH FILE|FILE NOT FOUND)", re.I),
               DiagnosticCategory.PATH, DiagnosticSeverity.ERROR),
    LogPattern("odb-unreadable",
               re.compile(r"(?:DATABASE WAS CREATED BY A NEWER RELEASE|ODB.*VERSION|CANNOT OPEN.*ODB)", re.I),
               DiagnosticCategory.ODB, DiagnosticSeverity.ERROR),
    LogPattern("output-not-written",
               re.compile(r"(?:OUTPUT REQUEST.*NOT AVAILABLE|OUTPUT DATABASE.*NOT WRITTEN)", re.I),
               DiagnosticCategory.OUTPUT, DiagnosticSeverity.WARNING),
    LogPattern("error-banner", re.compile(r"\*\*\*ERROR", re.I),
               DiagnosticCategory.UNKNOWN, DiagnosticSeverity.ERROR),
    LogPattern("warning-banner", re.compile(r"\*\*\*WARNING", re.I),
               DiagnosticCategory.UNKNOWN, DiagnosticSeverity.WARNING),
]


def list_diagnostic_pattern_specs() -> list[dict]:
    """Return the deterministic log parser pattern catalog."""
    specs = []
    for source_file, patterns in (
        (".msg", _MSG_PATTERNS),
        (".dat", _DAT_ERROR_PATTERNS),
    ):
        for entry in patterns:
            spec = {
                "id": f"{source_file[1:]}-{entry.slug}",
                "source_file": source_file,
                "category": entry.category.value,
                "severity": entry.severity.value,
                "pattern": entry.regex.pattern,
            }
            if entry.gate is not None:
                # The catalogue is user-facing; a pattern that only fires
                # under a condition must say so, or it reads as always-on.
                spec["only_when"] = entry.gate_reason
            specs.append(spec)
    return specs


def _parse_dat(path: Path, result: ParseResult) -> None:
    """Parse .dat file for data check errors."""
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return

    result.raw_snippets["dat"] = content[-1000:]

    for line_number, line in enumerate(content.splitlines(), start=1):
        for entry in _DAT_ERROR_PATTERNS:
            if entry.hit(line):
                result.events.append(DiagnosticEvent(
                    severity=entry.severity,
                    category=entry.category,
                    message=line.strip()[:200],
                    source_file=str(path.name),
                    line_number=line_number,
                ))
                break
