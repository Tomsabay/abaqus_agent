"""Human-readable KPI diff for two simulation runs or capsules."""

from __future__ import annotations


def diff_kpis(
    baseline: dict,
    candidate: dict,
    tolerances: dict | None = None,
    default_rtol: float = 0.05,
) -> dict:
    """Compare KPI dictionaries and classify each change."""
    tolerances = tolerances or {}
    names = sorted(set(baseline) | set(candidate))
    changes = []
    for name in names:
        if name not in baseline:
            changes.append({"name": name, "status": "ADDED", "before": None, "after": candidate[name]})
            continue
        if name not in candidate:
            changes.append({"name": name, "status": "REMOVED", "before": baseline[name], "after": None})
            continue

        before = _raw_value(baseline[name])
        after = _raw_value(candidate[name])
        try:
            before_f = float(before)
            after_f = float(after)
            delta = after_f - before_f
            rel = abs(delta) / max(abs(before_f), 1e-12)
            rtol = float(tolerances.get(name, default_rtol))
            status = "PASS" if rel <= rtol else "WARNING"
            changes.append({
                "name": name,
                "status": status,
                "before": before,
                "after": after,
                "delta": delta,
                "rel_change": rel,
                "rtol": rtol,
            })
        except (TypeError, ValueError):
            status = "PASS" if before == after else "WARNING"
            changes.append({"name": name, "status": status, "before": before, "after": after})

    return {
        "passed": all(c["status"] in ("PASS",) for c in changes),
        "changes": changes,
    }


def render_markdown(diff: dict) -> str:
    """Render a KPI diff as Markdown."""
    lines = [
        "# Simulation KPI Diff",
        "",
        "| KPI | Before | After | Delta | Rel Change | rtol | Status |",
        "|-----|--------|-------|-------|------------|------|--------|",
    ]
    for change in diff.get("changes", []):
        delta = change.get("delta", "-")
        rel = change.get("rel_change")
        rel_s = f"{rel * 100:.2f}%" if rel is not None else "-"
        rtol = change.get("rtol")
        rtol_s = f"{rtol * 100:.2f}%" if rtol is not None else "-"
        lines.append(
            f"| {change['name']} | {change.get('before')} | {change.get('after')} | "
            f"{delta} | {rel_s} | {rtol_s} | {change['status']} |"
        )
    return "\n".join(lines)


def _raw_value(value):
    if isinstance(value, dict) and "value" in value:
        return value["value"]
    return value
