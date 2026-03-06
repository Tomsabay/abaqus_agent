"""
cohesive_elements.py
--------------------
Cohesive element geometry code generator for Abaqus CAE noGUI scripts.

Generates cohesive zone models for delamination, adhesive joints,
and crack propagation simulations.
"""

from __future__ import annotations


def generate_cohesive_layer(geo: dict, model_name: str) -> str:
    """
    Generate CAE Python code for a cohesive layer between two substrates.

    Parameters (from spec.geometry):
        L          : length of substrate
        W          : width of substrate
        H          : height of each substrate (top & bottom)
        seed_size  : mesh seed size
        cohesive_thickness : cohesive layer thickness
    """
    L = geo["L"]
    W = geo["W"]
    H = geo.get("H", 5.0)
    seed = geo.get("seed_size", min(L, W) / 10)
    coh_t = geo.get("cohesive_thickness", 0.01)

    return f"""
# ── Cohesive Layer Geometry (Premium) ──

# Bottom substrate
p_bot = mdb.models['{model_name}'].Part(name='Bottom', dimensionality=THREE_D,
    type=DEFORMABLE_BODY)
s = mdb.models['{model_name}'].ConstrainedSketch(name='__profile__', sheetSize=200.0)
s.rectangle(point1=(0.0, 0.0), point2=({W}, {H}))
p_bot.BaseSolidExtrude(sketch=s, depth={L})
del mdb.models['{model_name}'].sketches['__profile__']
p_bot.Set(name='ALL', cells=p_bot.cells)
p_bot.Set(name='TOP_FACE', faces=p_bot.faces.getByBoundingBox(
    yMin={H}-0.01, yMax={H}+0.01))
p_bot.seedPart(size={seed}, deviationFactor=0.1, minSizeFactor=0.1)
p_bot.generateMesh()

# Top substrate
p_top = mdb.models['{model_name}'].Part(name='Top', dimensionality=THREE_D,
    type=DEFORMABLE_BODY)
s = mdb.models['{model_name}'].ConstrainedSketch(name='__profile__', sheetSize=200.0)
s.rectangle(point1=(0.0, 0.0), point2=({W}, {H}))
p_top.BaseSolidExtrude(sketch=s, depth={L})
del mdb.models['{model_name}'].sketches['__profile__']
p_top.Set(name='ALL', cells=p_top.cells)
p_top.Set(name='BOTTOM_FACE', faces=p_top.faces.getByBoundingBox(
    yMin=-0.01, yMax=0.01))
p_top.seedPart(size={seed}, deviationFactor=0.1, minSizeFactor=0.1)
p_top.generateMesh()

# Cohesive layer
p_coh = mdb.models['{model_name}'].Part(name='Cohesive', dimensionality=THREE_D,
    type=DEFORMABLE_BODY)
s = mdb.models['{model_name}'].ConstrainedSketch(name='__profile__', sheetSize=200.0)
s.rectangle(point1=(0.0, 0.0), point2=({W}, {coh_t}))
p_coh.BaseSolidExtrude(sketch=s, depth={L})
del mdb.models['{model_name}'].sketches['__profile__']
p_coh.Set(name='ALL', cells=p_coh.cells)
p_coh.seedPart(size={seed}, deviationFactor=0.1, minSizeFactor=0.1)

# Cohesive element type
elemType = mesh.ElemType(elemCode=COH3D8, elemLibrary=STANDARD,
    viscosity=1e-5)
p_coh.setElementType(regions=(p_coh.cells,), elemTypes=(elemType,))
p_coh.generateMesh()

# Cohesive Section
mdb.models['{model_name}'].CohesiveSection(
    name='CohesiveSection-1',
    material=mdb.models['{model_name}'].materials.keys()[0],
    response=TRACTION_SEPARATION,
    outOfPlaneThickness=None)

p_coh.SectionAssignment(
    region=p_coh.sets['ALL'],
    sectionName='CohesiveSection-1',
    offset=0.0,
    offsetType=MIDDLE_SURFACE,
    offsetField='',
    thicknessAssignment=FROM_SECTION)

# Assembly with proper positioning
a = mdb.models['{model_name}'].rootAssembly
a.DatumCsysByDefault(CARTESIAN)
inst_bot = a.Instance(name='Bottom-1', part=p_bot, dependent=ON)
inst_coh = a.Instance(name='Cohesive-1', part=p_coh, dependent=ON)
a.translate(instanceList=('Cohesive-1',), vector=(0.0, {H}, 0.0))
inst_top = a.Instance(name='Top-1', part=p_top, dependent=ON)
a.translate(instanceList=('Top-1',), vector=(0.0, {H + coh_t}, 0.0))

# Tie constraints
a.Set(name='BOT_TOP', faces=inst_bot.faces.getByBoundingBox(
    yMin={H}-0.01, yMax={H}+0.01))
a.Set(name='COH_BOT', faces=inst_coh.faces.getByBoundingBox(
    yMin={H}-0.01, yMax={H}+0.01))
a.Set(name='COH_TOP', faces=inst_coh.faces.getByBoundingBox(
    yMin={H+coh_t}-0.01, yMax={H+coh_t}+0.01))
a.Set(name='TOP_BOT', faces=inst_top.faces.getByBoundingBox(
    yMin={H+coh_t}-0.01, yMax={H+coh_t}+0.01))

mdb.models['{model_name}'].Tie(name='Tie-BotCoh',
    main=a.sets['BOT_TOP'], secondary=a.sets['COH_BOT'],
    positionToleranceMethod=COMPUTED, adjust=ON, tieRotations=ON)
mdb.models['{model_name}'].Tie(name='Tie-CohTop',
    main=a.sets['COH_TOP'], secondary=a.sets['TOP_BOT'],
    positionToleranceMethod=COMPUTED, adjust=ON, tieRotations=ON)

# Fixed BC region
a.Set(name='FIXED_END', faces=inst_bot.faces.getByBoundingBox(
    xMin=-0.01, xMax=0.01))
a.Set(name='LOAD_END', faces=inst_top.faces.getByBoundingBox(
    xMin={L}-0.01, xMax={L}+0.01))

# For the main script: use Part-1 = Bottom for section assignment compatibility
# The cohesive model uses a multi-part assembly
"""
