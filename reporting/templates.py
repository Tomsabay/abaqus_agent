"""Report templates for Abaqus run reports."""

from __future__ import annotations

from html import escape
from urllib.parse import quote

TEMPLATE_TITLES = {
    "standard": "Abaqus Run Report",
    "client_summary": "Simulation QA Summary",
    "engineering_delivery": "Engineering Delivery Report",
}


def available_templates() -> list[str]:
    """Return supported run report template names."""
    return list(TEMPLATE_TITLES)


def render_run_report_markdown(report: dict, template: str = "standard") -> str:
    """Render a run report with a named Markdown template."""
    if template == "client_summary":
        return _render_client_summary(report)
    if template == "engineering_delivery":
        return _render_engineering_delivery(report)
    return _render_standard(report)


def render_run_report_html(report: dict, template: str = "standard") -> str:
    """Render a run report as a standalone HTML document."""
    summary = report["summary"]
    title = TEMPLATE_TITLES.get(template, TEMPLATE_TITLES["standard"])
    contract_status, contract_class = _contract_status(report)
    run_id = summary.get("run_id") or "-"
    image_artifacts = report.get("image_artifacts", [])
    artifact_count = len(report.get("artifacts", {}))
    return "\n".join([
        "<!doctype html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>{escape(title)} - {escape(str(run_id))}</title>",
        "<style>",
        _html_styles(),
        "</style>",
        "</head>",
        "<body>",
        '<main class="page">',
        '<section class="hero">',
        f"<p>Run report</p><h1>{escape(title)}</h1>",
        f"<div class=\"run-id\">{escape(str(run_id))}</div>",
        "</section>",
        '<section class="metrics">',
        _metric("Status", summary.get("status") or "-", _status_class(summary.get("status"))),
        _metric("Model", summary.get("model_name") or "-"),
        _metric("Abaqus", summary.get("abaqus_release") or "-"),
        _metric("Contracts", contract_status, contract_class),
        _metric("KPIs", str(len(report.get("kpis", {})))),
        _metric("Artifacts", str(artifact_count)),
        "</section>",
        _kpi_table_html(report),
        _contract_table_html(report),
        _visuals_html(run_id, image_artifacts, report.get("image_artifact_sources", {})),
        _artifact_table_html(report),
        '<section class="block">',
        "<h2>Markdown Source</h2>",
        f"<pre>{escape(report.get('markdown', ''))}</pre>",
        "</section>",
        "</main>",
        "</body>",
        "</html>",
    ])


def _render_standard(report: dict) -> str:
    summary = report["summary"]
    lines = [
        "# Abaqus Run Report",
        "",
        f"- Run ID: `{summary.get('run_id')}`",
        f"- Status: `{summary.get('status')}`",
        f"- Model: `{summary.get('model_name') or '-'}`",
        f"- Abaqus release: `{summary.get('abaqus_release') or '-'}`",
        "",
        "## KPIs",
        "",
        "| KPI | Value | Regression |",
        "|-----|-------|------------|",
    ]
    _append_kpi_rows(lines, report)
    _append_contract_section(lines, report)
    _append_capsule_section(lines, report)
    _append_doctor_section(lines, report)
    return "\n".join(lines)


def _render_client_summary(report: dict) -> str:
    summary = report["summary"]
    status = summary.get("status") or "-"
    contracts = report.get("contracts", {})
    contract_results = contracts.get("results", []) if isinstance(contracts, dict) else []
    contract_status = "PASS" if contracts.get("passed") else ("FAIL" if contract_results else "-")
    lines = [
        "# Simulation QA Summary",
        "",
        f"Run `{summary.get('run_id')}` finished with status `{status}`.",
        "",
        "## Executive Result",
        "",
        f"- Model: `{summary.get('model_name') or '-'}`",
        f"- Abaqus release: `{summary.get('abaqus_release') or '-'}`",
        f"- Physics contracts: `{contract_status}`",
        f"- KPI count: `{len(report.get('kpis', {}))}`",
        f"- Artifact count: `{len(report.get('artifacts', {}))}`",
        "",
        "## KPI Table",
        "",
        "| KPI | Value | Regression |",
        "|-----|-------|------------|",
    ]
    _append_kpi_rows(lines, report)
    _append_contract_section(lines, report)
    _append_doctor_section(lines, report)
    return "\n".join(lines)


