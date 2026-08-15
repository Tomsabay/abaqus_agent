"""The value forms a spec may write where an Abaqus API argument is expected.

`generic_call` lets a spec name any Abaqus method. Its arguments are where the
spec stops being data and starts being geometry: `face@z=max` has to become a
resolved face at kernel time, `{new: ...}` has to construct an object, `{rp:
...}` has to place a reference point. This module is that translation and
nothing else -- one entry in _ARG_FORMS per form, one _arg_* leaf per entry.

It was 638 lines in the middle of build_v2.py, between the deck emitters and
the preview dumper, and it is the part a reader most often needs alone: the
question "what may I write here?" is answered entirely by _ARG_FORMS.
"""

from __future__ import annotations

import re

from core import selectors
from runner.spec_base import SpecError, _parse


# Mapping values that are not literals. Exactly one may appear in a mapping.
_ARG_FORMS = ("select", "one", "sketch", "datum", "ref", "literal", "bool",
              "new", "instance", "surface", "set", "vertex", "wire_at",
              "reference_point", "named_set")

# The modules the generated script imports. `{new: "mesh.ElemType"}` may reach
# any of them and nothing else -- not as a curated list of what is useful, but
# because a module the script never imported is a NameError either way. Derived
# from the import line rather than retyped, so the two cannot drift apart.
_IMPORT_LINE = ("import part, material, section, assembly, step, load, mesh, "
                "interaction, job, connectorBehavior")

_MODULES = tuple(name.strip()
                 for name in _IMPORT_LINE[len("import "):].split(","))

_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# An all-caps string is read as an abaqusConstants symbol: the generated script
# does `from abaqusConstants import *`, so emitting the bare word is enough, and
# a name that is not a symbol is a NameError that says so. `{literal: "RIM"}`
# forces a genuine all-caps string through.
_SYMBOL_RE = re.compile(r"^[A-Z][A-Z0-9_]+$")

def _generic_call(where: str, target: str, feat: dict, sketches: dict,
                  results: set, scope: str = "part",
                  surfaces: list | None = None,
                  sets: list | None = None) -> str:
    """Emit ``_gcall(<target>, '<Method>', {...})`` for one generic feature.

    ``surfaces``, when a list, both permits ``{surface: ...}`` arguments and
    collects the names they create, in the order the keywords are compiled. The
    interaction layer needs that order: a pair whose two surfaces are 5 mm apart
    is created without complaint, and knowing which two surfaces the call built
    is what makes the gap checkable. Left as None, the form is refused -- an
    assembly surface cannot exist while a part is still being shaped.
    """
    name = str(feat["call"])
    reserved = ("call", "as", "creates", "target", "expect")
    if not _IDENT_RE.match(name) or name.startswith("_"):
        raise SpecError(
            "%s: %r is not a public Abaqus method name. A leading underscore is "
            "refused outright — dispatch reaches whatever it is given, and "
            "`__class__` is not a modelling operation." % (where, name))

    alias = feat.get("as")
    if alias is not None:
        alias = str(alias)
        if not _IDENT_RE.match(alias):
            raise SpecError("%s: `as: %r` is not a usable name" % (where, alias))
        if alias in results:
            raise SpecError(
                "%s: `as: %r` is already the name of an earlier result"
                % (where, alias))

    pairs = []
    for key in sorted(feat):
        if key in reserved:
            continue
        if not _IDENT_RE.match(str(key)):
            raise SpecError(
                "%s: %r is not a keyword name Abaqus could accept" % (where, key))
        pairs.append("%r: %s" % (str(key),
                                 _arg_expr(where, str(key), feat[key],
                                           sketches, results, scope, surfaces,
                                           sets)))

    call = "_gcall(%s, %r, {%s}, %r)" % (target, name, ", ".join(pairs), where)
    if alias is None:
        return call
    # Bound after the arguments are compiled, so a feature cannot refer to its
    # own result.
    results.add(alias)
    return "_RESULTS[%r] = %s" % (alias, call)

