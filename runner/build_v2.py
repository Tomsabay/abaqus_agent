"""Generate an Abaqus/CAE noGUI script from a v2 assembly spec.

The v1 generator in build_model.py has one function per named shape, and each
one hardcodes ``Part-1`` and a single instance. This one reads ``parts`` /
``assembly`` / ``interactions`` / ``steps`` and emits as many parts, instances,
ties, boundary conditions and loads as the spec declares.

Two rules shape everything here:

* **Regions are named, and the names are checked.** Every BC, load and tie
  region comes from core/selectors.py, which emits a hit-count assertion next
  to the lookup. getByBoundingBox returns an empty sequence for a plane that
  does not exist and Set() accepts it, so without the assertion a typo produces
  a job that solves with the load applied to nothing.

* **Sets and surfaces live on the rootAssembly, not on the part.** A part
  instanced twice has one set of faces; ``Lower:face@y=max`` and
  ``Upper:face@y=max`` are different faces only once the instance transform has
  been applied. Assembly-level regions also give every set a globally unique
  name, which is what post/extract_kpis.py needs to resolve a KPI location
  without guessing which instance was meant.

The emitted script runs in the Abaqus 2021 kernel — Python 2.7. No f-strings,
no annotations, no pathlib in any generated text.
"""

from __future__ import annotations

import re
from pathlib import Path

from core import selectors
from tools.errors import AbaqusAgentError, ErrorCode
from runner import kernel_runtime
# Re-exported: build_v2.SpecError is what the rest of the tree catches.
from runner.spec_base import SpecError, _is_generic, _parse
from runner.mesh_policy import (
    DEFAULT_MESH_ELEMENT, _DIMENSIONALITY, _SHAPES_FOR_DIMENSIONALITY,
    _TECHNIQUE_CONSTANT, _companions, _mesh_shape, _mesh_technique)
from runner.preview import _preview_dump
from runner.arg_forms import (
    _IDENT_RE, _IMPORT_LINE, _MODULES, _SYMBOL_RE, _arg_expr, _generic_call)





# ---------------------------------------------------------------------------
# Cross-references JSON Schema cannot check
# ---------------------------------------------------------------------------

def validate_references(spec: dict) -> None:
    """Check every name one part of the spec uses against where it is defined.

    JSON Schema validates shapes, not relationships: it cannot tell that an
    instance names a part that was never declared. Left unchecked, the CAE
    script fails on a KeyError deep inside a generated file, which is a poor
    way to learn about a typo.
    """
    parts = {p["name"]: p for p in spec.get("parts", [])}
    if len(parts) != len(spec.get("parts", [])):
        raise SpecError("two parts share a name; part names must be unique")

    materials = {spec["material"]["name"]}
    materials.update(m["name"] for m in spec.get("materials", []) or [])
    for part in spec["parts"]:
        wanted = part["section"]["material"]
        if wanted not in materials:
            raise SpecError(
                "part %r asks for material %r, which is not defined. "
                "Defined: %s" % (part["name"], wanted, ", ".join(sorted(materials))))
        _validate_features(part)

    instances = {}
    for inst in spec["assembly"]["instances"]:
        if inst["name"] in instances:
            raise SpecError("two instances share the name %r" % inst["name"])
        if inst["part"] not in parts:
            raise SpecError(
                "instance %r is an instance of %r, which is not a declared "
                "part. Declared: %s"
                % (inst["name"], inst["part"], ", ".join(sorted(parts))))
        instances[inst["name"]] = inst

    # A pattern or a boolean creates instances the spec never listed, and a BC
    # on one of them is legitimate. Rather than weaken the check that catches
    # typos, an operation says what it will create -- and if it is wrong,
    # assembly.expect catches it at run time against the real assembly.
    for i, op in enumerate(spec["assembly"].get("operations", []) or []):
        for created in op.get("creates", []) or []:
            if created in instances:
                raise SpecError(
                    "assembly operation %d says it creates %r, which is "
                    "already an instance name" % (i + 1, created))
            instances[created] = op

    # Same walk as generation, for the same reason parts get one: a check that
    # lives apart from the code it guards drifts away from it.
    _interactions(spec, "")

    for where, raw, expect in _all_selectors(spec):
        sel = _parse(raw, expect, where)
        if sel.instance is None:
            raise SpecError(
                "%s: selector %r does not say which instance it is on. Write "
                "'<instance>:%s'." % (where, raw, raw))
        if sel.instance not in instances:
            raise SpecError(
                "%s: selector %r names instance %r, which does not exist. "
                "Instances: %s"
                % (where, raw, sel.instance, ", ".join(sorted(instances))))


def _validate_features(part: dict) -> None:
    """Compile the part's features and throw the result away.

    Validation and generation are the same walk on purpose. A check that lives
    apart from the code it guards drifts away from it, and the one thing this
    layer cannot afford is a spec that validates and then builds something else.
    """
    if "import" in part:
        # Same walk, the other shape. Without this an imported part reached
        # _feature_lines, which reads part["features"], and a spec with only
        # `import:` died with a bare KeyError naming no part and no key.
        _import_lines(part)
    else:
        _feature_lines(part)
    _expect_lines(part)


# ---------------------------------------------------------------------------
# Features: named ops (sugar) and generic dispatch
# ---------------------------------------------------------------------------
#
# Abaqus exposes 292 callables on Part and 71 on ConstrainedSketch, and the
# lists grow every release. Enumerating them here — one schema branch, one
# generator branch and one test per shape — is a race nobody wins, and the code
# it produces can only ever build the shapes somebody already thought of.
#
# So a feature may instead name the Abaqus method directly:
#
#     - call: BaseSolidRevolve
#       angle: 360.0
#       flipRevolveDirection: "OFF"
#       sketch: {sketch: profile}
#
# ``getattr(part, name)(**kwargs)`` does the rest. Measured on Abaqus 2021,
# every way of getting that wrong is loud: an unknown method is an
# AttributeError, an unknown keyword is "TypeError: keyword error on <name>",
# and a wrong argument type is "TypeError: point1; found string, expecting
# tuple". None of them is silent, which is what makes the dispatch safe.
#
# What generic dispatch DOES give up is the schema's protection: nothing here
# knows what `CutRevolve` was supposed to produce, so nothing can check it. That
# is why a part using generic calls must carry an `expect:` block — the truth
# layer moves from the call to the result. See _require_expect.




_EXPECT_KEYS = ("volume", "area", "cells", "faces", "edges", "vertices",
                "cylindrical_faces", "cylinders")

# How close a measured centroid has to sit to the one the spec states, when the
# spec does not say. RELATIVE to the feature, because the instrument's error is.
# getCentroid() is a tessellation estimate; measured on Abaqus 2021 over holes of
# r = 4, 6, 12 and 50 it lands on the axis exactly at r = 4 and 6 and misses by
# 0.00901 at r = 12 and 0.02690 at r = 50 -- 7.5e-4 and 5.4e-4 of r.
#
# This is a BOUND, not a model of the error. A separate probe built the same
# through hole at four scales two decades apart with r fixed at a twentieth of
# the part, and measured zero error at every one of them, r = 25 included. So
# the tessellation depends on more than the radius, and the only defensible
# thing to do with the numbers above is to stay above all of them.
#
# The absolute default this replaces (0.05, sized once against a 30 mm flange)
# was wrong at both ends of the scale, and the large end was measured, not
# projected: a through bore of r = 300 in a 900 mm plate reports its centroid
# 0.070931 from a position that is analytically exact, and the old default
# refused it. That is a false refusal of correct geometry -- the same failure a
# `r * 1.0e-4` tolerance caused once before, see _cut_missing. At the small end,
# a fixed 0.05 on a part half a millimetre across accepts a hole a tenth of the
# part away from where the spec said, so the check stops being one.
#
# The factor is ~2.7x the worst error measured, the floor keeps a hairline
# feature from being held to float noise, and both are the pair _cut_missing has
# used since that false refusal -- kept as names so the two cannot drift apart.
# Every passing check logs its margin, so the next person to touch these has
# measurements to touch them with. The gate item behind all of this is
# generic_big_bore_survives_its_own_instrument.
CENTROID_TOL_FLOOR = 1.0e-3
CENTROID_TOL_FACTOR = 2.0e-3


def _centroid_tol(size: float) -> float:
    """The default centroid tolerance for a feature of this size."""
    return max(CENTROID_TOL_FLOOR, abs(float(size)) * CENTROID_TOL_FACTOR)


# Relative, and the same number the part-level volume check has used since it
# was written. Kept as a name so the two cannot drift apart.
DEFAULT_VOLUME_TOL = 1.0e-3


def _feature_lines(part_spec: dict) -> list[str]:
    """Emit one part's feature calls, raising on anything that cannot be built."""
    part_name = str(part_spec["name"])
    sketches: dict[str, object] = {}   # id -> recorded profile, or None if generic
    results: set[str] = set()          # names bound by `as:`
    lines: list[str] = []
    solid = False
    generic = False
    meshed = False

    for i, feat in enumerate(part_spec["features"]):
        where = "part %r feature %d" % (part_name, i + 1)

        if "expect" in feat:
            # `expect:` is honoured on an interaction and on a condition,
            # refused on model_setup and on a step, and was silently DROPPED
            # here and on an assembly operation: schema/spec_schema.json's
            # generic_call ends additionalProperties:true, and _generic_call's
            # reserved tuple skips it, so it validated, generated an 84 KB
            # deck, and the number it stated appeared nowhere in it.
            raise SpecError(
                "%s: `expect:` on a feature has nothing to measure — a Part "
                "method returns a Feature, not geometry. What the part came "
                "out as goes in the part's own `expect:` block, which runs "
                "after every feature and before the mesh." % where)

        if "call" in feat:
            generic = True
            # Matched by shape, not by a list: generateMesh,
            # generateBottomUpSweptMesh, generateMeshByOffset and the rest all
            # read the same way. A future release that names a mesh generator
            # differently would slip past, which is exactly today's state, so
            # this can only improve on it.
            name = str(feat.get("call", ""))
            if name.startswith("generate") and "Mesh" in name:
                meshed = True
            lines.append(_generic_call(
                where, _dispatch_target(where, feat, results, "p"),
                feat, sketches, results))
            continue

        op = feat["op"]
        if op == "sketch":
            sid = str(feat["id"])
            if sid in sketches:
                raise SpecError("%s: sketch id %r is used twice" % (where, sid))
            if not _IDENT_RE.match(sid):
                # A sketch id becomes a variable name in the generated script.
                # `identifier` in the schema allows a hyphen, which Abaqus
                # accepts in an object name but Python does not in a variable --
                # so `id: hole-1` used to emit `_sk_hole-1 = ...` and die as a
                # syntax error inside the CAE kernel, far from the spec line.
                raise SpecError(
                    "%s: sketch id %r cannot be part of a variable name. Use "
                    "letters, digits and underscores." % (where, sid))
            if "entities" in feat:
                generic = True
                lines.append(_generic_sketch(where, part_name, feat, sketches,
                                             results))
                sketches[sid] = None
                continue
            plane = str(feat.get("plane", "XY")).upper()
            if plane != "XY":
                # Belt and braces behind the schema enum. This was silent: the
                # generator never read `plane`, so a spec asking for YZ got a
                # part built on XY and the emitted script was byte-identical.
                raise SpecError(
                    "%s: sketch %r asks for the %s plane. Only XY is built by "
                    "the named ops — the base extrude runs along +z from XY and "
                    "cut_extrude drives off the z=max face. Draw it with "
                    "`entities:` and a generic `call:` if you need another "
                    "plane, or rotate the instance in the assembly."
                    % (where, sid, plane))
            lines.append(_sketch(part_name, i, feat))
            sketches[sid] = feat["profile"]
            continue

        sid = str(feat["sketch"])
        if sid not in sketches:
            raise SpecError(
                "%s: %s refers to sketch %r before it is drawn. Sketches "
                "available here: %s"
                % (where, op, sid, ", ".join(sorted(sketches)) or "none"))
        profile = sketches[sid]
        if profile is None:
            # The named ops replay a recorded profile -- _cut needs the circle
            # centres to prove the hole landed where it was asked for. A generic
            # sketch has no such record, so the op cannot check itself, and an
            # unchecked cut is one that can silently miss.
            replacement = "BaseSolidExtrude" if op == "extrude" else "CutExtrude"
            raise SpecError(
                "%s: %s uses sketch %r, which is drawn from generic entities. "
                "The named ops replay a recorded profile and a generic sketch "
                "has none — use `call: %s` instead, and give the part an "
                "`expect:` block." % (where, op, sid, replacement))

        if op == "extrude":
            if solid:
                raise SpecError(
                    "%s: a second 'extrude' would replace the base solid. Use "
                    "'cut_extrude' to remove material." % where)
            solid = True
            lines.append("p.BaseSolidExtrude(sketch=_sk_%s, depth=%r)"
                         % (sid, float(feat["depth"])))
        else:  # cut_extrude
            if not solid:
                raise SpecError(
                    "%s: cut_extrude before anything has been extruded" % where)
            if "circle" not in profile:
                # A cut is checked afterwards by looking for the cylindrical
                # face it should have produced, and a rectangular cut leaves no
                # curved face to look for. Rather than run an unchecked cut --
                # which was measured to miss in silence, leaving the volume and
                # the element count untouched and raising nothing -- the shape
                # that cannot be verified is refused.
                raise SpecError(
                    "%s: cut_extrude with sketch %r, which is a rectangle. Only "
                    "circular cuts are supported by the named op, because only "
                    "they leave a cylindrical face the generator can check "
                    "afterwards, and a cut that misses is silent: same volume, "
                    "same mesh, no error." % (where, sid))
            # Everything about this call was measured rather than read: see
            # docs/ASSEMBLY_MODELING.md section 9 and the _cut docstring.
            lines.append("_cut(m, p, %r, %r, %r)"
                         % (part_name, sid, float(feat["depth"])))

    if meshed and not (part_spec.get("expect") or {}).get("mesh"):
        raise SpecError(
            "part %r meshes itself with a generic call, so it needs an "
            "`expect.mesh` block. Nothing else checks a mesh built this way — "
            "and measured on Abaqus 2021, elemShape=HEX with "
            "technique=SYSTEM_ASSIGN is ACCEPTED on a shape that has no hexes, "
            "produces zero elements and raises nothing. Give at least "
            "`elements:`." % part_spec["name"])
    if generic:
        _require_expect(part_spec)
    elif not solid:
        raise SpecError(
            "part %r never extrudes anything, so it has no volume" % part_name)
    return lines


