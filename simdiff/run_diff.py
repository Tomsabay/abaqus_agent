"""Run/capsule-level simulation diff helpers."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from .kpi_diff import diff_kpis


def load_run_payload(path: str | Path) -> dict:
    """Load a simulation payload from a run dir, capsule dir, result JSON, capsule JSON, or KPI JSON."""
    source = Path(path)
    if source.is_dir():
        result_path = source / "result.json"
        capsule_path = source / "capsule.json"
        spec_path = source / "spec.yaml"
    else:
        result_path = source if source.name == "result.json" else None
        capsule_path = source if source.name == "capsule.json" else None
        spec_path = source.with_name("spec.yaml") if source.name in {"result.json", "capsule.json"} else None

    result = _read_json(result_path) if result_path and result_path.exists() else {}
    capsule = _read_json(capsule_path) if capsule_path and capsule_path.exists() else {}
    if not result and not capsule:
        raw = _read_json(source)
        if "kpis" in raw or "contracts" in raw or "stages" in raw:
            result = raw
        else:
            result = {"kpis": raw}

    spec = _read_spec(source, spec_path, result, capsule)
    return {
        "source": str(source),
        "run_id": result.get("run_id") or capsule.get("run_id") or source.stem,
        "status": result.get("status") or capsule.get("provenance", {}).get("status"),
        "kpis": result.get("kpis", {}),
        "contracts": result.get("contracts") or capsule.get("contracts", {}),
        "regression": result.get("regression", {}),
        "spec": spec,
        "inputs": capsule.get("inputs", {}),
        "provenance": capsule.get("provenance", {}),
        "artifacts": capsule.get("artifacts", {}),
    }


def diff_runs(
    baseline: str | Path | dict,
    candidate: str | Path | dict,
    default_rtol: float = 0.05,
) -> dict:
    """Compare two run/capsule payloads."""
    base = load_run_payload(baseline) if not isinstance(baseline, dict) else baseline
    cand = load_run_payload(candidate) if not isinstance(candidate, dict) else candidate
    kpi_diff = diff_kpis(base.get("kpis", {}), cand.get("kpis", {}), default_rtol=default_rtol)
    contract_diff = _diff_contracts(base.get("contracts", {}), cand.get("contracts", {}))
    input_diff = _diff_mapping("input", base.get("inputs", {}), cand.get("inputs", {}))
    spec_diff = _diff_spec(base.get("spec", {}), cand.get("spec", {}))
    artifact_diff = _diff_artifacts(base.get("artifacts", {}), cand.get("artifacts", {}))
    provenance_diff = _diff_mapping("provenance", base.get("provenance", {}), cand.get("provenance", {}))

    sections = {
        "kpis": kpi_diff,
        "contracts": contract_diff,
        "inputs": input_diff,
        "spec": spec_diff,
        "artifacts": artifact_diff,
        "provenance": provenance_diff,
    }
    summary = _diff_summary(sections)
    return {
        "passed": _diff_passed(sections),
        "baseline": _identity(base),
        "candidate": _identity(cand),
        "summary": summary,
        "sections": sections,
        "changes": kpi_diff.get("changes", []),
    }


def render_run_markdown(diff: dict) -> str:
    """Render a run/capsule diff as Markdown."""
    lines = [
        "# Simulation Diff Report",
        "",
        f"- Baseline: `{diff.get('baseline', {}).get('run_id', '-')}`",
        f"- Candidate: `{diff.get('candidate', {}).get('run_id', '-')}`",
        f"- Overall: `{'PASS' if diff.get('passed') else 'WARNING'}`",
        "",
        "## Change Summary",
        "",
        "| Section | Total | PASS | WARNING | ADDED | REMOVED |",
        "|---------|-------|------|---------|-------|---------|",
    ]
    for section, counts in diff.get("summary", {}).get("sections", {}).items():
        lines.append(
            f"| {section} | {counts.get('total', 0)} | {counts.get('PASS', 0)} | "
            f"{counts.get('WARNING', 0)} | {counts.get('ADDED', 0)} | {counts.get('REMOVED', 0)} |"
        )
    lines += [
        "",
        "## KPI Diff",
        "",
        "| KPI | Before | After | Delta | Rel Change | Status |",
        "|-----|--------|-------|-------|------------|--------|",
    ]
    for change in diff.get("sections", {}).get("kpis", {}).get("changes", []):
        rel = change.get("rel_change")
        rel_s = f"{rel * 100:.2f}%" if rel is not None else "-"
        lines.append(
            f"| {change['name']} | {_fmt(change.get('before'))} | {_fmt(change.get('after'))} | "
            f"{_fmt(change.get('delta', '-'))} | {rel_s} | {change['status']} |"
        )

    lines += [
        "",
        "## Physics Contract Diff",
        "",
        "| Contract | Before | After | Status |",
        "|----------|--------|-------|--------|",
    ]
    contract_changes = diff.get("sections", {}).get("contracts", {}).get("changes", [])
    if contract_changes:
        for change in contract_changes:
            lines.append(
                f"| {change['name']} | {change.get('before', '-')} | "
                f"{change.get('after', '-')} | {change['status']} |"
            )
    else:
        lines.append("| - | - | - | PASS |")

    for section_name, title in [
        ("spec", "Spec Diff"),
        ("inputs", "Capsule Input Diff"),
        ("artifacts", "Artifact Diff"),
        ("provenance", "Provenance Diff"),
    ]:
        changes = diff.get("sections", {}).get(section_name, {}).get("changes", [])
        if not changes:
            continue
        lines += ["", f"## {title}", "", "| Field | Before | After | Status |", "|-------|--------|-------|--------|"]
        for change in changes:
            lines.append(
                f"| {change['path']} | {_fmt(change.get('before'))} | "
                f"{_fmt(change.get('after'))} | {change['status']} |"
            )
    return "\n".join(lines)


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _read_spec(source: Path, fallback_path: Path | None, result: dict, capsule: dict) -> dict:
    candidates = []
    base_dir = source if source.is_dir() else source.parent
    if fallback_path:
        candidates.append(fallback_path)
    for raw_path in (
        result.get("spec_path"),
        capsule.get("inputs", {}).get("spec_path"),
        capsule.get("inputs", {}).get("spec"),
    ):
        if isinstance(raw_path, str) and raw_path:
            path = Path(raw_path)
            candidates.append(path if path.is_absolute() else base_dir / path)

    for path in candidates:
        if path.exists():
            return _read_yaml(path)
    return {}


def _identity(payload: dict) -> dict:
    return {
        "run_id": payload.get("run_id"),
        "status": payload.get("status"),
        "source": payload.get("source"),
    }


def _diff_passed(sections: dict) -> bool:
    statuses = []
    for section in sections.values():
        statuses.extend(change.get("status") for change in section.get("changes", []))
    return all(status in ("PASS", "INFO", None) for status in statuses)


def _diff_summary(sections: dict) -> dict:
    section_counts = {}
    total_changes = 0
    warning_changes = 0
    structural_changes = 0
    for name, section in sections.items():
        counts = {"total": 0, "PASS": 0, "WARNING": 0, "ADDED": 0, "REMOVED": 0, "INFO": 0, "OTHER": 0}
        for change in section.get("changes", []):
            status = str(change.get("status") or "INFO").upper()
            bucket = status if status in counts else "OTHER"
            counts[bucket] += 1
            counts["total"] += 1
        total_changes += counts["total"]
        warning_changes += counts["WARNING"] + counts["OTHER"]
        structural_changes += counts["ADDED"] + counts["REMOVED"]
        section_counts[name] = counts
    return {
        "total_changes": total_changes,
        "warning_changes": warning_changes,
        "structural_changes": structural_changes,
        "sections": section_counts,
    }


def _diff_contracts(baseline: dict, candidate: dict) -> dict:
    base = {item.get("name"): item for item in baseline.get("results", []) if item.get("name")}
    cand = {item.get("name"): item for item in candidate.get("results", []) if item.get("name")}
    changes = []
    for name in sorted(set(base) | set(cand)):
        if name not in base:
            changes.append({"name": name, "before": None, "after": cand[name].get("status"), "status": "ADDED"})
        elif name not in cand:
            changes.append({"name": name, "before": base[name].get("status"), "after": None, "status": "REMOVED"})
        else:
            before = base[name].get("status")
            after = cand[name].get("status")
            status = "PASS" if before == after else "WARNING"
            changes.append({"name": name, "before": before, "after": after, "status": status})
    return {"passed": all(c["status"] == "PASS" for c in changes), "changes": changes}


def _diff_artifacts(baseline: dict, candidate: dict) -> dict:
    base = {name: meta.get("sha256") for name, meta in baseline.items()}
    cand = {name: meta.get("sha256") for name, meta in candidate.items()}
    return _diff_mapping("artifact", base, cand)


def _diff_spec(baseline: dict, candidate: dict) -> dict:
    return _diff_mapping("spec", _flatten(baseline), _flatten(candidate))


def _diff_mapping(_kind: str, baseline: dict, candidate: dict) -> dict:
    changes = []
    for path in sorted(set(baseline) | set(candidate)):
        if path not in baseline:
            changes.append({"path": path, "before": None, "after": candidate[path], "status": "ADDED"})
        elif path not in candidate:
            changes.append({"path": path, "before": baseline[path], "after": None, "status": "REMOVED"})
        elif baseline[path] != candidate[path]:
            changes.append({"path": path, "before": baseline[path], "after": candidate[path], "status": "WARNING"})
    return {"passed": not changes, "changes": changes}


def _flatten(value, prefix: str = "") -> dict:
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            child_prefix = f"{prefix}.{key}" if prefix else str(key)
            result.update(_flatten(item, child_prefix))
        return result
    if isinstance(value, list):
        return {prefix: json.dumps(value, sort_keys=True, ensure_ascii=False)}
    return {prefix: value}


def _fmt(value) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.6g}"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value).replace("\n", " ")
