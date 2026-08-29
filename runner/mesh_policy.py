"""Which element, which shape, which technique -- the lookup tables.

Every entry here is looked up, never derived from the element name. A family
missing from a table is refused by name with what to do about it, because the
alternative was a KeyError from inside the generator, or worse: Abaqus quietly
substituting a default element for the one the spec asked for and nothing
saying so.

Separated from the compiler because these are decisions about Abaqus, not about
the spec language -- they change when a new element family is verified, not
when the dialect grows -- and because core/element_risk.py reasons about
DEFAULT_MESH_ELEMENT by name.
"""

from __future__ import annotations

from runner.spec_base import SpecError, _is_generic

# Abaqus/Explicit steps, by the CAE method that creates them. `Explicit` in the
# name is not the test: TempDisplacementDynamicsStep is an Explicit step and
# does not contain the word, and no Standard method does contain it.
_EXPLICIT_STEP_CALLS = frozenset((
    "ExplicitDynamicsStep",
    "TempDisplacementDynamicsStep",
))


def _element_library(spec: dict) -> str:
    """STANDARD or EXPLICIT, decided by the steps the spec declares.

    Not a spec key, because a model cannot hold both: Abaqus/Standard and
    Abaqus/Explicit steps do not coexist in one model, so there is no case where
    an author would legitimately want the other one.

    It used to be the constant "STANDARD", and that is a silent failure, not a
    formality. Measured on Abaqus 2021 with cases/explicit_impact: the deck the
    constant produced carried `*Element, type=C3D8R` -- the same line as the
    frozen v1 deck -- and no `*Section Controls`, because hourglassControl is
    only reachable on the EXPLICIT library. The job COMPLETED with no error,
    and the reaction force came out 33501 N against the frozen 31817 N, a 5.3%
    error on a case whose own tolerance is 5%.

    Lives here rather than in build_v2 because _library_for below is allowed to
    overrule it for one element, and a rule and its exception belong together.
    """
    for step_spec in spec.get("steps") or []:
        if _is_generic(step_spec) and str(step_spec.get("call")) in _EXPLICIT_STEP_CALLS:
            return "EXPLICIT"
    return "STANDARD"

# What a `mesh:` block with no `element:` key gets. Named rather than inlined
# because core/element_risk.py has to warn about it by name: this is a
# first-order reduced-integration hex, so the value a spec receives by saying
# nothing is the one measured at 90.5x the closed form on a bending bar (#72).
# Changing it would rewrite every deck built from a spec that omits the key,
# including frozen ones, so it is a separate decision from warning about it.
DEFAULT_MESH_ELEMENT = "C3D8R"

# Companion element for the wedge/tet cells a free mesh may produce. Abaqus
# refuses a hex-only element type on a mesh that is not all hex, and the
# failure surfaces as a meshing error a long way from its cause.
# The hex element the spec names, and the wedge and tet of the same family to
# hand Abaqus for the cells a sweep or a free mesh leaves behind. Abaqus wants
# all three in one setElementType call; giving only the hex lets it fall back to
# a default for the others, which is a different element than the spec asked
# for and nothing says so.
#
# Explicitly NOT a list of "supported elements" -- an element missing from here
# is refused by name with what to do about it (see _companions), because the
# alternative was an uncaught KeyError from inside the generator.
_COMPANION = {
    # stress / displacement
    "C3D8R": ("C3D6", "C3D4"),
    "C3D8": ("C3D6", "C3D4"),
    "C3D8I": ("C3D6", "C3D4"),
    "C3D8H": ("C3D6H", "C3D4H"),
    "C3D20R": ("C3D15", "C3D10"),
    "C3D20": ("C3D15", "C3D10"),
    # heat transfer / mass diffusion
    "DC3D8": ("DC3D6", "DC3D4"),
    "DC3D20": ("DC3D15", "DC3D10"),
    # coupled temperature-displacement
    "C3D8T": ("C3D6T", "C3D4T"),
    "C3D8RT": ("C3D6T", "C3D4T"),
    "C3D20RT": ("C3D15T", "C3D10T"),
    # coupled thermal-electrical
    "Q3D8": ("Q3D6", "Q3D4"),
    # piezoelectric
    "C3D8E": ("C3D6E", "C3D4E"),
    "C3D20E": ("C3D15E", "C3D10E"),
}

