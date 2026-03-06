"""
coupled_outputs.py
------------------
KPI extractors for multi-physics coupled analysis results.

Extracts temperature, heat flux, and thermal gradient KPIs
from Abaqus ODB files containing coupled analysis results.
"""

from __future__ import annotations


def extract_temperature_max(odb, kpi: dict) -> float:
    """
    Extract maximum temperature from coupled analysis ODB.

    KPI spec:
        type: temperature_max
        location: optional node set name
    """
    step_key = list(odb.steps.keys())[-1]
    frame = odb.steps[step_key].frames[-1]

    # Temperature field: NT11 or TEMP
    for field_name in ("NT11", "TEMP", "NT"):
        if field_name in frame.fieldOutputs:
            field = frame.fieldOutputs[field_name]
            break
    else:
        raise KeyError("No temperature field (NT11/TEMP/NT) in frame outputs")

    location = kpi.get("location", "")
    if location and location.upper() in odb.rootAssembly.nodeSets:
        field = field.getSubset(region=odb.rootAssembly.nodeSets[location.upper()])

    vals = [v.data if hasattr(v, 'data') and not hasattr(v.data, '__len__') else v.data[0] for v in field.values]
    return max(vals) if vals else 0.0


def extract_heat_flux_max(odb, kpi: dict) -> float:
    """
    Extract maximum heat flux magnitude from coupled analysis ODB.

    KPI spec:
        type: heat_flux_max
        component: optional (HFL1, HFL2, HFL3, or magnitude)
        location: optional node set name
    """
    step_key = list(odb.steps.keys())[-1]
    frame = odb.steps[step_key].frames[-1]

    if "HFL" not in frame.fieldOutputs:
        raise KeyError("HFL not in frame field outputs")

    field = frame.fieldOutputs["HFL"]
    location = kpi.get("location", "")
    if location and location.upper() in odb.rootAssembly.nodeSets:
        field = field.getSubset(region=odb.rootAssembly.nodeSets[location.upper()])

    component = kpi.get("component", "magnitude")
    if component == "magnitude":
        vals = [v.magnitude for v in field.values if hasattr(v, "magnitude")]
    else:
        comp_idx = {"HFL1": 0, "HFL2": 1, "HFL3": 2}.get(component, 0)
        vals = [abs(v.data[comp_idx]) for v in field.values]

    return max(vals) if vals else 0.0


def extract_thermal_gradient(odb, kpi: dict) -> float:
    """
    Extract temperature gradient (max T - min T) from coupled analysis.

    KPI spec:
        type: thermal_gradient
        location: optional node set name
    """
    step_key = list(odb.steps.keys())[-1]
    frame = odb.steps[step_key].frames[-1]

    for field_name in ("NT11", "TEMP", "NT"):
        if field_name in frame.fieldOutputs:
            field = frame.fieldOutputs[field_name]
            break
    else:
        raise KeyError("No temperature field in frame outputs")

    location = kpi.get("location", "")
    if location and location.upper() in odb.rootAssembly.nodeSets:
        field = field.getSubset(region=odb.rootAssembly.nodeSets[location.upper()])

    vals = [v.data if hasattr(v, 'data') and not hasattr(v.data, '__len__') else v.data[0] for v in field.values]
    if not vals:
        return 0.0
    return max(vals) - min(vals)
