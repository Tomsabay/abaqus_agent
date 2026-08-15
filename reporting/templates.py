"""Report templates for Abaqus run reports."""

from __future__ import annotations

from html import escape
from urllib.parse import quote

TEMPLATE_TITLES = {
    "standard": "Abaqus Run Report",
    "client_summary": "Simulation QA Summary",
    "engineering_delivery": "Engineering Delivery Report",
}

# A run that produced no numbers has to say so on the first screen of every
# export channel, and must not carry numeric KPIs. Until 2026-08-15 this was
# the "demo mode" banner; the walkthrough it announced is gone, but a report
# for a machine without Abaqus still has to be unmistakable at a glance.
NO_SOLVE_BANNER = "未求解 · 无数值结果"
NO_SOLVE_DETAIL = "未检测到 Abaqus，无法求解；本报告不含任何数值 KPI。"

# A check that did not run is neither a pass nor a failure, and both the
# regression and the contract status can now say so explicitly: the
# orchestrator attaches a reason when it had no baseline to compare against
# or no contracts to evaluate.
NOT_GRADED = "NOT GRADED"


def _is_unsolved(report: dict) -> bool:
    """No solver ran, so there are no numbers to report.

    `status == "DEMO"` is only read here, never written: run directories
    archived before 2026-08-15 carry it, and a report built from one of them
    still has to come out honest."""
    return bool(report.get("unsolved")) or report.get("summary", {}).get("status") == "DEMO"


def _no_solve_banner_md_lines(report: dict) -> list[str]:
    if not _is_unsolved(report):
        return []
    return ["", f"> **{NO_SOLVE_BANNER}** — {NO_SOLVE_DETAIL}"]


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


def _solver_metric_value(summary: dict) -> tuple[str, str]:
    """(label, value) for the solver row.

    This branched on the backend until 2026-08-15, when the second one was
    removed: a CalculiX run had no Abaqus release, so printing the spec's
    release field on its cover would have made the archived report itself a
    false claim. No run on disk was ever produced that way, so nothing is left
    to read back.
    """
    return "Abaqus", summary.get("abaqus_release") or "-"


def render_run_report_html(report: dict, template: str = "standard") -> str:
    """Render a run report as a standalone HTML document."""
    summary = report["summary"]
    title = TEMPLATE_TITLES.get(template, TEMPLATE_TITLES["standard"])
    contract_status, contract_class = _contract_status(report)
    regression_status = _regression_status(report)
    run_id = summary.get("run_id") or "-"
    image_artifacts = report.get("image_artifacts", [])
    artifact_count = len(report.get("artifacts", {}))
    metrics = [
        _metric("Status", summary.get("status") or "-", _status_class(summary.get("status"))),
        _metric("Model", summary.get("model_name") or "-"),
        _metric(*_solver_metric_value(summary)),
        _metric("Contracts", contract_status, contract_class),
        _metric("KPIs", *_kpi_metric_value(report)),
        _metric("Artifacts", str(artifact_count)),
    ]
    if template == "engineering_delivery":
        metrics.insert(
            0,
            _metric(
                "Delivery Verdict",
                _delivery_verdict(summary.get("status") or "-", contract_status, regression_status),
                _status_class(_delivery_verdict(summary.get("status") or "-", contract_status, regression_status)),
            ),
        )
        metrics.insert(4, _metric("Regression", regression_status, _status_class(regression_status)))
    delivery_blocks = [_delivery_manifest_html(report)] if template == "engineering_delivery" else []
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
        (f'<div class="no-solve-banner">{escape(NO_SOLVE_BANNER)} — {escape(NO_SOLVE_DETAIL)}</div>'
         if _is_unsolved(report) else ""),
        f"<div class=\"run-id\">{escape(str(run_id))}</div>",
        "</section>",
        '<section class="metrics">',
        *metrics,
        "</section>",
        *delivery_blocks,
        _evidence_checklist_html(report),
        _kpi_table_html(report),
        _limitations_table_html(report),
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
        *_no_solve_banner_md_lines(report),
        "",
        f"- Run ID: `{summary.get('run_id')}`",
        f"- Status: `{summary.get('status')}`",
        f"- Model: `{summary.get('model_name') or '-'}`",
        f"- {_solver_metric_value(summary)[0]}: `{_solver_metric_value(summary)[1]}`",
        "",
        "## KPIs",
        "",
        "| KPI | Value | Regression |",
        "|-----|-------|------------|",
    ]
    _append_kpi_rows(lines, report)
    _append_contract_section(lines, report)
    _append_capsule_section(lines, report)
    _append_limitations_section(lines, report)
    _append_doctor_section(lines, report)
    return "\n".join(lines)


