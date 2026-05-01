"""
build_model.py
--------------
Tool: build_model(spec) -> {workdir, cae_path, inp_path}

Generates a CAE noGUI script from Problem Spec, executes it via
  abaqus cae noGUI=<script> -- <workdir> <spec_path>
and returns the paths to the resulting .cae and .inp files.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

from tools.errors import AbaqusAgentError, ErrorCode

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_model(spec_path: str | Path, workdir: str | Path | None = None) -> dict:
    """
    Build a model from a spec YAML file.

    Returns
    -------
    dict with keys:
        workdir   : Path  - run directory
        cae_path  : Path  - generated .cae file (may not exist for inp-only)
        inp_path  : Path  - generated .inp file
        run_id    : str   - reproducible hash of spec + abaqus_release
    """
    spec_path = Path(spec_path).resolve()
    spec = _load_spec(spec_path)

    run_id = _run_id(spec)
    workdir = Path(workdir) if workdir else spec_path.parent / "runs" / run_id
    workdir.mkdir(parents=True, exist_ok=True)

    inp_path = workdir / f"{spec['meta']['model_name']}.inp"

    # Idempotency: if .inp already exists and is valid, skip re-generation
    if inp_path.exists() and inp_path.stat().st_size > 0:
        return {
            "workdir": workdir,
            "cae_path": workdir / f"{spec['meta']['model_name']}.cae",
            "inp_path": inp_path,
            "run_id": run_id,
            "cached": True,
        }

    # Generate the CAE noGUI script
    script_path = workdir / "build_model_script.py"
    _write_cae_script(spec, script_path, workdir)

    # Execute: abaqus cae noGUI=script -- workdir spec_path
    _run_cae_nougui(script_path, workdir, spec["meta"]["abaqus_release"])

    cae_path = workdir / f"{spec['meta']['model_name']}.cae"
    if not inp_path.exists():
        raise AbaqusAgentError(
            ErrorCode.BUILD_FAILED,
            f".inp not generated after CAE run. Check {workdir / 'build_model_script.log'}",
            workdir=str(workdir),
        )

    return {
        "workdir": workdir,
        "cae_path": cae_path,
        "inp_path": inp_path,
        "run_id": run_id,
        "cached": False,
    }


# ---------------------------------------------------------------------------
# CAE noGUI script writer (geometry/BC/material dispatch)
# ---------------------------------------------------------------------------

def _write_cae_script(spec: dict, script_path: Path, workdir: Path) -> None:
    geo = spec["geometry"]
    mat = spec["material"]
    ana = spec["analysis"]
    bc  = spec.get("bc_load", {})
    out = spec["outputs"]

    model_name = spec["meta"]["model_name"]
    inp_name   = model_name

    geo_type = geo["type"]
    is_premium_geo = False
    if geo_type == "cantilever_block":
        geo_code = _geo_cantilever(geo, model_name)
    elif geo_type == "plate_with_hole":
        geo_code = _geo_plate_hole(geo, model_name)
    elif geo_type == "axisymmetric_disk":
        geo_code = _geo_axisym(geo, model_name)
    elif geo_type == "custom_inp":
        # Just copy the inp file directly - no CAE needed
        src = Path(geo["inp_path"]).resolve()
        shutil.copy(src, workdir / f"{model_name}.inp")
        script_path.write_text("# custom inp - no CAE script needed\n")
        return
    else:
        # Try premium geometry registry
        try:
            from premium.feature_registry import get_premium_geometry
            premium_gen = get_premium_geometry(geo_type)
            if premium_gen:
                geo_code = premium_gen(geo, model_name)
                is_premium_geo = True
            else:
                raise AbaqusAgentError(ErrorCode.UNSUPPORTED_GEOMETRY, f"Unsupported geometry type: {geo_type}")
        except ImportError:
            raise AbaqusAgentError(ErrorCode.UNSUPPORTED_GEOMETRY, f"Unsupported geometry type: {geo_type}")

    step_type = ana["step_type"]
    if step_type == "Static":
        step_code = _step_static(bc, model_name, out)
    elif step_type == "Frequency":
        step_code = _step_frequency(ana, model_name, out)
    elif step_type in ("Dynamic_Explicit", "Dynamic_Implicit"):
        step_code = _step_dynamic(step_type, ana, bc, model_name, out)
    else:
        # Try premium step registry
        try:
            from premium.feature_registry import get_premium_step
            premium_step = get_premium_step(step_type)
            if premium_step:
                step_code = premium_step(ana, bc, model_name, out)
            else:
                raise AbaqusAgentError(ErrorCode.UNSUPPORTED_STEP, f"Unsupported step type: {step_type}")
        except ImportError:
            raise AbaqusAgentError(ErrorCode.UNSUPPORTED_STEP, f"Unsupported step type: {step_type}")

    # Generate additional material code for coupled analyses
    extra_material_code = ""
    try:
        from premium.coupling.coupled_materials import (
            generate_thermal_material_code,
            needs_thermal_properties,
        )
        if needs_thermal_properties(spec):
            extra_material_code = generate_thermal_material_code(mat, model_name)
    except ImportError:
        pass

    # Generate adaptive mesh code if configured
    adaptive_code = ""
    adaptive = ana.get("adaptive_mesh", {})
    if adaptive.get("enabled"):
        try:
            from premium.adaptivity.ale_mesh import generate_ale_code, generate_ale_explicit_code
            from premium.licensing import feature_gate
            feature_gate.require("adaptivity")
            if step_type == "Dynamic_Explicit":
                adaptive_code = generate_ale_explicit_code(adaptive, spec)
            else:
                adaptive_code = generate_ale_code(adaptive, spec)
        except ImportError:
            pass

    # Premium geometry types handle their own section/assembly
    if is_premium_geo:
        section_code = "# Section handled by premium geometry module"
        assembly_code = "# Assembly handled by premium geometry module (if multi-part)"
    else:
        section_code = f"""mdb.models['{model_name}'].HomogeneousSolidSection(
    name='Section-1', material='{mat['name']}', thickness=1.0)
