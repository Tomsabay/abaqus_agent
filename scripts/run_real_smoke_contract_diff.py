#!/usr/bin/env python3
# ruff: noqa: E402
"""Generate Physics Contract and Simulation Diff evidence from a real smoke run."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from evidence.real_smoke_contract_diff import collect_real_smoke_contract_diff


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--smoke-dir", required=True, help="Directory containing smoke_evidence.json")
    parser.add_argument("--out-dir", required=True, help="Output directory for report artifacts")
    parser.add_argument("--contracts", help="Physics Contract YAML/JSON path; defaults to examples/contracts/<case>.yaml")
    parser.add_argument("--run-id", help="Safe run id for the generated capsule")
    parser.add_argument(
        "--allow-unverified",
        action="store_true",
        help="Generate a report even when the source smoke bundle is not real-env verified",
    )
    parser.add_argument("--json", action="store_true", help="Print generated evidence JSON")
    args = parser.parse_args(argv)

    evidence = collect_real_smoke_contract_diff(
        smoke_dir=args.smoke_dir,
        out_dir=args.out_dir,
        contracts_path=args.contracts,
        run_id=args.run_id,
        require_verified=not args.allow_unverified,
    )
    if args.json:
        print(json.dumps(evidence, indent=2, sort_keys=True))
    else:
        print(evidence["report_path"])
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
