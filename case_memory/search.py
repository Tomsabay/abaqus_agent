"""Deterministic local search over Abaqus run capsules.

Case Memory intentionally starts as a file-system index instead of a vector DB.
The first useful behavior is finding prior audited runs by status, KPIs,
contracts, diagnosis patterns, inputs, and simple similarity signals.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class CaseMemoryQuery:
    """Filters and ranking options for local case memory search."""

    roots: tuple[str | Path, ...]
    query: str = ""
    similar_to: str | Path | None = None
    status: str = ""
    model_name: str = ""
    contract: str = ""
    contracts_passed: str = ""
    diagnosis_id: str = ""
    kpi: str = ""
    artifact: str = ""
    limit: int = 10
    include_artifacts: bool = False
    sort_by: str = "score"
    sort_order: str = "desc"
    min_score: float = 0.0


def search_case_memory(query: CaseMemoryQuery | dict) -> dict:
    """Search run/capsule roots and return ranked, explainable matches."""
    q = _normalize_query(query)
    target = _load_target(q.similar_to) if q.similar_to else None
    entries = [_index_case(path) for path in _discover_capsules(q.roots)]
    scored = []

    for entry in entries:
        if target and entry.get("capsule_path") == target.get("capsule_path"):
            continue
        if not _passes_filters(entry, q):
            continue
        if q.query and not _query_matches(entry, q.query):
            continue
        score, reasons = _score_entry(entry, q, target)
        if score <= 0 and (q.query or target):
            continue
        if score < q.min_score:
            continue
        ranked = _public_entry(entry, include_artifacts=q.include_artifacts)
        ranked.update({"score": round(score, 3), "reasons": reasons})
        scored.append(ranked)

    _sort_matches(scored, q.sort_by, q.sort_order)
    limit = max(1, q.limit)
    return {
        "total_indexed": len(entries),
        "total_matches": len(scored),
        "query": {
            "roots": [str(root) for root in q.roots],
            "query": q.query,
            "similar_to": str(q.similar_to) if q.similar_to else "",
            "status": q.status,
            "model_name": q.model_name,
            "contract": q.contract,
            "contracts_passed": q.contracts_passed,
            "diagnosis_id": q.diagnosis_id,
            "kpi": q.kpi,
            "artifact": q.artifact,
            "limit": limit,
            "include_artifacts": q.include_artifacts,
            "sort_by": q.sort_by,
            "sort_order": q.sort_order,
            "min_score": q.min_score,
        },
        "matches": scored[:limit],
    }


def render_memory_markdown(result: dict) -> str:
    """Render search results as compact Markdown for CLI/MCP consumers."""
    lines = [
        "# Case Memory Search",
        "",
        f"Indexed: {result.get('total_indexed', 0)}",
        f"Matches: {result.get('total_matches', 0)}",
        "",
    ]
    matches = result.get("matches", [])
    if not matches:
        lines.append("No matching cases found.")
        return "\n".join(lines)

    lines += [
        "| Score | Run ID | Model | Status | KPIs | Reasons | Path |",
        "|-------|--------|-------|--------|------|---------|------|",
    ]
    for item in matches:
        kpis = ", ".join(item.get("kpi_names", [])[:5])
        reasons = "; ".join(item.get("reasons", [])[:4])
        lines.append(
            f"| {item.get('score', 0):.3f} | {item.get('run_id', '')} | "
            f"{item.get('model_name', '')} | {item.get('status', '')} | "
            f"{kpis} | {reasons} | {item.get('workdir', '')} |"
        )
    return "\n".join(lines)


def _normalize_query(query: CaseMemoryQuery | dict) -> CaseMemoryQuery:
    if isinstance(query, CaseMemoryQuery):
        return replace(
            query,
            contracts_passed=_normalize_contracts_passed(query.contracts_passed),
            sort_by=_normalize_sort_by(query.sort_by),
            sort_order=_normalize_sort_order(query.sort_order),
            min_score=float(query.min_score),
        )
    roots = query.get("roots") or ()
    if isinstance(roots, (str, Path)):
        roots = (roots,)
    return CaseMemoryQuery(
        roots=tuple(roots),
        query=str(query.get("query", "")),
        similar_to=query.get("similar_to") or None,
        status=str(query.get("status", "")),
        model_name=str(query.get("model_name", "")),
        contract=str(query.get("contract", "")),
        contracts_passed=_normalize_contracts_passed(str(query.get("contracts_passed", ""))),
        diagnosis_id=str(query.get("diagnosis_id", "")),
        kpi=str(query.get("kpi", "")),
        artifact=str(query.get("artifact", "")),
        limit=int(query.get("limit", 10)),
        include_artifacts=bool(query.get("include_artifacts", False)),
        sort_by=_normalize_sort_by(str(query.get("sort_by", "score"))),
        sort_order=_normalize_sort_order(str(query.get("sort_order", "desc"))),
        min_score=float(query.get("min_score", 0.0)),
    )


def _sort_matches(matches: list[dict], sort_by: str, sort_order: str) -> None:
    reverse = sort_order == "desc"
    if sort_by == "score":
        matches.sort(key=lambda item: (item.get("score", 0), item.get("created_at") or ""), reverse=reverse)
        return
    if sort_by == "created_at":
        matches.sort(key=lambda item: (item.get("created_at") or "", item.get("score", 0)), reverse=reverse)
        return
    if sort_by in {"kpi_count", "artifact_count"}:
        matches.sort(key=lambda item: (int(item.get(sort_by, 0)), item.get("score", 0)), reverse=reverse)
        return
    matches.sort(key=lambda item: str(item.get(sort_by, "")).lower(), reverse=reverse)


def _normalize_sort_by(value: str) -> str:
    return value if value in {
        "score",
        "created_at",
        "run_id",
        "model_name",
        "status",
        "kpi_count",
        "artifact_count",
    } else "score"


def _normalize_sort_order(value: str) -> str:
    return "asc" if value.lower() == "asc" else "desc"


def _normalize_contracts_passed(value: str) -> str:
    normalized = value.lower()
    return normalized if normalized in {"passed", "failed"} else ""


def _public_entry(entry: dict, include_artifacts: bool) -> dict:
    public = dict(entry)
    artifacts = public.pop("artifacts", {}) or {}
    public["artifact_count"] = len(artifacts)
    public["artifact_names"] = sorted(artifacts)[:20]
    public["kpi_count"] = len(public.get("kpi_names", []))
    public["contract_count"] = len(public.get("contract_names", []))
    if include_artifacts:
        public["artifacts"] = artifacts
    return public


def _discover_capsules(roots: tuple[str | Path, ...]) -> list[Path]:
    seen: set[Path] = set()
    capsules: list[Path] = []
    for raw_root in roots:
        root = Path(raw_root).expanduser()
        if root.is_file() and root.name == "capsule.json":
            candidates = [root]
        elif root.is_file() and root.name == "result.json":
            candidates = [root.parent / "capsule.json"]
        elif root.is_dir() and (root / "capsule.json").exists():
            candidates = [root / "capsule.json"]
        elif root.is_dir():
            candidates = sorted(root.rglob("capsule.json"))
        else:
            candidates = []

        for path in candidates:
            resolved = path.resolve()
            if resolved.exists() and resolved not in seen:
                seen.add(resolved)
                capsules.append(resolved)
    return capsules


def _index_case(capsule_path: Path) -> dict:
    capsule = _load_json(capsule_path) or {}
    workdir = capsule_path.parent
    result = _load_json(workdir / "result.json") or {}
    spec = _load_spec(capsule, result, workdir)
    kpis = _coerce_kpis(result.get("kpis") or capsule.get("kpis") or {})
    contracts = result.get("contracts") or capsule.get("contracts") or {}
    diagnosis = capsule.get("diagnosis") or result.get("diagnosis") or {}
    inputs = capsule.get("inputs") or {}
    provenance = capsule.get("provenance") or {}

    return {
        "run_id": capsule.get("run_id") or result.get("run_id") or workdir.name,
        "capsule_path": str(capsule_path),
        "result_path": str(workdir / "result.json") if (workdir / "result.json").exists() else "",
        "workdir": str(workdir),
        "created_at": capsule.get("created_at") or "",
        "model_name": inputs.get("model_name") or _nested(spec, ("meta", "model_name")) or "",
        "status": result.get("status") or provenance.get("status") or "",
        "abaqus_release": provenance.get("abaqus_release") or _nested(spec, ("meta", "abaqus_release")) or "",
        "geometry_type": _nested(spec, ("geometry", "type")) or "",
        "material_name": _nested(spec, ("material", "name")) or "",
        "solver": _nested(spec, ("analysis", "solver")) or "",
        "step_type": _nested(spec, ("analysis", "step_type")) or "",
        "kpis": kpis,
        "kpi_names": sorted(kpis),
        "contracts_passed": contracts.get("passed") if isinstance(contracts, dict) else None,
        "contract_names": _contract_names(contracts),
        "diagnosis_ids": _diagnosis_ids(diagnosis),
        "input_hashes": _input_hashes(inputs),
        "inputs": inputs,
        "artifacts": capsule.get("artifacts") or {},
    }


def _load_target(path: str | Path | None) -> dict | None:
    if not path:
        return None
    raw = Path(path).expanduser()
    capsule_path = raw / "capsule.json" if raw.is_dir() else raw
    if capsule_path.name == "result.json":
        candidate = capsule_path.parent / "capsule.json"
        if candidate.exists():
            capsule_path = candidate
    if capsule_path.name != "capsule.json" or not capsule_path.exists():
        return None
    return _index_case(capsule_path.resolve())


def _passes_filters(entry: dict, query: CaseMemoryQuery) -> bool:
    if query.status and entry.get("status", "").lower() != query.status.lower():
        return False
    if query.model_name and query.model_name.lower() not in entry.get("model_name", "").lower():
        return False
    if query.contract:
        needle = query.contract.lower()
        contract_names = [name.lower() for name in entry.get("contract_names", [])]
        if not any(needle in name for name in contract_names):
            return False
    if query.contracts_passed == "passed" and entry.get("contracts_passed") is not True:
        return False
    if query.contracts_passed == "failed" and entry.get("contracts_passed") is not False:
        return False
    if query.diagnosis_id and query.diagnosis_id not in entry.get("diagnosis_ids", []):
        return False
    if query.kpi and query.kpi not in entry.get("kpi_names", []):
        return False
    if query.artifact:
        needle = query.artifact.lower()
        artifact_names = [name.lower() for name in entry.get("artifacts", {})]
        if not any(needle in name for name in artifact_names):
            return False
    return True


def _score_entry(entry: dict, query: CaseMemoryQuery, target: dict | None) -> tuple[float, list[str]]:
    score = 0.0
    reasons: list[str] = []

    tokens = _tokens(query.query)
    if tokens:
        haystack = _search_text(entry)
        hits = [token for token in tokens if token in haystack]
        if hits:
            score += len(hits) * 1.0
            reasons.append("text:" + ",".join(hits[:5]))

    if query.artifact:
        score += 0.75
        reasons.append(f"artifact:{query.artifact}")
    if query.contract:
        score += 0.75
        reasons.append(f"contract:{query.contract}")

    if not tokens and not target:
        score += 0.1
        reasons.append("recent indexed case")

    if target:
        sim_score, sim_reasons = _similarity_score(entry, target)
        score += sim_score
        reasons.extend(sim_reasons)

    if entry.get("contracts_passed") is True:
        score += 0.15
        reasons.append("contracts passed")
    if entry.get("status") == "COMPLETED":
        score += 0.1
        reasons.append("completed run")
    if entry.get("diagnosis_ids"):
        score += 0.05
        reasons.append("has diagnosis")

    return score, reasons


def _similarity_score(entry: dict, target: dict) -> tuple[float, list[str]]:
    if entry.get("capsule_path") == target.get("capsule_path"):
        return 0.0, []

    score = 0.0
    reasons: list[str] = []
    for key, weight, label in [
        ("model_name", 2.0, "same model"),
        ("geometry_type", 1.5, "same geometry"),
        ("material_name", 1.0, "same material"),
        ("solver", 0.8, "same solver"),
        ("step_type", 0.5, "same step"),
    ]:
        if entry.get(key) and entry.get(key) == target.get(key):
            score += weight
            reasons.append(label)

    common_kpis = sorted(set(entry.get("kpi_names", [])) & set(target.get("kpi_names", [])))
    if common_kpis:
        score += min(2.0, 0.4 * len(common_kpis))
        reasons.append("shared KPIs:" + ",".join(common_kpis[:5]))

    common_hashes = sorted(set(entry.get("input_hashes", [])) & set(target.get("input_hashes", [])))
    if common_hashes:
        score += 3.0
        reasons.append("same input hash")

    common_diag = sorted(set(entry.get("diagnosis_ids", [])) & set(target.get("diagnosis_ids", [])))
    if common_diag:
        score += min(1.5, 0.5 * len(common_diag))
        reasons.append("shared diagnosis:" + ",".join(common_diag[:5]))

    return score, reasons


def _search_text(entry: dict) -> str:
    parts = [
        entry.get("run_id", ""),
        entry.get("workdir", ""),
        entry.get("capsule_path", ""),
        entry.get("result_path", ""),
        entry.get("model_name", ""),
        entry.get("status", ""),
        entry.get("abaqus_release", ""),
        entry.get("geometry_type", ""),
        entry.get("material_name", ""),
        entry.get("solver", ""),
        entry.get("step_type", ""),
        " ".join(entry.get("kpi_names", [])),
        " ".join(entry.get("contract_names", [])),
        " ".join(entry.get("diagnosis_ids", [])),
        " ".join(entry.get("artifacts", {}).keys()),
    ]
    text = " ".join(str(part).lower() for part in parts)
    compact = re.sub(r"[^a-z0-9]+", "", text)
    return f"{text} {compact}"


def _query_matches(entry: dict, query: str) -> bool:
    tokens = _tokens(query)
    if not tokens:
        return True
    haystack = _search_text(entry)
    return any(token in haystack for token in tokens)


def _tokens(text: str) -> list[str]:
    return [part.lower() for part in re.findall(r"[A-Za-z0-9_.:-]+", text or "")]


def _load_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _load_spec(capsule: dict, result: dict, workdir: Path) -> dict:
    if isinstance(result.get("spec"), dict):
        return result["spec"]
    inputs = capsule.get("inputs") or {}
    for raw_path in (inputs.get("spec"), inputs.get("spec_path")):
        if not raw_path:
            continue
        path = Path(raw_path)
        if not path.is_absolute():
            path = workdir / path
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            if isinstance(data, dict):
                return data
        except (OSError, yaml.YAMLError):
            continue
    return {}


def _coerce_kpis(raw: dict) -> dict:
    kpis = {}
    if not isinstance(raw, dict):
        return kpis
    for name, value in raw.items():
        if isinstance(value, dict) and "value" in value:
            kpis[name] = value["value"]
        else:
            kpis[name] = value
    return kpis


def _contract_names(contracts: Any) -> list[str]:
    if not isinstance(contracts, dict):
        return []
    return [
        str(item.get("name", ""))
        for item in contracts.get("results", [])
        if isinstance(item, dict) and item.get("name")
    ]


def _diagnosis_ids(diagnosis: Any) -> list[str]:
    if not isinstance(diagnosis, dict):
        return []
    return [
        str(item.get("id", ""))
        for item in diagnosis.get("matches", [])
        if isinstance(item, dict) and item.get("id")
    ]


def _input_hashes(inputs: Any) -> list[str]:
    if not isinstance(inputs, dict):
        return []
    return sorted(str(value) for key, value in inputs.items() if key.endswith("_sha256") and value)


def _nested(data: dict, keys: tuple[str, ...]) -> Any:
    cur: Any = data
    for key in keys:
        if not isinstance(cur, dict):
            return ""
        cur = cur.get(key)
    return cur or ""
