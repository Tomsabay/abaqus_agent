"""Named profiles, and the sketches drawn from them.

A `profile` in a v2 spec is one of three things -- a rect, a circle or a polygon
-- and this module is everything that follows from that choice: how big the
sketch canvas has to be, which ConstrainedSketch calls draw it, and what shape
data _cut() needs in order to redraw the same profile against a sketch
transform later.

The seam is between naming a shape and emitting a feature. build_v2.py decides
WHICH features a part gets and in what order; nothing in here knows a part has
features at all. That is why the polygon support landed here as one addition
rather than three scattered ones.

`_sheet_size_entities` and `_walk_numbers` are here for the same reason from the
other side: a generic entity-by-entity sketch names no profile, so its canvas
has to be inferred from the numbers its entities mention. Sizing a sketch is
sizing a sketch.

Runs in the host interpreter (3.13), not the Abaqus kernel -- it emits the
Python 2.7 text, it does not execute it.
"""

from __future__ import annotations

from runner.spec_base import SpecError


def _sketch(part_name: str, index: int, feat: dict) -> str:
    """Emit a sketch drawn in GLOBAL x, y.

    A sketch used for the base extrude is drawn on the XY plane directly. A
    sketch used for a cut is redrawn inside _cut() against a sketch transform,
    because a ConstrainedSketch made without one cannot drive CutExtrude. The
    profile is therefore also recorded as data, which is what _cut() replays.
    """
    profile = feat["profile"]
    var = "_sk_%s" % str(feat["id"])
    sheet = _sheet_size(profile)
    lines = ["%s = m.ConstrainedSketch(name=%r, sheetSize=%r)"
             % (var, "sk_%s_%s" % (part_name, str(feat["id"])), sheet)]
    if "rect" in profile:
        c1, c2 = profile["rect"]["corner1"], profile["rect"]["corner2"]
        lines.append("%s.rectangle(point1=(%r, %r), point2=(%r, %r))"
                     % (var, float(c1[0]), float(c1[1]), float(c2[0]), float(c2[1])))
    elif "polygon" in profile:
        for p1, p2 in _polygon_edges(profile):
            lines.append("%s.Line(point1=(%r, %r), point2=(%r, %r))"
                         % (var, p1[0], p1[1], p2[0], p2[1]))
    else:
        centre, radius = profile["circle"]["center"], float(profile["circle"]["r"])
        lines.append("%s.CircleByCenterPerimeter(center=(%r, %r), point1=(%r, %r))"
                     % (var, float(centre[0]), float(centre[1]),
                        float(centre[0]) + radius, float(centre[1])))
    lines.append("_SKETCHES[(%r, %r)] = %s"
                 % (str(part_name), str(feat["id"]), _profile_data(profile)))
    return "\n".join(lines)


def _polygon_points(profile: dict) -> list:
    return [(float(p[0]), float(p[1])) for p in profile["polygon"]["points"]]


def _polygon_edges(profile: dict) -> list:
    """The closed polygon as (start, end) pairs, refusing degenerate input.

    A zero-length Line is the failure worth spending code on: Abaqus takes the
    call, the sketch ends up with one fewer usable edge than the spec drew, and
    BaseSolidExtrude then fails on an open profile with a message that names the
    extrude rather than the duplicated point. Repeating the first point at the
    end to "close" the loop is the way that happens, so it is named explicitly.
    """
    pts = _polygon_points(profile)
    span = max([abs(a) for a, _ in pts] + [abs(b) for _, b in pts] + [1.0])
    tol = 1e-9 * span
    edges = []
    for i, p1 in enumerate(pts):
        p2 = pts[(i + 1) % len(pts)]
        if abs(p2[0] - p1[0]) <= tol and abs(p2[1] - p1[1]) <= tol:
            if i == len(pts) - 1:
                raise SpecError(
                    "polygon: the last point %r repeats the first. The loop is "
                    "closed for you — drop it." % (list(p1),))
            raise SpecError(
                "polygon: points %d and %d are the same point %r, which would "
                "draw a zero-length line." % (i, i + 1, list(p1)))
        edges.append((p1, p2))
    return edges


def _profile_data(profile: dict) -> str:
    """The profile as plain data, so _cut() can redraw it on a transform."""
    if "rect" in profile:
        c1, c2 = profile["rect"]["corner1"], profile["rect"]["corner2"]
        return ("{'rect': (%r, %r, %r, %r), 'circles': ()}"
                % (float(c1[0]), float(c1[1]), float(c2[0]), float(c2[1])))
    if "polygon" in profile:
        # 'circles' stays empty on purpose: _cut() reads it, finds nothing and
        # refuses, which is the same answer the named-op validator gives.
        pts = ", ".join("(%r, %r)" % (x, y) for x, y in _polygon_points(profile))
        return "{'rect': None, 'circles': (), 'poly': (%s,)}" % pts
    centre, radius = profile["circle"]["center"], float(profile["circle"]["r"])
    return ("{'rect': None, 'circles': ((%r, %r, %r),)}"
            % (float(centre[0]), float(centre[1]), radius))


def _sheet_size(profile: dict) -> float:
    if "rect" in profile:
        c1, c2 = profile["rect"]["corner1"], profile["rect"]["corner2"]
        span = max(abs(float(c2[0]) - float(c1[0])), abs(float(c2[1]) - float(c1[1])))
    elif "polygon" in profile:
        pts = _polygon_points(profile)
        xs = [x for x, _ in pts]
        ys = [y for _, y in pts]
        span = max(max(xs) - min(xs), max(ys) - min(ys))
    else:
        span = 2.0 * float(profile["circle"]["r"])
    return max(1.0, span * 4.0)


def _sheet_size_entities(feat: dict, entities: list) -> float:
    """The sketch canvas. Only ever the drawing grid, never the geometry.

    Taken from the coordinates the entities mention so a spec does not have to
    state it, but overridable: a sheet smaller than the profile makes CAE
    unhappy, and there is no way to know from a bare method name which of its
    arguments are points.
    """
    stated = feat.get("sheet_size")
    if stated:
        return float(stated)
    span = 0.0
    for value in _walk_numbers(entities):
        span = max(span, abs(value))
    return max(1.0, span * 4.0) if span else 200.0


def _walk_numbers(value):
    if isinstance(value, bool):
        return
    if isinstance(value, (int, float)):
        yield float(value)
    elif isinstance(value, (list, tuple)):
        for item in value:
            for found in _walk_numbers(item):
                yield found
    elif isinstance(value, dict):
        for key, item in value.items():
            if key in ("call", "as"):
                continue
            for found in _walk_numbers(item):
                yield found
