"""Evaluate physics contracts against extracted KPI values."""

from __future__ import annotations

import math
import operator

_BLOCKING_SEVERITIES = {"error", "critical", "fail"}
_NON_BLOCKING_SEVERITIES = {"warning", "warn", "info"}
_OPERATORS = {
    "<": operator.lt,
    "<=": operator.le,
    ">": operator.gt,
    ">=": operator.ge,
    "==": operator.eq,
    "!=": operator.ne,
}


def evaluate_contracts(contracts: list[dict], kpis: dict) -> dict:
    """Evaluate a list of deterministic contracts against KPI values."""
    results = [_evaluate_one(contract, kpis) for contract in contracts]
    return {
        "passed": all(r["passed"] or not _is_blocking(r["severity"]) for r in results),
        "results": results,
    }


def _evaluate_one(contract: dict, kpis: dict) -> dict:
    kind = contract.get("check") or contract.get("type", "range")
    severity = _normalize_severity(contract.get("severity", "error"))
    name = contract.get("name") or contract.get("kpi") or kind
    actual = None

    try:
        actual = _actual_value(contract, kpis)
        if kind == "range":
            passed, detail, expected = _check_range(contract, kpis)
        elif kind in ("direction", "operator"):
            passed, detail = _check_direction(contract, kpis)
            expected = _direction_expected(contract)
        elif kind == "relative_error":
            passed, detail, expected = _check_relative_error(contract, kpis)
        elif kind in ("order", "monotonic"):
            passed, detail = _check_order(contract, kpis)
            expected = contract.get("direction", "increasing")
        else:
            passed, detail = False, f"Unsupported contract type: {kind}"
            expected = None
    except KeyError as e:
        passed, detail = False, f"Missing KPI: {e.args[0]}"
        expected = None
    except (TypeError, ValueError) as e:
        passed, detail = False, f"Invalid contract value: {e}"
        expected = None

    status = _status(passed, severity)
    return {
        "name": name,
        "type": kind,
        "check": kind,
        "severity": severity,
        "status": status,
        "passed": passed,
        "actual": actual,
        "expected": expected,
        "detail": detail,
    }


def _require_kpi(contract: dict, kpis: dict) -> float:
    kpi = contract["kpi"]
    if kpi not in kpis:
        raise KeyError(kpi)
    return _coerce_number(kpis[kpi])


def _actual_value(contract: dict, kpis: dict):
    if "kpi" in contract:
        return _require_kpi(contract, kpis)
    if "kpis" in contract:
        return [_coerce_number(kpis[name]) if name in kpis else None for name in contract["kpis"]]
    return None


def _coerce_number(raw) -> float:
    if isinstance(raw, dict):
        raw = raw.get("value")
    value = float(raw)
    if not math.isfinite(value):
        raise ValueError(f"non-finite KPI value {raw!r}")
    return value


def _check_range(contract: dict, kpis: dict) -> tuple[bool, str, dict]:
    value = _require_kpi(contract, kpis)
    minimum = contract.get("min")
    maximum = contract.get("max")
    if minimum is not None and value < float(minimum):
        return False, f"{contract['kpi']}={value} < min {minimum}", {"min": minimum, "max": maximum}
    if maximum is not None and value > float(maximum):
        return False, f"{contract['kpi']}={value} > max {maximum}", {"min": minimum, "max": maximum}
    return True, f"{contract['kpi']}={value} in range", {"min": minimum, "max": maximum}


def _check_direction(contract: dict, kpis: dict) -> tuple[bool, str]:
    value = _require_kpi(contract, kpis)
    op = contract.get("operator")
    if op:
        target = float(contract.get("value", 0.0))
        if op not in _OPERATORS:
            return False, f"Unsupported operator: {op}"
        return _OPERATORS[op](value, target), f"{contract['kpi']}={value}, expected {op} {target}"

    direction = contract.get("direction", "negative")
    if direction == "negative":
        return value < 0, f"{contract['kpi']}={value}, expected negative"
    if direction == "positive":
        return value > 0, f"{contract['kpi']}={value}, expected positive"
    if direction == "zero":
        tolerance = float(contract.get("tolerance", 1e-12))
        return abs(value) <= tolerance, f"{contract['kpi']}={value}, expected near zero"
    return False, f"Unsupported direction: {direction}"


def _check_relative_error(contract: dict, kpis: dict) -> tuple[bool, str, dict]:
    value = _require_kpi(contract, kpis)
    expected = float(contract["expected"])
    rtol = float(contract.get("rtol", 0.05))
    atol = float(contract.get("atol", 0.0))
    err = abs(value - expected)
    limit = atol + rtol * max(abs(expected), 1e-12)
    return (
        err <= limit,
        f"{contract['kpi']} actual={value}, expected={expected}, err={err}, limit={limit}",
        {"value": expected, "rtol": rtol, "atol": atol, "limit": limit},
    )


def _check_order(contract: dict, kpis: dict) -> tuple[bool, str]:
    names = contract["kpis"]
    values = []
    for name in names:
        if name not in kpis:
            raise KeyError(name)
        values.append(_coerce_number(kpis[name]))
    direction = contract.get("direction", "increasing")
    if direction == "increasing":
        passed = all(a < b for a, b in zip(values, values[1:]))
    elif direction == "decreasing":
        passed = all(a > b for a, b in zip(values, values[1:]))
    else:
        return False, f"Unsupported order direction: {direction}"
    return passed, f"{names}={values}, expected {direction}"


def _direction_expected(contract: dict) -> str:
    if contract.get("operator"):
        return f"{contract['operator']} {contract.get('value', 0.0)}"
    return contract.get("direction", "negative")


def _normalize_severity(severity: str) -> str:
    normalized = str(severity or "error").lower()
    if normalized == "warn":
        return "warning"
    if normalized in _NON_BLOCKING_SEVERITIES or normalized in _BLOCKING_SEVERITIES:
        return normalized
    return "error"


def _is_blocking(severity: str) -> bool:
    return _normalize_severity(severity) in _BLOCKING_SEVERITIES


def _status(passed: bool, severity: str) -> str:
    if passed:
        return "PASS"
    if _is_blocking(severity):
        return "FAIL"
    if severity == "info":
        return "INFO"
    return "WARNING"
