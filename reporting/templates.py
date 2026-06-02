"""Markdown report templates for Abaqus run reports."""

from __future__ import annotations


def available_templates() -> list[str]:
    """Return supported run report template names."""
    return ["standard", "client_summary"]


def render_run_report_markdown(report: dict, template: str = "standard") -> str:
    """Render a run report with a named Markdown template."""
    if template == "client_summary":
        return _render_client_summary(report)
    return _render_standard(report)


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
