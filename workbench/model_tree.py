"""The model tree the left pane draws, derived from the spec and nothing else.

Why the server builds it rather than the browser: the page has no YAML parser.
frontend/vendor holds three.min.js and OrbitControls.js, and adding a YAML
implementation to render a sidebar would be a second grammar to keep in step
with schema/spec_schema.json — the tree would drift from what actually gets
built, which is the one failure this tree exists to prevent.

The rule the engine lives by applies here too: nothing a spec declares may
vanish. A key this module does not recognise becomes an `unknown` row naming
it, not a row that is quietly missing. A tree that draws four of five parts
looks exactly like a model that has four parts, and the user has no way to tell
the difference.
"""

from __future__ import annotations

from typing import Any

# Two dialects ship: v2 (the assembly form) and deck (a finished .inp handed
# over as it stands). The tree has to draw either, and has to say which one it
# drew.
#
# `geometry` and `bc_load` are deliberately NOT listed. They were v1's, the
# schema refuses them now, and this set is what decides `unknown_keys` -- so
# someone who types `geometry:` into the editor gets told the key does not
# exist, which is the whole point of the pane. `analysis` stays: it is still a
# legal v2 key (cpus, timeout), and treating it as a v1 marker used to send a
# valid v2 spec whose `parts:` block was not yet typed down the v1 branch, where
# it drew a part called "?" and a step called "Static" that the spec never said.
_TOP_KNOWN = {"meta", "material", "materials", "parts", "assembly",
              "interactions", "steps", "conditions", "outputs",
              "deck", "analysis"}


def _num(value: Any) -> str:
    """A number as the spec wrote it, not as float repr would rewrite it."""
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, float) and value == int(value) and abs(value) < 1e15:
        return "%g" % value
    return str(value)


def _vec(value: Any) -> str:
    if isinstance(value, (list, tuple)):
        return "(%s)" % ", ".join(_num(v) for v in value)
    return _num(value)


def _literal(value: Any) -> Any:
    """`{literal: "Press"}` and `{ref: x}` are how the dispatched form escapes
    the ALL-CAPS-becomes-a-symbol rule. For display, unwrap the readable one."""
    if isinstance(value, dict):
        if "literal" in value:
            return value["literal"]
        if "ref" in value:
            return "→%s" % value["ref"]
    return value


def _row(row_id: str, kind: str, label: str, **extra) -> dict:
    row = {"id": row_id, "kind": kind, "label": str(label)}
    row.update({k: v for k, v in extra.items() if v not in (None, [], {}, "")})
    return row


def _is_dispatched(entry: dict) -> bool:
    return isinstance(entry, dict) and "call" in entry


# --- parts ------------------------------------------------------------------

def _part_rows(spec: dict) -> list[dict]:
    rows = []
    for i, part in enumerate(spec.get("parts") or []):
        if not isinstance(part, dict):
            rows.append(_row("part:%d" % i, "unknown", "parts[%d]" % i,
                             detail="不是一个映射，无法解释", warn=True,
                             path="parts[%d]" % i))
            continue
        name = str(part.get("name") or "parts[%d]" % i)
        mesh = part.get("mesh") or {}
        section = part.get("section") or {}
        facts = []
        if section.get("type"):
            facts.append(["截面", str(section["type"])])
        if section.get("material"):
            facts.append(["材料", str(section["material"])])
        if mesh.get("element"):
            facts.append(["单元", str(mesh["element"])])
        if mesh.get("seed") is not None:
            facts.append(["种子", _num(mesh["seed"])])
        if mesh.get("technique"):
            facts.append(["网格技术", str(mesh["technique"])])

        ops = []
        generic = 0
        for feat in part.get("features") or []:
            if not isinstance(feat, dict):
                continue
            if "call" in feat:
                ops.append(str(feat["call"]))
                generic += 1
            elif "op" in feat:
                ops.append(str(feat["op"]))
        children = []
        for j, feat in enumerate(part.get("features") or []):
            if not isinstance(feat, dict):
                continue
            if "call" in feat:
                children.append(_row(
                    "part:%s:feat:%d" % (name, j), "call", str(feat["call"]),
                    detail="派发调用", path="parts[%d].features[%d]" % (i, j)))
            elif "op" in feat:
                label = str(feat["op"])
                bits = []
                if feat.get("id"):
                    bits.append(str(feat["id"]))
                if feat.get("sketch"):
                    bits.append("← %s" % feat["sketch"])
                if feat.get("depth") is not None:
                    bits.append("深度 %s" % _num(feat["depth"]))
                children.append(_row("part:%s:feat:%d" % (name, j), "op", label,
                                     detail=" · ".join(bits),
                                     path="parts[%d].features[%d]" % (i, j)))
            else:
                children.append(_row(
                    "part:%s:feat:%d" % (name, j), "unknown",
                    "features[%d]" % j,
                    detail="既没有 op 也没有 call", warn=True,
                    path="parts[%d].features[%d]" % (i, j)))

        # `expect:` is the truth layer — the tree should show that a part is
        # checked, because a part with no expect block is one the generator will
        # refuse the moment it uses a generic call.
        expect = part.get("expect") or {}
        for key in sorted(expect):
            facts.append(["expect.%s" % key, _vec(expect[key])])

        rows.append(_row(
            "part:%s" % name, "part", name,
            detail=" · ".join(ops) if ops else "没有 features",
            facts=facts, children=children,
            generic_calls=generic or None,
            path="parts[%d]" % i))
    return rows


