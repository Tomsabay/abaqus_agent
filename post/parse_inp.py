"""
post/parse_inp.py
-----------------
Pure-Python .inp reader that pulls out a *set of parts* the WBViewport can
render. Two input flavors are supported:

  1. Model-level flat layout (steel_frame_blast style):
       *NODE
         1, x, y, z
         ...
       *ELEMENT, TYPE=B31, ELSET=COLUMNS
         id, n1, n2
         ...
       *ELEMENT, TYPE=S4R, ELSET=SLABS
         id, n1, n2, n3, n4
     Every `*ELEMENT ... ELSET=<name>` block becomes one "part".

  2. Standard *Part / *Instance blocks (single-part CAE-written .inp):
     One part per `*PART, name=<name>` block; nodes/elements read locally.

Element families we care about right now:
  - Line beams (B31, B32, T3D2, B21, B22) -> emitted as line segments
  - Shells / 2D (S3/S4/CPS/CPE/M3D/CAX) -> exterior via build_surface()
  - Solids (C3D*)                        -> exterior via build_surface()

Zero deps. Meant to be safe to call from the py3 side of build_model.
"""

from __future__ import annotations

import json
from pathlib import Path

from post.export_odb_mesh import build_surface

LINE_ELEMENT_PREFIXES = ("B31", "B32", "B21", "B22", "B33", "T3D2", "T2D2")
SURFACE_ELEMENT_PREFIXES = (
    "C3D",  # 3D solids
    "S3", "S4", "S8", "STRI",  # shells
    "CPS", "CPE", "M3D", "CAX",  # 2D / axisym
)

# Cap total elements per part so a 1M-elem crash file doesn't hang the viewport.
MAX_ELEMENTS_PER_PART = 200_000

# Cap on the triangles one named surface may contribute to the tree overlay. A
# tie surface on a preview mesh is a few hundred, so this is two orders of
# magnitude of headroom; it exists so that a surface somehow covering the whole
# model cannot double the size of preview_mesh.json. A surface that hits it says
# so — `capped` on the surface, and a line in `degraded`.
MAX_FACETS_PER_SURFACE = 20_000


def _iter_data_rows(lines, start):
    """Yield comma-split data rows following an *KEYWORD line, until the next
    keyword (line starting with `*`) or EOF. Skips comment lines (`**`).

    A data line ending with "," continues on the next physical line — that is
    how CAE always writes C3D20R connectivity (21 numbers, split at 16). Before
    this join, the two halves parsed as two garbage rows, build_surface threw,
    and five of this repo's own decks previewed as empty models."""
    i = start
    while i < len(lines):
        raw = lines[i].strip()
        if not raw or raw.startswith("**"):
            i += 1
            continue
        if raw.startswith("*"):
            return
        last = i
        while raw.endswith(",") and last + 1 < len(lines):
            nxt = lines[last + 1].strip()
            if not nxt or nxt.startswith("*"):
                break
            raw = raw + nxt
            last += 1
        yield last, [c.strip() for c in raw.split(",") if c.strip()]
        i = last + 1


def _kw_and_params(line):
    """`*ELEMENT, TYPE=B31, ELSET=COLUMNS` -> ('ELEMENT', {'TYPE':'B31',...})."""
    parts = [p.strip() for p in line.strip().lstrip("*").split(",")]
    kw = parts[0].upper()
    params = {}
    for p in parts[1:]:
        if "=" in p:
            k, v = p.split("=", 1)
            params[k.strip().upper()] = v.strip()
    return kw, params


def _elem_family(el_type):
    t = el_type.upper()
    for p in LINE_ELEMENT_PREFIXES:
        if t.startswith(p):
            return "line"
    for p in SURFACE_ELEMENT_PREFIXES:
        if t.startswith(p):
            return "surface"
    return "unknown"


def _classify_part_color(name):
    """Assign an engineering-ish color to a part based on its name keyword.
    Falls back to a cycled palette in the frontend if not matched here."""
    n = name.upper()
    if "COLUMN" in n: return "#4a6fa5"    # steel blue
    if "BEAM"   in n: return "#d97757"    # brick orange
    if "SLAB" in n or "PLATE" in n: return "#8fa5b8"  # concrete gray
    if "BOLT" in n or "STUD" in n:  return "#c9a961"  # brass
    if "BRACE" in n: return "#5a7f5f"     # olive
    return None


def _read_nodes(lines, i, into):
    """Consume the data rows of a *NODE block. Returns the last line consumed."""
    last = i
    for j, row in _iter_data_rows(lines, i + 1):
        try:
            label = int(row[0])
            x = float(row[1]) if len(row) > 1 else 0.0
            y = float(row[2]) if len(row) > 2 else 0.0
            z = float(row[3]) if len(row) > 3 else 0.0
            into[label] = (x, y, z)
            last = j
        except (ValueError, IndexError):
            pass
    return last


