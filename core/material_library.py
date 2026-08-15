"""
core/material_library.py
------------------------
Named materials with numbers somebody else measured.

Every spec in this repo types its material by hand — ``E: 210000.0`` with a
``# MPa`` comment next to it. That works until the person writing the spec is
not the person who knows what steel weighs. ``load_material("Steel-Generic")``
hands back exactly that block, with every number traceable to a file, a licence
and an upstream commit.

A spec reaches it through ``material: {library: Steel-Generic}``, which
``resolve_spec_materials`` expands into numbers. That expansion has to run
before validation, and this is not a preference: ``schema/spec_schema.json``
declares the material block ``additionalProperties: false`` with a number for
every property, so a spec still carrying ``library:`` fails validation with
four errors -- measured -- ``'name'/'E'/'nu' is a required property`` and
``Additional properties are not allowed ('library' was unexpected)``.
``agent/orchestrator.py`` expands at load time, before ``validate_spec``, and
sees none of that. Any other path that validates a spec it has not expanded
will reject the key instead of resolving it.

The data ships in ``data/materials/freecad/*.json``, converted from FreeCAD's
material cards by ``data/materials/build_library.py``. Nothing here touches the
network, and nothing here imports a third-party package: at run time this is
stdlib plus JSON on disk.

Two things dominate the design.

**Units are the whole risk.** FreeCAD writes ``"7900 kg/m^3"`` and
``"210000 MPa"`` — a number and a unit, in one string, in SI. The spec dialect's
default system is mm_MPa_t, where that density is 7.9e-9. Getting the exponent
wrong does not crash anything; it produces a run that completes, a contour plot
that looks plausible, and an answer wrong by twelve orders of magnitude. So:
the unit is parsed off every value and looked up in a table, a unit that is not
in the table is refused rather than assumed, the arithmetic is done in Decimal
so 210000 MPa comes back as exactly 210000.0 and not 210000.00000000003, and
each shipped card carries the raw string beside the converted number so the
conversion can be checked without re-fetching anything.

**A refusal is a result.** A card missing E or nu cannot be a spec material
block, so it is not shipped, and ``data/materials/provenance.json`` records why.
A value FreeCAD wrote with a decimal comma (``"2200,00 MPa"``) is refused
outright rather than guessed at: read as a decimal point it is 2200 MPa, read as
a thousands separator it is 220000 MPa, and both are physically plausible
numbers for *some* material. A property this dialect has no key for is listed in
the provenance as not included, with the reason. What must never happen is a
number arriving in the spec block that nobody can trace back to a source.
"""

from __future__ import annotations

import difflib
import functools
import json
import re
from decimal import Decimal
from pathlib import Path
from typing import Any

from tools.errors import AbaqusAgentError, ErrorCode

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "materials"
CARD_DIR = DATA_DIR / "freecad"

CARD_SCHEMA = "abaqus_agent.material_card/1"


class MaterialLibraryError(AbaqusAgentError):
    """A material could not be produced. Always names what to write instead."""

    def __init__(self, message: str):
        super().__init__(ErrorCode.SPEC_INVALID, message)


# ---------------------------------------------------------------------------
# Units
# ---------------------------------------------------------------------------

# Physical dimension -> the unit every stored value is normalised to. SI is the
# storage form because that is what the upstream cards are written in, so the
# stored number can be eyeballed against the raw string next to it.
SI_UNIT = {
    "stress": "Pa",
    "density": "kg/m^3",
    "thermal_conductivity": "W/(m*K)",
    "specific_heat": "J/(kg*K)",
    "thermal_expansion": "1/K",
    "dimensionless": "-",
}

# Unit spellings this module will accept, and what each one is worth in the SI
# unit above. Deliberately a short list of spellings actually seen in the
# FreeCAD corpus plus the unambiguous neighbours. Anything else is refused --
# a guessed factor is the one failure mode that produces a wrong answer with no
# symptom, so the list only grows when someone has read the card that needs it.
UNIT_TO_SI: dict[str, dict[str, Decimal]] = {
    "stress": {
        "Pa": Decimal(1),
        "kPa": Decimal("1E3"),
        "MPa": Decimal("1E6"),
        "GPa": Decimal("1E9"),
        "N/mm^2": Decimal("1E6"),
        "N/mm2": Decimal("1E6"),
        "N/m^2": Decimal(1),
    },
    "density": {
        "kg/m^3": Decimal(1),
        "kg/m3": Decimal(1),
        "g/cm^3": Decimal("1E3"),
        "g/cm3": Decimal("1E3"),
        "kg/dm^3": Decimal("1E3"),
        "t/m^3": Decimal("1E3"),
    },
    "thermal_conductivity": {
        "W/m/K": Decimal(1),
        "W/(m*K)": Decimal(1),
        "W/m*K": Decimal(1),
        "W/mK": Decimal(1),
    },
    "specific_heat": {
        "J/kg/K": Decimal(1),
        "J/(kg*K)": Decimal(1),
        "J/kgK": Decimal(1),
    },
    "thermal_expansion": {
        "m/m/K": Decimal(1),
        "mm/mm/K": Decimal(1),
        "1/K": Decimal(1),
        "um/m/K": Decimal("1E-6"),
        "10^-6/K": Decimal("1E-6"),
    },
    "dimensionless": {
        "": Decimal(1),
    },
}

