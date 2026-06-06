"""Offline demo gallery generation for built-in evidence examples."""

from __future__ import annotations

import json
import time
import zipfile
from html import escape as escape_html
from pathlib import Path

from evidence.examples import GALLERY_EXAMPLE_CASES
from evidence.offline import collect_evidence_from_files

ROOT = Path(__file__).resolve().parents[1]


def collect_demo_gallery(out_dir: str | Path) -> dict:
    """Run all built-in offline examples and write a portable gallery."""
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    cases = []
    for case_name in GALLERY_EXAMPLE_CASES:
        case_out = out_path / case_name
        evidence = collect_evidence_from_files(
            baseline_kpis_path=ROOT / "examples" / "kpis" / f"{case_name}_baseline.json",
            candidate_kpis_path=ROOT / "examples" / "kpis" / f"{case_name}_candidate.json",
            contracts_path=ROOT / "examples" / "contracts" / f"{case_name}.yaml",
            out_dir=case_out,
            run_id=f"{case_name}-demo-gallery",
            extra_inputs=[ROOT / "cases" / case_name / "spec.yaml"],
        )
        evidence_path = case_out / "evidence.json"
        report_path = case_out / "evidence.md"
        html_path = case_out / "evidence.html"
        capsule_path = Path(evidence["capsule"]["manifest_path"])
        bundle_path = case_out / f"{case_name}-demo-bundle.zip"
        _write_case_bundle(
            bundle_path=bundle_path,
            case_name=case_name,
            evidence=evidence,
            evidence_path=evidence_path,
            report_path=report_path,
            html_path=html_path,
            capsule_path=capsule_path,
        )
        cases.append(
            {
                "case": case_name,
                "run_id": evidence["run_id"],
                "overall_status": evidence["overall_status"],
                "contracts_status": evidence["contracts"]["status"],
                "diff_status": evidence["diff"]["status"],
                "capsule_hash": evidence["capsule"]["capsule_hash"],
                "evidence_path": str(evidence_path),
                "report_path": str(report_path),
                "html_path": str(html_path),
                "capsule_manifest_path": str(capsule_path),
                "bundle_path": str(bundle_path),
            }
        )

    index = {
        "schema_version": "1.0",
        "project": "abaqus-agent",
        "workflow": "offline-demo-gallery",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "overall_status": "PASS"
        if all(case["overall_status"] == "PASS" for case in cases)
        else "FAIL",
        "case_count": len(cases),
        "cases": cases,
    }
    index_html_path = out_path / "index.html"
    index["index_html_path"] = str(index_html_path)
    index_html_path.write_text(render_index_html(index), encoding="utf-8")
    (out_path / "index.json").write_text(
        json.dumps(index, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (out_path / "index.md").write_text(render_index_markdown(index), encoding="utf-8")
    gallery_zip_path = out_path / "offline-demo-gallery.zip"
    _write_gallery_zip(gallery_zip_path, index=index, out_path=out_path)
    index["gallery_zip_path"] = str(gallery_zip_path)
    (out_path / "index.json").write_text(
        json.dumps(index, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return index


def render_index_markdown(index: dict) -> str:
    lines = [
        "# Abaqus Agent Offline Demo Gallery",
        "",
        f"- Overall status: `{index['overall_status']}`",
        f"- Case count: `{index['case_count']}`",
        f"- Generated at: `{index['generated_at']}`",
        "- Real Abaqus execution: `not verified`",
        "",
        "| Case | Overall | Contracts | Diff | Report | Bundle |",
        "|---|---|---|---|---|---|",
    ]
    for case in index["cases"]:
        lines.append(
            "| {case} | `{overall}` | `{contracts}` | `{diff}` | `{report}` | `{bundle}` |".format(
                case=case["case"],
                overall=case["overall_status"],
                contracts=case["contracts_status"],
                diff=case["diff_status"],
                report=case["report_path"],
                bundle=case["bundle_path"],
            )
        )
    lines.extend(
        [
            "",
            "This gallery uses supplied KPI JSON fixtures only. It does not invoke Abaqus, read ODB files, or prove real solver execution.",
            "",
        ]
    )
    return "\n".join(lines)


def render_index_html(index: dict) -> str:
    rows = []
    for case in index["cases"]:
        case_name = escape_html(case["case"])
        overall = escape_html(case["overall_status"])
        contracts = escape_html(case["contracts_status"])
        diff = escape_html(case["diff_status"])
        capsule_hash = escape_html(case["capsule_hash"][:12])
        rows.append(
            "\n".join(
                [
                    "<tr>",
                    f"<td>{case_name}</td>",
                    f"<td><span class=\"status status-{overall.lower()}\">{overall}</span></td>",
                    f"<td>{contracts}</td>",
                    f"<td>{diff}</td>",
                    f"<td><code>{capsule_hash}</code></td>",
                    (
                        f"<td><a href=\"{case_name}/evidence.html\">HTML</a> "
                        f"<a href=\"{case_name}/evidence.md\">Markdown</a> "
                        f"<a href=\"{case_name}/{case_name}-demo-bundle.zip\">Bundle</a></td>"
                    ),
                    "</tr>",
                ]
            )
        )

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Abaqus Agent Offline Demo Gallery</title>
  <style>
    :root {{
      color-scheme: light;
      --ink: #17202a;
      --muted: #5d6d7e;
      --line: #d7dde4;
      --panel: #f7f9fb;
      --accent: #0b6bcb;
      --pass: #117a37;
      --fail: #a93226;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: var(--ink);
      background: #ffffff;
      line-height: 1.45;
    }}
    main {{ max-width: 1100px; margin: 0 auto; padding: 32px 20px 40px; }}
    h1 {{ margin: 0 0 8px; font-size: 30px; letter-spacing: 0; }}
    p {{ margin: 0; color: var(--muted); }}
    .summary {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 12px;
      margin: 24px 0;
    }}
    .metric {{ border: 1px solid var(--line); border-radius: 8px; padding: 14px 16px; }}
    .metric span {{ display: block; color: var(--muted); font-size: 13px; }}
    .metric strong {{ display: block; margin-top: 6px; font-size: 20px; }}
    table {{ width: 100%; border-collapse: collapse; border: 1px solid var(--line); }}
    th, td {{ padding: 11px 12px; border-bottom: 1px solid var(--line); text-align: left; }}
    th {{ background: var(--panel); font-size: 13px; color: #34495e; }}
    a {{ color: var(--accent); text-decoration: none; margin-right: 10px; }}
    code {{ font-family: "SFMono-Regular", Consolas, monospace; font-size: 12px; }}
    .status {{ font-weight: 700; }}
    .status-pass {{ color: var(--pass); }}
    .status-fail {{ color: var(--fail); }}
    .boundary {{
      margin-top: 20px;
      padding: 12px 14px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      color: #34495e;
    }}
    @media (max-width: 720px) {{
      main {{ padding: 24px 14px 32px; }}
      table {{ display: block; overflow-x: auto; white-space: nowrap; }}
    }}
  </style>
</head>
<body>
  <main>
    <h1>Abaqus Agent Offline Demo Gallery</h1>
    <p>Four supplied KPI fixture cases rendered as portable offline evidence reports.</p>
    <section class="summary" aria-label="Gallery summary">
      <div class="metric"><span>Overall status</span><strong>{escape_html(index["overall_status"])}</strong></div>
      <div class="metric"><span>Case count</span><strong>{escape_html(str(index["case_count"]))}</strong></div>
      <div class="metric"><span>Generated at</span><strong>{escape_html(index["generated_at"])}</strong></div>
      <div class="metric"><span>Real Abaqus execution</span><strong>not verified</strong></div>
    </section>
    <table>
      <thead>
        <tr>
          <th>Case</th>
          <th>Overall</th>
          <th>Contracts</th>
          <th>Diff</th>
          <th>Capsule hash</th>
          <th>Artifacts</th>
        </tr>
      </thead>
      <tbody>
        {"".join(rows)}
      </tbody>
    </table>
    <p class="boundary">This gallery uses supplied KPI JSON fixtures only. It does not invoke Abaqus, read ODB files, or prove real solver execution.</p>
  </main>
</body>
</html>
"""


def _write_case_bundle(
    *,
    bundle_path: Path,
    case_name: str,
    evidence: dict,
    evidence_path: Path,
    report_path: Path,
    html_path: Path,
    capsule_path: Path,
) -> None:
    manifest = {
        "schema_version": "1.0",
        "case": case_name,
        "run_id": evidence["run_id"],
        "overall_status": evidence["overall_status"],
        "files": ["evidence.json", "evidence.md", "evidence.html", "capsule.json"],
    }
    with zipfile.ZipFile(bundle_path, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        bundle.write(evidence_path, "evidence.json")
        bundle.write(report_path, "evidence.md")
        bundle.write(html_path, "evidence.html")
        bundle.write(capsule_path, "capsule.json")
        bundle.writestr("bundle_manifest.json", json.dumps(manifest, indent=2, sort_keys=True))


def _write_gallery_zip(gallery_zip_path: Path, *, index: dict, out_path: Path) -> None:
    manifest = {
        "schema_version": "1.0",
        "workflow": index["workflow"],
        "overall_status": index["overall_status"],
        "case_count": index["case_count"],
        "files": ["index.json", "index.md", "index.html", "<case>/*", "cases/*"],
    }
    with zipfile.ZipFile(gallery_zip_path, "w", compression=zipfile.ZIP_DEFLATED) as gallery:
        gallery.write(out_path / "index.json", "index.json")
        gallery.write(out_path / "index.md", "index.md")
        gallery.write(out_path / "index.html", "index.html")
        gallery.writestr(
            "gallery_manifest.json",
            json.dumps(manifest, indent=2, sort_keys=True),
        )
        for case in index["cases"]:
            case_name = case["case"]
            case_dir = out_path / case_name
            gallery.write(case_dir / "evidence.json", f"{case_name}/evidence.json")
            gallery.write(case_dir / "evidence.md", f"{case_name}/evidence.md")
            gallery.write(case_dir / "evidence.html", f"{case_name}/evidence.html")
            gallery.write(
                Path(case["capsule_manifest_path"]),
                f"{case_name}/capsule.json",
            )
            gallery.write(Path(case["bundle_path"]), f"{case_name}/{case_name}-demo-bundle.zip")
            gallery.write(case_dir / "evidence.json", f"cases/{case_name}/evidence.json")
            gallery.write(case_dir / "evidence.md", f"cases/{case_name}/evidence.md")
            gallery.write(case_dir / "evidence.html", f"cases/{case_name}/evidence.html")
            gallery.write(
                Path(case["capsule_manifest_path"]),
                f"cases/{case_name}/capsule.json",
            )
            gallery.write(Path(case["bundle_path"]), f"cases/{case_name}/{case_name}-demo-bundle.zip")
