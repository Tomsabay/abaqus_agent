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
            tolerance = _tolerance_for(name, tolerances, default_rtol)
            rel_delta = None if abs(before_f) <= 1e-12 else delta / abs(before_f)
            rel_change = None if rel_delta is None else abs(rel_delta)
            limit = tolerance["atol"] + tolerance["rtol"] * max(abs(before_f), 1e-12)
            status = "PASS" if abs(delta) <= limit else "FAIL" if tolerance["strict"] else "WARNING"
            changes.append(
                {
                    "name": name,
                    "status": status,
                    "before": before,
                    "after": after,
                    "delta": delta,
                    "rel_delta": rel_delta,
                    "rel_change": rel_change,
                    "rtol": tolerance["rtol"],
                    "atol": tolerance["atol"],
                    "tolerance": {key: tolerance[key] for key in ("rtol", "atol")},
                }
            )
        except (TypeError, ValueError):
            status = "PASS" if before == after else "WARNING"
            changes.append({"name": name, "status": status, "before": before, "after": after})

    failed_count = sum(1 for c in changes if c["status"] == "FAIL")
    warning_count = sum(1 for c in changes if c["status"] == "WARNING")
    added_count = sum(1 for c in changes if c["status"] == "ADDED")
    removed_count = sum(1 for c in changes if c["status"] == "REMOVED")
    changed_count = failed_count + warning_count
    unchanged_count = sum(1 for c in changes if c["status"] == "PASS")
    passed = failed_count == 0 and warning_count == 0 and added_count == 0 and removed_count == 0
    if not changes:
        status = "INFO"
    else:
        status = "PASS" if passed else "FAIL" if failed_count or added_count or removed_count else "WARNING"
    return {
        "status": status,
        "passed": passed,
        "total": len(changes),
        "changed_count": changed_count,
        "added_count": added_count,
        "removed_count": removed_count,
        "unchanged_count": unchanged_count,
        "kpis": changes,
        "changes": changes,
    }


def render_markdown(diff: dict) -> str:
    """Render a KPI diff as Markdown."""
    if not diff.get("kpis") and not diff.get("changes"):
        return "# Simulation Diff: KPI\n\nNo KPI values supplied."

    lines = [
        "# Simulation Diff: KPI",
        "",
        "| KPI | Status | Baseline | Candidate | Delta | Rel Delta | Tolerance |",
        "|-----|--------|----------|-----------|-------|-----------|-----------|",
    ]
    for change in diff.get("kpis", diff.get("changes", [])):
        lines.append(
            f"| {change['name']} | {change['status']} | {_format_number(change.get('before'))} | "
            f"{_format_number(change.get('after'))} | {_format_number(change.get('delta'))} | "
            f"{_format_number(change.get('rel_delta'))} | {_format_tolerance(change)} |"
        )
    return "\n".join(lines)


def _raw_value(value):
    if isinstance(value, dict) and "value" in value:
        return value["value"]
    return value


def _tolerance_for(name: str, tolerances: dict, default_rtol: float) -> dict:
    raw = tolerances.get(name, default_rtol)
    if isinstance(raw, dict):
        return {
            "rtol": float(raw.get("rtol", default_rtol)),
            "atol": float(raw.get("atol", 0.0)),
            "strict": True,
        }
    return {"rtol": float(raw), "atol": 0.0, "strict": False}


def _format_number(value) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.12g}"
    return str(value)


def _format_tolerance(change: dict) -> str:
    if "rtol" not in change and "atol" not in change:
        return "-"
    return f"rtol={_format_number(change.get('rtol', 0.0))}, atol={_format_number(change.get('atol', 0.0))}"
