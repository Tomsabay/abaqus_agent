#!/usr/bin/env python3
"""Inspect Solver Doctor diagnostic pattern coverage without starting a server."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from doctor.solver_doctor import list_doctor_patterns  # noqa: E402


def _get_pattern(pattern_id: str) -> dict[str, Any]:
    catalog = list_doctor_patterns()
    for pattern in catalog["patterns"]:
        if pattern["id"] == pattern_id:
            return {
                "schema_version": catalog["schema_version"],
                "workflow": catalog["workflow"],
                "real_env_verified": catalog["real_env_verified"],
                "pattern": pattern,
            }
    raise KeyError(f"Solver Doctor pattern not found: {pattern_id}")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inspect Solver Doctor diagnostic parser patterns."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="List Solver Doctor patterns")
    list_parser.add_argument("--category", default="", help="Filter by diagnostic category")
    list_parser.add_argument("--severity", default="", help="Filter by severity")

    detail_parser = subparsers.add_parser("detail", help="Return one pattern by id")
    detail_parser.add_argument("pattern_id")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "list":
            data = list_doctor_patterns(category=args.category, severity=args.severity)
        elif args.command == "detail":
            data = _get_pattern(args.pattern_id)
        else:
            parser.error(f"Unsupported command: {args.command}")
        print(json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False))
        return 0
    except KeyError as exc:
        print(json.dumps({"error": str(exc)}, indent=2, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
