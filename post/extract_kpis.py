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
import re
import sys

try:
    from pathlib import Path
except ImportError:
    Path = None  # Py2 (Abaqus runtime); use os.path instead

NODE_SET_ALIASES = {
    "fixed_face": "FIXED_END",
    "load_face": "LOAD_END",
    "tip": "TIP_NODES",
    "tip_center": "TIP_NODES",
    "top_face": "LOAD_END",
}

ELEMENT_SET_ALIASES = {
    "fixed_face": "FIXED_END",
    "hole_edge": "HOLE_EDGE",
    "hole_edge_set": "HOLE_EDGE",
    "load_face": "LOAD_END",
    "top_face": "LOAD_END",
    "whole_model": "ALL",
}

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
            # Abaqus prints Windows locale messages in the system codepage.
            text=True, encoding="utf-8", errors="replace",
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


_J_CONTOUR = re.compile(r"^J at (.+)_Contour_(\d+)$", re.IGNORECASE)


def _j_contours(step):
    """Every contour integral in this step: label -> [J by contour number].

    The history key Abaqus writes is
    ``J at <request>_<crack>_<tip set>_Contour_<n>`` -- measured on Abaqus 2021,
    a request named `J` on a crack named `Crack` with tip set `TIP` came back as
    `J at J_CRACK_TIP_Contour_1`. Nothing here reconstructs that name; the
    contour suffix is stripped and whatever precedes it is the label a KPI's
    `location` is matched against.
    """
    found = {}
    for region in step.historyRegions.values():
        for hkey, hout in region.historyOutputs.items():
            hit = _J_CONTOUR.match(str(hkey))
            if hit is None:
                continue
            label, number = hit.group(1), int(hit.group(2))
            data = list(hout.data)
            if not data:
                continue
            found.setdefault(label, {})[number] = float(data[-1][1])
    return dict((label, [by_n[n] for n in sorted(by_n)])
                for label, by_n in found.items())