mdb.models['{model_name}'].parts['Part-1'].SectionAssignment(
    region=mdb.models['{model_name}'].parts['Part-1'].sets['ALL'],
    sectionName='Section-1', offset=0.0,
    offsetType=MIDDLE_SURFACE, offsetField='', thicknessAssignment=FROM_SECTION)"""
        assembly_code = f"""a = mdb.models['{model_name}'].rootAssembly
a.DatumCsysByDefault(CARTESIAN)
a.Instance(name='Part-1-1', part=mdb.models['{model_name}'].parts['Part-1'], dependent=ON)"""

    script = f"""# -*- coding: utf-8 -*-
# AUTO-GENERATED by abaqus-agent build_model.py
# DO NOT EDIT - regenerate from spec.yaml
# RUN: abaqus cae noGUI=build_model_script.py -- <workdir> <spec_path>

import sys
import os

# workdir is passed as first argument after --
workdir = sys.argv[-2] if len(sys.argv) >= 3 else os.getcwd()
os.chdir(workdir)

from abaqus import *
from abaqusConstants import *
import part, material, section, assembly, step, load, mesh, job, visualization

# Create the model (required before referencing mdb.models[name])
if '{model_name}' not in mdb.models.keys():
    mdb.Model(name='{model_name}')

# ── Geometry & Mesh ──────────────────────────────────────────────────────────
{geo_code}

# ── Material ─────────────────────────────────────────────────────────────────
mdb.models['{model_name}'].Material(name='{mat['name']}')
mdb.models['{model_name}'].materials['{mat['name']}'].Elastic(
    table=(({mat['E']}, {mat['nu']}),))
{f"mdb.models['{model_name}'].materials['{mat['name']}'].Density(table=(({mat.get('density', 7.85e-9)},),))" if mat.get('density') else '# density not specified'}
{extra_material_code}

# ── Section & Assignment ─────────────────────────────────────────────────────
{section_code}

# ── Assembly ─────────────────────────────────────────────────────────────────
{assembly_code}

# ── Step, BC, Load, Output ───────────────────────────────────────────────────
{step_code}

{adaptive_code}

