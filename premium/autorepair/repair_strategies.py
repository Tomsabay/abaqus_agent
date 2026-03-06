"""
repair_strategies.py
--------------------
Applies parameter changes from diagnosis to spec for retry.

Takes a diagnosis result and modifies the spec YAML to attempt
automatic repair of the failed simulation.
"""

from __future__ import annotations

import copy
from pathlib import Path

import yaml


def apply_repairs(spec: dict, diagnosis: dict) -> dict:
    """
    Apply parameter changes from diagnosis to create a repaired spec.

    Parameters
    ----------
    spec      : Original problem spec dict
    diagnosis : Diagnosis result with parameter_changes list

    Returns
    -------
    Modified spec dict ready for retry
    """
    repaired = copy.deepcopy(spec)
    changes = diagnosis.get("parameter_changes", [])

    for change in changes:
        param = change.get("param", "")
        suggested = change.get("suggested", "")

        _apply_single_change(repaired, param, suggested)

    # Track repair history
    meta = repaired.setdefault("meta", {})
    repair_history = meta.get("_repair_history", [])
    repair_history.append({
        "root_cause": diagnosis.get("root_cause", ""),
        "fix_action": diagnosis.get("fix_action", ""),
        "changes": changes,
    })
    meta["_repair_history"] = repair_history

    return repaired


def _apply_single_change(spec: dict, param: str, suggested: str) -> None:
    """Apply a single parameter change to the spec."""
    suggested_str = str(suggested).strip()

    # Increment size changes
    if param in ("initial_increment", "initial_inc"):
        try:
            val = float(suggested_str)
            # Modify by adjusting time_period / initial_inc ratio
            # The actual Abaqus parameter is controlled in step generation
            spec.setdefault("analysis", {})["_initial_inc"] = val
        except ValueError:
            pass

    elif param == "max_iterations":
        try:
            val = int(suggested_str)
            spec.setdefault("analysis", {})["_max_iterations"] = val
        except ValueError:
            pass

    elif param == "nlgeom":
        spec.setdefault("analysis", {})["nlgeom"] = suggested_str.upper() in ("ON", "TRUE", "YES")

    elif param == "seed_size":
        if "reduce" in suggested_str.lower():
            current = spec.get("geometry", {}).get("seed_size")
            if current:
                spec["geometry"]["seed_size"] = current * 0.5
        else:
            try:
                spec.setdefault("geometry", {})["seed_size"] = float(suggested_str)
            except ValueError:
                pass

    elif param == "memory":
        spec.setdefault("analysis", {})["memory"] = suggested_str

    elif param == "stabilize":
        if suggested_str.upper().startswith("ON"):
            spec.setdefault("analysis", {})["_stabilize"] = True

    elif param == "contact_stabilization":
        if suggested_str.upper() in ("ON", "TRUE"):
            spec.setdefault("analysis", {})["_contact_stabilization"] = True

    elif param == "output_frequency":
        try:
            val = int(suggested_str.split()[1]) if "every" in suggested_str else int(suggested_str)
            spec.setdefault("analysis", {})["_output_frequency"] = val
        except (ValueError, IndexError):
            pass

    elif param == "cpus":
        try:
            spec.setdefault("analysis", {})["cpus"] = int(suggested_str)
        except ValueError:
            pass


def save_repaired_spec(spec: dict, workdir: str | Path, attempt: int) -> Path:
    """Save a repaired spec to disk for the retry attempt."""
    workdir = Path(workdir)
    spec_path = workdir / f"spec_repair_{attempt}.yaml"
    spec_path.write_text(
        yaml.dump(spec, allow_unicode=True, default_flow_style=False),
        encoding="utf-8",
    )
    return spec_path


def can_retry(diagnosis: dict) -> bool:
    """Check if the diagnosis recommends retrying."""
    return (
        diagnosis.get("retry_recommended", False) and
        diagnosis.get("severity") != "FATAL"
    )