def _contour_integral_j(step, kpi):
    """The J-integral at a crack tip, refused rather than reported when wrong.

    Every other `expect:` in this dialect is checked while the model is being
    built. This one cannot be: J does not exist until the solve is over, and a
    contour integral produces a number for any crack you hand it, correct or
    not. So the checks live here, and they are the three things measured on
    Abaqus 2021 (artifacts/probe_crack) on a single-edge-notched plate,
    a/W = 0.2, plane strain, against the handbook J = 2.5576 N/mm:

      correct        J = 2.4685, 2.5013, 2.5032, 2.5033, 2.5033, 2.5033
                     outermost -2.12% from handbook; contours 2-6 agree to
                     within 7.7e-4 of their mean.

      no seam        J = -1.4e-16, -3.8e-16, -2.1e-15, -1.6e-15, -4.2e-15,
                     -1.3e-14. The crack line was never separated, so there is
                     no crack -- and the job COMPLETED with no warning. Note
                     what this is NOT: clean zeros. It is round-off either side
                     of nothing, and every value is NEGATIVE, so an `== 0.0`
                     test lets these reach the sign check below and reports a
                     missing seam as a reversed q vector. Hence the tolerance,
                     and hence its position first.

      q reversed     J = -2.5033, the right magnitude with the wrong sign, job
                     COMPLETED, no warning. THIS is why path-independence alone
                     is not enough: its contours agree to 7.7e-4, exactly as
                     well as the correct model's. A negative energy release
                     rate is meaningless, and the sign is the only tell.

    Contour 1 is excluded from the convergence test on purpose: it hugs the
    crack-tip singularity and is expected to differ (2.4685 against 2.5033).
    Including it would fail every correct model.
    """
    contours = _j_contours(step)
    if not contours:
        raise KeyError(
            "no contour-integral history in this step. A `contour_integral_j` "
            "KPI needs a history output request carrying "
            "contourIntegral=<name> and contourType=J_INTEGRAL; without one "
            "the odb has no J to read.")

    location = str(kpi.get("location", "") or "").strip()
    if location:
        hits = [label for label in contours
                if location.upper() in label.upper()]
        if not hits:
            raise KeyError(
                "location %r matches no contour integral (this step has: %s)"
                % (location, ", ".join(sorted(contours))))
        if len(hits) > 1:
            raise KeyError(
                "location %r matches %d contour integrals (%s). Name one."
                % (location, len(hits), ", ".join(sorted(hits))))
        label = hits[0]
    elif len(contours) > 1:
        raise KeyError(
            "this step has %d contour integrals (%s) and the KPI names none. "
            "Add `location` -- reducing across cracks would average two "
            "different crack tips into one number."
            % (len(contours), ", ".join(sorted(contours))))
    else:
        label = list(contours)[0]

    values = contours[label]
    outer = values[1:] if len(values) > 1 else values

    # Tested BEFORE the sign, and not with `== 0.0`. Measured on Abaqus 2021,
    # an unseparated crack does not come back as clean zeros: it comes back as
    # -1.4e-16, -3.8e-16, -2.1e-15 ... round-off either side of nothing. With
    # an equality test those fall through to the sign check below and a missing
    # seam is reported as a reversed q vector -- a confident, wrong diagnosis,
    # which is worse than none. The gate caught exactly that.
    #
    # The default floor is 1e-12: two orders above the largest round-off
    # measured (1.3e-14) and far below any J a real model produces. It is a
    # statement about double-precision noise, not about physics, so a unit
    # system where a real J is genuinely that small can override it.
    zero_tol = float(kpi.get("zero_tolerance", 1e-12))
    if all(abs(v) <= zero_tol for v in values):
        raise ValueError(
            "contour integral %r came back at %s on all %d contours, which is "
            "nothing (below %g). Measured on Abaqus 2021: that is what a crack "
            "whose line was never SEPARATED gives -- the seam is missing, so "
            "the 'crack' runs through continuous material. The job completes "
            "and warns about nothing. Assign a seam to the crack line, or "
            "check that the tip is on it."
            % (label, ", ".join("%.3g" % v for v in values), len(values),
               zero_tol))

    if any(v < 0.0 for v in outer):
        raise ValueError(
            "contour integral %r is negative (%s). J is an energy release rate "
            "and cannot be. Measured on Abaqus 2021, an extension direction "
            "pointing back along the crack instead of ahead of it gives "
            "exactly the right magnitude with the wrong sign, completes, and "
            "warns about nothing -- and its contours are as path-independent "
            "as the correct model's, so nothing but the sign catches it. "
            "Reverse the q vector." % (label, ", ".join("%g" % v for v in outer)))

    mean = sum(outer) / float(len(outer))
    tol = float(kpi.get("contour_tolerance", 0.05))
    spread = (max(outer) - min(outer)) / abs(mean) if mean else float("inf")
    if spread > tol:
        raise ValueError(
            "contour integral %r is not path-independent: contours 2..%d "
            "spread %.3g of their mean, over the %.3g allowed. A converged J "
            "does not depend on the contour -- measured on Abaqus 2021 a "
            "correct model gives 7.7e-04. Refine the mesh at the tip or ask "
            "for more contours. (Contour 1 is excluded; it hugs the "
            "singularity and is expected to differ.)"
            % (label, len(values), spread, tol))

    # The outermost contour, which is the converged one. Not a mean: the inner
    # contours are the ones still contaminated, and averaging them in would
    # drag the answer toward the singularity.
    return outer[-1]


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
        comp_idx = _component_index(component)
        vals = [v.data[comp_idx] for v in subset.values]
        return _reduce_values(vals, kpi.get("reducer"), "min")

    elif kpi_type == "field_max":
        component = str(kpi.get("component", "")).upper() or None
        name_upper = str(kpi.get("name", "")).upper()
        declared_var = "field_variable" in kpi
        # Auto-detect var_name from component prefix unless explicit
        if declared_var:
            var_name = str(kpi["field_variable"])
        elif component and component[0] == "U":
            var_name = "U"
        elif component and component[0] == "S":
            var_name = "S"
        elif component and component[:2] == "RF":
            var_name = "RF"
        elif name_upper.startswith("PEEQ"):
            var_name = "PEEQ"
            component = None
        else:
            # A MISES_* name lands here and gets "S", which is what the old
            # unconditional override produced -- except that override also ran
            # on top of an explicit field_variable, so a KPI declaring PEEQ
            # and merely NAMED "MISES_UTILISATION" read stress instead.
            var_name = "S"
        if var_name not in frame.fieldOutputs:
            raise KeyError("Field {} not in frame".format(repr(var_name)))
        field = frame.fieldOutputs[var_name]
        invariant = _resolve_invariant(kpi, name_upper, component,
                                       declared_var, var_name)
        if invariant:
            attr = _INVARIANT_ATTR[invariant]
            field = _at_element_nodal(field, var_name)
            field = _subset_field(odb, field, kpi.get("location", ""), "element")
            vals = [getattr(v, attr) for v in field.values if hasattr(v, attr)]
            if field.values and not vals:
                raise KeyError(
                    "invariant %s is not carried by the values of field %r "
                    "(a scalar or vector field has no tensor invariants)"
                    % (invariant, var_name))
        elif var_name in _SCALAR_FIELDS:
            field = _subset_field(odb, field, kpi.get("location", ""), "element")
            # scalar field, .data is a single float
            vals = [v.data for v in field.values]
        elif component:
            field = _at_element_nodal(field, var_name)
            field = _subset_field(odb, field, kpi.get("location", ""),
                                  _preferred_kind(var_name))
            comp_idx = _component_index(component)
            vals = [v.data[comp_idx] for v in field.values]
        else:
            field = _subset_field(odb, field, kpi.get("location", ""),
                                  _preferred_kind(var_name))
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
        # Same position rule as field_max: a minimum principal stress at the
        # integration points is not the same quantity as one at the nodes, and
        # a spec that reads S22 min and S22 max has to get both from one place.
        field = _at_element_nodal(field, var_name)
        # By variable, not hardcoded "node": var_name can be S here, and a
        # stress field subset by a node set selects zero values.
        field = _subset_field(odb, field, kpi.get("location", ""),
                              _preferred_kind(var_name))
        comp_idx = _component_index(component)
        vals = [v.data[comp_idx] for v in field.values]
        return _reduce_values(vals, kpi.get("reducer"), "min")

    elif kpi_type == "reaction_force_max":
        component = str(kpi.get("component", "RF3")).upper()
        if "RF" not in frame.fieldOutputs:
            raise KeyError("RF not in frame fieldOutputs")
        field = frame.fieldOutputs["RF"]
        field = _subset_field(odb, field, kpi.get("location", ""), "node")
        comp_idx = _component_index(component)
        # Signed when summing, magnitude otherwise. abs() per node before a sum
        # would add the two halves of a self-equilibrating set instead of
        # cancelling them, and report a force where there is none.
        if str(kpi.get("reducer", "")).lower() == "sum":
            vals = [v.data[comp_idx] for v in field.values]
        else:
            vals = [abs(v.data[comp_idx]) for v in field.values]
        return _reduce_values(vals, kpi.get("reducer"), "max")

    elif kpi_type == "history_output_max":
        # Find the named history variable, in the requested region.
        #
        # `location` used to be read by nobody here: the loop swept every
        # history region and reduced them together. Measured on a fake with
        # the roof node peaking at +10 and a base node at -500, asking for the
        # roof with reducer abs_max returned -500 -- the right variable from
        # the wrong point, with no error.
        #
        # Absent location still means "every region", because three frozen
        # KPIs (blast_plate ALLPD_MAX, steel_frame_blast ALLPD_MAX and
        # U2_ROOF_PEAK) carry no location and whole-model energies genuinely
        # live in one assembly-wide region.
        var = kpi.get("variable", "ALLPD")
        location = str(kpi.get("location", "") or "").strip()
        vals = []
        matched = []
        available = []
        for region_key, region in step.historyRegions.items():
            available.append(str(region_key))
            if location and not _history_region_matches(region_key, region,
                                                        location):
                continue
            for hkey, hout in region.historyOutputs.items():
                if hkey.upper() == var.upper():
                    matched.append(str(region_key))
                    for t, v in hout.data:
                        vals.append(v)
        if location and not matched:
            raise KeyError(
                "location %r matches no history region carrying %r "
                "(regions in this step: %s)"
                % (location, var, ", ".join(sorted(available)) or "<none>"))
        return _reduce_values(vals, kpi.get("reducer"), "abs_max")

    elif kpi_type == "contour_integral_j":
        return _contour_integral_j(step, kpi)

    elif kpi_type == "eigenfrequency":
        mode_str  = kpi.get("location", "mode_1")
        mode_n    = int(mode_str.split("_")[-1])
        mode_frames = step.frames
        # Real frequency ODBs carry frame.mode; match it exactly. Positional
        # fallback must skip a leading base-state frame (frequency 0/None),
        # otherwise mode_1 silently reads 0 Hz.
        for frq_frame in mode_frames:
            if getattr(frq_frame, "mode", None) == mode_n:
                return frq_frame.frequency
        mode_idx = mode_n - 1
        if len(mode_frames) > 0 and not getattr(mode_frames[0], "frequency", None):
            mode_idx = mode_n
        if 0 <= mode_idx < len(mode_frames):
            return mode_frames[mode_idx].frequency
        raise IndexError("Mode {} not available ({} frames)".format(mode_n, len(mode_frames)))

    elif kpi_type == "eigenvalue":
        # A *BUCKLE step's answer is a load MULTIPLIER on the reference load,
        # and it is not where a frequency is. Measured on Abaqus 2021
        # (artifacts/probe_job/probe5.py), on a fixed-free column whose Euler
        # load is 10794.88 N under a 1 N reference load:
        #
        #   frame.mode        1, 2, 3, 4   (the base state is mode 0)
        #   frame.frequency   None         <- so the eigenfrequency KPI's
        #                                     positional fallback would read
        #                                     nothing here and say so
        #   frame.frameValue  1.0 .. 4.0   <- the ORDINAL, not the eigenvalue
        #   frame.description 'Mode         1: EigenValue =   10785.'
        #
        # so the number exists in exactly one place and it is a string.
        # step.historyRegions is EMPTY for this procedure, and the .dat prints
        # the same 5 significant figures, so this is not a parsing shortcut
        # taken over a numeric API -- there is no numeric API to take.
        mode_str = kpi.get("location", "mode_1")
        mode_n = int(str(mode_str).split("_")[-1])
        for buckle_frame in step.frames:
            if getattr(buckle_frame, "mode", None) == mode_n:
                return _eigenvalue_of(buckle_frame, mode_n)
        modes = [getattr(f, "mode", None) for f in step.frames]
        raise IndexError(
            "mode {} is not in this step. Modes present: {}. A *BUCKLE step "
            "numbers the base state 0 and the eigenmodes from 1, so mode_1 is "
            "the first buckling mode.".format(mode_n, modes))

    elif kpi_type == "derived_stress_concentration":
        # WHAT THIS RETURNS: a STRESS, in the model's stress unit. Not a
        # concentration factor. There is no division by a nominal stress here
        # and there never was -- the comment that used to sit on this line
        # read `Kt = max_mises_at_hole / nominal_stress` and described a
        # division the code does not do, which is how the shipped plate_hole
        # case came to carry a `note` promising "analytical ~3.0" beside a KPI
        # that returns ~300 MPa.
        #
        # It is left as it is on purpose (#32): the name and the note live in
        # cases/plate_hole/spec.yaml, run_id = sha256(spec), and editing either
        # would invalidate a frozen Abaqus baseline that cannot be recomputed.
        # The behaviour is pinned by tests/test_scf_returns_a_stress.py so that
        # nobody "fixes" it into a ratio without noticing what that costs.
        #
        # It differs from `field_max` in one way only, and it is not the
        # arithmetic: this branch does not call `_at_element_nodal`, so the
        # value comes back at the INTEGRATION POINT while `field_max` returns
        # the unaveraged extrapolation to the element nodes. Measured on this
        # very plate, those two readings of the same peak are 8.2% apart. So
        # `SCF` is not `MISES_HOLE_EDGE` in different units either -- dividing
        # it by the nominal stress by hand does not reproduce the Kt the note
        # promises, and the shortfall is a position, not a rounding.
        if "S" not in frame.fieldOutputs:
            raise KeyError("S not in frame")
        field = frame.fieldOutputs["S"]
        location = kpi.get("location", "")
        subset = _subset_field(odb, field, location, "element")
        vals = [v.mises for v in subset.values if hasattr(v, "mises")]
        return _reduce_values(vals, kpi.get("reducer"), "max")

    else:
        raise ValueError("Unknown kpi type: {}".format(repr(kpi_type)))