# ── Write Job ────────────────────────────────────────────────────────────────
mdb.Job(name='{inp_name}', model='{model_name}',
        description='', type=ANALYSIS,
        atTime=None, waitMinutes=0, waitHours=0,
        queue=None, memory=90, memoryUnits=PERCENTAGE,
        getMemoryFromAnalysis=True,
        explicitPrecision=SINGLE, nodalOutputPrecision=SINGLE,
        echoPrint=OFF, modelPrint=OFF, contactPrint=OFF, historyPrint=OFF,
        userSubroutine='', scratch='', resultsFormat=ODB,
        multiprocessingMode=DEFAULT, numCpus=1, numGPUs=0)

mdb.jobs['{inp_name}'].writeInput(consistencyChecking=OFF)
print('INP_WRITTEN: ' + workdir + '/{inp_name}.inp')
mdb.saveAs('{inp_name}')
print('CAE_WRITTEN: ' + workdir + '/{inp_name}.cae')
"""
    script_path.write_text(script, encoding="utf-8")


# ---------------------------------------------------------------------------
# Geometry code generators
# ---------------------------------------------------------------------------

def _geo_cantilever(geo: dict, model_name: str) -> str:
    L, W, H = geo["L"], geo["W"], geo["H"]
    seed = geo.get("seed_size", min(L, W, H) / 4)
    return f"""
def _sketch_rect(model, w, h):
    s = model.ConstrainedSketch(name='__profile__', sheetSize=200.0)
    s.rectangle(point1=(0.0, 0.0), point2=(w, h))
    return s

p = mdb.models['{model_name}'].Part(name='Part-1', dimensionality=THREE_D,
    type=DEFORMABLE_BODY)
p.BaseSolidExtrude(sketch=_sketch_rect(mdb.models['{model_name}'], {W}, {H}), depth={L})
p.Set(name='ALL', cells=p.cells)
p.Set(name='FIXED_END', faces=p.faces.getByBoundingBox(zMin=-0.01, zMax=0.01,
    xMin=-0.01, xMax={W}+0.01, yMin=-0.01, yMax={H}+0.01))
p.Set(name='LOAD_END',  faces=p.faces.getByBoundingBox(zMin={L}-0.01, zMax={L}+0.01,
    xMin=-0.01, xMax={W}+0.01, yMin=-0.01, yMax={H}+0.01))
p.Surface(name='LOAD_SURF', side1Faces=p.faces.getByBoundingBox(zMin={L}-0.01, zMax={L}+0.01,
    xMin=-0.01, xMax={W}+0.01, yMin=-0.01, yMax={H}+0.01))
p.Surface(name='FIXED_SURF', side1Faces=p.faces.getByBoundingBox(zMin=-0.01, zMax=0.01,
    xMin=-0.01, xMax={W}+0.01, yMin=-0.01, yMax={H}+0.01))
p.seedPart(size={seed}, deviationFactor=0.1, minSizeFactor=0.1)
p.generateMesh()
# TIP_NODES: pick single closest node to (L, W/2, H/2)
tip_pt = ({W}/2.0, {H}/2.0, {L})
def _node_dist2(n):
    c = n.coordinates
    return (c[0]-tip_pt[0])**2 + (c[1]-tip_pt[1])**2 + (c[2]-tip_pt[2])**2
all_nodes = list(p.nodes)
all_nodes.sort(key=_node_dist2)
tip_node_label = all_nodes[0].label
tip_seq = p.nodes.sequenceFromLabels((tip_node_label,))
p.Set(name='TIP_NODES', nodes=tip_seq)
"""


def _geo_plate_hole(geo: dict, model_name: str) -> str:
    L, W, R = geo["L"], geo["W"], geo["R"]
    seed = geo.get("seed_size", 3.0)
    return f"""
import math
p = mdb.models['{model_name}'].Part(name='Part-1', dimensionality=TWO_D_PLANAR,
    type=DEFORMABLE_BODY)
s = mdb.models['{model_name}'].ConstrainedSketch(name='__profile__', sheetSize=300.0)
# Quarter plate with quarter circular hole at corner (0,0)
# Build closed boundary: (R,0)->(L,0)->(L,W)->(0,W)->(0,R)->arc->(R,0)
s.Line(point1=({R}, 0.0), point2=({L}, 0.0))
s.Line(point1=({L}, 0.0), point2=({L}, {W}))
s.Line(point1=({L}, {W}), point2=(0.0, {W}))
s.Line(point1=(0.0, {W}), point2=(0.0, {R}))
s.ArcByCenterEnds(center=(0.0, 0.0), point1=(0.0, {R}), point2=({R}, 0.0), direction=CLOCKWISE)
p.BaseShell(sketch=s)
del mdb.models['{model_name}'].sketches['__profile__']