# The 2D half, kept separate because the shapes are different words: a quad's
# leftover is a triangle, not a wedge and a tet. Same doctrine as _COMPANION --
# looked up, never derived. The second-order quads pair with the MODIFIED
# triangle (CPE8 -> CPE6M, not CPE6), which is what Abaqus's own crack examples
# use and is not something the name would tell you.
_COMPANION_2D = {
    # plane strain
    "CPE4": ("CPE3",), "CPE4R": ("CPE3",), "CPE4I": ("CPE3",),
    "CPE4H": ("CPE3H",),
    "CPE8": ("CPE6M",), "CPE8R": ("CPE6M",),
    # plane stress
    "CPS4": ("CPS3",), "CPS4R": ("CPS3",), "CPS4I": ("CPS3",),
    "CPS8": ("CPS6M",), "CPS8R": ("CPS6M",),
    # axisymmetric
    "CAX4": ("CAX3",), "CAX4R": ("CAX3",), "CAX4I": ("CAX3",),
    "CAX8": ("CAX6M",), "CAX8R": ("CAX6M",),
    # heat transfer, planar and axisymmetric
    "DC2D4": ("DC2D3",), "DC2D8": ("DC2D6",),
    "DCAX4": ("DCAX3",), "DCAX8": ("DCAX6",),
}
# Shells. A shell's leftover is a triangle, like a quad's, but the pairing is
# not the 2D one and cannot be guessed: the second-order shells pair with
# STRI65, and S4R5 with S3R5 rather than S3.
#
# Continuum shells (SC8R and its family) are deliberately absent. They are hex
# SHAPES carrying a shell formulation, so they belong on a solid body, and
# putting them in this table would let a surface part ask for one and mesh
# nothing quietly -- the failure this whole layer exists to stop.
_COMPANION_SHELL = {
    "S4": ("S3",), "S4R": ("S3",),
    "S4R5": ("S3R5",),
    "S8R": ("STRI65",), "S8R5": ("STRI65",),
}

_TRI_PRIMARY = set()
for _companions in _COMPANION_2D.values():
    _TRI_PRIMARY.update(_companions)
for _companions in _COMPANION_SHELL.values():
    _TRI_PRIMARY.update(_companions)
# The plain second-order triangles, which are nobody's companion above but are
# elements a spec may legitimately ask for on their own.
_TRI_PRIMARY.update(("CPE6", "CPS6", "CAX6"))

# Every wedge and tet named above is an element in its own right, and a body
# with no hexes in it has to be meshed with one. Derived from the table rather
# than typed out a second time: a family added to _COMPANION becomes meshable
# as a tet in the same edit, and the two lists cannot drift apart.
_TET_PRIMARY = set(tet for _, tet in _COMPANION.values())
_WEDGE_PRIMARY = set(wedge for wedge, _ in _COMPANION.values())

# The modified tets, which are nobody's default companion -- Abaqus fills the
# tet slot of a linear family with C3D4 -- but are what its own documentation
# asks for under contact, because the plain C3D4 is far too stiff and C3D10's
# corner nodes carry no consistent contact pressure. Named here because a spec
# that asks for one is asking on purpose.
_TET_PRIMARY.update(("C3D10M", "C3D10H", "C3D4H"))

# The tets that DO have a family, derived from the companion table rather than
# retyped: an element that is some hex's tet has a hex to be inferred from.
_FAMILY_TETS = frozenset(tet for _wedge, tet in _COMPANION.values())


def _shape_before_element(elem_codes: tuple) -> bool:
    """Must setMeshControls come BEFORE setElementType for this element list?

    Setting the shape first is always correct, and it is not the order the
    generator has always emitted -- so it is done only where it is required.
    Reversing it everywhere would move the eleven deck hashes
    tests/test_frozen_model_sections.py pins and force twenty-seven
    unreproducible run directories to rebuild; that reversal is worth doing on
    its own, with the archiving that goes with it.

    Where it IS required, measured on Abaqus 2021: a tet-only element list is
    rejected while the region still carries the default HEX controls --

        The Hex shape associated with the regions does not have a valid element
        type. Select a type that supports the Hex shape or change the mesh
        controls to remove the presence of hex elements.

    C3D10 gets away with it because Abaqus fills the empty hex slot from its
    own family (C3D20/C3D15/C3D10). C3D10M has no family to fill it from, which
    is the same fact `_TET_PRIMARY.update(("C3D10M", ...))` above states: it is
    nobody's default companion. So the test is a property of the element, not a
    second list of names.
    """
    return len(elem_codes) == 1 and elem_codes[0] not in _FAMILY_TETS