def _eigenvalue_of(frame, mode_n):
    """The buckling load multiplier, read out of the only place it exists.

    Abaqus 2021 writes it as text: 'Mode         1: EigenValue =   10785.'
    Five significant figures, and the .dat table prints exactly the same five,
    so this ceiling is Abaqus's rather than this parser's -- a caller cannot
    get more precision out of a *BUCKLE step from any API. Recorded here
    because a number that looks like a float invites the assumption that it
    carries a float's digits.

    Parsed strictly. A description that does not carry the marker is an error,
    not a fallback: the alternative candidates on the frame are frameValue
    (which is the mode ORDINAL, measured 1.0 for a mode whose eigenvalue is
    10785) and frequency (None), so any silent fallback here would return a
    plausible small integer instead of a buckling load.
    """
    text = str(getattr(frame, "description", ""))
    marker = "EigenValue"
    if marker not in text:
        raise ValueError(
            "mode {} carries no eigenvalue. Abaqus 2021 writes it into the "
            "frame description as 'EigenValue = <number>' and this frame's "
            "description is {!r}. Nothing else on the frame holds it: "
            "frameValue is the mode ordinal and frequency is None for a "
            "*BUCKLE step, so guessing from either would return a number that "
            "is not a buckling load.".format(mode_n, text))
    tail = text.split(marker, 1)[1].lstrip(" =\t")
    number = tail.split()[0] if tail.split() else ""
    try:
        return float(number)
    except ValueError:
        raise ValueError(
            "mode {} has an eigenvalue this parser cannot read: {!r} out of "
            "description {!r}".format(mode_n, number, text))


