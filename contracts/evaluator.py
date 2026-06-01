"""Evaluate physics contracts against extracted KPI values."""

from __future__ import annotations


def evaluate_contracts(contracts: list[dict], kpis: dict) -> dict:
    """Evaluate a list of deterministic contracts against KPI values."""
    results = [_evaluate_one(contract, kpis) for contract in contracts]
    return {
        "passed": all(r["passed"] or r["severity"] == "warning" for r in results),
        "results": results,
    }


def _evaluate_one(contract: dict, kpis: dict) -> dict:
    kind = contract.get("type", "range")
    severity = contract.get("severity", "error")
    name = contract.get("name") or contract.get("kpi") or kind

    try:
        if kind == "range":
            passed, detail = _check_range(contract, kpis)
        elif kind == "direction":
            passed, detail = _check_direction(contract, kpis)
        elif kind == "relative_error":
            passed, detail = _check_relative_error(contract, kpis)
        elif kind in ("order", "monotonic"):
            passed, detail = _check_order(contract, kpis)
        else:
            passed, detail = False, f"Unsupported contract type: {kind}"
    except KeyError as e:
        passed, detail = False, f"Missing KPI: {e.args[0]}"

    return {
        "name": name,
        "type": kind,
        "severity": severity,
        "passed": passed,
        "detail": detail,
    }


def _require_kpi(contract: dict, kpis: dict) -> float:
    kpi = contract["kpi"]
    if kpi not in kpis:
        raise KeyError(kpi)
    return float(kpis[kpi])


def _check_range(contract: dict, kpis: dict) -> tuple[bool, str]:
    value = _require_kpi(contract, kpis)
    minimum = contract.get("min")
    maximum = contract.get("max")
    if minimum is not None and value < float(minimum):
        return False, f"{contract['kpi']}={value} < min {minimum}"
    if maximum is not None and value > float(maximum):
        return False, f"{contract['kpi']}={value} > max {maximum}"
    return True, f"{contract['kpi']}={value} in range"


def _check_direction(contract: dict, kpis: dict) -> tuple[bool, str]:
    value = _require_kpi(contract, kpis)
    direction = contract.get("direction", "negative")
    if direction == "negative":
        return value < 0, f"{contract['kpi']}={value}, expected negative"
    if direction == "positive":
        return value > 0, f"{contract['kpi']}={value}, expected positive"
    if direction == "zero":
        tolerance = float(contract.get("tolerance", 1e-12))
        return abs(value) <= tolerance, f"{contract['kpi']}={value}, expected near zero"
    return False, f"Unsupported direction: {direction}"


def _check_relative_error(contract: dict, kpis: dict) -> tuple[bool, str]:
    value = _require_kpi(contract, kpis)
    expected = float(contract["expected"])
    rtol = float(contract.get("rtol", 0.05))
    atol = float(contract.get("atol", 0.0))
    err = abs(value - expected)
    limit = atol + rtol * max(abs(expected), 1e-12)
    return err <= limit, f"{contract['kpi']} actual={value}, expected={expected}, err={err}, limit={limit}"


def _check_order(contract: dict, kpis: dict) -> tuple[bool, str]:
    names = contract["kpis"]
    values = []
    for name in names:
        if name not in kpis:
            raise KeyError(name)
        values.append(float(kpis[name]))
    direction = contract.get("direction", "increasing")
    if direction == "increasing":
        passed = all(a < b for a, b in zip(values, values[1:]))
    elif direction == "decreasing":
        passed = all(a > b for a, b in zip(values, values[1:]))
    else:
        return False, f"Unsupported order direction: {direction}"
    return passed, f"{names}={values}, expected {direction}"
