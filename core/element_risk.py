"""Which element codes carry a silent accuracy risk, and where a spec used one.

WHY THIS EXISTS. #72. The same imported 10x10x100 bar, the same seed, the same
load — only the element code differs:

    C3D8I  tip -0.189446    0.54% from the closed form
    C3D8R  tip -17.237131   90.5x the closed form

and the C3D8R job reported COMPLETED with no warning anywhere.

REPRODUCED WHILE BUILDING THIS, on a different model -- a bar of the same size
built from this dialect rather than imported, under a distributed side pressure
rather than a tip force -- which is what turned the anecdote into a rule:

    elements through the 10 mm thickness   C3D8I       C3D8R        ratio
    1  (seed 10)                           -0.7126152  -65.66674    92.1x
    2  (seed  5)                           -0.7104333   -0.9517219   1.34x

Both jobs COMPLETED. Read the C3D8I column first: it moves 0.3% between the two
meshes, so it is already converged and the C3D8R answer is not "a mesh that is
too coarse" -- it is an element with no bending stiffness at all when there is
one layer of it. The number of layers through the thickness is the only knob
that changes anything. The trigger is one string in `mesh.element`,
which makes it the lowest-effort way in this whole engine to get an answer that
is confidently, enormously wrong.

Hourglassing is the cause. A first-order element with reduced integration has a
SINGLE integration point, and the bending modes of such an element produce zero
strain at that point — so they cost no energy and the element deforms into them
freely. Second-order reduced elements keep enough points that the modes are not
free, which is why C3D20R is the safe reduced element and C3D8R is not.

WHAT THIS DOES AND DOES NOT CLAIM (#72, decided 2026-08-07: 警告并写进报告).
It WARNS. It does not refuse, and it does not change any run's verdict — a
reduced-integration element is a legitimate choice, it is the right choice under
explicit dynamics with enhanced hourglass control, and on a model with no
bending in it the error does not appear at all. What is not legitimate is
getting the 90x answer with nothing on screen.

HOW IT DECIDES, AND WHERE IT REFUSES TO. Not a list of bad element names — the
list would go stale and a spec can name any element Abaqus has. The rule is
read off Abaqus's naming grammar:

    <family letters><node count><modifier letters>

`R` among the modifiers means reduced integration. First-order means the node
count is at most the topology's corner count, and the corner count comes from
the FAMILY, which is the one part that has to be looked up — `C3D8` is a
first-order hex while `CPE8` is a second-order quad, and nothing in the string
distinguishes them. So `_FAMILY_LINEAR_MAX` maps family prefixes, not elements:
a new element in a known family classifies correctly without an edit here.

A family that is not in the table and DOES carry an `R` is reported as
`unreadable`, never as safe. `B31R` is why: in a beam code the digits are not a
node count at all (`B31` = beam, 3D, order 1), so any rule read off them would
be inventing an answer. Silence from this module has to mean "no reduced
integration", not "we could not tell".
"""

from __future__ import annotations

import re

# family prefix -> the largest node count that is still FIRST-ORDER for the
# topologies that family covers. Longest prefix wins, so "SC" is found before
# "S" and a continuum shell is not mistaken for a conventional one.
#
# 8 for the 3D continuum families (hex 8 / wedge 6 / tet 4 are the first-order
# shapes; 20 / 15 / 10 are the second-order ones), 4 for the 2D continuum,
# shell and membrane families (quad 4 / tri 3 first-order; 8 / 6 second-order).
_FAMILY_LINEAR_MAX = {
    # 3D continuum: stress, heat transfer, acoustic, thermal-electrical,
    # cohesive, and the continuum shell, which is a hex.
    "C3D": 8, "DC3D": 8, "AC3D": 8, "Q3D": 8, "COH3D": 8, "SC": 8,
    "EC3D": 8, "DCC3D": 8,
    # 2D continuum: plane strain, plane stress, axisymmetric, generalised
    # plane strain, and their cohesive and heat-transfer counterparts.
    "CPE": 4, "CPS": 4, "CAX": 4, "CPEG": 4, "CGAX": 4, "COH2D": 4,
    "DC2D": 4, "DCAX": 4, "AC2D": 4, "ACAX": 4,
    # shells and membranes
    "S": 4, "SAX": 4, "STRI": 3, "M3D": 4, "SFM3D": 4, "DS": 4, "DSAX": 4,
}