def _select_step(odb, kpi):
    """Which step a KPI is measured in. Named for preference, numbered 1-based.

    Two things had to be decided here, and both were decided the way that makes
    a wrong answer impossible rather than the way that was already written:

    1. `odb.steps` is an Abaqus Repository, not a dict. `1 in odb.steps` does
       not return False -- it raises "String Expected as dictionary Key". So the
       membership test has to be guarded by the type, or every numeric selector
       dies with a message about dictionary keys that names neither the step nor
       the KPI.

    2. A numeric selector used to index the step list from ZERO, so `step: 1`
       read the SECOND step. On a three-step model that is the whole failure
       mode this project exists to stop: `step: 1` asking for the gravity step
       and getting the clamped one returns a number that is entirely plausible
       and entirely wrong, and only `step: 3` fails loudly (IndexError past the
       end). Nothing in the repository used a numeric selector, so the
       convention was free to be chosen: it is 1-based, because "step 1" means
       the first step in every context an engineer writes it in, and an
       out-of-range number is refused with the actual step names listed.
    """
    # Not `kpi.get("step") or kpi.get("step_name")`. Zero is falsy, so a spec
    # written against the old 0-based convention would fall straight through to
    # "no selector given" and measure the LAST step -- further from what it
    # asked for than the off-by-one it was trying to write.
    step_name = kpi.get("step")
    if step_name is None or step_name == "":
        step_name = kpi.get("step_name")

    keys = list(odb.steps.keys())
    if step_name is None or step_name == "":
        return odb.steps[keys[-1]]

    # `str` is the wrong test in here. This module runs under the Abaqus 2021
    # kernel, which is Python 2.7, and json.load gives back `unicode` -- so
    # isinstance(u"Push", str) is False and every named step would fall through
    # to the numeric branch and be refused. The 2024 kernel is Python 3.10 and
    # has no `unicode` at all, and this file has to read the same in both.
    try:
        _TEXT = (str, unicode)  # noqa: F821 - Python 2.7 kernel
    except NameError:
        _TEXT = (str,)

    # Compared by VALUE against the keys, not `step_name in odb.steps`.
    #
    # The isinstance guard above was already written for the Python 2.7 kernel,
    # but it fixed the type test and not the LOOKUP. odb.steps is an Abaqus
    # Repository and its membership test is type-checked: measured on Abaqus
    # 2021, an ODB holding step 'Buckle' answers `u'Buckle' in odb.steps` with
    # False, so a named step fell through to the numeric branch and was refused
    # with "Step u'Buckle' not found. This odb has 'Buckle'" -- a message that
    # prints the answer immediately next to the question.
    #
    # The KPI spec always arrives through json.load, which yields unicode under
    # 2.7, so this affected EVERY named step. It went unnoticed because every
    # shipped case selects its step by ordinal; the first spec in this
    # repository to write `step: <name>` was the buckling gate.
    if isinstance(step_name, _TEXT):
        for key in keys:
            if key == step_name:
                return odb.steps[key]

    ordinal = None
    if isinstance(step_name, int) and not isinstance(step_name, bool):
        ordinal = step_name
    elif isinstance(step_name, _TEXT) and step_name.isdigit():
        ordinal = int(str(step_name))

    if ordinal is not None:
        if 1 <= ordinal <= len(keys):
            return odb.steps[keys[ordinal - 1]]
        raise KeyError(
            "step {} is out of range: this odb has {} step(s), named {} "
            "(numbering starts at 1)".format(
                ordinal, len(keys), ", ".join(repr(k) for k in keys)))

    raise KeyError("Step {} not found. This odb has {}".format(
        repr(step_name), ", ".join(repr(k) for k in keys)))


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


