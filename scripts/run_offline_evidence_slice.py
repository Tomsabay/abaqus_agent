#!/usr/bin/env python3
# ruff: noqa: E402
"""
Offline v0.2 evidence slice CLI.

Given baseline KPI JSON, candidate KPI JSON, and Physics Contracts, this command
produces a portable Simulation QA bundle:
- evidence.json
- evidence.md
- capsule/<run-id>/capsule.json

It is designed for users who already have KPI values from an Abaqus workflow or
from the existing ODB extraction path. It does not invoke Abaqus.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from evidence.offline import collect_evidence_from_files


def collect_evidence(
    *,
    baseline_kpis_path: str | Path,
    candidate_kpis_path: str | Path,
    contracts_path: str | Path,
    out_dir: str | Path,
    run_id: str = "offline-evidence",
    extra_inputs: list[str | Path] | None = None,
) -> dict:
    """Backward-compatible wrapper for tests and direct imports."""
    return collect_evidence_from_files(
        baseline_kpis_path=baseline_kpis_path,
        candidate_kpis_path=candidate_kpis_path,
        contracts_path=contracts_path,
        out_dir=out_dir,
        run_id=run_id,
        extra_inputs=extra_inputs,
    )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run an offline Simulation QA evidence slice.")
    parser.add_argument("--baseline-kpis", required=True, help="Baseline KPI JSON object or {'kpis': ...}.")
    parser.add_argument("--candidate-kpis", required=True, help="Candidate KPI JSON object or {'kpis': ...}.")
    parser.add_argument("--contracts", required=True, help="JSON/YAML contracts or legacy expected.json.")
    parser.add_argument("--out-dir", required=True, help="Output directory for evidence bundle.")
    parser.add_argument("--run-id", default="offline-evidence", help="Capsule/evidence run id.")
    parser.add_argument(
        "--input",
        action="append",
        default=[],
        help="Additional input artifact to copy into the capsule; may be repeated.",
    )
    parser.add_argument("--json", action="store_true", help="Print evidence JSON instead of text summary.")
    return parser.parse_args(argv)


def run(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    evidence = collect_evidence(
        baseline_kpis_path=args.baseline_kpis,
        candidate_kpis_path=args.candidate_kpis,
        contracts_path=args.contracts,
        out_dir=args.out_dir,
        run_id=args.run_id,
        extra_inputs=args.input,
    )
    if args.json:
        print(json.dumps(evidence, indent=2, sort_keys=True))
    else:
        print(f"offline evidence slice: {evidence['overall_status']}")
        print(f"evidence: {Path(args.out_dir) / 'evidence.json'}")
        print(f"report: {Path(args.out_dir) / 'evidence.md'}")
        print(f"capsule: {evidence['capsule']['manifest_path']}")
    return 0 if evidence["overall_status"] in {"PASS", "WARNING", "INFO"} else 1


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