def _arg_expr(where: str, key: str, value, sketches: dict, results: set,
              scope: str = "part", surfaces: list | None = None,
              sets: list | None = None) -> str:
    """Compile one keyword value.

    ``scope`` decides what a selector resolves against. On a part feature the
    geometry is the part's own and a selector may not name an instance; in the
    assembly the same phrase must name one, because a part instanced twice has
    one set of faces and ``Lower:face@y=max`` and ``Upper:face@y=max`` are
    different faces only once the instance transform has been applied.
    """
    if isinstance(value, bool):
        # YAML reads bare on/off/yes/no as booleans, and Abaqus wants the
        # SymbolicConstant. Passing True where ON is meant is a TypeError deep
        # inside CAE that names neither the spec line nor the word that caused
        # it, so it is refused here where the fix is obvious.
        #
        # Not every keyword wants the symbol, though, and this used to leave
        # the ones that do not unreachable. Measured on Abaqus 2021:
        # keywordBlock.synchVersions(storeNodesAndElements='OFF') raises
        # "storeNodesAndElements; found string, expecting False, True, 0 or 1",
        # and quoting it was the only thing the message above suggested. So the
        # refusal now names the other way out as well.
        raise SpecError(
            "%s: %s is %r. YAML turns bare on/off/yes/no into booleans, and "
            'most Abaqus keywords want the symbol — quote it as "ON" / "OFF". '
            "For the few that genuinely want a Python boolean (measured: "
            "keywordBlock.synchVersions answers a string with "
            '"expecting False, True, 0 or 1"), write {bool: %s} to say so.'
            % (where, key, value, str(value).lower()))
    if value is None:
        return "None"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, str):
        if _SYMBOL_RE.match(value):
            return value
        return repr(str(value))
    if isinstance(value, (list, tuple)):
        items = [_arg_expr(where, key, item, sketches, results, scope,
                           surfaces, sets)
                 for item in value]
        if len(items) == 1:
            return "(%s,)" % items[0]
        return "(%s)" % ", ".join(items)
    if isinstance(value, dict):
        return _arg_mapping(where, key, value, sketches, results, scope,
                            surfaces, sets)
    raise SpecError("%s: %s is a %s, which cannot be passed to Abaqus"
                    % (where, key, type(value).__name__))

# Which sibling keys each mapping form tolerates beside itself.
#
# `new` is absent on purpose: its siblings ARE the constructor's keyword
# arguments, so it accepts anything. Every other form is listed, and the test
# that compares this table against _ARG_FORMS is what stops a form added later
# from quietly inheriting accept-anything -- which is how eight of the eleven
# came to drop unknown keys in silence.
_ARG_SIBLINGS = {
    "select": ("expect",),
    # Deliberately empty. The whole point of `one` is that the count is
    # exactly one, so an `expect:` beside it either repeats that or
    # contradicts it.
    "one": (),
    "surface": ("expect", "name"),
    "set": ("expect", "name"),
    # `name` because the deck's `ref node=` carries it -- measured, the card
    # reads `*Coupling, constraint name=Cpl, ref node=RP, surface=TIPFACE`.
    # No `expect`: the count is fixed at one by the form itself, because a
    # Coupling, a RigidBody and an MPC each control exactly one point.
    "reference_point": ("name",),
    # Deliberately empty. It names a set that already exists, so there is
    # nothing left to configure: an `expect:` here would be asserting a count
    # on somebody else's call.
    "named_set": (),
    "sketch": (),
    "datum": (),
    "ref": (),
    "literal": (),
    "bool": (),
    "instance": (),
    "vertex": (),
    "wire_at": (),
}