def _at_element_nodal(field, var_name):
    """Read a stress-like field where the peak actually is.

    Integration points sit INSIDE the element, so an integration-point maximum
    systematically under-reports a surface peak -- which is precisely where a
    stress concentration lives. ELEMENT_NODAL is the unaveraged extrapolation
    to the nodes, and it is what Abaqus/Viewer shows and what an engineer means
    by "the maximum stress".

    This used to be applied on the Mises branch only. Measured on a plate with
    a hole, the same peak read two ways came back as Mises 3.0966 (element
    nodal) and S22 2.8420 (integration point) -- an 8.2% gap between two
    numbers that are the same quantity at a traction-free point. Neither was
    wrong for its position; they simply were not comparable, and nothing said
    so. One helper for both branches is the point: they cannot drift again.

    Position BEFORE region. Chaining getSubset(region=...) and then
    getSubset(position=...) silently drops the region: measured on a real ODB,
    a 20-value hole-edge subset ballooned back to the 2504-value whole model on
    the second call. The narrow except covers only the position change (no
    abaqusConstants outside the kernel, or a field with no ELEMENT_NODAL data);
    a bad region must raise, not fall back to the whole model.
    """
    if str(var_name).upper() not in ("S", "E", "EE", "PE", "NE", "LE"):
        return field
    try:
        from abaqusConstants import ELEMENT_NODAL
        return field.getSubset(position=ELEMENT_NODAL)
    except Exception:
        return field


