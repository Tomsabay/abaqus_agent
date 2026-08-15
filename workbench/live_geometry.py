"""
workbench/live_geometry.py
--------------------------
Turn a HALF-WRITTEN draft into something drawable, so the viewport fills in
while the model is still typing instead of staying empty for minutes.

Two jobs, both pure functions over text:

``partial_spec``  tolerant YAML: the draft arrives one token at a time, so the
                  accumulated text is almost never valid YAML. Parse the
                  longest prefix that is.

``preview_payload`` the drawable subset. The named-op dialect is narrow on
                  purpose (XY sketch, one base extrude, circular cuts), and
                  that subset is exactly what a browser can draw by itself
                  with an extruded outline plus holes — no CAE, no solver, no
                  round trip.

What comes out of here is an APPROXIMATION and is labelled as one everywhere
it surfaces. It is not a validation signal: a spec that draws fine here can
still be refused by the builder (a selector that matches nothing, a cut with
no straight edge to orient against). The real preview replaces it the moment
the proposal lands.
"""

from __future__ import annotations

import math

import yaml

_SPEC_MARK = "===SPEC==="
_REPLY_MARK = "===REPLY==="

# How many trailing lines may be dropped to find a parseable prefix. A
# truncation error lives in the last line or two (a half-written `- {name:`);
# needing more than this means the text is not YAML at all yet.
_MAX_TRIM_LINES = 12


def partial_spec(text: str) -> dict | None:
    """The longest parseable prefix of a streaming draft, as a dict.

    Returns None while the text is not yet a YAML mapping — which is the
    normal state for the first few hundred tokens, and the whole state of a
    plan-stage stream (it has no spec at all).
    """
    if not text:
        return None
    body = text.split(_SPEC_MARK, 1)[1] if _SPEC_MARK in text else text
    body = body.split(_REPLY_MARK, 1)[0]
    body = body.lstrip()
    if body.startswith("```"):
        # ```yaml fence: drop the opening line, keep everything after it.
        body = body.split("\n", 1)[1] if "\n" in body else ""
    lines = body.split("\n")
    for cut in range(len(lines), max(0, len(lines) - _MAX_TRIM_LINES) - 1, -1):
        chunk = "\n".join(lines[:cut])
        if not chunk.strip():
            continue
        try:
            data = yaml.safe_load(chunk)
        except yaml.YAMLError:
            continue
        if isinstance(data, dict):
            return data
    return None


def _num(value) -> float | None:
    """A finite float, or None. Mid-stream a key can exist with no value yet
    (`depth:` alone parses to None), and a NaN would poison the viewport."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    v = float(value)
    return v if math.isfinite(v) else None


def _xy(value) -> list[float] | None:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return None
    a, b = _num(value[0]), _num(value[1])
    return None if a is None or b is None else [a, b]


def _outline(profile: dict) -> dict | None:
    if not isinstance(profile, dict):
        return None
    if "rect" in profile and isinstance(profile["rect"], dict):
        c1 = _xy(profile["rect"].get("corner1"))
        c2 = _xy(profile["rect"].get("corner2"))
        if c1 and c2:
            return {"kind": "rect", "corner1": c1, "corner2": c2}
    if "circle" in profile and isinstance(profile["circle"], dict):
        center = _xy(profile["circle"].get("center"))
        r = _num(profile["circle"].get("r"))
        if center and r and r > 0:
            return {"kind": "circle", "center": center, "r": r}
    return None


def _part_solid(part: dict) -> dict | None:
    """One part reduced to {outline, holes, depth} — or None if it is not (yet)
    a named-op solid. A generic `entities:` sketch or a `call:` feature has no
    recorded profile, so there is nothing to draw and nothing is guessed."""
    features = part.get("features")
    if not isinstance(features, list):
        return None
    sketches: dict[str, dict] = {}
    outline = None
    depth = None
    holes: list[dict] = []
    for feat in features:
        if not isinstance(feat, dict):
            continue
        op = feat.get("op")
        if op == "sketch":
            sid = feat.get("id")
            shape = _outline(feat.get("profile") or {})
            if isinstance(sid, str) and shape:
                sketches[sid] = shape
        elif op in ("extrude", "cut_extrude"):
            shape = sketches.get(str(feat.get("sketch")))
            d = _num(feat.get("depth"))
            if not shape or d is None:
                continue
            if op == "extrude":
                if outline is None:          # a second extrude is a spec error
                    outline, depth = shape, d
            elif shape["kind"] == "circle":  # only circular cuts are buildable
                holes.append({"center": shape["center"], "r": shape["r"],
                              "depth": d})
    if outline is None or depth is None:
        return None
    name = part.get("name")
    return {"name": str(name) if name is not None else "?",
            "outline": outline, "holes": holes, "depth": depth}


def preview_payload(spec: dict | None) -> dict | None:
    """The drawable view of a (possibly half-written) spec, or None.

    `parts` carries the solids; `instances` places them the way the assembly
    asks. A part with no instance is still drawn at the origin — during a
    stream the parts arrive long before the assembly block does, and an empty
    viewport until the very end is exactly what this exists to avoid.
    """
    if not isinstance(spec, dict):
        return None
    solids = []
    for part in spec.get("parts") or []:
        if isinstance(part, dict):
            solid = _part_solid(part)
            if solid:
                solids.append(solid)
    if not solids:
        return None
    instances = []
    assembly = spec.get("assembly")
    if isinstance(assembly, dict):
        for inst in assembly.get("instances") or []:
            if not isinstance(inst, dict):
                continue
            part = inst.get("part")
            if not isinstance(part, str):
                continue
            translate = inst.get("translate")
            xyz = [0.0, 0.0, 0.0]
            if isinstance(translate, (list, tuple)) and len(translate) == 3:
                vals = [_num(v) for v in translate]
                if all(v is not None for v in vals):
                    xyz = vals
            name = inst.get("name")
            instances.append({"name": str(name) if name is not None else part,
                              "part": part, "translate": xyz})
    return {"parts": solids, "instances": instances}