def _check_siblings(where: str, key: str, value: dict, form: str) -> None:
    allowed = _ARG_SIBLINGS.get(form)
    if allowed is None:      # `new`: siblings are constructor keywords
        return
    extra = set(value) - {form} - set(allowed)
    if not extra:
        return
    if not allowed:
        room = "nothing else belongs there"
    elif len(allowed) == 1:
        room = "only `%s` belongs there" % allowed[0]
    else:
        room = "only %s and `%s` belong there" % (
            ", ".join("`%s`" % a for a in allowed[:-1]), allowed[-1])
    hint = ""
    if form == "ref" and "attr" in extra:
        # The reachable one. `target: {ref:, attr:}` is a supported form, so
        # the same pair in an argument position looks legal -- and it used to
        # compile to the bare `_RESULTS[...]`, a different object than the
        # spec named, without a word.
        hint = (" `attr:` is legal in `target: {ref: ..., attr: ...}`, which "
                "calls a method ON that object; in an argument position there "
                "is nothing to call.")
    raise SpecError(
        "%s: %s carries %s alongside `%s`; %s.%s"
        % (where, key, ", ".join(sorted(extra)), form, room, hint))

def _arg_mapping(where: str, key: str, value: dict,
                 sketches: dict, results: set, scope: str = "part",
                 surfaces: list | None = None,
                 sets: list | None = None) -> str:
    forms = [form for form in _ARG_FORMS if form in value]
    if len(forms) != 1:
        raise SpecError(
            "%s: %s is a mapping, so it must name exactly one of %s. Got: %s"
            % (where, key, ", ".join(_ARG_FORMS),
               ", ".join(sorted(value)) or "nothing"))
    form = forms[0]
    _check_siblings(where, key, value, form)

    if form == "literal":
        literal = value["literal"]
        if isinstance(literal, bool) or not isinstance(literal, (str, int, float)):
            raise SpecError("%s: %s literal must be a string or a number"
                            % (where, key))
        return repr(str(literal) if isinstance(literal, str) else literal)

    if form == "bool":
        # The counterpart of the bare-boolean refusal. Most Abaqus keywords
        # want a SymbolicConstant and a YAML `off` arriving as False is the
        # mistake that refusal exists to catch -- but a few want the Python
        # value, and measured on Abaqus 2021 keywordBlock.synchVersions is one:
        # handed the string 'OFF' it raises "storeNodesAndElements; found
        # string, expecting False, True, 0 or 1". Written out rather than
        # inferred, so a bare `off` is still refused and only a spec that says
        # it means the boolean gets one.
        flag = value["bool"]
        if not isinstance(flag, bool):
            raise SpecError(
                "%s: %s has {bool: %r}, which is not a boolean. This form "
                "exists to say `I mean Python True/False, not the Abaqus "
                "symbol`; anything else belongs in one of the other forms."
                % (where, key, flag))
        return repr(flag)

    if form == "sketch":
        sid = str(value["sketch"])
        if sid not in sketches:
            raise SpecError(
                "%s: %s refers to sketch %r before it is drawn. Sketches "
                "available here: %s"
                % (where, key, sid, ", ".join(sorted(sketches)) or "none"))
        return "_sk_%s" % sid

    if form in ("datum", "ref"):
        alias = str(value[form])
        if alias not in results:
            raise SpecError(
                "%s: %s refers to %r, which no earlier feature bound with `as:`. "
                "Bound so far: %s"
                % (where, key, alias, ", ".join(sorted(results)) or "nothing"))
        if form == "datum" and scope == "model_setup":
            raise SpecError(
                "%s: %s wants datum %r, but model_setup runs before any part "
                "or assembly exists to hold one." % (where, key, alias))
        if form == "datum":
            # A Datum* method returns a FEATURE, not the datum. The datum lives
            # in the owner's `datums` under the feature's id, which is the
            # indirection every CAE macro contains and nothing explains. Which
            # owner depends on who made it: a part datum is not in a.datums.
            owner = "p" if scope == "part" else "a"
            return "%s.datums[_RESULTS[%r].id]" % (owner, alias)
        return "_RESULTS[%r]" % alias

    if form == "new":
        return _arg_new(where, key, value, sketches, results, scope)

    if form == "surface":
        return _arg_surface(where, key, value, scope, surfaces)

    if form == "set":
        return _arg_set(where, key, value, scope, sets)

    if form == "reference_point":
        return _arg_reference_point(where, key, value, scope, sets)

    if form == "named_set":
        return _arg_named_set(where, key, value, scope, sets)

    if form == "one":
        return _arg_one(where, key, value, scope)

    if form == "vertex":
        return _arg_vertex(where, key, value, scope)

    if form == "wire_at":
        return _arg_wire(where, key, value, scope)

    if form == "instance":
        name = str(value["instance"])
        if scope != "assembly":
            raise SpecError(
                "%s: %s names instance %r, but a part feature runs before "
                "anything is instanced." % (where, key, name))
        return "a.instances[%r]" % name

    raw = str(value["select"])
    sel = _parse(raw, value.get("expect"), "%s %s" % (where, key))
    if scope == "model_setup":
        raise SpecError(
            "%s: %s selects %r, but model_setup runs before any part or "
            "instance exists. Move it to the part, the assembly or an "
            "interaction." % (where, key, raw))
    if scope == "assembly":
        if sel.instance is None:
            raise SpecError(
                "%s: %s selects %r, which does not say which instance it is "
                "on. A part instanced twice has one set of faces; the two "
                "become different faces only after the instance transform. "
                "Write '<instance>:%s'." % (where, key, raw, raw))
        return selectors.resolve_expression(
            sel, "a.instances[%r]" % str(sel.instance))
    if sel.instance is not None:
        raise SpecError(
            "%s: %s selects %r, which names an instance. A feature is applied "
            "to the PART, before it is instanced — write %r."
            % (where, key, raw, raw.split(":", 1)[1]))
    return selectors.resolve_expression(sel, "p")