def _subset_field(odb, field, location, preferred):
    region = _resolve_region(odb, location, preferred)
    if region is None:
        return field
    return field.getSubset(region=region)


def _preferred_kind(var_name):
    """Node sets for nodal fields, element sets for element fields.

    Hardcoding one kind was the quiet half of the location bug: a stress
    field_min passed "node" and a displacement field_max passed "element",
    so once instance sets became resolvable the subset selected zero values.
    """
    return "node" if str(var_name).upper() in ("U", "V", "A", "RF") else "element"


def _resolve_region(odb, location, preferred):
    """Find the ODB region a spec ``location`` names.

    Returns None ONLY when the location legitimately means the whole model
    (empty, or the whole_model/all alias). A location that names a set which
    cannot be found raises KeyError listing what exists - returning the whole
    field instead is how "stress at the hole edge" silently became "max
    stress anywhere", with errors: [].

    Sets live in two places: on rootAssembly, or on an instance. Every model
    this repo builds creates them on the part (runner/build_model.py), so
    they surface on the instance - an assembly-only search finds nothing.
    """
    if not location:
        return None
    raw_key = str(location).split(":", 1)[-1]
    # whole_model is not a set lookup: the unsubsetted field IS the whole
    # model, on every ODB, including ones with no ALL set. Resolving it via
    # an elset alias broke nodal fields (NODE_SET_ALIASES has no entry).
    if raw_key.strip().lower() in ("whole_model", "all"):
        return None
    aliases = NODE_SET_ALIASES if preferred == "node" else ELEMENT_SET_ALIASES
    keys = [raw_key.upper()]
    alias = aliases.get(raw_key.lower())
    if alias:
        keys.append(alias.upper())

    assembly = odb.rootAssembly
    owners = [assembly]
    for inst_name in sorted(getattr(assembly, "instances", {}).keys()):
        owners.append(assembly.instances[inst_name])

    available = []
    surface_hit = False
    for owner in owners:
        if preferred == "node":
            candidates = [getattr(owner, "nodeSets", {}), getattr(owner, "elementSets", {})]
        else:
            candidates = [getattr(owner, "elementSets", {}), getattr(owner, "nodeSets", {})]
        for mapping in candidates:
            for key in keys:
                if key in mapping:
                    return mapping[key]
            for name in mapping.keys():
                if name not in available:
                    available.append(name)
        # Surfaces are SEARCHED but never RETURNED. `getSubset` rejects one --
        # "Surface based region for getSubset is not supported" -- so a surface
        # was never a region this could use; returning it only moved the
        # failure into the Abaqus kernel, where the KPI vanished from
        # result["kpis"] with the error left in stages.extract_kpis.errors and
        # the run still reporting COMPLETED.
        #
        # Still searched, because "not found" is the wrong thing to say: the
        # name is right and the author would go hunting for a typo. What is
        # wrong is the kind of object, and only a search can know that.
        for key in keys:
            if key in getattr(owner, "surfaces", {}):
                surface_hit = True

    if surface_hit:
        raise KeyError(
            "location %r is a SURFACE, and a KPI location has to be a set. "
            "Abaqus cannot take a field subset over a surface (getSubset "
            "answers 'Surface based region for getSubset is not supported'), "
            "so this KPI would be dropped from the results while the run "
            "still reported COMPLETED. Build a set covering the same region "
            "and name that instead. Sets in this ODB: %s"
            % (location, ", ".join(sorted(available)) or "<none>"))

    raise KeyError(
        "location %r not found in ODB (tried %s; available sets: %s)"
        % (location, ", ".join(keys), ", ".join(sorted(available)) or "<none>"))


