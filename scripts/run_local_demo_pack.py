#!/usr/bin/env python3
# ruff: noqa: E402
"""Create a one-command local Abaqus Agent demo pack."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import zipfile
from html import escape
from pathlib import Path
from typing import Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from doctor.solver_doctor import diagnose_log_texts, render_markdown
from evidence.demo_gallery import collect_demo_gallery
from simdiff.service import collect_kpi_diff


def create_local_demo_pack(out_dir: str | Path) -> dict:
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    gallery_dir = out_path / "offline-demo-gallery"
    gallery_index = collect_demo_gallery(gallery_dir)

    doctor_dir = out_path / "solver-doctor"
    doctor_report = diagnose_log_texts(
        job_name="demo-solver-doctor",
        logs={
            ".msg": "\n".join(
                [
                    "STEP     1  INCREMENT     5",
                    "***ERROR: THE SOLUTION HAS NOT CONVERGED",
                    "***WARNING: ZERO PIVOT DETECTED AT DOF 3 NODE 100",
                ]
            ),
            ".dat": "***ERROR: License checkout failed\n",
            ".log": "Abaqus JOB demo-solver-doctor\n",
        },
        workdir=doctor_dir,
    )
    doctor_json_path = doctor_dir / "doctor.json"
    doctor_markdown_path = doctor_dir / "doctor.md"
    doctor_json_path.write_text(
        json.dumps(doctor_report.to_dict(), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    doctor_markdown_path.write_text(render_markdown(doctor_report), encoding="utf-8")

    simdiff_dir = out_path / "simulation-diff"
    simdiff_result = collect_kpi_diff(
        baseline_kpis={"U_tip": -2.0, "max_mises": 100.0, "reaction_force": 250.0},
        candidate_kpis={
            "U_tip": -2.4,
            "max_mises": 100.0,
            "reaction_force": 252.0,
            "new_contact_energy": 1.5,
        },
        tolerances={
            "U_tip": {"rtol": 0.05},
            "reaction_force": {"rtol": 0.02},
        },
        out_dir=simdiff_dir,
        diff_id="demo-simulation-diff",
        input_metadata={"case": "cantilever", "source": "local-demo-pack"},
    )
    simdiff_json_path = simdiff_dir / "diff.json"
    simdiff_markdown_path = simdiff_dir / "diff.md"

    index = {
        "schema_version": "1.0",
        "project": "abaqus-agent",
        "workflow": "local-demo-pack",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "overall_status": "PASS"
        if gallery_index["overall_status"] == "PASS" and doctor_report.status
        else "FAIL",
        "real_env_verified": False,
        "offline_demo_gallery": {
            "overall_status": gallery_index["overall_status"],
            "case_count": gallery_index["case_count"],
            "cases": gallery_index["cases"],
            "index_path": str(gallery_dir / "index.json"),
            "report_path": str(gallery_dir / "index.md"),
            "html_path": str(gallery_dir / "index.html"),
            "zip_path": gallery_index["gallery_zip_path"],
        },
        "solver_doctor": {
            "status": doctor_report.status,
            "primary_category": doctor_report.primary_category,
            "finding_count": len(doctor_report.findings),
            "json_path": str(doctor_json_path),
            "markdown_path": str(doctor_markdown_path),
        },
        "simulation_diff": {
            "status": simdiff_result["overall_status"],
            "changed_count": simdiff_result["diff"]["changed_count"],
            "added_count": simdiff_result["diff"]["added_count"],
            "removed_count": simdiff_result["diff"]["removed_count"],
            "json_path": str(simdiff_json_path),
            "markdown_path": str(simdiff_markdown_path),
        },
    }
    pack_zip_path = out_path / "local-demo-pack.zip"
    index["index_path"] = str(out_path / "index.json")
    index["markdown_path"] = str(out_path / "index.md")
    index["html_path"] = str(out_path / "index.html")
    index["pack_zip_path"] = str(pack_zip_path)
    index["manifest_path"] = str(out_path / "local-demo-pack-manifest.json")
    (out_path / "index.json").write_text(
        json.dumps(index, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (out_path / "index.md").write_text(render_demo_pack_markdown(index), encoding="utf-8")
    (out_path / "index.html").write_text(render_demo_pack_html(index), encoding="utf-8")
    _write_demo_pack_manifest(out_path=out_path, index=index)
    _write_demo_pack_zip(pack_zip_path, out_path=out_path, index=index)
    return index


def render_demo_pack_markdown(index: dict) -> str:
    gallery = index["offline_demo_gallery"]
    doctor = index["solver_doctor"]
    simdiff = index["simulation_diff"]
    return "\n".join(
        [
            "# Abaqus Agent Local Demo Pack",
            "",
            f"- Overall status: `{index['overall_status']}`",
            f"- Real Abaqus execution: `{str(index['real_env_verified']).lower()}`",
            f"- Generated at: `{index['generated_at']}`",
            "",
            "## Offline Demo Gallery",
            "",
            f"- Status: `{gallery['overall_status']}`",
            f"- Case count: `{gallery['case_count']}`",
            f"- Report: `{gallery['report_path']}`",
            f"- HTML: `{gallery['html_path']}`",
            f"- ZIP: `{gallery['zip_path']}`",
            "",
            "## Solver Doctor Sample",
            "",
            f"- Status: `{doctor['status']}`",
            f"- Primary category: `{doctor['primary_category']}`",
            f"- Findings: `{doctor['finding_count']}`",
            f"- Report: `{doctor['markdown_path']}`",
            "",
            "## Simulation Diff Sample",
            "",
            f"- Status: `{simdiff['status']}`",
            f"- Changed KPIs: `{simdiff['changed_count']}`",
            f"- Added KPIs: `{simdiff['added_count']}`",
            f"- Removed KPIs: `{simdiff['removed_count']}`",
            f"- Report: `{simdiff['markdown_path']}`",
            "",
            "This demo pack uses supplied KPI fixtures and sample log text only. It does not invoke Abaqus, read ODB files, or prove real solver execution.",
            "",
        ]
    )


def render_demo_pack_html(index: dict) -> str:
    gallery = index["offline_demo_gallery"]
    doctor = index["solver_doctor"]
    simdiff = index["simulation_diff"]
    status_class = "pass" if index["overall_status"] == "PASS" else "fail"
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Abaqus Agent Local Demo Pack</title>
  <style>
    :root {{ color-scheme: light; --ink: #20242c; --muted: #5f6877; --line: #d9dee7; --panel: #f7f9fc; --ok: #0a7a45; --bad: #b42318; }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; font: 15px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: var(--ink); background: #fff; }}
    main {{ max-width: 1040px; margin: 0 auto; padding: 40px 24px 56px; }}
    header {{ border-bottom: 1px solid var(--line); padding-bottom: 24px; margin-bottom: 24px; }}
    h1 {{ margin: 0 0 10px; font-size: 32px; line-height: 1.15; letter-spacing: 0; }}
    h2 {{ margin: 0 0 14px; font-size: 20px; letter-spacing: 0; }}
    p {{ margin: 0; color: var(--muted); }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 14px; margin: 22px 0; }}
    .panel {{ border: 1px solid var(--line); border-radius: 8px; padding: 16px; background: var(--panel); }}
    .label {{ display: block; margin-bottom: 6px; color: var(--muted); font-size: 12px; text-transform: uppercase; }}
    .value {{ font-size: 22px; font-weight: 700; }}
    .pass {{ color: var(--ok); }}
    .fail {{ color: var(--bad); }}
    .links {{ display: flex; flex-wrap: wrap; gap: 10px; margin-top: 14px; }}
    a {{ color: #174ea6; text-decoration: none; font-weight: 600; }}
    a:hover {{ text-decoration: underline; }}
    table {{ width: 100%; border-collapse: collapse; margin-top: 10px; }}
    th, td {{ padding: 10px 8px; border-bottom: 1px solid var(--line); text-align: left; vertical-align: top; }}
    th {{ color: var(--muted); font-size: 12px; text-transform: uppercase; }}
    code {{ background: #eef2f7; border-radius: 4px; padding: 2px 5px; }}
    .boundary {{ margin-top: 22px; padding: 14px 16px; border-left: 4px solid #9aa4b2; background: #f4f6f9; color: #3f4855; }}
  </style>
</head>
<body>
  <main>
    <header>
      <h1>Abaqus Agent Local Demo Pack</h1>
      <p>Offline Simulation QA evidence bundle for local review and handoff.</p>
      <div class="links">
        <a href="index.json">Index JSON</a>
        <a href="index.md">Markdown report</a>
        <a href="local-demo-pack.zip">Demo ZIP</a>
      </div>
    </header>

    <section class="grid" aria-label="Summary">
      <div class="panel"><span class="label">Overall status</span><span class="value {status_class}">{escape(index["overall_status"])}</span></div>
      <div class="panel"><span class="label">Real Abaqus execution</span><span class="value">not verified</span></div>
      <div class="panel"><span class="label">Generated at</span><span class="value">{escape(index["generated_at"])}</span></div>
    </section>

    <section class="panel">
      <h2>Included Workflows</h2>
      <table>
        <thead><tr><th>Workflow</th><th>Status</th><th>Details</th><th>Files</th></tr></thead>
        <tbody>
          <tr>
            <td>Offline Demo Gallery</td>
            <td><code>{escape(gallery["overall_status"])}</code></td>
            <td>{escape(str(gallery["case_count"]))} built-in cases</td>
            <td><a href="offline-demo-gallery/index.html">HTML</a> · <a href="offline-demo-gallery/index.md">Report</a> · <a href="offline-demo-gallery/offline-demo-gallery.zip">ZIP</a></td>
          </tr>
          <tr>
            <td>Solver Doctor Sample</td>
            <td><code>{escape(doctor["status"])}</code></td>
            <td>{escape(doctor["primary_category"])} · {escape(str(doctor["finding_count"]))} findings</td>
            <td><a href="solver-doctor/doctor.md">Report</a> · <a href="solver-doctor/doctor.json">JSON</a></td>
          </tr>
          <tr>
            <td>Simulation Diff Sample</td>
            <td><code>{escape(simdiff["status"])}</code></td>
            <td>{escape(str(simdiff["changed_count"]))} changed · {escape(str(simdiff["added_count"]))} added · {escape(str(simdiff["removed_count"]))} removed</td>
            <td><a href="simulation-diff/diff.md">Report</a> · <a href="simulation-diff/diff.json">JSON</a></td>
          </tr>
        </tbody>
      </table>
    </section>

    <p class="boundary">This demo pack uses supplied KPI fixtures and sample log text only. It does not invoke Abaqus, read ODB files, or prove real solver execution.</p>
  </main>
</body>
</html>
"""


