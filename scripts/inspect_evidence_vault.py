#!/usr/bin/env python3
"""Inspect local Evidence Vault records without starting a server."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from evidence.vault import get_vault_file_path, get_vault_record, list_vault_entries  # noqa: E402
from scripts.verify_local_cli_smoke_bundle import verify_smoke_bundle  # noqa: E402
from scripts.verify_local_demo_pack_bundle import verify_demo_pack_bundle  # noqa: E402

TEXT_SUFFIXES = {".json", ".md", ".html"}


def _read_text_file(vault_id: str, filename: str, *, root: str, max_chars: int) -> dict[str, Any]:
    path = get_vault_file_path(vault_id, filename, root=root)
    if path.suffix not in TEXT_SUFFIXES:
        return {
            "error": f"Unsupported text vault file type: {filename}",
            "vault_id": vault_id,
            "filename": filename,
            "size_bytes": path.stat().st_size,
        }
    safe_max_chars = max(1, min(max_chars, 50000))
    content = path.read_text(encoding="utf-8")
    return {
        "vault_id": vault_id,
        "filename": filename,
        "path": str(path),
        "size_bytes": path.stat().st_size,
        "truncated": len(content) > safe_max_chars,
        "content": content[:safe_max_chars],
    }


def _copy_vault_file(vault_id: str, filename: str, *, root: str, out: str) -> dict[str, Any]:
    source = get_vault_file_path(vault_id, filename, root=root)
    target = Path(out).expanduser()
    if target.exists() and target.is_dir():
        target = target / Path(filename).name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    return {
        "vault_id": vault_id,
        "filename": filename,
        "source_path": str(source),
        "output_path": str(target),
        "size_bytes": target.stat().st_size,
    }


def _verify_smoke_bundle(vault_id: str, filename: str, *, root: str) -> dict[str, Any]:
    source = get_vault_file_path(vault_id, filename, root=root)
    data = verify_smoke_bundle(source)
    data["vault_id"] = vault_id
    data["filename"] = filename
    data["source_path"] = str(source)
    return data


def _verify_demo_pack_bundle(vault_id: str, filename: str, *, root: str) -> dict[str, Any]:
    source = get_vault_file_path(vault_id, filename, root=root)
    data = verify_demo_pack_bundle(source)
    data["vault_id"] = vault_id
    data["filename"] = filename
    data["source_path"] = str(source)
    return data


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default="", help="Override Evidence Vault root")
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="List/search vault records")
    list_parser.add_argument("--query", default="")
    list_parser.add_argument("--kind", default="")
    list_parser.add_argument("--status", default="")
    list_parser.add_argument("--limit", type=int, default=50)

    detail_parser = subparsers.add_parser("detail", help="Show one vault record")
    detail_parser.add_argument("vault_id")

    read_parser = subparsers.add_parser("read", help="Read one safe text vault file")
    read_parser.add_argument("vault_id")
    read_parser.add_argument("filename")
    read_parser.add_argument("--max-chars", type=int, default=20000)

    copy_parser = subparsers.add_parser("copy", help="Copy one vault file to a local path")
    copy_parser.add_argument("vault_id")
    copy_parser.add_argument("filename")
    copy_parser.add_argument("--out", required=True, help="Output file path or existing directory")

    verify_parser = subparsers.add_parser(
        "verify-smoke",
        help="Verify a stored local_cli_smoke.zip against its embedded manifest",
    )
    verify_parser.add_argument("vault_id")
    verify_parser.add_argument("--filename", default="local_cli_smoke.zip")

    verify_demo_pack_parser = subparsers.add_parser(
        "verify-demo-pack",
        help="Verify a stored local-demo-pack.zip against its embedded manifest",
    )
    verify_demo_pack_parser.add_argument("vault_id")
    verify_demo_pack_parser.add_argument("--filename", default="local-demo-pack.zip")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    root = args.root or None

    try:
        if args.command == "list":
            data = list_vault_entries(
                root=root,
                query=args.query,
                kind=args.kind,
                status=args.status,
                limit=args.limit,
            )
        elif args.command == "detail":
            data = get_vault_record(args.vault_id, root=root)
        elif args.command == "read":
            data = _read_text_file(
                args.vault_id,
                args.filename,
                root=root,
                max_chars=args.max_chars,
            )
            if "error" in data:
                print(json.dumps(data, ensure_ascii=False))
                return 2
        elif args.command == "copy":
            data = _copy_vault_file(
                args.vault_id,
                args.filename,
                root=root,
                out=args.out,
            )
        elif args.command == "verify-smoke":
            data = _verify_smoke_bundle(
                args.vault_id,
                args.filename,
                root=root,
            )
        elif args.command == "verify-demo-pack":
            data = _verify_demo_pack_bundle(
                args.vault_id,
                args.filename,
                root=root,
            )
        else:
            parser.error(f"Unknown command: {args.command}")
    except (FileNotFoundError, UnicodeDecodeError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        return 2

    print(json.dumps(data, ensure_ascii=False))
    if args.command in {"verify-demo-pack", "verify-smoke"} and data.get(
        "overall_status"
    ) != "PASS":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
