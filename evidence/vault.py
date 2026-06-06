"""Local persistent evidence vault."""

from __future__ import annotations

import json
import os
import re
import shutil
import time
import uuid
from pathlib import Path, PurePosixPath
from typing import Any

VAULT_SCHEMA_VERSION = "1.0"
VAULT_ENV = "ABAQUS_AGENT_EVIDENCE_VAULT"


def default_vault_root() -> Path:
    configured = os.environ.get(VAULT_ENV)
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".abaqus-agent" / "evidence-vault"


def create_vault_entry(
    *,
    kind: str,
    title: str,
    files: dict[str, str | Path],
    summary: dict[str, Any] | None = None,
    root: str | Path | None = None,
) -> dict[str, Any]:
    vault_root = Path(root).expanduser() if root is not None else default_vault_root()
    vault_root.mkdir(parents=True, exist_ok=True)
    safe_kind = _safe_slug(kind)
    created_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    vault_id = f"{safe_kind}-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}-{uuid.uuid4().hex[:8]}"
    entry_dir = vault_root / vault_id
    entry_dir.mkdir(parents=True, exist_ok=False)

    stored_files = {}
    for filename, source in files.items():
        safe_name = _safe_filename(filename)
        source_path = Path(source)
        if not source_path.exists() or not source_path.is_file():
            raise FileNotFoundError(f"Vault source file not found: {source}")
        target = entry_dir / safe_name
        if not target.resolve().is_relative_to(entry_dir.resolve()):
            raise ValueError(f"Vault filename is outside entry directory: {filename}")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, target)
        stored_files[safe_name] = {
            "filename": safe_name,
            "path": str(target),
            "size_bytes": target.stat().st_size,
        }

    record = {
        "schema_version": VAULT_SCHEMA_VERSION,
        "vault_id": vault_id,
        "kind": safe_kind,
        "title": title,
        "created_at": created_at,
        "summary": summary or {},
        "files": stored_files,
    }
    (entry_dir / "record.json").write_text(
        json.dumps(record, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return record


def list_vault_entries(
    *,
    root: str | Path | None = None,
    limit: int = 50,
    query: str = "",
    kind: str = "",
    status: str = "",
) -> dict[str, Any]:
    vault_root = Path(root).expanduser() if root is not None else default_vault_root()
    safe_limit = max(1, min(limit, 200))
    selected_query = query.strip().lower()
    selected_kind = kind.strip().lower()
    selected_status = status.strip().lower()
    if not vault_root.exists():
        return {
            "items": [],
            "total": 0,
            "root": str(vault_root),
            "query": selected_query,
            "kind": selected_kind,
            "status": selected_status,
        }

    records = []
    for record_path in vault_root.glob("*/record.json"):
        try:
            record = json.loads(record_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        record_kind = str(record.get("kind", "")).lower()
        record_status = _status_from_summary(record.get("summary", {})).lower()
        if selected_query and selected_query not in _record_search_text(record):
            continue
        if selected_kind and record_kind != selected_kind:
            continue
        if selected_status and record_status != selected_status:
            continue
        records.append(record)
    records.sort(key=lambda record: record.get("created_at", ""), reverse=True)
    return {
        "items": records[:safe_limit],
        "total": len(records),
        "root": str(vault_root),
        "query": selected_query,
        "kind": selected_kind,
        "status": selected_status,
    }


def get_vault_record(
    vault_id: str,
    *,
    root: str | Path | None = None,
) -> dict[str, Any]:
    safe_vault_id = _safe_slug(vault_id)
    vault_root = Path(root).expanduser() if root is not None else default_vault_root()
    record_path = vault_root / safe_vault_id / "record.json"
    if not record_path.exists() or not record_path.is_file():
        raise FileNotFoundError(f"Vault record not found: {vault_id}")
    try:
        return json.loads(record_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise FileNotFoundError(f"Vault record not found: {vault_id}") from exc


def get_vault_file_path(
    vault_id: str,
    filename: str,
    *,
    root: str | Path | None = None,
) -> Path:
    safe_vault_id = _safe_slug(vault_id)
    safe_name = _safe_filename(filename)
    vault_root = Path(root).expanduser() if root is not None else default_vault_root()
    entry_dir = vault_root / safe_vault_id
    path = entry_dir / safe_name
    if not path.resolve().is_relative_to(entry_dir.resolve()):
        raise FileNotFoundError(f"Vault file not found: {vault_id}/{filename}")
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"Vault file not found: {vault_id}/{filename}")
    return path


def _safe_slug(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip()).strip(".-")
    if not cleaned:
        raise ValueError("Vault id/kind is required")
    if cleaned in {".", ".."}:
        raise ValueError("Vault id/kind is invalid")
    return cleaned


def _status_from_summary(summary: dict[str, Any]) -> str:
    for key in ("overall_status", "status", "doctor_status", "contracts_status"):
        value = summary.get(key)
        if value:
            return str(value)
    return "UNKNOWN"


def _record_search_text(record: dict[str, Any]) -> str:
    parts = [
        record.get("vault_id", ""),
        record.get("kind", ""),
        record.get("title", ""),
        _status_from_summary(record.get("summary", {})),
        json.dumps(record.get("summary", {}), sort_keys=True),
        " ".join(record.get("files", {}).keys()),
    ]
    return " ".join(str(part) for part in parts).lower()


def _safe_filename(value: str) -> str:
    raw = value.strip()
    if not raw:
        raise ValueError("Vault filename is invalid")
    if "\\" in raw:
        raise ValueError(f"Vault filename must use POSIX separators: {value}")
    relative = PurePosixPath(raw)
    if relative.is_absolute():
        raise ValueError(f"Vault filename must be relative: {value}")
    parts = [part for part in relative.parts if part not in {"", "."}]
    if not parts or any(part == ".." for part in parts):
        raise ValueError(f"Vault filename is invalid: {value}")
    for part in parts:
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", part):
            raise ValueError(f"Vault filename contains unsupported characters: {value}")
    return PurePosixPath(*parts).as_posix()
