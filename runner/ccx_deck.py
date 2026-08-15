"""
ccx_deck.py
-----------
Write a flat CalculiX input deck from a Problem Spec, and translate an
Abaqus/CAE assembly deck into the flat form CalculiX can read.

Two entry points:

  ``write_ccx_deck(spec, workdir)``  — generated path (geometry.type =
      cantilever_block): mesh via runner/ccx_mesh.py, cards written here.

  ``translate_abaqus_inp(text)``     — custom_inp path: an Abaqus/CAE deck is
      assembly-style (``*Part`` / ``*Assembly`` / ``*Instance``) and CalculiX
      cannot read it. ccx treats those wrappers as *uninterpretable cards* and
      only WARNS, so the sets end up defined WITHOUT the instance prefix while
      every reference still carries it — the run then dies on
      "*ERROR reading *BOUNDARY: node set PART-1-1.FIXED_END". Prefix stripping
      is therefore mandatory, not cosmetic.

Everything here is pure text: no subprocess, no solver, fully unit-testable.
"""

from __future__ import annotations

import re
from pathlib import Path

from runner.ccx_mesh import StructuredMesh, build_mesh

# Cards Abaqus/CAE emits that carry no meaning for CalculiX. ccx would only warn
# about them, but a warning-free log is what lets a REAL warning stand out.
_DROP_CARDS_SIMPLE = (
    "*preprint", "*part", "*end part", "*assembly", "*end assembly",
    "*instance", "*end instance", "*restart",
)
# Cards whose *data lines* must go too (they carry an output variable list).
_DROP_CARDS_WITH_DATA = (
    "*output", "*node output", "*element output", "*contact output",
    "*node print", "*el print", "*node file", "*el file", "*energy print",
)

_ENCASTRE_DOFS = "1, 3"   # solid elements have 3 translational DOF only
_PINNED_DOFS = "1, 3"

_INSTANCE_PREFIX_RE = re.compile(r"\b([A-Za-z_][\w\-]*)\.([A-Za-z_][\w\-]*)\b")


def _is_keyword(line: str) -> bool:
    return line.lstrip().startswith("*") and not line.lstrip().startswith("**")


def _card_name(line: str) -> str:
    """Lower-cased keyword name of a card line, without parameters."""
    return line.lstrip().split(",", 1)[0].strip().lower()


def _strip_instance_prefixes(line: str, instances: set[str]) -> str:
    """Turn ``Part-1-1.FIXED_END`` into ``FIXED_END`` for known instance names."""
    if not instances or "." not in line:
        return line

    def _sub(match: re.Match) -> str:
        return match.group(2) if match.group(1).lower() in instances else match.group(0)

    return _INSTANCE_PREFIX_RE.sub(_sub, line)


def _collect_instance_names(lines: list[str]) -> set[str]:
    names: set[str] = set()
    for line in lines:
        if _is_keyword(line) and _card_name(line) == "*instance":
            for param in line.split(",")[1:]:
                key, _, value = param.partition("=")
                if key.strip().lower() == "name":
                    names.add(value.strip().lower())
    return names