def _read_elements(lines, i, params, into):
    el_type = params.get("TYPE", "")
    elset_name = params.get("ELSET", el_type or "PART")
    rows = []
    last = i
    for j, row in _iter_data_rows(lines, i + 1):
        try:
            conn = [int(x) for x in row[1:]]
            if conn:
                rows.append((int(row[0]), conn))
                if len(rows) > MAX_ELEMENTS_PER_PART:
                    break
            last = j
        except (ValueError, IndexError):
            pass
    into.append((elset_name, el_type, rows))
    return last


def _read_instance_placement(lines, start):
    """Read an *Instance block's optional translation and rotation data lines.

    Abaqus writes at most two: `dx, dy, dz`, then
    `xa, ya, za, xb, yb, zb, angle` — a rotation of `angle` degrees about the
    axis running a -> b. Returns (translate, rotate, index_after, inline_mesh).
    """
    translate = None
    rotate = None
    inline_mesh = False
    i = start
    while i < len(lines):
        raw = lines[i].strip()
        if not raw or raw.startswith("**"):
            i += 1
            continue
        if raw.startswith("*"):
            kw, _params = _kw_and_params(raw)
            if kw == "END INSTANCE":
                return translate, rotate, i + 1, inline_mesh
            # A *Node / *Element inside the instance means an orphan mesh
            # carried on the instance itself rather than on a *Part.
            if kw in ("NODE", "ELEMENT"):
                inline_mesh = True
            i += 1
            continue
        values = []
        for cell in raw.split(","):
            cell = cell.strip()
            if not cell:
                continue
            try:
                values.append(float(cell))
            except ValueError:
                values = []
                break
        if len(values) == 3 and translate is None:
            translate = tuple(values)
        elif len(values) == 7:
            rotate = tuple(values)
        i += 1
    return translate, rotate, i, inline_mesh


def _rotate_point(point, axis_a, axis_b, degrees):
    """Rodrigues rotation of `point` about the a->b axis, right-hand rule."""
    import math

    kx, ky, kz = (axis_b[0] - axis_a[0], axis_b[1] - axis_a[1], axis_b[2] - axis_a[2])
    norm = math.sqrt(kx * kx + ky * ky + kz * kz)
    if norm == 0.0:
        return point
    kx, ky, kz = kx / norm, ky / norm, kz / norm
    theta = math.radians(degrees)
    c, s = math.cos(theta), math.sin(theta)
    vx, vy, vz = (point[0] - axis_a[0], point[1] - axis_a[1], point[2] - axis_a[2])
    cross = (ky * vz - kz * vy, kz * vx - kx * vz, kx * vy - ky * vx)
    dot = kx * vx + ky * vy + kz * vz
    return (
        axis_a[0] + vx * c + cross[0] * s + kx * dot * (1.0 - c),
        axis_a[1] + vy * c + cross[1] * s + ky * dot * (1.0 - c),
        axis_a[2] + vz * c + cross[2] * s + kz * dot * (1.0 - c),
    )


def place_nodes(local_nodes, translate, rotate):
    """Put a part's local node coordinates where the assembly says they go.

    **Translation first, then rotation**, with the rotation axis read as
    already being in final global coordinates.

    That order was measured, not assumed, and the assumption would have been
    wrong. A probe instance translated (20, 0, 0) and turned 90 degrees about Z
    was built in CAE and its assembly-space node coordinates dumped as ground
    truth; the .inp CAE wrote for it carries

        1.2246e-15,  20.,  0.
        1.2246e-15,  20.,  0.,  1.2246e-15,  20.,  1.0,  89.99999927

    - a translation of (0, 20, 0), which is the ASKED-FOR (20, 0, 0) already
    turned by the rotation, and an axis running through that translated point.
    Replaying those two lines node for node:

        rotate-then-translate   max node error = 2.0e+01
        translate-then-rotate   max node error = 5.1e-08

    (the 5e-8 is CAE's own round-tripping: it wrote 89.9999992730282 degrees.)

    The wrong order agrees with the right one whenever the translation is
    parallel to the rotation axis, which covers most real assemblies — so it
    would have shipped, looked right in every case anyone checked, and put a
    part in the wrong place the first time someone rotated about an offset
    axis. See tests/test_parse_inp_assembly.py.
    """
    if translate is None and rotate is None:
        return dict(local_nodes)
    placed = {}
    for label, xyz in local_nodes.items():
        point = xyz
        if translate is not None:
            point = (point[0] + translate[0], point[1] + translate[1],
                     point[2] + translate[2])
        if rotate is not None:
            point = _rotate_point(point, rotate[0:3], rotate[3:6], rotate[6])
        placed[label] = point
    return placed


