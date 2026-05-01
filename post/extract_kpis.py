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
    import shutil
    import subprocess

    odb_path = Path(odb_path).resolve()
    workdir  = Path(workdir) if workdir else odb_path.parent

    # Write kpi_spec to temp file for passing to abaqus python
    kpi_spec_file = workdir / "_kpi_spec.json"
    kpi_spec_file.write_text(json.dumps(kpi_spec), encoding="utf-8")

    result_file = workdir / "_kpi_result.json"
    this_script = Path(__file__).resolve()

    cmd = [
        (shutil.which("abaqus") or "abaqus"), "python", str(this_script),
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
    step_key  = list(odb.steps.keys())[-1]   # default: last step
    step      = odb.steps[step_key]
    frame     = step.frames[-1]              # default: last frame

    if kpi_type == "nodal_displacement":
        component = kpi.get("component", "U2")
        field = frame.fieldOutputs["U"]
        location = kpi.get("location", "")
        if location and location in odb.rootAssembly.nodeSets:
            subset = field.getSubset(region=odb.rootAssembly.nodeSets[location.upper()])
        else:
            subset = field
        comp_idx = {"U1": 0, "U2": 1, "U3": 2}.get(component, 1)
        vals = [v.data[comp_idx] for v in subset.values]
        return min(vals) if vals else 0.0

    elif kpi_type == "field_max":
        var_name  = kpi.get("field_variable", "S")
        component = kpi.get("component", None)
        if "MISES" in kpi.get("name", "").upper():
            var_name = "S"
        if var_name not in frame.fieldOutputs:
            raise KeyError("Field {} not in frame".format(repr(var_name)))
        field = frame.fieldOutputs[var_name]
        if "MISES" in kpi.get("name", "").upper():
            vals = [v.mises for v in field.values if hasattr(v, "mises")]
        elif component:
            comp_idx = {"U1": 0, "U2": 1, "U3": 2, "S11": 0, "S22": 1, "S33": 2}.get(component, 0)
            vals = [v.data[comp_idx] for v in field.values]
        else:
            vals = [v.magnitude for v in field.values if hasattr(v, "magnitude")]
        return max(vals) if vals else 0.0

    elif kpi_type == "field_min":
        var_name  = kpi.get("field_variable", "U")
        component = kpi.get("component", "U3")
        if var_name not in frame.fieldOutputs:
            raise KeyError("Field {} not in frame".format(repr(var_name)))
        field = frame.fieldOutputs[var_name]
        comp_idx = {"U1": 0, "U2": 1, "U3": 2}.get(component, 2)
        vals = [v.data[comp_idx] for v in field.values]
        return min(vals) if vals else 0.0

    elif kpi_type == "reaction_force_max":
        component = kpi.get("component", "RF3")
        if "RF" not in frame.fieldOutputs:
            raise KeyError("RF not in frame fieldOutputs")
        field = frame.fieldOutputs["RF"]
        comp_idx = {"RF1": 0, "RF2": 1, "RF3": 2}.get(component, 2)
        vals = [abs(v.data[comp_idx]) for v in field.values]
        return max(vals) if vals else 0.0

    elif kpi_type == "eigenfrequency":
        mode_str  = kpi.get("location", "mode_1")
        mode_idx  = int(mode_str.split("_")[-1]) - 1
        if mode_idx < len(step.frames):
            frq_frame = step.frames[mode_idx]
            return frq_frame.frequency
        raise IndexError("Mode {} not available (only {} modes)".format(mode_idx+1, len(step.frames)))

    elif kpi_type == "derived_stress_concentration":
        # Kt = max_mises_at_hole / nominal_stress
        if "S" not in frame.fieldOutputs:
            raise KeyError("S not in frame")
        field = frame.fieldOutputs["S"]
        location = kpi.get("location", "")
        if location and location.upper() in odb.rootAssembly.elementSets:
            subset = field.getSubset(region=odb.rootAssembly.elementSets[location.upper()])
        else:
            subset = field
        vals = [v.mises for v in subset.values if hasattr(v, "mises")]
        return max(vals) if vals else 0.0

    else:
        raise ValueError("Unknown kpi type: {}".format(repr(kpi_type)))


# ---------------------------------------------------------------------------
# Entry point detection
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # When called via 'abaqus python extract_kpis.py -- ...'
    _inner_main()