def _stated_measures(expect: dict) -> list[str]:
    """Which expect keys actually carry something to check.

    `cylinders: []` is the case this exists for: the key is present, so a naive
    membership test calls the part covered, and _expect_lines then emits nothing
    at all. The schema's minItems catches it first, but this layer is the belt
    behind that brace -- and here a gap means a generic part with NO truth layer,
    which is the one state the design does not allow.
    """
    stated = []
    for key in _EXPECT_KEYS:
        value = expect.get(key)
        if value is None or (key == "cylinders" and not value):
            continue
        stated.append(key)
    return stated


def _require_expect(part_spec: dict) -> None:
    expect = part_spec.get("expect") or {}
    if _stated_measures(expect):
        return
    raise SpecError(
        "part %r uses generic feature calls, so it needs an `expect:` block. A "
        "named op has a check written behind it; a generic call cannot have "
        "one, because nothing here knows what the method was meant to produce. "
        "And every way this goes wrong is silent — measured on Abaqus 2021, a "
        "cut that lands off the solid leaves the volume untouched and raises "
        "nothing, and one with the sketch orientation transposed leaves the "
        "volume EXACTLY right with x and y swapped. Give at least one of: %s."
        % (part_spec["name"], ", ".join(_EXPECT_KEYS)))


def _generic_sketch(where: str, part_name: str, feat: dict,
                    sketches: dict, results: set) -> str:
    """A sketch drawn entity by entity instead of from a named profile."""
    sid = str(feat["id"])
    var = "_sk_%s" % sid
    entities = feat["entities"]
    args = ["name=%r" % ("sk_%s_%s" % (part_name, sid)),
            "sheetSize=%r" % _sheet_size_entities(feat, entities)]
    if "transform" in feat:
        # A sketch that will drive a cut has to be BUILT with the transform --
        # measured: CutExtrude on a sketch made without one raises "Cut extrude
        # feature failed", and there is no way to attach it afterwards.
        args.append("transform=%s"
                    % _arg_expr(where, "transform", feat["transform"],
                                sketches, results))
    lines = ["%s = m.ConstrainedSketch(%s)" % (var, ", ".join(args))]
    for j, entity in enumerate(entities):
        if "call" not in entity:
            raise SpecError("%s: sketch %r entity %d has no `call`"
                            % (where, sid, j + 1))
        lines.append(_generic_call("%s sketch %r entity %d" % (where, sid, j + 1),
                                   var, entity, sketches, results))
    return "\n".join(lines)


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






























# A quality row is a criterion plus a bound on it. Everything that is not one
# of these is handed to verifyMeshQuality as a keyword, so `threshold: 5.0`
# needs no special case here and neither will the next criterion Abaqus adds.
_QUALITY_RESERVED = ("criterion", "max", "min", "max_failed", "allow_na")


def _quality_rows(where: str, rows) -> str:
    """``expect.mesh.quality`` -- criteria the spec wants measured, and bounds.

    Kept generic rather than a pair of named knobs because the criteria are
    not interchangeable and no subset of them is "the important ones". Asked on
    Abaqus 2021, the valid set is ASPECT_RATIO, LARGE_ANGLE,
    LARGE_ANGLE_TRI_FACE, LARGE_ANGLE_QUAD_FACE, LONGEST_EDGE,
    ANGULAR_DEVIATION, SHAPE_FACTOR, STABLE_TIME_INCREMENT,
    GEOM_DEVIATION_FACTOR, SMALL_ANGLE, SHORTEST_EDGE, ANALYSIS_CHECKS,
    SMALL_ANGLE_TRI_FACE, SMALL_ANGLE_QUAD_FACE and MAX_FREQUENCY -- and that
    list came out of Abaqus's own error message, not out of a manual, so the
    deck does not need to carry a copy that can go stale.
    """
    if rows is None:
        return "None"
    if not isinstance(rows, list) or not rows:
        raise SpecError(
            "%s.quality: must be a non-empty list of {criterion: ..., ...} "
            "entries" % where)
    out = []
    for i, row in enumerate(rows):
        at = "%s.quality[%d]" % (where, i)
        if not isinstance(row, dict) or "criterion" not in row:
            raise SpecError("%s: every entry needs `criterion:`" % at)
        name = str(row["criterion"])
        if not _SYMBOL_RE.match(name):
            raise SpecError(
                "%s: criterion %r is not an abaqusConstants symbol. It is the "
                "bare word, all caps: ASPECT_RATIO, SMALL_ANGLE, "
                "SHORTEST_EDGE ..." % (at, name))

        bounds = []
        for key in ("max", "min"):
            value = row.get(key)
            if value is None:
                continue
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise SpecError("%s: `%s` must be a number" % (at, key))
            bounds.append("%r: %r" % (key, float(value)))

        max_failed = row.get("max_failed")
        if max_failed is not None:
            if isinstance(max_failed, bool) or not isinstance(max_failed, int):
                raise SpecError("%s: `max_failed` must be a whole number" % at)
            bounds.append("'max_failed': %d" % int(max_failed))

        kwargs = []
        for key in sorted(set(row) - set(_QUALITY_RESERVED)):
            value = row[key]
            if isinstance(value, (dict, list, tuple)):
                raise SpecError(
                    "%s: `%s` is passed straight to verifyMeshQuality, so it "
                    "has to be a number or a symbol" % (at, key))
            kwargs.append("%r: %s" % (str(key), _arg_expr(at, key, value,
                                                          {}, set())))

        if max_failed is not None and "threshold" not in row:
            raise SpecError(
                "%s: `max_failed` counts the elements Abaqus flags, and it only "
                "flags any once a `threshold:` says what counts as bad. State "
                "the threshold, or bound `max:`/`min:` on the worst value "
                "instead." % at)
        if not bounds:
            raise SpecError(
                "%s: states a criterion and no bound, so it would measure and "
                "then accept anything. Measured on Abaqus 2021, a 0.5x0.5x20 "
                "mesh of aspect ratio 40 passes ANALYSIS_CHECKS with 0 failed "
                "and 0 warned and is 5.2%% off on tip deflection -- the number "
                "has to be stated to mean anything." % at)

        out.append("{'criterion': %r, 'kwargs': {%s}, 'allow_na': %r, %s}"
                   % (name, ", ".join(kwargs),
                      bool(row.get("allow_na", False)), ", ".join(bounds)))
    body = ", ".join(out)
    return "(%s,)" % body if len(out) == 1 else "(%s)" % body


def _expect_lines(part_spec: dict) -> list[str]:
    expect = part_spec.get("expect") or {}
    stated: dict[str, object] = {}
    for key in _stated_measures(expect):
        if key == "cylinders":
            continue
        stated[key] = (float(expect[key]) if key in ("volume", "area")
                       else int(expect[key]))
    if "volume" in stated and expect.get("volume_tol") is not None:
        stated["volume_tol"] = float(expect["volume_tol"])
    if "area" in stated and expect.get("area_tol") is not None:
        stated["area_tol"] = float(expect["area_tol"])

    cylinders = expect.get("cylinders") or []
    rows = []
    for i, entry in enumerate(cylinders):
        where = "part %r expect.cylinders[%d]" % (part_spec["name"], i)
        at = entry.get("at")
        if not isinstance(at, (list, tuple)) or len(at) != 3:
            raise SpecError("%s: `at` must be three numbers (x, y, z)" % where)
        radius = float(entry["r"])
        if radius <= 0.0:
            raise SpecError("%s: r must be positive" % where)
        tol = float(entry["at_tol"]) if "at_tol" in entry else _centroid_tol(radius)
        if tol <= 0.0:
            raise SpecError("%s: at_tol must be positive" % where)
        rows.append("(%r, %r, %r, %r, %r)"
                    % (radius, float(at[0]), float(at[1]), float(at[2]), tol))
    if rows:
        stated["cylinders"] = "(%s,)" % ", ".join(rows)

    lines = []
    if stated:
        body = ", ".join(
            "%r: %s" % (key,
                        stated[key] if key == "cylinders" else repr(stated[key]))
            for key in sorted(stated))
        lines.append("_expect_part(p, %r, {%s})" % (str(part_spec["name"]), body))
    return lines


def _mesh_check_line(part_spec: dict) -> str:
    """The mesh check, wherever the mesh happens to have been made.

    Placement is the caller's business and it is not cosmetic: a part with a
    declarative `mesh:` block is meshed AFTER the geometry expectations run, so
    emitting this alongside them would check a part with no elements and refuse
    it as empty. A part meshed by a generic call already has its mesh by then.
    Both routes end up calling the same function with the same arguments.
    """
    name = str(part_spec["name"])
    mesh_expect = (part_spec.get("expect") or {}).get("mesh")
    if not mesh_expect:
        return "_mesh_check(p, %r)" % name

    where = "part %r expect.mesh" % part_spec["name"]
    unknown = set(mesh_expect) - {"elements", "nodes", "max_warned", "quality"}
    if unknown:
        raise SpecError("%s: %s is not something the mesh check measures"
                        % (where, ", ".join(sorted(unknown))))
    counts = []
    for key in ("elements", "nodes"):
        stated = mesh_expect.get(key)
        if stated is None:
            counts.append("None")
            continue
        try:
            counts.append(repr(selectors.normalise_expect(
                stated, default_plural=True)))
        except selectors.SelectorError as exc:
            raise SpecError("%s.%s: %s" % (where, key, exc))
    warned = mesh_expect.get("max_warned")
    # `nodes` rides as a KEYWORD and only when stated, so every part that does
    # not use it emits exactly the line it emitted before. Not cosmetic: the
    # frozen-model guard compares shipped decks byte for byte, and a sixth
    # positional argument would have rewritten every one of them to say the
    # same thing.
    tail = "" if counts[1] == "None" else ", nodes_expect=%s" % counts[1]
    return ("_mesh_check(p, %r, %s, %s, %s%s)"
            % (name, counts[0],
               repr(int(warned)) if warned is not None else "None",
               _quality_rows(where, mesh_expect.get("quality")), tail))


def _nested_selectors(node):
    """Every ``{select: ...}`` / ``{surface: ...}`` / ``{set: ...}`` in a call.

    A generic call's regions are not at a fixed key -- they are wherever the
    Abaqus method happens to want them -- so they have to be found rather than
    read off. Without this an interaction naming an instance that does not exist
    fails at run time with a KeyError inside a generated file, which is the
    failure mode validate_references exists to prevent.
    """
    if isinstance(node, dict):
        for form in ("select", "surface", "set"):
            if form in node and isinstance(node[form], str):
                yield (node[form], node.get("expect"))
                return
        # `one` forces its own expect, so it does not read one off the node.
        # It is listed here because leaving it out is a fail-open: measured,
        # {one: "Typo:face@x=min"} passed validate_references where the same
        # typo under {select:} was caught, and the bad instance name became a
        # KeyError inside the generated file instead.
        if "one" in node and isinstance(node["one"], str):
            yield (node["one"], "=1")
            return
        for key, value in node.items():
            if key in ("call", "as", "creates", "target"):
                continue
            for found in _nested_selectors(value):
                yield found
    elif isinstance(node, list):
        for item in node:
            for found in _nested_selectors(item):
                yield found


def _all_selectors(spec: dict):
    for i, op in enumerate(spec.get("assembly", {}).get("operations", []) or []):
        for raw, expect in _nested_selectors(op):
            yield ("assembly operation %d" % (i + 1), raw, expect)
    for i, inter in enumerate(spec.get("interactions", []) or []):
        label = inter.get("name") or "interaction %d" % (i + 1)
        if "call" in inter:
            for raw, expect in _nested_selectors(inter):
                yield ("interaction %d" % (i + 1), raw, expect)
            continue
        yield ("%s main" % label, inter["main"], inter.get("main_expect"))
        yield ("%s secondary" % label, inter["secondary"], inter.get("secondary_expect"))
    for i, entry in enumerate(spec.get("conditions", []) or []):
        for raw, expect in _nested_selectors(entry):
            yield ("condition %d" % (i + 1), raw, expect)
    for step in spec["steps"]:
        if _is_generic(step):
            for raw, expect in _nested_selectors(step):
                yield ("step %r" % step.get("name"), raw, expect)
            continue
        for i, bc in enumerate(step.get("bcs", []) or []):
            name = bc.get("name") or "bc %d" % (i + 1)
            yield ("step %r %s" % (step["name"], name), bc["region"], bc.get("expect"))
        for i, load in enumerate(step.get("loads", []) or []):
            name = load.get("name") or "load %d" % (i + 1)
            yield ("step %r %s" % (step["name"], name), load["region"], load.get("expect"))
    for i, entry in enumerate(spec.get("outputs", {}).get("regions", []) or []):
        yield ("outputs.regions[%d] %s" % (i, entry.get("name", "?")),
               entry["region"], entry.get("expect"))




# ---------------------------------------------------------------------------
# Script generation
# ---------------------------------------------------------------------------

def _resolve_file_args(spec: dict, spec_dir) -> tuple[dict, list[str]]:
    """Turn every ``{file: <path>}`` in the spec into an absolute literal.

    Done here, once, on a copy, rather than threading a directory down through
    every argument compiler: a path is the one kind of value that cannot be
    decided from the spec alone, and having exactly one place that decides it
    is what makes it auditable.

    Relative to the SPEC file, not to the run directory. `custom_inp` already
    resolves that way (`runner/build_model.py:_build_custom_inp`), the run
    directory is created per run and holds nothing the author put there, and a
    spec is the thing a person edits next to their geometry.

    A path that does not exist is refused HERE, before Abaqus is launched and
    before a licence is taken. Measured on Abaqus 2021, `mdb.openStep` on a
    missing file raises inside the kernel, which costs a CAE start-up and
    reports the failure in a log rather than against the spec line.

    Returns the rewritten spec and every path it resolved, because the build
    cache has to hash their CONTENTS: the generated script embeds the path, so
    editing a geometry file in place leaves the script byte-identical and the
    deck would be reused. That exact bug was found and fixed once already for
    `custom_inp` (see `_build_fingerprint`), and an import reintroduces it.
    """
    found: list[str] = []

    def walk(node, where):
        if isinstance(node, dict):
            if "file" in node:
                extra = set(node) - {"file"}
                if extra:
                    raise SpecError(
                        "%s: {file: ...} carries %s alongside it; a path names "
                        "a file and nothing else."
                        % (where, ", ".join(sorted(extra))))
                raw = node["file"]
                if not isinstance(raw, str) or not raw.strip():
                    raise SpecError("%s: {file: %r} is not a path"
                                    % (where, raw))
                path = Path(raw)
                if not path.is_absolute():
                    if spec_dir is None:
                        raise SpecError(
                            "%s: {file: %r} is relative and there is no spec "
                            "file to be relative TO -- this spec was handed "
                            "over as a mapping, not read from disk. Give an "
                            "absolute path." % (where, raw))
                    path = Path(spec_dir) / path
                path = path.resolve()
                if not path.exists():
                    raise SpecError(
                        "%s: {file: %r} resolves to %s, which does not exist. "
                        "Refused here rather than in the kernel, so the spec "
                        "line is named and no licence is taken."
                        % (where, raw, path))
                found.append(str(path))
                return {"literal": str(path)}
            return dict((k, walk(v, "%s.%s" % (where, k)))
                        for k, v in node.items())
        if isinstance(node, list):
            return [walk(v, "%s[%d]" % (where, i))
                    for i, v in enumerate(node)]
        return node

    return walk(spec, "spec"), found