def parse_inp(inp_path):
    """Return {'parts': [{name, family, element_type, is_beam, nodes:flat,
    tris:flat or lines:flat, node_count, tri_count or line_count, color}, ...],
    'bbox': [[minxyz],[maxxyz]], 'source': path}."""
    lines = Path(inp_path).read_text(encoding="utf-8", errors="replace").splitlines()
    model_nodes = {}    # label -> (x,y,z), for flat decks with no *Part blocks
    model_elems = []    # [(elset_name, el_type, [(id, [conn])])]
    part_defs = {}      # part name -> {'nodes': {...}, 'elements': [...]}
    instances = []      # [{'name','part','translate','rotate'}]
    problems = []       # plain-Chinese, user-facing; parse_ok carries fatality
    inline_mesh_instances = []
    current_part = None

    i = 0
    while i < len(lines):
        raw = lines[i].strip()
        if not raw or raw.startswith("**") or not raw.startswith("*"):
            i += 1
            continue
        kw, params = _kw_and_params(raw)

        if kw == "PART":
            name = params.get("NAME", "Part-%d" % (len(part_defs) + 1))
            current_part = part_defs.setdefault(name, {"nodes": {}, "elements": []})
            i += 1
            continue

        if kw == "END PART":
            current_part = None
            i += 1
            continue

        if kw == "INSTANCE":
            translate, rotate, nxt, inline = _read_instance_placement(lines, i + 1)
            name = params.get("NAME", "?")
            if inline:
                inline_mesh_instances.append(name)
            instances.append({
                "name": name,
                "part": params.get("PART", ""),
                "translate": translate,
                "rotate": rotate,
            })
            i = nxt
            continue

        if kw == "NODE":
            target = current_part["nodes"] if current_part is not None else model_nodes
            i = _read_nodes(lines, i, target) + 1
            continue

        if kw == "ELEMENT":
            target = current_part["elements"] if current_part is not None else model_elems
            i = _read_elements(lines, i, params, target) + 1
            continue

        i += 1

    if part_defs:
        return _render_assembly(part_defs, instances, inline_mesh_instances,
                                problems, inp_path)
    return _render_flat(model_nodes, model_elems, problems, inp_path)


def _render_flat(all_nodes, elem_blocks, problems, inp_path):
    """A model-level deck: one preview part per `*ELEMENT ... ELSET=` block."""
    blocks = [(name, el_type, rows, all_nodes, "", {})
              for name, el_type, rows in elem_blocks]
    parts, used_node_labels, _label_maps = _render_blocks(blocks, problems)
    fatal = []
    if not parts:
        fatal.append(
            "没有解析出任何可渲染的部件"
            + ("：" + "；".join(problems) if problems else
               "（文件里没有 *NODE/*ELEMENT 数据）"))
    return _assemble_result(parts, used_node_labels, fatal + problems, not fatal,
                            str(inp_path))


def _render_assembly(part_defs, instances, inline_mesh_instances, problems, inp_path):
    """A *Part / *Instance deck: one preview part per INSTANCE, positioned.

    Per instance, not per part: a part instanced three times is three bodies in
    three places, and node labels are local to the part, so two instances of it
    both number from 1.
    """
    fatal = []
    if inline_mesh_instances:
        # An orphan mesh defined inside *Instance is numbered in assembly space
        # already, and mixing it with part-local numbering would silently pick
        # the wrong nodes. Not seen from this repo's generator; refuse rather
        # than half-support it.
        fatal.append(
            "*Instance（%s）自带 *Node/*Element（孤立网格），本解析器只支持引用"
            "*Part 的实例——拒绝预览，以免取错节点号"
            % ", ".join(sorted(set(inline_mesh_instances))))
    if not instances:
        fatal.append(
            "这个 .inp 有 %d 个 *Part 块却没有 *Instance，无法知道它们摆在哪里"
            "——拒绝预览" % len(part_defs))

    blocks = []
    missing = []
    for inst in instances:
        definition = part_defs.get(inst["part"])
        if definition is None:
            missing.append("%s(part=%s)" % (inst["name"], inst["part"] or "?"))
            continue
        placed = place_nodes(definition["nodes"], inst["translate"], inst["rotate"])
        many = len(definition["elements"]) > 1
        for elset_name, el_type, rows in definition["elements"]:
            display = "%s:%s" % (inst["name"], elset_name) if many else inst["name"]
            blocks.append((display, el_type, rows, placed, inst["name"],
                           {"instance": inst["name"], "part": inst["part"]}))
    if missing:
        fatal.append(
            "*Instance（%s）引用了文件里不存在的 *Part——拒绝预览" % ", ".join(missing))

    if fatal:
        return _assemble_result([], set(), fatal + problems, False, str(inp_path))

    parts, used_node_labels, _label_maps = _render_blocks(blocks, problems)
    if not parts:
        fatal.append(
            "没有解析出任何可渲染的部件"
            + ("：" + "；".join(problems) if problems else "（*Part 块里没有单元）"))
    return _assemble_result(parts, used_node_labels, fatal + problems, not fatal,
                            str(inp_path))


