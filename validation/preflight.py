"""Environment preflight checks for real Abaqus validation runs."""

from __future__ import annotations

import os
import platform
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tools.abaqus_cmd import get_abaqus_cmd

_VERSION_RE = re.compile(r"\b(?:Abaqus|SIMULIA)\D*(20\d{2})(?:\D|$)", re.IGNORECASE)


def run_environment_preflight(
    *,
    abaqus_cmd: str | None = None,
    timeout_seconds: float = 15.0,
    check_release: bool = True,
) -> dict[str, Any]:
    """Collect machine and Abaqus command readiness evidence."""
    command = abaqus_cmd or get_abaqus_cmd()
    command_path = _resolve_command(command)
    command_found = command_path is not None
    release_check = _release_check(command_path, timeout_seconds, check_release)
    status = _overall_status(command_found, release_check)

    return {
        "schema_version": "0.1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "version": platform.version(),
            "machine": platform.machine(),
            "python_version": platform.python_version(),
            "python_executable": sys.executable,
            "cwd": str(Path.cwd()),
        },
        "abaqus": {
            "command": command,
            "resolved_path": str(command_path) if command_path else "",
            "command_found": command_found,
            "release_check": release_check,
        },
        "checks": _checks(command_found, release_check),
    }


def render_preflight_markdown(result: dict[str, Any]) -> str:
    """Render preflight output as a compact Markdown evidence report."""
    platform_info = result.get("platform", {})
    abaqus = result.get("abaqus", {})
    release = abaqus.get("release_check", {})
    lines = [
        "# Abaqus Environment Preflight",
        "",
        f"Overall: {str(result.get('status', 'unknown')).upper()}",
        "",
        "## Machine",
        "",
        f"- OS: {platform_info.get('system', '')} {platform_info.get('release', '')}",
        f"- Machine: {platform_info.get('machine', '')}",
        f"- Python: {platform_info.get('python_version', '')}",
        f"- Python executable: `{platform_info.get('python_executable', '')}`",
        f"- Working directory: `{platform_info.get('cwd', '')}`",
        "",
        "## Abaqus Command",
        "",
        f"- Requested command: `{abaqus.get('command', '')}`",
        f"- Resolved path: `{abaqus.get('resolved_path', '') or 'not found'}`",
        f"- Command found: {abaqus.get('command_found', False)}",
        f"- Release check: {release.get('status', 'unknown')}",
    ]
    if release.get("version"):
        lines.append(f"- Detected release: {release['version']}")
    if release.get("command"):
        lines.append(f"- Release command: `{' '.join(release['command'])}`")
    if release.get("returncode") is not None:
        lines.append(f"- Return code: {release['returncode']}")
    if release.get("output"):
        lines.extend(["", "### Release Output", "", "```text", release["output"], "```"])
    if release.get("error"):
        lines.extend(["", "### Error", "", "```text", release["error"], "```"])

    lines.extend(["", "## Checks", "", "| Check | Status | Detail |", "|-------|--------|--------|"])
    for check in result.get("checks", []):
        detail = str(check.get("detail", "")).replace("\n", " ")
        lines.append(f"| {check.get('name', '')} | {check.get('status', '')} | {detail} |")
    return "\n".join(lines)


def _resolve_command(command: str) -> Path | None:
    path = Path(command).expanduser()
    if path.exists():
        return path
    resolved = shutil.which(command)
    return Path(resolved) if resolved else None


def _release_check(command_path: Path | None, timeout_seconds: float, check_release: bool) -> dict[str, Any]:
    if not check_release:
        return {"status": "skipped", "version": "", "output": "", "error": ""}
    if command_path is None:
        return {"status": "not_run", "version": "", "output": "", "error": "abaqus command not found"}

    command = [str(command_path), "information=release"]
    try:
        proc = subprocess.run(
            command,
            cwd=os.getcwd(),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        output = _trim_output((exc.stdout or "") + "\n" + (exc.stderr or ""))
        return {
            "status": "timeout",
            "command": command,
            "version": "",
            "returncode": None,
            "output": output,
            "error": f"timed out after {timeout_seconds:g}s",
        }
    except OSError as exc:
        return {
            "status": "error",
            "command": command,
            "version": "",
            "returncode": None,
            "output": "",
            "error": str(exc),
        }

    output = _trim_output((proc.stdout or "") + "\n" + (proc.stderr or ""))
    return {
        "status": "pass" if proc.returncode == 0 else "fail",
        "command": command,
        "version": _detect_version(output),
        "returncode": proc.returncode,
        "output": output,
        "error": "" if proc.returncode == 0 else "release command returned non-zero",
    }


def _overall_status(command_found: bool, release_check: dict[str, Any]) -> str:
    if not command_found:
        return "missing_abaqus"
    release_status = release_check.get("status")
    if release_status == "pass":
        return "ready"
    if release_status == "skipped":
        return "unknown"
    return "release_check_failed"


def _checks(command_found: bool, release_check: dict[str, Any]) -> list[dict[str, str]]:
    checks = [{
        "name": "abaqus_command",
        "status": "pass" if command_found else "fail",
        "detail": "Abaqus command resolved" if command_found else "Add Abaqus to PATH or pass --abaqus-cmd",
    }]
    release_status = release_check.get("status", "unknown")
    checks.append({
        "name": "abaqus_release",
        "status": release_status,
        "detail": _release_detail(release_check),
    })
    return checks


def _release_detail(release_check: dict[str, Any]) -> str:
    status = release_check.get("status")
    if status == "pass":
        version = release_check.get("version")
        return f"Release command passed; detected {version}" if version else "Release command passed"
    if status == "skipped":
        return "Release command was skipped"
    if status == "not_run":
        return "Abaqus command was not found"
    return release_check.get("error") or "Release command did not pass"


def _detect_version(output: str) -> str:
    match = _VERSION_RE.search(output)
    return match.group(1) if match else ""


def _trim_output(output: str, limit: int = 4000) -> str:
    clean = output.strip()
    if len(clean) <= limit:
        return clean
    return clean[:limit] + "\n...[truncated]"
