"""
extract_kpis_ccx.py
-------------------
KPI extraction for the CalculiX fallback backend: ``.dat`` / ``.frd`` -> KPI dict.

Deliberately a SEPARATE module from post/extract_kpis.py. That one runs inside
``abaqus python`` (Python 2.7 — no f-strings, no pathlib, no annotations); this
one runs in the project venv on plain Python 3 and must never be imported by
the Abaqus-side script.

Output contract matches the ODB extractor (``{"kpis": {...}, "errors": [...]}``)
so the orchestrator, contracts and regression code need no branch — plus a
``kpi_provenance`` map, because a CalculiX number is not automatically an
Abaqus-equivalent number and the difference has to travel with the value.

Two hard-won format facts, both verified on ccx 2.23 output:

  * ``.frd`` data lines are FIXED WIDTH: 13-char record header then 12-char
    fields, with no separator. ``-2.24087E-01-2.19571E-01`` is two values, so
    ``str.split()`` silently mis-parses negative numbers.
  * The shear component ORDER differs between the two files. ``.dat`` prints
    sxx,syy,szz,sxy,sxz,syz while ``.frd`` prints SXX,SYY,SZZ,SXY,SYZ,SZX.
    Invisible in a von Mises test (all shears get squared and summed) but wrong
    for any single-component stress KPI.
"""

from __future__ import annotations

import math
import re
from pathlib import Path

from runner.ccx_deck import resolve_set_name

# .frd fixed-width layout
_FRD_HEADER_WIDTH = 13
_FRD_FIELD_WIDTH = 12

_DAT_DISP_RE = re.compile(r"displacements\s+\(.*?\)\s+for set\s+(\S+)", re.IGNORECASE)
_DAT_FORCE_RE = re.compile(r"forces\s+\(.*?\)\s+for set\s+(\S+)", re.IGNORECASE)

_COMPONENT_INDEX = {
    "U1": 0, "U2": 1, "U3": 2,
    "RF1": 0, "RF2": 1, "RF3": 2,
    "F1": 0, "F2": 1, "F3": 2,
}

# .frd stress column order (see module docstring).
_FRD_STRESS_ORDER = ("SXX", "SYY", "SZZ", "SXY", "SYZ", "SZX")
# .dat *EL PRINT stress column order — different, on purpose.
_DAT_STRESS_ORDER = ("SXX", "SYY", "SZZ", "SXY", "SXZ", "SYZ")


class CcxResultError(Exception):
    """A KPI could not be produced from the CalculiX result files."""


# ---------------------------------------------------------------------------
# .dat parsing
# ---------------------------------------------------------------------------

def dat_is_eigenvalue_output(dat_text: str) -> bool:
    """ccx spaces its .dat banners letter by letter; squeeze before matching."""
    squeezed = " ".join(dat_text.split())
    return ("E I G E N V A L U E N U M B E R" in squeezed
            or "E I G E N V A L U E O U T P U T" in squeezed)


def parse_dat_blocks(dat_text: str, header_re: re.Pattern) -> dict[str, dict[int, list[float]]]:
    """Return ``{SET_NAME: {node_id: [v1, v2, v3]}}`` for one .dat block kind.

    Later increments overwrite earlier ones, so what comes back is the final
    state of the analysis — the same thing the ODB path reads from the last frame.
    """
    blocks: dict[str, dict[int, list[float]]] = {}
    current: dict[int, list[float]] | None = None

    for raw in dat_text.splitlines():
        line = raw.strip()
        match = header_re.search(line)
        if match:
            current = blocks.setdefault(match.group(1).upper(), {})
            continue
        if current is None or not line:
            continue
        parts = line.split()
        if len(parts) < 2 or not parts[0].isdigit():
            current = None
            continue
        try:
            current[int(parts[0])] = [float(p) for p in parts[1:]]
        except ValueError:
            current = None
    return blocks


def parse_ccx_tip_u2(dat_text: str, node_id: int) -> float | None:
    """U2 of ``node_id`` from a .dat displacement block.

    Kept as a named helper because scripts/run_free_solver_check.py re-exports
    it and tests/test_free_solver_check.py imports it from there.
    """
    for values in parse_dat_blocks(dat_text, _DAT_DISP_RE).values():
        if node_id in values and len(values[node_id]) >= 2:
            return values[node_id][1]
    return None


# ---------------------------------------------------------------------------
# .frd parsing
# ---------------------------------------------------------------------------

