#!/usr/bin/env python3
"""Verify a local demo pack ZIP bundle against its embedded manifest."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

MANIFEST_NAME = "local-demo-pack-manifest.json"


def verify_demo_pack_bundle(zip_path: str | Path) -> dict[str, Any]:
    bundle_path = Path(zip_path)
    result = _build_result(str(bundle_path))

    try:
        with zipfile.ZipFile(bundle_path) as bundle:
            return _verify_opened_demo_pack_bundle(bundle, result)
    except zipfile.BadZipFile as exc:
        result["error"] = f"Invalid ZIP bundle: {exc}"
        return result


def verify_demo_pack_bundle_bytes(zip_bytes: bytes, *, zip_path: str) -> dict[str, Any]:
    result = _build_result(zip_path)
    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as bundle:
            return _verify_opened_demo_pack_bundle(bundle, result)
    except zipfile.BadZipFile as exc:
        result["error"] = f"Invalid ZIP bundle: {exc}"
        return result


def _build_result(zip_path: str) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "project": "abaqus-agent",
        "workflow": "local-demo-pack-bundle-verify",
        "zip_path": zip_path,
        "overall_status": "FAIL",
        "real_env_verified": False,
        "files": [],
    }


def _verify_opened_demo_pack_bundle(
    bundle: zipfile.ZipFile,
    result: dict[str, Any],
) -> dict[str, Any]:
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
    result["bundle_generated_at"] = manifest.get("generated_at")
    if manifest.get("workflow") != "local-demo-pack":
        result["error"] = "Manifest workflow must be local-demo-pack"
        return result

    files = manifest.get("files")
    if not isinstance(files, list) or not files:
        result["error"] = "Manifest files must be a non-empty list"
        return result

    checked_files = [_verify_manifest_entry(bundle, members, item) for item in files]
    result["files"] = checked_files
    result["checked_file_count"] = len(checked_files)
    result["overall_status"] = (
        "PASS" if checked_files and all(item["status"] == "PASS" for item in checked_files) else "FAIL"
    )
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
    parser.add_argument("zip_path", help="Path to local-demo-pack.zip")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        result = verify_demo_pack_bundle(args.zip_path)
    except FileNotFoundError as exc:
        result = {
            "schema_version": "1.0",
            "project": "abaqus-agent",
            "workflow": "local-demo-pack-bundle-verify",
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
