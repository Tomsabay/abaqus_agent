"""Limit table loading and code-side verdicts for generated calculation reports.

BUILD_SPEC W20 criterion 3: the *file* owns the engineering judgement, not a
model. Every entry must carry ``value`` / ``unit`` / ``source``; a KPI without a
limit stays explicitly unjudged, and a report built without a limit file gets no
conclusion section at all (see ``NO_LIMITS_NOTICE``).

Pure stdlib + PyYAML: importable from the frozen bundle and from tests without
python-docx / openpyxl.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

VERDICT_OK = "满足"
VERDICT_FAIL = "不满足"
VERDICT_NONE = "未设限值（不判定）"

OVERALL_OK = f"总体判定：{VERDICT_OK}"
OVERALL_FAIL = f"总体判定：{VERDICT_FAIL}"

NO_LIMITS_NOTICE = (
    "未提供限值表：本工具不做工程判定，已跳过结论段。"
    "请用 --limits 指定限值文件（示例：course/materials/module5/limits.yaml，"
    "每条限值须含 value / unit / source 三字段）后重跑。"
)

REQUIRED_FIELDS = ("value", "unit", "source")
DIRECTIONS = ("max", "min")


class LimitsError(ValueError):
    """Raised when a limit file is missing, unreadable, or incomplete."""


@dataclass(frozen=True)
class Limit:
    """One limit row: the number, its unit, and where the number came from."""

    name: str
    value: float
    unit: str
    source: str
    label: str = ""
    direction: str = "max"
    absolute: bool = False

    @property
    def relation(self) -> str:
        return "≤" if self.direction == "max" else "≥"


@dataclass(frozen=True)
class Judgement:
    """Code-computed comparison of one KPI against one limit."""

    name: str
    label: str
    actual: float
    compared: float
    limit: Limit | None
    utilisation_pct: float | None
    verdict: str

    @property
    def judged(self) -> bool:
        return self.limit is not None

    @property
    def ok(self) -> bool:
        return self.verdict == VERDICT_OK

    @property
    def unit(self) -> str:
        return self.limit.unit if self.limit else ""

    @property
    def source(self) -> str:
        return self.limit.source if self.limit else ""


def format_number(value: Any) -> str:
    """Format a KPI/limit number for report text (5 significant digits)."""
    if value is None:
        return "-"
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, (int, float)):
        if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
            return str(value)
        return "%.5g" % value
    return str(value)


def format_pct(value: float | None) -> str:
    """Format a utilisation ratio as a percentage string."""
    if value is None:
        return "-"
    return "%.1f%%" % value


def load_limits(path: str | Path) -> dict[str, Limit]:
    """Load a limit table keyed by KPI name.

    Accepts either a top-level ``limits:`` mapping or a bare mapping of KPI
    name -> entry. Raises LimitsError on any missing/invalid field so a bad
    limit file can never silently degrade into "no limit, no verdict".
    """
    limits_path = Path(path)
    if not limits_path.is_file():
        raise LimitsError(f"限值文件不存在：{limits_path}")
    try:
        raw = yaml.safe_load(limits_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise LimitsError(f"限值文件不是合法 YAML：{limits_path}: {e}") from e
    if not isinstance(raw, dict):
        raise LimitsError(f"限值文件顶层必须是映射：{limits_path}")
    table = raw.get("limits", raw)
    if not isinstance(table, dict) or not table:
        raise LimitsError(f"限值文件不含任何限值条目：{limits_path}")

    limits: dict[str, Limit] = {}
    for name, entry in table.items():
        if name == "meta":
            continue
        if not isinstance(entry, dict):
            raise LimitsError(f"限值条目 {name} 必须是映射（含 value/unit/source）")
        missing = [field for field in REQUIRED_FIELDS if entry.get(field) in (None, "")]
        if missing:
            raise LimitsError(f"限值条目 {name} 缺少字段：{', '.join(missing)}")
        try:
            value = float(entry["value"])
        except (TypeError, ValueError) as e:
            raise LimitsError(f"限值条目 {name} 的 value 不是数值：{entry['value']!r}") from e
        direction = str(entry.get("direction", "max")).strip().lower()
        if direction not in DIRECTIONS:
            raise LimitsError(f"限值条目 {name} 的 direction 必须是 max 或 min，收到 {direction!r}")
        if value == 0.0:
            raise LimitsError(f"限值条目 {name} 的 value 不能为 0（利用率无法定义）")
        limits[str(name)] = Limit(
            name=str(name),
            value=value,
            unit=str(entry["unit"]),
            source=str(entry["source"]),
            label=str(entry.get("label", "")),
            direction=direction,
            absolute=bool(entry.get("absolute", False)),
        )
    if not limits:
        raise LimitsError(f"限值文件不含任何限值条目：{limits_path}")
    return limits


def judge_kpi(name: str, actual: Any, limit: Limit | None) -> Judgement:
    """Compare one KPI value against one limit (pure arithmetic, no inference)."""
    numeric = isinstance(actual, (int, float)) and not isinstance(actual, bool)
    if limit is None or not numeric:
        return Judgement(
            name=name,
            label=limit.label if limit else "",
            actual=actual if numeric else float("nan"),
            compared=float(actual) if numeric else float("nan"),
            limit=None,
            utilisation_pct=None,
            verdict=VERDICT_NONE,
        )
    value = float(actual)
    compared = abs(value) if limit.absolute else value
    if limit.direction == "max":
        ok = compared <= limit.value
        utilisation = compared / limit.value * 100.0
    else:
        ok = compared >= limit.value
        utilisation = limit.value / compared * 100.0 if compared != 0 else float("inf")
    return Judgement(
        name=name,
        label=limit.label or name,
        actual=value,
        compared=compared,
        limit=limit,
        utilisation_pct=utilisation,
        verdict=VERDICT_OK if ok else VERDICT_FAIL,
    )


def judge_kpis(kpis: dict[str, Any], limits: dict[str, Limit]) -> list[Judgement]:
    """Judge every KPI in ``kpis`` (stable order: input order)."""
    return [judge_kpi(name, value, limits.get(name)) for name, value in kpis.items()]


def overall_verdict(judgements: list[Judgement]) -> str:
    """Overall verdict line: FAIL if any judged KPI fails, else OK."""
    judged = [j for j in judgements if j.judged]
    if not judged:
        return VERDICT_NONE
    return VERDICT_OK if all(j.ok for j in judged) else VERDICT_FAIL


def max_utilisation(judgements: list[Judgement]) -> Judgement | None:
    """The judged KPI with the highest utilisation, or None when nothing judged."""
    judged = [j for j in judgements if j.judged and j.utilisation_pct is not None]
    if not judged:
        return None
    return max(judged, key=lambda j: j.utilisation_pct or 0.0)


def conclusion_lines(
    judgements: list[Judgement],
    limits_path: str | Path | None,
) -> list[str]:
    """Render the conclusion section as plain text lines.

    With no limit file the only output is NO_LIMITS_NOTICE — the tool refuses to
    conclude rather than letting a model guess (W20 criterion 3).
    """
    if limits_path is None:
        return [NO_LIMITS_NOTICE]
    judged = [j for j in judgements if j.judged]
    unjudged = [j for j in judgements if not j.judged]
    if not judged:
        return [
            "限值表未覆盖本次任何 KPI，无法判定：" + "、".join(j.name for j in unjudged),
            f"限值文件：{limits_path}",
        ]
    failed = [j for j in judged if not j.ok]
    overall = OVERALL_FAIL if failed else OVERALL_OK
    lines = [
        f"按限值表逐项判定：{len(judged)} 项已设限值 KPI 中 "
        f"{len(judged) - len(failed)} 项{VERDICT_OK}、{len(failed)} 项{VERDICT_FAIL}"
        f" —— {overall}。",
    ]
    worst = max_utilisation(judgements)
    if worst is not None and worst.limit is not None:
        lines.append(
            f"最大利用率 {format_pct(worst.utilisation_pct)}"
            f"（{worst.name} {worst.label}：实测 {format_number(worst.compared)} {worst.unit}，"
            f"限值要求 {worst.limit.relation} {format_number(worst.limit.value)} {worst.unit}）。"
        )
    for j in failed:
        assert j.limit is not None
        lines.append(
            f"超限项 {j.name}（{j.label}）：实测 {format_number(j.compared)} {j.unit}，"
            f"未满足「{j.limit.relation} {format_number(j.limit.value)} {j.unit}」，"
            f"利用率 {format_pct(j.utilisation_pct)}，限值来源：{j.source}"
        )
    if unjudged:
        lines.append(
            "限值表未覆盖、本报告不予判定的 KPI："
            + "、".join(j.name for j in unjudged)
            + "（补齐限值后重跑即可判定）。"
        )
    lines.append(
        f"判定依据全部来自限值文件 {limits_path}；比较由代码完成，"
        "报告不含任何由模型推断的工程结论。"
    )
    return lines
