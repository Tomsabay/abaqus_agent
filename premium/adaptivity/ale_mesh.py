"""
ale_mesh.py
-----------
ALE (Arbitrary Lagrangian-Eulerian) adaptive mesh code generator.

ALE adaptive meshing maintains a high-quality mesh during large
deformation by sweeping and smoothing the mesh periodically.
"""

from __future__ import annotations


def inject_ale_adaptive_mesh(context: dict) -> dict:
    """
    Pipeline hook: inject ALE adaptive mesh controls into the spec
    if adaptive_mesh is configured.

    Called as a pre_build hook by the orchestrator.
    """
    spec = context.get("spec", {})
    adaptive = spec.get("analysis", {}).get("adaptive_mesh", {})

    if adaptive.get("enabled") and adaptive.get("method") == "ale":
        context["adaptive_mesh_code"] = generate_ale_code(adaptive, spec)

    return context


def generate_ale_code(adaptive: dict, spec: dict) -> str:
    """
    Generate Abaqus CAE Python code for ALE adaptive meshing.

    ALE parameters:
        frequency   : mesh sweep frequency (every N increments)
        smoothing   : smoothing method (volume/laplacian/equipotential)
    """
    frequency = adaptive.get("frequency", 10)
    smoothing = adaptive.get("smoothing", "volume")
    model_name = spec.get("meta", {}).get("model_name", "Model")

    smoothing_map = {
        "volume": "GEOMETRY_ENHANCED",
        "laplacian": "MESHSMOOTHING",
        "equipotential": "STANDARD",
    }
    smooth_method = smoothing_map.get(smoothing, "GEOMETRY_ENHANCED")

    return f"""
# ── ALE Adaptive Mesh (Premium) ──
# Enable adaptive mesh domain on the entire part instance
a = mdb.models['{model_name}'].rootAssembly
region = a.instances['Part-1-1'].sets['ALL']

mdb.models['{model_name}'].AdaptiveMeshDomain(
    region=region,
    controls=None,
    frequency={frequency},
    meshSweeps=1)

# Adaptive mesh controls
mdb.models['{model_name}'].AdaptiveMeshControl(
    name='AdaptiveControl-1',
    smoothingAlgorithm={smooth_method},
    smoothingPriority=UNIFORM,
    initialFeatureAngle=30.0,
    transitionFeatureAngle=30.0,
    momentumAdvection=ELEMENT_CENTER_PROJECTION,
    meshingPredictor=CURRENT,
    curvatureRefinement=1.0)

# Apply controls to the domain
mdb.models['{model_name}'].adaptiveMeshDomains['Part-1-1.ALL'].setValues(
    controls='AdaptiveControl-1')
"""


def generate_ale_explicit_code(adaptive: dict, spec: dict) -> str:
    """
    Generate ALE code specifically for Explicit dynamics.

    In explicit, ALE is commonly used for high-deformation problems
    like impact, forming, and penetration.
    """
    frequency = adaptive.get("frequency", 5)
    model_name = spec.get("meta", {}).get("model_name", "Model")

    return f"""
# ── ALE Adaptive Mesh for Explicit (Premium) ──
a = mdb.models['{model_name}'].rootAssembly
region = a.instances['Part-1-1'].sets['ALL']

mdb.models['{model_name}'].AdaptiveMeshDomain(
    region=region,
    frequency={frequency},
    meshSweeps=3)

mdb.models['{model_name}'].AdaptiveMeshControl(
    name='ExplicitALE-1',
    smoothingAlgorithm=GEOMETRY_ENHANCED,
    smoothingPriority=GRADED,
    initialFeatureAngle=30.0,
    transitionFeatureAngle=30.0,
    momentumAdvection=ELEMENT_CENTER_PROJECTION,
    meshingPredictor=CURRENT,
    curvatureRefinement=1.0,
    volumetricSmoothingWeight=1.0,
    laplacianSmoothingWeight=0.0,
    equipotentialSmoothingWeight=0.0)
"""