def imported_files(spec: dict, spec_dir=None) -> list[str]:
    """Every path a `{file:}` in this spec resolves to, for the build cache."""
    return _resolve_file_args(spec, spec_dir)[1]


def generate_script(spec: dict, spec_dir=None) -> str:
    spec = _resolve_file_args(spec, spec_dir)[0]
    validate_references(spec)
    model = spec["meta"]["model_name"]

    # Written out rather than built as one list literal because the job block
    # needs what the conditions block learned: which sets a load was put on,
    # and how many nodes the spec said each holds.
    points_by_set: dict[str, int] = {}
    conditions = _conditions(spec, model, points_by_set)
    steps = _steps(spec, model, points_by_set)
    blocks = [
        _header(model),
        selectors.RUNTIME,
        _materials(spec, model),
        _model_setup(spec, model),
        _parts(spec, model),
        _assembly(spec, model),
        _interactions(spec, model),
        steps,
        conditions,
        _outputs(spec, model),
        _preview_dump(spec, model),
        _job(model, points_by_set, _keyword_inserts(spec)),
    ]
    # A block that had nothing to say contributes no blank line. Without this
    # the four cases that ship would each gain one, and a deck that differs is
    # a deck somebody has to re-read.
    return "\n".join(block for block in blocks if block.strip())


def _header(model: str) -> str:
    # The runtime table is generated from the same tuple the host-side check
    # uses, not written out again. Spelled twice they drift the moment a module
    # is added: the host would accept `connectorBehavior.ConnectorElasticity`
    # and the script would meet a KeyError.
    table = "_MODULES = {%s}" % ", ".join(
        "%r: %s" % (name, name) for name in _MODULES)
    return _PREAMBLE % (_IMPORT_LINE, table, str(model)) + _HELPERS


# The Python 2.7 these two constants hold is the payload, not the compiler.
# It was 1777 of this file's 6021 lines; see runner/kernel_runtime.py, whose
# split into topical chunks is pinned byte-identical by
# tests/test_kernel_runtime.py.
_PREAMBLE = kernel_runtime.PREAMBLE
_HELPERS = kernel_runtime.HELPERS


# Material properties that are one constant in a one-row table, which is the
# shape Abaqus wants for a property that does not vary. Same methods and same
# spelling as the v1 generator uses, so a spec means the same thing in both
# dialects.
_MATERIAL_SCALARS = (
    ("density", "Density"),
    ("conductivity", "Conductivity"),
    ("specific_heat", "SpecificHeat"),
    ("expansion_coeff", "Expansion"),
    ("electrical_conductivity", "ElectricalConductivity"),
)

_MATERIAL_KNOWN = ({"name", "E", "nu", "yield", "hardening"}
                   | {key for key, _ in _MATERIAL_SCALARS})

# Keys the schema declares that this side cannot turn into a material property,
# each with the reason. Named individually because "unknown key" is the wrong
# thing to say about a key the schema itself offers.
_MATERIAL_UNBUILDABLE = {
    "yield_stress": "write `yield` — that is the key this dialect reads, and "
                    "two spellings for one property is two places to disagree",
    "fracture_energy": "a cohesive damage property, and there is no cohesive "
                       "section in this dialect to attach it to",
    "max_traction": "a cohesive damage property, and there is no cohesive "
                    "section in this dialect to attach it to",
}


def _materials(spec: dict, model: str) -> str:
    """Every material property the spec declared, or a refusal naming the one
    that could not be built.

    Nothing is dropped in silence. This block used to emit Elastic and Density
    and ignore the rest, which meant a spec saying `yield: 250` got a purely
    elastic model: measured on Abaqus 2021, a cantilever loaded past its plastic
    limit came back COMPLETED with a peak Mises of 917.4 MPa against the 250 MPa
    it had declared, no *Plastic card in the input file and not one word in the
    log. The v1 generator emits Plastic for the same key, so the same spec meant
    two different models depending on which dialect read it.
    """
    lines = ["# --- Materials -------------------------------------------------------------"]
    entries = [spec["material"]] + list(spec.get("materials", []) or [])
    seen: set = set()
    for mat in entries:
        name = str(mat["name"])
        where = "material %r" % name
        if name in seen:
            continue
        seen.add(name)

        for key in sorted(mat):
            if key in _MATERIAL_KNOWN:
                continue
            reason = _MATERIAL_UNBUILDABLE.get(key)
            raise SpecError(
                "%s: %s" % (where, ("`%s` cannot be built here: %s"
                                    % (key, reason)) if reason else
                            ("`%s` is not a material property this dialect "
                             "knows. It reads: %s."
                             % (key, ", ".join(sorted(_MATERIAL_KNOWN)))))
                + " Declaring a property that is not emitted would leave the "
                  "spec saying one thing and the model doing another.")

        lines.append("m.Material(name=%r)" % name)
        lines.append("m.materials[%r].Elastic(table=((%r, %r),))"
                     % (name, float(mat["E"]), float(mat["nu"])))
        for key, method in _MATERIAL_SCALARS:
            if mat.get(key) is None:
                continue
            lines.append("m.materials[%r].%s(table=((%r,),))"
                         % (name, method, float(mat[key])))
        lines.extend(_plasticity(where, name, mat))
    return "\n".join(lines)


def _plasticity(where: str, name: str, mat: dict) -> list[str]:
    """Bilinear plasticity, spelled exactly as the v1 generator spells it.

    Two points: yield at zero plastic strain, and yield + 0.1 * hardening at a
    plastic strain of 0.1, so `hardening` is a modulus in stress units. Copied
    rather than reinvented because cases/cantilever_plastic is calibrated
    against the v1 form, and a second interpretation of the same key would make
    the two dialects disagree about the same spec.
    """
    if mat.get("yield") is None:
        if mat.get("hardening") is not None:
            raise SpecError(
                "%s: `hardening` without `yield` has nothing to harden. A "
                "hardening modulus is the slope after yielding starts; without "
                "a yield stress there is no plasticity to give it to." % where)
        return []
    stress = float(mat["yield"])
    hardening = float(mat.get("hardening") or 0.0)
    return ["m.materials[%r].Plastic(table=((%r, 0.0), (%r, 0.1)))"
            % (name, stress, stress + hardening * 0.1)]


def _parts(spec: dict, model: str) -> str:
    lines = ["# --- Parts -----------------------------------------------------------------"]
    for part_spec in spec["parts"]:
        lines.append(_one_part(part_spec))
    return "\n".join(lines)










def _assigns_its_own_section(part_spec: dict) -> bool:
    """Has the spec taken responsibility for section assignment itself.

    Only a dispatched `call: SectionAssignment` counts. Named ops cannot
    assign a section, so there is nothing else to look for -- and looking for
    something vaguer here would flip shipped specs onto the other path and
    move five frozen decks.
    """
    for feature in part_spec.get("features") or []:
        if isinstance(feature, dict) and str(feature.get("call", "")) == "SectionAssignment":
            return True
    return False


# What `expect:` has to state on an IMPORTED part, and why nothing else will
# do. Measured on Abaqus 2021 by exporting one 10 x 10 x 100 bar and reading it
# back three ways (artifacts/probe_import):
#
#   openStep   1 cell,  volume 10000.0,  6 faces,  8 vertices
#   openAcis   1 cell,  volume 10000.0,  6 faces,  8 vertices
#   openIges   0 cells, volume     0.0,  6 faces, 24 vertices, NO EXCEPTION
#
# IGES has no solid entity in the flavour Abaqus writes, so what comes back is
# six unstitched faces. `getVolume()` on it returns 0.0 rather than raising, and
# a part with no cells takes an empty `p.Set(name='ALL', cells=p.cells)` and an
# empty SectionAssignment without complaint. The FACE COUNT IS IDENTICAL to the
# solid's, so `expect: {faces: 6}` passes on both -- which is why one of
# `volume` or `cells` is required rather than "an expect block".
_IMPORT_EXPECT_KEYS = ("volume", "cells")
# The other half of the same rule, for a file that carries a MESH instead of a
# shape. Measured on Abaqus 2021 (artifacts/probe_orphan), `PartFromInputFile`
# on a deck holding one meshed bar returns 189 nodes, 80 elements and 0 cells,
# 0 faces, 0 edges, 0 vertices -- and `getVolume()` on it answers 0.0 without
# raising, exactly as the IGES shell does. So neither list can be the whole
# requirement: a geometry import must say volume or cells, a mesh import must
# say nodes or elements, and stating the wrong pair aborts at run time with the
# measured zero rather than silently.
_IMPORT_MESH_EXPECT_KEYS = ("nodes", "elements")


def _import_expect(part_spec: dict) -> tuple:
    """(geometry stated, mesh stated) -- what this import says it will be."""
    expect = part_spec.get("expect") or {}
    geometry = set(expect) & set(_IMPORT_EXPECT_KEYS)
    mesh = set(expect.get("mesh") or {}) & set(_IMPORT_MESH_EXPECT_KEYS)
    return geometry, mesh


def _is_orphan_import(part_spec: dict) -> bool:
    """A part read from a file that states a mesh and no geometry.

    Decided by what the SPEC declares rather than by the method it names.
    `PartFromInputFile` and `PartFromNastranFile` both make orphan meshes and
    the list would grow; more to the point, which one a file needs is the
    author's knowledge, and the run-time checks catch a wrong declaration
    either way -- a geometry claim on an orphan part meets volume 0.0, and a
    mesh claim on a shell meets 0 elements.
    """
    if "import" not in part_spec:
        return False
    geometry, mesh = _import_expect(part_spec)
    return bool(mesh) and not geometry


def _require_import_expect(part_spec: dict, where: str) -> None:
    geometry, mesh = _import_expect(part_spec)
    if geometry or mesh:
        return
    stated_mesh = (part_spec.get("expect") or {}).get("mesh")
    if stated_mesh:
        # Reached by writing `expect.mesh` with only `quality` or
        # `max_warned` in it, which are bounds on a mesh rather than a
        # statement of what arrived. Without this the message below says
        # "Stated: mesh" and reads as though the block had been ignored.
        raise SpecError(
            "%s: `expect.mesh` here states %s, which bounds a mesh without "
            "saying what came out of the file. Add `nodes` or `elements`: "
            "measured on Abaqus 2021, a part read by PartFromInputFile "
            "answers getVolume() with 0.0 and has 0 cells, so the counts are "
            "the only thing that says the file that arrived is the file that "
            "was meant." % (where, ", ".join(sorted(stated_mesh)) or "nothing"))
    raise SpecError(
        "%s: an imported part must state what came back -- `expect.volume` or "
        "`expect.cells` for a shape, or `expect.mesh.nodes` / "
        "`expect.mesh.elements` for a mesh. Measured on Abaqus 2021 with one "
        "bar exported and read back: STEP and SAT return 1 cell and volume "
        "10000.0; IGES returns 0 cells and volume 0.0 WITHOUT RAISING, with "
        "the SAME 6 faces the solid has, so a face count cannot tell them "
        "apart; and PartFromInputFile returns 189 nodes and 80 elements with "
        "0 cells and volume 0.0. Every one of those then takes an empty cell "
        "set and an empty section assignment in silence. Stated: %s."
        % (where, ", ".join(sorted(set(part_spec.get("expect") or {})))
           or "nothing"))


def _import_without_an_opener(part_spec: dict, where: str) -> list[str]:
    """One call on the model that makes the part itself.

    `PartFromGeometryFile` needs a file opened first; `PartFromInputFile` does
    not, and takes no `name` either. Measured on Abaqus 2021: a deck whose part
    is called `Bar` imports as `BAR`, and a deck holding two parts imports both
    (`ALPHA`, `BETA`). Since every other line in the generated script names the
    part from the spec, the name is taken back with `parts.changeKey` -- which
    was measured to work -- and a file that produced anything other than
    exactly one part is refused rather than guessed at.
    """
    made = part_spec["import"].get("part")
    if not isinstance(made, dict) or "call" not in made:
        raise SpecError(
            "%s: with no `open:`, `import.part` must be a call mapping naming "
            "a model method that makes the part, e.g. "
            "{call: PartFromInputFile, inputFileName: {file: bar.inp}}. "
            "Written as a call rather than a format flag because Abaqus reads "
            "an Abaqus deck and a Nastran deck with different methods, each "
            "taking its own keywords." % where)
    for reserved, why in (
            ("name", "measured on Abaqus 2021, PartFromInputFile does not "
                     "take one -- the deck names the part and Abaqus upper-"
                     "cases it, so the part's own `name:` is applied "
                     "afterwards with parts.changeKey"),
            ("as", "the part is picked up from the model below")):
        if reserved in made:
            raise SpecError("%s: `import.part.%s` is not settable here -- %s."
                            % (where, reserved, why))
    results: set[str] = set()
    return [
        "",
        "_before_import = list(m.parts.keys())",
        _generic_call(where, "m", dict(made), {}, results),
        "p = _gimported(m, %r, _before_import, %r)"
        % (str(part_spec["name"]), where),
    ]