# SI -> target system, per dimension, and the label the converted number now
# carries. mm_MPa_t is the spec dialect's default (mm, N, MPa, tonne, s), where
# energy is N*mm = mJ and power is mW.
#
#   density            kg/m^3 -> t/mm^3    1e-3 t / 1e9 mm^3      = 1e-12
#   stress             Pa     -> MPa                              = 1e-6
#   conductivity       W/(m*K)-> mW/(mm*K) 1e3 mW / 1e3 mm        = 1
#   specific heat      J/(kg*K)->mJ/(t*K)  1e3 mJ / 1e-3 t        = 1e6
#   thermal expansion  1/K    -> 1/K                              = 1
#
# The two that read as "no conversion needed" are the ones worth stating
# explicitly: conductivity really is numerically identical in the two systems,
# and specific heat really is not.
UNIT_SYSTEMS: dict[str, dict[str, tuple[Decimal, str]]] = {
    "mm_MPa_t": {
        "stress": (Decimal("1E-6"), "MPa"),
        "density": (Decimal("1E-12"), "t/mm^3"),
        "thermal_conductivity": (Decimal(1), "mW/(mm*K)"),
        "specific_heat": (Decimal("1E6"), "mJ/(t*K)"),
        "thermal_expansion": (Decimal(1), "1/K"),
        "dimensionless": (Decimal(1), "-"),
    },
    "SI_m_kg_s": {
        "stress": (Decimal(1), "Pa"),
        "density": (Decimal(1), "kg/m^3"),
        "thermal_conductivity": (Decimal(1), "W/(m*K)"),
        "specific_heat": (Decimal(1), "J/(kg*K)"),
        "thermal_expansion": (Decimal(1), "1/K"),
        "dimensionless": (Decimal(1), "-"),
    },
}

DEFAULT_UNITS = "mm_MPa_t"

# U+00B5 MICRO SIGN and U+03BC GREEK SMALL LETTER MU both appear in the wild and
# are indistinguishable on screen; fold them onto ASCII before the table lookup.
_MICRO = {"µ": "u", "μ": "u"}


def normalise_unit(unit: str) -> str:
    """Fold the spellings that differ only in glyph, not in meaning."""
    text = (unit or "").strip()
    for micro, ascii_ in _MICRO.items():
        text = text.replace(micro, ascii_)
    return " ".join(text.split()).replace(" ", "")