def _render_blocks(blocks, problems):
    """Turn (name, el_type, rows, node_map, scope, extra) into preview parts.

    Shared by the .inp reader and the CAE-side instance dump so the two
    producers of this format cannot drift in how they count or triangulate.

    ``scope`` namespaces node labels. It matters: two instances of the same
    part both number their nodes from 1, so a global label set would report
    a two-plate assembly as having half the nodes it has.

    The third return value is the index->label table of each emitted part, in
    the same order as ``parts``. build_surface renumbers nodes into a compact
    per-part order and only that order can index ``part['nodes']``, so anything
    that arrives keyed by LABEL — a named surface, a named set — needs this
    table to be drawable. Returned rather than stored on the part because the
    front end already renders parts[] and that shape is not to move.
    """
    parts = []
    label_maps = []
    # Nodes are shared between parts (a beam-column joint node belongs to both
    # ELSETs), so the model total must be a set union, not a sum of per-part
    # counts — summing double-counts every shared node.
    used_node_labels = set()

    for name, el_type, rows, node_map, scope, extra in blocks:
        family = _elem_family(el_type)
        if not rows:
            continue
        if family == "unknown":
            # Named, not silent: a preview missing the rigid die or the
            # connectors reads as "the model has none" unless it says so.
            problems.append(
                "已忽略无法预览的单元块：ELSET=%s（TYPE=%s，该单元族不支持预览）"
                % (name, el_type))
            continue
        if len(rows) > MAX_ELEMENTS_PER_PART:
            problems.append(
                "ELSET=%s 超过 %d 个单元，预览只画了前一部分"
                % (name, MAX_ELEMENTS_PER_PART))

        if family == "line":
            # Emit as line segments: pairs of node labels flattened to coords.
            used_labels = []
            label_to_idx = {}
            flat_nodes = []
            flat_lines = []
            for _eid, conn in rows:
                if len(conn) < 2:
                    continue
                for lbl in conn[:2]:
                    if lbl not in label_to_idx:
                        if lbl not in node_map:
                            break
                        xyz = node_map[lbl]
                        label_to_idx[lbl] = len(used_labels)
                        used_labels.append(lbl)
                        flat_nodes.extend([xyz[0], xyz[1], xyz[2]])
                if all(lbl in label_to_idx for lbl in conn[:2]):
                    flat_lines.extend([label_to_idx[conn[0]], label_to_idx[conn[1]]])
            if not flat_lines:
                continue
            used_node_labels.update((scope, lbl) for lbl in used_labels)
            part = {
                "name": name,
                "family": "line",
                "element_type": el_type,
                "nodes": flat_nodes,
                "lines": flat_lines,
                "node_count": len(used_labels),
                "line_count": len(flat_lines) // 2,
                # One beam element renders as exactly one segment, so these
                # coincide here — but keep them distinct so the UI can label
                # "elements" and "render primitives" without conflating them.
                "element_count": len(flat_lines) // 2,
                "color": _classify_part_color(name),
            }
            part.update(extra)
            parts.append(part)
            label_maps.append(used_labels)
            continue

        # surface: use build_surface() to extract exterior triangles.
        # Restrict node_coords to labels we can see (avoid KeyError on
        # unresolved refs from a broken .inp).
        part_nodes = {}
        elements = []
        for _eid, conn in rows:
            if all(lbl in node_map for lbl in conn):
                elements.append((el_type, tuple(conn)))
                for lbl in conn:
                    part_nodes[lbl] = node_map[lbl]
        dropped = len(rows) - len(elements)
        if dropped:
            problems.append(
                "ELSET=%s：%d/%d 个单元引用了不存在的节点号，已跳过（部分渲染）"
                % (name, dropped, len(rows)))
        if not elements:
            continue
        try:
            flat_nodes, flat_tris, _labels = build_surface(part_nodes, elements)
        except Exception as exc:
            # The old bare continue here is what turned a parse bug into an
            # empty-but-successful preview. The reason must survive.
            problems.append(
                "ELSET=%s（TYPE=%s）外表面提取失败：%s: %s"
                % (name, el_type, type(exc).__name__, exc))
            continue
        if not flat_nodes:
            continue
        used_node_labels.update((scope, lbl) for lbl in part_nodes)
        part = {
            "name": name,
            "family": "surface",
            "element_type": el_type,
            "nodes": flat_nodes,
            "tris": flat_tris,
            "node_count": len(_labels),
            # tri_count is a RENDER count (exterior surface triangulation);
            # element_count is how many real FE elements this ELSET holds. For a
            # solid these differ by an order of magnitude — never show tris to
            # the user as if they were elements.
            "tri_count": len(flat_tris) // 3,
            "element_count": len(elements),
            "color": _classify_part_color(name),
        }
        part.update(extra)
        parts.append(part)
        label_maps.append(_labels)

    return parts, used_node_labels, label_maps


