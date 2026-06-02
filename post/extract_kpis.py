"""
extract_kpis.py
---------------
Tool: extract_kpis(odb_path, kpi_spec) -> {kpis}

Extracts KPIs from an Abaqus .odb file using odbAccess.
Designed to run under: abaqus python post/extract_kpis.py -- <odb_path> <kpi_spec.json>

This script runs INSIDE the Abaqus Python runtime so only stdlib + Abaqus modules
are available. The outer agent calls it via subprocess.
"""

from __future__ import print_function

import json
import sys

try:
    from pathlib import Path
except ImportError:
    Path = None  # Py2 (Abaqus runtime); use os.path instead

# ---------------------------------------------------------------------------
# Outer-agent API (subprocess caller)
# ---------------------------------------------------------------------------

def extract_kpis(odb_path, kpi_spec, workdir=None):
    """
    Invoke 'abaqus python' to extract KPIs from the ODB.

    Called from the outer Python environment (orchestrator, tests, etc.).

    Returns
    -------
    dict:
        kpis      : dict  - {kpi_name: value}
        errors    : list  - any extraction errors
        odb_path  : str
    """
    import subprocess

    odb_path = Path(odb_path).resolve()
    workdir  = Path(workdir) if workdir else odb_path.parent

    # Write kpi_spec to temp file for passing to abaqus python
    kpi_spec_file = workdir / "_kpi_spec.json"
    kpi_spec_file.write_text(json.dumps(kpi_spec), encoding="utf-8")

    result_file = workdir / "_kpi_result.json"
    this_script = Path(__file__).resolve()

    from tools.abaqus_cmd import get_abaqus_cmd
    cmd = [
        get_abaqus_cmd(), "python", str(this_script),
        "--", str(odb_path), str(kpi_spec_file), str(result_file),
    ]

    try:
        proc = subprocess.run(
            cmd,
            cwd=str(workdir),
            capture_output=True,
            text=True, errors='replace', encoding='utf-8',
            timeout=300,
        )
    except FileNotFoundError:
        return {
            "kpis": {},
            "errors": ["'abaqus' not found in PATH"],
            "odb_path": str(odb_path),
        }
    except subprocess.TimeoutExpired:
        return {
            "kpis": {},
            "errors": ["KPI extraction timed out after 300s"],
            "odb_path": str(odb_path),
        }

    if result_file.exists():
        try:
            return json.loads(result_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass

    return {
        "kpis": {},
        "errors": [proc.stderr[-2000:] or "No result file produced"],
        "odb_path": str(odb_path),
    }


# ---------------------------------------------------------------------------
# Abaqus-runtime inner script
# (runs INSIDE abaqus python; only stdlib + Abaqus available)
# ---------------------------------------------------------------------------

def _inner_main():
    """Entry point when executed via 'abaqus python extract_kpis.py'."""
    # Arguments passed after '--' by the outer caller
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    if len(args) < 3:
        print("Usage: abaqus python extract_kpis.py -- <odb> <kpi_spec.json> <result.json>")
        sys.exit(1)

    odb_path      = args[0]
    kpi_spec_path = args[1]
    result_path   = args[2]

    with open(kpi_spec_path, "r") as f:
        kpi_spec = json.load(f)

    result = {"kpis": {}, "errors": [], "odb_path": odb_path}

    try:
        import odbAccess  # only available in Abaqus Python runtime

        # Check/upgrade ODB if needed
        if odbAccess.isUpgradeRequiredForOdb(upgradeRequiredOdbPath=odb_path):
            upgraded = odb_path.replace(".odb", "_upgraded.odb")
            odbAccess.upgradeOdb(existingOdbPath=odb_path, upgradedOdbPath=upgraded)
            odb_path = upgraded
            result["odb_upgraded"] = True

        odb = odbAccess.openOdb(path=odb_path, readOnly=True)

        for kpi in kpi_spec:
            try:
                value = _extract_single_kpi(odb, kpi)
                result["kpis"][kpi["name"]] = value
            except Exception as e:
                result["errors"].append("{}: {}".format(kpi['name'], str(e)))

        odb.close()

    except ImportError:
        result["errors"].append("odbAccess not available - run via 'abaqus python'")
    except Exception as e:
        result["errors"].append("ODB open failed: {}".format(str(e)))

    with open(result_path, "w") as f:
        json.dump(result, f, indent=2, default=lambda o: float(o) if hasattr(o, '__float__') else str(o))

    print("KPI_RESULT_WRITTEN: " + result_path)


def _extract_single_kpi(odb, kpi):
    """Extract a single KPI from an open ODB object."""
    kpi_type = kpi.get("type", "")
    step = _select_step(odb, kpi)
    frame = _select_frame(step, kpi)

    if kpi_type == "nodal_displacement":
        component = str(kpi.get("component", "U2")).upper()
        field = frame.fieldOutputs["U"]
        location = kpi.get("location", "")
        subset = _subset_field(odb, field, location, "node")
        comp_idx = _component_index(component, 1)
        vals = [v.data[comp_idx] for v in subset.values]
        return _reduce_values(vals, kpi.get("reducer"), "min")

    elif kpi_type == "field_max":
        component = str(kpi.get("component", "")).upper() or None
        # Auto-detect var_name from component prefix unless explicit
        if "field_variable" in kpi:
            var_name = str(kpi["field_variable"])
        elif component and component[0] == "U":
            var_name = "U"
        elif component and component[0] == "S":
            var_name = "S"
        elif component and component[:2] == "RF":
            var_name = "RF"
        elif str(kpi.get("name", "")).upper().startswith("PEEQ"):
            var_name = "PEEQ"
            component = None
        else:
            var_name = "S"
        if "MISES" in kpi.get("name", "").upper():
            var_name = "S"
        if var_name not in frame.fieldOutputs:
            raise KeyError("Field {} not in frame".format(repr(var_name)))
        field = frame.fieldOutputs[var_name]
        field = _subset_field(odb, field, kpi.get("location", ""), "element")
        invariant = str(kpi.get("invariant", "")).upper()
        if invariant == "MISES" or "MISES" in kpi.get("name", "").upper():
            try:
                from abaqusConstants import ELEMENT_NODAL
                nodal_field = field.getSubset(position=ELEMENT_NODAL)
                vals = [v.mises for v in nodal_field.values if hasattr(v, "mises")]
            except Exception:
                vals = [v.mises for v in field.values if hasattr(v, "mises")]
        elif var_name in ("PEEQ", "ALLPD", "ALLIE", "ALLKE"):
            # scalar field, .data is a single float
            vals = [v.data for v in field.values]
        elif component:
            comp_idx = _component_index(component, 0)
            vals = [v.data[comp_idx] for v in field.values]
        else:
            vals = [v.magnitude for v in field.values if hasattr(v, "magnitude")]
        return _reduce_values(vals, kpi.get("reducer"), "max")

    elif kpi_type == "field_min":
        component = str(kpi.get("component", "U3")).upper()
        if "field_variable" in kpi:
            var_name = str(kpi["field_variable"])
        elif component and component[0] == "U":
            var_name = "U"
        elif component and component[0] == "S":
            var_name = "S"
        elif component and component[:2] == "RF":
            var_name = "RF"
        else:
            var_name = "U"
        if var_name not in frame.fieldOutputs:
            raise KeyError("Field {} not in frame".format(repr(var_name)))
        field = frame.fieldOutputs[var_name]
        field = _subset_field(odb, field, kpi.get("location", ""), "node")
        comp_idx = _component_index(component, 2)
        vals = [v.data[comp_idx] for v in field.values]
        return _reduce_values(vals, kpi.get("reducer"), "min")

    elif kpi_type == "reaction_force_max":
        component = str(kpi.get("component", "RF3")).upper()
        if "RF" not in frame.fieldOutputs:
            raise KeyError("RF not in frame fieldOutputs")
        field = frame.fieldOutputs["RF"]
        field = _subset_field(odb, field, kpi.get("location", ""), "node")
        comp_idx = _component_index(component, 2)
        vals = [abs(v.data[comp_idx]) for v in field.values]
        return _reduce_values(vals, kpi.get("reducer"), "max")

    elif kpi_type == "history_output_max":
        # Find the named history variable in any history region.
        var = kpi.get("variable", "ALLPD")
        vals = []
        for region_key, region in step.historyRegions.items():
            for hkey, hout in region.historyOutputs.items():
                if hkey.upper() == var.upper():
                    for t, v in hout.data:
                        vals.append(v)
        return _reduce_values(vals, kpi.get("reducer"), "abs_max")

    elif kpi_type == "eigenfrequency":
        mode_str  = kpi.get("location", "mode_1")
        mode_n    = int(mode_str.split("_")[-1])
        if mode_n < len(step.frames):
            frq_frame = step.frames[mode_n]
            return frq_frame.frequency
        raise IndexError("Mode {} not available (only {} modes)".format(mode_n, len(step.frames) - 1))

    elif kpi_type == "derived_stress_concentration":
        # Kt = max_mises_at_hole / nominal_stress
        if "S" not in frame.fieldOutputs:
            raise KeyError("S not in frame")
        field = frame.fieldOutputs["S"]
        location = kpi.get("location", "")
        subset = _subset_field(odb, field, location, "element")
        vals = [v.mises for v in subset.values if hasattr(v, "mises")]
        return _reduce_values(vals, kpi.get("reducer"), "max")

    else:
        raise ValueError("Unknown kpi type: {}".format(repr(kpi_type)))


def _select_step(odb, kpi):
    step_name = kpi.get("step") or kpi.get("step_name")
    keys = list(odb.steps.keys())
    if step_name:
        if step_name in odb.steps:
            return odb.steps[step_name]
        if isinstance(step_name, int):
            return odb.steps[keys[step_name]]
        step_text = str(step_name)
        if step_text.isdigit():
            return odb.steps[keys[int(step_text)]]
        raise KeyError("Step {} not found".format(repr(step_name)))
    return odb.steps[keys[-1]]


def _select_frame(step, kpi):
    frame_spec = kpi.get("frame", "last")
    if frame_spec in (None, "", "last"):
        return step.frames[-1]
    if frame_spec == "first":
        return step.frames[0]
    if isinstance(frame_spec, int):
        return step.frames[frame_spec]
    frame_text = str(frame_spec)
    if frame_text.isdigit():
        return step.frames[int(frame_text)]
    if "_" in frame_text and frame_text.rsplit("_", 1)[-1].isdigit():
        return step.frames[int(frame_text.rsplit("_", 1)[-1])]
    raise ValueError("Unsupported frame selector: {}".format(repr(frame_spec)))


def _subset_field(odb, field, location, preferred):
    region = _resolve_region(odb, location, preferred)
    if region is None:
        return field
    return field.getSubset(region=region)


def _resolve_region(odb, location, preferred):
    if not location:
        return None
    key = str(location).split(":", 1)[-1].upper()
    assembly = odb.rootAssembly
    candidates = []
    if preferred == "node":
        candidates = [getattr(assembly, "nodeSets", {}), getattr(assembly, "elementSets", {})]
    elif preferred == "element":
        candidates = [getattr(assembly, "elementSets", {}), getattr(assembly, "nodeSets", {})]
    else:
        candidates = [getattr(assembly, "elementSets", {}), getattr(assembly, "nodeSets", {})]
    candidates.append(getattr(assembly, "surfaces", {}))
    for mapping in candidates:
        if key in mapping:
            return mapping[key]
    return None


def _component_index(component, default):
    return {
        "U1": 0, "U2": 1, "U3": 2,
        "S11": 0, "S22": 1, "S33": 2,
        "RF1": 0, "RF2": 1, "RF3": 2,
    }.get(str(component).upper(), default)


def _reduce_values(vals, reducer, default_reducer):
    if not vals:
        return 0.0
    mode = str(reducer or default_reducer).lower()
    if mode == "min":
        return min(vals)
    if mode == "last":
        return vals[-1]
    if mode == "abs_max":
        return max(vals, key=lambda value: abs(value))
    return max(vals)


# ---------------------------------------------------------------------------
# Entry point detection
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # When called via 'abaqus python extract_kpis.py -- ...'
    _inner_main()