def collect_demo_pack_vault_files(index: dict) -> dict[str, Path]:
    gallery = index["offline_demo_gallery"]
    files = {
        "index.json": Path(index["index_path"]),
        "index.md": Path(index["markdown_path"]),
        "index.html": Path(index["html_path"]),
        "local-demo-pack-manifest.json": Path(index["manifest_path"]),
        "local-demo-pack.zip": Path(index["pack_zip_path"]),
        "offline-demo-gallery/index.json": Path(gallery["index_path"]),
        "offline-demo-gallery/index.md": Path(gallery["report_path"]),
        "offline-demo-gallery/index.html": Path(gallery["html_path"]),
        "offline-demo-gallery/offline-demo-gallery.zip": Path(gallery["zip_path"]),
        "solver-doctor/doctor.json": Path(index["solver_doctor"]["json_path"]),
        "solver-doctor/doctor.md": Path(index["solver_doctor"]["markdown_path"]),
        "simulation-diff/diff.json": Path(index["simulation_diff"]["json_path"]),
        "simulation-diff/diff.md": Path(index["simulation_diff"]["markdown_path"]),
    }
    for case in gallery["cases"]:
        case_name = case["case"]
        case_prefix = f"offline-demo-gallery/{case_name}"
        files[f"{case_prefix}/evidence.json"] = Path(case["evidence_path"])
        files[f"{case_prefix}/evidence.md"] = Path(case["report_path"])
        files[f"{case_prefix}/evidence.html"] = Path(case["html_path"])
        files[f"{case_prefix}/capsule.json"] = Path(case["capsule_manifest_path"])
        files[f"{case_prefix}/{case_name}-demo-bundle.zip"] = Path(case["bundle_path"])
    return files