def _history_region_matches(region_key, region, location):
    """Does this history region answer to the name the spec used.

    Abaqus names them 'Node PART-1-1.7', 'Element PART-1-1.3 Int Point 1',
    'Assembly ASSEMBLY' -- so a substring test on the key is what a spec
    author can actually write. Matching is case-insensitive and also tries
    the region's own `name`, which real ODBs carry and fakes may not.
    """
    wanted = str(location).strip().upper()
    if not wanted:
        return True
    if wanted in str(region_key).upper():
        return True
    name = getattr(region, "name", None)
    if name is not None and wanted in str(name).upper():
        return True
    return False


_COMPONENT_INDEX = {
    "U1": 0, "U2": 1, "U3": 2,
    "S11": 0, "S22": 1, "S33": 2,
    "RF1": 0, "RF2": 1, "RF3": 2,
}


def _component_index(component):
    """Resolve a component name to its index, or refuse.

    This used to be a ``.get(name, default)``. The default was reachable only
    for a name the table did not know, so every unrecognised component came
    back as a real number from the wrong slot: measured, ``S12`` -> 0, which
    is ``S11``; ``E22`` -> 0; ``UR3`` -> 1, which is ``U2``. Worse, the four
    call sites passed three different defaults (1 / 0 / 2 / 2), so the same
    typo produced a different wrong number depending on which KPI type it
    appeared in.

    Refusing here is the whole point: a component name we cannot resolve has
    no safe default, and every default this code used to fall back to returned
    a different wrong number depending on the KPI type.
    """
    key = str(component).upper()
    if key in _COMPONENT_INDEX:
        return _COMPONENT_INDEX[key]
    # An invariant written into `component:` is the one wrong spelling worth
    # naming, because it is the plausible one: MISES is what an engineer calls
    # the number, and it is not a component of anything. Measured -- this
    # exact confusion sat in scripts/run_dropped_input_check.py, where it had
    # worked by accident while the default index still existed.
    if key in _INVARIANT_ATTR:
        raise KeyError(
            "component %r is an invariant, not a component. Write "
            "`invariant: %s` instead; `component:` takes one of %s."
            % (component, key, ", ".join(sorted(_COMPONENT_INDEX))))
    raise KeyError(
        "component %r is not one of %s. This layer will not guess: an "
        "unrecognised name used to resolve to a default index and report a "
        "real number from the wrong slot." % (
            component, ", ".join(sorted(_COMPONENT_INDEX))))


