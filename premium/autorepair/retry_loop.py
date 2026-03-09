"""
retry_loop.py
-------------
Orchestrator integration for automatic failure repair.

Provides a hook that intercepts job failures, diagnoses them,
applies repairs, and retries the simulation.
"""

from __future__ import annotations

import json
from pathlib import Path

from premium.autorepair.diagnosis import diagnose_failure
from premium.autorepair.log_parser import parse_job_diagnostics
from premium.autorepair.repair_strategies import apply_repairs, can_retry, save_repaired_spec


def autorepair_hook(context: dict) -> dict:
    """
    Pipeline hook for post_submit_failure.

    Called by the orchestrator when a job fails. Attempts to:
    1. Parse diagnostic files
    2. Diagnose root cause (LLM or rule-based)
    3. Apply repairs to spec
    4. Signal retry

    Context keys expected:
        spec      : dict - current spec
        workdir   : Path - working directory
        job_name  : str  - failed job name
        error     : AbaqusAgentError
        attempt   : int  - current attempt number
        max_retries: int - max retry attempts

    Context keys set:
        repaired_spec  : dict - modified spec for retry
        diagnosis      : dict - diagnosis result
        should_retry   : bool - whether to retry
    """
    spec = context.get("spec", {})
    workdir = Path(context.get("workdir", "."))
    job_name = context.get("job_name", "")
    error = context.get("error")
    attempt = context.get("attempt", 0)
    max_retries = context.get("max_retries", 3)

    # Don't retry if we've exhausted attempts
    if attempt >= max_retries:
        context["should_retry"] = False
        context["diagnosis"] = {
            "root_cause": "Maximum retry attempts reached",
            "severity": "FATAL",
            "retry_recommended": False,
        }
        return context

    # Parse diagnostic files
    parse_result = parse_job_diagnostics(workdir, job_name)

    # Diagnose
    error_code = error.code.value if error else ""
    diagnosis = diagnose_failure(
        parse_result,
        job_name,
        error_code=error_code,
        use_llm=True,
        llm_backend="auto",
    )

    context["diagnosis"] = diagnosis

    # Check if we should retry
    if not can_retry(diagnosis):
        context["should_retry"] = False
        return context

    # Apply repairs
    repaired_spec = apply_repairs(spec, diagnosis)
    spec_path = save_repaired_spec(repaired_spec, workdir, attempt + 1)

    context["repaired_spec"] = repaired_spec
    context["repaired_spec_path"] = str(spec_path)
    context["should_retry"] = True

    # Save diagnosis for debugging
    diag_path = workdir / f"diagnosis_{attempt}.json"
    diag_path.write_text(
        json.dumps(diagnosis, indent=2, default=str),
        encoding="utf-8",
    )

    return context


def run_autorepair_loop(orchestrator, max_retries: int = 3) -> dict:
    """
    Run the full auto-repair loop on an orchestrator instance.

    This is the main entry point called by the extended orchestrator.
    It wraps the standard pipeline with retry logic.
    """
    from tools.errors import AbaqusAgentError

    for attempt in range(max_retries + 1):
        try:
            result = orchestrator.run()
            if result.get("status") == "COMPLETED":
                if attempt > 0:
                    result["autorepair"] = {
                        "attempts": attempt,
                        "repaired": True,
                    }
                return result

        except AbaqusAgentError as e:
            if attempt >= max_retries:
                raise

            # Build context for hook
            context = {
                "spec": orchestrator.spec,
                "workdir": orchestrator.workdir,
                "job_name": orchestrator.spec.get("meta", {}).get("model_name", ""),
                "error": e,
                "attempt": attempt,
                "max_retries": max_retries,
            }

            # Run repair hook
            context = autorepair_hook(context)

            if not context.get("should_retry"):
                raise

            # Update orchestrator with repaired spec
            orchestrator.spec = context["repaired_spec"]

            # Clear cached build artifacts for retry
            if orchestrator.workdir:
                inp_path = Path(orchestrator.workdir) / f"{orchestrator.spec['meta']['model_name']}.inp"
                if inp_path.exists():
                    inp_path.unlink()

    return orchestrator.result