def _render_client_summary(report: dict) -> str:
    summary = report["summary"]
    status = summary.get("status") or "-"
    # No contracts evaluated means nothing was verified — say so. Reporting an
    # empty contract set as PASS claims a check that never ran, and every
    # workbench run currently lands in exactly that branch.
    contract_status, _ = _contract_status(report)
    lines = [
        "# Simulation QA Summary",
        *_no_solve_banner_md_lines(report),
        "",
        f"Run `{summary.get('run_id')}` finished with status `{status}`.",
        "",
        "## Executive Result",
        "",
        f"- Model: `{summary.get('model_name') or '-'}`",
        f"- {_solver_metric_value(summary)[0]}: `{_solver_metric_value(summary)[1]}`",
        f"- Physics contracts: `{contract_status}`",
        f"- KPI count: `{_kpi_metric_value(report)[0]}`",
        f"- Artifact count: `{len(report.get('artifacts', {}))}`",
        "",
        "## KPI Table",
        "",
        "| KPI | Value | Regression |",
        "|-----|-------|------------|",
    ]
    _append_kpi_rows(lines, report)
    _append_contract_section(lines, report)
    _append_limitations_section(lines, report)
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
        *_no_solve_banner_md_lines(report),
        "",
        "## Acceptance Snapshot",
        "",
        f"- Delivery verdict: `{verdict}`",
        f"- Run status: `{status}`",
        f"- Physics contracts: `{contract_status}`",
        f"- KPI regression: `{regression_status}`",
        f"- Model: `{summary.get('model_name') or '-'}`",
        f"- {_solver_metric_value(summary)[0]}: `{_solver_metric_value(summary)[1]}`",
        "",
        "## Traceability",
        "",
        f"- Run ID: `{summary.get('run_id') or '-'}`",
        f"- Capsule path: `{summary.get('capsule_path') or '-'}`",
        f"- Result path: `{summary.get('result_path') or '-'}`",
        f"- Workdir: `{summary.get('workdir') or '-'}`",
        "",
        "## Delivery Manifest",
        "",
        "| Item | Status | Detail |",
        "|------|--------|--------|",
    ]
    _append_delivery_manifest_rows(lines, report)
    lines += [
        "",
        "## Evidence Checklist",
        "",
        "| Evidence | Status | Detail |",
        "|----------|--------|--------|",
    ]
    _append_evidence_rows(lines, report)
    lines += [
        "",
        "## KPI Evidence",
        "",
        "| KPI | Value | Regression |",
        "|-----|-------|------------|",
    ]
    _append_kpi_rows(lines, report)
    _append_contract_section(lines, report)
    _append_artifact_section(lines, report)
    _append_limitations_section(lines, report)
    _append_doctor_section(lines, report)
    return "\n".join(lines)


def _append_kpi_rows(lines: list[str], report: dict) -> None:
    comparisons = report.get("regression", {}).get("comparisons", {})
    kpis = report.get("kpis", {})
    if not kpis and _is_unsolved(report):
        lines.append(f"| （{NO_SOLVE_BANNER} — 未生成 KPI） | - | - |")
        return
    for name, value in sorted(kpis.items()):
        comp = comparisons.get(name, {})
        status = comp.get("status", "-")
        lines.append(f"| {name} | {_format_kpi_value(value, comp)} | {status} |")
    # In the SAME table as the values, not a footnote below it. A KPI that was
    # asked for and never came back is a fact about this table's completeness,
    # and a reader who scans only the table is the reader who needs it.
    for entry in report.get("kpis_missing", []):
        reason = " ".join(_missing_kpi_reason(entry).split()).replace("|", "/")
        lines.append(
            f"| {_missing_kpi_name(entry)} | "
            f"{reason or 'requested by the spec, never returned'} | NOT EXTRACTED |")


