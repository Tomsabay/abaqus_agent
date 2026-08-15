"""One catalogue for text that reaches a human, in Chinese and English.

The users this is built for are Chinese-speaking simulation engineers, so
Chinese is the source language and the fallback: a missing English string
shows the Chinese one, never a bare key.

Why a catalogue rather than translating at the call site: a refusal is stored
in ``result.json`` and read back months later, possibly by someone reading in
the other language. So the pipeline records a *key* plus parameters and
renders at display time — the same reason a timestamp is stored as an instant
and formatted at the edge.

The frontend gets this catalogue from ``GET /api/i18n/messages?lang=...``
rather than keeping its own copy of it. One catalogue, two consumers; a
translation fixed here is fixed everywhere, and the two can never drift into
saying different things about the same refusal.
"""

from __future__ import annotations

import locale
import os

ENV_LANG = "ABAQUS_AGENT_LANG"
SUPPORTED = ("zh", "en")
DEFAULT = "zh"

# Keys asked for but not in the catalogue. Tests assert this stays empty; a
# runtime lookup still returns something usable rather than raising, because a
# missing translation must never be the reason a solve fails.
_missing: set[str] = set()


def resolve_lang(requested: str | None = None) -> str:
    """Pick a language from an explicit request, the environment, or the OS.

    Accepts anything an ``Accept-Language`` header might hold, so
    ``zh-CN,zh;q=0.9`` resolves to ``zh``.
    """
    for candidate in (requested, os.environ.get(ENV_LANG)):
        if not candidate:
            continue
        for chunk in str(candidate).split(","):
            tag = chunk.split(";")[0].strip().lower()
            if tag.startswith("zh"):
                return "zh"
            if tag.startswith("en"):
                return "en"
    try:
        system = (locale.getlocale()[0] or "").lower()
    except (ValueError, TypeError):
        system = ""
    return "zh" if system.startswith(("zh", "chinese")) else "en" if system else DEFAULT


def render(key: str, lang: str | None = None, *, fallback: str = "", **params) -> str:
    """Look up ``key``; interpolate ``params``; fall back rather than raise.

    ``fallback`` is the Chinese text the producer already had on hand. It is
    used when the key is unknown, which keeps a stale key showing real prose
    instead of ``ccx.load.blast``.
    """
    lang = resolve_lang(lang)
    entry = CATALOGUE.get(key)
    if entry is None:
        _missing.add(key)
        return (fallback or key).format(**params) if params else (fallback or key)
    text = entry.get(lang) or entry.get(DEFAULT) or fallback or key
    return text.format(**params) if params else text


def catalogue_for(lang: str | None = None) -> dict[str, str]:
    """Flat {key: text} for one language — what the frontend registers."""
    lang = resolve_lang(lang)
    return {key: (entry.get(lang) or entry.get(DEFAULT, key))
            for key, entry in CATALOGUE.items()}


def missing_keys() -> list[str]:
    return sorted(_missing)


# ---------------------------------------------------------------------------
# Catalogue
#
# Keep the Chinese verbatim from where it was written. The English is a
# translation of the same claim, not a softened version of it: a refusal that
# reads as an apology in one language and a technical fact in the other is two
# different products.
# ---------------------------------------------------------------------------