# Second-order tets. Named rather than derived because "has a 10 in it" is a
# spelling rule, not an element property, and the next family will break it.
_QUADRATIC_TETS = frozenset(("C3D10", "C3D10M", "C3D10H", "C3D10MH",
                             "C3D10T", "C3D10MT"))


def _library_for(elem_codes: tuple, library: str) -> str:
    """STANDARD or EXPLICIT for this element list -- usually just `library`.

    C3D10M is the tet Abaqus's own documentation asks for under contact, and it
    is a legal Abaqus/Explicit element. But asking CAE for it through the
    EXPLICIT library does not produce it. Measured on Abaqus 2021 by writing the
    input file and reading the card back, which is the only witness that counts
    here -- MeshElement.type answers C3D4 even for an assignment that writes
    C3D10:

        mesh.ElemType(C3D10M, elemLibrary=EXPLICIT)  -> *Element, type=C3D4
                                                       96 nodes / 324 elements
        mesh.ElemType(C3D10M, elemLibrary=STANDARD)  -> *Element, type=C3D10M
                                                       577 nodes / 324 elements
        mesh.ElemType(C3D10, elemLibrary=STANDARD)   -> *Element, type=C3D10

    So the EXPLICIT library silently drops the element to a linear tet, and a
    linear tet is several times too stiff -- a wrong answer that meshes, solves
    and looks ordinary. The STANDARD library writes the card the deck needs, and
    `*Dynamic, Explicit` runs C3D10M perfectly well.

    The one thing the EXPLICIT library buys, and the reason _element_library
    exists at all, is hourglassControl -- which is meaningless on C3D10M: it has
    no reduced integration and no hourglass modes. So nothing is given up.

    The substitution is checked at run time rather than trusted; see
    _expect_second_order in the kernel runtime.
    """
    if (library == "EXPLICIT" and len(elem_codes) == 1
            and elem_codes[0] in _QUADRATIC_TETS
            and elem_codes[0] not in _FAMILY_TETS):
        return "STANDARD"
    return library

# Which techniques each shape can be meshed with. Abaqus refuses the rest, but
# it refuses them from inside the kernel, where the message names neither the
# part nor the spec key -- and a refusal that cannot be traced back to a line of
# the spec is not much better than a silent one.
#
# HEX keeps `free` even though free meshing is a tet/quad idea: it fails loudly
# and immediately, and the pre-existing decks in this repo rely on the mapping
# being passed straight through.
_SHAPE_TECHNIQUES = {
    "HEX": ("structured", "sweep", "free"),
    "TET": ("free",),
    "WEDGE": ("sweep",),
    # The 2D pair. QUAD is the planar analogue of HEX and takes the same three;
    # TRI, like TET, only free-meshes.
    "QUAD": ("structured", "sweep", "free"),
    "TRI": ("free",),
}

_TECHNIQUE_CONSTANT = {"structured": "STRUCTURED", "sweep": "SWEEP",
                       "free": "FREE"}


# What a part is, and which sequence holds its BODY. Everything downstream of
# a part -- the section assignment, the element type, the mesh controls -- acts
# on cells in 3D and on faces in 2D, and the difference is not cosmetic: a
# `Set(cells=p.cells)` on a planar part builds a set of ZERO cells and assigns a
# section to nothing, in silence. That is the same failure shape the IGES shell
# and the orphan mesh both produced, so it gets the same treatment -- the body
# attribute is chosen from the declared dimensionality, once, here.
#
# AXISYMMETRIC is planar in exactly this sense (a face in the r-z plane), which
# is why it shares the row rather than getting its own.
_DIMENSIONALITY = {
    "THREE_D": "cells",
    "TWO_D_PLANAR": "faces",
    "AXISYMMETRIC": "faces",
}


def _companions(part_name: str, element: str) -> tuple:
    """The wedge and tet to pair with the hex the spec named.

    An element with no entry used to raise a bare `KeyError: 'DC3D8'` out of the
    generator -- no part name, no spec key, nothing to act on. It is refused by
    name now. The pairing cannot be guessed from the code: DC3D8's wedge is
    DC3D6, C3D8H's is C3D6H, C3D8RT's is C3D6T and not C3D6RT, and getting it
    wrong means Abaqus quietly meshes part of the body with a default element
    of a different formulation.
    """
    if element in _COMPANION:
        return _COMPANION[element]
    raise SpecError(
        "part %r: mesh.element %r has no wedge/tet companion recorded here, so "
        "the cells a sweep leaves behind would get an Abaqus default of some "
        "other formulation without saying so. Recorded: %s. Add the family's "
        "own wedge and tet to _COMPANION in runner/build_v2.py -- the names do "
        "not follow a rule (DC3D8 pairs with DC3D6, C3D8RT with C3D6T), so they "
        "have to be looked up, not derived."
        % (part_name, element, ", ".join(sorted(_COMPANION))))

