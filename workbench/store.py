"""
workbench/store.py
------------------
Disk-backed session store for the workbench.

One JSON file per session under artifacts/workbench_sessions/ (override with
ABAQUS_AGENT_WORKBENCH_SESSION_DIR, used by tests). Sessions survive server
restarts; only the newest KEEP_SESSIONS files are retained.
"""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path

from core import config

STORE_DIR_ENV = config.ENV_WORKBENCH_SESSION_DIR
KEEP_SESSIONS = 100
_SESSION_PREFIX = "wb-"


def store_dir() -> Path:
    # config resolves override → packaged data dir → repo-local (dev).
    return config.workbench_session_dir()


def _session_path(session_id: str) -> Path:
    return store_dir() / f"{session_id}.json"


def valid_session_id(session_id: str) -> bool:
    return (
        session_id.startswith(_SESSION_PREFIX)
        and session_id.replace(_SESSION_PREFIX, "", 1).isalnum()
        and len(session_id) <= 40
    )


def new_session(title: str = "") -> dict:
    now = time.time()
    session = {
        "session_id": _SESSION_PREFIX + uuid.uuid4().hex[:10],
        "title": title.strip()[:80] or "新会话",
        "created_at": now,
        "updated_at": now,
        "messages": [],
        "current_spec_yaml": None,
        "pending": None,
        "runs": [],
    }
    save_session(session)
    return session


def load_session(session_id: str) -> dict | None:
    if not valid_session_id(session_id):
        return None
    path = _session_path(session_id)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) and data.get("session_id") == session_id else None


def save_session(session: dict) -> None:
    directory = store_dir()
    directory.mkdir(parents=True, exist_ok=True)
    session["updated_at"] = time.time()
    path = _session_path(session["session_id"])
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(session, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
    _prune(directory)


def list_sessions() -> list[dict]:
    directory = store_dir()
    if not directory.is_dir():
        return []
    summaries = []
    for path in directory.glob(f"{_SESSION_PREFIX}*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict) or not data.get("session_id"):
            continue
        summaries.append({
            "session_id": data["session_id"],
            "title": data.get("title", ""),
            "created_at": data.get("created_at", 0),
            "updated_at": data.get("updated_at", 0),
            "message_count": len(data.get("messages", [])),
            "run_count": len(data.get("runs", [])),
            "has_pending": bool(data.get("pending")),
        })
    return sorted(summaries, key=lambda s: s["updated_at"], reverse=True)


def _prune(directory: Path) -> None:
    files = sorted(
        directory.glob(f"{_SESSION_PREFIX}*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for stale in files[KEEP_SESSIONS:]:
        try:
            stale.unlink()
        except OSError:
            pass