def _render_engineering_delivery(report: dict) -> str:
    summary = report["summary"]
    status = summary.get("status") or "-"
    contract_status, _contract_class = _contract_status(report)
    regression_status = _regression_status(report)
    verdict = _delivery_verdict(status, contract_status, regression_status)
    lines = [
        "# Engineering Delivery Report",
        "",
        "## Acceptance Snapshot",
        "",
        f"- Delivery verdict: `{verdict}`",
        f"- Run status: `{status}`",
        f"- Physics contracts: `{contract_status}`",
        f"- KPI regression: `{regression_status}`",
        f"- Model: `{summary.get('model_name') or '-'}`",
        f"- Abaqus release: `{summary.get('abaqus_release') or '-'}`",
        "",
        "## Traceability",
        "",
        f"- Run ID: `{summary.get('run_id') or '-'}`",
        f"- Capsule path: `{summary.get('capsule_path') or '-'}`",
        f"- Result path: `{summary.get('result_path') or '-'}`",
        f"- Workdir: `{summary.get('workdir') or '-'}`",
        "",
        "## KPI Evidence",
        "",
        "| KPI | Value | Regression |",
        "|-----|-------|------------|",
    ]
    _append_kpi_rows(lines, report)
    _append_contract_section(lines, report)
    _append_artifact_section(lines, report)
    _append_doctor_section(lines, report)
    return "\n".join(lines)


def _append_kpi_rows(lines: list[str], report: dict) -> None:
    comparisons = report.get("regression", {}).get("comparisons", {})
    for name, value in sorted(report.get("kpis", {}).items()):
        comp = comparisons.get(name, {})
        status = comp.get("status", "-")
        lines.append(f"| {name} | {_format_kpi_value(value, comp)} | {status} |")


def _append_contract_section(lines: list[str], report: dict) -> None:
    contracts = report.get("contracts", {})
    contract_results = contracts.get("results", []) if isinstance(contracts, dict) else []
    if not contract_results:
        return
    lines += [
        "",
        "## Physics Contracts",
        "",
        f"Overall: `{'PASS' if contracts.get('passed') else 'FAIL'}`",
        "",
        "| Name | Check | Severity | Status | Detail |",
        "|------|-------|----------|--------|--------|",
    ]
    for item in contract_results:
        detail = str(item.get("detail", "")).replace("\n", " ")
        lines.append(
            f"| {item.get('name', '-')} | {item.get('check') or item.get('type', '-')} | "
            f"{item.get('severity', '-')} | {item.get('status', '-')} | {detail} |"
        )


def _append_capsule_section(lines: list[str], report: dict) -> None:
    summary = report["summary"]
    lines += [
        "",
        "## Capsule",
        "",
        f"- Capsule path: `{summary.get('capsule_path') or '-'}`",
        f"- Artifacts: `{len(report.get('artifacts', {}))}`",
    ]


def _append_artifact_section(lines: list[str], report: dict) -> None:
    artifacts = report.get("artifacts", {})
    lines += [
        "",
        "## Artifact Inventory",
        "",
        "| Artifact | Bytes | SHA-256 |",
        "|----------|-------|---------|",
    ]
    if not artifacts:
        lines.append("| - | - | - |")
        return
    for name, meta in sorted(artifacts.items()):
        lines.append(f"| {name} | {meta.get('bytes', '-')} | {meta.get('sha256', '-')} |")


def _append_doctor_section(lines: list[str], report: dict) -> None:
    diagnosis = report.get("diagnosis", {})
    if not diagnosis.get("matched"):
        return
    lines += ["", "## Solver Doctor", ""]
    for match in diagnosis.get("matches", []):
        lines.append(f"- `{match.get('id')}` {match.get('severity')}: {match.get('suggestion')}")


