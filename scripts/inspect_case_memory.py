#!/usr/bin/env python3
"""Inspect and compare local Case Memory records without starting a server."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from evidence.case_memory import search_case_memory  # noqa: E402
from evidence.case_memory_diff import collect_case_memory_diff  # noqa: E402
from evidence.vault import VAULT_ENV  # noqa: E402
from simdiff.service import validate_diff_id  # noqa: E402


def _apply_root(root: str | None) -> str | None:
    previous = os.environ.get(VAULT_ENV)
    if root:
        os.environ[VAULT_ENV] = str(Path(root).expanduser())
    return previous


def _restore_root(previous: str | None, root_was_set: bool) -> None:
    if not root_was_set:
        return
    if previous is None:
        os.environ.pop(VAULT_ENV, None)
    else:
        os.environ[VAULT_ENV] = previous


def _find_memory(memory_id: str) -> dict[str, Any]:
    result = search_case_memory(query=memory_id, limit=200, url_prefix="case-memory://vault")
    for item in result["items"]:
        if item["memory_id"] == memory_id or item["vault_id"] == memory_id:
            return item
    raise FileNotFoundError(f"Case Memory entry not found: {memory_id}")


def _run_diff(args: argparse.Namespace) -> dict[str, Any]:
    safe_diff_id = validate_diff_id(args.diff_id)
    out_dir = Path(args.out_dir) if args.out_dir else Path(
        tempfile.mkdtemp(prefix=f"abaqus-agent-case-memory-diff-{safe_diff_id}.")
    )
    result = collect_case_memory_diff(
        baseline_vault_id=args.baseline_vault_id,
        candidate_vault_id=args.candidate_vault_id,
        out_dir=out_dir,
        diff_id=safe_diff_id,
        baseline_filename=args.baseline_filename,
        candidate_filename=args.candidate_filename,
    )
    report_path = out_dir / "diff.md"
    return {
        "diff_id": result["diff_id"],
        "overall_status": result["overall_status"],
        "real_env_verified": result["real_env_verified"],
        "diff": result["diff"],
        "case_memory_diff": result["case_memory_diff"],
        "diff_path": str(out_dir / "diff.json"),
        "report_path": str(report_path),
        "report_markdown": report_path.read_text(encoding="utf-8"),
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inspect local Case Memory records backed by the Evidence Vault."
    )
    parser.add_argument("--root", help="Evidence Vault root; defaults to ABAQUS_AGENT_EVIDENCE_VAULT or ~/.abaqus-agent/evidence-vault")
    subparsers = parser.add_subparsers(dest="command", required=True)

    search_parser = subparsers.add_parser("search", help="Search local Case Memory records")
    search_parser.add_argument("--query", default="", help="Text query over id, kind, title, status, files, and summary")
    search_parser.add_argument("--kind", default="", help="Filter by evidence kind")
    search_parser.add_argument("--status", default="", help="Filter by derived status")
    search_parser.add_argument("--limit", type=int, default=50, help="Maximum records to return")

    detail_parser = subparsers.add_parser("detail", help="Return one Case Memory record")
    detail_parser.add_argument("memory_id", help="Case Memory id or vault id")

    diff_parser = subparsers.add_parser("diff", help="Compare KPI artifacts from two Case Memory vault entries")
    diff_parser.add_argument("baseline_vault_id")
    diff_parser.add_argument("candidate_vault_id")
    diff_parser.add_argument("--baseline-filename", default=None, help="Optional safe nested baseline evidence.json or diff.json")
    diff_parser.add_argument("--candidate-filename", default=None, help="Optional safe nested candidate evidence.json or diff.json")
    diff_parser.add_argument("--diff-id", default="case-memory-diff", help="Safe id for the generated diff")
    diff_parser.add_argument("--out-dir", default=None, help="Output directory for diff.json and diff.md")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    previous_root = _apply_root(args.root)
    root_was_set = bool(args.root)
    try:
        if args.command == "search":
            data = search_case_memory(
                query=args.query,
                kind=args.kind,
                status=args.status,
                limit=args.limit,
                url_prefix="case-memory://vault",
            )
        elif args.command == "detail":
            data = _find_memory(args.memory_id)
        elif args.command == "diff":
            data = _run_diff(args)
        else:
            parser.error(f"Unsupported command: {args.command}")
        print(json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False))
        return 0
    except (FileNotFoundError, json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}, indent=2, sort_keys=True))
        return 2
    finally:
        _restore_root(previous_root, root_was_set)


if __name__ == "__main__":
    raise SystemExit(main())