def _append_contract_section(lines: list[str], report: dict) -> None:
    contracts = report.get("contracts", {})
    contract_results = contracts.get("results", []) if isinstance(contracts, dict) else []
    if not contract_results:
        # Silence here made a run with zero contracts look identical to one
        # whose contracts all held: the section simply was not printed.
        reason = contracts.get("not_checked_reason") if isinstance(contracts, dict) else ""
        if reason:
            lines += ["", "## Physics Contracts", "",
                      f"Overall: `{NOT_GRADED}` — {reason}"]
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


def _append_evidence_rows(lines: list[str], report: dict) -> None:
    for item in _evidence_items(report):
        lines.append(
            f"| {_markdown_cell(item['label'])} | {_markdown_cell(item['status'])} | "
            f"{_markdown_cell(item['detail'])} |"
        )


def _append_delivery_manifest_rows(lines: list[str], report: dict) -> None:
    for item in _delivery_manifest_items(report):
        lines.append(
            f"| {_markdown_cell(item['label'])} | {_markdown_cell(item['status'])} | "
            f"{_markdown_cell(item['detail'])} |"
        )


def _limitation_rows(report: dict) -> list[tuple]:
    """(what, value, why) per limitation, whichever shape it arrived in.

    Two shapes have always coexisted in `result["limitations"]`: the backend
    layer writes `{feature, value, reason}` records and
    `runner/dat_warnings.limitation_lines()` writes plain sentences. Both are
    real; a reader that handles one silently drops the other, which is exactly
    how the .dat integrity findings spent months rendering as blank cards in
    the workbench.
    """
    rows = []
    for entry in report.get("limitations", []) or []:
        if isinstance(entry, str):
            rows.append(("-", "-", entry))
        elif isinstance(entry, dict):
            rows.append((str(entry.get("feature", "") or "-"),
                         str(entry.get("value", "") or "-"),
                         str(entry.get("reason", "") or "-")))
    return rows


def _append_limitations_section(lines: list[str], report: dict) -> None:
    """What this run cannot be trusted about, in the archived report.

    Until #72 this existed only on the live page. An archived report is what
    gets sent to somebody who was not there — a hourglass-prone element, a tie
    that silently dropped 85 nodes, a KPI that never came back — and it carried
    none of it. The run's verdict is unchanged by anything here (#73(b), #72):
    these are caveats on numbers that were produced, not a claim they are
    wrong.
    """
    rows = _limitation_rows(report)
    if not rows:
        return
    lines += ["", "## Known Limitations", "",
              "| Where | Value | Why it matters |",
              "|-------|-------|----------------|"]
    for what, value, why in rows:
        clean = " ".join(str(why).split()).replace("|", "/")
        lines.append(f"| {what} | {value} | {clean} |")


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
        if isinstance(contracts, dict) and contracts.get("not_checked_reason"):
            return NOT_GRADED, "warn"
        return "-", ""
    if contracts.get("passed"):
        return "PASS", "pass"
    return "FAIL", "fail"


def _regression_status(report: dict) -> str:
    regression = report.get("regression", {})
    if not isinstance(regression, dict):
        return "-"
    # The verdict written on top of the comparisons outranks the comparisons.
    # A run blocked by dat-integrity keeps every comparison at PASS on purpose
    # -- equilibrium holds however the load gets carried -- and only
    # `passed` is set to False. Deriving the status from the comparisons alone
    # printed `Regression: PASS` for a model that was provably not the one the
    # spec described, re-asserting the exact claim
    # _block_regression_on_integrity exists to withdraw.
    if regression.get("passed") is False:
        return "FAIL"
    comparisons = regression.get("comparisons", {})
    statuses = {str(comp.get("status", "")).upper() for comp in comparisons.values()}
    statuses.discard("")
    if not statuses:
        return NOT_GRADED if regression.get("not_compared_reason") else "-"
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
    if (contract_status in {"-", "FAIL", NOT_GRADED}
            or regression_status in {"-", "FAIL", NOT_GRADED}):
        return "REVIEW"
    return "PASS"