def parse_quantity(raw: Any, dimension: str, *, where: str = "") -> dict:
    """Split ``"7900 kg/m^3"`` into a number, a unit, and its SI value.

    Refuses rather than guesses. The three refusals below are all cases that
    would otherwise yield a plausible-looking number:

    * a decimal comma — ``"2200,00 MPa"`` is 2200 or 220000 depending on which
      locale wrote it, and this module has no way to tell;
    * a unit that is not in ``UNIT_TO_SI`` — assuming SI is how a GPa card
      becomes a 1000x error;
    * a bare number where a unit is expected — same reason.
    """
    if dimension not in UNIT_TO_SI:
        raise MaterialLibraryError(
            "内部错误：未知的量纲 %r。可用量纲：%s"
            % (dimension, "、".join(sorted(UNIT_TO_SI))))

    text = str(raw).strip()
    label = ("%s：" % where) if where else ""

    if "," in text:
        raise MaterialLibraryError(
            "%s值 %r 里有逗号。逗号既可能是小数点（%s）也可能是千分位（%s），"
            "两个读法都是物理上说得通的数，本模块不猜——请把上游卡片改成用小数点的"
            "写法再转换。"
            % (label, text, text.replace(",", ".", 1), text.replace(",", "", 1)))

    number_text, unit_text = _split_number(text)
    if number_text is None:
        raise MaterialLibraryError(
            "%s值 %r 开头不是一个数字，无法解析。期望的写法是「数字 单位」，"
            "例如 \"7900 kg/m^3\"。" % (label, text))

    unit = normalise_unit(unit_text)
    table = UNIT_TO_SI[dimension]
    if unit not in table:
        if dimension == "dimensionless":
            raise MaterialLibraryError(
                "%s值 %r 带了单位 %r，但这是无量纲量（例如泊松比），不应该有单位。"
                % (label, text, unit_text.strip()))
        raise MaterialLibraryError(
            "%s单位 %r 不在 %s 的已知单位表里，拒绝换算（猜一个换算系数正是"
            "「结果看起来正常但差几个数量级」的来源）。已知单位：%s。"
            "要支持新单位，请在 core/material_library.py 的 UNIT_TO_SI[%r] 里"
            "加上它对 %s 的换算系数。"
            % (label, unit_text.strip() or "(空)", dimension,
               "、".join(sorted(k for k in table if k)), dimension,
               SI_UNIT[dimension]))

    try:
        number = Decimal(number_text)
    except Exception as exc:  # pragma: no cover - _split_number already gated it
        raise MaterialLibraryError(
            "%s数字部分 %r 无法解析：%s" % (label, number_text, exc))

    return {
        "raw": text,
        "raw_number": number_text,
        "raw_unit": unit_text.strip(),
        "unit": unit,
        "dimension": dimension,
        "si": number * table[unit],
        "si_unit": SI_UNIT[dimension],
    }


def _split_number(text: str) -> tuple[str | None, str]:
    """Longest leading run that ``Decimal`` accepts, and the rest.

    Hand-rolled rather than a regex because the number and the unit are only
    separated by convention: ``"0.000012 m/m/K"`` has a space, ``"30deg"``
    would not, and the exponent marker ``e`` is also a letter a unit can start
    with. Taking the longest prefix Decimal accepts settles all three the same
    way.
    """
    best: tuple[str | None, str] = (None, text)
    for end in range(len(text), 0, -1):
        head = text[:end]
        if head[-1] not in "0123456789.":
            continue
        try:
            Decimal(head)
        except Exception:
            continue
        return head, text[end:]
    return best


def convert(si_value: Decimal | float | str, dimension: str,
            units: str = DEFAULT_UNITS) -> tuple[float, str]:
    """SI value -> (value in ``units``, the unit label it now carries)."""
    system = _unit_system(units)
    if dimension not in system:
        raise MaterialLibraryError(
            "内部错误：单位制 %r 没有定义量纲 %r 的换算。" % (units, dimension))
    factor, label = system[dimension]
    value = Decimal(str(si_value)) * factor
    return float(value), label


def _unit_system(units: str) -> dict[str, tuple[Decimal, str]]:
    if units not in UNIT_SYSTEMS:
        raise MaterialLibraryError(
            "不认识的单位制 %r。本模块支持：%s。spec 里 meta.units 写哪个，"
            "load_material 就传哪个——两边不一致会得到量级完全错误的模型。"
            % (units, "、".join(sorted(UNIT_SYSTEMS))))
    return UNIT_SYSTEMS[units]


# ---------------------------------------------------------------------------
# FreeCAD card -> spec material block
# ---------------------------------------------------------------------------

# spec material key, FreeCAD card key, dimension. The order is the order the
# emitted material block is written in.
SPEC_PROPERTIES: tuple[tuple[str, str, str], ...] = (
    ("E", "YoungsModulus", "stress"),
    ("nu", "PoissonRatio", "dimensionless"),
    ("density", "Density", "density"),
    ("conductivity", "ThermalConductivity", "thermal_conductivity"),
    ("specific_heat", "SpecificHeat", "specific_heat"),
    ("expansion_coeff", "ThermalExpansionCoefficient", "thermal_expansion"),
)

# schema/spec_schema.json requires both of these on the material block, so a
# card without them cannot become one. Refused at build time, not at load time.
REQUIRED_SPEC_KEYS = ("E", "nu")

# `yield` and not `yield_stress`: runner/build_v2.py refuses `yield_stress` by
# name and tells you to write `yield`, which is the key that actually becomes a
# *Plastic card. Kept out of the default material block on purpose -- see
# load_material.
PLASTIC_PROPERTY = ("yield", "YieldStrength", "stress")

