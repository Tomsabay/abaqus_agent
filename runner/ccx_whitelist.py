"""
ccx_whitelist.py
----------------
Refuse-before-run gate for decks handed to CalculiX.

WHY A WHITELIST AND NOT AN EXIT-CODE CHECK. CalculiX silently DROPS load
keywords it does not recognise and still exits 0. A deck carrying
``*INCIDENT WAVE INTERACTION, CONWEP`` runs to completion, writes a full .frd,
and reports every displacement as exactly 0.000000E+00 — the console shows only
``*WARNING in calinput. Card image cannot be interpreted``. The step itself was
legal, so ``No analysis was selected`` never appears either. Any gate based on
the exit code, on result files existing, or on that one console string, ships a
numerically plausible wrong answer.

So: every keyword and every element type in the deck must be on a list we have
actually verified. Anything else is refused with the offending card named.

Element failures (COH3D8, SC8R, C3D8H, B33 ...) are loud rc=201 errors in ccx,
but they are listed here anyway so the user gets a plain-language refusal
before a solve instead of a solver traceback after one.
"""

from __future__ import annotations

import re

# Keywords verified to be honoured by ccx 2.23, or verified harmless no-ops.
_ALLOWED_KEYWORDS = frozenset({
    "*heading", "*node", "*element", "*nset", "*elset", "*surface",
    "*material", "*elastic", "*density", "*plastic", "*expansion",
    "*conductivity", "*specific heat",
    "*solid section", "*shell section", "*beam section", "*membrane section",
    "*boundary", "*cload", "*dload", "*dsload", "*temperature",
    "*initial conditions", "*amplitude", "*orientation", "*transform",
    "*step", "*end step", "*static",
    "*controls", "*time points", "*restart",
    "*node print", "*el print", "*node file", "*el file", "*contact file",
    "*contact print", "*energy print", "*section print",
    "*equation", "*rigid body", "*physical constants", "*film", "*radiate",
    "*cflux", "*dflux", "*include",
})

# Cards ccx 2.23 does implement, but which this project has never compared
# against an Abaqus baseline. They were on the allowed list above with zero
# verification items behind them, which is the one thing the capability gate
# exists to prevent: ccx would solve the deck, exit 0, and the numbers would be
# reported exactly like verified ones. Contact is where the two solvers differ
# most (node-to-face vs surface-to-surface, different penalty stiffness
# defaults, different stress averaging), so "it ran" says very little.
#
# To promote one of these: add a passing item to
# scripts/run_calculix_backend_check.py that compares it to an Abaqus run, then
# move the card into _ALLOWED_KEYWORDS.
_UNVERIFIED_KEYWORDS = frozenset({
    "*contact pair", "*surface interaction", "*surface behavior",
    "*friction", "*gap", "*clearance", "*tie",
})

# The analysis-procedure cards. These were on _ALLOWED_KEYWORDS on the bar "ccx
# implements it" -- which is the wrong bar, and the same wrong bar the contact
# family above already sits here for. Worse, for a custom_inp spec the deck IS
# the model: core/backends.py:241 reads analysis.step_type off the SPEC, and
# schema/spec_schema.json makes `analysis` optional entirely, so a deck whose
# step is *FREQUENCY is evaluated as Static and every step-type refusal in
# _STEP_KEYS is simply never asked. Measured on ccx 2.23: a real Abaqus 2021
# modal deck ran rc=0 with no dropped cards, and the pipeline reported a
# mass-normalised eigenvector component as a tip displacement.
#
# value = the analysis.step_type the capability matrix would have refused, or
# None where the spec dialect has no name for the procedure at all (reachable
# only through custom_inp, i.e. never seen by the matrix under any spelling).
_UNVERIFIED_PROCEDURES = {
    "*frequency": "Frequency",
    "*dynamic": "Dynamic_Implicit / Dynamic_Explicit",
    "*coupled temperature-displacement": "Coupled_Temperature_Displacement",
    "*buckle": None,
    "*visco": None,
    "*heat transfer": None,
}

# Cards Abaqus/CAE emits that runner/ccx_deck.translate_abaqus_inp removes.
# Reaching the gate with one of these still present is a translator bug, not a
# user error, so they are refused rather than tolerated.
_MUST_BE_TRANSLATED = frozenset({
    "*part", "*end part", "*assembly", "*end assembly",
    "*instance", "*end instance", "*preprint", "*output",
    "*node output", "*element output", "*contact output",
})

# Element types verified to load in ccx 2.23.
_ALLOWED_ELEMENTS = frozenset({
    "C3D4", "C3D6", "C3D8", "C3D8I", "C3D8R", "C3D10", "C3D15", "C3D20", "C3D20R",
    "CPS3", "CPS4", "CPS4R", "CPS6", "CPS8", "CPS8R",
    "CPE3", "CPE4", "CPE4R", "CPE8",
    "CAX3", "CAX4", "CAX4R", "CAX8", "CAX8R",
    "S3", "S4", "S4R", "S6", "S8", "S8R",
    "B31", "B31R", "B32", "T3D2", "M3D4R", "DC3D8",
})