def _collect_demo_pack_zip_sources(out_path: Path, index: dict) -> list[tuple[Path, str]]:
    sources = [
        (out_path / "index.json", "index.json"),
        (out_path / "index.md", "index.md"),
        (out_path / "index.html", "index.html"),
        (
            Path(index["offline_demo_gallery"]["index_path"]),
            "offline-demo-gallery/index.json",
        ),
        (
            Path(index["offline_demo_gallery"]["report_path"]),
            "offline-demo-gallery/index.md",
        ),
        (
            Path(index["offline_demo_gallery"]["html_path"]),
            "offline-demo-gallery/index.html",
        ),
        (
            Path(index["offline_demo_gallery"]["zip_path"]),
            "offline-demo-gallery/offline-demo-gallery.zip",
        ),
    ]
    for case in index["offline_demo_gallery"]["cases"]:
        case_name = case["case"]
        case_prefix = f"offline-demo-gallery/{case_name}"
        sources.extend(
            [
                (Path(case["evidence_path"]), f"{case_prefix}/evidence.json"),
                (Path(case["report_path"]), f"{case_prefix}/evidence.md"),
                (Path(case["html_path"]), f"{case_prefix}/evidence.html"),
                (Path(case["capsule_manifest_path"]), f"{case_prefix}/capsule.json"),
                (Path(case["bundle_path"]), f"{case_prefix}/{case_name}-demo-bundle.zip"),
            ]
        )
    sources.extend(
        [
            (Path(index["solver_doctor"]["json_path"]), "solver-doctor/doctor.json"),
            (Path(index["solver_doctor"]["markdown_path"]), "solver-doctor/doctor.md"),
            (Path(index["simulation_diff"]["json_path"]), "simulation-diff/diff.json"),
            (Path(index["simulation_diff"]["markdown_path"]), "simulation-diff/diff.md"),
        ]
    )
    return sources