# Card keys this dialect has no home for, each with the reason, because "this
# key was ignored" is not an acceptable thing for a material library to leave
# unsaid. A key in neither this table nor the two above is still reported --
# see _partition_models -- so a future FreeCAD release adding a property cannot
# slip past unnoticed.
UNMAPPED_REASONS = {
    "UltimateTensileStrength":
        "抗拉强度是失效判据，不是本构。spec 的 material 块只描述本构，没有这个键；"
        "要用它做校核请写进 expected.json 的判据里。",
    "CompressiveStrength":
        "抗压强度同样是失效判据，spec 的 material 块没有对应键。",
    "ShearModulus":
        "各向同性材料的剪切模量由 E 和 ν 决定，spec 只在 materials[] 的复合材料"
        "条目里有独立的 G12。这里保留原始值供人工核对，不写进 material 块。",
    "AngleOfFriction":
        "内摩擦角属于 Mohr-Coulomb 一类本构，本 dialect 不生成这种材料卡。",
}

# Card keys that carry no physics and are folded into the card's source block
# instead of being reported as dropped properties.
_METADATA_KEYS = {
    "UUID", "Father", "ProductURL", "StandardCode", "KindOfMaterial",
    "MaterialNumber", "SpecificPrice", "Vendor", "ProductName",
}


_SAFE_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")


def _partition_models(models: dict) -> dict[str, Any]:
    """Flatten a card's ``Models`` block into one key -> raw-string mapping.

    Flattened because the model a property sits under is not stable: the same
    YoungsModulus lives under ``LinearElastic`` in one card,
    ``IsotropicLinearElastic`` in another and ``Linear Elastic`` -- with a space
    -- in a third. Keying off the model name would silently lose the odd ones.
    A key that appears under two models with different values is a contradiction
    in the card, so it is refused rather than resolved by iteration order.
    """
    flat: dict[str, tuple[str, str]] = {}
    for model_name, body in (models or {}).items():
        if not isinstance(body, dict):
            continue
        for key, value in body.items():
            if key in _METADATA_KEYS:
                continue
            previous = flat.get(key)
            if previous is not None and str(previous[1]).strip() != str(value).strip():
                raise MaterialLibraryError(
                    "卡片里 %s 出现两次且取值不同：%s 下是 %r，%s 下是 %r。"
                    "这是上游数据自相矛盾，不做取舍。"
                    % (key, previous[0], previous[1], model_name, value))
            flat[key] = (model_name, value)
    return {k: v[1] for k, v in flat.items()}


def card_from_fcmat(document: dict, source: dict) -> dict:
    """Convert one parsed .FCMat document into a shippable card.

    ``document`` is the YAML mapping as FreeCAD writes it; ``source`` is the
    provenance the caller knows and this module cannot (path, commit, url,
    retrieval date). Raises MaterialLibraryError if the card cannot serve as a
    spec material block -- the caller records that as a refusal.
    """
    general = document.get("General") or {}
    name = str(source.get("name") or general.get("Name") or "").strip()
    if not name:
        raise MaterialLibraryError("卡片没有名字，无法入库。")
    # The name goes into the spec as material.name and from there into the CAE
    # script as an Abaqus material name, so it has to survive both. FreeCAD's
    # own Name field does not always: "Aluminum 6061-T6" has a space in it.
    if not _SAFE_NAME.match(name):
        raise MaterialLibraryError(
            "材料名 %r 里有 spec / Abaqus 材料名不接受的字符（只允许字母开头、"
            "字母数字下划线连字符）。" % name)

    licence = str(general.get("License") or "").strip()
    if not licence:
        raise MaterialLibraryError("卡片没有 License 字段，无法判断能不能分发。")

    flat = _partition_models(document.get("Models") or {})

    properties: dict[str, dict] = {}
    for spec_key, card_key, dimension in SPEC_PROPERTIES:
        if card_key not in flat:
            continue
        parsed = parse_quantity(flat[card_key], dimension,
                                where="%s.%s" % (name, card_key))
        properties[spec_key] = _property_entry(parsed, card_key)

    missing = [k for k in REQUIRED_SPEC_KEYS if k not in properties]
    if missing:
        raise MaterialLibraryError(
            "卡片缺少 %s，而 schema 里 material 块必须有 E 和 ν，"
            "所以它没法当材料用。" % "、".join(missing))

    nu = properties["nu"]["si"]
    if not 0.0 <= nu < 0.5:
        raise MaterialLibraryError(
            "泊松比 %s 不在 schema 允许的 [0, 0.5) 区间内，写进 spec 会被校验挡下。"
            % nu)

    plastic = None
    spec_key, card_key, dimension = PLASTIC_PROPERTY
    if card_key in flat:
        parsed = parse_quantity(flat[card_key], dimension,
                                where="%s.%s" % (name, card_key))
        plastic = {spec_key: _property_entry(parsed, card_key)}

    unmapped = []
    handled = ({c for _, c, _ in SPEC_PROPERTIES} | {PLASTIC_PROPERTY[1]})
    for card_key in sorted(flat):
        if card_key in handled:
            continue
        unmapped.append({
            "fcmat_key": card_key,
            "raw": str(flat[card_key]).strip(),
            "reason": UNMAPPED_REASONS.get(
                card_key,
                "本模块不认识这个卡片字段，没有对应的 spec material 键。"
                "如果它是需要的物理量，请在 core/material_library.py 的 "
                "SPEC_PROPERTIES 里加映射。"),
        })

    return {
        "schema": CARD_SCHEMA,
        "name": name,
        "upstream_name": str(general.get("Name") or "").strip(),
        "category": str(source.get("category") or "").strip(),
        "description": str(general.get("Description") or "").strip(),
        "license": licence,
        "source": dict(source, author=str(general.get("Author") or "").strip(),
                       uuid=str(general.get("UUID") or "").strip()),
        "properties": properties,
        "plasticity": plastic,
        "unmapped": unmapped,
        "notes": consistency_notes(properties, plastic, flat),
    }


