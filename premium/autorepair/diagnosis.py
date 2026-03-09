"""
diagnosis.py
------------
LLM-powered root cause diagnosis for Abaqus job failures.

Uses the failure_analyzer.txt prompt template and the LLM planner
to diagnose failures and suggest parameter changes.
"""

from __future__ import annotations

import os
from pathlib import Path

import yaml

from premium.autorepair.log_parser import DiagnosticCategory, ParseResult

FAILURE_PROMPT_PATH = Path(__file__).parent.parent.parent / "prompts" / "failure_analyzer.txt"
PREMIUM_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "failure_repair.txt"


def diagnose_failure(
    parse_result: ParseResult,
    job_name: str,
    error_code: str = "",
    use_llm: bool = True,
    llm_backend: str = "auto",
) -> dict:
    """
    Diagnose a job failure and return structured repair recommendations.

    Returns
    -------
    dict with keys:
        root_cause       : str
        severity         : "FATAL" | "RECOVERABLE" | "WARNING"
        fix_action       : str
        parameter_changes: list[dict] (param, current, suggested, reason)
        retry_recommended: bool
    """
    # First try LLM-based diagnosis
    if use_llm:
        try:
            return _llm_diagnosis(parse_result, job_name, error_code, llm_backend)
        except Exception:
            pass

    # Fallback to rule-based diagnosis
    return _rule_based_diagnosis(parse_result, job_name, error_code)


def _llm_diagnosis(
    parse_result: ParseResult,
    job_name: str,
    error_code: str,
    backend: str,
) -> dict:
    """Use LLM to diagnose failure."""
    # Load prompt template
    if PREMIUM_PROMPT_PATH.exists():
        template = PREMIUM_PROMPT_PATH.read_text(encoding="utf-8")
    elif FAILURE_PROMPT_PATH.exists():
        template = FAILURE_PROMPT_PATH.read_text(encoding="utf-8")
    else:
        raise FileNotFoundError("No failure analysis prompt template found")

    # Fill template
    prompt = template.replace("{JOB_NAME}", job_name)
    prompt = prompt.replace("{ERROR_CODE}", error_code)
    prompt = prompt.replace("{LOG_SNIPPET}", parse_result.to_llm_context())

    # Call LLM
    raw = _call_llm(prompt, backend)

    # Parse YAML response
    try:
        result = yaml.safe_load(raw)
        if isinstance(result, dict):
            return {
                "root_cause": result.get("root_cause", "Unknown"),
                "severity": result.get("severity", "RECOVERABLE"),
                "fix_action": result.get("fix_action", ""),
                "parameter_changes": result.get("parameter_changes", []),
                "retry_recommended": result.get("retry_recommended", False),
            }
    except yaml.YAMLError:
        pass

    raise ValueError("LLM returned unparseable response")


def _call_llm(prompt: str, backend: str) -> str:
    """Call LLM backend for diagnosis."""
    if backend == "auto":
        if os.environ.get("ANTHROPIC_API_KEY"):
            backend = "anthropic"
        elif os.environ.get("OPENAI_API_KEY"):
            backend = "openai"
        else:
            raise RuntimeError("No LLM API key available")

    if backend == "anthropic":
        import anthropic
        client = anthropic.Anthropic()
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text.strip()
    elif backend == "openai":
        from openai import OpenAI
        client = OpenAI()
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=1000,
        )
        return response.choices[0].message.content.strip()

    raise ValueError(f"Unknown backend: {backend}")


# -----------------------------------------------------------------
# Rule-based diagnosis fallback
# -----------------------------------------------------------------

_RULE_TABLE: dict[DiagnosticCategory, dict] = {
    DiagnosticCategory.CONVERGENCE: {
        "root_cause": "Newton-Raphson iterations did not converge within allowed attempts",
        "severity": "RECOVERABLE",
        "fix_action": "Reduce initial increment size and increase maximum iterations",
        "parameter_changes": [
            {"param": "initial_increment", "current": "0.1", "suggested": "0.01", "reason": "Smaller steps improve convergence"},
            {"param": "max_iterations", "current": "default", "suggested": "20", "reason": "Allow more iterations per increment"},
            {"param": "nlgeom", "current": "OFF", "suggested": "ON", "reason": "Enable geometric nonlinearity for large deformation"},
        ],
        "retry_recommended": True,
    },
    DiagnosticCategory.ELEMENT_DISTORTION: {
        "root_cause": "Elements became excessively distorted during deformation",
        "severity": "RECOVERABLE",
        "fix_action": "Refine mesh in distorted regions and reduce load increments",
        "parameter_changes": [
            {"param": "seed_size", "current": "auto", "suggested": "reduce by 50%", "reason": "Finer mesh resists distortion"},
            {"param": "initial_increment", "current": "0.1", "suggested": "0.02", "reason": "Smaller increments reduce per-step deformation"},
        ],
        "retry_recommended": True,
    },
    DiagnosticCategory.RIGID_BODY_MOTION: {
        "root_cause": "Unconstrained rigid body motion detected (zero pivot in stiffness matrix)",
        "severity": "RECOVERABLE",
        "fix_action": "Check boundary conditions for completeness; add springs or stabilization",
        "parameter_changes": [
            {"param": "stabilize", "current": "OFF", "suggested": "ON (1e-4)", "reason": "Add artificial damping to suppress rigid body modes"},
        ],
        "retry_recommended": True,
    },
    DiagnosticCategory.CONTACT: {
        "root_cause": "Contact algorithm encountered excessive opening/overclosure or chattering",
        "severity": "RECOVERABLE",
        "fix_action": "Enable contact stabilization and adjust initial gap/overclosure",
        "parameter_changes": [
            {"param": "contact_stabilization", "current": "OFF", "suggested": "ON", "reason": "Stabilize contact during initial iterations"},
            {"param": "initial_increment", "current": "0.1", "suggested": "0.01", "reason": "Smaller increments for better contact resolution"},
        ],
        "retry_recommended": True,
    },
    DiagnosticCategory.MEMORY: {
        "root_cause": "Insufficient memory for solver operations",
        "severity": "RECOVERABLE",
        "fix_action": "Increase memory allocation or reduce model size",
        "parameter_changes": [
            {"param": "memory", "current": "90%", "suggested": "95%", "reason": "Allow more system memory"},
            {"param": "output_frequency", "current": "every increment", "suggested": "every 5 increments", "reason": "Reduce output data volume"},
        ],
        "retry_recommended": True,
    },
}


def _rule_based_diagnosis(
    parse_result: ParseResult, job_name: str, error_code: str
) -> dict:
    """Rule-based fallback diagnosis when LLM is unavailable."""
    category = parse_result.primary_category

    if category in _RULE_TABLE:
        return _RULE_TABLE[category].copy()

    return {
        "root_cause": f"Job failed with error code: {error_code}",
        "severity": "FATAL",
        "fix_action": "Manual inspection required. Check .msg and .dat files.",
        "parameter_changes": [],
        "retry_recommended": False,
    }