def translate_abaqus_inp(inp_text: str) -> tuple[str, list[str]]:
    """Flatten an Abaqus/CAE deck for CalculiX.

    Returns ``(flat_text, notes)`` where notes are plain-language descriptions
    of every rewrite, so the console can show the user what changed rather than
    silently handing a different model to a different solver.
    """
    lines = inp_text.splitlines()
    instances = _collect_instance_names(lines)
    notes: list[str] = []
    out: list[str] = []

    dropping_data = False
    in_boundary = False
    dropped_wrappers = 0
    dropped_output = 0
    stripped_refs = 0
    encastre = 0

    for raw in lines:
        line = raw.rstrip()
        stripped = line.strip()

        if not stripped:
            continue
        if stripped.startswith("**"):
            continue

        if _is_keyword(line):
            dropping_data = False
            name = _card_name(line)
            in_boundary = name == "*boundary"

            if name in _DROP_CARDS_SIMPLE:
                dropped_wrappers += 1
                continue
            if name in _DROP_CARDS_WITH_DATA:
                dropped_output += 1
                dropping_data = True
                continue

            # ", internal" and "name=" are Abaqus bookkeeping; ccx warns on them.
            if name in ("*elset", "*nset"):
                parts = [p for p in line.split(",") if p.strip().lower() != "internal"]
                line = ",".join(parts)
            if name == "*step":
                parts = [
                    p for p in line.split(",")
                    if not p.strip().lower().startswith("name=")
                ]
                line = ",".join(parts)

            new_line = _strip_instance_prefixes(line, instances)
            if new_line != line:
                stripped_refs += 1
            out.append(new_line)
            continue

        if dropping_data:
            continue

        new_line = _strip_instance_prefixes(line, instances)
        if new_line != line:
            stripped_refs += 1
        line = new_line

        if in_boundary:
            fields = [f.strip() for f in line.split(",")]
            if len(fields) == 2 and fields[1].upper() == "ENCASTRE":
                line = "%s, %s" % (fields[0], _ENCASTRE_DOFS)
                encastre += 1
            elif len(fields) == 2 and fields[1].upper() == "PINNED":
                line = "%s, %s" % (fields[0], _PINNED_DOFS)
                encastre += 1

        out.append(line)

    if dropped_wrappers:
        notes.append(
            "已展平 Abaqus 装配结构（删除 %d 行 *Part/*Assembly/*Instance 包装卡）：CalculiX 不认识这些卡"
            % dropped_wrappers
        )
    if stripped_refs:
        notes.append(
            "已去掉 %d 处 instance 前缀（如 Part-1-1.FIXED_END → FIXED_END）：CalculiX 定义的集合名不带前缀"
            % stripped_refs
        )
    if encastre:
        notes.append(
            "已把 %d 条 ENCASTRE/PINNED 约束改写成显式自由度 (1, 3)：CalculiX 没有这两个命名边界类型"
            % encastre
        )
    if dropped_output:
        notes.append(
            "已删除 %d 条 Abaqus *Output 输出请求，改用 CalculiX 的 *NODE PRINT/*EL FILE"
            % dropped_output
        )
    return "\n".join(out) + "\n", notes


# ---------------------------------------------------------------------------
# Result requests
# ---------------------------------------------------------------------------

_NODE_SET_ALIASES = {
    "fixed_face": "FIXED_END",
    "load_face": "LOAD_END",
    "tip": "TIP_NODES",
    "tip_center": "TIP_NODES",
    "top_face": "LOAD_END",
}
_ELEMENT_SET_ALIASES = {
    "fixed_face": "FIXED_END",
    "hole_edge": "HOLE_EDGE",
    "hole_edge_set": "HOLE_EDGE",
    "load_face": "LOAD_END",
    "top_face": "LOAD_END",
    "whole_model": "ALL",
}


def resolve_set_name(location: str | None, kind: str) -> str | None:
    """Map a spec ``location`` onto a deck set name (same aliases as the ODB path)."""
    if not location:
        return None
    raw = str(location).split(":", 1)[-1].strip()
    aliases = _NODE_SET_ALIASES if kind == "node" else _ELEMENT_SET_ALIASES
    return (aliases.get(raw.lower()) or raw).upper()


def result_request_block(kpi_spec: list[dict]) -> str:
    """CalculiX-native output requests derived from the KPI recipe.

    Without this the .dat comes back 0 bytes: ccx ignores Abaqus ``*Output``
    cards entirely, so the deck must ask for results in its own dialect.
    """
    node_print: dict[str, set[str]] = {}
    want_stress_file = False

    for kpi in kpi_spec:
        kind = kpi.get("type")
        if kind in ("nodal_displacement", "field_min"):
            name = resolve_set_name(kpi.get("location"), "node") or "ALL"
            node_print.setdefault(name, set()).add("U")
        elif kind == "reaction_force_max":
            name = resolve_set_name(kpi.get("location"), "node") or "ALL"
            node_print.setdefault(name, set()).add("RF")
        elif kind in ("field_max", "derived_stress_concentration"):
            want_stress_file = True

    lines: list[str] = []
    for set_name in sorted(node_print):
        lines.append("*NODE PRINT, NSET=%s" % set_name)
        lines.append(", ".join(sorted(node_print[set_name])))
    # .frd always carries U so the 3D result view has something to show.
    lines.append("*NODE FILE")
    lines.append("U, RF")
    if want_stress_file:
        lines.append("*EL FILE")
        lines.append("S")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Generated deck
# ---------------------------------------------------------------------------

def _fmt(value: float) -> str:
    return repr(float(value))