def _assemble_result(parts, used_node_labels, problems, parse_ok, source,
                     assembly=None):
    if parts:
        all_xs = [c for p in parts for c in p["nodes"][0::3]]
        all_ys = [c for p in parts for c in p["nodes"][1::3]]
        all_zs = [c for p in parts for c in p["nodes"][2::3]]
    else:
        all_xs = all_ys = all_zs = []
    if all_xs:
        bbox = [[min(all_xs), min(all_ys), min(all_zs)],
                [max(all_xs), max(all_ys), max(all_zs)]]
    else:
        bbox = [[0, 0, 0], [0, 0, 0]]

    return {
        # /3-assembly adds `assembly` alongside the untouched parts[]. It is
        # null for a payload built from an .inp (no CAE session ever saw it)
        # and for a CAE dump written before this key existed; the schema says
        # the field is there, not that it is populated.
        "format": "abaqus-agent-mesh/3-assembly",
        "source": source,
        "parse_ok": parse_ok,
        "problems": problems,
        "parts": parts,
        "assembly": assembly,
        "bbox": bbox,
        "part_count": len(parts),
        # Model totals, not sums of per-part figures: nodes are de-duplicated
        # across ELSETs, and elements are real FE elements rather than the
        # triangles we happen to draw.
        "node_count": len(used_node_labels),
        "element_count": sum(p.get("element_count", 0) for p in parts),
        # Render budget, kept separate so the viewport can reason about cost.
        "render_triangle_count": sum(p.get("tri_count", 0) for p in parts),
        "render_line_count": sum(p.get("line_count", 0) for p in parts),
    }


def parts_from_instance_dump(raw, source="preview_raw.json"):
    """Build the same preview payload from CAE's own assembly-space dump.

    This is the exact path for a generated v2 assembly. CAE is asked where each
    instance's nodes actually are rather than the transform being recomputed
    from the *Instance data lines, because the order a translation and a
    rotation compose in is precisely the kind of detail that yields a
    confident, wrong picture. The .inp reader learns the transform anyway — a
    custom_inp deck arrives with no CAE session — and is checked against this.

    Two dump shapes are read. Both carry `instances`; the newer one
    (`assembly_dump`) also carries the named surfaces and sets, the
    interactions and conditions that use them, and each part's section — the
    model tree and the contact overlay, none of which is derivable from
    triangles. The older one is still on disk in every run directory built
    before that key existed, and comes back with `assembly: null`.
    """
    problems = []
    instances = raw.get("instances") or []
    if raw.get("truncated"):
        problems.append(
            "装配单元数超过预览上限 %s，已放弃 CAE 侧导出（不做截断——只画一半"
            "又不说，比不画更糟）" % raw.get("element_cap", "?"))
    if not instances:
        # The tree still gets its names: a truncated dump has no mesh to draw
        # but every surface, interaction and condition in it is still true.
        return _assemble_result([], set(), problems or ["CAE 侧预览导出为空"],
                                False, source, _assembly_overlay(raw, [], [], {}))

    blocks = []
    # How many nodes each block really has, keyed the way parts[] can be looked
    # up again. It cannot be taken from parts[]: that carries a RENDER figure,
    # because build_surface keeps only the nodes an exterior CORNER-node
    # triangle touches. Measured on the cached preview_raw.json of the runs in
    # this repo — two_plate_tie C3D20R 498 of 2117, plate_hole_v2 C3D20R 2174
    # of 7457, block_friction_slide C3D8I 274 of 351 — so a tree row taking it
    # from there would report a quarter of the nodes beside a true element
    # count. In all nine of those blocks the labels the elements reference are
    # exactly the instance's node list, which is why counting them is the
    # instance's own figure and still splits correctly for a mixed-type mesh.
    node_totals = {}
    for inst in instances:
        name = str(inst.get("name") or "?")
        node_map = {int(lbl): (float(x), float(y), float(z))
                    for lbl, x, y, z in inst.get("nodes", [])}
        # One instance can hold more than one element type (a swept mesh drops
        # wedges in alongside the hexes), and build_surface needs them grouped.
        by_type = {}
        for index, (el_type, conn) in enumerate(inst.get("elements", [])):
            by_type.setdefault(str(el_type), []).append((index, list(conn)))
        for el_type, rows in sorted(by_type.items()):
            display = name if len(by_type) == 1 else "%s:%s" % (name, el_type)
            node_totals[(name, el_type)] = len(
                set(label for _index, conn in rows for label in conn))
            blocks.append((display, el_type, rows, node_map, name,
                           {"instance": name, "part": str(inst.get("part") or "")}))

    parts, used, label_maps = _render_blocks(blocks, problems)
    return _assemble_result(parts, used, problems, bool(parts), source,
                            _assembly_overlay(raw, parts, label_maps,
                                              node_totals))


