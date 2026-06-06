#!/usr/bin/env python3
"""
Render a smoke evidence JSON bundle into a human-readable Markdown report.

This renderer is intentionally evidence-only. It does not run Abaqus and does
not upgrade dry-run or mock-real evidence into real environment verification.
"""

from __future__ import annotations

import argparse
import json
import shlex
import sys
from pathlib import Path
from typing import Sequence


def load_evidence(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"smoke evidence not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("smoke evidence must be a JSON object")
    if "stages" not in data or not isinstance(data["stages"], list):
        raise ValueError("smoke evidence is missing a stages[] array")
    return data


def _text(value: object, default: str = "") -> str:
    if value is None:
        return default
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _md_cell(value: object) -> str:
    text = _text(value, "-").replace("\n", " ").replace("|", "\\|")
    return text if text else "-"


def _format_command(command: object) -> str:
    if not command:
        return "-"
    if isinstance(command, list):
        return shlex.join(str(part) for part in command)
    return str(command)


def _missing_items(evidence: dict) -> list[dict]:
    items: list[dict] = []
    for key in ("require_real_missing", "missing"):
        for item in evidence.get(key, []):
            if isinstance(item, dict) and item not in items:
                items.append(item)
    return items


def render_markdown(evidence: dict, *, source_path: Path | None = None) -> str:
    title = "Abaqus Smoke Evidence Report"
    lines = [
        f"# {title}",
        "",
        "## Summary",
        "",
        f"- Project: `{_text(evidence.get('project'), 'unknown')}`",
        f"- Mode: `{_text(evidence.get('mode'), 'unknown')}`",
        f"- Case: `{_text(evidence.get('case'), 'unknown')}`",
        f"- Overall status: `{_text(evidence.get('overall_status'), 'unknown')}`",
        f"- Real Abaqus verified: `{_text(evidence.get('real_env_verified'), 'false')}`",
        f"- Generated at: `{_text(evidence.get('generated_at'), 'unknown')}`",
        f"- Evidence directory: `{_text(evidence.get('out_dir'), 'unknown')}`",
    ]
    if source_path:
        lines.append(f"- Source evidence: `{source_path}`")

    lines.extend(
        [
            "",
            "## Verification Boundary",
            "",
        ]
    )
    if evidence.get("real_env_verified"):
        lines.append(
            "This bundle records real-environment verification for every stage marked as requiring real Abaqus."
        )
    else:
        lines.append(
            "This bundle is not proof of real Abaqus end-to-end execution. Dry-run, mock-real, missing-prerequisite, and environment-limited stages remain non-real verification."
        )

    missing = _missing_items(evidence)
    if missing:
        lines.extend(["", "## Missing Prerequisites", ""])
        for item in missing:
            capability = _text(item.get("capability") or item.get("name"), "unknown")
            reason = _text(item.get("reason") or item.get("missing_reason"), "unspecified")
            lines.append(f"- `{capability}`: {reason}")

    lines.extend(
        [
            "",
            "## Stage Summary",
            "",
            "| Stage | Status | Real Required | Real Verified | Artifact | Missing Reason |",
            "|---|---|---:|---:|---|---|",
        ]
    )
    for stage in evidence["stages"]:
        lines.append(
            "| {name} | {status} | {required} | {verified} | {artifact} | {missing_reason} |".format(
                name=_md_cell(stage.get("name")),
                status=_md_cell(stage.get("status")),
                required=_md_cell(stage.get("real_env_required")),
                verified=_md_cell(stage.get("real_env_verified")),
                artifact=_md_cell(stage.get("artifact_path")),
                missing_reason=_md_cell(stage.get("missing_reason")),
            )
        )

    lines.extend(["", "## Stage Evidence", ""])
    for stage in evidence["stages"]:
        lines.extend(
            [
                f"### {_text(stage.get('name'), 'unknown')}",
                "",
                f"- Status: `{_text(stage.get('status'), 'unknown')}`",
                f"- Command: `{_format_command(stage.get('command'))}`",
                f"- Artifact: `{_text(stage.get('artifact_path'), '-')}`",
            ]
        )
        missing_reason = stage.get("missing_reason")
        if missing_reason:
            lines.append(f"- Missing reason: {missing_reason}")
        stage_evidence = stage.get("evidence") or []
        if stage_evidence:
            lines.append("- Evidence:")
            for item in stage_evidence:
                lines.append(f"  - `{_text(item)}`")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render smoke_evidence.json into Markdown.")
    parser.add_argument("evidence", help="Path to smoke_evidence.json.")
    parser.add_argument(
        "--out",
        help="Optional Markdown output path. Prints to stdout when omitted.",
    )
    return parser.parse_args(argv)


def run(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    evidence_path = Path(args.evidence)
    try:
        evidence = load_evidence(evidence_path)
        markdown = render_markdown(evidence, source_path=evidence_path)
    except (FileNotFoundError, json.JSONDecodeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.out:
        Path(args.out).write_text(markdown, encoding="utf-8")
    else:
        print(markdown, end="")
    return 0


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
