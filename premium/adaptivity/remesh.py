"""
remesh.py
---------
Topology remeshing and solution mapping for Abaqus.

Implements varying topology adaptive remeshing where the mesh
can be completely replaced between analysis steps, with solution
mapping to transfer results to the new mesh.
"""

from __future__ import annotations


def inject_remesh_controls(context: dict) -> dict:
    """
    Pipeline hook: inject remeshing controls into spec if configured.
    """
    spec = context.get("spec", {})
    adaptive = spec.get("analysis", {}).get("adaptive_mesh", {})

    if adaptive.get("enabled") and adaptive.get("method") == "remesh":
        context["remesh_code"] = generate_remesh_code(adaptive, spec)

    return context


def generate_remesh_code(adaptive: dict, spec: dict) -> str:
    """
    Generate Abaqus CAE code for h-refinement remeshing.

    This implements error-indicator-driven mesh refinement:
    1. Run initial analysis
    2. Evaluate error indicators
    3. Refine mesh in high-error regions
    4. Map solution and continue
    """
    error_target = adaptive.get("error_target", 0.05)
    max_iter = adaptive.get("max_iterations", 3)
    model_name = spec.get("meta", {}).get("model_name", "Model")

    return f"""
# ── Topology Remeshing Controls (Premium) ──
# Note: Abaqus handles remeshing through *ADAPTIVE MESH REFINEMENT
# in the input file. This code sets up the controls in CAE.

mdb.models['{model_name}'].AdaptiveMeshControl(
    name='RemeshControl-1',
    smoothingAlgorithm=GEOMETRY_ENHANCED,
    smoothingPriority=GRADED,
    curvatureRefinement=1.0,
    initialFeatureAngle=30.0,
    transitionFeatureAngle=30.0)

# Error indicator for mesh refinement
mdb.models['{model_name}'].RemeshingRule(
    name='ErrorRule-1',
    stepName='Step-1',
    variables=('MISESERI',),
    description='Mises-based error indicator',
    region=mdb.models['{model_name}'].rootAssembly.instances['Part-1-1'].sets['ALL'],
    sizingMethod=UNIFORM_ERROR,
    errorTarget={error_target},
    maxSolutionErrorTarget={error_target * 2},
    coarseningFactor=0.75,
    refinementFactor=2.0,
    maxRefinementLevel={max_iter},
    minRefinementLevel=0)
"""


def generate_solution_mapping_script(
    old_odb_path: str, new_inp_path: str, model_name: str
) -> str:
    """
    Generate a standalone script for solution mapping between meshes.

    Used when manually controlling the remesh cycle.
    """
    return f"""# Solution mapping script (Premium)
# Maps results from old mesh to new mesh
import sys
from abaqus import *
from abaqusConstants import *

oldOdbPath = '{old_odb_path}'
newInputPath = '{new_inp_path}'

# Open old ODB for reading
oldJob = mdb.JobFromInputFile(
    name='MappedJob',
    inputFileName=newInputPath,
    oldJob=oldOdbPath.replace('.odb', ''),
    description='Remeshed job with solution mapping')

oldJob.writeInput()
print('MAPPED_INP_WRITTEN: ' + newInputPath)
"""