def _mesh_shape(part_name: str, element: str) -> tuple:
    """The elemShape this element needs, and the ElemType codes to hand Abaqus.

    A hex element brings its family's wedge and tet along, because a sweep
    leaves cells behind that are neither and Abaqus would fill them with a
    default of some other formulation. A tet or a wedge element stands alone:
    there is nothing left over to fill.

    The shape matters more than the elements do. `elemShape` defaults to HEX,
    and HEX on a body that has no hexes in it is ACCEPTED -- it meshes nothing
    and raises nothing (measured; see `_mesh_diagnosis`). So the one thing this
    must never do is return HEX for an element that is not a hex.
    """
    if element in _COMPANION:
        wedge, tet = _COMPANION[element]
        return "HEX", (element, wedge, tet)
    if element in _TET_PRIMARY:
        return "TET", (element,)
    if element in _WEDGE_PRIMARY:
        return "WEDGE", (element,)
    # The 2D pair. Same argument as above one dimension down: a free quad mesh
    # leaves triangles behind, and a quad element handed to Abaqus alone lets
    # it fill them with a default of some other formulation.
    if element in _COMPANION_2D:
        return "QUAD", (element,) + tuple(_COMPANION_2D[element])
    if element in _COMPANION_SHELL:
        return "QUAD", (element,) + tuple(_COMPANION_SHELL[element])
    if element in _TRI_PRIMARY:
        return "TRI", (element,)
    raise SpecError(
        "part %r: mesh.element %r is neither a hex with a wedge/tet companion "
        "recorded here nor a wedge or tet this generator knows, so the cells a "
        "sweep leaves behind would get an Abaqus default of some other "
        "formulation without saying so. Recorded hexes: %s. Recorded tets: %s. "
        "Recorded wedges: %s. Add the family's own wedge and tet to _COMPANION "
        "in runner/build_v2.py -- the names do not follow a rule (DC3D8 pairs "
        "with DC3D6, C3D8RT with C3D6T), so they have to be looked up, not "
        "derived. Recorded 2D quads: %s. Recorded 2D triangles: %s. Recorded "
        "shells: %s."
        % (part_name, element, ", ".join(sorted(_COMPANION)),
           ", ".join(sorted(_TET_PRIMARY)), ", ".join(sorted(_WEDGE_PRIMARY)),
           ", ".join(sorted(_COMPANION_2D)), ", ".join(sorted(_TRI_PRIMARY)),
           ", ".join(sorted(_COMPANION_SHELL))))

# Which elemShapes belong to which dimensionality. A planar part meshed with a
# hex element is not a slightly-wrong choice, it is nonsense -- and Abaqus's
# answer to nonsense here is to mesh nothing quietly, which is exactly what the
# shape layer exists to prevent.
_SHAPES_FOR_DIMENSIONALITY = {
    "THREE_D": ("HEX", "TET", "WEDGE"),
    "TWO_D_PLANAR": ("QUAD", "TRI"),
    "AXISYMMETRIC": ("QUAD", "TRI"),
}

# A shell part is THREE_D -- that is the Abaqus constant and it is not negotiable,
# a surface in space is a 3D part -- but its body is faces and it meshes with
# quads and triangles like a planar part does. Abaqus offers no dimensionality
# that says so, so it is the SECTION that says it, and this is the row that
# replaces the THREE_D one when it does.
_SHAPES_FOR_SHELL = ("QUAD", "TRI")

def _mesh_technique(part_name: str, shape: str, technique) -> str:
    """The technique to write, refused here when the shape cannot take it.

    Omitting it is only allowed on HEX, where Abaqus' own default is a hex
    technique and leaving the controls alone is therefore harmless. On TET and
    WEDGE the control has to be written whatever the spec said, because the
    default elemShape is HEX -- which is the case that meshes nothing quietly.
    """
    allowed = _SHAPE_TECHNIQUES[shape]
    if technique is None:
        return allowed[0]
    if str(technique) not in allowed:
        raise SpecError(
            "part %r: mesh.element is a %s element, and Abaqus meshes %s "
            "shapes with %s -- not %r. Either change mesh.technique, or name a "
            "hex element if the body really is sweepable."
            % (part_name, shape.lower(), shape.lower(),
               " or ".join(repr(item) for item in allowed), str(technique)))
    return str(technique)