def _arg_surface(where: str, key: str, value: dict, scope: str,
                 surfaces: list | None) -> str:
    """``{surface: "Lower:face@z=max"}`` -- build the surface a pair needs.

    Tie, contact, coupling and shell-to-solid all take Regions, and a Region
    that spans faces is an assembly Surface, which has to be created before it
    can be passed. Creating it inline keeps the pair readable as one thing
    instead of three lines that have to agree with each other.
    """
    if surfaces is None:
        raise SpecError(
            "%s: %s asks for a surface. Surfaces live on the assembly, and a "
            "part feature runs before anything is instanced — build the "
            "geometry here and make the surface in the interaction that uses "
            "it." % (where, key))
    raw = str(value["surface"])
    sel = _parse(raw, value.get("expect"), "%s %s" % (where, key))
    if sel.instance is None:
        raise SpecError(
            "%s: %s selects %r, which does not say which instance it is on. A "
            "part instanced twice has one set of faces; the two become "
            "different faces only after the instance transform. Write "
            "'<instance>:%s'." % (where, key, raw, raw))
    kwarg = sel.surface_kwarg
    if kwarg is None:
        raise SpecError(
            "%s: %s selects %ss, which cannot form a surface. A tie and a "
            "contact pair both need faces." % (where, key, sel.kind))

    name = str(value.get("name") or "%s_%s" % (
        re.sub(r"[^A-Za-z0-9]+", "_", where).strip("_"), key)).upper()
    if not _IDENT_RE.match(name):
        raise SpecError("%s: %s asks for surface name %r, which Abaqus cannot "
                        "use" % (where, key, name))
    if name in surfaces:
        raise SpecError(
            "%s: %s would create surface %r, which this interaction already "
            "created. Give one of them a `name:`." % (where, key, name))
    surfaces.append(name)
    return "_gsurface(a, %r, %s, %r, %r)" % (
        name, selectors.resolve_expression(
            sel, "a.instances[%r]" % str(sel.instance)), kwarg, where)