def _import_lines(part_spec: dict) -> list[str]:
    """Open a geometry file and make a part out of what came back.

    Two dispatched calls rather than a fixed pair, because Abaqus opens STEP,
    IGES, ACIS, VDA, CATIA, Parasolid and Pro/E with a different method each,
    all taking `fileName` and each taking its own extras (openIges alone has
    msbo, trimCurve and topology). An enum here could only ever import the
    formats somebody had already written a branch for.
    """
    name = str(part_spec["name"])
    spec = part_spec["import"]
    where = "part %r import" % name
    if "features" in part_spec:
        raise SpecError(
            "%s: this part has both `import:` and `features:`. A part is "
            "either read from a file or built here; doing both would mean the "
            "features silently reshape somebody else's geometry." % where)

    opener = spec.get("open")
    if opener is not None and (not isinstance(opener, dict)
                               or "call" not in opener):
        raise SpecError(
            "%s: `import.open` must be a call mapping naming the Abaqus "
            "opener, e.g. {call: openStep, fileName: {file: bracket.step}}. "
            "Abaqus opens each format with its own method and each takes its "
            "own keywords, so this names the method rather than choosing from "
            "a list." % where)

    _require_import_expect(part_spec, where)
    if opener is None:
        return _import_without_an_opener(part_spec, where)

    for key, why in (
            ("as", "the result goes straight into PartFromGeometryFile below "
                   "and is not reachable from anywhere else"),
            ("target", "an opener is a method on `mdb`, which is what makes "
                       "it the one call in a spec that is not on the model or "
                       "the part")):
        if key in opener:
            # Both would have been overwritten silently: `as` by the internal
            # alias, `target` by the fixed `mdb`. Dropping a key the spec wrote
            # is the defect this layer keeps finding elsewhere, so it is not
            # introduced here.
            raise SpecError("%s.open: `%s:` is not settable here -- %s."
                            % (where, key, why))

    results: set[str] = set()
    alias = "imported_geometry_%s" % re.sub(r"[^A-Za-z0-9_]+", "_", name)
    lines = [""]
    lines.append(_generic_call(where + ".open", "mdb",
                               dict(opener, **{"as": alias}), {}, results))

    made = dict(spec.get("part") or {})
    for reserved, why in (("name", "the part's own `name:` is what names it"),
                          ("geometryFile", "the opener above supplies it")):
        if reserved in made:
            raise SpecError("%s: `import.part.%s` is not settable here -- %s."
                            % (where, reserved, why))
    made["name"] = {"literal": name}
    made["geometryFile"] = {"ref": alias}
    made.setdefault("dimensionality", "THREE_D")
    made.setdefault("type", "DEFORMABLE_BODY")
    made["call"] = "PartFromGeometryFile"
    lines.append("p = " + _generic_call(where, "m", made, {}, results))
    return lines


def _one_part(part_spec: dict) -> str:
    name = str(part_spec["name"])
    mesh_spec = part_spec.get("mesh") or {}
    orphan = _is_orphan_import(part_spec)
    if orphan and mesh_spec:
        raise SpecError(
            "part %r is imported as a mesh (its `expect` states nodes or "
            "elements and no volume or cells) and also carries a `mesh:` "
            "block. There is nothing to seed: measured on Abaqus 2021, a part "
            "read by PartFromInputFile has 0 cells, 0 faces and 0 edges, so "
            "seedPart and setElementType have no region to act on. The mesh "
            "came in the file; say what it should be in `expect.mesh`." % name)
    if not mesh_spec and not (part_spec.get("expect") or {}).get("mesh"):
        # `mesh:` is optional and the emitter below branches on it with no
        # else, so a part in neither state used to get no seedPart, no
        # generateMesh and no check. Measured: it reaches the .inp as an empty
        # `*Part` with a live `*Instance`, the job COMPLETED, and the part
        # contributed no mass and no stiffness with nothing saying so. Lowest
        # trigger of any silent failure in this layer -- one omitted optional
        # key -- so it is refused here rather than left to the reader.
        raise SpecError(
            "part %r has no `mesh:` block and no `expect.mesh`, so nothing "
            "meshes it and nothing checks that anything did. An unmeshed part "
            "still reaches the input file as an empty *Part with a live "
            "*Instance and the job completes without a word. Either give it a "
            "`mesh:` block, or mesh it with generic calls and say what the "
            "mesh should come to in `expect.mesh`." % name)
    dimensionality = str(part_spec.get("dimensionality", "THREE_D")).upper()
    if dimensionality not in _DIMENSIONALITY:
        raise SpecError(
            "part %r declares dimensionality %r. Known: %s. This is not a "
            "cosmetic label -- it decides whether the section, the element "
            "type and the mesh controls act on the part's cells or on its "
            "faces, and getting it wrong builds a set of zero entities and "
            "assigns a section to nothing, in silence."
            % (name, part_spec.get("dimensionality"),
               ", ".join(sorted(_DIMENSIONALITY))))
    body = _DIMENSIONALITY[dimensionality]

    element = str(mesh_spec.get("element", DEFAULT_MESH_ELEMENT))
    shape, elem_codes = _mesh_shape(name, element)
    allowed_shapes = _SHAPES_FOR_DIMENSIONALITY[dimensionality]
    if mesh_spec and shape not in allowed_shapes:
        raise SpecError(
            "part %r is %s and asks for mesh.element %r, which is a %s "
            "element. A %s part can only be meshed with %s. Abaqus does not "
            "refuse this pairing -- elemShape defaults to HEX and a shape a "
            "body has none of meshes nothing without raising, which is the "
            "silent failure this layer exists to stop."
            % (name, dimensionality, element, shape, dimensionality,
               " or ".join(allowed_shapes)))
    library = "STANDARD"

    # A planar section carries a thickness; a 3D one must not. Measured on
    # Abaqus 2021: `thickness=None` on a plane-strain part is accepted and
    # Abaqus assumes 1.0, so an author who meant 5 mm gets a fifth of the
    # stiffness with nothing said. It is therefore read from the spec when the
    # part is planar, and refused on a 3D part where it would mean nothing.
    thickness = part_spec["section"].get("thickness")
    if thickness is not None and dimensionality == "THREE_D":
        raise SpecError(
            "part %r is THREE_D and its section states a thickness. A solid "
            "section on a 3D body has no thickness -- the geometry is the "
            "thickness. Drop the key, or declare the part TWO_D_PLANAR." % name)
    section_line = ("m.HomogeneousSolidSection(name=%r, material=%r, thickness=%s)"
                    % ("SEC_" + name, str(part_spec["section"]["material"]),
                       "None" if thickness is None else repr(float(thickness))))
    assigns_own = _assigns_its_own_section(part_spec)

    if "import" in part_spec:
        lines = _import_lines(part_spec)
    else:
        lines = [
            "",
            "p = m.Part(name=%r, dimensionality=%s, type=DEFORMABLE_BODY)"
            % (name, dimensionality),
        ]
    if assigns_own:
        # Ahead of the features, because the spec has to be able to name it:
        # SEC_<part> is what the half the spec did not partition off gets, and
        # defining it afterwards means `sectionName: SEC_Bar` inside a feature
        # dies with 'The section "SEC_Bar" does not exist in the model.'
        # (measured). On the fallback path it stays where it was.
        lines.append(section_line)
    if "import" not in part_spec:
        lines += _feature_lines(part_spec)
    # Before meshing, on purpose: `expect` describes the geometry, and meshing a
    # part that is already the wrong shape burns minutes and then passes its own
    # mesh check.
    lines += _expect_lines(part_spec)

    if assigns_own:
        # The section itself was already defined above the features. What is
        # dropped here is the whole-part assignment that used to follow the
        # spec's own and override it -- measured on a partitioned bar, the
        # written .inp carried one `*Solid Section, elset=ALL, material=Steel`
        # and nothing referenced the aluminium at all.
        lines.append("_expect_sections(p, %r)" % name)
    elif orphan:
        # `cells=p.cells` is the whole reason this branch exists. Measured on
        # Abaqus 2021, on a part with no cells it builds a set holding 0 cells
        # and then assigns a section to 0 cells, BOTH WITHOUT AN EXCEPTION --
        # the shape that made `expect` mandatory for geometry imports in the
        # first place. An orphan mesh has elements instead, and an element set
        # is what `*Solid Section, elset=` wants anyway.
        lines += [
            "p.Set(name='ALL', elements=p.elements)",
            section_line,
            "p.SectionAssignment(region=p.sets['ALL'], sectionName=%r, offset=0.0,"
            % ("SEC_" + name),
            "    offsetType=MIDDLE_SURFACE, offsetField='',",
            "    thicknessAssignment=FROM_SECTION)",
        ]
    else:
        # Byte-for-byte as it was, including the order: every shipped spec is
        # on this path and five frozen decks are compared against HEAD.
        lines += [
            "p.Set(name='ALL', %s=p.%s)" % (body, body),
            section_line,
            "p.SectionAssignment(region=p.sets['ALL'], sectionName=%r, offset=0.0,"
            % ("SEC_" + name),
            "    offsetType=MIDDLE_SURFACE, offsetField='',",
            "    thicknessAssignment=FROM_SECTION)",
        ]
    if mesh_spec:
        lines.append("p.setElementType(regions=(p.%s,), elemTypes=(" % body)
        lines += ["    mesh.ElemType(elemCode=%s, elemLibrary=%s)," % (code, library)
                  for code in elem_codes]
        # A one-element tuple keeps its comma. Without it the kernel says
        # "elemTypes; found ElemType, expecting tuple" -- which is a loud
        # failure, but only reachable once a single-shape element exists.
        if len(elem_codes) > 1:
            lines[-1] = lines[-1].rstrip(",")
        lines[-1] += "))"
        technique = mesh_spec.get("technique")
        if technique or shape not in ("HEX", "QUAD"):
            # Written unconditionally off HEX because elemShape defaults to HEX,
            # and HEX on a body with no hexes meshes nothing without raising.
            # Measured: HEX/STRUCTURED fails outright on a plate with a hole
            # ("Some regions cannot be Mapped") unless the part is partitioned.
            # It fails loudly, so it is left available rather than refused.
            lines.append(
                "p.setMeshControls(regions=p.%s, elemShape=%s, technique=%s)"
                % (body, shape,
                   _TECHNIQUE_CONSTANT[_mesh_technique(name, shape, technique)]))
        lines.append("p.seedPart(size=%r, deviationFactor=0.1, minSizeFactor=0.1)"
                     % float(mesh_spec["seed"]))
        lines += _local_seeds(name, mesh_spec)
        lines += ["p.generateMesh()", _mesh_check_line(part_spec)]
    elif (part_spec.get("expect") or {}).get("mesh"):
        # No declarative mesh block, so a generic call made the mesh and it
        # already exists by the time the geometry expectations have run.
        lines.append(_mesh_check_line(part_spec))
    # After the mesh, because a seam has nothing to show before there is one.
    lines += _seam_check_lines(part_spec)
    return "\n".join(lines)


def _seam_names(part_spec: dict) -> list[tuple]:
    """Every `assignSeam` in this part, with the set each one was handed.

    Matched on the METHOD NAME, which is the one place in this dialect that is
    justified: the question is not "what does Abaqus offer" but "does this part
    contain something whose effect has to be checked", and the answer has to
    come from the spec rather than from a list of blessed operations.
    """
    found = []
    for i, feature in enumerate(part_spec.get("features") or []):
        if not isinstance(feature, dict) or feature.get("call") != "assignSeam":
            continue
        where = "part %r feature %d" % (str(part_spec["name"]), i + 1)
        region = feature.get("regions")
        if not isinstance(region, dict) or "set" not in region:
            raise SpecError(
                "%s: assignSeam needs `regions: {set: ...}`. Measured on "
                "Abaqus 2021, it answers a raw sequence with `regions; found "
                "GeomSequence, expecting Set` on the part exactly as it does "
                "on the assembly, so `{select:}` cannot reach it." % where)
        name = region.get("name")
        if not name:
            raise SpecError(
                "%s: the set a seam is assigned to needs an explicit `name:`. "
                "The check that the seam did anything has to find that set "
                "again after the mesh is generated, and a derived name would "
                "make the spec and the check agree by coincidence." % where)
        found.append((str(name).upper(), where))
    return found


def _seam_check_lines(part_spec: dict) -> list[str]:
    """A seam that changed nothing is the failure this has to catch.

    Measured on Abaqus 2021 (artifacts/probe_seam2), one 10 x 10 x 10 block
    partitioned at mid-height, meshed at seed 5:

        no seam                     27 nodes
        seam on the INTERIOR face   36 nodes   <- the 9 seam positions doubled
        seam on the top face        27 nodes   <- accepted, no exception
        seam on the bottom face     27 nodes   <- accepted, no exception

    So `assignSeam` on a face that is not shared by two cells returns without a
    word and leaves the model exactly as it was. Picking the wrong face with a
    selector is an ordinary mistake, and the result is a model with no crack in
    it that builds, solves and reports success.

    What makes it checkable: after meshing, the seam's own set holds BOTH
    copies. Measured, the interior case gives 18 nodes at 9 distinct positions
    -- exactly two per position -- where an unseamed face gives 9 at 9. So the
    number of positions carrying more than one node IS the seam, and the spec
    states it.
    """
    seams = _seam_names(part_spec)
    stated = (part_spec.get("expect") or {}).get("seams")
    if not seams:
        # Not `return []`. A part that states a seam and assigns none has had
        # its expectation dropped on the floor, which is the shape #46 was:
        # the gate was built and then never locked, so writing one was
        # indistinguishable from writing nothing. Renaming the set in the
        # feature and forgetting the expect entry lands exactly here.
        if stated:
            raise SpecError(
                "part %r states expect.seams and no feature assigns a seam, "
                "so nothing would check it. Either add the `assignSeam` "
                "feature or drop the expectation." % str(part_spec["name"]))
        return []
    if not stated:
        raise SpecError(
            "part %r assigns a seam and does not say what it should come to. "
            "Write `expect.seams: [{set: <NAME>, duplicated: <n>}]`. This is "
            "required rather than optional because the failure is silent: "
            "measured on Abaqus 2021, assignSeam on a face that is not shared "
            "by two cells is accepted without an exception and changes "
            "nothing -- 27 nodes before and 27 after, where the correct face "
            "gives 36." % str(part_spec["name"]))
    if not isinstance(stated, list):
        raise SpecError("part %r: expect.seams must be a list"
                        % str(part_spec["name"]))

    by_set = {}
    for entry in stated:
        if not isinstance(entry, dict) or "set" not in entry \
                or "duplicated" not in entry:
            raise SpecError(
                "part %r: each entry in expect.seams needs `set` and "
                "`duplicated` -- the set the seam was assigned to, and how "
                "many node positions along it should end up carrying two "
                "nodes instead of one." % str(part_spec["name"]))
        by_set[str(entry["set"]).upper()] = entry["duplicated"]

    lines = []
    for name, where in seams:
        if name not in by_set:
            raise SpecError(
                "%s assigns a seam to set %r and expect.seams does not "
                "mention it. Stated: %s."
                % (where, name, ", ".join(sorted(by_set)) or "nothing"))
        wanted = by_set.pop(name)
        if not isinstance(wanted, int) or isinstance(wanted, bool) \
                or wanted < 1:
            raise SpecError(
                "%s: expect.seams `duplicated` for %r is %r. It is a count of "
                "node positions and a seam that duplicates none of them did "
                "nothing, so it has to be at least 1."
                % (where, name, wanted))
        lines.append("_expect_seam(p, %r, %d, %r)" % (name, wanted, where))
    if by_set:
        raise SpecError(
            "part %r: expect.seams names %s, and no feature assigns a seam to "
            "it." % (str(part_spec["name"]), ", ".join(sorted(by_set))))
    return lines