# --- assembly ---------------------------------------------------------------

def _instance_rows(spec: dict) -> list[dict]:
    rows = []
    assembly = spec.get("assembly") or {}
    for i, inst in enumerate(assembly.get("instances") or []):
        if not isinstance(inst, dict):
            rows.append(_row("inst:%d" % i, "unknown", "instances[%d]" % i,
                             detail="不是一个映射，无法解释", warn=True,
                             path="assembly.instances[%d]" % i))
            continue
        name = str(inst.get("name") or "instances[%d]" % i)
        facts = []
        if inst.get("part"):
            facts.append(["零件", str(inst["part"])])
        if inst.get("translate"):
            facts.append(["平移", _vec(inst["translate"])])
        if inst.get("rotate"):
            rot = inst["rotate"]
            if isinstance(rot, dict):
                facts.append(["旋转", "%s° 绕 %s→%s"
                              % (_num(rot.get("angle")), _vec(rot.get("axis_start")),
                                 _vec(rot.get("axis_end")))])
            else:
                facts.append(["旋转", _vec(rot)])
        rows.append(_row("inst:%s" % name, "instance", name,
                         detail=str(inst.get("part") or ""), facts=facts,
                         # The viewport keys its meshes by instance name, so this
                         # is what a click has to send it.
                         instance=name,
                         # Machine field, not the "零件" fact above. The page
                         # needs the part name to colour a part row the same as
                         # its first instance, and reading it out of `facts`
                         # meant matching on a display label -- which breaks the
                         # moment the tree is rendered in English, and put a
                         # Chinese literal in the JS besides.
                         part=str(inst.get("part") or ""),
                         path="assembly.instances[%d]" % i))
    for i, op in enumerate(assembly.get("operations") or []):
        if _is_dispatched(op):
            rows.append(_row("asmop:%d" % i, "call", str(op["call"]),
                             detail="装配操作",
                             path="assembly.operations[%d]" % i))
        else:
            rows.append(_row("asmop:%d" % i, "unknown",
                             "assembly.operations[%d]" % i,
                             detail="没有 call", warn=True,
                             path="assembly.operations[%d]" % i))
    return rows


# --- interactions -----------------------------------------------------------

def _interaction_rows(spec: dict) -> list[dict]:
    rows = []
    for i, inter in enumerate(spec.get("interactions") or []):
        if not isinstance(inter, dict):
            rows.append(_row("inter:%d" % i, "unknown", "interactions[%d]" % i,
                             detail="不是一个映射，无法解释", warn=True,
                             path="interactions[%d]" % i))
            continue
        if _is_dispatched(inter):
            name = str(_literal(inter.get("name")) or inter["call"])
            facts = [["调用", str(inter["call"])]]
            surfaces = []
            for key, value in sorted(inter.items()):
                if isinstance(value, dict) and "surface" in value:
                    surfaces.append(str(value["surface"]))
                    facts.append([key, str(value["surface"])])
            rows.append(_row("inter:%s" % name, "call", name,
                             detail=str(inter["call"]), facts=facts,
                             surfaces=surfaces,
                             path="interactions[%d]" % i))
            continue
        name = str(inter.get("name") or "interactions[%d]" % i)
        kind = str(inter.get("type") or "?")
        facts = []
        main = inter.get("main")
        secondary = inter.get("secondary")
        if main:
            facts.append(["主面", str(main)])
        if secondary:
            facts.append(["从面", str(secondary)])
        if inter.get("position_tolerance") is not None:
            facts.append(["位置容差", _num(inter["position_tolerance"])])
        prop = inter.get("property") or {}
        if prop.get("friction") is not None:
            facts.append(["摩擦系数", _num(prop["friction"])])
        if prop.get("normal"):
            facts.append(["法向", str(prop["normal"])])
        if inter.get("sliding"):
            facts.append(["滑移", str(inter["sliding"])])
        rows.append(_row("inter:%s" % name, kind, name, detail=kind, facts=facts,
                         selectors=[s for s in (main, secondary) if s],
                         path="interactions[%d]" % i))
    return rows


# --- steps and conditions ---------------------------------------------------