def _format_kpi_value(value, comp: dict) -> str:
    if isinstance(value, dict):
        raw_value = value.get("value", "-")
        unit = value.get("unit") or comp.get("unit") or ""
        return f"{raw_value} {unit}".strip()
    return str(value)


def _contract_status(report: dict) -> tuple[str, str]:
    contracts = report.get("contracts", {})
    results = contracts.get("results", []) if isinstance(contracts, dict) else []
    if not results:
        return "-", ""
    if contracts.get("passed"):
        return "PASS", "pass"
    return "FAIL", "fail"


def _regression_status(report: dict) -> str:
    comparisons = report.get("regression", {}).get("comparisons", {})
    statuses = {str(comp.get("status", "")).upper() for comp in comparisons.values()}
    statuses.discard("")
    if not statuses:
        return "-"
    if "FAIL" in statuses:
        return "FAIL"
    if "WARNING" in statuses:
        return "WARNING"
    if statuses <= {"PASS", "INFO"}:
        return "PASS"
    return ",".join(sorted(statuses))


def _delivery_verdict(status: str, contract_status: str, regression_status: str) -> str:
    if status != "COMPLETED":
        return "REVIEW"
    if contract_status in {"-", "FAIL"} or regression_status in {"-", "FAIL"}:
        return "REVIEW"
    return "PASS"


def _status_class(status: str | None) -> str:
    if status in {"COMPLETED", "COMPLETED (sim)", "DRY_RUN_PASS", "PASS", "INFO"}:
        return "pass"
    if status == "WARNING":
        return "warn"
    if status:
        return "fail"
    return ""


def _metric(label: str, value: str, css_class: str = "") -> str:
    class_attr = f' class="{css_class}"' if css_class else ""
    return (
        '<article class="metric">'
        f"<span>{escape(label)}</span>"
        f"<strong{class_attr}>{escape(str(value))}</strong>"
        "</article>"
    )


def _kpi_table_html(report: dict) -> str:
    comparisons = report.get("regression", {}).get("comparisons", {})
    rows = []
    for name, value in sorted(report.get("kpis", {}).items()):
        comp = comparisons.get(name, {})
        status = comp.get("status", "-")
        rows.append(
            "<tr>"
            f"<td><code>{escape(str(name))}</code></td>"
            f"<td>{escape(_format_kpi_value(value, comp))}</td>"
            f"<td class=\"{_status_class(status)}\">{escape(str(status))}</td>"
            "</tr>"
        )
    if not rows:
        rows.append('<tr><td colspan="3" class="muted">No KPI values reported.</td></tr>')
    return _table_block("KPI / Regression", ["KPI", "Value", "Regression"], rows)


def _contract_table_html(report: dict) -> str:
    contracts = report.get("contracts", {})
    results = contracts.get("results", []) if isinstance(contracts, dict) else []
    rows = []
    for item in results:
        status = item.get("status") or ("PASS" if item.get("passed") else "FAIL")
        detail = str(item.get("detail", "")).replace("\n", " ")
        rows.append(
            "<tr>"
            f"<td><code>{escape(str(item.get('name', '-')))}</code></td>"
            f"<td>{escape(str(item.get('check') or item.get('type') or '-'))}</td>"
            f"<td>{escape(str(item.get('severity', '-')))}</td>"
            f"<td class=\"{_status_class(status)}\">{escape(str(status))}</td>"
            f"<td>{escape(detail)}</td>"
            "</tr>"
        )
    if not rows:
        rows.append('<tr><td colspan="5" class="muted">No Physics Contract results reported.</td></tr>')
    return _table_block("Physics Contracts", ["Name", "Check", "Severity", "Status", "Detail"], rows)