# Every invariant an Abaqus FieldValue carries, mapped to its attribute.
# `invariant:` used to be compared against the single string "MISES", so the
# other names fell through to `.magnitude` -- measured on one value carrying
# all of them, MAX_PRINCIPAL / MIN_PRINCIPAL / TRESCA / PRESS all returned
# 123.456, four different physical quantities collapsed onto one number and
# none of them the one asked for.
_INVARIANT_ATTR = {
    "MISES": "mises",
    "MAX_PRINCIPAL": "maxPrincipal",
    "MID_PRINCIPAL": "midPrincipal",
    "MIN_PRINCIPAL": "minPrincipal",
    "TRESCA": "tresca",
    "PRESS": "press",
    "INV3": "inv3",
}

_SCALAR_FIELDS = ("PEEQ", "ALLPD", "ALLIE", "ALLKE")


def _resolve_invariant(kpi, name_upper, component, declared_var, var_name):
    """Which invariant to read, or None for the component/magnitude paths.

    An explicit `invariant:` wins and is checked against the table. Otherwise
    a KPI whose *name* contains MISES still selects the Mises invariant --
    kept deliberately, because five frozen cases (cantilever,
    cantilever_plastic, plate_hole, two_plate_tie, two_plate_contact) name a
    KPI MISES_* and declare nothing at all. What changed is that the name is
    now a fallback instead of an override: it used to run unconditionally,
    after and on top of an explicit field_variable.
    """
    stated = str(kpi.get("invariant", "")).upper()
    if stated:
        if stated not in _INVARIANT_ATTR:
            raise ValueError(
                "invariant %r is not one of %s" % (
                    kpi.get("invariant"), ", ".join(sorted(_INVARIANT_ATTR))))
        if component:
            raise ValueError(
                "KPI %r gives both invariant %r and component %r. The "
                "component branch used to win silently, so the spec said one "
                "thing and the number was another. Give one." % (
                    kpi.get("name"), kpi.get("invariant"), kpi.get("component")))
        return stated
    if component or declared_var or str(var_name).upper() in _SCALAR_FIELDS:
        return None
    if "MISES" in name_upper:
        return "MISES"
    return None


def _reduce_values(vals, reducer, default_reducer):
    if not vals:
        # An empty selection means the set was wrong, the position was wrong,
        # or the variable is absent. 0.0 here once shipped as a real KPI
        # (steel_frame_blast U2_MAX_LATERAL: 0.0, errors: []) - a fabricated
        # number, which is exactly what this pipeline exists to prevent.
        raise ValueError("no values selected: wrong set name, wrong position, "
                         "or the variable is absent from this ODB")
    mode = str(reducer or default_reducer).lower()
    if mode == "min":
        return min(vals)
    if mode == "max":
        return max(vals)
    if mode == "last":
        return vals[-1]
    if mode == "abs_max":
        return max(vals, key=lambda value: abs(value))
    if mode == "sum":
        # The only honest answer for a reaction force. A prescribed
        # displacement is resisted at every node of the region; the total is
        # the force, and the largest single nodal share is a mesh artefact.
        return sum(vals)
    if mode == "mean":
        return sum(vals) / float(len(vals))
    # NOT `return max(vals)`. That was the catch-all here, so `reducer: "sum"`
    # -- or any typo -- came back as a maximum, with the right units, the right
    # sign and a plausible magnitude. A KPI that silently answers a different
    # question than the one asked is the failure this whole pipeline exists to
    # prevent, so an unknown reducer is fatal and says what it knows.
    raise ValueError(
        "unknown reducer %r; known reducers are max, min, sum, mean, last, "
        "abs_max" % reducer)


# ---------------------------------------------------------------------------
# Entry point detection
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # When called via 'abaqus python extract_kpis.py -- ...'
    _inner_main()
