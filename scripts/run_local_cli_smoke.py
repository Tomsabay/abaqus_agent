#!/usr/bin/env python3
"""Run a no-server product smoke over local CLI inspection surfaces."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import time
import zipfile
from html import escape
from pathlib import Path
from typing import Any, Callable, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from evidence.vault import create_vault_entry  # noqa: E402
from scripts.run_local_demo_pack import (  # noqa: E402
    collect_demo_pack_vault_files,
    create_local_demo_pack,
)

CheckFn = Callable[[dict[str, Any]], tuple[bool, str]]


def collect_local_cli_smoke(out_dir: str | Path, vault_root: str | Path | None = None) -> dict[str, Any]:
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    vault_path = Path(vault_root) if vault_root else out_path / "evidence-vault"
    demo_pack_dir = out_path / "demo-pack"
    demo_index = create_local_demo_pack(demo_pack_dir)
    vault_record = create_vault_entry(
        kind="local-demo-pack",
        title="local-cli-smoke-demo-pack",
        files=collect_demo_pack_vault_files(demo_index),
        summary={
            "overall_status": demo_index["overall_status"],
            "gallery_cases": demo_index["offline_demo_gallery"]["case_count"],
            "solver_doctor_status": demo_index["solver_doctor"]["status"],
            "simulation_diff_status": demo_index["simulation_diff"]["status"],
            "real_env_verified": False,
        },
        root=vault_path,
    )
    vault_id = vault_record["vault_id"]

    steps = [
        _run_json_step(
            "evidence-vault-list",
            [
                "scripts/inspect_evidence_vault.py",
                "--root",
                str(vault_path),
                "list",
                "--query",
                "local-demo-pack.zip",
                "--kind",
                "local-demo-pack",
                "--status",
                "PASS",
            ],
            lambda data: (data["total"] >= 1, f"{data['total']} matching vault entries"),
        ),
        _run_json_step(
            "evidence-vault-detail",
            [
                "scripts/inspect_evidence_vault.py",
                "--root",
                str(vault_path),
                "detail",
                vault_id,
            ],
            lambda data: (data["vault_id"] == vault_id, f"detail for {data['vault_id']}"),
        ),
        _run_json_step(
            "evidence-vault-read",
            [
                "scripts/inspect_evidence_vault.py",
                "--root",
                str(vault_path),
                "read",
                vault_id,
                "index.md",
                "--max-chars",
                "120",
            ],
            lambda data: ("Abaqus Agent Local Demo Pack" in data["content"], "read index.md text artifact"),
        ),
        _run_json_step(
            "evidence-vault-copy",
            [
                "scripts/inspect_evidence_vault.py",
                "--root",
                str(vault_path),
                "copy",
                vault_id,
                "local-demo-pack.zip",
                "--out",
                str(out_path / "copied-local-demo-pack.zip"),
            ],
            lambda data: (
                Path(data["output_path"]).exists()
                and Path(data["output_path"]).name == "copied-local-demo-pack.zip",
                "copied local-demo-pack.zip artifact",
            ),
        ),
        _run_json_step(
            "case-memory-search",
            [
                "scripts/inspect_case_memory.py",
                "--root",
                str(vault_path),
                "search",
                "--query",
                "local-cli-smoke-demo-pack",
                "--kind",
                "local-demo-pack",
                "--status",
                "PASS",
            ],
            lambda data: (data["total"] >= 1, f"{data['total']} matching memory entries"),
        ),
        _run_json_step(
            "case-memory-detail",
            [
                "scripts/inspect_case_memory.py",
                "--root",
                str(vault_path),
                "detail",
                vault_id,
            ],
            lambda data: (data["memory_id"] == vault_id, f"detail for {data['memory_id']}"),
        ),
        _run_json_step(
            "case-memory-diff",
            [
                "scripts/inspect_case_memory.py",
                "--root",
                str(vault_path),
                "diff",
                vault_id,
                vault_id,
                "--baseline-filename",
                "offline-demo-gallery/cantilever/evidence.json",
                "--candidate-filename",
                "offline-demo-gallery/plate_hole/evidence.json",
                "--diff-id",
                "local-cli-smoke-diff",
                "--out-dir",
                str(out_path / "case-memory-diff"),
            ],
            lambda data: (data["overall_status"] == "FAIL", "nested Case Memory diff returned FAIL"),
        ),
        _run_json_step(
            "kpi-recipes-list",
            [
                "scripts/inspect_kpi_recipes.py",
                "list",
                "--case",
                "modal",
                "--kpi-type",
                "eigenfrequency",
            ],
            lambda data: (data["total"] == 1, "modal eigenfrequency recipe listed"),
        ),
        _run_json_step(
            "kpi-recipes-export",
            [
                "scripts/inspect_kpi_recipes.py",
                "export",
                "modal-first-three-frequencies",
                "--out",
                str(out_path / "modal-kpi-spec.json"),
            ],
            lambda data: (Path(data["kpi_spec_path"]).exists(), "modal recipe kpi_spec exported"),
        ),
        _run_json_step(
            "solver-doctor-patterns-list",
            [
                "scripts/inspect_solver_doctor_patterns.py",
                "list",
                "--category",
                "license",
                "--severity",
                "error",
            ],
            lambda data: (data["total"] >= 1, "license error patterns listed"),
        ),
        _run_json_step(
            "solver-doctor-patterns-detail",
            [
                "scripts/inspect_solver_doctor_patterns.py",
                "detail",
                "msg-10-license",
            ],
            lambda data: (data["pattern"]["category"] == "LICENSE", "license pattern detail loaded"),
        ),
    ]

    report = {
        "schema_version": "1.0",
        "project": "abaqus-agent",
        "workflow": "local-cli-smoke",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "overall_status": "PASS" if all(step["status"] == "PASS" for step in steps) else "FAIL",
        "real_env_verified": False,
        "vault_root": str(vault_path),
        "vault_id": vault_id,
        "demo_pack_index": demo_index["index_path"],
        "steps": steps,
    }
    report["json_path"] = str(out_path / "local_cli_smoke.json")
    report["markdown_path"] = str(out_path / "local_cli_smoke.md")
    report["html_path"] = str(out_path / "local_cli_smoke.html")
    report["zip_path"] = str(out_path / "local_cli_smoke.zip")
    report["manifest_path"] = str(out_path / "local_cli_smoke_manifest.json")
    report["copied_demo_pack_zip_path"] = str(out_path / "copied-local-demo-pack.zip")
    _write_report_files(report, out_path)
    _write_smoke_manifest(report, out_path)
    _write_smoke_zip(out_path)
    smoke_vault = create_vault_entry(
        kind="local-cli-smoke",
        title="local-cli-smoke-report",
        files={
            "local_cli_smoke.json": out_path / "local_cli_smoke.json",
            "local_cli_smoke.md": out_path / "local_cli_smoke.md",
            "local_cli_smoke.html": out_path / "local_cli_smoke.html",
            "local_cli_smoke_manifest.json": out_path / "local_cli_smoke_manifest.json",
            "local_cli_smoke.zip": out_path / "local_cli_smoke.zip",
            "copied-local-demo-pack.zip": out_path / "copied-local-demo-pack.zip",
        },
        summary={
            "overall_status": report["overall_status"],
            "step_count": len(steps),
            "vault_id": vault_id,
            "real_env_verified": False,
        },
        root=vault_path,
    )
    report["smoke_vault_id"] = smoke_vault["vault_id"]
    report["smoke_vault_root"] = str(vault_path)
    report["smoke_vault_files"] = sorted(smoke_vault["files"])
    _write_report_files(report, out_path)
    _write_smoke_manifest(report, out_path)
    _write_smoke_zip(out_path)
    _rewrite_stored_smoke_report(report, vault_path)
    return report


def _run_json_step(name: str, args: list[str], check: CheckFn) -> dict[str, Any]:
    command = [sys.executable, str(ROOT / args[0]), *args[1:]]
    proc = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    data: dict[str, Any] = {}
    detail = ""
    status = "FAIL"
    if proc.stdout.strip():
        try:
            data = json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            detail = f"Invalid JSON output: {exc}"
    if proc.returncode == 0 and data:
        try:
            ok, detail = check(data)
        except (KeyError, TypeError, ValueError) as exc:
            ok = False
            detail = str(exc)
        status = "PASS" if ok else "FAIL"
    elif not detail:
        detail = data.get("error") if data else (proc.stderr.strip() or "command failed")
    return {
        "name": name,
        "status": status,
        "returncode": proc.returncode,
        "detail": detail,
        "command": command,
    }


def render_smoke_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Abaqus Agent Local CLI Smoke",
        "",
        f"- Overall status: `{report['overall_status']}`",
        f"- Real Abaqus execution: `{'verified' if report['real_env_verified'] else 'not verified'}`",
        f"- Vault id: `{report['vault_id']}`",
        f"- Vault root: `{report['vault_root']}`",
    ]
    if report.get("smoke_vault_id"):
        lines.append(f"- Smoke report vault id: `{report['smoke_vault_id']}`")
    lines.extend(
        [
            "",
            "## Steps",
            "",
            "| Step | Status | Detail |",
            "|---|---|---|",
        ]
    )
    for step in report["steps"]:
        lines.append(f"| `{step['name']}` | `{step['status']}` | {step['detail']} |")
    lines.extend(
        [
            "",
            "## Verification Boundary",
            "",
            "This smoke uses supplied KPI fixtures, generated local demo artifacts, and sample log text only. It does not invoke Abaqus, read ODB files, start a server, or prove real solver execution.",
            "",
        ]
    )
    return "\n".join(lines)


def _write_report_files(report: dict[str, Any], out_path: Path) -> None:
    (out_path / "local_cli_smoke.json").write_text(
        json.dumps(report, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (out_path / "local_cli_smoke.md").write_text(render_smoke_markdown(report), encoding="utf-8")
    (out_path / "local_cli_smoke.html").write_text(render_smoke_html(report), encoding="utf-8")


def _write_smoke_zip(out_path: Path) -> None:
    with zipfile.ZipFile(out_path / "local_cli_smoke.zip", "w", zipfile.ZIP_DEFLATED) as bundle:
        for filename in (
            "local_cli_smoke.json",
            "local_cli_smoke.md",
            "local_cli_smoke.html",
            "local_cli_smoke_manifest.json",
            "copied-local-demo-pack.zip",
        ):
            path = out_path / filename
            if path.exists():
                bundle.write(path, arcname=filename)


def _write_smoke_manifest(report: dict[str, Any], out_path: Path) -> None:
    files = []
    for filename in (
        "local_cli_smoke.json",
        "local_cli_smoke.md",
        "local_cli_smoke.html",
        "copied-local-demo-pack.zip",
    ):
        path = out_path / filename
        if not path.exists():
            continue
        files.append(
            {
                "filename": filename,
                "size_bytes": path.stat().st_size,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
    manifest = {
        "schema_version": "1.0",
        "project": report["project"],
        "workflow": report["workflow"],
        "generated_at": report["generated_at"],
        "overall_status": report["overall_status"],
        "real_env_verified": report["real_env_verified"],
        "vault_id": report["vault_id"],
        "smoke_vault_id": report.get("smoke_vault_id"),
        "files": files,
    }
    (out_path / "local_cli_smoke_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _rewrite_stored_smoke_report(report: dict[str, Any], vault_path: Path) -> None:
    smoke_dir = vault_path / report["smoke_vault_id"]
    stored_json = smoke_dir / "local_cli_smoke.json"
    stored_markdown = smoke_dir / "local_cli_smoke.md"
    stored_html = smoke_dir / "local_cli_smoke.html"
    stored_manifest = smoke_dir / "local_cli_smoke_manifest.json"
    copied_demo_pack = Path(report.get("copied_demo_pack_zip_path", ""))
    stored_json.write_text(
        json.dumps(report, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    stored_markdown.write_text(render_smoke_markdown(report), encoding="utf-8")
    stored_html.write_text(render_smoke_html(report), encoding="utf-8")
    if copied_demo_pack.exists():
        shutil.copy2(copied_demo_pack, smoke_dir / "copied-local-demo-pack.zip")
    _write_smoke_manifest(report, smoke_dir)
    _write_smoke_zip(smoke_dir)
    record_path = smoke_dir / "record.json"
    record = json.loads(record_path.read_text(encoding="utf-8"))
    record["summary"]["smoke_vault_id"] = report["smoke_vault_id"]
    record["files"]["local_cli_smoke.json"]["size_bytes"] = stored_json.stat().st_size
    record["files"]["local_cli_smoke.md"]["size_bytes"] = stored_markdown.stat().st_size
    record["files"]["local_cli_smoke.html"]["size_bytes"] = stored_html.stat().st_size
    record["files"]["local_cli_smoke_manifest.json"]["size_bytes"] = stored_manifest.stat().st_size
    record["files"]["local_cli_smoke.zip"]["size_bytes"] = (
        smoke_dir / "local_cli_smoke.zip"
    ).stat().st_size
    record_path.write_text(
        json.dumps(record, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def render_smoke_html(report: dict[str, Any]) -> str:
    status_class = "pass" if report["overall_status"] == "PASS" else "fail"
    step_rows = "\n".join(
        "<tr>"
        f"<td><code>{escape(step['name'])}</code></td>"
        f"<td><span class=\"{escape(step['status'].lower())}\">{escape(step['status'])}</span></td>"
        f"<td>{escape(step['detail'])}</td>"
        "</tr>"
        for step in report["steps"]
    )
    smoke_vault_line = ""
    if report.get("smoke_vault_id"):
        smoke_vault_line = (
            "<p><span>Smoke report vault id</span>"
            f"<strong>{escape(report['smoke_vault_id'])}</strong></p>"
        )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Abaqus Agent Local CLI Smoke</title>
  <style>
    :root {{ color-scheme: light; --ink: #20242c; --muted: #5f6877; --line: #d8dee8; --panel: #f7f9fc; --ok: #0a7a45; --bad: #b42318; }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; font: 15px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: var(--ink); background: #fff; }}
    main {{ max-width: 1040px; margin: 0 auto; padding: 40px 24px 56px; }}
    header {{ border-bottom: 1px solid var(--line); padding-bottom: 22px; margin-bottom: 22px; }}
    h1 {{ margin: 0 0 8px; font-size: 32px; line-height: 1.15; letter-spacing: 0; }}
    h2 {{ margin: 0 0 12px; font-size: 20px; letter-spacing: 0; }}
    p {{ margin: 0 0 8px; color: var(--muted); }}
    .summary {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 12px; margin: 18px 0 24px; }}
    .panel {{ border: 1px solid var(--line); border-radius: 8px; padding: 15px; background: var(--panel); }}
    .panel span {{ display: block; color: var(--muted); font-size: 12px; text-transform: uppercase; margin-bottom: 6px; }}
    .panel strong {{ display: block; overflow-wrap: anywhere; font-size: 20px; }}
    .pass {{ color: var(--ok); font-weight: 700; }}
    .fail {{ color: var(--bad); font-weight: 700; }}
    table {{ width: 100%; border-collapse: collapse; }}
    th, td {{ padding: 10px 8px; border-bottom: 1px solid var(--line); text-align: left; vertical-align: top; }}
    th {{ color: var(--muted); font-size: 12px; text-transform: uppercase; }}
    code {{ background: #eef2f7; border-radius: 4px; padding: 2px 5px; }}
    .boundary {{ margin-top: 22px; padding: 14px 16px; border-left: 4px solid #9aa4b2; background: #f4f6f9; color: #3f4855; }}
  </style>
</head>
<body>
  <main>
    <header>
      <h1>Abaqus Agent Local CLI Smoke</h1>
      <p>No-server product smoke over local Evidence Vault, Case Memory, KPI Recipe, and Solver Doctor Pattern CLI surfaces.</p>
    </header>
    <section class="summary" aria-label="Summary">
      <div class="panel"><span>Overall status</span><strong class="{status_class}">{escape(report["overall_status"])}</strong></div>
      <div class="panel"><span>Real Abaqus execution</span><strong>not verified</strong></div>
      <div class="panel"><span>Demo pack vault id</span><strong>{escape(report["vault_id"])}</strong></div>
      <div class="panel"><span>Vault root</span><strong>{escape(report["vault_root"])}</strong></div>
      <div class="panel">{smoke_vault_line}</div>
    </section>
    <section class="panel">
      <h2>Smoke Steps</h2>
      <table>
        <thead><tr><th>Step</th><th>Status</th><th>Detail</th></tr></thead>
        <tbody>
          {step_rows}
        </tbody>
      </table>
    </section>
    <p class="boundary">This smoke uses supplied KPI fixtures, generated local demo artifacts, and sample log text only. It does not invoke Abaqus, read ODB files, start a server, or prove real solver execution.</p>
  </main>
</body>
</html>
"""


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run local no-server CLI smoke.")
    parser.add_argument("--out-dir", required=True, help="Directory for smoke report output.")
    parser.add_argument("--vault-root", default=None, help="Optional Evidence Vault root.")
    parser.add_argument("--json", action="store_true", help="Print report JSON.")
    return parser.parse_args(argv)


def run(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    report = collect_local_cli_smoke(args.out_dir, vault_root=args.vault_root)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(render_smoke_markdown(report))
    return 0 if report["overall_status"] == "PASS" else 1


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
