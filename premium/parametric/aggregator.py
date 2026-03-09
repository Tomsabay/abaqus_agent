"""
aggregator.py
-------------
Result aggregation and sensitivity analysis for parametric sweeps.

Provides functions to analyze how parameters influence KPIs,
generate sensitivity rankings, and create summary reports.
"""

from __future__ import annotations

import math
from pathlib import Path


def compute_sensitivity(sweep_results: dict) -> dict:
    """
    Compute parameter sensitivity for each KPI.

    Uses a simple one-at-a-time variance-based approach:
    For each parameter, measure how much each KPI changes
    relative to its total variation.

    Returns
    -------
    dict mapping KPI name -> list of {parameter, sensitivity, direction}
    """
    results = sweep_results.get("results", [])
    parameters = sweep_results.get("parameters", [])
    completed = [r for r in results if r and r.get("status") == "COMPLETED"]

    if len(completed) < 2:
        return {}

    # Collect all KPI names
    kpi_names = set()
    for r in completed:
        kpi_names.update(r.get("kpis", {}).keys())

    sensitivity = {}
    for kpi_name in kpi_names:
        param_effects = []
        for param in parameters:
            path = param["path"]
            effect = _compute_parameter_effect(completed, path, kpi_name)
            if effect is not None:
                param_effects.append({
                    "parameter": path,
                    "sensitivity": round(effect["sensitivity"], 4),
                    "direction": effect["direction"],
                    "correlation": round(effect["correlation"], 4),
                })

        # Sort by sensitivity (descending)
        param_effects.sort(key=lambda x: abs(x["sensitivity"]), reverse=True)
        sensitivity[kpi_name] = param_effects

    return sensitivity


def _compute_parameter_effect(
    results: list[dict], param_path: str, kpi_name: str
) -> dict | None:
    """Compute effect of a single parameter on a single KPI."""
    pairs = []
    for r in results:
        sample = r.get("sample", {})
        kpis = r.get("kpis", {})

        param_val = sample.get(param_path)
        kpi_data = kpis.get(kpi_name)
        if param_val is None or kpi_data is None:
            continue

        kpi_val = kpi_data.get("value", kpi_data) if isinstance(kpi_data, dict) else kpi_data
        if isinstance(param_val, (int, float)) and isinstance(kpi_val, (int, float)):
            pairs.append((param_val, kpi_val))

    if len(pairs) < 2:
        return None

    param_vals = [p[0] for p in pairs]
    kpi_vals = [p[1] for p in pairs]

    # Compute correlation coefficient
    corr = _pearson_correlation(param_vals, kpi_vals)

    # Compute sensitivity as normalized range ratio
    param_range = max(param_vals) - min(param_vals)
    kpi_range = max(kpi_vals) - min(kpi_vals)

    if param_range == 0:
        return None

    # Normalized sensitivity: how much KPI changes per unit parameter change
    param_mean = sum(param_vals) / len(param_vals)
    kpi_mean = sum(kpi_vals) / len(kpi_vals)

    sensitivity = (kpi_range / max(abs(kpi_mean), 1e-10)) / (param_range / max(abs(param_mean), 1e-10))

    return {
        "sensitivity": sensitivity,
        "direction": "positive" if corr > 0 else "negative",
        "correlation": corr,
    }


def _pearson_correlation(x: list[float], y: list[float]) -> float:
    """Compute Pearson correlation coefficient."""
    n = len(x)
    if n < 2:
        return 0.0

    x_mean = sum(x) / n
    y_mean = sum(y) / n

    cov = sum((xi - x_mean) * (yi - y_mean) for xi, yi in zip(x, y))
    std_x = math.sqrt(sum((xi - x_mean) ** 2 for xi in x))
    std_y = math.sqrt(sum((yi - y_mean) ** 2 for yi in y))

    if std_x == 0 or std_y == 0:
        return 0.0

    return cov / (std_x * std_y)


def generate_sensitivity_report(sweep_results: dict) -> str:
    """Generate a Markdown sensitivity analysis report."""
    sensitivity = compute_sensitivity(sweep_results)
    summary = sweep_results.get("summary", {})

    lines = [
        "# Parametric Sweep - Sensitivity Analysis Report",
        "",
        f"**Strategy**: {sweep_results.get('strategy', 'N/A')}",
        f"**Total variants**: {summary.get('total', 0)}",
        f"**Completed**: {summary.get('completed', 0)}",
        f"**Completion rate**: {summary.get('completion_rate', 0):.1%}",
        "",
    ]

    # Parameters
    lines.append("## Parameters")
    lines.append("")
    lines.append("| Parameter | Min | Max | Steps |")
    lines.append("|-----------|-----|-----|-------|")
    for p in sweep_results.get("parameters", []):
        vals = p.get("values", [])
        v_min = p.get("min", min(vals) if vals else "N/A")
        v_max = p.get("max", max(vals) if vals else "N/A")
        steps = len(vals) if vals else p.get("steps", "N/A")
        lines.append(f"| `{p['path']}` | {v_min} | {v_max} | {steps} |")
    lines.append("")

    # KPI Statistics
    kpi_stats = summary.get("kpi_statistics", {})
    if kpi_stats:
        lines.append("## KPI Statistics")
        lines.append("")
        lines.append("| KPI | Min | Max | Mean | Range |")
        lines.append("|-----|-----|-----|------|-------|")
        for name, stats in kpi_stats.items():
            lines.append(
                f"| {name} | {stats['min']:.4g} | {stats['max']:.4g} | "
                f"{stats['mean']:.4g} | {stats['range']:.4g} |"
            )
        lines.append("")

    # Sensitivity Rankings
    if sensitivity:
        lines.append("## Parameter Sensitivity Rankings")
        lines.append("")
        for kpi_name, effects in sensitivity.items():
            lines.append(f"### {kpi_name}")
            lines.append("")
            if effects:
                lines.append("| Rank | Parameter | Sensitivity | Direction | Correlation |")
                lines.append("|------|-----------|-------------|-----------|-------------|")
                for i, e in enumerate(effects, 1):
                    lines.append(
                        f"| {i} | `{e['parameter']}` | {e['sensitivity']:.4f} | "
                        f"{e['direction']} | {e['correlation']:.4f} |"
                    )
            else:
                lines.append("*No significant parameter effects detected.*")
            lines.append("")

    return "\n".join(lines)


def save_report(sweep_results: dict, workdir: str | Path) -> Path:
    """Save sensitivity report to file."""
    workdir = Path(workdir)
    report = generate_sensitivity_report(sweep_results)
    report_path = workdir / "parametric_sweep" / "sensitivity_report.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8")
    return report_path