def parse_frd_block(frd_text: str, block_name: str) -> dict[int, list[float]]:
    """Return ``{node_id: [components...]}`` for the last ``-4 <block_name>`` block."""
    lines = frd_text.splitlines()
    result: dict[int, list[float]] = {}
    in_block = False

    for raw in lines:
        if raw.startswith(" -4"):
            fields = raw[3:].split()
            name = fields[0] if fields else ""
            if name.upper() == block_name.upper():
                in_block = True
                result = {}
            else:
                in_block = False
            continue
        if not in_block:
            continue
        if raw.startswith(" -5"):
            continue
        if raw.startswith(" -3") or raw.startswith("  100"):
            in_block = False
            continue
        if raw.startswith(" -1"):
            node_id = int(raw[3:_FRD_HEADER_WIDTH])
            result[node_id] = _frd_fields(raw[_FRD_HEADER_WIDTH:])
        elif raw.startswith(" -2") and result:
            last = max(result)
            result[last].extend(_frd_fields(raw[_FRD_HEADER_WIDTH:]))
    return result


def _frd_fields(payload: str) -> list[float]:
    values = []
    for start in range(0, len(payload), _FRD_FIELD_WIDTH):
        chunk = payload[start:start + _FRD_FIELD_WIDTH].strip()
        if chunk:
            values.append(float(chunk))
    return values


def von_mises(components: list[float], order: tuple[str, ...] = _FRD_STRESS_ORDER) -> float:
    """von Mises from 6 stress components. CalculiX writes no MISES invariant."""
    if len(components) < 6:
        raise CcxResultError("需要 6 个应力分量才能算 Mises，实际拿到 %d 个" % len(components))
    comp = dict(zip(order, components))
    s_xx, s_yy, s_zz = comp["SXX"], comp["SYY"], comp["SZZ"]
    s_xy = comp["SXY"]
    s_yz = comp["SYZ"]
    # .frd calls it SZX, .dat calls the same component SXZ.
    s_zx = comp.get("SZX", comp.get("SXZ", 0.0))
    return math.sqrt(
        0.5 * ((s_xx - s_yy) ** 2 + (s_yy - s_zz) ** 2 + (s_zz - s_xx) ** 2)
        + 3.0 * (s_xy ** 2 + s_yz ** 2 + s_zx ** 2)
    )


# ---------------------------------------------------------------------------
# KPI extraction
# ---------------------------------------------------------------------------

def _reduce(values: list[float], reducer: str | None, default: str) -> float:
    if not values:
        raise CcxResultError("结果文件里没有可用数值")
    mode = str(reducer or default).lower()
    if mode == "min":
        return min(values)
    if mode == "last":
        return values[-1]
    if mode == "abs_max":
        return max(values, key=abs)
    return max(values)


def _select_nodes(blocks: dict[str, dict[int, list[float]]], set_name: str | None) -> dict[int, list[float]]:
    if set_name and set_name in blocks:
        return blocks[set_name]
    if set_name:
        raise CcxResultError("结果文件里没有集合 %s 的输出块" % set_name)
    merged: dict[int, list[float]] = {}
    for block in blocks.values():
        merged.update(block)
    return merged


def _refuse_unhonourable_location(kpi: dict) -> None:
    """The .frd field blocks are whole-model only — refuse a narrower request.

    CalculiX's *EL FILE / *NODE FILE output has no per-set variant, so a KPI
    that asks for "stress at the hole edge" cannot be honoured from the .frd.
    Before this guard the location string was simply ignored and the
    whole-model extreme came back under the user's KPI name — the same silent
    fallback the Abaqus extractor had, by a different route.
    """
    location = kpi.get("location")
    if not location:
        return
    if str(location).split(":", 1)[-1].strip().lower() in ("whole_model", "all"):
        return
    raise CcxResultError(
        "outputs.kpis[%s].location=%s：CalculiX 的 .frd 场输出是全模型块，"
        "无法按集合取值 —— 拒绝而不是悄悄退回全模型"
        % (kpi.get("name", "?"), location))


