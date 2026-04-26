"""
shell_elements.py
-----------------
Shell geometry code generator for Abaqus CAE noGUI scripts.

Generates planar shell parts with S4R/S3 elements.
Supports rectangular plates with optional cutouts.
"""

from __future__ import annotations


def generate_shell_plate(geo: dict, model_name: str) -> str:
    """
    Generate CAE Python code for a shell plate geometry.

    Parameters (from spec.geometry):
        L          : length (x-direction)
        W          : width (y-direction)
        thickness  : shell thickness
        seed_size  : mesh seed size
        R          : optional hole radius (centered at L/2, W/2)
    """
    L = geo["L"]
    W = geo["W"]
    thickness = geo.get("thickness", 1.0)
    seed = geo.get("seed_size", min(L, W) / 10)
    R = geo.get("R", 0)

    hole_code = ""
    if R > 0:
        hole_code = f"""
s.CircleByCenterPerimeter(center=({L/2}, {W/2}), point1=({L/2 + R}, {W/2}))
"""

    return f"""
# ── Shell Plate Geometry (Premium) ──
p = mdb.models['{model_name}'].Part(name='Part-1', dimensionality=THREE_D,
    type=DEFORMABLE_BODY)
s = mdb.models['{model_name}'].ConstrainedSketch(name='__profile__', sheetSize=max({L}, {W})*2)
s.rectangle(point1=(0.0, 0.0), point2=({L}, {W}))
{hole_code}
p.BaseShell(sketch=s)
del mdb.models['{model_name}'].sketches['__profile__']

# Sets
p.Set(name='ALL', faces=p.faces)
p.Set(name='FIXED_END', edges=p.edges.getByBoundingBox(
    xMin=-0.01, xMax=0.01, yMin=-0.01, yMax={W}+0.01))
p.Set(name='LOAD_END', edges=p.edges.getByBoundingBox(
    xMin={L}-0.01, xMax={L}+0.01, yMin=-0.01, yMax={W}+0.01))

# Shell Section (override the default solid section)
mdb.models['{model_name}'].HomogeneousShellSection(
    name='ShellSection-1',
    material='{model_name}_mat' if '{model_name}_mat' in list(mdb.models['{model_name}'].materials.keys()) else list(mdb.models['{model_name}'].materials.keys())[0],
    thickness={thickness},
    idealization=NO_IDEALIZATION,
    poissonDefinition=DEFAULT,
    thicknessModulus=None,
    temperature=GRADIENT,
    useDensity=OFF,
    integrationRule=SIMPSON,
    numIntPts=5)

p.SectionAssignment(
    region=p.sets['ALL'],
    sectionName='ShellSection-1',
    offset=0.0,
    offsetType=MIDDLE_SURFACE,
    offsetField='',
    thicknessAssignment=FROM_SECTION)

# Mesh with S4R elements
elemType1 = mesh.ElemType(elemCode=S4R, elemLibrary=STANDARD,
    secondOrderAccuracy=OFF, hourglassControl=DEFAULT)
elemType2 = mesh.ElemType(elemCode=S3, elemLibrary=STANDARD)
p.setElementType(regions=(p.faces,), elemTypes=(elemType1, elemType2))
p.seedPart(size={seed}, deviationFactor=0.1, minSizeFactor=0.1)
p.generateMesh()
"""


def get_shell_section_override() -> str:
    """Return code that prevents the default solid section from being created."""
    return "# Shell section is handled by shell_elements.py - skip default solid section"