def _property_entry(parsed: dict, card_key: str) -> dict:
    """One property, stored three ways so the conversion needs no second source.

    ``raw`` is what FreeCAD wrote, ``si`` is that value in SI, and the
    mm_MPa_t block is the default unit system precomputed. The loader does not
    read that last one -- it re-derives it from ``si`` -- which is what makes
    ``test_shipped_cards_match_recomputed_conversion`` able to catch a data file
    that went stale after a factor changed.
    """
    default_value, default_unit = convert(parsed["si"], parsed["dimension"])
    return {
        "fcmat_key": card_key,
        "raw": parsed["raw"],
        "raw_unit": parsed["raw_unit"],
        "parsed_unit": parsed["unit"],
        "dimension": parsed["dimension"],
        "si": float(parsed["si"]),
        "si_unit": parsed["si_unit"],
        DEFAULT_UNITS: default_value,
        "%s_unit" % DEFAULT_UNITS: default_unit,
    }


def consistency_notes(properties: dict, plastic: dict | None,
                      flat: dict) -> list[str]:
    """Things the upstream card says that disagree with itself.

    Not errors -- the numbers are shipped either way, because editing somebody
    else's measured data is worse than repeating it. But a spec author picking
    a material deserves to see them, so they ride along in the provenance.
    """
    notes: list[str] = []

    if plastic is not None and "UltimateTensileStrength" in flat:
        try:
            uts = parse_quantity(flat["UltimateTensileStrength"], "stress")
        except MaterialLibraryError:
            uts = None
        if uts is not None and plastic["yield"]["si"] > float(uts["si"]):
            notes.append(
                "上游卡片的屈服强度（%s）高于抗拉强度（%s），物理上讲不通；"
                "两个数按原样保留，用之前请自己核对来源。"
                % (plastic["yield"]["raw"], uts["raw"]))

    if "ShearModulus" in flat and "E" in properties and "nu" in properties:
        try:
            shear = parse_quantity(flat["ShearModulus"], "stress")
        except MaterialLibraryError:
            shear = None
        implied = properties["E"]["si"] / (2.0 * (1.0 + properties["nu"]["si"]))
        if shear is not None and float(shear["si"]) > 0 and implied > 0:
            # Percent of the implied value, and the text says so. Against the
            # card's own G the same disagreement reads far larger --
            # PET-Generic's 0.0385 GPa is 97% away from the implied 1.158 GPa
            # but 2908% away from itself -- and a percentage whose base is not
            # stated is a number the reader cannot re-derive. The implied value
            # is the right base because E and nu are the two numbers this
            # dialect actually ships.
            deviation = abs(float(shear["si"]) - implied) / implied
            if deviation > 0.05:
                notes.append(
                    "卡片给的剪切模量是 %s，而由 E 和 ν 推出的 G=E/(2(1+ν)) 是 %.4g Pa，"
                    "相差 %.1f%%（以推出来的值为基准）；说明这张卡不是严格各向同性的"
                    "一致数据。本 dialect 只用 E 和 ν，G 不参与计算。"
                    % (shear["raw"], implied, deviation * 100.0))

    return notes