def _arg_set(where: str, key: str, value: dict, scope: str,
             sets: list | None) -> str:
    """``{set: "Bar:face@z=min", name: "FIX"}`` -- the region a condition acts on.

    A boundary condition and a load both take a Region, and unlike an
    interaction they usually want a SET rather than a surface: nodes, not
    faces. The set is named and created here so the assembly carries it, which
    is also what makes the node count checkable -- and the node count is the
    whole difference between 100 N and 400 N.

    Measured on Abaqus 2021, a 10x10x100 cantilever with `cf2=-100` on a set
    of the four tip corners: total reaction 400 N, tip -0.7584553 mm, job
    COMPLETED, no warning. The same call at cf2=-25 on the same four nodes is
    100 N and -0.1896138, which is P L^3 / (3 E I) to 0.45%. The magnitude is
    written per node, so the number in the spec is not the load.
    """
    if scope == "part":
        # A PART set, which is a different object from an assembly set and the
        # one a seam needs. Measured on Abaqus 2021 (artifacts/probe_seam2):
        # `p.engineeringFeatures.assignSeam` refuses a raw sequence exactly the
        # way the assembly one does -- "regions; found GeomSequence, expecting
        # Set" -- so there was no way to write a seam at all. Given a part Set
        # it works, and the node count moves: a 10 x 10 x 10 block partitioned
        # at mid-height meshes to 27 nodes without a seam and 36 with one, the
        # 9 duplicated nodes of the 3 x 3 seam face, and the deck carries 36.
        #
        # Part scope is also the RIGHT scope rather than merely a workable one.
        # Part features run before `generateMesh`, so the seam is assigned to
        # an unmeshed part; assigned afterwards it takes effect only if
        # something remeshes, which is the silent-no-op shape this dialect
        # keeps having to design around.
        raw = str(value["set"])
        sel = _parse(raw, value.get("expect"), "%s %s" % (where, key))
        if sel.instance is not None:
            raise SpecError(
                "%s: %s selects %r, which names an instance. A part set is "
                "built on the PART, before it is instanced — write %r."
                % (where, key, raw, raw.split(":", 1)[1]))
        name = str(value.get("name") or "%s_%s" % (
            re.sub(r"[^A-Za-z0-9]+", "_", where).strip("_"), key)).upper()
        if not _IDENT_RE.match(name):
            raise SpecError(
                "%s: %s asks for set name %r, which Abaqus cannot use"
                % (where, key, name))
        # Duplicates are caught in the kernel by _gset, which is holding the
        # part and can list the names that are really on it. There is no
        # per-part registry on this side to check against, and inventing one
        # would duplicate a check that already exists somewhere better.
        return "_gset(p, %r, %s, %r, %r)" % (
            name, selectors.resolve_expression(sel, "p"), sel.attribute, where)

    if sets is None:
        # A dispatch path that keeps no set registry. Assembly operations and
        # conditions both keep one; a generic STEP does not, because a step is
        # made before any region exists to put in a set.
        raise SpecError(
            "%s: %s asks for a set, and this dispatch point keeps no set "
            "registry, so it cannot build one. A seam belongs on the PART (a "
            "part feature builds a part set with this same form, and it runs "
            "before the mesh, which is when a seam has to be assigned); a "
            "crack front or a load region belongs in `assembly.operations` or "
            "`conditions`, both of which can. Otherwise use `{select:}` for "
            "calls that take a sequence." % (where, key))

    raw = str(value["set"])
    sel = _parse(raw, value.get("expect"), "%s %s" % (where, key))
    if sel.instance is None:
        raise SpecError(
            "%s: %s selects %r, which does not say which instance it is on. "
            "Write '<instance>:%s'." % (where, key, raw, raw))

    name = str(value.get("name") or "%s_%s" % (
        re.sub(r"[^A-Za-z0-9]+", "_", where).strip("_"), key)).upper()
    if not _IDENT_RE.match(name):
        raise SpecError("%s: %s asks for set name %r, which Abaqus cannot use"
                        % (where, key, name))
    if name in [entry["name"] for entry in sets]:
        raise SpecError(
            "%s: %s would create set %r, which this call already created. Give "
            "one of them a `name:`." % (where, key, name))

    # The record, not just the name: whether this call needs `expect.points` is
    # decided by the caller, which is the only place that can see both the sets
    # it built and the expectations it carries.
    sets.append({"name": name, "kind": sel.kind, "expect": sel.expect})
    return "_gset(a, %r, %s, %r, %r)" % (
        name, selectors.resolve_expression(
            sel, "a.instances[%r]" % str(sel.instance)),
        sel.attribute, where)

