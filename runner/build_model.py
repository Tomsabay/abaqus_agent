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
    if workdir:
        # Resolved, not just wrapped: _run_cae_nougui passes the script path to
        # `abaqus cae noGUI=` while running with cwd=workdir, so a relative
        # workdir is re-interpreted relative to itself and CAE reports "The
        # following file(s) could not be located" for a script that is sitting
        # right there. Hit while probing a selector mismatch through
        # `python runner/build_model.py <spec> <relative-dir>`.
        workdir = Path(workdir).resolve()
    else:
        # Default run root is spec-relative (cases/<case>/runs/) in dev. Packaged
        # mode redirects to the user data dir so runs never write into a
        # read-only install directory. Keep the redirect shallow — Abaqus
        # rejects input paths > 256 chars (see submit_job._build_cmd).
        from core import config
        root = config.run_root()
        workdir = (root / run_id) if root else spec_path.parent / "runs" / run_id
    workdir.mkdir(parents=True, exist_ok=True)

    inp_path = workdir / f"{spec['meta']['model_name']}.inp"

    # Reuse is allowed only on PROOF, never on file existence. run_id hashes
    # the spec alone, so "the .inp is already there" proves nothing about it
    # being the deck THIS build would produce: the source .inp of a custom_inp
    # spec can change under an unchanged path, the generator code can change,
    # the probed solver can change. Reproduced before this guard: edit a
    # custom_inp source 100N -> 900N, rerun, cached=True, and the solver ran
    # the 100N deck — COMPLETED, fresh timestamps, stale physics.
    is_custom = not _is_v2(spec) and spec["geometry"]["type"] == "custom_inp"
    fingerprint = _build_fingerprint(spec, spec_path, workdir)
    rebuild_reason = None
    if inp_path.exists() and inp_path.stat().st_size > 0:
        miss = _cache_verdict(workdir, inp_path, fingerprint)
        if miss is None:
            # Preview mesh may be missing on cached runs (e.g. cache predates
            # the feature) — regenerate from preview_raw.json without CAE.
            cached_mesh = _write_preview_mesh(workdir, inp_path)
            result = {
                "workdir": workdir,
                "cae_path": workdir / f"{spec['meta']['model_name']}.cae",
                "inp_path": inp_path,
                "run_id": run_id,
                "cached": True,
                "cache_reason": (
                    "构建指纹一致（spec / %s / 求解器版本均未变），复用既有 deck"
                    % ("源 .inp 内容" if is_custom else "生成器脚本")),
                "preview_mesh": cached_mesh.name if cached_mesh else None,
            }
            if is_custom:
                result["custom_inp"] = True
                result["source_inp_path"] = _resolve_custom_src(spec, spec_path)
            return result
        # Fail closed: anything unproven rebuilds.
        rebuild_reason = "重新生成 deck：%s" % miss

    if is_custom:
        result = _build_custom_inp(spec, spec_path, workdir, inp_path, run_id)
        _write_build_manifest(workdir, inp_path, fingerprint)
        if rebuild_reason:
            result["cache_reason"] = rebuild_reason
        return result

    # Generate the CAE noGUI script
    script_path = workdir / "build_model_script.py"
    _write_cae_script(spec, script_path, workdir, spec_path)

    # Execute: abaqus cae noGUI=script -- workdir spec_path
    _run_cae_nougui(script_path, workdir, spec["meta"]["abaqus_release"])

    cae_path = workdir / f"{spec['meta']['model_name']}.cae"
    if not inp_path.exists():
        why, snippet = _why_no_inp(workdir)
        raise AbaqusAgentError(
            ErrorCode.BUILD_FAILED,
            f".inp not generated after CAE run. {why}",
            log_snippet=snippet,
            workdir=str(workdir),
        )

    # Turn the CAE-side preview_raw.json dump into a WBViewport-compatible
    # mesh.json — this is what the workbench 3D preview reads while the user
    # is still iterating on the spec (no ODB needed).
    mesh_path = _write_preview_mesh(workdir, inp_path)

    # After the .inp, never before: a crash in between must leave a cache
    # miss, not a manifest vouching for a deck that was never written.
    _write_build_manifest(workdir, inp_path, fingerprint)

    result = {
        "workdir": workdir,
        "cae_path": cae_path,
        "inp_path": inp_path,
        "run_id": run_id,
        "cached": False,
        "preview_mesh": mesh_path.name if mesh_path else None,
    }
    if rebuild_reason:
        result["cache_reason"] = rebuild_reason
    return result


