"""
beam_elements.py
----------------
Beam geometry code generator for Abaqus CAE noGUI scripts.

Generates wire parts with B31/B32 beam elements.
Supports frame structures defined by nodes and connections.
"""

from __future__ import annotations


def generate_beam_frame(geo: dict, model_name: str) -> str:
    """
    Generate CAE Python code for a beam frame geometry.

    Parameters (from spec.geometry):
        L          : total length (for simple cantilever beam)
        W          : optional height for portal frame
        seed_size  : mesh seed size
        profile    : beam cross-section profile dict
        points     : list of [x, y, z] node coordinates
        connections: list of [i, j] element connectivity
        num_segments: number of segments for simple beam
    """
    L = geo.get("L", 100.0)
    seed = geo.get("seed_size", L / 10)
    profile = geo.get("profile", {"type": "rectangular", "width": 10.0, "height": 10.0})
    points = geo.get("points", None)
    connections = geo.get("connections", None)

    # Profile generation
    profile_code = _generate_profile_code(profile, model_name)

    if points and connections:
        # Arbitrary frame
        wire_code = _generate_frame_wires(points, connections, model_name)
    else:
        # Simple straight beam along x-axis
        num_seg = geo.get("num_segments", 10)
        step_len = L / num_seg
        wire_code = f"""
p = mdb.models['{model_name}'].Part(name='Part-1', dimensionality=THREE_D,
    type=DEFORMABLE_BODY)
e_pts = [(ii * {step_len}, 0.0, 0.0) for ii in range({num_seg} + 1)]
for ii in range(len(e_pts) - 1):
    p.WirePolyLine(points=(e_pts[ii], e_pts[ii+1]), mergeType=MERGE,
        meshable=ON)
"""

    return f"""
# ── Beam Frame Geometry (Premium) ──
{wire_code}

# Sets
p.Set(name='ALL', edges=p.edges)
# Fixed end: nodes at x=0
p.Set(name='FIXED_END', vertices=p.vertices.getByBoundingBox(
    xMin=-0.01, xMax=0.01, yMin=-1e6, yMax=1e6, zMin=-1e6, zMax=1e6))
# Load end: nodes at x=L
p.Set(name='LOAD_END', vertices=p.vertices.getByBoundingBox(
    xMin={L}-0.01, xMax={L}+0.01, yMin=-1e6, yMax=1e6, zMin=-1e6, zMax=1e6))

# Beam Profile
{profile_code}

# Beam Section
mdb.models['{model_name}'].BeamSection(
    name='BeamSection-1',
    integration=DURING_ANALYSIS,
    poissonRatio=0.0,
    profile='BeamProfile-1',
    material=mdb.models['{model_name}'].materials.keys()[0],
    temperatureVar=LINEAR,
    consistentMassMatrix=False)

p.SectionAssignment(
    region=p.sets['ALL'],
    sectionName='BeamSection-1',
    offset=0.0,
    offsetType=MIDDLE_SURFACE,
    offsetField='',
    thicknessAssignment=FROM_SECTION)

# Beam section orientation
p.assignBeamSectionOrientation(
    region=p.sets['ALL'],
    method=N1_COSINES,
    n1=(0.0, 0.0, -1.0))

# Mesh with B31 elements
elemType = mesh.ElemType(elemCode=B31, elemLibrary=STANDARD)
p.setElementType(regions=(p.edges,), elemTypes=(elemType,))
p.seedPart(size={seed}, deviationFactor=0.1, minSizeFactor=0.1)
p.generateMesh()
"""


def _generate_profile_code(profile: dict, model_name: str) -> str:
    """Generate Abaqus beam profile definition code."""
    ptype = profile.get("type", "rectangular")

    if ptype == "rectangular":
        w = profile.get("width", 10.0)
        h = profile.get("height", 10.0)
        return f"""
mdb.models['{model_name}'].RectangularProfile(
    name='BeamProfile-1', a={w}, b={h})
"""
    elif ptype == "circular":
        r = profile.get("radius", 5.0)
        return f"""
mdb.models['{model_name}'].CircularProfile(
    name='BeamProfile-1', r={r})
"""
    elif ptype == "I_beam":
        fw = profile.get("flange_width", 20.0)
        ft = profile.get("flange_thickness", 2.0)
        wt = profile.get("web_thickness", 1.5)
        h = profile.get("height", 30.0)
        return f"""
mdb.models['{model_name}'].IProfile(
    name='BeamProfile-1',
    l={h/2}, h={h/2}, b1={fw}, b2={fw},
    t1={ft}, t2={ft}, s={wt})
"""
    elif ptype == "pipe":
        r = profile.get("radius", 10.0)
        wt = profile.get("wall_thickness", 1.0)
        return f"""
mdb.models['{model_name}'].PipeProfile(
    name='BeamProfile-1', r={r}, t={wt})
"""
    else:
        # Default to rectangular
        return f"""
mdb.models['{model_name}'].RectangularProfile(
    name='BeamProfile-1', a=10.0, b=10.0)
"""


def _generate_frame_wires(points: list, connections: list, model_name: str) -> str:
    """Generate wire geometry from node coordinates and connectivity."""
    pts_code = "pts = [\n"
    for p in points:
        if len(p) == 2:
            pts_code += f"    ({p[0]}, {p[1]}, 0.0),\n"
        else:
            pts_code += f"    ({p[0]}, {p[1]}, {p[2]}),\n"
    pts_code += "]\n"

    conn_code = "conns = [\n"
    for c in connections:
        conn_code += f"    ({c[0]}, {c[1]}),\n"
    conn_code += "]\n"

    return f"""
p = mdb.models['{model_name}'].Part(name='Part-1', dimensionality=THREE_D,
    type=DEFORMABLE_BODY)
{pts_code}
{conn_code}
for i, j in conns:
    p.WirePolyLine(points=(pts[i], pts[j]), mergeType=MERGE, meshable=ON)
"""