def _point3(where: str, key: str, raw, what: str) -> tuple:
    if not isinstance(raw, (list, tuple)) or len(raw) != 3:
        raise SpecError("%s: %s %s must be three numbers" % (where, key, what))
    out = []
    for value in raw:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise SpecError("%s: %s %s must be three numbers, got %r"
                            % (where, key, what, raw))
        out.append(float(value))
    return tuple(out)

def _arg_reference_point(where: str, key: str, value: dict, scope: str,
                         sets: list | None) -> str:
    """``{reference_point: [x, y, z]}`` -- the point a constraint controls.

    Coupling, RigidBody and MultipointConstraint all take a control point, and
    nothing in this dialect could produce one. Measured on Abaqus 2021
    (artifacts/probe_rp), the round trip is three objects deep and none of them
    is nameable from a spec: `a.ReferencePoint(...)` returns a FEATURE, the
    point is `a.referencePoints[feature.id]`, and the constraint wants a REGION
    over that. So the form makes all three and hands back the set.

    Two ways to say where. Three numbers are assembly coordinates. `{at:
    "<instance>:face@z=max"}` puts it at the centroid of exactly one selected
    entity, which is what a control point almost always wants and takes the
    arithmetic out of it -- and the arithmetic is worth taking out, because
    getting it wrong is silent: the same bar with the point 50 mm past the end
    of the face solved with 0 errors, 0 warnings and COMPLETED, and answered
    `location: whole_model` with -0.61471903 against a theory of -0.19047619.
    Nothing refuses an offset point, because an offset control point is also
    how a moment gets applied; the two look identical from here.

    A second form falls out of this one. A reference point sits on no face and
    no edge, so no selector can find it again -- which would leave a coupling
    that can be created and then never loaded. `{named_set:}` is how a later
    call reaches it; see _arg_named_set.
    """
    if sets is None:
        raise SpecError(
            "%s: %s asks for a reference point. A reference point is created "
            "on the ASSEMBLY and handed to a constraint as a region, so this "
            "form belongs in an interaction, a step or a condition -- not "
            "where the part is still being shaped." % (where, key))

    raw = value["reference_point"]
    name = str(value.get("name") or "%s_%s" % (
        re.sub(r"[^A-Za-z0-9]+", "_", where).strip("_"), key)).upper()
    if not _IDENT_RE.match(name):
        raise SpecError("%s: %s asks for set name %r, which Abaqus cannot use"
                        % (where, key, name))
    if name in [entry["name"] for entry in sets]:
        raise SpecError(
            "%s: %s would create set %r, which this call already created. Give "
            "one of them a `name:`." % (where, key, name))
    sets.append({"name": name, "kind": "reference_point", "expect": "=1"})

    if isinstance(raw, dict):
        if set(raw) != {"at"}:
            raise SpecError(
                "%s: %s has {reference_point: {%s}}. Give three numbers for "
                "assembly coordinates, or `{at: \"<instance>:face@z=max\"}` to "
                "put it at the centroid of exactly one selected entity."
                % (where, key, ", ".join(sorted(raw)) or "nothing"))
        at = str(raw["at"])
        entity = _arg_one(where, key, {"one": at}, scope)
        return "_grp(a, %r, _rp_centroid(%s, %r, %r), %r, %r)" % (
            name, entity, where, at, where, at)

    point = _point3(where, key, raw, "reference_point")
    return "_grp(a, %r, %r, %r)" % (name, point, where)