def _artifact_table_html(report: dict) -> str:
    rows = []
    for name, meta in sorted(report.get("artifacts", {}).items()):
        rows.append(
            "<tr>"
            f"<td><code>{escape(str(name))}</code></td>"
            f"<td>{escape(str(meta.get('bytes', '-')))}</td>"
            f"<td>{escape(str(meta.get('sha256', '-')))}</td>"
            "</tr>"
        )
    if not rows:
        rows.append('<tr><td colspan="3" class="muted">No artifacts reported.</td></tr>')
    return _table_block("Artifacts", ["Artifact", "Bytes", "SHA-256"], rows)


def _visuals_html(run_id: str, image_artifacts: list[str], sources: dict[str, str] | None = None) -> str:
    if not image_artifacts:
        return '<section class="block"><h2>ODB Visuals</h2><p class="muted">No image artifacts reported.</p></section>'
    images = []
    sources = sources or {}
    for name in image_artifacts:
        src = sources.get(name) or f"/api/run/{quote(str(run_id), safe='')}/artifact/{quote(str(name))}"
        images.append(
            '<figure class="visual">'
            f'<img src="{escape(src)}" alt="{escape(str(name))}">'
            f"<figcaption>{escape(str(name))}</figcaption>"
            "</figure>"
        )
    return '<section class="block"><h2>ODB Visuals</h2><div class="visual-grid">' + "".join(images) + "</div></section>"


def _table_block(title: str, headers: list[str], rows: list[str]) -> str:
    head = "".join(f"<th>{escape(header)}</th>" for header in headers)
    return (
        '<section class="block">'
        f"<h2>{escape(title)}</h2>"
        "<table>"
        f"<thead><tr>{head}</tr></thead>"
        f"<tbody>{''.join(rows)}</tbody>"
        "</table>"
        "</section>"
    )


def _html_styles() -> str:
    return """
:root {
  color-scheme: light;
  --ink: #1f2933;
  --muted: #667085;
  --line: #d7dce3;
  --panel: #f6f8fb;
  --accent: #d85b21;
  --pass: #178a50;
  --warn: #b7791f;
  --fail: #c53030;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: #eef2f6;
  color: var(--ink);
  font-family: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  line-height: 1.55;
}
.page { max-width: 1040px; margin: 0 auto; padding: 34px 24px 56px; }
.hero {
  border-top: 5px solid var(--accent);
  background: white;
  padding: 30px;
  margin-bottom: 18px;
}
.hero p {
  margin: 0 0 6px;
  color: var(--muted);
  font-size: 12px;
  letter-spacing: .08em;
  text-transform: uppercase;
}
h1, h2 { margin: 0; line-height: 1.2; }
h1 { font-size: 34px; }
h2 { font-size: 18px; margin-bottom: 14px; }
.run-id {
  margin-top: 12px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  color: var(--muted);
}
.metrics {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 18px;
}
.metric, .block {
  background: white;
  border: 1px solid var(--line);
  border-radius: 8px;
}
.metric { padding: 16px; }
.metric span {
  display: block;
  color: var(--muted);
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: .07em;
  margin-bottom: 8px;
}
.metric strong {
  display: block;
  font-size: 20px;
  overflow-wrap: anywhere;
}
.block { padding: 22px; margin-top: 18px; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th, td { border-bottom: 1px solid var(--line); padding: 9px 8px; text-align: left; vertical-align: top; }
th {
  color: var(--muted);
  font-size: 11px;
  letter-spacing: .06em;
  text-transform: uppercase;
}
code, pre { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }
pre {
  white-space: pre-wrap;
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 6px;
  padding: 14px;
  overflow-x: auto;
}
.muted { color: var(--muted); }
.pass { color: var(--pass); }
.warn { color: var(--warn); }
.fail { color: var(--fail); }
.visual-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
  gap: 14px;
}
.visual { margin: 0; }
.visual img {
  width: 100%;
  height: auto;
  border: 1px solid var(--line);
  border-radius: 6px;
}
.visual figcaption {
  margin-top: 6px;
  color: var(--muted);
  font-size: 12px;
}
@media (max-width: 760px) {
  .page { padding: 18px 12px 32px; }
  .metrics { grid-template-columns: 1fr; }
  h1 { font-size: 26px; }
  .block { overflow-x: auto; }
}
""".strip()
