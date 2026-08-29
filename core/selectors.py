"""Named geometric selectors for the v2 assembly dialect.

Why this module exists at all
-----------------------------
Abaqus scripting picks geometry by coordinate — ``findAt((x, y, z))`` or
``faces.getByBoundingBox(...)``. Neither raises when the coordinate is wrong.
``findAt`` hands back the nearest face; ``getByBoundingBox`` hands back an empty
sequence, and ``part.Set(name='FIX', faces=<empty>)`` is accepted without
complaint. The job then runs, the solver reports COMPLETED, and the boundary
condition was applied to nothing or to the wrong face. That is a confidently
wrong answer, which is the one outcome this project treats as worse than a
refusal.

So a selector here is two things at once: a way to say *which* region without
writing raw coordinates, and an assertion about *how many* entities that phrase
is supposed to match. The generated CAE script checks the count before it
creates the set, and aborts naming the selector that missed.

Grammar (the authoritative definition — schema/spec_schema.json deliberately
does not restate it):

    [<instance>:]<kind>@<term>[&<term>...]

    term   <axis>=<place>                   a plane
         | r=<number>                       curvature
         | box=x0,y0,z0,x1,y1,z1            wholly inside
         | at=x,y,z                         centred there
         | all

    kind   face | faces | edge | edges | cell | cells | vertex | vertices
           node | nodes | element | elements
    axis   x | y | z
    place  min | max | <number>

``&`` means AND: every term has to hold. It exists because one predicate is not
enough to name a bolt hole. A column flange drilled four times answers
``face@r=10`` with all four holes — same radius, that is the point of a bolt
group — and tying one bolt to four holes is a model that meshes, solves, and is
wrong.

``at=`` is the other half of the same job, and the plane form cannot do it. A
plane compiles to ``getByBoundingBox``, which means WHOLLY INSIDE a thin slab,
and a hole's cylindrical wall spans its own diameter along every axis: the wall
of a 20 dia hole centred at y=1400 runs y 1390..1410, so ``face@y=1400``
matches it never, at any tolerance a plane can carry without swallowing the
neighbouring hole. ``at=`` compares the entity's own bounding-box centre
instead. So the phrase for one bolt hole is ``face@r=10&at=92,1400,0`` — "the
radius-10 face centred there" — and the numbers in it are the ones the author
already typed to place the bolt. The alternative already in the grammar, a
six-number ``box=`` drawn around the hole, works and is the coordinate
arithmetic this module exists to remove.

`node` and `element` name MESH, not geometry, and they exist because an orphan
mesh part has no geometry at all. Measured on Abaqus 2021
(artifacts/probe_orphan), `m.PartFromInputFile` on a deck holding one meshed bar
returns a part with 189 nodes, 80 elements and **0 cells, 0 faces, 0 edges, 0
vertices** — so every selector above resolves against an empty sequence, and
`part.Set(name='FIX', faces=<empty>)` is accepted in silence, which is the
failure this whole module was written for.

`element` takes only `@all`, and that is measured rather than conservative.
`getByBoundingBox` on a mesh element sequence requires the element to be WHOLLY
INSIDE the box: on the same bar, a box one element thick caught the 4 elements
of that layer, and the tolerance band this module actually emits — span x 1e-6,
so about 1e-4 mm on a 100 mm bar — caught **0 of 80**. A plane is a surface and
an element is a volume; the two only meet if the band is thick enough to
swallow whole elements, and that thickness is a number the author would have to
work out from the seed. Computing it here would be the coordinate arithmetic
this module exists to remove. `node@` has no such problem: a node is a point,
and the same band caught the 9 that lie on the root plane.

Singular and plural are not cosmetic. ``face@z=max`` defaults to expecting
exactly one; ``faces@z=max`` defaults to at least one. An explicit ``expect``
always wins.

``@r=`` exists because a hole's wall cannot be named by a plane: its bounding
box is the whole plate in x and y. Measured on Abaqus 2021, ``face.getRadius()``
returns the radius of a cylindrical face and raises ``Face is not cylindrical``
on a planar one (``edge.getRadius()`` likewise, with ``Edge is not circular``),
so a radius filter is exact and needs no coordinates at all. The alternative,
``getByBoundingCylinder``, was measured to return every face in the part when
given a large enough radius — containment is not identity, so it cannot mean
"this is the hole".

This module runs on the host (Python 3). The code it *emits* runs in the Abaqus
2021 kernel (Python 2.7): no f-strings, no annotations, no pathlib in the
generated text.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

KINDS = {
    "face": ("faces", "side1Faces"),
    "edge": ("edges", "side1Edges"),
    "cell": ("cells", None),
    "vertex": ("vertices", None),
    # Mesh, not geometry. An orphan mesh part has only these two.
    "node": ("nodes", None),
    "element": ("elements", None),
}
# Stripping a trailing 's' turns `vertices` into `vertice`, so the plurals are
# spelled out rather than derived. Abaqus itself spells the sequence
# `part.vertices`, so the plural a user reaches for is the irregular one.
PLURALS = {attribute: kind for kind, (attribute, _s) in KINDS.items()}
AXES = ("x", "y", "z")
# `r` and `radius` are the same word. Written on the left of `=` where an axis
# would go, because the shape of the phrase is the same — "the entities where
# this quantity has this value" — and a second syntax would buy nothing.
RADIUS_WORDS = ("r", "radius")
# Only faces and edges have a radius. Nothing else does -- getRadius() is not
# even defined on a cell, a vertex, a node or an element -- and accepting
# `cells@r=5` would emit a filter that silently matches nothing.
RADIUS_KINDS = ("face", "edge")
# Kinds the plane form cannot address, with the reason each one carries into
# its refusal. Measured on Abaqus 2021 (artifacts/probe_orphan): a box one
# element thick caught the 4 elements of that layer, and the band this module
# emits -- span x 1e-6 -- caught 0 of 80, because getByBoundingBox on elements
# means WHOLLY INSIDE. A plane is a surface; an element is a volume.
PLANE_REFUSED = {
    "element": (
        "an element is a volume and `getByBoundingBox` on elements means "
        "wholly inside, so a plane never cuts one. Measured on Abaqus 2021, "
        "the tolerance band this dialect emits (the model span x 1e-6) matched "
        "0 of 80 elements at z=min, while a band one element thick matched the "
        "4 of that layer -- and that thickness is a number you would have to "
        "work out from the seed, which is the coordinate arithmetic selectors "
        "exist to remove. Write `element@all` for the whole mesh, "
        "`element@box=x0,y0,z0,x1,y1,z1` for the ones inside a region you can "
        "name, or select the nodes instead: `node@z=min` matched the 9 on that "
        "plane"),
    # Same semantics, same answer, and it was still on offer. A cell is a
    # volume for exactly the reason an element is. Measured on Abaqus 2021
    # (artifacts/probe_cell) on a plate partitioned into two cells at x=10:
    #
    #   cell@x=min, band span x 1e-4 (what this module emits)   0 of 2
    #   cell@x=min, band span x 1e-6 (tighter)                  0 of 2
    #   a box containing the whole first cell                   1
    #   face@x=min, SAME band as the first row                  1
    #
    # The last two rows are why this is a refusal and not a wider tolerance:
    # the band is not too thin -- it catches the face that lies in that plane
    # -- and the box that does catch the cell is one that contains all of it,
    # which is the wholly-inside rule. No band that is a plane can ever match.
    "cell": (
        "a cell is a volume and `getByBoundingBox` on cells means wholly "
        "inside, so a plane never cuts one -- it matches nothing, every time. "
        "Measured on Abaqus 2021 on a plate partitioned into two cells: "
        "`cell@x=min` matched 0 of 2 both at the band this dialect emits and "
        "at one a hundred times tighter, while `face@x=min` at the same band "
        "matched 1 and a box containing the whole cell matched 1. That last row "
        "is now a form you can write: `cell@box=x0,y0,z0,x1,y1,z1` takes the "
        "cells wholly inside a box, which is how you name ONE of two cells "
        "either side of a partition. Otherwise `cell@all` for every cell, or "
        "name the geometry by its faces, which do lie in planes"),
}

# `box` sits where an axis would, like `r` does: same phrase shape, "the
# entities where this quantity has this value". Its right-hand side is six
# numbers, so it needs its own alternative rather than the single-value one.
BOX_WORD = "box"
# `at` is three numbers: where the entity is CENTRED, as opposed to `box`'s two
# corners it has to fit inside. The word is borrowed on purpose from
# `expect.cylinders[].at`, which already means the centre of a hole in this
# dialect -- so the number that placed a bolt is the number that names it.
AT_WORD = "at"

_SELECTOR_RE = re.compile(
    r"""^
    (?:(?P<instance>[A-Za-z_][A-Za-z0-9_-]*)\s*:\s*)?
    (?P<kind>[A-Za-z]+)
    \s*@\s*
    (?P<terms>\S.*)
    $""",
    re.VERBOSE,
)

_TERM_RE = re.compile(
    r"""^
    (?:
        (?P<all>all)
      | box\s*=\s*(?P<box>[-+0-9.eE\s,]+)
      | at\s*=\s*(?P<at>[-+0-9.eE\s,]+)
      | (?P<axis>[A-Za-z]+)\s*=\s*(?P<place>min|max|[-+0-9.eE]+)
    )
    $""",
    re.VERBOSE,
)

_EXPECT_RE = re.compile(r"^(?P<op>>=|<=|>|<|=)?(?P<n>\d+)$")


class SelectorError(ValueError):
    """A selector that cannot be parsed. The message is shown to the user."""


@dataclass(frozen=True)
class Selector:
    raw: str
    instance: str | None
    kind: str          # normalised singular: face / edge / cell / vertex
    plural: bool
    # One (axis, place) pair per `&`-joined term, in the order written. axis is
    # 'x' | 'y' | 'z' | 'r' | 'box'; both are None for `all`.
    terms: tuple[tuple[str | None, str | None], ...]
    expect: str        # normalised, e.g. '>=1' or '=2'

    @property
    def axis(self) -> str | None:
        """The first term's axis. A one-term selector is still the common case,
        and every caller that predates `&` reads it."""
        return self.terms[0][0]

    @property
    def place(self) -> str | None:
        return self.terms[0][1]

    @property
    def attribute(self) -> str:
        """The Abaqus sequence to search: faces / edges / cells / vertices."""
        return KINDS[self.kind][0]

    @property
    def by_radius(self) -> bool:
        return any(axis == "r" for axis, _p in self.terms)

    @property
    def by_box(self) -> bool:
        return any(axis == BOX_WORD for axis, _p in self.terms)

    @property
    def surface_kwarg(self) -> str | None:
        """The Surface() keyword for this kind, or None if it cannot be one."""
        return KINDS[self.kind][1]

    def describe(self) -> str:
        return self.raw


def parse(raw: str, expect: object = None) -> Selector:
    """Parse a selector string. Raises SelectorError with a usable message."""
    if not isinstance(raw, str) or not raw.strip():
        raise SelectorError("a selector cannot be empty")
    text = raw.strip()

    match = _SELECTOR_RE.match(text)
    if not match:
        raise SelectorError(
            "cannot read the selector %r. Expected something like "
            "'Lower:face@z=max', 'Upper:faces@y=0', 'Plate:cells@all', "
            "'Plate:edge@box=0,-1,-1,10,1,1' (six numbers, "
            "xMin,yMin,zMin,xMax,yMax,zMax) or 'Col:face@r=10&at=92,1400,0' "
            "(every '&'-joined term has to hold)." % raw)

    kind_word = match.group("kind").lower()
    plural = kind_word in PLURALS
    kind = PLURALS[kind_word] if plural else kind_word
    if kind not in KINDS:
        raise SelectorError(
            "selector %r asks for %r; known kinds are %s (singular or plural)."
            % (raw, match.group("kind"), ", ".join(sorted(KINDS))))

    terms = _parse_terms(raw, kind, match.group("terms"))
    return Selector(
        raw=text,
        instance=match.group("instance"),
        kind=kind,
        plural=plural,
        terms=terms,
        expect=normalise_expect(
            expect, default_plural=plural or terms[0][0] is None),
    )


def _parse_terms(raw: str, kind: str,
                 written: str) -> tuple[tuple[str | None, str | None], ...]:
    """Split on '&' and parse each side, refusing combinations that are empty.

    A term that cannot match alongside another is refused HERE rather than left
    to the count assertion, because the two failures read differently: a count
    mismatch says "the model is not what you thought", and this says "the phrase
    could not have matched whatever the model is".
    """
    pieces = [piece.strip() for piece in written.split("&")]
    if any(not piece for piece in pieces):
        raise SelectorError(
            "selector %r has an empty term around '&'. Each side of an '&' is a "
            "condition, e.g. 'face@r=10&y=1400'." % raw)

    terms = []
    seen = {}
    for piece in pieces:
        axis, place = _parse_term(raw, kind, piece)
        if axis is None and len(pieces) > 1:
            raise SelectorError(
                "selector %r ANDs 'all' with something else. 'all' is every "
                "entity of that kind, so the other term is the whole selector "
                "-- write that one on its own." % raw)
        if axis in seen:
            raise SelectorError(
                "selector %r gives %r twice, as %r and %r. Every term has to "
                "hold at once and an entity has one %s, so this matches nothing "
                "however the model is built." % (raw, axis, seen[axis], place, axis))
        seen[axis] = place
        terms.append((axis, place))
    return tuple(terms)


def _parse_term(raw: str, kind: str, text: str) -> tuple[str | None, str | None]:
    match = _TERM_RE.match(text)
    if not match:
        raise SelectorError(
            "cannot read the selector %r: %r is not a term. A term is 'all', an "
            "axis and a place ('z=max', 'y=0'), a radius ('r=10'), a box "
            "('box=0,-1,-1,10,1,1') or a centre ('at=0,0,0')."
            % (raw, text))

    if match.group("all"):
        axis = place = None
    elif match.group("box") is not None:
        # SIX numbers, xMin yMin zMin xMax yMax zMax -- Abaqus's own
        # getByBoundingBox order, so a reader who knows the API knows this.
        #
        # This is the form that answers "which of the two". A plane names
        # everything lying in it and `@all` names everything; between them
        # there was nothing, so a spec could not say "the half of the crack
        # line left of the tip" or "the cell on one side of the partition" --
        # the gap recorded against `cell@<plane>` when that form was refused.
        # A box is not a new idea here either: `getByBoundingBox` is what every
        # other form already compiles to.
        axis = BOX_WORD
        numbers = _numbers(raw, match.group("box"), "six", BOX_WORD,
                           "xMin,yMin,zMin,xMax,yMax,zMax -- the same order as "
                           "Abaqus's own getByBoundingBox")
        for index, letter in enumerate("xyz"):
            if numbers[index] > numbers[index + 3]:
                raise SelectorError(
                    "selector %r has %sMin=%s above %sMax=%s. An inverted box "
                    "matches nothing, every time, and Abaqus does not object "
                    "-- it returns an empty sequence, which is what this layer "
                    "exists to stop." % (raw, letter, numbers[index],
                                         letter, numbers[index + 3]))
        place = ",".join(repr(value) for value in numbers)
    elif match.group("at") is not None:
        axis = AT_WORD
        place = ",".join(repr(value) for value in _numbers(
            raw, match.group("at"), "three", AT_WORD,
            "x,y,z -- the point the entity is centred on"))
    else:
        axis = match.group("axis").lower()
        place = match.group("place")
        if axis in RADIUS_WORDS:
            axis = "r"
            if kind not in RADIUS_KINDS:
                raise SelectorError(
                    "selector %r asks for %ss by radius, but only faces and "
                    "edges have one. A cell, a vertex, a node and an element "
                    "never do, so this would match nothing however the model "
                    "is built." % (raw, kind))
            if place in ("min", "max"):
                raise SelectorError(
                    "selector %r asks for radius %r. 'min' and 'max' locate a "
                    "plane along an axis; a radius has to be the number you "
                    "drew." % (raw, place))
            # SelectorError IS a ValueError, so the conversion and the range
            # check cannot share a try: raising inside it is caught by its own
            # except and reported as "expected a number".
            try:
                value = float(place)
            except ValueError:
                raise SelectorError(
                    "selector %r has %r as a radius; expected a number."
                    % (raw, place))
            if value <= 0.0:
                raise SelectorError(
                    "selector %r asks for radius %s; a radius is positive."
                    % (raw, place))
        elif axis not in AXES:
            raise SelectorError(
                "selector %r selects on %r; expected an axis (x, y, z) or a "
                "radius (r)." % (raw, match.group("axis")))
        elif kind in PLANE_REFUSED:
            raise SelectorError(
                "selector %r puts %ss on a plane, and %s."
                % (raw, kind, PLANE_REFUSED[kind]))
        elif place not in ("min", "max"):
            try:
                float(place)
            except ValueError:
                raise SelectorError(
                    "selector %r has %r on the right of '='; expected a number, "
                    "'min' or 'max'." % (raw, place))

    return axis, place


def _numbers(raw: str, written: str, wanted: str, word: str,
             order: str) -> list[float]:
    """The comma-separated numbers a `box=` or `at=` was given, or a refusal.

    `wanted` is the count spelled out, because it reads as prose in the message
    and the message is the whole point of refusing here rather than letting the
    count assertion catch it later.
    """
    count = {"three": 3, "six": 6}[wanted]
    parts = [piece.strip() for piece in written.split(",")]
    if len(parts) != count:
        raise SelectorError(
            "selector %r gives %d number(s) to `%s=`; it takes %s, %s."
            % (raw, len([p for p in parts if p]), word, wanted, order))
    numbers = []
    for piece in parts:
        try:
            numbers.append(float(piece))
        except ValueError:
            raise SelectorError(
                "selector %r has %r in its `%s=`; every one of the %s has to be "
                "a number. 'min' and 'max' are for the plane form -- a `%s=` is "
                "the coordinates you mean." % (raw, piece, word, wanted, word))
    return numbers


def normalise_expect(expect: object, default_plural: bool) -> str:
    """Turn 1 / '2' / '>=1' into a canonical form, or supply the default.

    The default is the reason singular and plural are spelled differently:
    ``face@z=max`` means one face and says so without the author having to
    remember to write ``expect: 1``. That matters because the count assertion
    only protects the selectors that carry one.
    """
    if expect is None:
        return ">=1" if default_plural else "=1"
    if isinstance(expect, bool):    # bool is an int; nobody means expect: true
        raise SelectorError("expect must be a count, not %r" % expect)
    text = str(expect).strip().replace(" ", "")
    match = _EXPECT_RE.match(text)
    if not match:
        raise SelectorError(
            "cannot read expect=%r. Use a count (2) or a comparison "
            "('>=1', '<=4')." % expect)
    op = match.group("op") or "="
    return "%s%s" % (op, int(match.group("n")))


def satisfies(count: int, expect: str) -> bool:
    """Host-side twin of the check the generated script performs."""
    match = _EXPECT_RE.match(expect)
    if not match:
        raise SelectorError("malformed expect %r" % expect)
    op, n = match.group("op") or "=", int(match.group("n"))
    return {
        "=": count == n,
        ">=": count >= n,
        "<=": count <= n,
        ">": count > n,
        "<": count < n,
    }[op]


# ---------------------------------------------------------------------------
# Code generation (target: Abaqus 2021 kernel, Python 2.7)
# ---------------------------------------------------------------------------

RUNTIME = '''
# --- selector runtime (generated; see core/selectors.py) --------------------
_SEL_TOL = 1.0e-6


def _sel_log(text):
    """Record what each selector matched, in the run directory.

    Measured: print() from a `abaqus cae noGUI` script does NOT reach the
    launcher's stdout. It lands in the CAE replay file (abaqus.rpy), which is
    session-numbered and gets overwritten, so the one record of which face each
    selector picked was effectively unfindable. A failure still surfaces --
    exceptions go to stderr and build_model_script.log -- but a SUCCESSFUL
    build left no evidence at all, and "which face did it actually take" is
    exactly the question this layer exists to answer.
    """
    print(text)
    try:
        handle = open(os.path.join(workdir, 'selectors.log'), 'a')
        try:
            handle.write(text + '\\n')
        finally:
            handle.close()
    except Exception:
        pass

def _sel_bbox(owner):
    """Bounding box of a part or a positioned instance, in its own space.

    Measured on Abaqus 2021, and both halves of this were surprises:

      * NEITHER a part nor an instance has getBoundingBox() -- both raise
        AttributeError, so this function has never once taken its first
        branch. (An earlier version of this note claimed instances had it;
        measured directly on a PartInstance, they do not. The loop is kept
        because it costs one failed getattr and a future release may add it.)
      * The old fallback walked owner.vertices and took min/max, which is
        exact for a box and badly wrong for anything curved. On a flange
        revolved to an outer radius of 30 it returned x 4..30, z 0..0 against
        a true extent of x -30..30, z -30..30: the widest point of a revolved
        solid is in the middle of a curved face and has no vertex anywhere
        near it. Every extruded box shipped so far happened to have all its
        extremes at vertices, which is why nothing caught this.

    The geometry sequences carry the real thing -- cells/faces/edges each have
    getBoundingBox() and all three returned the correct box. vertices does too,
    and returns the same wrong answer as the hand-rolled loop, so it is last.

    `nodes` is last of all, and it is what makes `node@z=min` work on an orphan
    mesh. Measured on Abaqus 2021 (artifacts/probe_orphan), a part read by
    PartFromInputFile has 0 cells, 0 faces, 0 edges and 0 vertices, and each of
    those EMPTY sequences answers getBoundingBox() with a reversed degenerate
    box -- low (0, 0, 0), high (-1, -1, -1) -- rather than raising. The
    high > low guard below already rejects that, which is why appending nodes
    is safe: on any part with geometry the loop still stops at cells, and only
    a part that has none reaches this.
    """
    for source in (owner, getattr(owner, 'cells', None),
                   getattr(owner, 'faces', None), getattr(owner, 'edges', None),
                   getattr(owner, 'vertices', None),
                   getattr(owner, 'nodes', None)):
        if source is None:
            continue
        try:
            bb = source.getBoundingBox()
        except Exception:
            continue
        low, high = tuple(bb['low']), tuple(bb['high'])
        if high[0] > low[0] or high[1] > low[1] or high[2] > low[2]:
            return (low, high)
    raise ValueError('cannot determine a bounding box for ' + str(owner))


def _sel_by_radius(seq, radius, tol):
    """Every face/edge whose radius is `radius`, as a concatenated sequence.

    Measured on Abaqus 2021: getRadius() returns the radius of a cylindrical
    face or a circular edge, and raises AbaqusException ("Face is not
    cylindrical" / "Edge is not circular") on everything else. So the try/except
    IS the "is this curved" test -- there is no predicate that answers it
    directly, and dir(face) confirms none was hiding.

    The result is built by slice-concatenation rather than as a Python list.
    Set(faces=[...]) wants an Abaqus geometry sequence, and seq[i:i+1] + ... is
    the documented way to build one from chosen indices.
    """
    picked = None
    for item in seq:
        try:
            found = item.getRadius()
        except Exception:
            continue
        if abs(found - radius) > tol:
            continue
        i = item.index
        piece = seq[i:i + 1]
        picked = piece if picked is None else picked + piece
    return picked if picked is not None else seq[0:0]


def _sel_centred_at(seq, point, tol):
    """Every entity whose own bounding-box centre is `point`.

    Not getCentroid(): measured on Abaqus 2021, that is an estimate off the
    facetted display geometry, and it is the wrong quantity anyway -- the
    centroid of a half-cylinder is not on its axis. The bounding-box midpoint
    IS on the axis for a cylindrical face, which is where a bolt hole is named.

    The box comes from a one-item SLICE rather than the entity: a slice is a
    geometry sequence and sequences are what carry getBoundingBox() (the same
    reason _sel_bbox walks owner.faces and not owner).
    """
    picked = None
    for item in seq:
        i = item.index
        piece = seq[i:i + 1]
        try:
            bb = piece.getBoundingBox()
        except Exception:
            continue
        low, high = tuple(bb['low']), tuple(bb['high'])
        near = True
        for k in range(3):
            if abs((low[k] + high[k]) / 2.0 - point[k]) > tol:
                near = False
                break
        if not near:
            continue
        picked = piece if picked is None else picked + piece
    return picked if picked is not None else seq[0:0]


def _sel_expect_ok(count, expect):
    op = expect[:2] if expect[:2] in ('>=', '<=') else expect[:1]
    n = int(expect[len(op):])
    if op == '=':
        return count == n
    if op == '>=':
        return count >= n
    if op == '<=':
        return count <= n
    if op == '>':
        return count > n
    return count < n


def _sel_resolve(owner, attribute, axis, place, expect, label, scale_tol):
    """Return the entities a selector names, or die naming the selector.

    Dying here is the point. getByBoundingBox returns an empty sequence for a
    plane that does not exist, Set() accepts an empty sequence, and the job
    then solves with the boundary condition applied to nothing.
    """
    found, box = _sel_find(owner, attribute, axis, place, scale_tol)
    return _sel_checked(found, attribute, expect, label, box)


def _sel_resolve_and(owner, attribute, terms, expect, label, scale_tol):
    """The entities that satisfy EVERY term -- what `&` compiles to.

    Intersected by `.index` rather than by object identity: Abaqus hands back a
    NEW wrapper each time a sequence is sliced, so `face in other_sequence` and
    `set(seq_a) & set(seq_b)` both come back empty even when the same face is in
    both. The index is the stable name.
    """
    seq = getattr(owner, attribute)
    keep = None
    notes = []
    for axis, place in terms:
        found, box = _sel_find(owner, attribute, axis, place, scale_tol)
        notes.append(box.strip())
        ids = set()
        for item in found:
            ids.add(item.index)
        keep = ids if keep is None else (keep & ids)
    picked = None
    for i in sorted(keep):
        piece = seq[i:i + 1]
        picked = piece if picked is None else picked + piece
    if picked is None:
        picked = seq[0:0]
    return _sel_checked(picked, attribute, expect, label, ' ' + ' & '.join(notes))


def _sel_checked(found, attribute, expect, label, box):
    count = len(found)
    if not _sel_expect_ok(count, expect):
        message = ('SELECTOR_MISMATCH: %s matched %d %s, expected %s. '
                   'The build stops here rather than applying it to the wrong '
                   'region.' % (label, count, attribute, expect))
        _sel_log(message)
        raise ValueError(message)
    # The bounding box goes in the log on purpose. It is the one number that
    # says whether an instance was measured in assembly space or in its own
    # part space, and getting that wrong picks a real face on the wrong side of
    # the model without matching zero. Measured on Abaqus 2021: an instance
    # reports its box in ASSEMBLY space, so `Upper:face@y=5` means y=5 after
    # the translate, which is what the author of the spec meant.
    _sel_log('SELECTOR_OK: %s -> %d %s%s' % (label, count, attribute, box))
    return found


def _sel_find(owner, attribute, axis, place, scale_tol):
    """One term, with no assertion attached: the entities and a note for the log."""
    seq = getattr(owner, attribute)
    box = ''
    if axis is None:
        found = seq[:]
    elif axis == 'box':
        # The six numbers the spec typed, padded by the same tolerance the
        # plane form uses. Padding is not slack: an entity whose coordinate is
        # exactly a corner of the box is a coin flip on float comparison
        # otherwise, and this form exists to be written against coordinates the
        # author already knows. Writing a box that abuts a neighbour is caught
        # by the count, which is the assertion every form here carries.
        numbers = [float(piece) for piece in place.split(',')]
        low, high = _sel_bbox(owner)
        span = max(high[0] - low[0], high[1] - low[1], high[2] - low[2])
        tol = max(_SEL_TOL, span * scale_tol)
        found = seq.getByBoundingBox(
            xMin=numbers[0] - tol, yMin=numbers[1] - tol, zMin=numbers[2] - tol,
            xMax=numbers[3] + tol, yMax=numbers[4] + tol, zMax=numbers[5] + tol)
        box = ' box=%s..%s pad=%s' % (tuple(numbers[:3]), tuple(numbers[3:]), tol)
    elif axis == 'r':
        # Relative tolerance: a radius is a length the author typed, not a
        # coordinate that fell out of a boolean operation, so it should match
        # to within rounding rather than to within a fraction of the model.
        radius = float(place)
        found = _sel_by_radius(seq, radius, max(_SEL_TOL, radius * 1.0e-6))
        box = ' radius=%s' % radius
    elif axis == 'at':
        numbers = [float(piece) for piece in place.split(',')]
        low, high = _sel_bbox(owner)
        span = max(high[0] - low[0], high[1] - low[1], high[2] - low[2])
        tol = max(_SEL_TOL, span * scale_tol)
        found = _sel_centred_at(seq, numbers, tol)
        box = ' at=%s tol=%s' % (tuple(numbers), tol)
    else:
        low, high = _sel_bbox(owner)
        box = ' bbox=%s..%s' % (low, high)
        idx = {'x': 0, 'y': 1, 'z': 2}[axis]
        if place == 'min':
            target = low[idx]
        elif place == 'max':
            target = high[idx]
        else:
            target = float(place)
        span = max(high[0] - low[0], high[1] - low[1], high[2] - low[2])
        tol = max(_SEL_TOL, span * scale_tol)
        lo = [low[0] - tol, low[1] - tol, low[2] - tol]
        hi = [high[0] + tol, high[1] + tol, high[2] + tol]
        lo[idx] = target - tol
        hi[idx] = target + tol
        found = seq.getByBoundingBox(xMin=lo[0], yMin=lo[1], zMin=lo[2],
                                     xMax=hi[0], yMax=hi[1], zMax=hi[2])
    return found, box
# --- end selector runtime --------------------------------------------------
'''

# Faces of a rectangular block sit exactly on the bounding box, but a face that
# is merely *near* a plane must not be swept in, so the tolerance is a fraction
# of the model span rather than a fixed length. 1e-4 of the span is ~0.01 mm on
# a 100 mm part: far above float noise, far below any feature we can mesh.
DEFAULT_SCALE_TOL = 1.0e-4


def resolve_expression(selector: Selector, owner_expr: str,
                       scale_tol: float = DEFAULT_SCALE_TOL) -> str:
    """Emit the call that resolves this selector against ``owner_expr``.

    ``owner_expr`` is generated Python naming the part or instance to search,
    e.g. ``a.instances['Lower']``.

    A one-term selector still emits ``_sel_resolve`` with the same arguments in
    the same order it always did. That is deliberate: tests/test_frozen_model_
    sections.py pins the emitted model text for the shipped cases, and routing
    every selector through the new call would move all five hashes to say
    nothing had changed about what they build.
    """
    tail = [
        repr(str(selector.expect)),
        repr(str(selector.raw)),
        repr(float(scale_tol)),
    ]
    if len(selector.terms) == 1:
        axis, place = selector.terms[0]
        args = [owner_expr, repr(str(selector.attribute)),
                repr(str(axis)) if axis else "None",
                repr(str(place)) if place else "None"] + tail
        return "_sel_resolve(%s)" % ", ".join(args)
    written = ", ".join("(%r, %r)" % (str(axis), str(place))
                        for axis, place in selector.terms)
    args = [owner_expr, repr(str(selector.attribute)),
            "(%s,)" % written] + tail
    return "_sel_resolve_and(%s)" % ", ".join(args)
