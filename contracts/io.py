"""
io.py
-----
Load Physics Contracts from JSON/YAML files and legacy expected.json files.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml


def load_contracts(path: str | Path) -> list[dict[str, Any]]:
    """
    Load contract definitions from JSON/YAML.

    Accepted shapes:
    - [{"type": "range", ...}, ...]
    - {"contracts": [{"type": "range", ...}, ...]}
    - legacy expected.json: {"kpis": {"U_tip": {"value": ..., "rtol": ...}}}
    """
    data = _load_structured(path)
    if isinstance(data, list):
        return [_normalize_contract(item) for item in data]
    if isinstance(data, dict):
        if "contracts" in data:
            contracts = data["contracts"]
            if not isinstance(contracts, list):
                raise ValueError("contracts must be a list")
            return [_normalize_contract(item) for item in contracts]
        if "kpis" in data:
            return contracts_from_expected(data)
    raise ValueError("contract file must be a list, a {'contracts': [...]} object, or legacy expected.json")


def contracts_from_expected(expected: dict[str, Any]) -> list[dict[str, Any]]:
    """Convert legacy expected.json KPI references into relative_error contracts."""
    kpis = expected.get("kpis")
    if not isinstance(kpis, dict):
        raise ValueError("expected.json must contain a kpis object")

    contracts = []
    for name, definition in sorted(kpis.items()):
        if not isinstance(definition, dict) or "value" not in definition:
            raise ValueError(f"expected KPI {name} must define value")
        contract = {
            "name": f"{name} reference tolerance",
            "type": "relative_error",
            "kpi": name,
            "reference": definition["value"],
            "rtol": definition.get("rtol", 0.05),
            "atol": definition.get("atol", 0.0),
        }
        if "unit" in definition:
            contract["unit"] = definition["unit"]
        if "note" in definition:
            contract["note"] = definition["note"]
        contracts.append(contract)
    return contracts


def _load_structured(path: str | Path) -> Any:
    file_path = Path(path)
    text = file_path.read_text(encoding="utf-8")
    if file_path.suffix.lower() == ".json":
        return json.loads(text)
    return yaml.safe_load(text)


def _normalize_contract(contract: Any) -> dict[str, Any]:
    if not isinstance(contract, dict):
        raise ValueError("each contract must be an object")
    if "type" not in contract:
        raise ValueError("each contract must define type")
    return dict(contract)