# <family letters (may contain digits, as in C3D)><node count><modifiers>
# The prefix is non-greedy so the node count is the LAST digit run: "C3D8R"
# cannot resolve to family "C" / nodes "3", because the modifiers that would
# leave ("D8R") contain a digit and `[A-Z]*` refuses it.
_CODE = re.compile(r"^(?P<family>[A-Z0-9]*?)(?P<nodes>\d+)(?P<mods>[A-Z]*)$")

RISK = "risk"
CLEAR = "clear"
UNREADABLE = "unreadable"

# The measurement this whole module is built on, quoted wherever it warns. A
# warning that says "may be inaccurate" is advice; one that says "90.5x on a
# bar we actually ran" is evidence.
MEASURED = ("实测（Abaqus 2021，两次独立复现）："
            "① 导入的 10×10×100 bar 加尖端力——C3D8I −0.189446（离闭式解 0.54%），"
            "C3D8R −17.237131，是闭式解的 90.5 倍；"
            "② 用本方言从零件建的同尺寸悬臂加侧向均布压力，厚度方向只有 1 层单元时"
            "（seed 10）C3D8I −0.7126152、C3D8R −65.66674，差 92.1 倍；"
            "加到 2 层（seed 5）差 1.34 倍——两次作业都报 COMPLETED，"
            "而 C3D8I 从 1 层到 2 层只变了 0.3%，也就是说错的那一边不是网格不够密")

FIX = ("弯曲为主的静力问题用 C3D8I（非协调模式）或 C3D20R；"
       "非用 C3D8R 不可就把厚度方向的单元层数加上去——实测 1 层差 92 倍、"
       "2 层差 1.34 倍，这是唯一一个真正改变结果的旋钮；"
       "显式动力学要用 C3D8R 的话，把单元类型写成 "
       "`{new: mesh.ElemType, elemCode: C3D8R, elemLibrary: EXPLICIT, "
       "hourglassControl: ENHANCED}`；"
       "确认模型里没有弯曲，则这条提示可以忽略")


def parse_element_code(code: str) -> dict | None:
    """`{"family", "nodes", "mods"}`, or None if the string is not an element code."""
    match = _CODE.match(str(code or "").strip().upper())
    if not match:
        return None
    # A family with no letter in it is not an element code -- "12345" would
    # otherwise parse as 12345 nodes and be waved through as "no R, no reduced
    # integration", which is a true sentence about a string that is not an
    # element.
    if not any(ch.isalpha() for ch in match.group("family")):
        return None
    return {"family": match.group("family"),
            "nodes": int(match.group("nodes")),
            "mods": match.group("mods")}


def _linear_max(family: str) -> int | None:
    """The family's first-order node ceiling. Longest prefix wins."""
    best = None
    for prefix, ceiling in _FAMILY_LINEAR_MAX.items():
        if family.startswith(prefix) and (best is None or len(prefix) > len(best[0])):
            best = (prefix, ceiling)
    return best[1] if best else None