def _condition_label(entry: dict, index: int) -> tuple[str, str]:
    name = _literal(entry.get("name"))
    if not isinstance(name, str) or not name:
        name = "conditions[%d]" % index
    return str(name), str(entry.get("call") or "?")


def _step_rows(spec: dict) -> list[dict]:
    """Steps, with each condition filed under the step it names.

    A dispatched condition declares its own `createStepName`, which is the only
    thing that says where it acts — Abaqus refuses a name that is not a step, so
    a condition filed under `(未归属)` here means the spec is about to be
    refused, and saying so on screen beats saying it in a traceback.
    """
    conditions: dict[str, list[dict]] = {}
    orphans: list[dict] = []
    for i, entry in enumerate(spec.get("conditions") or []):
        if not isinstance(entry, dict) or "call" not in entry:
            orphans.append(_row("cond:%d" % i, "unknown", "conditions[%d]" % i,
                                detail="没有 call", warn=True,
                                path="conditions[%d]" % i))
            continue
        name, call = _condition_label(entry, i)
        step = _literal(entry.get("createStepName"))
        facts = [["调用", call]]
        sets = []
        region = entry.get("region")
        if isinstance(region, dict):
            for form in ("set", "surface", "select"):
                if form in region:
                    facts.append(["区域", str(region[form])])
                    sets.append(str(region.get("name") or region[form]))
                    break
            if region.get("expect"):
                facts.append(["数量断言", str(region["expect"])])
        for key in sorted(entry):
            if key in ("call", "name", "createStepName", "region", "expect",
                       "as", "target"):
                continue
            facts.append([key, _vec(entry[key])])
        points = (entry.get("expect") or {}).get("points")
        if points is not None:
            facts.append(["expect.points", _num(points)])
        row = _row("cond:%s" % name, "condition", name, detail=call,
                   facts=facts, sets=sets, path="conditions[%d]" % i)
        if isinstance(step, str) and step:
            conditions.setdefault(step, []).append(row)
        else:
            orphans.append(row)

    rows = []
    for i, step in enumerate(spec.get("steps") or []):
        if not isinstance(step, dict):
            rows.append(_row("step:%d" % i, "unknown", "steps[%d]" % i,
                             detail="不是一个映射，无法解释", warn=True,
                             path="steps[%d]" % i))
            continue
        if _is_dispatched(step):
            name = str(_literal(step.get("name")) or "steps[%d]" % i)
            facts = [["调用", str(step["call"])]]
            for key in sorted(step):
                if key in ("call", "name", "expect", "as", "target"):
                    continue
                facts.append([key, _vec(_literal(step[key]))])
            children = conditions.pop(name, [])
            rows.append(_row("step:%s" % name, "step", name,
                             detail=str(step["call"]), facts=facts,
                             children=children, path="steps[%d]" % i))
            continue
        name = str(step.get("name") or "steps[%d]" % i)
        facts = [["类型", str(step.get("type") or "Static")]]
        for key in ("time_period", "initial_inc", "min_inc", "max_inc",
                    "max_num_inc", "nlgeom"):
            if step.get(key) is not None:
                facts.append([key, _num(step[key])])
        children = []
        for j, bc in enumerate(step.get("bcs") or []):
            children.append(_row(
                "step:%s:bc:%d" % (name, j), "condition",
                str(bc.get("name") or "bcs[%d]" % j),
                detail=str(bc.get("type") or "?"),
                facts=[["区域", str(bc.get("region") or "")]],
                selectors=[str(bc["region"])] if bc.get("region") else None,
                path="steps[%d].bcs[%d]" % (i, j)))
        for j, load in enumerate(step.get("loads") or []):
            facts = [["区域", str(load.get("region") or "")]]
            if load.get("value") is not None:
                facts.append(["大小", _num(load["value"])])
            children.append(_row(
                "step:%s:load:%d" % (name, j), "condition",
                str(load.get("name") or "loads[%d]" % j),
                detail=str(load.get("type") or "?"), facts=facts,
                selectors=[str(load["region"])] if load.get("region") else None,
                path="steps[%d].loads[%d]" % (i, j)))
        children.extend(conditions.pop(name, []))
        rows.append(_row("step:%s" % name, "step", name,
                         detail=str(step.get("type") or "Static"),
                         facts=facts, children=children,
                         path="steps[%d]" % i))

    # Anything left named a step that does not exist. Abaqus refuses this, so it
    # is worth a warning row rather than silence.
    for step_name in sorted(conditions):
        rows.append(_row(
            "step:missing:%s" % step_name, "unknown", step_name,
            detail="conditions 指向了这个分析步，但 steps 里没有它", warn=True,
            children=conditions[step_name]))
    if orphans:
        rows.append(_row("step:orphans", "unknown", "(未归属)",
                         detail="没有 createStepName 或无法解释的条件", warn=True,
                         children=orphans))
    return rows