def _evidence_items(report: dict) -> list[dict[str, str]]:
    summary = report["summary"]
    contract_status, _contract_class = _contract_status(report)
    regression_status = _regression_status(report)
    artifacts = report.get("artifacts", {})
    kpis = report.get("kpis", {})
    diagnosis = report.get("diagnosis", {})
    matches = diagnosis.get("matches", []) if isinstance(diagnosis, dict) else []
    capsule_path = summary.get("capsule_path") or ""
    result_path = summary.get("result_path") or ""
    items = [
        {
            "label": "Run capsule",
            "status": "PASS" if capsule_path or report.get("capsule") else "REVIEW",
            "detail": capsule_path or "No capsule path recorded",
        },
        {
            "label": "Result JSON",
            "status": "PASS" if result_path or kpis or report.get("regression") else "REVIEW",
            "detail": result_path or "Result evidence inferred from loaded report fields",
        },
        {
            "label": "KPI extraction",
            "status": "PASS" if kpis else "REVIEW",
            "detail": f"{len(kpis)} KPI values recorded",
        },
        {
            "label": "KPI regression",
            "status": regression_status if regression_status != "-" else "REVIEW",
            "detail": _regression_detail(report),
        },
        {
            "label": "Physics contracts",
            "status": contract_status if contract_status != "-" else "REVIEW",
            "detail": _contract_detail(report),
        },
        {
            "label": "Artifact inventory",
            "status": "PASS" if artifacts else "REVIEW",
            "detail": f"{len(artifacts)} artifacts recorded",
        },
    ]
    if matches:
        severities = ", ".join(sorted({str(match.get("severity", "-")) for match in matches}))
        items.append({
            "label": "Solver Doctor",
            "status": "WARNING",
            "detail": f"{len(matches)} diagnostic matches: {severities}",
        })
    else:
        items.append({
            "label": "Solver Doctor",
            "status": "INFO",
            "detail": "No diagnostic matches reported",
        })
    return items


def _delivery_manifest_items(report: dict) -> list[dict[str, str]]:
    summary = report["summary"]
    artifacts = report.get("artifacts", {})
    image_artifacts = report.get("image_artifacts", [])
    total_bytes = sum(_artifact_bytes(meta) for meta in artifacts.values())
    bundle_parts = ["report.md", "report.html", "artifact_manifest.json"]
    if report.get("capsule"):
        bundle_parts.append("capsule.json")
    if summary.get("result_path") or report.get("kpis") or report.get("regression"):
        bundle_parts.append("result.json")
    return [
        {
            "label": "Run identity",
            "status": "PASS" if summary.get("run_id") else "REVIEW",
            "detail": f"run_id={summary.get('run_id') or '-'}, model={summary.get('model_name') or '-'}",
        },
        {
            "label": "Bundle contents",
            "status": "PASS" if report.get("capsule") or artifacts else "REVIEW",
            "detail": ", ".join(bundle_parts),
        },
        {
            "label": "Artifact payload",
            "status": "PASS" if artifacts else "REVIEW",
            "detail": f"{len(artifacts)} artifacts, {_format_bytes(total_bytes)} recorded",
        },
        {
            "label": "Visual evidence",
            "status": "PASS" if image_artifacts else "INFO",
            "detail": f"{len(image_artifacts)} image artifacts",
        },
    ]


def _regression_detail(report: dict) -> str:
    regression = report.get("regression", {})
    if not isinstance(regression, dict):
        regression = {}
    comparisons = regression.get("comparisons", {})
    if not comparisons:
        # The orchestrator says WHY it compared nothing; "none reported" reads
        # like a reporting gap when it is a missing baseline.
        return regression.get("not_compared_reason") or "No KPI regression comparisons reported"
    counts: dict[str, int] = {}
    for comp in comparisons.values():
        status = str(comp.get("status") or "-").upper()
        counts[status] = counts.get(status, 0) + 1
    return ", ".join(f"{status}: {count}" for status, count in sorted(counts.items()))


def _contract_detail(report: dict) -> str:
    contracts = report.get("contracts", {})
    results = contracts.get("results", []) if isinstance(contracts, dict) else []
    if not results:
        if isinstance(contracts, dict) and contracts.get("not_checked_reason"):
            return contracts["not_checked_reason"]
        return "No Physics Contract results reported"
    passed = sum(1 for item in results if item.get("status") == "PASS" or item.get("passed") is True)
    failed = len(results) - passed
    return f"{passed} passed, {failed} failed"


def _status_class(status: str | None) -> str:
    if status in {"COMPLETED", "COMPLETED (sim)", "DRY_RUN_PASS", "PASS", "INFO"}:
        return "pass"
    if status in {"WARNING", "REVIEW", "DEMO", NOT_GRADED}:
        return "warn"
    if status:
        return "fail"
    return ""