def _mesh_cards(mesh: StructuredMesh) -> list[str]:
    lines = ["*NODE, NSET=NALL"]
    for nid, x, y, z in mesh.nodes:
        lines.append("%d, %s, %s, %s" % (nid, _fmt(x), _fmt(y), _fmt(z)))
    lines.append("*ELEMENT, TYPE=%s, ELSET=EALL" % mesh.element_type)
    for eid, conn in mesh.elements:
        # ccx tolerates long lines but Abaqus-style 16-per-line wrapping keeps
        # the deck readable and diffable against a CAE deck.
        head = "%d, %s" % (eid, ", ".join(str(n) for n in conn[:15]))
        if len(conn) > 15:
            lines.append(head + ",")
            lines.append(", ".join(str(n) for n in conn[15:]))
        else:
            lines.append(head)
    for name in sorted(mesh.node_sets):
        lines.append("*NSET, NSET=%s" % name)
        lines.extend(_wrap_ids(mesh.node_sets[name]))
    for name in sorted(mesh.element_sets):
        lines.append("*ELSET, ELSET=%s" % name)
        lines.extend(_wrap_ids(mesh.element_sets[name]))
    return lines


def _wrap_ids(ids: tuple[int, ...], per_line: int = 8) -> list[str]:
    out = []
    for start in range(0, len(ids), per_line):
        out.append(", ".join(str(i) for i in ids[start:start + per_line]) + ",")
    return out


def build_ccx_deck(spec: dict, mesh: StructuredMesh, kpi_spec: list[dict]) -> str:
    """Assemble a complete flat CalculiX deck for a supported spec."""
    meta = spec.get("meta", {}) or {}
    mat = spec.get("material", {}) or {}
    bc = spec.get("bc_load", {}) or {}

    mat_name = str(mat.get("name", "MATERIAL")).upper()

    lines: list[str] = [
        "*HEADING",
        "%s -- generated by abaqus-agent for CalculiX (fallback backend)"
        % meta.get("model_name", "Model"),
    ]
    lines.extend(_mesh_cards(mesh))

    lines.append("*MATERIAL, NAME=%s" % mat_name)
    lines.append("*ELASTIC")
    lines.append("%s, %s" % (_fmt(mat["E"]), _fmt(mat["nu"])))
    if mat.get("density") is not None:
        lines.append("*DENSITY")
        lines.append(_fmt(mat["density"]))
    lines.append("*SOLID SECTION, ELSET=EALL, MATERIAL=%s" % mat_name)

    lines.append("*BOUNDARY")
    lines.append("FIXED_END, 1, 3")

    lines.append("*STEP")
    lines.append("*STATIC")

    load_type = bc.get("load_type")
    if load_type == "concentrated_force":
        direction = int(bc.get("direction", 2))
        lines.append("*CLOAD")
        lines.append("TIP_NODES, %d, %s" % (direction, _fmt(bc.get("value", 0.0))))
    else:  # pragma: no cover - guarded by core.backends before we get here
        raise ValueError("CalculiX 后端不支持载荷类型 %r" % (load_type,))

    lines.append(result_request_block(kpi_spec).rstrip("\n"))
    lines.append("*END STEP")
    return "\n".join(lines) + "\n"


def write_ccx_deck(
    spec: dict,
    workdir: str | Path,
    kpi_spec: list[dict],
    source_inp: str | Path | None = None,
) -> tuple[Path, list[str]]:
    """Write ``<model_name>.inp`` for CalculiX. Returns (path, translation notes)."""
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    model_name = spec.get("meta", {}).get("model_name", "Model")
    inp_path = workdir / ("%s.inp" % model_name)

    if source_inp is not None:
        raw = Path(source_inp).read_text(encoding="utf-8", errors="replace")
        flat, notes = translate_abaqus_inp(raw)
        block = result_request_block(kpi_spec)
        flat = _inject_before_end_step(flat, block)
        notes.append("已注入 CalculiX 输出请求卡（*NODE PRINT / *NODE FILE），否则 .dat 为空")
        inp_path.write_text(flat, encoding="utf-8")
        return inp_path, notes

    mesh = build_mesh(spec)
    deck = build_ccx_deck(spec, mesh, kpi_spec)
    inp_path.write_text(deck, encoding="utf-8")
    notes = [
        "网格由 abaqus-agent 的纯 Python 结构化网格器生成：%d 个 %s 单元 / %d 个节点"
        % (mesh.element_count, mesh.element_type, mesh.node_count),
    ]
    return inp_path, notes


def _inject_before_end_step(text: str, block: str) -> str:
    lines = text.splitlines()
    for idx in range(len(lines) - 1, -1, -1):
        if _is_keyword(lines[idx]) and _card_name(lines[idx]) == "*end step":
            lines[idx:idx] = block.rstrip("\n").splitlines()
            return "\n".join(lines) + "\n"
    return text.rstrip("\n") + "\n" + block