def hourglass_verdict(code: str) -> dict:
    """`{"code", "verdict", "why"}` for one element code.

    Three verdicts, and the third one matters: `unreadable` is what a reduced
    element from a family this cannot classify gets. Calling it `clear` would
    make silence mean "safe" when it only means "we did not know".
    """
    parsed = parse_element_code(code)
    text = str(code or "").strip().upper()
    if parsed is None:
        return {"code": text, "verdict": UNREADABLE,
                "why": "%r 不符合 <族><节点数><修饰符> 的单元命名式，无法判断积分方案"
                       % text}
    if "R" not in parsed["mods"]:
        # True regardless of family: no reduced integration, no hourglass modes
        # from reduced integration. This is why an unknown family is usually
        # silent rather than noisy.
        return {"code": text, "verdict": CLEAR,
                "why": "修饰符里没有 R，不是缩减积分单元"}
    ceiling = _linear_max(parsed["family"])
    if ceiling is None:
        return {"code": text, "verdict": UNREADABLE,
                "why": "%s 是缩减积分（带 R），但族前缀 %r 不在已登记的连续体/壳/膜"
                       "族里——例如梁单元 B31 的数字是「三维、一阶」不是节点数，"
                       "照节点数判会是编出来的答案" % (text, parsed["family"])}
    if parsed["nodes"] > ceiling:
        return {"code": text, "verdict": CLEAR,
                "why": "%d 个节点超过 %s 族的一阶上限 %d，是二阶缩减积分单元，"
                       "积分点数量足以约束弯曲模态" % (parsed["nodes"],
                                                    parsed["family"], ceiling)}
    return {"code": text, "verdict": RISK,
            "why": "%s 是一阶缩减积分单元（%d 节点 ≤ %s 族一阶上限 %d，修饰符含 R），"
                   "只有一个积分点，弯曲模态在该点不产生应变、因而不耗能。%s"
                   % (text, parsed["nodes"], parsed["family"], ceiling, MEASURED)}


def _v2_mesh_elements(spec: dict) -> list[tuple]:
    """(where, code, is_default, hourglass) for every part with a mesh block.

    `is_default` is the case worth having this whole module for: `mesh:` with
    no `element:` key gets **C3D8R**, so the 90x answer is what a spec gets by
    saying nothing at all. See `runner/build_v2.py` `_part_lines`.
    """
    from runner.build_v2 import DEFAULT_MESH_ELEMENT

    rows = []
    for index, part in enumerate(spec.get("parts") or []):
        if not isinstance(part, dict):
            continue
        mesh = part.get("mesh")
        if not isinstance(mesh, dict):
            continue
        name = str(part.get("name", index))
        hourglass = str(mesh.get("hourglass_control") or "").upper()
        declared = mesh.get("element")
        if declared is None:
            rows.append(("parts[%s].mesh（没写 element:）" % name,
                         DEFAULT_MESH_ELEMENT, True, hourglass))
        else:
            rows.append(("parts[%s].mesh.element" % name, str(declared), False,
                         hourglass))
    return rows


def spec_hourglass_findings(spec: dict) -> list[dict]:
    """Every place in a spec that asks for a first-order reduced element.

    v1 specs are not walked and that is not an oversight: v1 has no element
    key. `runner/build_model.py` picks C3D20R under Standard and C3D8R with
    `hourglassControl=ENHANCED` under Explicit — the second is the textbook
    correct use of a reduced element, so there is nothing to warn about and
    warning anyway would teach the reader to ignore this channel.

    A v2 spec that writes that same combination itself — `hourglass_control`
    other than DEFAULT, in a model whose steps are explicit — is the same
    textbook case and is treated the same way. BOTH halves are required. Under
    Standard the warning stands whatever the hourglass setting says, because the
    92x measurement above is a static bending case, and nothing here has
    measured ENHANCED rescuing one; assuming it would is exactly the kind of
    unmeasured claim this module exists to avoid making.
    """
    from runner.build_v2 import _element_library

    explicit = _element_library(spec or {}) == "EXPLICIT"
    findings = []
    for where, code, is_default, hourglass in _v2_mesh_elements(spec or {}):
        verdict = hourglass_verdict(code)
        if verdict["verdict"] != RISK:
            continue
        if explicit and hourglass and hourglass != "DEFAULT":
            continue
        findings.append({
            "where": where,
            "element": verdict["code"],
            "from_default": is_default,
            "why": verdict["why"],
            "fix": FIX,
        })
    return findings


def limitation_entries(findings: list[dict]) -> list[dict]:
    """The findings in the shape `result["limitations"]` carries."""
    entries = []
    for f in findings:
        default_note = ("——而且 spec 没写 element:，这是**默认值**，"
                        "什么都不写就会拿到它。" if f["from_default"] else "")
        entries.append({
            "feature": f["where"],
            "value": f["element"],
            "kind": "hourglass_risk",
            "reason": "%s%s 修法：%s" % (f["why"], default_note, f["fix"]),
        })
    return entries
