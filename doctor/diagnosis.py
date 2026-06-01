"""Pattern-based Abaqus solver diagnostics."""

from __future__ import annotations

import re
from pathlib import Path

import yaml


def load_patterns(path: str | Path | None = None) -> list[dict]:
    """Load solver diagnostic patterns."""
    pattern_path = Path(path) if path else Path(__file__).with_name("patterns.yaml")
    data = yaml.safe_load(pattern_path.read_text(encoding="utf-8"))
    return data.get("patterns", [])


def diagnose_logs(paths: list[str | Path] | None = None, text: str = "",
                  patterns: list[dict] | None = None) -> dict:
    """Diagnose Abaqus logs from files and/or raw text."""
    corpus = text or ""
    for path in paths or []:
        p = Path(path)
        if p.exists():
            corpus += "\n" + p.read_text(encoding="utf-8", errors="replace")

    matches = []
    for pattern in patterns or load_patterns():
        regex = re.compile(pattern["regex"], re.IGNORECASE | re.MULTILINE)
        match = regex.search(corpus)
        if match:
            matches.append({
                "id": pattern["id"],
                "category": pattern["category"],
                "severity": pattern.get("severity", "error"),
                "evidence": match.group(0)[:500],
                "suggestion": pattern.get("suggestion", ""),
            })

    return {
        "matched": bool(matches),
        "matches": matches,
    }