def _arg_named_set(where: str, key: str, value: dict, scope: str,
                   sets: list | None) -> str:
    """``{named_set: "RP"}`` -- the set an earlier call in this spec built.

    Needed because of one asymmetry. Every other region form re-finds its
    region by geometry, so two calls acting on the same face just write the
    same selector twice. A reference point cannot be re-found: it sits on no
    face and no edge, and no selector reaches it. Without this form a coupling
    could be created and then never loaded, which is the entire purpose of
    creating one -- so `{reference_point:}` without `{named_set:}` would be a
    feature that cannot be used for the thing it is for.

    Deliberately not a lookup at generation time: the set registry is built
    per call (`sets: list = []` in each of the interaction, step and condition
    loops), so nothing on this side can see across two calls. The kernel can,
    and `_gnamed` refuses there with the assembly's actual set names in the
    message -- a better list than this side could produce anyway.
    """
    if sets is None:
        raise SpecError(
            "%s: %s names an assembly set. Sets are built on the assembly, so "
            "this form belongs in an interaction, a step or a condition, not "
            "where the part is still being shaped." % (where, key))
    raw = value["named_set"]
    if not isinstance(raw, str) or not raw.strip():
        raise SpecError(
            "%s: %s must name a set as a string, e.g. `{named_set: RP}`. Got "
            "%r." % (where, key, raw))
    # Upper-cased for the same reason the creating forms upper-case: Abaqus set
    # names are case-insensitive and `{set:}` and `{reference_point:}` both
    # store the name folded, so a spec writing `name: rp` there and
    # `named_set: rp` here has to reach the same set.
    name = raw.strip().upper()
    if not _IDENT_RE.match(name):
        raise SpecError("%s: %s names set %r, which Abaqus cannot use"
                        % (where, key, name))
    return "_gnamed(a, %r, %r)" % (name, where)

def _arg_one(where: str, key: str, value: dict, scope: str) -> str:
    """``{one: "Mover:face@x=min"}`` -- the entity, not the sequence of one.

    `{select:}` always compiles to a GeomSequence: core/selectors.py returns
    whatever getByBoundingBox produced, never an element of it. Four of the
    eleven argument forms therefore cannot feed a method that wants one Face,
    Edge or Cell -- which is what every positioning constraint (FaceToFace,
    ParallelFace, EdgeToEdge) takes. `{one:}` is one form rather than a
    face_at/edge_at/cell_at family: it reuses the whole selector grammar and
    the existing count assertion, and serves any method that wants a single
    entity of any kind.
    """
    raw = str(value["one"])
    sel = _parse(raw, "=1", "%s %s" % (where, key))
    if scope == "model_setup":
        raise SpecError(
            "%s: %s selects %r, but model_setup runs before any part or "
            "instance exists. Move it to the part, the assembly or an "
            "interaction." % (where, key, raw))
    if scope == "assembly":
        if sel.instance is None:
            raise SpecError(
                "%s: %s selects %r, which does not say which instance it is "
                "on. A part instanced twice has one set of faces; the two "
                "become different faces only after the instance transform. "
                "Write '<instance>:%s'." % (where, key, raw, raw))
        owner = "a.instances[%r]" % str(sel.instance)
    else:
        if sel.instance is not None:
            raise SpecError(
                "%s: %s selects %r, which names an instance. A feature is "
                "applied to the PART, before it is instanced — write %r."
                % (where, key, raw, raw.split(":", 1)[1]))
        owner = "p"
    return "_gone(%s, %r)" % (selectors.resolve_expression(sel, owner),
                              "%s %s" % (where, key))

