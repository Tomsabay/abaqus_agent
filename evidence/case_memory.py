"""Case Memory helpers backed by the local evidence vault."""

from __future__ import annotations

from typing import Any

from evidence.vault import list_vault_entries


def search_case_memory(
    *,
    query: str = "",
    kind: str = "",
    status: str = "",
    limit: int = 50,
    url_prefix: str = "/api/evidence/vault",
) -> dict[str, Any]:
    vault = list_vault_entries(limit=max(limit, 1))
    normalized_query = query.strip().lower()
    normalized_kind = kind.strip().lower()
    normalized_status = status.strip().lower()

    items = []
    for record in vault["items"]:
        item = _record_to_memory_item(record, url_prefix=url_prefix)
        if normalized_kind and item["kind"].lower() != normalized_kind:
            continue
        if normalized_status and item["status"].lower() != normalized_status:
            continue
        if normalized_query and normalized_query not in _search_blob(item):
            continue
        items.append(item)

    safe_limit = max(1, min(limit, 200))
    return {
        "schema_version": "1.0",
        "workflow": "case-memory-vault-search",
        "query": query,
        "kind": kind,
        "status": status,
        "items": items[:safe_limit],
        "total": len(items),
        "root": vault["root"],
    }


def _record_to_memory_item(record: dict[str, Any], *, url_prefix: str) -> dict[str, Any]:
    files = sorted(record.get("files", {}))
    vault_id = record["vault_id"]
    return {
        "memory_id": vault_id,
        "vault_id": vault_id,
        "kind": record.get("kind", ""),
        "title": record.get("title", ""),
        "created_at": record.get("created_at", ""),
        "status": _status_from_summary(record.get("summary", {})),
        "summary": record.get("summary", {}),
        "files": files,
        "vault_urls": {
            filename: f"{url_prefix}/{vault_id}/{filename}"
            for filename in files
        },
    }


def _status_from_summary(summary: dict[str, Any]) -> str:
    for key in ("overall_status", "status", "doctor_status", "contracts_status"):
        value = summary.get(key)
        if value:
            return str(value)
    return "UNKNOWN"


def _search_blob(item: dict[str, Any]) -> str:
    values = [
        item.get("memory_id", ""),
        item.get("kind", ""),
        item.get("title", ""),
        item.get("status", ""),
        " ".join(item.get("files", [])),
    ]
    summary = item.get("summary", {})
    values.extend(str(value) for value in summary.values())
    return " ".join(values).lower()