def _write_preview_mesh(workdir: Path, inp_path: Path | None = None) -> Path | None:
    """Turn the CAE-side dump (or, for custom_inp, the .inp itself) into a
    WBViewport-friendly mesh JSON. Best-effort — never raises.

    Two paths converge into the same output file (preview_mesh.json):
      1. preview_raw.json present (single-part CAE noGUI build) -> legacy
         single-mesh JSON with nodes/tris.
      2. Falls back to parsing inp_path directly -> multi-part JSON with
         parts=[{name, family, nodes, tris|lines, ...}]. Handles both
         custom_inp and any generated .inp with multiple ELSET blocks.
    """
    raw_path = workdir / "preview_raw.json"
    # Path 3 (v2 assemblies): CAE dumped every instance already positioned in
    # assembly space. Preferred over parsing the .inp because the transform is
    # read off the model rather than recomputed from *Instance data lines.
    if raw_path.exists():
        try:
            import json

            raw = json.loads(raw_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            raw = None
        if isinstance(raw, dict) and raw.get("format") == "abaqus-agent-preview/instances":
            from post.parse_inp import parts_from_instance_dump
            out = workdir / "preview_mesh.json"
            data = parts_from_instance_dump(raw, source=str(inp_path or raw_path))
            out.write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")
            return out
    # Path 2: no CAE dump but we have an .inp — parse it into multi-part.
    if not raw_path.exists() and inp_path is not None and inp_path.exists():
        try:
            from post.parse_inp import write_parts_mesh
            out = workdir / "preview_mesh.json"
            write_parts_mesh(inp_path, out)
            return out
        except Exception as exc:
            # Best-effort stays best-effort (a broken preview must not fail a
            # build), but the reason must survive somewhere findable.
            import sys
            print("preview_mesh generation failed for %s: %s: %s"
                  % (inp_path, type(exc).__name__, exc), file=sys.stderr)
            return None
    if not raw_path.exists():
        return None
    try:
        import json

        from post.export_odb_mesh import build_surface

        raw = json.loads(raw_path.read_text(encoding="utf-8"))
        node_coords = {int(lbl): (x, y, z) for lbl, x, y, z in raw["nodes"]}
        elements = [(el_type, tuple(conn)) for el_type, conn in raw["elements"]]
        flat_nodes, flat_tris, _labels = build_surface(node_coords, elements)
        xs, ys, zs = flat_nodes[0::3], flat_nodes[1::3], flat_nodes[2::3]
        mesh = {
            "format": "abaqus-agent-mesh/1",
            "step": "preview",
            "is_modal": False,
            "mode": None,
            "frequency": None,
            "node_count": len(_labels),
            "tri_count": len(flat_tris) // 3,
            "nodes": flat_nodes,
            "tris": flat_tris,
            "fields": {},
            "displacement": [0.0] * (len(_labels) * 3),
            "bbox": [[min(xs), min(ys), min(zs)],
                     [max(xs), max(ys), max(zs)]] if xs else [[0, 0, 0], [0, 0, 0]],
        }
        out = workdir / "preview_mesh.json"
        out.write_text(json.dumps(mesh, separators=(",", ":")), encoding="utf-8")
        return out
    except Exception as _pv_e:
        # Preview is best-effort; don't fail the build. Log it so we can see
        # what went wrong from backend.err.log without wrapping every caller.
        import sys as _sys
        import traceback as _tb
        _sys.stderr.write("[_write_preview_mesh] %s\n" % _pv_e)
        _tb.print_exc(file=_sys.stderr)
        _sys.stderr.flush()
        return None


# ---------------------------------------------------------------------------
# CAE noGUI script writer (geometry/BC/material dispatch)
# ---------------------------------------------------------------------------

def _is_v2(spec: dict) -> bool:
    """True for the assembly dialect. `parts` is the discriminator the schema
    branches on, so nothing else may be used here or the two would disagree."""
    return "parts" in spec


def _write_cae_script(spec: dict, script_path: Path, workdir: Path,
                      spec_path: Path | None = None) -> None:
    if _is_v2(spec):
        from runner.build_v2 import generate_script
        # The spec's own directory is what a `{file:}` path is relative to --
        # the same rule custom_inp already uses. None when the caller had no
        # spec on disk, which makes a relative path a refusal rather than a
        # guess.
        spec_dir = spec_path.parent if spec_path is not None else None
        script_path.write_text(generate_script(spec, spec_dir=spec_dir),
                               encoding="utf-8")
        return

    geo = spec["geometry"]
    mat = spec["material"]
    ana = spec["analysis"]
    bc  = spec.get("bc_load", {})
    out = spec["outputs"]

    model_name = spec["meta"]["model_name"]
    inp_name   = model_name

    geo_type = geo["type"]
    # plate_with_hole is a quarter-symmetry model: its geometry only creates
    # SYM_X/SYM_Y sets, so the encastre branch (FIXED_END) can never work.
    # Normalize here so every step generator takes the symmetry path.
    if geo_type == "plate_with_hole" and "symmetry" not in str(bc.get("fixed_face", "")).lower():
        bc = {**bc, "fixed_face": str(bc.get("fixed_face") or "x=0") + "_symmetry"}
    is_feature_geo = False
    if geo_type == "cantilever_block":
        geo_code = _geo_cantilever(geo, model_name, ana)
    elif geo_type == "plate_with_hole":
        geo_code = _geo_plate_hole(geo, model_name)
    elif geo_type == "axisymmetric_disk":
        geo_code = _geo_axisym(geo, model_name)
    elif geo_type == "square_plate":
        geo_code = _geo_square_plate(geo, model_name, ana)
    elif geo_type == "custom_inp":
        raise AbaqusAgentError(
            ErrorCode.BUILD_FAILED,
            "custom_inp should be handled before CAE script generation",
        )
    else:
        # Try the feature-module geometry registry
        try:
            from features.feature_registry import get_geometry_generator
            feature_gen = get_geometry_generator(geo_type)
            if feature_gen:
                geo_code = feature_gen(geo, model_name)
                is_feature_geo = True
            else:
                raise AbaqusAgentError(ErrorCode.UNSUPPORTED_GEOMETRY, f"Unsupported geometry type: {geo_type}")
        except ImportError:
            raise AbaqusAgentError(ErrorCode.UNSUPPORTED_GEOMETRY, f"Unsupported geometry type: {geo_type}")

    step_type = ana["step_type"]
    if step_type == "Static":
        step_code = _step_static(bc, model_name, out)
    elif step_type == "Frequency":
        step_code = _step_frequency(ana, bc, model_name, out)
    elif step_type in ("Dynamic_Explicit", "Dynamic_Implicit"):
        step_code = _step_dynamic(step_type, ana, bc, model_name, out)
    else:
        # Try the feature-module step registry
        try:
            from features.feature_registry import get_step_generator
            feature_step = get_step_generator(step_type)
            if feature_step:
                step_code = feature_step(ana, bc, model_name, out)
            else:
                raise AbaqusAgentError(ErrorCode.UNSUPPORTED_STEP, f"Unsupported step type: {step_type}")
        except ImportError:
            raise AbaqusAgentError(ErrorCode.UNSUPPORTED_STEP, f"Unsupported step type: {step_type}")

    # Generate additional material code for coupled analyses
    extra_material_code = ""
    try:
        from features.coupling.coupled_materials import (
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
            from features.adaptivity.ale_mesh import generate_ale_code, generate_ale_explicit_code
            if step_type == "Dynamic_Explicit":
                adaptive_code = generate_ale_explicit_code(adaptive, spec)
            else:
                adaptive_code = generate_ale_code(adaptive, spec)
        except ImportError:
            pass

    # Feature-module geometry types handle their own section/assembly
    if is_feature_geo:
        section_code = "# Section handled by extended geometry module"
        assembly_code = "# Assembly handled by extended geometry module (if multi-part)"
    elif geo_type == "square_plate":
        plate_thickness = geo.get("thickness", 25.0)
        section_code = f"""mdb.models['{model_name}'].HomogeneousShellSection(
    name='Section-1', preIntegrate=OFF, material='{mat['name']}',
    thicknessType=UNIFORM, thickness={plate_thickness},
    integrationRule=SIMPSON, numIntPts=5)
mdb.models['{model_name}'].parts['Part-1'].SectionAssignment(
    region=mdb.models['{model_name}'].parts['Part-1'].sets['ALL'],
    sectionName='Section-1', offset=0.0,
    offsetType=MIDDLE_SURFACE, offsetField='', thicknessAssignment=FROM_SECTION)"""
        assembly_code = f"""a = mdb.models['{model_name}'].rootAssembly
a.DatumCsysByDefault(CARTESIAN)
a.Instance(name='Part-1-1', part=mdb.models['{model_name}'].parts['Part-1'], dependent=ON)"""
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
{("mdb.models['" + model_name + "'].materials['" + mat['name'] + "'].Plastic(table=((" + str(mat['yield']) + ", 0.0), (" + str(mat['yield'] + mat.get('hardening', 0.0) * 0.1) + ", 0.1)))") if mat.get('yield') else '# no plastic'}
{extra_material_code}

# ── Section & Assignment ─────────────────────────────────────────────────────
{section_code}

# ── Assembly ─────────────────────────────────────────────────────────────────
{assembly_code}

# ── Step, BC, Load, Output ───────────────────────────────────────────────────
{step_code}

{adaptive_code}

# ── Preview mesh dump (best-effort, before job write) ──────────────────────
# Raw nodes/elements dumped here; py3 side turns it into the WBViewport mesh.
try:
    import json as _preview_json
    _pv_p = None
    try:
        _pv_p = mdb.models['{model_name}'].parts['Part-1']
    except Exception:
        _pv_p = None
    if _pv_p is not None and len(_pv_p.nodes) > 0 and len(_pv_p.elements) > 0:
        # element.connectivity in CAE is a tuple of 0-based node INDICES into
        # p.nodes, not labels. Build an index->label table so we can emit
        # label-keyed connectivity that matches export_odb_mesh conventions.
        _pv_index_to_label = [int(_n.label) for _n in _pv_p.nodes]
        _pv_nodes = [(_pv_index_to_label[_i], float(_n.coordinates[0]),
                      float(_n.coordinates[1]), float(_n.coordinates[2]))
                     for _i, _n in enumerate(_pv_p.nodes)]
        _pv_elems = [(str(_el.type),
                      [_pv_index_to_label[int(_c)] for _c in _el.connectivity])
                     for _el in _pv_p.elements]
        with open(os.path.join(workdir, 'preview_raw.json'), 'w') as _pv_f:
            _preview_json.dump({{'nodes': _pv_nodes,
                                 'elements': _pv_elems}}, _pv_f)
        print('PREVIEW_DUMPED: preview_raw.json (nodes=' + str(len(_pv_nodes))
              + ' elems=' + str(len(_pv_elems)) + ')')
except Exception as _pv_e:
    print('PREVIEW_DUMP_FAILED: ' + str(_pv_e))

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

def _geo_cantilever(geo: dict, model_name: str, ana: dict = None) -> str:
    L, W, H = geo["L"], geo["W"], geo["H"]
    seed = geo.get("seed_size", min(L, W, H) / 4)
    step_type = (ana or {}).get("step_type", "Static")
    solver = (ana or {}).get("solver", "standard")
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
# Nearest node to the tip-face center: a bounding box only works when the seed
# happens to place a node exactly at (W/2, H/2), which breaks on refined meshes.
_tip_best = None
_tip_bestd = 1.0e30
for _n in p.nodes:
    _c = _n.coordinates
    if abs(_c[2] - {L}) <= 0.01:
        _d = (_c[0] - {W}/2.0)**2 + (_c[1] - {H}/2.0)**2
        if _d < _tip_bestd:
            _tip_bestd = _d
            _tip_best = _n.label
p.Set(name='TIP_NODES', nodes=p.nodes.sequenceFromLabels((_tip_best,)))
# Use C3D8I (incompatible modes) — eliminates shear locking + hourglass for solid bending
# Choose element type based on solver: C3D20R for Standard, C3D8R for Explicit
import abaqusConstants as _C
_is_explicit = '{step_type}'.startswith('Dynamic_Explicit') or '{solver}' == 'explicit'
if _is_explicit:
    elemType_hex = mesh.ElemType(elemCode=_C.C3D8R, elemLibrary=_C.EXPLICIT, hourglassControl=_C.ENHANCED)
    elemType_wedge = mesh.ElemType(elemCode=_C.C3D6, elemLibrary=_C.EXPLICIT)
else:
    elemType_hex = mesh.ElemType(elemCode=_C.C3D20R, elemLibrary=_C.STANDARD)
    elemType_wedge = mesh.ElemType(elemCode=_C.C3D15, elemLibrary=_C.STANDARD)
p.setElementType(regions=(p.cells,), elemTypes=(elemType_hex, elemType_wedge))
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
# Use CPS4 full integration (CPS4R reduced has hourglass issues)
from abaqusConstants import CPS4, CPS3, STANDARD, ENHANCED
elemType_quad = mesh.ElemType(elemCode=CPS4, elemLibrary=STANDARD)
elemType_tri = mesh.ElemType(elemCode=CPS3, elemLibrary=STANDARD)
p.setElementType(regions=(p.faces,), elemTypes=(elemType_quad, elemType_tri))

"""


def _geo_square_plate(geo: dict, model_name: str, ana: dict = None) -> str:
    """Square steel plate, modeled with shell elements (S4R for Explicit, S4 for Standard).
    All 4 edges clamped (FIXED_EDGES), top surface = BLAST_SURF.
    Center node = TIP_NODES (track max deflection).
    """
    L = geo["L"]
    seed = geo.get("seed_size", L / 20.0)
    step_type = (ana or {}).get("step_type", "Static")
    is_explicit = step_type == "Dynamic_Explicit" or (ana or {}).get("solver") == "explicit"
    return f"""
# Square plate (3D shell)
p = mdb.models['{model_name}'].Part(name='Part-1', dimensionality=THREE_D,
    type=DEFORMABLE_BODY)
s = mdb.models['{model_name}'].ConstrainedSketch(name='__profile__', sheetSize=2*{L})
s.rectangle(point1=(0.0, 0.0), point2=({L}, {L}))
p.BaseShell(sketch=s)
del mdb.models['{model_name}'].sketches['__profile__']

p.Set(name='ALL', faces=p.faces)
# Four clamped edges
p.Set(name='FIXED_EDGES', edges=p.edges.getByBoundingBox(
    xMin=-0.01, xMax={L}+0.01,
    yMin=-0.01, yMax={L}+0.01,
    zMin=-0.01, zMax=0.01))
# Top surface = where blast pressure applied (positive face normal = +z)
p.Surface(name='BLAST_SURF', side1Faces=p.faces)
# Section: shell with given thickness
p.seedPart(size={seed}, deviationFactor=0.1, minSizeFactor=0.1)
p.generateMesh()

# Center node = TIP for max deflection tracking
center = ({L}/2.0, {L}/2.0, 0.0)
def _dist2(n):
    c = n.coordinates
    return (c[0]-center[0])**2 + (c[1]-center[1])**2 + (c[2]-center[2])**2
nodes_sorted = sorted(list(p.nodes), key=_dist2)
center_label = nodes_sorted[0].label
p.Set(name='TIP_NODES', nodes=p.nodes.sequenceFromLabels((center_label,)))

# Element type: S4R for Explicit (with hourglass control), S4 for Standard
from abaqusConstants import S4R, S4, S3, STANDARD, EXPLICIT, ENHANCED
if {is_explicit}:
    elem_quad = mesh.ElemType(elemCode=S4R, elemLibrary=EXPLICIT, hourglassControl=ENHANCED)
    elem_tri = mesh.ElemType(elemCode=S3, elemLibrary=EXPLICIT)
else:
    elem_quad = mesh.ElemType(elemCode=S4, elemLibrary=STANDARD)
    elem_tri = mesh.ElemType(elemCode=S3, elemLibrary=STANDARD)
p.setElementType(regions=(p.faces,), elemTypes=(elem_quad, elem_tri))
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
    load_type = str(bc.get("load_type", "pressure")).lower()
    fixed_face = bc.get("fixed_face", "x=0")
    direction = bc.get("direction", None)  # 1=X, 2=Y, 3=Z
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
    # Load: explicit force requests use TIP_NODES; pressure stays on LOAD_SURF even if direction is present.
    if load_type in {"concentrated_force", "force", "nodal_force"}:
        cf_kwargs = []
        direction = int(direction or 2)
        for d in (1, 2, 3):
            cf_kwargs.append("cf{}={}".format(d, load_val if d == int(direction) else 0.0))
        load_code = (
            "mdb.models['" + model_name + "'].ConcentratedForce(\n"
            "    name='Load-1', createStepName='Step-1',\n"
            "    region=a.instances['Part-1-1'].sets['TIP_NODES'],\n"
            "    " + ", ".join(cf_kwargs) + ", distributionType=UNIFORM)"
        )
    else:
        load_code = (
            "mdb.models['" + model_name + "'].Pressure(\n"
            "    name='Load-1', createStepName='Step-1',\n"
            "    region=a.instances['Part-1-1'].surfaces['LOAD_SURF'],\n"
            # The sign IS the load direction: Abaqus pressure is positive into
            # the surface, so a spec asking for -100 means tension. An abs()
            # here (added 11b1324) silently turned plate_hole's tension into
            # compression. Mises is magnitude-only, so MISES_HOLE_EDGE still
            # landed at 295.6 against an expected 300 and the contour looked
            # right — only U_X_MAX gave it away, coming out exactly 0.0 because
            # every U1 was negative and the max sat on the symmetry plane.
            # The dynamic pressure branch never had the abs(); this restores
            # agreement between them.
            "    magnitude=" + str(float(load_val)) + ", amplitude=UNSET,\n"
            "    distributionType=UNIFORM)"
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
{load_code}

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


def _step_frequency(ana: dict, bc: dict, model_name: str, out: dict) -> str:
    n = ana.get("num_eigenmodes", 6)
    fixed_face = (bc or {}).get("fixed_face")
    if fixed_face:
        bc_code = (
            "a = mdb.models['" + model_name + "'].rootAssembly\n"
            "mdb.models['" + model_name + "'].EncastreBC(\n"
            "    name='Fixed', createStepName='Initial',\n"
            "    region=a.instances['Part-1-1'].sets['FIXED_END'])"
        )
        eig_kwargs = "minEigen=0.0, maxEigen=None, vectors=18"
    else:
        bc_code = ""
        eig_kwargs = "minEigen=-1.0, maxEigen=None, vectors=18,\n    shift=-1.0"
    return f"""
{bc_code}

mdb.models['{model_name}'].FrequencyStep(
    name='Step-1', previous='Initial',
    numEigen={n}, eigensolver=LANCZOS,
    {eig_kwargs},
    maxIterations=30, blockSize=DEFAULT, maxBlocks=DEFAULT,
    normalization=MASS, propertyEvaluationFrequency=None)

mdb.models['{model_name}'].fieldOutputRequests['F-Output-1'].setValues(
    variables=('U',))
"""


def _step_dynamic(step_type: str, ana: dict, bc: dict, model_name: str, out: dict) -> str:
    t = ana.get("time_period", 1e-3)
    load_val = bc.get("value", -1.0)
    load_type = bc.get("load_type", "pressure")
    direction = bc.get("direction", 3)
    if step_type == "Dynamic_Explicit":
        # Friedlander air-blast (Kingery-Bulmash) for blast_conwep load type
        if load_type == "blast_conwep":
            tnt_kg = bc.get("blast_tnt_kg", 10.0)
            standoff_mm = bc.get("blast_standoff_mm", 2000.0)
            return _step_blast_explicit(t, tnt_kg, standoff_mm, model_name, out)
        # Build load code based on load_type
        if load_type == "displacement":
            d = int(direction)
            disp_kwargs = []
            for i in (1, 2, 3):
                disp_kwargs.append("u{}={}".format(i, load_val if i == d else 0.0))
            load_code = (
                "mdb.models['" + model_name + "'].DisplacementBC(\n"
                "    name='Load-1', createStepName='Step-1',\n"
                "    region=a.instances['Part-1-1'].sets['LOAD_END'],\n"
                "    " + ", ".join(disp_kwargs) + ", amplitude='Amp-1',\n"
                "    distributionType=UNIFORM, fixed=OFF)"
            )
        else:
            load_code = (
                "mdb.models['" + model_name + "'].Pressure(\n"
                "    name='Load-1', createStepName='Step-1',\n"
                "    region=a.instances['Part-1-1'].surfaces['LOAD_SURF'],\n"
                "    magnitude=" + str(load_val) + ", amplitude='Amp-1',\n"
                "    distributionType=UNIFORM)"
            )
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

{load_code}

mdb.models['{model_name}'].fieldOutputRequests['F-Output-1'].setValues(
    variables=('S', 'E', 'U', 'V', 'RF'), numIntervals=20)
"""
    else:
        return _step_static(bc, model_name, out)


# ---------------------------------------------------------------------------
# Abaqus execution helpers
# ---------------------------------------------------------------------------

def _step_blast_explicit(t: float, tnt_kg: float, standoff_mm: float,
                         model_name: str, out: dict) -> str:
    """Friedlander air-blast loading (Kingery-Bulmash empirical approximations).

    P(t) = P_max * (1 - t/td) * exp(-b*t/td)
      P_max  = peak overpressure (MPa)
      td     = positive phase duration (s)
      b      = wave decay coefficient (~1.0)

    All values use mm/MPa/t/s units.
    Kingery-Bulmash scaled distance Z = R / W^(1/3)  where R in m, W in kg.
    """
    import math
    R_m = standoff_mm / 1000.0
    W_kg = tnt_kg
    Z = R_m / (W_kg ** (1.0/3.0))  # m/kg^(1/3)
    # Kingery-Bulmash polynomial fits (simplified), valid for 0.05 < Z < 40
    # Peak incident overpressure (kPa) — Mills (1987) approximation
    if Z < 0.05:
        Z = 0.05
    if Z > 40:
        Z = 40
    P_kpa = 1772.0 / Z**3 - 114.0 / Z**2 + 108.0 / Z
    # Reflected pressure ~= 2-8x incident; use 2x for far-field, more for near
    P_ref_kpa = P_kpa * (2.0 + 6.0 * math.exp(-0.5 * Z))
    P_max_mpa = max(P_ref_kpa / 1000.0, 0.001)
    # Positive phase duration (ms) — Kinney-Graham approximation
    td_ms = 980.0 * (1 + (Z/0.54)**10) / ((1 + (Z/0.02)**3) * (1 + (Z/0.74)**6) *
                                          math.sqrt(1 + (Z/6.9)**2)) * (W_kg ** (1.0/3.0))
    td_s = td_ms / 1000.0
    if td_s < 1e-5:
        td_s = 1e-5
    if td_s > t:
        td_s = t * 0.5
    # Build amplitude table (Friedlander) — sample 30 points
    b = 1.0
    n_pts = 30
    pts = []
    for i in range(n_pts + 1):
        ti = (td_s * i / n_pts)
        if ti >= td_s:
            amp = 0.0
        else:
            amp = (1.0 - ti/td_s) * math.exp(-b * ti/td_s)
        pts.append((ti, amp))
    # After td_s: amp = 0 (no negative phase modeled)
    pts.append((t, 0.0))
    amp_data = ", ".join("({:.6e}, {:.6e})".format(ti, ai) for ti, ai in pts)

    # Note: Pressure with negative magnitude pushes INTO surface (compressive)
    # For air blast, the wave pushes plate downward (-z normal direction)
    # We use Pressure on BLAST_SURF with magnitude = P_max_mpa (positive = compressive into surface)
    return f"""
# === Friedlander air-blast load ===
# TNT = {tnt_kg} kg, standoff = {standoff_mm} mm, scaled distance Z = {Z:.3f} m/kg^(1/3)
# Peak reflected pressure = {P_max_mpa:.3f} MPa, positive phase td = {td_s*1000:.2f} ms

mdb.models['{model_name}'].ExplicitDynamicsStep(
    name='Step-1', previous='Initial',
    timePeriod={t}, description='Explicit blast dynamics')

a = mdb.models['{model_name}'].rootAssembly

# Boundary: clamp all four plate edges
mdb.models['{model_name}'].EncastreBC(
    name='Fixed', createStepName='Initial',
    region=a.instances['Part-1-1'].sets['FIXED_EDGES'])

# Friedlander tabular amplitude
mdb.models['{model_name}'].TabularAmplitude(
    name='BlastAmp', timeSpan=STEP, smooth=SOLVER_DEFAULT,
    data=({amp_data},))

# Pressure on BLAST_SURF (magnitude scaled by amplitude)
mdb.models['{model_name}'].Pressure(
    name='AirBlast', createStepName='Step-1',
    region=a.instances['Part-1-1'].surfaces['BLAST_SURF'],
    magnitude={P_max_mpa}, amplitude='BlastAmp',
    distributionType=UNIFORM)

# Field outputs (include PEEQ for plastic strain, ALLPD for plastic dissipation)
mdb.models['{model_name}'].fieldOutputRequests['F-Output-1'].setValues(
    variables=('S', 'PE', 'PEEQ', 'U', 'V', 'A'), numIntervals=20)

# History outputs: track center node, energies
try:
    mdb.models['{model_name}'].HistoryOutputRequest(
        name='TIP', createStepName='Step-1',
        region=a.instances['Part-1-1'].sets['TIP_NODES'],
        variables=('U3', 'V3', 'A3'))
except (KeyError, Exception):
    pass

mdb.models['{model_name}'].HistoryOutputRequest(
    name='Energy', createStepName='Step-1',
    variables=('ALLKE', 'ALLIE', 'ALLPD', 'ALLSE'))
"""



def _why_no_inp(workdir: Path) -> tuple[str, str]:
    """Say what actually stopped the build, instead of naming a file to read.

    Three things are on disk and none of them was being looked at.

    A dispatched call can take the Abaqus kernel down: `FluidPipeSection` with a
    step-scoped region raises EXCEPTION_ACCESS_VIOLATION out of ABQcaeK.exe,
    which is not a Python exception, so the deck's own gates never run and
    selectors.log just stops. The launcher returns 0 either way, so the only
    signal is the missing .inp — and the old message for that was "check the
    log", with an empty snippet and a suggestion to simplify the geometry, which
    is advice for a different problem entirely.

    selectors.log's last line names the feature or condition that was being
    built when it stopped, which is the single most useful thing to say.
    """
    reasons: list[str] = []
    detail: list[str] = []

    log = workdir / "build_model_script.log"
    text = log.read_text(encoding="utf-8", errors="replace") if log.exists() else ""
    fort = workdir / "fort.7"
    kernel = fort.read_text(encoding="utf-8", errors="replace") if fort.exists() else ""
    if "EXCEPTION_ACCESS_VIOLATION" in text or "EXCEPTION_ACCESS_VIOLATION" in kernel:
        reasons.append(
            "the Abaqus kernel crashed (EXCEPTION_ACCESS_VIOLATION in "
            "ABQcaeK.exe). That is a crash inside Abaqus itself, not a bad "
            "spec value — no Python exception is raised and no gate in the "
            "generated deck can catch it")

    selectors = workdir / "selectors.log"
    if selectors.exists():
        lines = [ln.strip() for ln in
                 selectors.read_text(encoding="utf-8", errors="replace").splitlines()
                 if ln.strip()]
        if lines:
            detail.append("selectors.log stops after: %s" % lines[-1])
            reasons.append("it stopped while building %s"
                           % lines[-1].split(":", 1)[-1].strip()[:120])

    if text:
        errors = [ln.strip() for ln in text.splitlines()
                  if "Error" in ln or "error:" in ln]
        if errors:
            detail.append("abaqus said: %s" % errors[-1][:300])

    if not reasons:
        reasons.append("no kernel crash and no refusal in selectors.log, so "
                       "the deck ran to the end without writing the file")
    return ("; ".join(reasons) + ". Full output: %s" % log,
            "\n".join(detail)[-2000:])


def _run_cae_nougui(script_path: Path, workdir: Path, abaqus_release: str) -> None:
    """Execute abaqus cae noGUI=<script> and capture output."""
    log_path = workdir / "build_model_script.log"
    from tools.abaqus_cmd import get_abaqus_cmd
    cmd = [get_abaqus_cmd(), "cae", f"noGUI={script_path}", "--", str(workdir), "spec"]
    try:
        result = subprocess.run(
            cmd,
            cwd=str(workdir),
            capture_output=True,
            text=True, errors='replace', encoding='utf-8',
            # Without this the child inherits the MCP server's protocol pipe and
            # deadlocks on Windows.
            stdin=subprocess.DEVNULL,
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


# ---------------------------------------------------------------------------
# Build identity: what the deck on disk actually depends on
# ---------------------------------------------------------------------------

MANIFEST_NAME = "build_manifest.json"


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _resolve_custom_src(spec: dict, spec_path: Path) -> Path:
    raw = Path(spec["geometry"]["inp_path"])
    src = raw if raw.is_absolute() else Path(spec_path).parent / raw
    return src.resolve()


def _build_fingerprint(spec: dict, spec_path: Path, workdir: Path) -> dict:
    """Everything the deck depends on, hashed.

    Generator identity is the sha256 of the CAE script this generator emits
    for this spec — NOT a hash of this module's bytes. Comparing emitted
    script bytes catches exactly the code changes that would alter the deck,
    and does not invalidate every cache on a comment or a reformat. The
    script embeds the workdir path, so a moved run directory reads as a miss,
    which is the safe direction. For custom_inp the script is a constant
    placeholder; source_inp_sha256 carries the identity instead.
    """
    from tools.abaqus_cmd import detect_abaqus_release

    fingerprint = {
        "spec_sha256": hashlib.sha256(
            json.dumps(spec, sort_keys=True, default=str).encode()).hexdigest(),
        # Probed, not asserted — and None (no solver on this machine) is a
        # value like any other: it must match None to reuse.
        "abaqus_release_probed": detect_abaqus_release(),
    }
    if not _is_v2(spec) and spec["geometry"]["type"] == "custom_inp":
        src = _resolve_custom_src(spec, spec_path)
        fingerprint["source_inp_sha256"] = _sha256_file(src) if src.exists() else None
    else:
        import tempfile

        probe_dir = Path(tempfile.mkdtemp(prefix="abq_fp_probe_"))
        try:
            probe = probe_dir / "probe.py"
            _write_cae_script(spec, probe, workdir, spec_path)
            fingerprint["generator_script_sha256"] = _sha256_file(probe)
        finally:
            shutil.rmtree(probe_dir, ignore_errors=True)
        fingerprint["imported_files_sha256"] = _imported_files_sha256(
            spec, spec_path)
    return fingerprint


def _imported_files_sha256(spec: dict, spec_path: Path) -> dict | None:
    """Hash the CONTENTS of every file a `{file:}` in the spec points at.

    The generated script embeds the resolved path, not the bytes, so a geometry
    file edited in place leaves the script identical and the cache would hand
    back a deck built from the old shape. That is the custom_inp bug this
    module already documents at the top of `build_model` -- source edited
    100N -> 900N, rerun, cached=True, COMPLETED, stale physics -- and an
    `import:` reintroduces it with geometry instead of loads.

    None rather than {} when there is nothing to hash, so a spec that gains its
    first import reads as a miss rather than matching an old manifest.
    """
    if not _is_v2(spec):
        return None
    from runner.build_v2 import imported_files

    try:
        paths = imported_files(spec, spec_path.parent if spec_path else None)
    except Exception:
        # A path that cannot be resolved is a build-time refusal with a proper
        # message; here it just means there is nothing to vouch for.
        return None
    if not paths:
        return None
    return dict((path, _sha256_file(Path(path))) for path in sorted(paths))


def _write_build_manifest(workdir: Path, inp_path: Path, fingerprint: dict) -> None:
    manifest = dict(fingerprint)
    manifest["inp_sha256"] = _sha256_file(inp_path)
    (workdir / MANIFEST_NAME).write_text(
        json.dumps(manifest, indent=2), encoding="utf-8")


def _cache_verdict(workdir: Path, inp_path: Path, fresh: dict) -> str | None:
    """None = proven reuse. Otherwise the plain-Chinese reason to rebuild."""
    manifest_path = workdir / MANIFEST_NAME
    if not manifest_path.exists():
        return "该目录没有构建指纹（旧缓存或外来 deck），无法证明它对应当前 spec"
    try:
        stored = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "构建指纹文件损坏，无法证明缓存对应当前 spec"
    labels = {
        "spec_sha256": "spec 内容",
        "generator_script_sha256": "建模脚本生成器",
        "abaqus_release_probed": "检测到的 Abaqus 版本",
        "source_inp_sha256": "源 .inp 文件内容",
    }
    for key, label in labels.items():
        if (key in fresh or key in stored) and stored.get(key) != fresh.get(key):
            return "%s已变化" % label
    if stored.get("inp_sha256") != _sha256_file(inp_path):
        return "run 目录里的 .inp 与构建指纹不符（deck 被绕过本工具修改过）"
    return None


def _build_custom_inp(spec: dict, spec_path: Path, workdir: Path, inp_path: Path, run_id: str) -> dict:
    """Copy an existing .inp into the run directory without launching Abaqus/CAE."""
    raw_src = Path(spec["geometry"]["inp_path"])
    src = raw_src if raw_src.is_absolute() else spec_path.parent / raw_src
    src = src.resolve()
    if not src.exists():
        raise AbaqusAgentError(ErrorCode.FILE_NOT_FOUND, f"custom_inp source not found: {src}")
    if src.suffix.lower() != ".inp":
        raise AbaqusAgentError(ErrorCode.BUILD_FAILED, f"custom_inp must point to a .inp file: {src}")

    if src != inp_path.resolve():
        shutil.copyfile(src, inp_path)
    (workdir / "build_model_script.py").write_text(
        "# custom inp - no CAE script needed\n",
        encoding="utf-8",
    )

    # Same multi-part preview mesh the CAE path produces, so the workbench
    # 3D preview lights up on the first run — not only on cache-hit rebuilds.
    mesh_path = _write_preview_mesh(workdir, inp_path)

    return {
        "workdir": workdir,
        "cae_path": workdir / f"{spec['meta']['model_name']}.cae",
        "inp_path": inp_path,
        "source_inp_path": src,
        "run_id": run_id,
        "cached": False,
        "custom_inp": True,
        "preview_mesh": mesh_path.name if mesh_path else None,
    }


def _run_id(spec: dict) -> str:
    """Deterministic run ID from spec content + release.

    One definition, in core.helpers. This used to be a second copy of the
    hash, and core.helpers.make_run_id had drifted to hashing the raw YAML
    text instead -- so the id the API reported and the directory this creates
    were different strings for the same run.
    """
    from core.helpers import run_id_for_spec
    return run_id_for_spec(spec)


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