def _write_demo_pack_manifest(*, out_path: Path, index: dict) -> None:
    files = []
    for source_path, filename in _collect_demo_pack_zip_sources(out_path, index):
        payload = source_path.read_bytes()
        files.append(
            {
                "filename": filename,
                "size_bytes": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
        )
    manifest = {
        "schema_version": "1.0",
        "project": index["project"],
        "workflow": index["workflow"],
        "generated_at": index["generated_at"],
        "overall_status": index["overall_status"],
        "real_env_verified": index["real_env_verified"],
        "files": files,
    }
    Path(index["manifest_path"]).write_text(
        json.dumps(manifest, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _write_demo_pack_zip(pack_zip_path: Path, *, out_path: Path, index: dict) -> None:
    with zipfile.ZipFile(pack_zip_path, "w", compression=zipfile.ZIP_DEFLATED) as pack:
        for source_path, filename in _collect_demo_pack_zip_sources(out_path, index):
            pack.write(source_path, filename)
        pack.write(Path(index["manifest_path"]), "local-demo-pack-manifest.json")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a local product demo pack.")
    parser.add_argument("--out-dir", required=True, help="Directory for demo pack output.")
    parser.add_argument("--json", action="store_true", help="Print index JSON.")
    return parser.parse_args(argv)


def run(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    index = create_local_demo_pack(args.out_dir)
    if args.json:
        print(json.dumps(index, indent=2, sort_keys=True))
    else:
        print(render_demo_pack_markdown(index))
    return 0 if index["overall_status"] == "PASS" else 1


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