# --- outputs ----------------------------------------------------------------

def _output_rows(spec: dict) -> list[dict]:
    rows = []
    outputs = spec.get("outputs") or {}
    for i, region in enumerate(outputs.get("regions") or []):
        if not isinstance(region, dict):
            continue
        name = str(region.get("name") or "regions[%d]" % i)
        rows.append(_row("region:%s" % name, "region", name,
                         detail="测量区域",
                         facts=[["选择器", str(region.get("region") or "")]],
                         selectors=[str(region["region"])] if region.get("region") else None,
                         path="outputs.regions[%d]" % i))
    for i, kpi in enumerate(outputs.get("kpis") or []):
        if not isinstance(kpi, dict):
            continue
        name = str(kpi.get("name") or "kpis[%d]" % i)
        facts = []
        for key in ("type", "location", "component", "invariant",
                    "field_variable", "step", "frame"):
            if kpi.get(key) is not None:
                facts.append([key, str(kpi[key])])
        rows.append(_row("kpi:%s" % name, "kpi", name,
                         detail=str(kpi.get("type") or "?"), facts=facts,
                         path="outputs.kpis[%d]" % i))
    variables = outputs.get("field_variables")
    if variables:
        rows.append(_row("outputs:field_variables", "fields", "场输出变量",
                         detail=", ".join(str(v) for v in variables),
                         path="outputs.field_variables"))
    return rows


# --- entry point ------------------------------------------------------------

def build_tree(spec: dict | None) -> dict:
    """The tree for one spec. Never raises — a broken spec still gets a pane.

    Returns {dialect, model, groups:[{id,label,count,rows:[...]}], unknown_keys}.
    """
    if not isinstance(spec, dict):
        return {"dialect": "unknown", "model": "", "groups": [],
                "unknown_keys": [], "problems": ["spec 不是一个映射"]}

    meta = spec.get("meta") or {}
    model = str(meta.get("model_name") or "")
    dialect = "deck" if spec.get("deck") else (
        "v2" if spec.get("parts") else "unknown")

    materials = []
    mat_entries = ([("material", spec["material"])]
                   if isinstance(spec.get("material"), dict) else [])
    mat_entries += [("materials[%d]" % mi, mat)
                    for mi, mat in enumerate(spec.get("materials") or [])]
    for mat_path, mat in mat_entries:
        if not isinstance(mat, dict):
            continue
        name = str(mat.get("name") or "?")
        facts = [[k, _num(v)] for k, v in sorted(mat.items()) if k != "name"]
        materials.append(_row("material:%s" % name, "material", name,
                              detail=" · ".join("%s %s" % (k, v) for k, v in facts[:3]),
                              facts=facts, path=mat_path))

    if dialect == "deck":
        # Drawing empty `零件` and `分析步` groups here would say the model has
        # no parts and no steps, when in fact it has a whole deck of both that
        # this tree simply cannot see inside. One row that says so is honest;
        # two empty groups are not.
        deck_file = str((spec.get("deck") or {}).get("file") or "?")
        groups = [
            {"id": "materials", "label": "材料", "count": len(materials),
             "rows": materials},
            {"id": "deck", "label": "输入文件", "count": 1, "rows": [
                _row("deck", "deck", deck_file,
                     detail="整份 .inp 原样提交；零件/分析步/边界条件都在文件里",
                     facts=[["file", deck_file]], path="deck")]},
            {"id": "outputs", "label": "输出", "count": len(_output_rows(spec)),
             "rows": _output_rows(spec)},
        ]
    else:
        parts = _part_rows(spec)
        instances = _instance_rows(spec)
        interactions = _interaction_rows(spec)
        steps = _step_rows(spec)
        outputs = _output_rows(spec)
        groups = [
            {"id": "materials", "label": "材料", "count": len(materials),
             "rows": materials},
            {"id": "parts", "label": "零件", "count": len(parts), "rows": parts},
            {"id": "assembly", "label": "装配", "count": len(instances),
             "rows": instances},
            {"id": "interactions", "label": "相互作用",
             "count": len(interactions), "rows": interactions},
            {"id": "steps", "label": "分析步", "count": len(steps), "rows": steps},
            {"id": "outputs", "label": "输出", "count": len(outputs),
             "rows": outputs},
        ]

    # Every top-level key the tree did not read. Not decoration: a spec that
    # carries a block this module has never heard of is exactly the case where a
    # tree drawn from a partial reading is worse than no tree.
    unknown = sorted(k for k in spec if k not in _TOP_KNOWN)
    return {"dialect": dialect, "model": model,
            "groups": [g for g in groups if g["rows"] or g["id"] in ("parts", "steps")],
            "unknown_keys": unknown, "problems": []}