p.Set(name='ALL', faces=p.faces)
p.Set(name='HOLE_EDGE', edges=p.edges.getByBoundingCylinder(
    (0.0, 0.0, 0.0), (0.0, 0.0, 1.0), {R}+0.5))
p.Set(name='LOAD_END',  edges=p.edges.getByBoundingBox(
    xMin={L}-0.01, xMax={L}+0.01, yMin=-0.01, yMax={W}+0.01))
p.Set(name='SYM_X', edges=p.edges.getByBoundingBox(
    xMin=-0.01, xMax=0.01, yMin={R}-0.01, yMax={W}+0.01))
p.Set(name='SYM_Y', edges=p.edges.getByBoundingBox(
    yMin=-0.01, yMax=0.01, xMin={R}-0.01, xMax={L}+0.01))
p.Surface(name='LOAD_SURF', side1Edges=p.edges.getByBoundingBox(
    xMin={L}-0.01, xMax={L}+0.01, yMin=-0.01, yMax={W}+0.01))
p.seedPart(size={seed}, deviationFactor=0.1, minSizeFactor=0.1)
p.generateMesh()

"""


def _geo_axisym(geo: dict, model_name: str) -> str:
    L, R = geo.get("L", 50.0), geo.get("R", 20.0)
    seed = geo.get("seed_size", 3.0)
    return f"""
p = mdb.models['{model_name}'].Part(name='Part-1', dimensionality=AXISYMMETRIC,
    type=DEFORMABLE_BODY)
s = mdb.models['{model_name}'].ConstrainedSketch(name='__profile__', sheetSize=200.0,
    transform=None)
s.rectangle(point1=(0.0, 0.0), point2=({R}, {L}))
p.BaseShell(sketch=s)
del mdb.models['{model_name}'].sketches['__profile__']
p.Set(name='ALL', faces=p.faces)
p.seedPart(size={seed}, deviationFactor=0.1, minSizeFactor=0.1)
p.generateMesh()
"""


# ---------------------------------------------------------------------------
# Step/BC/Load code generators
# ---------------------------------------------------------------------------

def _step_static(bc: dict, model_name: str, out: dict) -> str:
    load_val = bc.get("value", -1.0)
    fixed_face = bc.get("fixed_face", "x=0")
    # BC: detect symmetry vs encastre
    if "symmetry" in fixed_face.lower():
        bc_code = (
            "mdb.models['{model_name}'].XsymmBC(\n"
            "    name='SymX', createStepName='Initial',\n"
            "    region=a.instances['Part-1-1'].sets['SYM_X'])\n"
            "mdb.models['{model_name}'].YsymmBC(\n"
            "    name='SymY', createStepName='Initial',\n"
            "    region=a.instances['Part-1-1'].sets['SYM_Y'])"
        ).replace('{model_name}', model_name)
    else:
        bc_code = (
            "mdb.models['" + model_name + "'].EncastreBC(\n"
            "    name='Fixed', createStepName='Initial',\n"
            "    region=a.instances['Part-1-1'].sets['FIXED_END'])"
        )
    return f"""
mdb.models['{model_name}'].StaticStep(name='Step-1', previous='Initial',
    description='Static analysis', timePeriod=1.0,
    initialInc=0.1, minInc=1e-5, maxInc=1.0,
    nlgeom=OFF)

a = mdb.models['{model_name}'].rootAssembly
inst = a.instances['Part-1-1']

# Fixed BC
{bc_code}

# Load
mdb.models['{model_name}'].Pressure(
    name='Load-1', createStepName='Step-1',
    region=a.instances['Part-1-1'].surfaces['LOAD_SURF'],
    magnitude={abs(load_val)}, amplitude=UNSET,
    distributionType=UNIFORM)

# Field outputs
mdb.models['{model_name}'].fieldOutputRequests['F-Output-1'].setValues(
    variables=('S', 'E', 'U', 'RF'))