def _assembly_overlay(raw, parts, label_maps, node_totals):
    """The model tree and the contact overlay, from CAE's own assembly dump.

    Returns None for a dump written before the assembly section existed —
    cached preview_raw.json files from earlier runs are still on disk and are
    still regenerated into preview_mesh.json without CAE. None says "this dump
    never carried it"; an empty list would say "this model has none".

    Facets are neither dumped by CAE nor recomputed from an element face table
    here. They are selected out of the exterior triangulation the part already
    carries: a triangle belongs to a surface when all three of its nodes are on
    that surface. Two reasons. The face tables live in exactly one place
    (post/export_odb_mesh.element_faces) and a second copy inside the CAE-side
    string would drift from it unwatched. And build_surface renumbers nodes into
    a compact per-part order, so facets built anywhere else would have to be
    remapped into it before the viewport could draw them anyway.

    What that costs: the test is node membership, so a triangle that is not on
    the surface but all three of whose nodes are — possible where a surface
    wraps a sharp edge — is drawn as part of it. This is a highlight over a
    preview; the region the solver gets is the one CAE built, not this one.
    """
    if not raw.get("assembly_dump"):
        return None

    degraded = [str(entry) for entry in (raw.get("degraded") or [])]
    by_instance = {}
    for index, part in enumerate(parts):
        by_instance.setdefault(str(part.get("instance") or ""), []).append(index)
    if not parts:
        # One line, not one per region: with no mesh at all (a truncated dump)
        # every surface would otherwise repeat the same complaint.
        degraded.append("这次预览没有可渲染的网格，模型树只有名字，点开不会高亮")

    surfaces = [_overlay_region(entry, parts, label_maps, by_instance, degraded,
                                "面", True)
                for entry in raw.get("surfaces") or []]
    sets = [_overlay_region(entry, parts, label_maps, by_instance, degraded,
                            "集合", False)
            for entry in raw.get("sets") or []]
    known_surfaces = set(item["name"] for item in surfaces)
    known_sets = set(item["name"] for item in sets)
    _report_partial_highlights(surfaces + sets, degraded)
    return {
        "surfaces": surfaces,
        "sets": sets,
        "pick_faces": _overlay_pick_faces(raw, parts, label_maps, by_instance,
                                          degraded),
        "interactions": _overlay_interactions(raw, known_surfaces, degraded),
        "conditions": _overlay_conditions(raw, known_surfaces, known_sets,
                                          degraded),
        "counts": _overlay_counts(raw, parts, degraded, node_totals),
        "degraded": degraded,
    }


def _overlay_pick_faces(raw, parts, label_maps, by_instance, degraded):
    """CAE's geometric faces as clickable regions of the preview mesh.

    Each row pairs the measurements a `face@box=` selector is generated from
    (the assembly-space bbox CAE reported, radius/normal where the face has
    one) with the exterior triangles that lie on the face — triangle INDICES
    into the part's tris array, because that is the number a raycast hit
    carries (hit.faceIndex), so the viewport's lookup is an array read, not a
    vertex-triple comparison. Same membership test as `_overlay_facets`, same
    honest gap: a triangle whose three corners all sit on the face counts as
    on it.

    Faces the dump shipped without a bbox or without nodes are DROPPED with
    one aggregate line: a face the generator cannot write a selector for must
    not be clickable, or the click would have to answer with a guess.
    """
    out = []
    unusable = 0
    for inst in raw.get("instances") or []:
        iname = str(inst.get("name") or "")
        targets = by_instance.get(iname) or []
        dropped = int(inst.get("faces_dropped") or 0)
        if dropped:
            degraded.append(
                "实例 %s 有 %d 个几何面没进预览（超上限或读不出节点），"
                "这些面在 3D 里点不出来" % (iname, dropped))
        for entry in inst.get("faces") or []:
            bbox = entry.get("bbox")
            labels = set(int(label) for label in entry.get("node_labels") or [])
            if not bbox or not labels:
                unusable += 1
                continue
            row = {
                "instance": iname,
                "face": int(entry.get("face") or 0),
                "bbox": [[float(v) for v in bbox[0]],
                         [float(v) for v in bbox[1]]],
                "node_count": int(entry.get("node_total") or len(labels)),
                "capped": bool(entry.get("capped")),
                "parts": [],
            }
            for key in ("radius", "area"):
                if entry.get(key) is not None:
                    row[key] = float(entry[key])
            if entry.get("normal") is not None:
                row["normal"] = [float(v) for v in entry["normal"]]
            for index in targets:
                tris = parts[index].get("tris") or []
                found, capped = _overlay_tri_indices(labels, tris,
                                                     label_maps[index])
                if capped:
                    row["capped"] = True
                if found:
                    row["parts"].append({"part": index, "tris": found})
            if row["parts"]:
                out.append(row)
            else:
                unusable += 1
    if unusable:
        degraded.append(
            "%d 个几何面在预览网格里找不到自己的三角形（或没带包围盒），"
            "3D 里点不中它们，选择器仍可手写" % unusable)
    return out


