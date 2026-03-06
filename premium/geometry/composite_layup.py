"""
composite_layup.py
------------------
Composite layup geometry code generator for Abaqus CAE noGUI scripts.

Generates shell parts with CompositeLayup sections for
fiber-reinforced polymer (FRP) and laminated composite structures.
"""

from __future__ import annotations


def generate_composite_plate(geo: dict, model_name: str) -> str:
    """
    Generate CAE Python code for a composite plate with layup.

    Parameters (from spec.geometry):
        L          : length (x-direction)
        W          : width (y-direction)
        seed_size  : mesh seed size
        layup      : list of {material, thickness, orientation} dicts
    """
    L = geo["L"]
    W = geo["W"]
    seed = geo.get("seed_size", min(L, W) / 10)
    layup = geo.get("layup", [
        {"material": "CFRP", "thickness": 0.125, "orientation": 0},
        {"material": "CFRP", "thickness": 0.125, "orientation": 90},
        {"material": "CFRP", "thickness": 0.125, "orientation": 90},
        {"material": "CFRP", "thickness": 0.125, "orientation": 0},
    ])

    # Generate layup plies code
    plies_code = _generate_plies(layup, model_name)

    return f"""
# ── Composite Plate Geometry (Premium) ──
p = mdb.models['{model_name}'].Part(name='Part-1', dimensionality=THREE_D,
    type=DEFORMABLE_BODY)
s = mdb.models['{model_name}'].ConstrainedSketch(name='__profile__', sheetSize=max({L}, {W})*2)
s.rectangle(point1=(0.0, 0.0), point2=({L}, {W}))
p.BaseShell(sketch=s)
del mdb.models['{model_name}'].sketches['__profile__']

# Sets
p.Set(name='ALL', faces=p.faces)
p.Set(name='FIXED_END', edges=p.edges.getByBoundingBox(
    xMin=-0.01, xMax=0.01, yMin=-0.01, yMax={W}+0.01))
p.Set(name='LOAD_END', edges=p.edges.getByBoundingBox(
    xMin={L}-0.01, xMax={L}+0.01, yMin=-0.01, yMax={W}+0.01))

# Composite Layup Section
layup = mdb.models['{model_name}'].parts['Part-1'].CompositeLayup(
    name='CompositeLayup-1',
    description='Auto-generated composite layup',
    elementType=SHELL,
    offsetType=MIDDLE_SURFACE,
    symmetric=False,
    thicknessAssignment=FROM_SECTION)

layup.Section(
    preIntegrate=OFF,
    integrationRule=SIMPSON,
    poissonDefinition=DEFAULT,
    thicknessModulus=None,
    temperature=GRADIENT,
    useDensity=OFF)

layup.ReferenceOrientation(
    orientationType=GLOBAL,
    localCsys=None,
    fieldName='',
    additionalRotationType=ROTATION_NONE,
    angle=0.0,
    additionalRotationField='',
    axis=AXIS_3,
    stackDirection=STACK_3)

{plies_code}

# Mesh with S4R elements (composite-capable)
elemType1 = mesh.ElemType(elemCode=S4R, elemLibrary=STANDARD,
    secondOrderAccuracy=OFF, hourglassControl=DEFAULT)
elemType2 = mesh.ElemType(elemCode=S3, elemLibrary=STANDARD)
p.setElementType(regions=(p.faces,), elemTypes=(elemType1, elemType2))
p.seedPart(size={seed}, deviationFactor=0.1, minSizeFactor=0.1)
p.generateMesh()
"""


def _generate_plies(layup: list[dict], model_name: str) -> str:
    """Generate CompositePly definitions for each ply in the layup."""
    code = ""
    for i, ply in enumerate(layup):
        mat_name = ply["material"]
        thickness = ply["thickness"]
        orientation = ply.get("orientation", 0)
        ply_name = f"Ply-{i+1}"

        code += f"""
layup.CompositePly(
    suppressed=False,
    plyName='{ply_name}',
    region=mdb.models['{model_name}'].parts['Part-1'].sets['ALL'],
    material='{mat_name}',
    thicknessType=SPECIFY_THICKNESS,
    thickness={thickness},
    orientationType=SPECIFY_ORIENT,
    orientationValue={orientation},
    additionalRotationType=ROTATION_NONE,
    additionalRotationField='',
    axis=AXIS_3,
    angle=0.0,
    numIntPoints=3)
"""
    return code