def _local_seeds(part_name: str, mesh_spec: dict) -> list[str]:
    """Refine the mesh where the spec says to.

    A uniform seed fine enough for a hole edge is a seed fine enough for the
    whole plate, which is how a stress-concentration model becomes a twenty
    minute job. The refinement is what makes the case runnable, so it has to be
    expressible -- and it has to go through the same counted selector as
    everything else, because seeding an empty edge set is silent: the mesh
    still generates, just at the coarse size, and Kt comes out low and
    plausible.
    """
    lines: list[str] = []
    for i, seed in enumerate(mesh_spec.get("local_seeds", []) or []):
        where = "part %r local_seeds[%d]" % (part_name, i)
        raw = str(seed["region"])
        sel = _parse(raw, seed.get("expect"), where)
        if sel.instance is not None:
            raise SpecError(
                "%s: %r names an instance. A local seed is applied to the PART, "
                "before it is instanced, so it cannot name one -- write %r."
                % (where, raw, raw.split(":", 1)[1]))
        if sel.kind != "edge":
            raise SpecError(
                "%s: %r selects %ss. Abaqus seeds edges; a face or a cell has "
                "no seed of its own." % (where, raw, sel.kind))
        call = selectors.resolve_expression(sel, "p")
        lines.append("p.seedEdgeBySize(edges=%s," % call)
        lines.append("    size=%r, deviationFactor=0.1, minSizeFactor=0.1,"
                     % float(seed["size"]))
        lines.append("    constraint=FINER)")
    return lines


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
    else:
        centre, radius = profile["circle"]["center"], float(profile["circle"]["r"])
        lines.append("%s.CircleByCenterPerimeter(center=(%r, %r), point1=(%r, %r))"
                     % (var, float(centre[0]), float(centre[1]),
                        float(centre[0]) + radius, float(centre[1])))
    lines.append("_SKETCHES[(%r, %r)] = %s"
                 % (str(part_name), str(feat["id"]), _profile_data(profile)))
    return "\n".join(lines)


def _profile_data(profile: dict) -> str:
    """The profile as plain data, so _cut() can redraw it on a transform."""
    if "rect" in profile:
        c1, c2 = profile["rect"]["corner1"], profile["rect"]["corner2"]
        return ("{'rect': (%r, %r, %r, %r), 'circles': ()}"
                % (float(c1[0]), float(c1[1]), float(c2[0]), float(c2[1])))
    centre, radius = profile["circle"]["center"], float(profile["circle"]["r"])
    return ("{'rect': None, 'circles': ((%r, %r, %r),)}"
            % (float(centre[0]), float(centre[1]), radius))


def _sheet_size(profile: dict) -> float:
    if "rect" in profile:
        c1, c2 = profile["rect"]["corner1"], profile["rect"]["corner2"]
        span = max(abs(float(c2[0]) - float(c1[0])), abs(float(c2[1]) - float(c1[1])))
    else:
        span = 2.0 * float(profile["circle"]["r"])
    return max(1.0, span * 4.0)


def _assembly(spec: dict, model: str) -> str:
    lines = [
        "",
        "# --- Assembly --------------------------------------------------------------",
        "a = m.rootAssembly",
        "a.DatumCsysByDefault(CARTESIAN)",
    ]
    for inst in spec["assembly"]["instances"]:
        lines.append("a.Instance(name=%r, part=m.parts[%r], dependent=ON)"
                     % (str(inst["name"]), str(inst["part"])))
        if inst.get("translate"):
            t = inst["translate"]
            lines.append("a.translate(instanceList=(%r,), vector=(%r, %r, %r))"
                         % (str(inst["name"]), float(t[0]), float(t[1]), float(t[2])))
        if inst.get("rotate"):
            rot = inst["rotate"]
            origin = rot.get("origin", [0.0, 0.0, 0.0])
            axis = rot["axis"]
            lines.append(
                "a.rotate(instanceList=(%r,), axisPoint=(%r, %r, %r),\n"
                "         axisDirection=(%r, %r, %r), angle=%r)"
                % (str(inst["name"]),
                   float(origin[0]), float(origin[1]), float(origin[2]),
                   float(axis[0]), float(axis[1]), float(axis[2]),
                   float(rot["angle"])))
    # The snapshot has to be taken before the operations run, because the only
    # way to tell a part an operation created from one the spec declared is to
    # have looked first.
    #
    # Both lines are emitted together or not at all, and only when there are
    # operations, so the five shipped cases keep the decks they have. That is
    # not just thrift: with no operations nothing new can reach the analysis.
    # This is the one block whose dispatch defaults to the root assembly; the
    # other three default to the model (`_dispatch_target`), and the methods
    # that make an instance are assembly methods. A bare `m.Part(...)` from
    # anywhere else creates a part nothing can instance, because
    # validate_references requires every declared instance to name a part from
    # `parts:`. Same predicate, and the same kind of reason, as the
    # _expect_connectors line a few lines down.
    operations = spec["assembly"].get("operations") or []
    if operations:
        lines.append("_asm_parts_before = set(m.parts.keys())")
    lines += _assembly_operations(spec)
    if operations:
        lines.append("_expect_asm_meshed(m, a, _asm_parts_before)")
    lines += _assembly_expect(spec)
    return "\n".join(lines)


def _assembly_operations(spec: dict) -> list[str]:
    """Generic dispatch against the root assembly.

    `instances` with translate/rotate covers positioning by arithmetic, which
    means every position is a number somebody worked out by hand. The rest of
    the assembly API is not reachable that way and is where the interesting
    operations live: LinearInstancePattern, RadialInstancePattern,
    InstanceFromBooleanCut, PartFromBooleanMerge, and the positioning
    CONSTRAINTS (FaceToFace, ParallelFace, CoincidentPoint, EdgeToEdge) that let
    a spec say "this face against that face" instead of computing the vector.

    Same dispatch as a part feature, one scope difference: here a selector must
    name its instance, because that is the only thing that distinguishes two
    instances of one part.
    """
    results: set[str] = set()
    lines: list[str] = []
    for i, op in enumerate(spec["assembly"].get("operations", []) or []):
        where = "assembly operation %d" % (i + 1)
        if "call" not in op:
            raise SpecError("%s has no `call`" % where)
        # Assembly operations can build a Set since #76, which is what a crack
        # front needs -- but a SEAM still may not be assigned here, and the
        # refusal has to stay for a reason that has nothing to do with sets.
        # Measured (#70): a seam assigned AFTER `generateMesh` leaves the
        # node count untouched and raises nothing. Part features run before
        # `generateMesh`; assembly operations run after it. Whether Abaqus
        # would even accept an ASSEMBLY set here is NOT measured and does not
        # need to be -- both answers make the route wrong, and stating the one
        # we did not check would be the same inference-as-measurement this
        # task had to correct once already. So the refusal is on timing, and
        # the message routes to where the timing is right.
        if str(op["call"]) == "assignSeam":
            raise SpecError(
                "%s assigns a seam on the assembly. A seam belongs on the "
                "PART, and the reason is timing rather than scope. Measured on "
                "Abaqus 2021: a seam assigned AFTER `generateMesh` leaves the "
                "node count exactly as it was and says nothing -- 27 nodes "
                "before and 27 after, against 36 when the same seam is "
                "assigned first. Part features run before `generateMesh`; "
                "assembly operations run after it. So nothing this route "
                "produces can separate anything, whatever Abaqus makes of the "
                "argument. Move the same call into the part's `features:` -- "
                "`{set:}` builds a part set there -- and state "
                "`expect.seams: [{set: <name>, duplicated: <n>}]`." % where)
        singular = _singular_selects(op)
        measures = _asm_op_expect(where, op)
        # An assembly operation can build an assembly Set and an assembly
        # Surface, like a condition can. It could not until #76, and the
        # refusal read "an assembly operation cannot build one" -- true of this
        # function and not of Abaqus. `a.Set(...)` is what
        # `engineeringFeatures.ContourIntegral(crackFront=...)` is documented to
        # take: a crack front is an ASSEMBLY set, not a part set, because the
        # crack is declared on the instanced model.
        #
        # What this is NOT: the thing that made the contour integral
        # unwritable. Measured (artifacts/probe_ci_tuple_solve, Abaqus 2021),
        # `{select:}` compiles to a tuple, the tuple-retry shim hands it over,
        # and the same plate comes back at J = 2.503265619277954 either way --
        # the same number to every digit. What the set form adds is a NAMED
        # crack front, which `{named_set:}` can reuse and which reads back in
        # the ODB. The two things that really were in the way were THREE_D
        # parts and no selector able to name one of two.
        sets: list = []
        surfaces: list = []
        call = _generic_call(where, _dispatch_target(where, op, results, "a"),
                             op, {}, results, scope="assembly",
                             surfaces=surfaces, sets=sets)
        if not singular and measures is None:
            lines.append(call)
            continue
        # Bound so the return value can be looked at. A user `as:` cannot
        # collide: _generic_call binds aliases into the _RESULTS dict, never
        # as a bare module name.
        handle = "_asm_op_%d" % (i + 1)
        if call.startswith("_RESULTS["):
            lines.append(call)
            handle = call.split(" = ", 1)[0]
        else:
            lines.append("%s = %s" % (handle, call))
        if singular:
            lines.append("_expect_recorded(%s, %r, %r)"
                         % (handle, where, ", ".join(singular)))
        if measures is not None:
            lines.append("_expect_asm_op(m, %s, %r, %s)"
                         % (handle, where, measures))
    return lines


def _asm_op_expect(where: str, op: dict) -> str | None:
    """`expect:` on an assembly operation -- what to measure on what it made.

    Honoured rather than refused, unlike model_setup and steps, because an
    operation returns a modelling result and one of its silent failures is
    measured. Abaqus 2021, artifacts/probe_asm_op_expect:

      cut that removes nothing   RAISES ("The cut operation failed because the
                                 base instance was not modified") -- loud
                                 already, nothing to add.
      merge across a gap         does NOT raise. Returns a Part carrying every
                                 cubic millimetre of both bodies (10000.0 for
                                 two 5000 halves) and TWO cells instead of one,
                                 so what solves is two loose pieces where the
                                 spec asked for one solid.

    That is why the vocabulary is volume AND cells: on the one failure that is
    silent, volume is blind and only the cell count sees it.
    """
    expect = op.get("expect")
    if expect is None:
        return None
    if not isinstance(expect, dict):
        raise SpecError("%s: `expect:` must be a mapping" % where)
    unknown = set(expect) - {"volume", "volume_tol", "cells"}
    if unknown:
        raise SpecError(
            "%s: expect measures `volume` and `cells` on what the call "
            "returned; got %s. A measure that is not taken is worse than none, "
            "because it reads as checked."
            % (where, ", ".join(sorted(unknown))))
    if "volume_tol" in expect and "volume" not in expect:
        raise SpecError(
            "%s: `expect.volume_tol` without `expect.volume` — a tolerance on "
            "a number nobody stated." % where)
    if "volume" not in expect and "cells" not in expect:
        raise SpecError(
            "%s: `expect:` states neither volume nor cells, so it checks "
            "nothing." % where)
    volume = expect.get("volume")
    cells = expect.get("cells")
    if volume is not None and float(volume) <= 0.0:
        raise SpecError("%s: `expect.volume` is %s; a volume is positive."
                        % (where, volume))
    if cells is not None and int(cells) < 0:
        raise SpecError("%s: `expect.cells` is %s; a count is not negative."
                        % (where, cells))
    return "(%s, %s, %s)" % (
        "None" if volume is None else repr(float(volume)),
        repr(float(expect.get("volume_tol", DEFAULT_VOLUME_TOL))),
        "None" if cells is None else repr(int(cells)))


def _singular_selects(op: dict) -> list[str]:
    """The argument keys this call is handed a sequence of exactly one for.

    `{select:}` always compiles to a GeomSequence -- core/selectors.py returns
    what getByBoundingBox produced, never an entity out of it -- so a method
    that wants one Face is handed a container instead. This finds the shape;
    only the kernel can tell whether the method minded, so this list is what
    arms the check there and nothing more.
    """
    keys = []
    for key, value in op.items():
        if key in ("call", "as", "creates", "target", "expect"):
            continue
        if not isinstance(value, dict) or "select" not in value:
            continue
        if value.get("expect") is not None:
            continue            # said out loud that a sequence was meant
        try:
            if selectors.parse(str(value["select"])).expect == "=1":
                keys.append(key)
        except selectors.SelectorError:
            continue            # _generic_call reports it with the real message
    return keys


def _assembly_expect(spec: dict) -> list[str]:
    """What the finished assembly should be, checked before anything uses it.

    The failures this catches were all measured: a pattern that produces
    nothing (`instances`), a positioning constraint that moves nothing (`at`),
    a wire nothing was assigned to (`wires`). Every one of them leaves a model
    that meshes, solves and reports COMPLETED.

    NOT a boolean that removes nothing, which this used to claim. Measured:
    after InstanceFromBooleanCut the assembly holds the same three names
    whether the cut removed material or not, so the count is blind to it, and
    a through-pin cut does not move the bounding box the centroid comes from.
    Nothing in this layer reads a volume -- getVolume() is called in exactly
    one place in the generator, on a part declared in `parts:`, and a part an
    operation creates is not one of those.
    """
    expect = spec["assembly"].get("expect") or {}
    unknown = set(expect) - {"instances", "at", "wires"}
    if unknown:
        raise SpecError("assembly.expect: %s is not something the check "
                        "measures" % ", ".join(sorted(unknown)))
    lines = []

    # Only an assembly operation can make a wire (WirePolyLine is an assembly
    # method and nothing else creates assembly-level edges), so a spec without
    # operations cannot have one -- which is also why the four shipped cases
    # generate exactly what they did before.
    if spec["assembly"].get("operations") or expect.get("wires") is not None:
        want = expect.get("wires")
        lines.append("_expect_connectors(m, a, %s)"
                     % ("None" if want is None else int(want)))
    if not expect:
        return lines
    if expect.get("instances") is not None:
        lines.append("_expect_instances(a, %d)" % int(expect["instances"]))
    rows = []
    for i, entry in enumerate(expect.get("at") or []):
        where = "assembly.expect.at[%d]" % i
        centre = entry.get("centroid")
        if not isinstance(centre, (list, tuple)) or len(centre) != 3:
            raise SpecError("%s: `centroid` must be three numbers" % where)
        # Unlike a cylinder, an instance carries no radius the host can scale
        # against, and its size is not known until the assembly exists. So the
        # default is left as None and _expect_placed derives it from the box it
        # measures anyway. An explicit tol still wins.
        if "tol" in entry:
            tol = float(entry["tol"])
            if tol <= 0.0:
                raise SpecError("%s: tol must be positive" % where)
            tol_arg = repr(tol)
        else:
            tol_arg = "None"
        rows.append("(%r, %r, %r, %r, %s)"
                    % (str(entry["instance"]), float(centre[0]),
                       float(centre[1]), float(centre[2]), tol_arg))
    if rows:
        lines.append("_expect_placed(a, (%s,))" % ", ".join(rows))
    return lines