def _extract_one(kpi: dict, dat_text: str, frd_text: str) -> tuple[float, dict]:
    kind = kpi.get("type")

    if kind in ("nodal_displacement", "field_min"):
        default_comp = "U2" if kind == "nodal_displacement" else "U3"
        component = str(kpi.get("component", default_comp)).upper()
        idx = _COMPONENT_INDEX.get(component)
        if idx is None:
            raise CcxResultError("不认识的位移分量 %s" % component)
        set_name = resolve_set_name(kpi.get("location"), "node")
        nodes = _select_nodes(parse_dat_blocks(dat_text, _DAT_DISP_RE), set_name)
        values = [v[idx] for v in nodes.values() if len(v) > idx]
        return _reduce(values, kpi.get("reducer"), "min"), {
            "source": "ccx.dat",
            "definition": "node",
            "abaqus_equivalent": True,
        }

    if kind == "reaction_force_max":
        component = str(kpi.get("component", "RF3")).upper()
        idx = _COMPONENT_INDEX.get(component)
        if idx is None:
            raise CcxResultError("不认识的反力分量 %s" % component)
        set_name = resolve_set_name(kpi.get("location"), "node")
        nodes = _select_nodes(parse_dat_blocks(dat_text, _DAT_FORCE_RE), set_name)
        values = [abs(v[idx]) for v in nodes.values() if len(v) > idx]
        return _reduce(values, kpi.get("reducer"), "max"), {
            "source": "ccx.dat",
            "definition": "node",
            "abaqus_equivalent": True,
        }

    if kind in ("field_max", "derived_stress_concentration"):
        component = str(kpi.get("component", "")).upper()
        wants_mises = (
            kind == "derived_stress_concentration"
            or str(kpi.get("invariant", "")).upper() == "MISES"
            or "MISES" in str(kpi.get("name", "")).upper()
            or not component
        )
        if wants_mises:
            _refuse_unhonourable_location(kpi)
            stress = parse_frd_block(frd_text, "STRESS")
            if not stress:
                raise CcxResultError("`.frd` 里没有 STRESS 结果块")
            values = [von_mises(v) for v in stress.values() if len(v) >= 6]
            return _reduce(values, kpi.get("reducer"), "max"), {
                "source": "ccx.frd",
                "definition": "nodal_averaged",
                "abaqus_equivalent": False,
                "note": (
                    "CalculiX 的 .frd 应力是相邻单元平均后的节点值；Abaqus 取的是"
                    "不平均的 ELEMENT_NODAL 外插值。两者定义不同，数值不可直接对比。"
                ),
            }
        idx = _COMPONENT_INDEX.get(component)
        if idx is None:
            raise CcxResultError("CalculiX 后端暂不支持分量 %s 的 field_max" % component)
        _refuse_unhonourable_location(kpi)
        block = "DISP" if component.startswith("U") else "FORC"
        nodes = parse_frd_block(frd_text, block)
        values = [v[idx] for v in nodes.values() if len(v) > idx]
        return _reduce(values, kpi.get("reducer"), "max"), {
            "source": "ccx.frd",
            "definition": "node",
            "abaqus_equivalent": True,
        }

    raise CcxResultError("CalculiX 后端不支持 KPI 类型 %r" % (kind,))


def extract_kpis_ccx(job_stem: str, workdir: str | Path, kpi_spec: list[dict]) -> dict:
    """Extract KPIs from a finished CalculiX job.

    Returns the same top-level shape as post.extract_kpis.extract_kpis, plus
    ``kpi_provenance``. A KPI that cannot be produced yields NO value and an
    explicit error — never a 0.0 placeholder.
    """
    workdir = Path(workdir)
    dat_path = workdir / ("%s.dat" % job_stem)
    frd_path = workdir / ("%s.frd" % job_stem)

    result: dict = {
        "kpis": {},
        "errors": [],
        "kpi_provenance": {},
        "dat_path": str(dat_path),
        "frd_path": str(frd_path),
        "backend": "calculix",
    }

    dat_text = dat_path.read_text(encoding="utf-8", errors="replace") if dat_path.exists() else ""
    frd_text = frd_path.read_text(encoding="utf-8", errors="replace") if frd_path.exists() else ""

    if not dat_text.strip() and not frd_text.strip():
        result["errors"].append(
            "CalculiX 没有产生任何结果文件（.dat/.frd 都为空）——不输出任何 KPI"
        )
        return result

    if dat_is_eigenvalue_output(dat_text):
        result["errors"].append(
            "这个 .dat 是特征值分析的输出：重复出现的 displacements 块是一阶一阶的"
            "特征向量，不是同一个分析的一个个增量，parse_dat_blocks 的「后一个覆盖"
            "前一个 = 最终状态」在这里不成立。取最后一块等于把第 N 阶质量归一化特征"
            "向量的分量当成位移报出来（量纲是 1/√质量，不是 mm；实测密度×4 该值恰好"
            "减半）。这里不输出任何 KPI —— 正常情况下 runner/ccx_whitelist.py 会在"
            "求解前就拒掉这份 deck，能走到这里说明门禁被绕过了，请报告这个 case"
        )
        return result

    for kpi in kpi_spec:
        name = kpi.get("name", "?")
        try:
            value, provenance = _extract_one(kpi, dat_text, frd_text)
        except (CcxResultError, KeyError, ValueError) as exc:
            result["errors"].append("%s: %s" % (name, exc))
            continue
        result["kpis"][name] = value
        result["kpi_provenance"][name] = provenance
    return result
