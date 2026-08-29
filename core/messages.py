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
    instead of ``backend.select.abaqus_not_found``.
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

    # -- backend selection -------------------------------------------------
    "backend.select.bad_env_value": {
        "zh": "{env}={value} 不是合法取值（只能是 auto 或 abaqus）",
        "en": "{env}={value} is not a valid setting (choose auto or abaqus)",
    },
    "backend.select.bad_env_hint": {
        "zh": "这个工具只驱动 Abaqus，{env} 只能设成 auto 或 abaqus",
        "en": "This tool drives Abaqus only; {env} must be either auto or abaqus",
    },
    "backend.select.abaqus_not_found": {
        "zh": "没有找到 Abaqus。这是一个驱动 Abaqus 的工具，没有它就没有可求解的对象："
              "把 abaqus.bat 加进 PATH，或用 {env} 指定它的完整路径",
        "en": "Abaqus not found. This tool drives Abaqus, so without it there is nothing "
              "to solve: put abaqus.bat on PATH, or set {env} to its full path",
    },
    "backend.select.abaqus_auto": {
        "zh": "检测到 Abaqus，使用它求解",
        "en": "Abaqus detected; solving with it",
    },
    "backend.select.abaqus_explicit": {
        "zh": "用户指定 Abaqus",
        "en": "Abaqus was requested explicitly",
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
    # Says what ran, not what it sounds like. `_dry_build_notes` calls
    # `generate_script`, which COMPILES the CAE script and never starts CAE --
    # so every selector in the spec is still unresolved at this point.
    # Measured 2026-08-18: a frame proposal announced "模型试建" and then failed
    # the real build on `LeftColPlate:face@r=9&at=115,60,8 matched 0 faces`,
    # because `at=` is in assembly coordinates and the spec used part-local
    # ones. Nothing before CAE could have known. Claiming a build here is the
    # NG-12 mistake in the product's own voice.
    "planner.deepseek_used": {
        "zh": "已由 DeepSeek 生成 spec 提案（云端 LLM），提案已通过 schema 校验、KPI 干检"
              "与建模脚本生成。注意：脚本只是生成，没有启动 CAE，选择器要到真机建模时"
              "才解析——选错面这类问题在这一步看不出来。",
        "en": "Proposed a spec with DeepSeek (cloud LLM); the proposal passed the schema, "
              "the KPI dry check, and the model script compiled. Note the script was only "
              "generated — CAE was not started, so every selector is still unresolved and a "
              "selector that matches nothing cannot be seen at this stage.",
    },
    "planner.deepseek_failed": {
        "zh": "DeepSeek 规划失败：{error}",
        "en": "DeepSeek planning failed: {error}",
    },
    "planner.deepseek_selection_unaimed": {
        "zh": "已看到你 @ 的：{labels}。DeepSeek 每次从头生成整份 spec、看不到当前模型，"
              "@ 引用只有 Claude 后端能精确落到对象上。",
        "en": "Saw your @-mentions: {labels}. DeepSeek writes a whole spec from scratch and "
              "does not see the current model; only the Claude backend can aim an edit at "
              "an object.",
    },

}