def _region(where: str, raw: str, expect, set_name: str, as_surface: bool) -> str:
    """Emit an assembly-level Set or Surface built from a checked selector."""
    sel = _parse(raw, expect, where)
    owner = "a.instances[%r]" % str(sel.instance)
    call = selectors.resolve_expression(sel, owner)
    if as_surface:
        kwarg = sel.surface_kwarg
        if kwarg is None:
            raise SpecError(
                "%s: %r selects %ss, which cannot form a surface. A pressure "
                "load and a tie both need faces." % (where, raw, sel.kind))
        return "a.Surface(name=%r, %s=%s)" % (set_name, kwarg, call)
    return "a.Set(name=%r, %s=%s)" % (set_name, sel.attribute, call)


def _interactions(spec: dict, model: str) -> str:
    entries = spec.get("interactions", []) or []
    if not entries:
        return ""
    lines = ["",
             "# --- Interactions ----------------------------------------------------------"]
    results: set = set()
    for i, inter in enumerate(entries):
        if "call" in inter:
            lines.extend(_generic_interaction(
                i, inter, results, _declared_materials(spec)))
            continue
        name = str(inter.get("name") or "Interaction-%d" % (i + 1))
        main_set, sec_set = name.upper() + "_MAIN", name.upper() + "_SEC"
        lines.append(_region("%s main" % name, inter["main"],
                             inter.get("main_expect"), main_set, as_surface=True))
        lines.append(_region("%s secondary" % name, inter["secondary"],
                             inter.get("secondary_expect"), sec_set, as_surface=True))
        if inter["type"] == "tie":
            lines.append(_tie_call(name, inter, main_set, sec_set))
        else:
            lines.extend(_contact_calls(name, inter, main_set, sec_set))
    return "\n".join(lines)


def _dispatch_target(where: str, entry: dict, results: set,
                     default: str = "m", materials: tuple = ()) -> str:
    """`default` unless `target:` redirects to an earlier result or a member.

    Spelled `target` and not `on`: YAML 1.1 reads a bare `on` as the boolean
    true, so the key would arrive as True and never match. The schema suite has
    a test for exactly that, and it caught it.

    Every dispatch path goes through here, which is the point. `target` sits in
    _generic_call's reserved tuple, so a path that hard-coded its target dropped
    the key without a word: `target: "banana"` on a condition generated a clean
    deck and solved. Going through here on all five paths turns that into either
    the redirect the spec asked for or a refusal naming what is bound.

    What it buys beyond the fix: the seven methods an existing load or BC
    exposes -- setValuesInStep, deactivate, suppress, move, reset, resume,
    setValues -- were unreachable from a spec, because they are calls on the
    object rather than on the model. `as:` binds the load, `target: {ref: ...}`
    calls into it.

    `materials` is passed by `_model_setup` and by nothing else, on purpose. A
    constitutive model has to be on the material before a section assignment
    uses it, and `model_setup` is the block that runs before the parts do.
    Whether adding one from `interactions`, `steps` or `conditions` -- all
    after the section is assigned -- takes effect at all is not measured, so
    the form is not offered there rather than offered and hoped for.

    `attr` without `ref` names a member of the DEFAULT object, which is the
    only way to reach the two members that hang off the model and the assembly
    and are not results of anything: `m.keywordBlock`, for a card the dialect
    has no name for, and `a.engineeringFeatures`, which is where cracks, seams
    and pressure penetration live. Neither is returned by a call, so `as:`
    cannot bind them and `{ref:}` cannot name them.
    """
    onto = entry.get("target")
    if onto is None:
        return default
    if not isinstance(onto, dict) or not set(onto) <= {"ref", "attr"} \
            or not ({"ref", "attr"} & set(onto)):
        raise SpecError(
            "%s: `target:` must name a `ref:` (something an earlier call bound "
            "with `as:`), an `attr:` (a member of the default object, which is "
            "how `keywordBlock` and `engineeringFeatures` are reached), or "
            "both. It is what puts NormalBehavior on the contact property that "
            "was just made, instead of on the model." % where)

    attr = onto.get("attr")
    if attr is not None:
        # General contact configures itself through members rather than
        # keywords: contactPropertyAssignments.appendInStep(...),
        # includedPairs.setValuesInStep(...). Without a way to name the member,
        # ContactStd is reachable and unusable.
        attr = str(attr)
        if not _IDENT_RE.match(attr) or attr.startswith("_"):
            raise SpecError("%s: `target.attr: %r` is not a public member name"
                            % (where, attr))

    if "ref" not in onto:
        if attr is None:
            # `target: {attr: }` is a YAML null, and the two branches above
            # both let it through: the key is present so the shape check
            # passes, and the value is None so the name check is skipped. It
            # would emit `_gcall(m.None, ...)`, which is a SyntaxError in a
            # generated script and names neither the spec line nor the key.
            raise SpecError(
                "%s: `target: {attr: }` has no member name. Write the member "
                "of the default object to call into -- `keywordBlock` or "
                "`engineeringFeatures` -- or drop `target:` to call on the "
                "default object itself." % where)
        return "%s.%s" % (default, attr)

    alias = str(onto["ref"])
    if alias not in results:
        # A material this spec declared is reachable by name, without any
        # earlier call having bound it. `material:` and `materials[]` build
        # into m.materials, and nothing gave them an `as:` -- so before this,
        # the ONLY way to add a constitutive model the closed key set cannot
        # express (Hyperelastic, LAMINA, a multi-point hardening curve, a
        # temperature-dependent property) was to re-declare the material in
        # model_setup, which silently wiped everything the spec had said about
        # it. Measured on Abaqus 2021 (artifacts/probe_material): after a
        # second m.Material(name='Steel'), elastic, plastic and density are all
        # gone, and nothing raises. Reaching the existing object instead keeps
        # them -- the same probe put Hyperelastic on a material and found its
        # Elastic still there afterwards.
        #
        # Nothing extra is emitted for this. A declared material compiles
        # straight to m.materials['<name>'], so a spec that does not use the
        # form produces the deck it produced before, byte for byte.
        if alias in materials:
            target = "m.materials[%r]" % alias
            return target if attr is None else "%s.%s" % (target, attr)
        raise SpecError(
            "%s: `target: {ref: %r}` names nothing an earlier call bound. "
            "Bound so far: %s%s"
            % (where, alias, ", ".join(sorted(results)) or "nothing",
               ("; declared materials: %s" % ", ".join(sorted(materials)))
               if materials else ""))
    target = "_RESULTS[%r]" % alias
    if attr is not None:
        target = "%s.%s" % (target, attr)
    return target


def _model_setup(spec: dict, model: str) -> str:
    """Model-level calls that have to happen before anything is built.

    `interactions:` runs after the assembly, because a tie needs instances to
    make surfaces from. A ConnectorSection does not -- and it cannot wait,
    because the SectionAssignment that names it lives in assembly.operations
    and runs first. Measured on Abaqus 2021, assigning a section that does not
    exist yet raises `ValueError: The section "Spring" does not exist in the
    model.`, so a forward reference is not an option and the ordering has to be
    stated. Nothing is built at this point, so a selector here has nothing to
    resolve against and is refused.
    """
    entries = spec.get("model_setup", []) or []
    if not entries:
        return ""
    declared = _declared_materials(spec)
    lines = ["",
             "# --- Model setup -----------------------------------------------------------"]
    results: set = set()
    for i, entry in enumerate(entries):
        where = "model_setup %d" % (i + 1)
        if "call" not in entry:
            raise SpecError("%s has no `call`" % where)
        if entry.get("expect") is not None:
            raise SpecError(
                "%s carries `expect:`. Nothing is built yet, so there is "
                "nothing here to measure." % where)
        alias = entry.get("as")
        if alias is not None and str(alias) in declared:
            raise SpecError(
                "%s: `as: %s` is already the name of a material this spec "
                "declared, and an alias takes precedence over it -- so a later "
                "`target: {ref: %s}` would call into whatever this line built "
                "rather than into the material, without saying so. Give the "
                "alias a name of its own."
                % (where, str(alias), str(alias)))
        _refuse_material_rebuild(where, entry, declared)
        lines.append(_generic_call(
            where, _dispatch_target(where, entry, results, materials=declared),
            entry, {}, results, scope="model_setup"))
    lines.extend(_material_survival_lines(declared, spec))
    return "\n".join(lines)


def _declared_materials(spec: dict) -> tuple:
    """The names `_materials` builds, in the order it builds them.

    Read from the spec rather than parsed back out of the emitted lines: the
    two would drift, and this is the list a refusal quotes.
    """
    names: list = []
    for mat in [spec["material"]] + list(spec.get("materials", []) or []):
        name = str(mat["name"])
        if name not in names:
            names.append(name)
    return tuple(names)


def _refuse_material_rebuild(where: str, entry: dict, declared: tuple,
                             in_model_setup: bool = True) -> None:
    """`call: Material` on a name the spec already declared, refused here.

    Measured on Abaqus 2021 (artifacts/probe_material). A material carrying
    Elastic, Plastic and Density, then handed a second `m.Material(name=...)`
    under the same name:

        before  elastic True  plastic True  density True
        after   elastic False plastic False density False

    and nothing raised. Not just the Elastic: the yield and the density the
    spec declared are gone too, which is the 917 MPa failure `_materials`
    exists to prevent, arriving by a different door. The blocks run in order --
    `_materials` then `_model_setup` -- so the rebuild always wins.

    Refused rather than reordered, because the spec means two contradictory
    things and picking one silently is the thing this dialect does not do.
    The message names the route that works, and that route was measured too:
    `m.materials['Rubber'].Hyperelastic(...)` succeeded and left the existing
    Elastic in place.

    Scope, stated twice because both halves matter.

    WHICH CALL: the one measured to do it. A different call that clobbers a
    material is caught after the fact by the survival check below, which needs
    no list of method names.

    WHICH BLOCK: all four that dispatch onto the model, not just model_setup.
    `interactions`, `steps` and `conditions` reach `m` exactly the same way, so
    the same line erases a material from any of them; guarding one block would
    have left three doors open on a failure whose whole character is that it is
    silent. What differs is the way out. `target: {ref: <material>}` is offered
    in model_setup only -- a constitutive model has to be on the material
    before a section assignment uses it -- so from the other three the honest
    instruction is to move the line, not to rewrite it in place.
    """
    if str(entry.get("call")) != "Material":
        return
    name = entry.get("name")
    if name is None or str(name) not in declared:
        return
    route = (
        "call INTO the existing material instead: `target: {ref: %s}`. That "
        "was measured to keep what was already there." % str(name)
        if in_model_setup else
        "put it in `model_setup:` and call into the existing material there, "
        "`target: {ref: %s}` -- which is also the only place early enough for "
        "a section assignment to see the result." % str(name))
    raise SpecError(
        "%s: `call: Material` with name %r rebuilds a material this spec "
        "already declared, which ERASES it. Measured on Abaqus 2021: a second "
        "Material() under the same name leaves elastic, plastic and density "
        "all absent, and raises nothing -- so the E, the yield and the density "
        "in this spec would be silently gone from the model it builds. "
        "To add a constitutive model the material keys cannot express "
        "(Hyperelastic, an anisotropic LAMINA elastic, a multi-point hardening "
        "curve, a temperature-dependent property), %s "
        "If a genuinely separate material is meant, give it a name of its own."
        % (where, str(name), route))


def _material_survival_lines(declared: tuple, spec: dict) -> list:
    """Did every declared material still have its properties when setup ended.

    The refusal above knows one method name. This knows none, and that is the
    point: any call in model_setup that clears a material -- by a route nobody
    has measured yet -- is caught here, because what is checked is the model,
    not the spec. It runs once, after the whole block, so the cost is one pass
    over the declared names.

    Emitted only when `model_setup` is present, and emitted INLINE rather than
    as a helper in the preamble. That is deliberate: `build_model.py`
    fingerprints the whole script for its run cache, so adding a preamble
    helper would invalidate every shipped case's cached run and rebuild frozen
    baselines in place. No shipped case has a `model_setup`, so written here it
    costs nothing anywhere else -- and a spec without one produces the deck it
    produced before, byte for byte (tests/test_frozen_model_sections compares
    from `# --- Materials` on).

    Python 2.7 in the kernel: no f-strings, no comprehension scoping games.
    """
    if not declared:
        return []
    wanted = []
    for mat in [spec["material"]] + list(spec.get("materials", []) or []):
        name = str(mat["name"])
        if any(name == n for n, _ in wanted):
            continue
        attrs = ["elastic"]
        for key, method in _MATERIAL_SCALARS:
            if mat.get(key) is not None:
                attrs.append(method[0].lower() + method[1:])
        if mat.get("yield") is not None:
            attrs.append("plastic")
        wanted.append((name, attrs))
    return [
        "",
        "# Every declared material, still carrying what it was given, after",
        "# model_setup ran. Measured on Abaqus 2021: a second Material() under",
        "# an existing name leaves elastic, plastic and density all absent and",
        "# raises nothing. The generation-time refusal knows one method name;",
        "# this knows none, so a call nobody has measured yet is caught too.",
        "for _mat_name, _mat_attrs in %r:" % (wanted,),
        "    if _mat_name not in m.materials.keys():",
        "        _expect_fail('MATERIAL_ERASED: %s was declared by this spec "
        "and is not in the model after model_setup ran. Something in that "
        "block removed it.' % _mat_name)",
        "    _mat_obj = m.materials[_mat_name]",
        "    _mat_gone = [_a for _a in _mat_attrs "
        "if getattr(_mat_obj, _a, None) is None]",
        "    if _mat_gone:",
        "        _expect_fail('MATERIAL_ERASED: %s lost %s after model_setup "
        "ran, so the spec declares properties the model does not have. "
        "Measured on Abaqus 2021, a second Material() under an existing name "
        "does exactly this and raises nothing -- call into the material with "
        "target: {ref: %s} instead of rebuilding it.' "
        "% (_mat_name, ', '.join(_mat_gone), _mat_name))",
        "_sel_log('MATERIAL_SURVIVED: ' + ', '.join([_n for _n, _ in %r]))"
        % (wanted,),
    ]


