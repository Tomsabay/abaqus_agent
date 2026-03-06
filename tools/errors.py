"""
errors.py
---------
Structured error codes and exception class for abaqus-agent.
Every tool returns or raises an AbaqusAgentError with a machine-readable ErrorCode.
"""

from __future__ import annotations

from enum import Enum


class ErrorCode(str, Enum):
    # Build / geometry
    BUILD_FAILED          = "BUILD_FAILED"
    UNSUPPORTED_GEOMETRY  = "UNSUPPORTED_GEOMETRY"
    UNSUPPORTED_STEP      = "UNSUPPORTED_STEP"
    FILE_NOT_FOUND        = "FILE_NOT_FOUND"
    PATH_TOO_LONG         = "PATH_TOO_LONG"          # Abaqus 256-char limit

    # Syntax / validation
    SYNTAX_ERROR          = "SYNTAX_ERROR"
    SCHEMA_VALIDATION     = "SCHEMA_VALIDATION"
    STATIC_GUARD_BLOCKED  = "STATIC_GUARD_BLOCKED"   # dangerous code detected

    # Execution
    ABAQUS_NOT_FOUND      = "ABAQUS_NOT_FOUND"
    LICENSE_UNAVAILABLE   = "LICENSE_UNAVAILABLE"
    TIMEOUT               = "TIMEOUT"
    JOB_FAILED            = "JOB_FAILED"
    NONCONVERGENCE        = "NONCONVERGENCE"
    MEMORY_ERROR          = "MEMORY_ERROR"

    # ODB / post-processing
    ODB_NOT_FOUND         = "ODB_NOT_FOUND"
    ODB_UPGRADE_REQUIRED  = "ODB_UPGRADE_REQUIRED"
    ODB_INVALID           = "ODB_INVALID"
    KPI_EXTRACTION_FAILED = "KPI_EXTRACTION_FAILED"

    # LLM / orchestrator
    SPEC_INVALID          = "SPEC_INVALID"
    LLM_GENERATION_FAILED = "LLM_GENERATION_FAILED"

    # Premium / licensing
    PREMIUM_FEATURE_REQUIRED = "PREMIUM_FEATURE_REQUIRED"

    # Generic
    UNKNOWN               = "UNKNOWN"


# Suggested next action for each error code (for agent self-repair)
ERROR_SUGGESTIONS: dict[ErrorCode, str] = {
    ErrorCode.BUILD_FAILED:         "Check CAE script log; try simpler geometry or reduce mesh seed",
    ErrorCode.UNSUPPORTED_GEOMETRY: "Use one of: cantilever_block, plate_with_hole, axisymmetric_disk, custom_inp",
    ErrorCode.UNSUPPORTED_STEP:     "Use one of: Static, Frequency, Dynamic_Explicit, Dynamic_Implicit",
    ErrorCode.FILE_NOT_FOUND:       "Verify paths; check that build_model ran successfully",
    ErrorCode.PATH_TOO_LONG:        "Shorten workdir path to < 200 chars to stay under Abaqus 256-char limit",
    ErrorCode.SYNTAX_ERROR:         "Run syntaxcheck; fix .inp keyword errors before submitting",
    ErrorCode.SCHEMA_VALIDATION:    "Fix spec.yaml to comply with schema/spec_schema.json",
    ErrorCode.STATIC_GUARD_BLOCKED: "Remove dangerous imports (os/subprocess/socket) from generated script",
    ErrorCode.ABAQUS_NOT_FOUND:     "Add Abaqus to PATH; verify installation with 'abaqus information=release'",
    ErrorCode.LICENSE_UNAVAILABLE:  "Wait for license token or reduce concurrent jobs",
    ErrorCode.TIMEOUT:              "Increase timeout_seconds or reduce model size / increase cpus",
    ErrorCode.JOB_FAILED:           "Check .log/.msg files; run syntaxcheck; inspect .dat for diagnostics",
    ErrorCode.NONCONVERGENCE:       "Reduce load increment, enable nlgeom, check BCs, refine mesh",
    ErrorCode.MEMORY_ERROR:         "Increase memory allocation or reduce model size / output frequency",
    ErrorCode.ODB_NOT_FOUND:        "Job may have failed before writing ODB; check .log file",
    ErrorCode.ODB_UPGRADE_REQUIRED: "Run upgrade_odb_if_needed() before extraction",
    ErrorCode.ODB_INVALID:          "ODB may be corrupted; re-run the job",
    ErrorCode.KPI_EXTRACTION_FAILED:"Check kpi_spec types and location set names in the model",
    ErrorCode.SPEC_INVALID:         "Validate spec against schema/spec_schema.json",
    ErrorCode.LLM_GENERATION_FAILED:"Retry with more specific constraints or use a template",
    ErrorCode.PREMIUM_FEATURE_REQUIRED: "This feature requires a premium license. Set ABAQUS_AGENT_LICENSE_KEY or ABAQUS_AGENT_FEATURES env var",
    ErrorCode.UNKNOWN:              "Inspect logs for details",
}


class AbaqusAgentError(Exception):
    """
    Structured exception for the Abaqus Agent.

    Attributes
    ----------
    code        : ErrorCode
    message     : str
    suggestion  : str   - auto-filled from ERROR_SUGGESTIONS
    log_snippet : str   - relevant log excerpt (last 2000 chars)
    workdir     : str   - working directory for debugging
    """

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        log_snippet: str = "",
        workdir: str = "",
        **kwargs,
    ):
        super().__init__(message)
        self.code        = code
        self.message     = message
        self.suggestion  = ERROR_SUGGESTIONS.get(code, "")
        self.log_snippet = log_snippet
        self.workdir     = workdir
        self.extra       = kwargs

    def to_dict(self) -> dict:
        return {
            "error_code": self.code.value,
            "message": self.message,
            "suggestion": self.suggestion,
            "log_snippet": self.log_snippet[-500:] if self.log_snippet else "",
            "workdir": self.workdir,
        }

    def __str__(self) -> str:
        parts = [f"[{self.code.value}] {self.message}"]
        if self.suggestion:
            parts.append(f"  → Suggestion: {self.suggestion}")
        if self.workdir:
            parts.append(f"  → Workdir: {self.workdir}")
        return "\n".join(parts)
