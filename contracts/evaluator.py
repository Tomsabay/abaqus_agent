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


def evaluate_contracts(arg1: list[dict] | dict, arg2: list[dict] | dict) -> dict:
    """Evaluate deterministic contracts against KPI values.

    The public API has used both argument orders in this repo. Accept both
    evaluate_contracts(contracts, kpis) and evaluate_contracts(kpis, contracts)
    so release evidence tooling can coexist with the v0.2 kernel path.
    """
    if isinstance(arg1, dict) and isinstance(arg2, list):
        kpis = arg1
        contracts = arg2
    elif isinstance(arg1, list) and isinstance(arg2, dict):
        contracts = arg1
        kpis = arg2
    else:
        raise TypeError("evaluate_contracts expects (contracts, kpis) or (kpis, contracts)")

    results = [_evaluate_one(contract, kpis) for contract in contracts]
    failed_count = sum(1 for r in results if r["status"] == "FAIL")
    warning_count = sum(1 for r in results if r["status"] == "WARNING")
    status = "FAIL" if failed_count else "WARNING" if warning_count else "PASS"
    return {
        "status": status,
        "passed": failed_count == 0,
        "total": len(results),
        "passed_count": sum(1 for r in results if r["passed"]),
        "failed_count": failed_count,
        "warning_count": warning_count,
        "checks": results,
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
        extra = {}
        if kind == "relative_error":
            extra["rel_error"] = _relative_error_value(actual, expected)
    except KeyError as e:
        passed, detail = False, f"missing KPI: {e.args[0]}"
        expected = None
        extra = {}
    except (TypeError, ValueError) as e:
        passed, detail = False, f"Invalid contract value: {e}"
        expected = None
        extra = {}

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
        "message": detail,
        **extra,
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
        return False, f"{contract['kpi']}={value} below min {minimum}", {"min": minimum, "max": maximum}
    if maximum is not None and value > float(maximum):
        return False, f"{contract['kpi']}={value} above max {maximum}", {"min": minimum, "max": maximum}
    return True, f"{contract['kpi']}={value} in range", {"min": minimum, "max": maximum}


def _check_direction(contract: dict, kpis: dict) -> tuple[bool, str]:
    value = _require_kpi(contract, kpis)
    op = contract.get("operator") or contract.get("op")
    if op in _OPERATORS:
        target = float(contract.get("value", 0.0))
        return _OPERATORS[op](value, target), f"{contract['kpi']}={value}, expected {op} {target}"

    direction = op or contract.get("direction", "negative")
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
    expected = float(contract.get("expected", contract.get("reference")))
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
    op = contract.get("operator") or contract.get("op")
    if op in _OPERATORS:
        return f"{op} {contract.get('value', 0.0)}"
    return op or contract.get("direction", "negative")


def _relative_error_value(actual, expected):
    if not isinstance(expected, dict) or actual is None:
        return None
    value = expected.get("value")
    if value is None:
        return None
    if abs(float(value)) <= 1e-12:
        return None
    return abs(float(actual) - float(value)) / abs(float(value))


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