def _overlay_tri_indices(labels, tris, label_map):
    """Triangle indices (tris位置//3) whose three corners all lie on a face."""
    found = []
    for i in range(0, len(tris) - 2, 3):
        if (label_map[tris[i]] in labels and label_map[tris[i + 1]] in labels
                and label_map[tris[i + 2]] in labels):
            if len(found) >= MAX_FACETS_PER_SURFACE:
                return found, True
            found.append(i // 3)
    return found, False


def _report_partial_highlights(regions, degraded):
    """A highlight that covers part of its region must not read as all of it.

    Structural, not an error: the preview mesh is an exterior CORNER-node
    triangulation, so a quadratic element's midside nodes and a solid's
    interior nodes are not in it and cannot be lit. Measured on the cached
    dumps in this repo, that leaves 23.5% of the nodes drawable on the C3D20R
    two_plate_tie mesh and 29.2% on plate_hole_v2 — so a set reported as 2117
    nodes lights 498 of them, and without this line the missing three quarters
    read as a selector that picked up less than the spec asked for.

    One line for all of them, not one each: on a quadratic mesh every region is
    partial, and 200 identical complaints are read as noise and then ignored.
    `drawn_nodes` on each region carries the per-region figure.
    """
    partial = [item["name"] for item in regions
               if item["parts"] and item["drawn_nodes"] < item["node_count"]]
    if not partial:
        return
    shown = "、".join(partial[:5])
    if len(partial) > 5:
        shown += " 等 %d 个" % len(partial)
    degraded.append(
        "%d 个区域的高亮盖不住它全部的节点：预览网格只画外表面，二次单元的"
        "中间节点和实体内部的节点都不在里面，点不亮。每个区域的 drawn_nodes "
        "是真正画得出来的数量（%s）" % (len(partial), shown))


def _overlay_region(entry, parts, label_maps, by_instance, degraded, what,
                    as_facets):
    """One named surface or set, placed on the parts the viewport will draw."""
    name = str(entry.get("name") or "?")
    instance = str(entry.get("instance") or "")
    labels = set(int(label) for label in entry.get("node_labels") or [])
    out = {
        "name": name,
        "instance": instance,
        "node_count": int(entry.get("node_total") or len(labels)),
        # Carried from the dump: the node list itself may already be a prefix,
        # in which case the highlight is partial however it is drawn.
        "capped": bool(entry.get("capped")),
        # How many of those nodes the viewport can actually light. Below
        # `node_count` whenever the region holds a node the preview mesh does
        # not carry, which on a quadratic mesh is every midside node.
        "drawn_nodes": 0,
        "parts": [],
    }
    targets = by_instance.get(instance) if instance else None
    if not targets:
        if instance and parts:
            degraded.append(
                "%s %s 在实例 %s 上，但预览里没有这个实例的网格，模型树里点不开它"
                % (what, name, instance))
        return out

    # Counted as LABELS rather than as a sum of the per-part lists: one instance
    # split across two element-type blocks carries a shared node in both node
    # arrays, and summing would put drawn_nodes above node_count.
    covered = set()
    for index in targets:
        part = parts[index]
        if as_facets:
            found, capped = _overlay_facets(labels, part.get("tris") or [],
                                            label_maps[index])
            if capped:
                out["capped"] = True
                degraded.append(
                    "%s %s 的三角面超过 %d，预览只画了前一部分"
                    % (what, name, MAX_FACETS_PER_SURFACE))
            if found:
                out["parts"].append({"part": index, "facets": found,
                                     "facet_count": len(found) // 3})
        else:
            found = [position for position, label
                     in enumerate(label_maps[index]) if label in labels]
            if found:
                out["parts"].append({"part": index, "nodes": found})
        covered.update(label_maps[index][position] for position in found)
    out["drawn_nodes"] = len(covered)
    if not out["parts"]:
        degraded.append(
            "%s %s 的节点在实例 %s 的预览网格里一个都没对上，这一项不高亮"
            % (what, name, instance))
    return out


def _overlay_facets(labels, tris, label_map):
    """Which of a part's exterior triangles lie entirely on a named surface."""
    facets = []
    for i in range(0, len(tris) - 2, 3):
        first, second, third = tris[i], tris[i + 1], tris[i + 2]
        if (label_map[first] in labels and label_map[second] in labels
                and label_map[third] in labels):
            if len(facets) >= 3 * MAX_FACETS_PER_SURFACE:
                return facets, True
            facets.extend((first, second, third))
    return facets, False


def _overlay_interactions(raw, known_surfaces, degraded):
    """Tree rows for what joins two bodies, with the bound CAE measured."""
    rows = []
    for entry in raw.get("interactions") or []:
        name = str(entry.get("name") or "?")
        kept = []
        for surface in entry.get("surfaces") or []:
            if str(surface) in known_surfaces:
                kept.append(str(surface))
            else:
                degraded.append(
                    "交互 %s 用到的面 %s 不在预览里，这一行点不出接触面"
                    % (name, surface))
        rows.append({
            "name": name,
            "kind": str(entry.get("kind") or ""),
            "call": str(entry.get("call") or ""),
            "surfaces": kept,
            # An UPPER BOUND on the separation, not the separation. _surface_gap
            # measures node-to-node while Abaqus ties node-to-SURFACE, so a
            # secondary node landing mid-face on a coarser main surface reads as
            # far away when it is on it. bearing_block's BoreTie ties
            # Housing:face@r=12 to Bushing:face@r=12 -- the same cylinder, bonded
            # under a position tolerance of 0.05 -- and this number comes back
            # 2.389, because the two sides carry 418 and 1628 nodes. So it may
            # not be shown as 间隙 without saying it is an upper bound; a tie
            # that bound would read as one that did not.
            #
            # It is still the number worth carrying, because the error is one
            # way: it can over-report and never under-report, and a pair wider
            # than its position tolerance is created without complaint and
            # solves to completion holding nothing. None means it was not
            # measured -- `degraded` says why -- and does not mean zero.
            "gap": entry.get("gap"),
            "gap_nodes": entry.get("gap_nodes"),
        })
    return rows


def _overlay_conditions(raw, known_surfaces, known_sets, degraded):
    """Tree rows for BCs, loads and fields: which call, which step, which region."""
    rows = []
    for entry in raw.get("conditions") or []:
        name = str(entry.get("name") or "?")
        row = {"name": name, "call": str(entry.get("call") or ""),
               "step": entry.get("step"), "sets": [], "surfaces": []}
        for key, known in (("sets", known_sets), ("surfaces", known_surfaces)):
            for region in entry.get(key) or []:
                if str(region) in known:
                    row[key].append(str(region))
                else:
                    degraded.append(
                        "条件 %s 用到的区域 %s 不在预览里，这一行点不出作用区域"
                        % (name, region))
        rows.append(row)
    return rows


def _overlay_counts(raw, parts, degraded, node_totals):
    """Per-part figures the tree shows without asking for the model again.

    `nodes` and `elements` are both the model's own figures, which is the whole
    point of the row: they sit next to each other and a reader compares them.
    `parts[]['node_count']` looks like the first of the two and is not — it
    counts the nodes the exterior corner-node triangulation happens to touch,
    which on the C3D20R decks here is 498 of 2117. Reported from there it would
    have read as 498 nodes carrying 320 elements, and the model total in the
    same payload (4234) would not have been the sum of its parts.
    """
    by_instance = {}
    for entry in raw.get("sections") or []:
        by_instance[str(entry.get("instance") or "")] = entry
    counts = []
    for index, part in enumerate(parts):
        name = str(part.get("name") or "?")
        instance = str(part.get("instance") or "")
        element_type = str(part.get("element_type") or "")
        found = by_instance.get(instance) or {}
        sections = [str(item) for item in found.get("sections") or []]
        materials = [str(item) for item in found.get("materials") or []]
        nodes = node_totals.get((instance, element_type))
        if nodes is None:
            nodes = int(part.get("node_count") or 0)
            degraded.append(
                "部件 %s 的节点数用的是预览网格里的 %d 个（只有外表面的角节点），"
                "没拿到这个实例真正的节点数" % (name, nodes))
        counts.append({
            "part": index,
            "name": name,
            "instance": instance,
            "abaqus_part": str(part.get("part") or found.get("part") or ""),
            # Real FE figures. The triangles are a render count and are
            # deliberately not repeated here as if they were the same thing.
            "nodes": int(nodes),
            "elements": int(part.get("element_count") or 0),
            "element_type": element_type,
            "sections": sections,
            "materials": materials,
        })
        if not sections:
            degraded.append(
                "部件 %s（实例 %s）没有拿到截面名，模型树只显示网格数量，不显示截面和材料"
                % (name, instance or "?"))
        elif not materials:
            degraded.append(
                "部件 %s 的截面 %s 没有报出材料名（连接器/复合材料截面就是这样），"
                "模型树只显示截面" % (name, "、".join(sections)))
    return counts


def write_parts_mesh(inp_path, out_path):
    """Convenience: parse inp -> write JSON that WBViewport can consume."""
    data = parse_inp(inp_path)
    Path(out_path).write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")
    return data


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("usage: parse_inp.py <inp> [out.json]")
        sys.exit(1)
    inp = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else inp + ".parts.json"
    data = write_parts_mesh(inp, out)
    print("PARTS_WRITTEN %s parts=%d nodes=%d elems=%d"
          % (out, data["part_count"], data["node_count"], data["element_count"]))