def _arg_vertex(where: str, key: str, value: dict, scope: str) -> str:
    """``{vertex: {instance: Fixed, at: [x, y, z]}}`` -- a corner, by position.

    WirePolyLine is why this exists, and why it takes an instance rather than
    bare coordinates. Measured on Abaqus 2021: a wire built from coordinate
    tuples is ACCEPTED, adds a real edge to a.edges, and a ConnectorSection
    assigns to it without complaint -- and the solver then says "CONNECTOR
    ELEMENT 1 (ASSEMBLY) NODE NUMBERS CANNOT BE BOTH ZERO", because the wire is
    attached to nothing. Nothing at build time can tell the two apart: both
    endpoints sit on a mesh node either way, and the difference is which
    instance owns them. So the spec cannot write the coordinate form at all.
    """
    if scope != "assembly":
        raise SpecError(
            "%s: %s asks for a vertex of an instance, which only exists in the "
            "assembly." % (where, key))
    body = value["vertex"]
    if not isinstance(body, dict) or set(body) != {"instance", "at"}:
        raise SpecError(
            "%s: %s must be {vertex: {instance: <name>, at: [x, y, z]}}"
            % (where, key))
    instance = str(body["instance"])
    point = _point3(where, key, body["at"], "`at`")
    return "_gvertex(a, %r, %r, %r)" % (instance, point, where)

def _arg_wire(where: str, key: str, value: dict, scope: str) -> str:
    """``{wire_at: [[x,y,z], [x,y,z]]}`` -- the wire that runs between them.

    A wire adds its edge to the ASSEMBLY, not to any instance, so the ordinary
    selector cannot reach it: `Fixed:edge@z=max` resolves against
    a.instances['Fixed'].edges, which measured 12 while a.edges held only the 4
    wires. The two endpoints that created the wire are what finds it again, and
    the count assertion is what catches a wire that was never made.
    """
    if scope != "assembly":
        raise SpecError(
            "%s: %s asks for a wire, which lives on the assembly." % (where, key))
    raw = value["wire_at"]
    if not isinstance(raw, (list, tuple)) or len(raw) != 2:
        raise SpecError("%s: %s must be {wire_at: [[x,y,z], [x,y,z]]}"
                        % (where, key))
    first = _point3(where, key, raw[0], "first end")
    second = _point3(where, key, raw[1], "second end")
    if first == second:
        raise SpecError("%s: %s names the same point twice" % (where, key))
    return "_gwire(a, %r, %r, %r)" % (first, second, where)

def _arg_new(where: str, key: str, value: dict,
             sketches: dict, results: set, scope: str) -> str:
    """``{new: "mesh.ElemType", ...}`` -- construct an object, not call a method.

    Dispatch targets an object and calls a method on it. Some Abaqus arguments
    are not values but objects that have to be built first, and the one that
    forces this to exist is ``setElementType(elemTypes=(mesh.ElemType(...), ))``:
    ElemType is a constructor in the `mesh` module, reachable from no part and
    no assembly. Without this the whole meshing API stays behind a hand-written
    wrapper, which is the enumeration this layer exists to avoid.
    """
    dotted = str(value["new"])
    if dotted.count(".") != 1:
        raise SpecError(
            "%s: %s asks for %r. Write it as <module>.<Class>, e.g. "
            "'mesh.ElemType'. Modules available: %s"
            % (where, key, dotted, ", ".join(_MODULES)))
    module_name, class_name = dotted.split(".")
    if module_name not in _MODULES:
        raise SpecError(
            "%s: %s asks for module %r, which the generated script does not "
            "import. Available: %s" % (where, key, module_name,
                                       ", ".join(_MODULES)))
    if not _IDENT_RE.match(class_name) or class_name.startswith("_"):
        raise SpecError("%s: %s asks for %r, which is not a public class name"
                        % (where, key, class_name))
    pairs = []
    for sub in sorted(value):
        if sub == "new":
            continue
        if not _IDENT_RE.match(str(sub)):
            raise SpecError("%s: %r is not a keyword name Abaqus could accept"
                            % (where, sub))
        pairs.append("%r: %s" % (str(sub),
                                 _arg_expr(where, "%s.%s" % (key, sub),
                                           value[sub], sketches, results, scope)))
    return "_gnew(%r, %r, {%s}, %r)" % (module_name, class_name,
                                        ", ".join(pairs), where)