def _generic_interaction(index: int, inter: dict, results: set,
                         declared: tuple = ()) -> list[str]:
    """One interaction written as the Abaqus call it is.

    Everything that joins instances hangs off the MODEL -- Tie, Coupling,
    RigidBody, ShellSolidCoupling, MultipointConstraint, the contact family,
    ConnectorSection -- while the regions they join belong to the ASSEMBLY. So
    the target is `m` and the selector scope is the assembly: a phrase here has
    to name its instance, for the same reason it does in an assembly operation.

    Measured on Abaqus 2021, the model object answers a mistake exactly the way
    Part does -- AttributeError for a method it has not got, "keyword error on
    <name>" for a keyword, "master; found string, expecting Region" for a type.
    That is what makes dispatching to all 299 of its callables safe.
    """
    where = "interaction %d" % (index + 1)
    if "type" in inter:
        raise SpecError(
            "%s: names both `call: %s` and `type: %s`. `type` is the two-name "
            "shorthand and `call` is the Abaqus method — pick one."
            % (where, inter["call"], inter["type"]))

    _refuse_material_rebuild(where, inter, declared, in_model_setup=False)
    target = _dispatch_target(where, inter, results)
    surfaces: list = []
    lines = [_generic_call(where, target, inter, {}, results,
                           scope="assembly", surfaces=surfaces)]
    lines.extend(_interaction_expect(where, inter, surfaces))
    return lines


def _interaction_expect(where: str, inter: dict, surfaces: list) -> list[str]:
    """The gap check, and why a two-surface call may not go without one.

    A pair whose surfaces are farther apart than its position tolerance is
    created silently, writes a normal *Tie card, and solves to completion with
    the two bodies unbonded. Measured: 7.95x the correct tip deflection on a
    two-layer cantilever, job status SUCCESS. Nothing else in the pipeline can
    see that, so a call that builds exactly two surfaces has to say how far
    apart it expects them to be. Stating a deliberate clearance is a fine
    answer -- `{min: 0.4, max: 0.6}` for a pair meant to close under load -- the
    point is that the number is stated and checked, not that it is zero.
    """
    expect = inter.get("expect") or {}
    if not isinstance(expect, dict):
        raise SpecError("%s: `expect:` must be a mapping" % where)
    unknown = set(expect) - {"gap"}
    if unknown:
        raise SpecError(
            "%s: expect knows `gap` and nothing else here; got %s. A measure "
            "that is not taken is worse than none, because it reads as checked."
            % (where, ", ".join(sorted(unknown))))

    gap = expect.get("gap")
    if gap is None:
        if len(surfaces) == 2:
            raise SpecError(
                "%s: builds two surfaces, so it needs `expect: {gap: {max: "
                "...}}`. Measured on Abaqus 2021: a pair 0.05 apart with a 0.01 "
                "position tolerance is accepted, writes a real *Tie card and "
                "COMPLETES SUCCESSFULLY with the bodies unbonded — 7.95x the "
                "right deflection. Say how far apart these two should be."
                % where)
        return []

    if not isinstance(gap, dict):
        raise SpecError("%s: expect.gap must be a mapping with `max`, `min` or "
                        "both" % where)
    unknown = set(gap) - {"max", "min", "between"}
    if unknown:
        raise SpecError("%s: expect.gap knows max, min and between; got %s"
                        % (where, ", ".join(sorted(unknown))))

    pair = gap.get("between")
    if pair is None:
        if len(surfaces) != 2:
            raise SpecError(
                "%s: expect.gap needs two surfaces to measure between, and this "
                "call builds %d. Name them with `between: [<surface>, "
                "<surface>]`." % (where, len(surfaces)))
        pair = list(surfaces)
    else:
        if not isinstance(pair, list) or len(pair) != 2:
            raise SpecError("%s: expect.gap.between must name exactly two "
                            "surfaces" % where)
        pair = [str(entry).upper() for entry in pair]

    low, high = gap.get("min"), gap.get("max")
    if low is None and high is None:
        raise SpecError(
            "%s: expect.gap states neither max nor min, so it checks nothing."
            % where)
    for label, bound in (("max", high), ("min", low)):
        if bound is not None and (isinstance(bound, bool)
                                  or not isinstance(bound, (int, float))):
            raise SpecError("%s: expect.gap.%s must be a number" % (where, label))
    if low is not None and high is not None and float(low) > float(high):
        raise SpecError("%s: expect.gap has min %r above max %r"
                        % (where, low, high))

    return ["_expect_gap(a, %r, %r, %r, %s, %s)"
            % (where, pair[0], pair[1],
               "None" if low is None else repr(float(low)),
               "None" if high is None else repr(float(high)))]


def _tie_call(name: str, inter: dict, main_set: str, sec_set: str) -> str:
    if inter.get("property"):
        raise SpecError(
            "interaction %r is a tie but carries a `property` block. A tie is a "
            "constraint, not a contact interaction — it has no friction and no "
            "normal behaviour, so those settings would be silently discarded."
            % name)

    tolerance = inter.get("position_tolerance")
    # positionToleranceMethod=COMPUTED lets Abaqus pick, and anything outside
    # the tolerance is left untied with only a warning in the .dat. Stating a
    # tolerance is therefore the only way to know the pair bound.
    if tolerance is None:
        tol_args = "positionToleranceMethod=COMPUTED,"
    else:
        tol_args = ("positionToleranceMethod=SPECIFIED, positionTolerance=%r,"
                    % float(tolerance))
    return ("_tie(m, %r, a.surfaces[%r], a.surfaces[%r],\n"
            "     %s adjust=%s, tieRotations=ON, thickness=ON)"
            % (name, main_set, sec_set, tol_args,
               "ON" if inter.get("adjust") else "OFF"))


def _contact_calls(name: str, inter: dict, main_set: str, sec_set: str) -> list[str]:
    prop = inter.get("property") or {}
    friction = float(prop.get("friction", 0.0) or 0.0)
    separation = prop.get("allow_separation", True)
    prop_name = name.upper() + "_PROP"

    lines = [
        "m.ContactProperty(%r)" % prop_name,
        "m.interactionProperties[%r].NormalBehavior(" % prop_name,
        "    pressureOverclosure=HARD, allowSeparation=%s,"
        % ("ON" if separation else "OFF"),
        "    constraintEnforcementMethod=DEFAULT)",
    ]
    if friction > 0.0:
        lines += [
            "m.interactionProperties[%r].TangentialBehavior(" % prop_name,
            "    formulation=PENALTY, directionality=ISOTROPIC,",
            "    slipRateDependency=OFF, pressureDependency=OFF,",
            "    temperatureDependency=OFF, dependencies=0,",
            "    table=((%r, ),), shearStressLimit=None," % friction,
            "    maximumElasticSlip=FRACTION, fraction=0.005,",
            "    elasticSlipStiffness=None)",
        ]
    else:
        # Spelled out rather than left to the default. FRICTIONLESS is what
        # Abaqus assumes when no tangential behaviour is defined, but a reader
        # of the deck cannot tell "frictionless on purpose" from "nobody
        # thought about friction", and those are different models.
        lines += [
            "m.interactionProperties[%r].TangentialBehavior(formulation=FRICTIONLESS)"
            % prop_name,
        ]
    lines.append(
        "_contact(m, %r, a.surfaces[%r], a.surfaces[%r],\n"
        "         createStepName='Initial', sliding=%s, thickness=ON,\n"
        "         interactionProperty=%r, adjustMethod=NONE,\n"
        "         initialClearance=OMIT, datumAxis=None, clearanceRegion=None)"
        % (name, main_set, sec_set,
           "SMALL" if str(inter.get("sliding", "small")) == "small" else "FINITE",
           prop_name))
    return lines




def _generic_step(index: int, entry: dict, results: set,
                  declared: tuple = ()) -> list[str]:
    """One step written as the Abaqus call it is.

    `StaticStep` was the only thing the enumerated block could say. Everything
    else the release offers -- FrequencyStep, ImplicitDynamicsStep,
    ExplicitDynamicsStep, BuckleStep, HeatTransferStep, Visco, Riks -- is a
    method on the model with the same shape, and none of them needed a new
    case here.

    Guarded, because the two ways this goes wrong were measured. A `previous:`
    that names nothing raises "There is no step by that name", which is loud
    enough. Two steps that both name `Initial` are BOTH accepted and come out
    in the reverse order, which is not -- see _expect_steps.
    """
    where = "step %d" % (index + 1)
    if "type" in entry:
        raise SpecError(
            "%s: has both `call: %s` and `type: %s`. `type` is the named "
            "shorthand and `call` is the Abaqus method — pick one."
            % (where, entry["call"], entry["type"]))
    for key in ("bcs", "loads"):
        if key in entry:
            raise SpecError(
                "%s: a generic step cannot carry `%s:`. Conditions are Abaqus "
                "calls too and they go in the top-level `conditions:` block, "
                "each naming its own `createStepName:` — which Abaqus refuses "
                "outright if the step is not there." % (where, key))
    if entry.get("expect") is not None:
        raise SpecError(
            "%s: `expect:` on a step has nothing to measure. The order the "
            "steps end up in is checked for every spec, without being asked."
            % where)
    _refuse_material_rebuild(where, entry, declared, in_model_setup=False)
    return [_generic_call(where, _dispatch_target(where, entry, results),
                          entry, {}, results, scope="assembly")]


def _generic_step_name(index: int, entry: dict) -> str:
    """The name a dispatched step declares, read on this side.

    Wanted twice. Once to check the order the steps come out in. Once because a
    NAMED step written after a dispatched one has to chain onto it: the named
    form takes its `previous` from the step before it, and while that variable
    only advanced in the named branch, a mixed spec emitted the second step with
    `previous='Initial'` -- which inserts it BEFORE the dispatched one. Caught by
    _expect_steps at run time rather than solved wrong, but a legitimate spec
    that fails at the solver is still a defect.
    """
    name = entry.get("name")
    if isinstance(name, dict) and "literal" in name:
        name = name["literal"]
    if not isinstance(name, str) or not name:
        raise SpecError(
            "step %d: a step needs a `name:` this side can read, so "
            "the order it runs in can be checked. Write "
            '`name: {literal: "Press"}`.' % (index + 1))
    return str(name)


def _step_names(spec: dict) -> list[str]:
    """The order the spec wrote, which is not necessarily the order that runs."""
    names = []
    for i, entry in enumerate(spec.get("steps", []) or []):
        if _is_generic(entry):
            names.append(_generic_step_name(i, entry))
        else:
            names.append(str(entry["name"]))
    return names


def _conditions(spec: dict, model: str, points_by_set: dict) -> str:
    """Boundary conditions, loads and predefined fields, dispatched.

    One block for all three because Abaqus makes no distinction: EncastreBC,
    Pressure and Temperature are all methods on the model taking a region and a
    createStepName. CAE groups them the same way, in the Load module.

    Emitted after every step, so `createStepName:` can name any of them. A name
    that is not a step is refused by Abaqus itself -- measured: "The specified
    step either does not exist or is the Initial step."
    """
    entries = spec.get("conditions", []) or []
    if not entries:
        return ""
    lines = ["",
             "# --- Conditions ------------------------------------------------------------"]
    results: set = set()
    declared = _declared_materials(spec)
    named: dict[str, str] = {}
    for i, entry in enumerate(entries):
        where = "condition %d" % (i + 1)
        if not _is_generic(entry):
            raise SpecError(
                "%s has no `call`. Every condition here is the Abaqus method "
                "that makes it: EncastreBC, DisplacementBC, Pressure, "
                "ConcentratedForce, Temperature, Gravity ..." % where)
        _reuse_refuse(where, entry, named)
        _refuse_material_rebuild(where, entry, declared, in_model_setup=False)
        sets: list = []
        surfaces: list = []
        lines.append(_generic_call(where,
                                   _dispatch_target(where, entry, results),
                                   entry, {}, results,
                                   scope="assembly", surfaces=surfaces,
                                   sets=sets))
        lines.extend(_condition_expect(where, entry, sets))
        stated = (entry.get("expect") or {}).get("points")
        if stated is not None and sets:
            points_by_set[sets[0]["name"]] = int(stated)
    return "\n".join(lines)


def _reuse_refuse(where: str, entry: dict, named: dict) -> None:
    """Two conditions may not carry the same Abaqus name.

    Measured on Abaqus 2021, and it is not a duplicate-key error -- it is worse.
    A second `DisplacementBC(name='Push', ...)` REPLACES the first outright, and
    the model keeps only the later region and the later step. A spec that says
    "hold at 0 in step One, move to -5 in step Two" as two conditions produces
    an input file whose step One carries no boundary card at all:

        === *Step One ===        (nothing)
        === *Step Two ===
        *Boundary
        TIP2, 2, 2, -5.

    Abaqus does not complain, the input file is written, and the log line for
    the second condition reads GENERIC_OK. The named shorthand has guarded this
    since it was written (_reuse_check); the dispatched form has to as well.

    A name this side cannot read is not refused here -- it is caught at run time
    instead, against the registries, by _gcall.
    """
    name = entry.get("name")
    if isinstance(name, dict) and "literal" in name:
        name = name["literal"]
    if not isinstance(name, str) or not name:
        return
    if name in named:
        raise SpecError(
            "%s: %s already carries the name %r. Abaqus does not add a second "
            "condition of that name — it REPLACES the first, keeping only the "
            "later region and the later step, and says nothing. If this is one "
            "condition whose value changes between steps, that is "
            "`setValuesInStep` on the condition itself: bind the first with "
            "`as: <alias>` and write the change as "
            "`{call: setValuesInStep, target: {ref: <alias>}, stepName: ...}`. "
            "The named `steps[].bcs` / `steps[].loads` shorthand does the same "
            "thing on its own. If they are two different conditions, give them "
            "different names."
            % (where, named[name], name))
    named[name] = where


def _condition_expect(where: str, entry: dict, sets: list) -> list[str]:
    """`expect.points` -- how many nodes the condition actually lands on.

    Measured on Abaqus 2021: `cf2=-100` on a set of the four tip corners of a
    cantilever gives a total reaction of 400 N and a tip deflection of
    -0.7584553 mm, against 100 N and -0.1896138 for the same call at cf2=-25
    on those same four nodes. Both jobs COMPLETE with no warning. A
    concentrated load is written per node, so the magnitude in the spec is not
    the load.

    Optional here on purpose. Which conditions write a per-node card is
    Abaqus's business, not something to be inferred from whether the selector
    picked vertices or faces -- and the face case is the worse one, because
    there the node count moves with the mesh seed. The requirement is enforced
    after the input file is written, against the *Cload cards actually in it.
    """
    expect = entry.get("expect")
    if expect is None:
        # Not required here, and deliberately not guessed at either. Whether
        # this condition writes a per-node card is decided by Abaqus, not by
        # the shape of the selector, so the requirement is enforced against the
        # input file Abaqus actually wrote -- see _expect_cload.
        return []

    if not isinstance(expect, dict) or set(expect) - {"points"}:
        raise SpecError(
            "%s: expect: takes `points` and nothing else — the number of nodes "
            "the condition applies to." % where)
    if "points" not in expect:
        raise SpecError("%s: expect: is empty" % where)
    points = expect["points"]
    if isinstance(points, bool) or not isinstance(points, int) or points < 1:
        raise SpecError("%s: expect.points must be a whole number of nodes, "
                        "at least 1" % where)
    if not sets:
        raise SpecError(
            "%s: expect.points counts the nodes of the set this call builds, "
            "and it builds none. Give the region as "
            '`{set: "<instance>:<kind>@<where>"}`.' % where)
    if len(sets) > 1:
        raise SpecError(
            "%s: builds %d sets, so `expect.points` does not say which one. "
            "Split the call." % (where, len(sets)))
    return ["_expect_points(a, %r, %d, %r)"
            % (sets[0]["name"], int(points), where)]