# ---------------------------------------------------------------------------
# The library on disk
# ---------------------------------------------------------------------------

def _normalise_name(name: str) -> str:
    """Lookup key: case, hyphen, underscore and space all folded away."""
    return "".join(ch for ch in str(name).lower()
                   if ch.isalnum())


@functools.lru_cache(maxsize=1)
def _index() -> dict[str, dict]:
    """Every shipped card, keyed by file stem, read once per process.

    Read from the directory rather than from a generated index file: an index
    is a second copy of the truth, and the failure mode of a stale one is a
    material that lists but does not load. Twenty small JSON files is not a
    cost worth introducing that for.
    """
    if not CARD_DIR.is_dir():
        raise MaterialLibraryError(
            "材料库目录不存在：%s。它应该随仓库一起分发；"
            "如果是自己从源码跑，请先执行 data/materials/build_library.py 生成。"
            % CARD_DIR)

    cards: dict[str, dict] = {}
    for path in sorted(CARD_DIR.glob("*.json")):
        try:
            card = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise MaterialLibraryError(
                "材料卡 %s 读不出来：%s" % (path.name, exc))
        if card.get("schema") != CARD_SCHEMA:
            raise MaterialLibraryError(
                "材料卡 %s 的 schema 是 %r，本模块只认 %r。"
                % (path.name, card.get("schema"), CARD_SCHEMA))
        if not isinstance(card.get("name"), str) or not card["name"]:
            raise MaterialLibraryError(
                "材料卡 %s 没有 name 字段，取不到。" % path.name)
        if card["name"] in cards:
            raise MaterialLibraryError(
                "两张材料卡都叫 %r（%s 和 %s）。名字是查找键，重名会让其中一张"
                "永远取不到。" % (card["name"],
                                 cards[card["name"]]["source"].get("path"),
                                 card["source"].get("path")))
        cards[card["name"]] = card

    if not cards:
        raise MaterialLibraryError(
            "材料库目录 %s 里一张卡都没有。" % CARD_DIR)
    return cards


@functools.lru_cache(maxsize=1)
def _aliases() -> dict[str, str]:
    """Normalised lookup key -> canonical card name.

    The card's own ``Name`` field is registered as an alias when it differs
    from the file stem, because that is the string FreeCAD's UI shows. An alias
    that two cards both claim resolves to neither: ``_resolve`` refuses it and
    prints both candidates. Silently handing back whichever card the iteration
    reached first is the failure this guards against -- the caller would get a
    material it did not ask for and nothing would say so.
    """
    claims: dict[str, set[str]] = {}
    for name, card in _index().items():
        for candidate in (name, card.get("upstream_name") or ""):
            if candidate:
                claims.setdefault(_normalise_name(candidate), set()).add(name)
    return {key: next(iter(owners))
            for key, owners in claims.items() if len(owners) == 1}


def _claimants(key: str) -> list[str]:
    """Every card a normalised lookup key could mean.

    Recomputed instead of cached alongside _aliases because it is only ever
    asked on the failure path, where one pass over seventeen cards already in
    memory costs nothing and a second cache would be a second thing to
    invalidate.
    """
    owners = set()
    for name, card in _index().items():
        for candidate in (name, card.get("upstream_name") or ""):
            if candidate and _normalise_name(candidate) == key:
                owners.add(name)
    return sorted(owners)


def _summary(card: dict, units: str = DEFAULT_UNITS) -> str:
    props = card["properties"]
    bits = []
    for key, label in (("E", "E"), ("nu", "ν"), ("density", "ρ")):
        entry = props.get(key)
        if entry is None:
            continue
        value, unit = convert(entry["si"], entry["dimension"], units)
        bits.append("%s=%g%s" % (label, value, "" if unit == "-" else " " + unit))
    category = card.get("category") or "未分类"
    return "%s（%s，%s）：%s" % (card["name"], category, card["license"],
                                "，".join(bits))


def list_materials(units: str = DEFAULT_UNITS) -> list[dict]:
    """Every material in the library, with a one-line summary each.

    Each entry is ``{"name", "summary", "license", "category", "description"}``.
    ``name`` is what ``load_material`` takes; ``summary`` carries E, ν and ρ in
    ``units`` so a caller can pick without opening the card.
    """
    _unit_system(units)
    return [
        {
            "name": card["name"],
            "summary": _summary(card, units),
            "license": card["license"],
            "category": card.get("category") or "",
            "description": card.get("description") or "",
        }
        for card in sorted(_index().values(), key=lambda c: c["name"])
    ]


