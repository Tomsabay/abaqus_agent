#!/usr/bin/env python3
"""Verify a local CLI smoke ZIP bundle against its embedded manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

from scripts.verify_local_demo_pack_bundle import verify_demo_pack_bundle_bytes

MANIFEST_NAME = "local_cli_smoke_manifest.json"
COPIED_DEMO_PACK_NAME = "copied-local-demo-pack.zip"


def verify_smoke_bundle(zip_path: str | Path) -> dict[str, Any]:
    bundle_path = Path(zip_path)
    result: dict[str, Any] = {
        "schema_version": "1.0",
        "project": "abaqus-agent",
        "workflow": "local-cli-smoke-bundle-verify",
        "zip_path": str(bundle_path),
        "overall_status": "FAIL",
        "real_env_verified": False,
        "files": [],
    }

    try:
        with zipfile.ZipFile(bundle_path) as bundle:
            members = set(bundle.namelist())
            result["zip_members"] = sorted(members)
            if MANIFEST_NAME not in members:
                result["error"] = f"Missing {MANIFEST_NAME}"
                return result

            try:
                manifest = json.loads(bundle.read(MANIFEST_NAME))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                result["error"] = f"Invalid {MANIFEST_NAME}: {exc}"
                return result

            result["bundle_workflow"] = manifest.get("workflow")
            result["bundle_overall_status"] = manifest.get("overall_status")
            result["smoke_vault_id"] = manifest.get("smoke_vault_id")
            files = manifest.get("files")
            if not isinstance(files, list) or not files:
                result["error"] = "Manifest files must be a non-empty list"
                return result

            checked_files = [_verify_manifest_entry(bundle, members, item) for item in files]
            result["files"] = checked_files
            result["checked_file_count"] = len(checked_files)
            nested_demo_pack_status = "NOT_PRESENT"
            if COPIED_DEMO_PACK_NAME in members:
                nested_demo_pack = verify_demo_pack_bundle_bytes(
                    bundle.read(COPIED_DEMO_PACK_NAME),
                    zip_path=COPIED_DEMO_PACK_NAME,
                )
                nested_demo_pack_status = nested_demo_pack["overall_status"]
                result["copied_demo_pack_verification"] = nested_demo_pack
            result["overall_status"] = (
                "PASS"
                if checked_files
                and all(item["status"] == "PASS" for item in checked_files)
                and nested_demo_pack_status in {"PASS", "NOT_PRESENT"}
                else "FAIL"
            )
            return result
    except zipfile.BadZipFile as exc:
        result["error"] = f"Invalid ZIP bundle: {exc}"
        return result


def _verify_manifest_entry(
    bundle: zipfile.ZipFile,
    members: set[str],
    item: Any,
) -> dict[str, Any]:
    filename = item.get("filename") if isinstance(item, dict) else None
    entry: dict[str, Any] = {
        "filename": filename,
        "expected_size_bytes": item.get("size_bytes") if isinstance(item, dict) else None,
        "expected_sha256": item.get("sha256") if isinstance(item, dict) else None,
        "status": "FAIL",
    }
    if not isinstance(filename, str) or not filename:
        entry["reason"] = "Manifest entry filename must be a non-empty string"
        return entry
    if _is_unsafe_member_name(filename):
        entry["status"] = "UNSAFE_NAME"
        entry["reason"] = "Manifest filename must be a relative ZIP member name"
        return entry
    if filename not in members:
        entry["status"] = "MISSING"
        entry["reason"] = "Manifest file is missing from ZIP"
        return entry

    content = bundle.read(filename)
    actual_size = len(content)
    actual_sha256 = hashlib.sha256(content).hexdigest()
    entry["actual_size_bytes"] = actual_size
    entry["actual_sha256"] = actual_sha256

    if item.get("size_bytes") != actual_size:
        entry["status"] = "SIZE_MISMATCH"
        entry["reason"] = "ZIP member size does not match manifest"
        return entry
    if item.get("sha256") != actual_sha256:
        entry["status"] = "SHA256_MISMATCH"
        entry["reason"] = "ZIP member SHA-256 does not match manifest"
        return entry

    entry["status"] = "PASS"
    return entry


def _is_unsafe_member_name(filename: str) -> bool:
    path = PurePosixPath(filename)
    return path.is_absolute() or ".." in path.parts or filename.endswith("/")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("zip_path", help="Path to local_cli_smoke.zip")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        result = verify_smoke_bundle(args.zip_path)
    except FileNotFoundError as exc:
        result = {
            "schema_version": "1.0",
            "project": "abaqus-agent",
            "workflow": "local-cli-smoke-bundle-verify",
            "zip_path": args.zip_path,
            "overall_status": "FAIL",
            "real_env_verified": False,
            "error": str(exc),
            "files": [],
        }

    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        print(f"{result['overall_status']} {args.zip_path}")
        for item in result.get("files", []):
            print(f"- {item['filename']}: {item['status']}")
        if result.get("error"):
            print(f"error: {result['error']}")
    return 0 if result["overall_status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