def _steps(spec: dict, model: str, points_by_set: dict) -> str:
    lines = ["",
             "# --- Steps, BCs, loads -----------------------------------------------------"]
    previous = "Initial"
    # A boundary condition that appears in more than one step is ONE condition
    # whose value changes, not two conditions. Abaqus enforces that: names are
    # unique model-wide, and the second DisplacementBC of the same name
    # replaces the first. "Hold it, then move it" is the shape of every
    # preload-then-load analysis, so it has to be expressible.
    seen_bcs: dict[str, str] = {}
    seen_loads: dict[str, str] = {}
    results: set = set()
    generic = False
    for index, step_spec in enumerate(spec["steps"]):
        if _is_generic(step_spec):
            generic = True
            lines += _generic_step(index, step_spec, results,
                                   _declared_materials(spec))
            # A named step written after this one chains onto it.
            previous = _generic_step_name(index, step_spec)
            continue
        name = str(step_spec["name"])
        lines.append(
            "m.StaticStep(name=%r, previous=%r, timePeriod=%r,\n"
            "    initialInc=%r, minInc=%r, maxInc=%r, maxNumInc=%r, nlgeom=%s)"
            % (name, previous,
               float(step_spec.get("time_period", 1.0)),
               float(step_spec.get("initial_inc", 0.1)),
               float(step_spec.get("min_inc", 1e-5)),
               float(step_spec.get("max_inc", 1.0)),
               int(step_spec.get("max_num_inc", 100)),
               "ON" if step_spec.get("nlgeom") else "OFF"))
        for i, bc in enumerate(step_spec.get("bcs", []) or []):
            lines.append(_bc(name, i, bc, seen_bcs))
        for i, load in enumerate(step_spec.get("loads", []) or []):
            lines.append(_load(name, i, load, seen_loads, points_by_set))
        previous = name
    if generic:
        # Only for the dispatched form. The named shorthand chains `previous`
        # itself, one step to the next, so its order cannot come out wrong and
        # the line would be noise in every deck that already ships.
        lines.append("_expect_steps(m, %r)" % (tuple(_step_names(spec)),))
    return "\n".join(lines)


def _reuse_check(kind: str, name: str, region: str, seen: dict, where: str) -> bool:
    """Return True when this name was already created, and guard the region.

    An Abaqus BC or load keeps the region it was created with; a later step can
    only change its VALUES. Letting the spec name the same condition on a
    different region would silently apply the change to the original region,
    which is a model nobody wrote.
    """
    if name not in seen:
        seen[name] = region
        return False
    if seen[name] != region:
        raise SpecError(
            "%s: %s %r first appears on %r and reappears on %r. A %s that "
            "spans steps keeps the region it was created with — only its "
            "values may change. Use a different name for a different region."
            % (where, kind, name, seen[name], region, kind))
    return True


def _bc(step_name: str, index: int, bc: dict, seen: dict) -> str:
    name = str(bc.get("name") or "BC-%d" % (index + 1))
    set_name = "BC_%s" % name.upper()
    where = "step %r %s" % (step_name, name)
    kind = bc["type"]

    if _reuse_check("boundary condition", name, str(bc["region"]), seen, where):
        if kind != "displacement":
            raise SpecError(
                "%s: %r is a %r boundary condition repeated in a later step. "
                "Only 'displacement' carries values that can change; a fixed "
                "restraint is either on or off." % (where, name, kind))
        # Only the components actually named. setValuesInStep rejects UNSET
        # outright ("Invalid propagation status for 'u1' attribute") because
        # there the omission IS the instruction: a component left out keeps
        # whatever the previous step gave it.
        args = ["%s=%r" % (dof, float(bc[dof]))
                for dof in ("u1", "u2", "u3") if dof in bc]
        if not args:
            raise SpecError(
                "%s: %r reappears in a later step without prescribing anything. "
                "Give the component that changes." % (where, name))
        return ("m.boundaryConditions[%r].setValuesInStep(stepName=%r, %s)"
                % (name, step_name, ", ".join(args)))

    lines = [_region(where, bc["region"], bc.get("expect"), set_name, as_surface=False)]
    region = "a.sets[%r]" % set_name
    # Every BC is created in the Initial step: a boundary condition that only
    # exists from Step-1 onwards leaves the model unrestrained in Initial, and
    # Abaqus reports that as a numerical singularity rather than as the missing
    # BC it is.
    if kind == "encastre":
        lines.append("m.EncastreBC(name=%r, createStepName='Initial', region=%s)"
                     % (name, region))
    elif kind == "pinned":
        lines.append("m.PinnedBC(name=%r, createStepName='Initial', region=%s)"
                     % (name, region))
    elif kind in ("symmetry_x", "symmetry_y", "symmetry_z"):
        fn = {"symmetry_x": "XsymmBC", "symmetry_y": "YsymmBC",
              "symmetry_z": "ZsymmBC"}[kind]
        lines.append("m.%s(name=%r, createStepName='Initial', region=%s)"
                     % (fn, name, region))
    else:  # displacement
        args = _displacement_args(bc, where)
        lines.append("m.DisplacementBC(name=%r, createStepName=%r, region=%s,\n"
                     "    %s, amplitude=UNSET, distributionType=UNIFORM)"
                     % (name, step_name, region, ", ".join(args)))
    return "\n".join(lines)


def _displacement_args(bc: dict, where: str) -> list[str]:
    args = []
    for dof in ("u1", "u2", "u3"):
        args.append("%s=%s" % (dof, repr(float(bc[dof])) if dof in bc else "UNSET"))
    if all(a.endswith("UNSET") for a in args):
        raise SpecError(
            "%s: a 'displacement' BC that prescribes no component is a no-op. "
            "Give at least one of u1 / u2 / u3." % where)
    return args


def _load(step_name: str, index: int, load: dict, seen: dict,
          points_by_set: dict) -> str:
    name = str(load.get("name") or "Load-%d" % (index + 1))
    set_name = "LOAD_%s" % name.upper()
    where = "step %r %s" % (step_name, name)
    kind = load["type"]
    value = float(load["value"])

    if _reuse_check("load", name, str(load["region"]), seen, where):
        # Abaqus propagates a load into every following step by default, so a
        # repeat means "change the magnitude from here on".
        if kind == "pressure":
            return ("m.loads[%r].setValuesInStep(stepName=%r, magnitude=%r)"
                    % (name, step_name, value))
        direction = int(load.get("direction") or 0)
        if not direction:
            raise SpecError(
                "%s: a concentrated_force needs a direction (1, 2 or 3)." % where)
        components = ", ".join(
            "cf%d=%r" % (d, value if d == direction else 0.0) for d in (1, 2, 3))
        return ("m.loads[%r].setValuesInStep(stepName=%r, %s)"
                % (name, step_name, components))

    if kind == "pressure":
        lines = [_region(where, load["region"], load.get("expect"), set_name,
                         as_surface=True)]
        # The sign is the direction and is carried through untouched: Abaqus
        # pressure is positive INTO the surface. An abs() here once turned
        # plate_with_hole's tension into compression, and Mises being
        # magnitude-only meant the contour still looked right.
        lines.append(
            "m.Pressure(name=%r, createStepName=%r, region=a.surfaces[%r],\n"
            "    magnitude=%r, amplitude=UNSET, distributionType=UNIFORM)"
            % (name, step_name, set_name, value))
        return "\n".join(lines)

    if load.get("direction") is None:
        raise SpecError(
            "%s: a concentrated_force needs a direction (1, 2 or 3)." % where)
    direction = int(load["direction"])
    # The named form has exactly the same hazard as the dispatched one: the
    # magnitude is written per node. Measured on Abaqus 2021, the same cf2 on
    # four tip corners instead of one totals 400 N and the job completes.
    points = load.get("points")
    if points is not None:
        if isinstance(points, bool) or not isinstance(points, int) or points < 1:
            raise SpecError("%s: `points` must be a whole number of nodes, at "
                            "least 1" % where)
        points_by_set[set_name] = int(points)
    lines = [_region(where, load["region"], load.get("expect"), set_name,
                     as_surface=False)]
    components = ", ".join(
        "cf%d=%r" % (d, value if d == direction else 0.0) for d in (1, 2, 3))
    lines.append(
        "m.ConcentratedForce(name=%r, createStepName=%r, region=a.sets[%r],\n"
        "    %s, distributionType=UNIFORM)"
        % (name, step_name, set_name, components))
    return "\n".join(lines)


# What a stress analysis wants, and what every spec got whether it was a stress
# analysis or not.
_DEFAULT_FIELD_VARIABLES = ("S", "E", "U", "RF")


def _outputs(spec: dict, model: str) -> str:
    """The field output request, which the spec may now name.

    This line was a literal. S, E and RF do not exist in a heat transfer step,
    so Abaqus refuses the whole request -- "Invalid variables are specified in
    an output request" -- and no input file is written at all. Measured: a
    dispatched HeatTransferStep with two TemperatureBCs builds both conditions
    successfully (GENERIC_OK twice) and then dies here; delete this one line
    from the generated deck and the same spec produces its .inp. So the step
    layer had opened up a physics the output block still could not express.

    No gate on the names: a variable this release does not have is refused by
    Abaqus itself, loudly, by name. A check here would only be a second list to
    keep in step with the release.
    """
    variables = spec.get("outputs", {}).get("field_variables")
    if variables is None:
        variables = _DEFAULT_FIELD_VARIABLES
    else:
        if not isinstance(variables, (list, tuple)) or not variables:
            raise SpecError(
                "outputs.field_variables: needs at least one variable name, "
                "e.g. ['NT', 'HFL'] for a heat transfer analysis")
        bad = [v for v in variables if not isinstance(v, str) or not v.strip()]
        if bad:
            raise SpecError(
                "outputs.field_variables: %r is not a variable name" % (bad[0],))
        variables = tuple(str(v) for v in variables)
    lines = [
        "",
        "# --- Output requests -------------------------------------------------------",
        "m.fieldOutputRequests['F-Output-1'].setValues(variables=%r)" % (variables,),
    ]
    lines += _measurement_regions(spec)
    return "\n".join(lines)


def _measurement_regions(spec: dict) -> list[str]:
    """Sets that exist only to be read from, not to carry a condition.

    Without these, every KPI location has to be a BC or a load set, or
    `whole_model`. `whole_model` is the trap: on a plate with a hole clamped at
    one end, the largest Mises in the model is at the clamp, not at the hole,
    and a KPI called HOOP_MAX would quietly report the clamp.
    """
    lines: list[str] = []
    seen = set()
    for i, entry in enumerate(spec.get("outputs", {}).get("regions", []) or []):
        name = str(entry["name"])
        where = "outputs.regions[%d] %s" % (i, name)
        if name in seen:
            raise SpecError("%s: two measurement regions share the name %r"
                            % (where, name))
        seen.add(name)
        set_name = "REGION_%s" % name.upper()
        lines.append(_region(where, entry["region"], entry.get("expect"),
                             set_name, as_surface=False))
    return lines






















_KEYWORD_BLOCK = "keywordBlock"


def _keyword_inserts(spec: dict) -> list[tuple[str, str]]:
    """Every line a `keywordBlock` insert asks for, and where it was asked.

    Collected from the spec rather than from the block that emits the call,
    because a keywordBlock insert is legal in any block whose default object is
    the model, and WHERE it goes is the user's problem to get right. The block
    is not populated until the model is complete enough to write, so an insert
    put too early has nothing to land in -- measured on Abaqus 2021 that is an
    IndexError and the build stops, which is a good outcome and not one this
    collector has to catch. See `_expect_keywords` for every case measured
    and for the one that is genuinely quiet.

    `insert` takes text as a string or as a sequence of lines; both are read
    here, and each line is checked on its own so a failure names the line.
    """
    found: list[tuple[str, str]] = []
    blocks = (("model_setup", spec.get("model_setup")),
              ("interaction", spec.get("interactions")),
              ("condition", spec.get("conditions")),
              ("step", spec.get("steps")))
    for label, entries in blocks:
        for i, entry in enumerate(entries or []):
            if not isinstance(entry, dict):
                continue
            onto = entry.get("target")
            if not isinstance(onto, dict) or "ref" in onto:
                continue
            if str(onto.get("attr")) != _KEYWORD_BLOCK:
                continue
            if str(entry.get("call")) != "insert":
                continue
            text = entry.get("text")
            lines = text if isinstance(text, (list, tuple)) else [text]
            for j, line in enumerate(lines):
                if line is None or not str(line).strip():
                    continue
                found.append(("%s %d keywordBlock line %d"
                              % (label, i + 1, j + 1), str(line)))
    return found


def _job(model: str, points_by_set: dict | None = None,
         keywords: list[tuple[str, str]] | None = None) -> str:
    # Emitted even when the spec stated nothing: an empty mapping is the case
    # that catches an unstated multi-node *Cload, which is the whole point.
    checks = ["_expect_cload(a, workdir + '/' + MODEL + '.inp', %r)"
              % (dict(sorted((points_by_set or {}).items())),)]
    if keywords:
        checks.append("_expect_keywords(workdir + '/' + MODEL + '.inp', %r)"
                      % (tuple(keywords),))
    return _JOB % ("\n".join(checks) + "\n")


_JOB = """
# --- Write the job ---------------------------------------------------------
mdb.Job(name=MODEL, model=MODEL, description='', type=ANALYSIS,
        atTime=None, waitMinutes=0, waitHours=0,
        queue=None, memory=90, memoryUnits=PERCENTAGE,
        getMemoryFromAnalysis=True,
        explicitPrecision=SINGLE, nodalOutputPrecision=SINGLE,
        echoPrint=OFF, modelPrint=OFF, contactPrint=OFF, historyPrint=OFF,
        userSubroutine='', scratch='', resultsFormat=ODB,
        multiprocessingMode=DEFAULT, numCpus=1, numGPUs=0)

mdb.jobs[MODEL].writeInput(consistencyChecking=OFF)
%s
print('INP_WRITTEN: ' + workdir + '/' + MODEL + '.inp')
mdb.saveAs(MODEL)
print('CAE_WRITTEN: ' + workdir + '/' + MODEL + '.cae')
"""