def load_material(name: str, units: str = DEFAULT_UNITS, *,
                  include_plasticity: bool = False) -> tuple[dict, dict]:
    """Return ``(material_block, provenance)`` for a named material.

    ``material_block`` drops straight into a spec's ``material:`` key and
    contains only keys schema/spec_schema.json declares.

    Plasticity is opt-in. Several cards carry a yield strength, and emitting it
    by default would turn a linear-elastic study into an elastoplastic one
    without the spec author asking -- ``runner/build_v2.py`` turns ``yield``
    into a bilinear *Plastic table. When it is left out it is named in
    ``provenance["not_included"]``, so the value is visible without being
    imposed.
    """
    _unit_system(units)
    card = _resolve(name)

    block: dict[str, Any] = {"name": card["name"]}
    reported: dict[str, dict] = {}
    for spec_key, _card_key, _dim in SPEC_PROPERTIES:
        entry = card["properties"].get(spec_key)
        if entry is None:
            continue
        value, unit = convert(entry["si"], entry["dimension"], units)
        block[spec_key] = value
        reported[spec_key] = {
            "value": value,
            "unit": unit,
            "raw": entry["raw"],
            "raw_unit": entry["raw_unit"],
            "parsed_unit": entry["parsed_unit"],
            "si": entry["si"],
            "si_unit": entry["si_unit"],
            "fcmat_key": entry["fcmat_key"],
        }

    # Copied, not referenced: the cards live in a process-wide cache, and a
    # caller that edits what it was handed would corrupt every later load.
    not_included = [dict(entry) for entry in (card.get("unmapped") or [])]
    plastic = card.get("plasticity") or {}
    if plastic:
        entry = plastic["yield"]
        value, unit = convert(entry["si"], entry["dimension"], units)
        if include_plasticity:
            block["yield"] = value
            reported["yield"] = {
                "value": value,
                "unit": unit,
                "raw": entry["raw"],
                "raw_unit": entry["raw_unit"],
                "parsed_unit": entry["parsed_unit"],
                "si": entry["si"],
                "si_unit": entry["si_unit"],
                "fcmat_key": entry["fcmat_key"],
            }
        else:
            not_included.append({
                "fcmat_key": entry["fcmat_key"],
                "raw": entry["raw"],
                "reason": "这张卡有屈服强度（%g %s）。默认不写进 material 块，"
                          "因为写了就会生成 *Plastic，把线弹性分析变成弹塑性分析。"
                          "要用请调 load_material(..., include_plasticity=True)。"
                          % (value, unit),
            })

    provenance = {
        "material": card["name"],
        "units": units,
        "license": card["license"],
        "attribution": attribution_line(card),
        "source": dict(card.get("source") or {}),
        "properties": reported,
        "not_included": not_included,
        "notes": list(card.get("notes") or []),
    }
    return block, provenance


def attribution_line(card: dict) -> str:
    """The credit line CC-BY asks for, per card, ready to paste into a report."""
    source = card.get("source") or {}
    author = source.get("author") or "FreeCAD contributors"
    return ("材料数据 %s 来自 FreeCAD 材料卡 %s，作者 %s，许可 %s，来源 %s"
            % (card["name"], source.get("path") or "?", author,
               card["license"], source.get("url") or source.get("raw_url") or "?"))


def _resolve(name: str) -> dict:
    cards = _index()
    if name in cards:
        return cards[name]
    key = _normalise_name(name)
    alias = _aliases().get(key)
    if alias:
        return cards[alias]

    clashing = _claimants(key)
    if len(clashing) > 1:
        raise MaterialLibraryError(
            "%r 在库里同时是 %s 的名字，指的是哪一张卡没有依据可判，所以不猜。"
            "请改用文件名那一个（data/materials/freecad/<名字>.json 的名字）。"
            % (name, "、".join(clashing)))

    close = difflib.get_close_matches(key, list(_aliases()), n=5, cutoff=0.5)
    suggestions = []
    for match in close:
        owner = _aliases()[match]
        if owner not in suggestions:
            suggestions.append(owner)
    hint = ("最接近的是：%s。" % "、".join(suggestions) if suggestions
            else "库里一共 %d 种，用 list_materials() 看全部。" % len(cards))
    raise MaterialLibraryError(
        "材料库里没有 %r。%s材料卡在 data/materials/freecad/，"
        "一个材料一个文件；要加新材料请把它的 .FCMat 放进去后跑 "
        "data/materials/build_library.py。" % (name, hint))