def _kpi_metric_value(report: dict) -> tuple[str, str]:
    """(value, css_class) for the KPI count.

    It used to print `len(report["kpis"])` — the count of what was DELIVERED,
    with nothing to compare it against. Two of three requested KPIs read
    exactly like two of two, so a run that dropped one looked complete on its
    own cover page. `kpis_missing` gives the denominator back.

    #73(b): this changes what the cover SHOWS, not what the run is graded as.
    A shortfall is a warn, never a fail — that was decided deliberately,
    because failing the run would re-grade every frozen baseline.
    """
    delivered = len(report.get("kpis", {}))
    missing = len(report.get("kpis_missing", []))
    if not missing:
        return str(delivered), ""
    return "%d of %d" % (delivered, delivered + missing), "warn"


def _missing_kpi_name(entry) -> str:
    """A `kpis_missing` entry is a dict; tolerate a bare name from older runs."""
    if isinstance(entry, str):
        return entry
    return str((entry or {}).get("name", "")) or "-"


def _missing_kpi_reason(entry) -> str:
    if isinstance(entry, str):
        return ""
    return str((entry or {}).get("reason", "") or "")


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
    for entry in report.get("kpis_missing", []):
        reason = _missing_kpi_reason(entry)
        rows.append(
            "<tr>"
            f"<td><code>{escape(_missing_kpi_name(entry))}</code></td>"
            f"<td class=\"muted\">{escape(reason or 'requested by the spec, never returned')}</td>"
            "<td class=\"fail\">NOT EXTRACTED</td>"
            "</tr>"
        )
    if not rows:
        empty_text = (
            f"{NO_SOLVE_BANNER} — 未检测到 Abaqus，无法求解，未生成 KPI。"
            if _is_unsolved(report) else "No KPI values reported."
        )
        rows.append(f'<tr><td colspan="3" class="muted">{escape(empty_text)}</td></tr>')
    return _table_block("KPI / Regression", ["KPI", "Value", "Regression"], rows)


def _limitations_table_html(report: dict) -> str:
    rows = _limitation_rows(report)
    if not rows:
        return ""
    body = [
        "<tr>"
        f"<td><code>{escape(what)}</code></td>"
        f"<td>{escape(value)}</td>"
        f"<td class=\"warn\">{escape(why)}</td>"
        "</tr>"
        for what, value, why in rows
    ]
    return _table_block("Known Limitations", ["Where", "Value", "Why it matters"],
                        body)


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


def _delivery_manifest_html(report: dict) -> str:
    rows = []
    for item in _delivery_manifest_items(report):
        status = item["status"]
        rows.append(
            "<tr>"
            f"<td>{escape(item['label'])}</td>"
            f"<td class=\"{_status_class(status)}\">{escape(status)}</td>"
            f"<td>{escape(item['detail'])}</td>"
            "</tr>"
        )
    return _table_block("Delivery Manifest", ["Item", "Status", "Detail"], rows)


def _evidence_checklist_html(report: dict) -> str:
    rows = []
    for item in _evidence_items(report):
        status = item["status"]
        rows.append(
            "<tr>"
            f"<td>{escape(item['label'])}</td>"
            f"<td class=\"{_status_class(status)}\">{escape(status)}</td>"
            f"<td>{escape(item['detail'])}</td>"
            "</tr>"
        )
    return _table_block("Evidence Checklist", ["Evidence", "Status", "Detail"], rows)


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


def _artifact_bytes(meta) -> int:
    if not isinstance(meta, dict):
        return 0
    try:
        return int(meta.get("bytes") or 0)
    except (TypeError, ValueError):
        return 0


def _format_bytes(num_bytes: int) -> str:
    units = ["B", "KB", "MB", "GB"]
    value = float(num_bytes)
    unit = units[0]
    for unit in units:
        if value < 1024 or unit == units[-1]:
            break
        value /= 1024
    if unit == "B":
        return f"{int(value)} {unit}"
    return f"{value:.1f} {unit}"


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
.no-solve-banner {
  margin-top: 14px;
  padding: 10px 14px;
  border: 1px solid var(--warn);
  border-left: 5px solid var(--warn);
  background: #fdf6ec;
  color: var(--warn);
  font-weight: 600;
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


def _markdown_cell(value: str) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")
