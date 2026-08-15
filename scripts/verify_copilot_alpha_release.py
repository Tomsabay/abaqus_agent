#!/usr/bin/env python3
"""Summarize Abaqus/CAE Copilot MVP release evidence.

This gate does not publish anything. It reads local evidence artifacts and
reports whether the Copilot MVP is ready for an internal Alpha demo, while
keeping the interactive CAE GUI screenshot gap explicit.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

REAL_SMOKE_RESULT = Path("artifacts/copilot/real_smoke_cli_codex/Cantilever_200mm_Static_copilot_result.json")
PLUGIN_RUN_PLAN_TRACE = Path("artifacts/copilot/plugin_run_plan_codex/copilot_plugin_run_plan_trace.json")
PLUGIN_RUN_PLAN_RESULT = Path("artifacts/copilot/plugin_run_plan_codex/Cantilever_200mm_Static_copilot_result.json")
PLUGIN_MANIFEST = Path("artifacts/copilot/plugin_manifest/abaqus_agent_plugin_manifest.json")
GUI_SCREENSHOT = Path("artifacts/copilot/desktop_before_cae.png")

# artifacts/ is gitignored, so a fresh clone loses regenerated evidence; the
# original real-run artifacts are tracked here so the gate stays truthful.
TRACKED_EVIDENCE_DIR = Path("evidence/copilot_alpha")


def resolve_evidence_path(root: Path, primary: Path) -> Path:
    """Prefer the artifacts copy; fall back to the tracked evidence snapshot."""
    candidate = root / primary
    if candidate.exists():
        return candidate
    fallback = root / TRACKED_EVIDENCE_DIR / primary.name
    return fallback if fallback.exists() else candidate

REQUIRED_MENU_ENTRIES = [
    "AbaqusAgent Copilot: Open Sidecar",
    "AbaqusAgent Copilot: Run Current Plan",
    "AbaqusAgent Copilot: Execute Next Action",
    "AbaqusAgent Copilot: Check Session Status",
]


def collect_release_gate(
    *,
    root: Path = ROOT,
    strict_gui: bool = False,
) -> dict[str, Any]:
    checks = [
        _check_codex_real_smoke(root),
        _check_plugin_run_plan(root),
        _check_plugin_manifest(root),
        _check_gui_visual_evidence(root),
    ]
    required_pass = all(
        check["status"] == "PASS"
        for check in checks
        if check["id"] != "interactive_cae_gui_visual"
    )
    gui_status = next(
        check["status"] for check in checks if check["id"] == "interactive_cae_gui_visual"
    )
    if required_pass and gui_status == "PASS":
        overall_status = "RELEASE_READY"
    elif required_pass and gui_status == "BLOCKED" and not strict_gui:
        overall_status = "ALPHA_READY_WITH_GUI_BLOCKER"
    else:
        overall_status = "FAIL"
    return {
        "overall_status": overall_status,
        "strict_gui": strict_gui,
        "checks": checks,
        "next_required_evidence": (
            "Capture an interactive Abaqus/CAE GUI screenshot or recording showing "
            "the Plug-ins menu and AbaqusAgent Copilot: Run Current Plan."
            if gui_status != "PASS"
            else ""
        ),
    }


def write_release_gate(report: dict[str, Any], out_dir: Path) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "copilot_alpha_release_gate.json"
    markdown_path = out_dir / "copilot_alpha_release_gate.md"
    json_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    markdown_path.write_text(_render_markdown(report), encoding="utf-8")
    return {"json": str(json_path), "markdown": str(markdown_path)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", default="artifacts/copilot/release_gate")
    parser.add_argument("--strict-gui", action="store_true")
    args = parser.parse_args(argv)

    report = collect_release_gate(root=ROOT, strict_gui=args.strict_gui)
    paths = write_release_gate(report, Path(args.out_dir))
    output = report | {"files": paths}
    print(json.dumps(output, indent=2, ensure_ascii=False, sort_keys=True))
    return 0 if report["overall_status"] != "FAIL" else 1


def _check_codex_real_smoke(root: Path) -> dict[str, Any]:
    path = resolve_evidence_path(root, REAL_SMOKE_RESULT)
    data = _read_json(path)
    passed = data.get("status") == "COMPLETED"
    return {
        "id": "codex_strict_real_abaqus_smoke",
        "status": "PASS" if passed else "FAIL",
        "artifact": str(path),
        "evidence": {
            "job_name": data.get("job_name"),
            "status": data.get("status"),
            "max_displacement": data.get("max_displacement"),
            "max_mises": data.get("max_mises"),
        },
    }


def _check_plugin_run_plan(root: Path) -> dict[str, Any]:
    trace_path = resolve_evidence_path(root, PLUGIN_RUN_PLAN_TRACE)
    result_path = resolve_evidence_path(root, PLUGIN_RUN_PLAN_RESULT)
    trace = _read_json(trace_path)
    result = _read_json(result_path)
    executed = [item.get("action") for item in trace.get("executed", [])]
    passed = (
        trace.get("status") == "completed"
        and trace.get("summary", {}).get("pending_count") == 0
        and trace.get("summary", {}).get("completed_count") == 3
        and result.get("status") == "COMPLETED"
    )
    return {
        "id": "plugin_run_current_plan_real_abaqus",
        "status": "PASS" if passed else "FAIL",
        "artifact": str(trace_path),
        "evidence": {
            "executed_actions": executed,
            "completed_count": trace.get("summary", {}).get("completed_count"),
            "pending_count": trace.get("summary", {}).get("pending_count"),
            "result_path": str(result_path),
            "result_status": result.get("status"),
        },
    }


def _check_plugin_manifest(root: Path) -> dict[str, Any]:
    path = resolve_evidence_path(root, PLUGIN_MANIFEST)
    data = _read_json(path)
    menu_entries = data.get("menu_entries") or []
    missing = [entry for entry in REQUIRED_MENU_ENTRIES if entry not in menu_entries]
    passed = not missing and data.get("default_action") == "AbaqusAgent Copilot: Run Current Plan"
    return {
        "id": "plugin_runtime_manifest",
        "status": "PASS" if passed else "FAIL",
        "artifact": str(path),
        "evidence": {
            "menu_entries": menu_entries,
            "missing_menu_entries": missing,
            "default_action": data.get("default_action"),
            "server_url": data.get("server_url"),
            "session_id": data.get("session_id"),
        },
    }


def _check_gui_visual_evidence(root: Path) -> dict[str, Any]:
    path = root / GUI_SCREENSHOT
    exists = path.exists()
    size = path.stat().st_size if exists else 0
    # The current captured artifact is a black SSH-session screenshot, not proof
    # of an interactive Abaqus/CAE Plug-ins menu.
    return {
        "id": "interactive_cae_gui_visual",
        "status": "BLOCKED",
        "artifact": str(path),
        "evidence": {
            "screenshot_exists": exists,
            "screenshot_bytes": size,
            "blocker": (
                "SSH-launched GUI processes run in Session 0 and CopyFromScreen "
                "returns a black frame; RDP/console capture is required."
            ),
        },
    }


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Copilot Alpha Release Gate",
        "",
        f"Overall status: `{report['overall_status']}`",
        f"Strict GUI: `{report['strict_gui']}`",
        "",
        "## Checks",
    ]
    for check in report["checks"]:
        lines.extend(
            [
                "",
                f"### {check['id']}",
                "",
                f"- Status: `{check['status']}`",
                f"- Artifact: `{check['artifact']}`",
                "- Evidence:",
                "```json",
                json.dumps(check["evidence"], indent=2, ensure_ascii=False, sort_keys=True),
                "```",
            ]
        )
    if report.get("next_required_evidence"):
        lines.extend(["", "## Next Required Evidence", "", report["next_required_evidence"]])
    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
