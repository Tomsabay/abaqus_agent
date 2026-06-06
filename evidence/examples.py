"""
examples.py
-----------
Offline Evidence example gallery fixtures.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from contracts.io import load_contracts
from evidence.offline import load_kpis

ROOT = Path(__file__).resolve().parents[1]
GALLERY_EXAMPLE_CASES = ("cantilever", "plate_hole", "modal", "explicit_impact")
CUSTOM_INP_EXAMPLE = "custom_inp_deck"
EXAMPLE_CASES = (*GALLERY_EXAMPLE_CASES, CUSTOM_INP_EXAMPLE)


def list_examples() -> dict[str, Any]:
    """Return available offline evidence example summaries."""
    return {
        "cases": [
            _example_summary(case_name)
            for case_name in EXAMPLE_CASES
        ]
    }


def get_example(case_name: str) -> dict[str, Any]:
    """Return one offline evidence example payload."""
    if case_name not in EXAMPLE_CASES:
        raise KeyError(f"Unknown offline evidence example: {case_name}")

    summary = _example_summary(case_name)
    baseline_path = ROOT / summary["baseline_kpis_path"]
    candidate_path = ROOT / summary["candidate_kpis_path"]
    contracts_path = ROOT / summary["contracts_path"]
    input_path = ROOT / summary["input_path"]
    return {
        "case": case_name,
        "run_id": summary["run_id"],
        "input_path": str(input_path.relative_to(ROOT)),
        "input_type": summary["input_type"],
        "baseline_kpis": load_kpis(baseline_path),
        "candidate_kpis": load_kpis(candidate_path),
        "contracts": load_contracts(contracts_path),
        "paths": {
            "baseline_kpis": str(baseline_path.relative_to(ROOT)),
            "candidate_kpis": str(candidate_path.relative_to(ROOT)),
            "contracts": str(contracts_path.relative_to(ROOT)),
        },
    }


def _example_summary(case_name: str) -> dict[str, str]:
    if case_name == CUSTOM_INP_EXAMPLE:
        return {
            "case": case_name,
            "run_id": "custom-inp-deck-example-offline",
            "input_type": "custom_inp",
            "input_path": "examples/inp/custom_cantilever.inp",
            "baseline_kpis_path": "examples/kpis/custom_inp_deck_baseline.json",
            "candidate_kpis_path": "examples/kpis/custom_inp_deck_candidate.json",
            "contracts_path": "examples/contracts/custom_inp_deck.yaml",
        }
    return {
        "case": case_name,
        "run_id": f"{case_name}-example-offline",
        "input_type": "problem_spec",
        "input_path": f"cases/{case_name}/spec.yaml",
        "baseline_kpis_path": f"examples/kpis/{case_name}_baseline.json",
        "candidate_kpis_path": f"examples/kpis/{case_name}_candidate.json",
        "contracts_path": f"examples/contracts/{case_name}.yaml",
    }