CATALOGUE: dict[str, dict[str, str]] = {

    # -- backend labels ----------------------------------------------------
    "backend.label.abaqus_unknown_version": {
        "zh": "Abaqus（版本未探测到）",
        "en": "Abaqus (version not detected)",
    },
    "backend.label.calculix_unknown_version": {
        "zh": "CalculiX（版本未探测到）",
        "en": "CalculiX (version not detected)",
    },
    "backend.label.demo": {
        "zh": "演示模式（未检测到求解器）",
        "en": "Demo mode (no solver detected)",
    },

    # -- backend selection -------------------------------------------------
    "backend.select.bad_env_value": {
        "zh": "{env}={value} 不是合法取值（可选 auto/abaqus/calculix/demo）",
        "en": "{env}={value} is not a valid setting (choose auto, abaqus, calculix or demo)",
    },
    "backend.select.bad_env_hint": {
        "zh": "求解器后端只能设成 auto、abaqus、calculix 或 demo",
        "en": "The solver backend must be one of auto, abaqus, calculix or demo",
    },
    "backend.select.demo_requested": {
        "zh": "用户显式要求演示模式",
        "en": "Demo mode was explicitly requested",
    },
    "backend.select.abaqus_requested_missing": {
        "zh": "用户显式指定 Abaqus，但机器上找不到它",
        "en": "Abaqus was explicitly requested but is not installed on this machine",
    },
    "backend.select.abaqus_not_found": {
        "zh": "没有找到 Abaqus：把 abaqus.bat 加进 PATH，或用 {env} 指定完整路径",
        "en": "Abaqus not found: put abaqus.bat on PATH, or set {env} to its full path",
    },
    "backend.select.abaqus_auto": {
        "zh": "检测到 Abaqus，使用主后端求解",
        "en": "Abaqus detected; solving on the primary backend",
    },
    "backend.select.abaqus_explicit": {
        "zh": "用户指定 Abaqus",
        "en": "Abaqus was requested explicitly",
    },
    "backend.select.calculix_requested_missing": {
        "zh": "用户显式指定 CalculiX，但机器上找不到它",
        "en": "CalculiX was explicitly requested but is not installed on this machine",
    },
    "backend.select.calculix_not_found": {
        "zh": "没有找到 CalculiX：把 ccx 加进 PATH，或用 {env} 指定 ccx.exe 的完整路径",
        "en": "CalculiX not found: put ccx on PATH, or set {env} to the full path of ccx.exe",
    },
    "backend.select.calculix_no_version": {
        "zh": "读不到 CalculiX 自报的版本号（ccx -v），无法确认能力边界，宁可拒绝也不猜",
        "en": "CalculiX will not report its own version (ccx -v). Without it the capability "
              "boundary cannot be established, and refusing beats guessing",
    },
    "backend.select.calculix_fallback": {
        "zh": "未检测到 Abaqus，降级到 CalculiX（仅支持已验证的功能子集）",
        "en": "No Abaqus detected; falling back to CalculiX (verified subset only)",
    },
    "backend.select.calculix_explicit": {
        "zh": "用户指定 CalculiX",
        "en": "CalculiX was requested explicitly",
    },
    "backend.select.no_solver": {
        "zh": "未检测到 Abaqus，也未检测到 CalculiX：只能演示流程，不产生任何数值",
        "en": "Neither Abaqus nor CalculiX detected: the pipeline can be demonstrated, "
              "but no number will be produced",
    },

    # -- offline planner replies -------------------------------------------
    # These land in the chat as the assistant's own words. Unlike a refusal in
    # result.json they are not re-read years later, so they are rendered once
    # in the language the UI was in when the message was sent, and the
    # transcript keeps that language — the same way a human conversation does.
    "planner.template_used": {
        "zh": "已用模板引擎生成 spec 提案（离线模式，按关键词推断）。",
        "en": "Proposed a spec with the template engine (offline; inferred from keywords).",
    },
    "planner.release_is_placeholder": {
        "zh": "⚠ 未检测到已安装的 Abaqus，spec 里的版本号 {release} 是占位默认值、不是实测结果；"
              "真正求解时会以运行时探测到的版本为准。",
        "en": "⚠ No installed Abaqus was detected, so the release {release} in this spec is "
              "a placeholder rather than a measurement. The actual solve uses whatever "
              "release is detected at run time.",
    },
    "planner.open_questions": {
        "zh": "待确认信息：",
        "en": "Still to confirm: ",
    },
    "planner.claude_failed": {
        "zh": "Claude 规划失败：{error}",
        "en": "Claude planning failed: {error}",
    },
    "planner.claude_failed_fallback": {
        "zh": "（Claude 规划失败已降级模板：{error}）",
        "en": "(Claude planning failed; fell back to the template engine: {error})",
    },
    "planner.cli_unavailable": {
        "zh": "claude CLI 不可用（未安装或不在 PATH）。",
        "en": "The claude CLI is not available (not installed, or not on PATH).",
    },

    # -- how to lift a CalculiX refusal ------------------------------------
    # Carries its own leading separator so a refusal is composed by plain
    # concatenation. Otherwise every consumer — Python, and the JS that renders
    # the same refusal in the browser — would need its own copy of the rule
    # that Chinese joins with 。 and English with a full stop and a space.
    "ccx.howto": {
        "zh": "。如需这项功能请安装 Abaqus（设置 {env} 指向 abaqus.bat）",
        "en": ". Install Abaqus to use this (point {env} at abaqus.bat)",
    },

    # -- geometry ----------------------------------------------------------
    "ccx.geometry.plate_with_hole": {
        "zh": "带孔平板需要 Abaqus/CAE 划分曲边网格，本项目没有自带的自由网格器；"
              "凑合近似会直接改变应力集中系数 Kt，所以拒绝",
        "en": "A plate with a hole needs Abaqus/CAE to mesh the curved edge, and this "
              "project ships no free mesher of its own. Approximating the hole would "
              "change the stress concentration factor Kt itself, so it is refused",
    },
    "ccx.geometry.square_plate": {
        "zh": "壳单元模型尚未在 CalculiX 上验证过（ccx 内部会把壳展开成三维实体，"
              "节点编号和应力定义都不同），未验证的东西不上线",
        "en": "Shell models have not been verified on CalculiX (ccx expands shells into "
              "3D solids internally, changing both node numbering and the stress "
              "definition). Unverified means unsupported",
    },
    "ccx.geometry.axisymmetric_disk": {
        "zh": "轴对称模型尚未在 CalculiX 上验证过基准值，未验证的东西不上线",
        "en": "Axisymmetric models have no CalculiX baseline comparison yet. "
              "Unverified means unsupported",
    },
    "ccx.geometry.beam_frame": {
        "zh": "梁模型在 CalculiX 里会被展开成三维实体单元，结果是剪切柔性的、"
              "和 Abaqus 的梁理论不是一个量纲的答案",
        "en": "CalculiX expands beam models into 3D solid elements. The result is "
              "shear-flexible and is not the same quantity Abaqus beam theory returns",
    },
    "ccx.geometry.composite_plate": {
        "zh": "CalculiX 的复合材料铺层只支持 S8R/S6 单元，且铺层角要写成命名 *ORIENTATION，"
              "没有忠实的自动转换办法",
        "en": "CalculiX composite layups support only S8R/S6 elements and require ply "
              "angles as named *ORIENTATION cards; there is no faithful automatic "
              "translation",
    },
    "ccx.geometry.cohesive_layer": {
        "zh": "CalculiX 没有 cohesive 单元族（COH3D8/COH3D6/COH2D4 全部报错）",
        "en": "CalculiX has no cohesive element family (COH3D8/COH3D6/COH2D4 all error out)",
    },
    "ccx.geometry.unsupported": {
        "zh": "CalculiX 后端不支持这种几何类型",
        "en": "The CalculiX backend does not support this geometry type",
    },

    # -- assembly dialect --------------------------------------------------
    "ccx.spec.assembly_dialect": {
        "zh": "多零件装配（parts / assembly / interactions）要靠 Abaqus/CAE 建实体、"
              "划网格、按面选区域；CalculiX 只吃已经划好网格的 .inp，本项目没有自带的"
              "几何内核和网格器，装配这一段没法自己生成。绑定和接触也还没在 CalculiX 上"
              "比对过基准值",
        "en": "A multi-part assembly (parts / assembly / interactions) relies on Abaqus/CAE "
              "to build the solids, mesh them, and pick regions by face. CalculiX only "
              "consumes an already-meshed .inp, and this project ships neither a geometry "
              "kernel nor a mesher, so the assembly stage cannot be generated. Ties and "
              "contact also have no CalculiX baseline comparison yet",
    },

    # -- step type ---------------------------------------------------------
    "ccx.step.frequency": {
        "zh": "模态分析尚未在 CalculiX 上比对过基准频率；ccx 有 *FREQUENCY 关键字，"
              "但没验证过就说支持，等于让这套「诚实降级」的界面自己说谎",
        "en": "Modal analysis has no CalculiX baseline frequency comparison yet. ccx does "
              "have the *FREQUENCY keyword, but calling it supported on that basis would "
              "make an interface built on honest degradation lie about itself",
    },
    "ccx.step.dynamic_implicit": {
        "zh": "隐式动力学尚未在 CalculiX 上比对过基准值",
        "en": "Implicit dynamics has no CalculiX baseline comparison yet",
    },
    "ccx.step.dynamic_explicit": {
        "zh": "CalculiX 的显式积分没有 Abaqus/Explicit 的沙漏控制和接触阻尼，"
              "算得出数但物理上不等价",
        "en": "CalculiX explicit integration has neither Abaqus/Explicit's hourglass "
              "control nor its contact damping. It will produce a number, but not a "
              "physically equivalent one",
    },
    "ccx.step.coupled_temp_disp": {
        "zh": "热-力耦合尚未在 CalculiX 上比对过基准值",
        "en": "Coupled temperature-displacement has no CalculiX baseline comparison yet",
    },
    "ccx.step.coupled_thermal_electrical": {
        "zh": "CalculiX 根本没有热-电耦合分析类型：它会忽略这张卡、退出码仍然是 0，"
              "然后给你一个没算过的结果",
        "en": "CalculiX has no coupled thermal-electrical analysis at all: it ignores the "
              "card, still exits 0, and hands back a result it never computed",
    },
    "ccx.step.unsupported": {
        "zh": "CalculiX 后端只验证过 Static 分析步",
        "en": "Only the Static step has been verified on the CalculiX backend",
    },
    "ccx.step.nlgeom": {
        "zh": "几何非线性尚未在 CalculiX 上比对过基准值；对非线性请求悄悄给一个线性答案，"
              "正是这套门禁要防的错",
        "en": "Geometric nonlinearity has no CalculiX baseline comparison yet, and quietly "
              "answering a nonlinear request with a linear result is precisely the mistake "
              "this gate exists to prevent",
    },
    "ccx.step.adaptive_mesh": {
        "zh": "CalculiX 没有自适应网格/ALE 重划分",
        "en": "CalculiX has no adaptive meshing or ALE remeshing",
    },
    "ccx.step.parametric_sweep": {
        "zh": "参数扫掠目前只在 Abaqus 后端实现",
        "en": "Parametric sweeps are implemented on the Abaqus backend only",
    },
    "ccx.runner.no_mpi": {
        "zh": "这个 CalculiX 构建没有 MPI 并行，只能用线程（OMP_NUM_THREADS）。"
              "把 mp_mode 改成 threads 即可继续",
        "en": "This CalculiX build has no MPI parallelism, only threads "
              "(OMP_NUM_THREADS). Set mp_mode to threads to continue",
    },

    # -- loads -------------------------------------------------------------
    "ccx.load.blast_conwep": {
        "zh": "CalculiX 不认识 CONWEP 爆炸载荷：实测它会静默丢掉这张卡、退出码 0、"
              "所有位移输出 0.000000E+00 —— 这是最危险的一种错，必须拒绝",
        "en": "CalculiX does not recognise the CONWEP blast load. Measured behaviour: it "
              "silently drops the card, exits 0, and reports every displacement as "
              "0.000000E+00 — the most dangerous failure there is, so it must be refused",
    },
    "ccx.load.pressure": {
        "zh": "压力载荷需要把 Abaqus 的面名转成 ccx 的单元面编号，尚未验证",
        "en": "Pressure loads require translating Abaqus surface names into ccx element "
              "face numbering, which has not been verified yet",
    },
    "ccx.load.displacement": {
        "zh": "强制位移载荷尚未在 CalculiX 上验证",
        "en": "Prescribed displacement loads have not been verified on CalculiX",
    },
    "ccx.load.temperature": {
        "zh": "温度载荷尚未在 CalculiX 上验证",
        "en": "Temperature loads have not been verified on CalculiX",
    },
    "ccx.load.heat_flux": {
        "zh": "热流载荷尚未在 CalculiX 上验证",
        "en": "Heat flux loads have not been verified on CalculiX",
    },
    "ccx.load.body_heat_flux": {
        "zh": "体热流载荷尚未在 CalculiX 上验证",
        "en": "Body heat flux loads have not been verified on CalculiX",
    },
    "ccx.load.unsupported": {
        "zh": "CalculiX 后端未验证这种载荷类型",
        "en": "This load type has not been verified on the CalculiX backend",
    },
    "ccx.load.thermal_bc": {
        "zh": "热边界条件（对流/辐射）在 CalculiX 里要写成单元面编号形式，尚未验证",
        "en": "Thermal boundary conditions (convection/radiation) must be written as "
              "element face numbers in CalculiX, which has not been verified",
    },

    # -- material ----------------------------------------------------------
    "ccx.material.conductivity": {
        "zh": "CalculiX 没有热-电耦合分析，电导率无处可用",
        "en": "CalculiX has no coupled thermal-electrical analysis, so conductivity has "
              "nowhere to be used",
    },
    "ccx.material.fracture_energy": {
        "zh": "CalculiX 没有 cohesive 单元，断裂能没有对应模型",
        "en": "CalculiX has no cohesive elements, so fracture energy has no counterpart",
    },
    "ccx.material.max_traction": {
        "zh": "CalculiX 没有 cohesive 单元，最大牵引力没有对应模型",
        "en": "CalculiX has no cohesive elements, so maximum traction has no counterpart",
    },
    "ccx.material.plasticity": {
        "zh": "塑性材料尚未在 CalculiX 上比对过基准值",
        "en": "Plasticity has no CalculiX baseline comparison yet",
    },
    "ccx.material.multi_material": {
        "zh": "多材料/正交异性材料尚未在 CalculiX 上验证",
        "en": "Multi-material and orthotropic definitions have not been verified on CalculiX",
    },

    # -- KPIs --------------------------------------------------------------
    "ccx.kpi.eigenfrequency": {
        "zh": "特征频率 KPI 依赖模态分析，后者尚未在 CalculiX 上验证",
        "en": "An eigenfrequency KPI depends on modal analysis, which has not been "
              "verified on CalculiX",
    },
    "ccx.kpi.history_output_max": {
        "zh": "CalculiX 没有 history region 输出，能量分量只出现在控制台文字里；"
              "去正则匹配控制台文本凑一个数，正是 G2 门禁要挡的那种无出处数值",
        "en": "CalculiX has no history region output; energy components appear only in "
              "console text. Regex-scraping a number out of console text is exactly the "
              "kind of unsourced value this project refuses to report",
    },
    "ccx.kpi.unsupported": {
        "zh": "CalculiX 后端不支持这种 KPI",
        "en": "The CalculiX backend does not support this KPI type",
    },
    "ccx.kpi.location_whole_model_only": {
        "zh": "CalculiX 的 .frd 场输出是全模型块，无法按集合取值；"
              "这个 KPI 在 CalculiX 上只能对整个模型取极值",
        "en": "CalculiX .frd field output comes in whole-model blocks and cannot be read "
              "at a named set, so on CalculiX this KPI can only take an extremum over the "
              "whole model",
    },
    "ccx.kpi.stress_not_comparable": {
        "zh": "应力类 KPI 会照常输出，但 CalculiX 给的是 .frd 里相邻单元平均后的节点应力，"
              "Abaqus 给的是不平均的 ELEMENT_NODAL 外插值 —— 同一个网格上实测差约 6%。"
              "这个数会带定义标签输出，且不参与与 Abaqus 基准的达标判定",
        "en": "Stress KPIs are still produced, but CalculiX reports nodal stress averaged "
              "across adjacent elements in the .frd, where Abaqus reports an unaveraged "
              "ELEMENT_NODAL extrapolation — measured ~6% apart on the same mesh. The "
              "number is tagged with its definition and takes no part in pass/fail "
              "against an Abaqus baseline",
    },

    # -- custom .inp -------------------------------------------------------
    "ccx.custom_inp.flattened": {
        "zh": "自带 .inp 会先被展平成 CalculiX 格式（去掉 *Part/*Assembly/*Instance、"
              "改写 ENCASTRE），再逐张卡做白名单检查；出现任何未验证的关键字都会直接拒绝，"
              "而不是交给求解器静默忽略",
        "en": "A supplied .inp is first flattened into CalculiX form (*Part/*Assembly/"
              "*Instance removed, ENCASTRE rewritten), then checked card by card against "
              "an allowlist. Any unverified keyword is refused outright rather than handed "
              "to the solver to ignore in silence",
    },
}
