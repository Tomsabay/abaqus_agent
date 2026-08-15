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


def normalize_contracts(items: Any) -> list[dict[str, Any]]:
    """Validate and normalize an already-parsed list of contracts.

    For contracts that arrive as data rather than as a file: embedded in a
    spec, or handed to the orchestrator directly. Same rules either way, so
    there is one definition of what a contract is.
    """
    if isinstance(items, dict):
        items = items.get("contracts", [])
    if items is None:
        return []
    if not isinstance(items, list):
        raise ValueError("contracts must be a list")
    return [_normalize_contract(item) for item in items]


def _normalize_contract(contract: Any) -> dict[str, Any]:
    """`check:` and `type:` are the same field under two names.

    contracts/evaluator.py has always read `contract.get("check") or
    contract.get("type")`, and the repo ships both dialects: every file under
    examples/contracts/ says `type:`, cases/cantilever/contracts.yaml says
    `check:`. This loader used to demand `type:`, so it raised ValueError on
    the only contract file the cases actually ship -- reachable from
    evidence/offline.py and evidence/real_smoke_contract_diff.py, both of
    which take the path from their caller.

    Neither key is a fail-open: evaluator's `.get("type", "range")` default
    turns a misspelled kind into a range check, which then reports on whatever
    min/max the contract happens not to have.
    """
    if not isinstance(contract, dict):
        raise ValueError("each contract must be an object")
    kind = contract.get("check") or contract.get("type")
    if not kind:
        raise ValueError(
            "each contract must define check (or its older spelling, type); "
            "got keys: %s" % sorted(contract))
    normalized = dict(contract)
    normalized["check"] = normalized["type"] = kind
    return normalized