# ---------------------------------------------------------------------------
# Spec integration
# ---------------------------------------------------------------------------

# The keys a `library:` block may carry that are not material properties. Every
# other key is an override of the card, and every override is recorded -- a
# number that came from the spec and a number that came from FreeCAD must never
# be indistinguishable in the report.
_LIBRARY_CONTROL_KEYS = ("library", "name", "plasticity")


def resolve_spec_materials(spec: dict) -> tuple[dict, list[dict]]:
    """Expand every ``library:`` reference in a spec into the numbers it names.

    Returns ``(spec, provenance)``. The spec is a copy -- the caller's dict is
    never edited, because a run that fails halfway through resolution must leave
    the spec it was handed exactly as it found it.

    Deliberately done at LOAD time, before validation and before the run id is
    taken, so that:

      * schema/spec_schema.json sees a material block with real numbers in it
        and applies the same rules it applies to a hand-written one;
      * runner/build_v2.py needs no branch at all -- the deck a library material
        produces is byte-identical to the deck the same numbers typed by hand
        produce, which is what makes the frozen baselines comparable;
      * the run id, which hashes the spec, changes when the library data does.
        That is the correct behaviour and not an inconvenience: different
        numbers are a different model.

    A key written alongside ``library:`` overrides the card. That is the point
    -- "steel, but our yield" is the common case -- but the override is listed
    in the provenance with both values, so a report can say which number the
    analysis actually used and where the other one came from.
    """
    provenance: list[dict] = []
    if not isinstance(spec, dict):
        return spec, provenance

    units = str((spec.get("meta") or {}).get("units") or DEFAULT_UNITS)
    out = dict(spec)

    single = out.get("material")
    if isinstance(single, dict) and "library" in single:
        block, prov = _resolve_block(single, units, "material")
        out["material"] = block
        provenance.append(prov)

    many = out.get("materials")
    if isinstance(many, list):
        resolved = []
        for index, entry in enumerate(many):
            if isinstance(entry, dict) and "library" in entry:
                block, prov = _resolve_block(
                    entry, units, "materials[%d]" % index)
                resolved.append(block)
                provenance.append(prov)
            else:
                resolved.append(entry)
        out["materials"] = resolved

    return out, provenance


def _resolve_block(entry: dict, units: str, where: str) -> tuple[dict, dict]:
    """One ``library:`` block -> the material block plus where it came from."""
    card_name = entry["library"]
    if not isinstance(card_name, str) or not card_name.strip():
        raise MaterialLibraryError(
            "%s 的 library 必须是材料名（字符串），现在是 %r。"
            "用 list_materials() 看库里有哪些。" % (where, card_name))

    want_plastic = bool(entry.get("plasticity", False))
    block, prov = load_material(card_name, units,
                               include_plasticity=want_plastic)

    # The spec may rename it, and the rename is passed through unchecked on
    # purpose: schema/spec_schema.json types material.name as a bare string
    # with no pattern -- `{"name": "My Steel! 1.0", ...}` validates, measured --
    # so a `library:` block that refused it would be stricter than typing the
    # same numbers by hand, and the two paths have to produce the same deck.
    # Card names are checked at build time by _SAFE_NAME instead; all 17 of
    # them also satisfy the schema's `definitions/identifier`.
    spec_name = entry.get("name")
    if spec_name is not None:
        block["name"] = str(spec_name)

    overrides = []
    for key, value in entry.items():
        if key in _LIBRARY_CONTROL_KEYS:
            continue
        overrides.append({
            "key": key,
            "spec_value": value,
            "card_value": block.get(key),
            "note": ("卡里没有这个键，spec 直接提供" if key not in block
                     else "spec 覆盖了材料卡的值"),
        })
        block[key] = value

    missing = [key for key in REQUIRED_SPEC_KEYS if key not in block]
    if missing:
        raise MaterialLibraryError(
            "材料卡 %r 没有 %s，无法单独构成 %s 的材料块——"
            "spec 的 material 块必须有 E 和 ν。要么在同一个块里补上，"
            "要么换一张卡。这张卡有：%s。"
            % (card_name, "、".join(missing), where,
               "、".join(sorted(k for k in block if k != "name"))))

    prov["spec_path"] = where
    prov["spec_name"] = block["name"]
    prov["overrides"] = overrides
    prov["plasticity_requested"] = want_plastic
    return block, prov
