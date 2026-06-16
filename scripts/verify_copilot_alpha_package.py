#!/usr/bin/env python3
"""Verify an AbaqusAgent Copilot Alpha ZIP package."""

from __future__ import annotations

import argparse
import json
import zipfile
from pathlib import Path
from typing import Any

REQUIRED_MEMBERS = [
    "README.md",
    "PACKAGE_MANIFEST.json",
    "plugin/abaqusAgent_plugin.py",
    "plugin/abaqus_agent_config.example.json",
    "docs/COPILOT_MVP.md",
    "evidence/copilot_alpha_release_gate.json",
    "evidence/copilot_alpha_release_gate.md",
    "evidence/real_smoke/Cantilever_200mm_Static_copilot_result.json",
    "evidence/plugin_run_plan/copilot_plugin_run_plan_trace.json",
    "evidence/plugin_run_plan/Cantilever_200mm_Static_copilot_result.json",
    "evidence/plugin_manifest/abaqus_agent_plugin_manifest.json",
]


def verify_copilot_alpha_package(zip_path: str | Path) -> dict[str, Any]:
    path = Path(zip_path)
    result: dict[str, Any] = {
        "schema_version": "1.0",
        "workflow": "copilot-alpha-package-verify",
        "zip_path": str(path),
        "overall_status": "FAIL",
        "missing_members": [],
        "checks": [],
    }
    try:
        with zipfile.ZipFile(path) as bundle:
            return _verify_opened_package(bundle, result)
    except FileNotFoundError as exc:
        result["error"] = str(exc)
        return result
    except zipfile.BadZipFile as exc:
        result["error"] = f"Invalid ZIP package: {exc}"
        return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("zip_path", help="Path to abaqus-agent-copilot-alpha.zip")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    result = verify_copilot_alpha_package(args.zip_path)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    else:
        print(f"{result['overall_status']} {args.zip_path}")
        for check in result.get("checks", []):
            print(f"- {check['id']}: {check['status']}")
        if result.get("error"):
            print(f"error: {result['error']}")
    return 0 if result["overall_status"] == "PASS" else 1


def _verify_opened_package(
    bundle: zipfile.ZipFile,
    result: dict[str, Any],
) -> dict[str, Any]:
    members = set(bundle.namelist())
    result["zip_members"] = sorted(members)
    missing = [member for member in REQUIRED_MEMBERS if member not in members]
    result["missing_members"] = missing
    result["checks"].append(
        {
            "id": "required_members",
            "status": "PASS" if not missing else "FAIL",
            "missing": missing,
        }
    )
    manifest = _read_json_member(bundle, "PACKAGE_MANIFEST.json")
    gate = _read_json_member(bundle, "evidence/copilot_alpha_release_gate.json")
    config = _read_json_member(bundle, "plugin/abaqus_agent_config.example.json")

    manifest_status = _check_manifest(manifest, members)
    gate_status = _check_release_gate(gate)
    config_status = _check_config_example(config)
    result["checks"].extend([manifest_status, gate_status, config_status])
    result["package_overall_status"] = manifest.get("overall_status")
    result["strict_gui_ready"] = manifest.get("strict_gui_ready")
    result["overall_status"] = (
        "PASS" if all(check["status"] == "PASS" for check in result["checks"]) else "FAIL"
    )
    return result


def _check_manifest(manifest: dict[str, Any], members: set[str]) -> dict[str, Any]:
    included = manifest.get("included_files")
    missing_from_manifest = [
        member
        for member in REQUIRED_MEMBERS
        if member not in {"README.md", "PACKAGE_MANIFEST.json"} and member not in (included or [])
    ]
    missing_from_zip = [member for member in included or [] if member not in members]
    passed = (
        manifest.get("package") == "abaqus-agent-copilot-alpha"
        and manifest.get("overall_status") in {"ALPHA_READY_WITH_GUI_BLOCKER", "RELEASE_READY"}
        and isinstance(included, list)
        and not missing_from_manifest
        and not missing_from_zip
    )
    return {
        "id": "package_manifest",
        "status": "PASS" if passed else "FAIL",
        "package": manifest.get("package"),
        "overall_status": manifest.get("overall_status"),
        "missing_from_manifest": missing_from_manifest,
        "missing_from_zip": missing_from_zip,
    }


def _check_release_gate(gate: dict[str, Any]) -> dict[str, Any]:
    checks = {item.get("id"): item.get("status") for item in gate.get("checks", [])}
    passed = (
        gate.get("overall_status") in {"ALPHA_READY_WITH_GUI_BLOCKER", "RELEASE_READY"}
        and checks.get("codex_strict_real_abaqus_smoke") == "PASS"
        and checks.get("plugin_run_current_plan_real_abaqus") == "PASS"
        and checks.get("plugin_runtime_manifest") == "PASS"
        and checks.get("interactive_cae_gui_visual") in {"PASS", "BLOCKED"}
    )
    return {
        "id": "release_gate_evidence",
        "status": "PASS" if passed else "FAIL",
        "overall_status": gate.get("overall_status"),
        "checks": checks,
    }


def _check_config_example(config: dict[str, Any]) -> dict[str, Any]:
    passed = isinstance(config.get("server_url"), str) and "session_id" in config
    return {
        "id": "config_example",
        "status": "PASS" if passed else "FAIL",
        "server_url": config.get("server_url"),
        "has_session_id": "session_id" in config,
    }


def _read_json_member(bundle: zipfile.ZipFile, member: str) -> dict[str, Any]:
    try:
        return json.loads(bundle.read(member).decode("utf-8"))
    except (KeyError, UnicodeDecodeError, json.JSONDecodeError):
        return {}


if __name__ == "__main__":
    raise SystemExit(main())