# History outputs - tip node (optional, may not exist for all cases)
try:
    mdb.models['{model_name}'].HistoryOutputRequest(
        name='TIP', createStepName='Step-1',
        region=a.instances['Part-1-1'].sets['TIP_NODES'],
        variables=('U1', 'U2', 'U3'))
except (KeyError, Exception):
    pass
"""


def _step_frequency(ana: dict, model_name: str, out: dict) -> str:
    n = ana.get("num_eigenmodes", 6)
    return f"""
mdb.models['{model_name}'].FrequencyStep(
    name='Step-1', previous='Initial',
    numEigen={n}, eigensolver=LANCZOS,
    minEigen=-1.0, maxEigen=None, vectors=18,
    maxIterations=30, blockSize=DEFAULT, maxBlocks=DEFAULT,
    normalization=MASS, propertyEvaluationFrequency=None,
    shift=-1.0)

mdb.models['{model_name}'].fieldOutputRequests['F-Output-1'].setValues(
    variables=('U',))
"""


def _step_dynamic(step_type: str, ana: dict, bc: dict, model_name: str, out: dict) -> str:
    t = ana.get("time_period", 1e-3)
    load_val = bc.get("value", -1.0)
    if step_type == "Dynamic_Explicit":
        return f"""
mdb.models['{model_name}'].ExplicitDynamicsStep(
    name='Step-1', previous='Initial',
    timePeriod={t}, description='Explicit dynamic')

a = mdb.models['{model_name}'].rootAssembly

mdb.models['{model_name}'].EncastreBC(
    name='Fixed', createStepName='Initial',
    region=a.instances['Part-1-1'].sets['FIXED_END'])

mdb.models['{model_name}'].SmoothStepAmplitude(name='Amp-1',
    timeSpan=STEP, data=((0.0, 0.0), ({t}, 1.0)))

mdb.models['{model_name}'].Pressure(
    name='Load-1', createStepName='Step-1',
    region=a.instances['Part-1-1'].surfaces['LOAD_SURF'],
    magnitude={abs(load_val)}, amplitude='Amp-1',
    distributionType=UNIFORM)

mdb.models['{model_name}'].fieldOutputRequests['F-Output-1'].setValues(
    variables=('S', 'E', 'U', 'V', 'RF'), numIntervals=20)
"""
    else:
        return _step_static(bc, model_name, out)


# ---------------------------------------------------------------------------
# Abaqus execution helpers
# ---------------------------------------------------------------------------

def _run_cae_nougui(script_path: Path, workdir: Path, abaqus_release: str) -> None:
    """Execute abaqus cae noGUI=<script> and capture output."""
    log_path = workdir / "build_model_script.log"
    _abq = shutil.which("abaqus") or "abaqus"
    cmd = [_abq, "cae", f"noGUI={script_path}", "--", str(workdir), "spec"]
    try:
        result = subprocess.run(
            cmd,
            cwd=str(workdir),
            capture_output=True,
            text=True, errors='replace', encoding='utf-8',
            timeout=600,
        )
        log_path.write_text(result.stdout + "\n" + result.stderr, encoding="utf-8")
        if result.returncode != 0:
            raise AbaqusAgentError(
                ErrorCode.BUILD_FAILED,
                f"abaqus cae noGUI returned {result.returncode}. See {log_path}",
                log_snippet=result.stderr[-2000:],
                workdir=str(workdir),
            )
    except subprocess.TimeoutExpired:
        raise AbaqusAgentError(
            ErrorCode.TIMEOUT,
            "abaqus cae noGUI timed out after 600s",
            workdir=str(workdir),
        )
    except FileNotFoundError:
        raise AbaqusAgentError(
            ErrorCode.ABAQUS_NOT_FOUND,
            "'abaqus' executable not found. Check PATH and Abaqus installation.",
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_spec(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _run_id(spec: dict) -> str:
    """Deterministic run ID from spec content + release."""
    payload = json.dumps(spec, sort_keys=True, default=str).encode()
    return hashlib.sha256(payload).hexdigest()[:16]


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python build_model.py <spec.yaml> [workdir]")
        sys.exit(1)
    spec_file = sys.argv[1]
    wd = sys.argv[2] if len(sys.argv) > 2 else None
    result = build_model(spec_file, wd)
    print(json.dumps({k: str(v) for k, v in result.items()}, indent=2))