_KEYWORD_RE = re.compile(r"^\s*\*([^,\n]*)", re.IGNORECASE)
_ELEM_TYPE_RE = re.compile(r"\btype\s*=\s*([A-Za-z0-9]+)", re.IGNORECASE)


class DeckRefused(Exception):
    """The deck contains something CalculiX cannot solve faithfully."""

    def __init__(self, reasons: list[str]):
        self.reasons = reasons
        super().__init__("; ".join(reasons))


def scan_deck(deck_text: str) -> list[str]:
    """Return plain-language reasons the deck must not go to CalculiX (empty = clean)."""
    reasons: list[str] = []
    seen_bad_keywords: set[str] = set()
    seen_bad_elements: set[str] = set()

    for raw in deck_text.splitlines():
        line = raw.rstrip()
        stripped = line.lstrip()
        if not stripped.startswith("*") or stripped.startswith("**"):
            continue

        match = _KEYWORD_RE.match(line)
        if not match:
            continue
        # ccx itself collapses whitespace inside keyword names when it echoes
        # them; normalise the same way so "*SOLID  SECTION" cannot slip past.
        keyword = "*" + " ".join(match.group(1).split()).lower()

        if keyword in _MUST_BE_TRANSLATED:
            if keyword not in seen_bad_keywords:
                seen_bad_keywords.add(keyword)
                reasons.append(
                    "%s 是 Abaqus 装配格式的卡，CalculiX 读不了；这份 .inp 没有被展平，"
                    "属于内部错误，请报告这个 case" % keyword.upper()
                )
            continue

        if keyword in _UNVERIFIED_PROCEDURES:
            if keyword not in seen_bad_keywords:
                seen_bad_keywords.add(keyword)
                step_type = _UNVERIFIED_PROCEDURES[keyword]
                reasons.append(
                    "%s 是分析步类型卡：deck 里写的是哪个过程，ccx 就算哪个过程，"
                    "spec 的 analysis.step_type 管不到它（custom_inp 的模型就是 deck "
                    "本身）。这个过程在 CalculiX 上还没有跟 Abaqus 对过基准值 —— %s "
                    "在 core/backends.py 的能力矩阵里就是拒的。ccx 会照常算完、退出码 "
                    "0、一张卡都不丢，结果会被当成验证过的数报出去：实测一份只有 "
                    "*FREQUENCY、没有任何载荷卡的 deck，位移 KPI 报出 -110.9003"
                    "（模型总长 200mm），那是第 6 阶质量归一化特征向量的分量，把请求"
                    "模态数改成 3 就换一个数。出路：在 scripts/"
                    "run_calculix_backend_check.py 里加一条与 Abaqus 比对的通过项，"
                    "再把这张卡挪回 _ALLOWED_KEYWORDS；在那之前请用 Abaqus 后端跑"
                    "这个模型"
                    % (keyword.upper(),
                       ("analysis.step_type=%s" % step_type) if step_type
                       else "spec 里根本没有能表达这个过程的字段")
                )
            continue

        if keyword in _UNVERIFIED_KEYWORDS:
            if keyword not in seen_bad_keywords:
                seen_bad_keywords.add(keyword)
                reasons.append(
                    "%s（接触/绑定）在 CalculiX 上还没有跟 Abaqus 对过基准值。"
                    "ccx 认识这张卡、会算完、退出码是 0，但两个求解器的接触算法本来"
                    "就不一样，没比对过就报数等于拿没验证的结果冒充验证过的，所以拒绝"
                    % keyword.upper()
                )
            continue

        if keyword not in _ALLOWED_KEYWORDS:
            if keyword not in seen_bad_keywords:
                seen_bad_keywords.add(keyword)
                reasons.append(
                    "CalculiX 不认识 %s：它会静默忽略这张卡并照常算完（退出码仍是 0），"
                    "结果会是错的，所以这里直接拒绝" % keyword.upper()
                )
            continue

        if keyword == "*element":
            elem_match = _ELEM_TYPE_RE.search(line)
            elem_type = (elem_match.group(1).upper() if elem_match else "")
            if elem_type and elem_type not in _ALLOWED_ELEMENTS and elem_type not in seen_bad_elements:
                seen_bad_elements.add(elem_type)
                reasons.append(
                    "CalculiX 没有 %s 单元（Abaqus 独有），无法求解这个模型" % elem_type
                )
    return reasons


def assert_translatable(deck_text: str) -> None:
    """Raise DeckRefused when the deck contains anything unverified."""
    reasons = scan_deck(deck_text)
    if reasons:
        raise DeckRefused(reasons)


def allowed_keywords() -> frozenset[str]:
    return _ALLOWED_KEYWORDS


def allowed_elements() -> frozenset[str]:
    return _ALLOWED_ELEMENTS
