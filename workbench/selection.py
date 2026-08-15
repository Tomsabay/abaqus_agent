"""Resolve chat @-mentions to the spec entries the model tree drew.

WHY THIS IS A RESOLVER AND NOT A GRAMMAR. A mention arrives as a tree row id
(`part:Plate`, `inst:P`, `kpi:J_TIP`), and the one thing that must never happen
is this module growing its own opinion about which spec entry that names —
`model_tree` already decided when it drew the row, and two modules deciding
independently is how the tree and the chat drift apart. So resolution is:
build the same tree, find the row, read the `path` the tree stamped on it,
fetch that path out of the spec. A row the tree did not draw cannot be
mentioned, which is exactly the "selection = what you can see" semantics.

FAIL CLOSED, TO THE USER. A ref that does not resolve — the part was renamed,
the pending proposal dropped it, the id is garbage — raises SelectionError and
the chat endpoint turns that into a 400 naming the ref. Passing an unresolved
mention through to the LLM would have it answer about an object that is not in
the spec, confidently.

The second ref kind, `selector`, is the 3D viewport's: a click on a face
arrives as an already-generated selector expression plus the measurements it
was generated from. It is validated by the same parser the build uses
(`core.selectors.parse`), so an expression the build would refuse is refused
here, before it is ever suggested to the model.
"""

from __future__ import annotations

import re

import yaml

from core import selectors
from workbench.model_tree import build_tree

# One mention's fragment in the prompt. Whole parts with many features can run
# long; the cap keeps one mention from eating the entire prompt budget, and the
# truncation SAYS SO rather than ending mid-line as if that were the entry.
_FRAGMENT_CHARS = 1800
MAX_REFS = 8

_PATH_SEG = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)((?:\[\d+\])*)$")


class SelectionError(ValueError):
    """A mention that does not resolve against the spec being discussed."""


def _fetch(spec: dict, path: str):
    """Walk `parts[0].features[2]` / `outputs.kpis[1]` out of the spec.

    Raises SelectionError naming the path — a path stamped by the tree can
    still dangle when the resolver runs against a different spec text than the
    tree drew (the user kept an old tab open), and that case is the user's to
    see, not to paper over.
    """
    node = spec
    for segment in path.split("."):
        match = _PATH_SEG.match(segment)
        if not match:
            raise SelectionError("路径 %r 不是这棵树会生成的形状" % path)
        key, indexes = match.group(1), match.group(2)
        if not isinstance(node, dict) or key not in node:
            raise SelectionError("spec 里没有 %r（走到 %r 就断了）" % (path, key))
        node = node[key]
        for raw in re.findall(r"\[(\d+)\]", indexes):
            i = int(raw)
            if not isinstance(node, list) or i >= len(node):
                raise SelectionError(
                    "spec 里没有 %r（%s[%d] 越界）" % (path, key, i))
            node = node[i]
    return node


def _find_row(tree: dict, ref: str) -> dict | None:
    def walk(rows):
        for row in rows or []:
            if row.get("id") == ref:
                return row
            hit = walk(row.get("children"))
            if hit is not None:
                return hit
        return None

    for group in tree.get("groups") or []:
        hit = walk(group.get("rows"))
        if hit is not None:
            return hit
    return None


def _fragment(value) -> str:
    text = yaml.dump(value, allow_unicode=True, default_flow_style=False,
                     sort_keys=False).rstrip()
    if len(text) > _FRAGMENT_CHARS:
        text = text[:_FRAGMENT_CHARS].rstrip() + "\n# …（片段过长已截断，完整内容看当前 spec）"
    return text


def resolve_refs(spec: dict, refs: list) -> list[dict]:
    """Every mention resolved, or SelectionError naming the first that is not.

    Returns rows of:
      {"label", "kind", "path", "fragment"}            for tree refs
      {"label", "kind": "selector", "selector", "note"} for viewport picks
    """
    if not isinstance(refs, list):
        raise SelectionError("selection 必须是一个列表")
    if len(refs) > MAX_REFS:
        raise SelectionError("一次最多 @ %d 个对象（收到 %d 个）"
                             % (MAX_REFS, len(refs)))
    if not isinstance(spec, dict):
        raise SelectionError("当前没有 spec，@引用没有可指的对象——先让助手生成一版")

    tree = build_tree(spec)
    resolved = []
    for entry in refs:
        if not isinstance(entry, dict):
            raise SelectionError("selection 里有一项不是对象：%r" % (entry,))

        if entry.get("kind") == "selector" or "selector" in entry:
            raw = str(entry.get("selector") or "")
            try:
                sel = selectors.parse(raw)
            except selectors.SelectorError as exc:
                raise SelectionError(
                    "视口点选生成的选择器 %r 过不了解析：%s" % (raw, exc)) from exc
            resolved.append({
                "label": str(entry.get("label") or raw),
                "kind": "selector",
                "selector": raw,
                # Measurements the pick was generated from (bbox, radius,
                # match count). Passed through verbatim — the prompt quotes
                # them so the model knows the selector is measured, not typed.
                "note": str(entry.get("note") or ""),
                "instance": sel.instance,
            })
            continue

        ref = str(entry.get("ref") or "")
        if not ref:
            raise SelectionError("selection 里有一项既没有 ref 也没有 selector")
        row = _find_row(tree, ref)
        if row is None:
            raise SelectionError(
                "@%s 指向 %r，但当前 spec 的模型树里没有这一行——"
                "它可能已被改名或删除，重新从树里选一次"
                % (entry.get("label") or ref, ref))
        path = row.get("path")
        if not path:
            raise SelectionError(
                "%r 是一行诊断信息（%s），不指向 spec 里的任何条目，没法 @ 它"
                % (ref, row.get("label")))
        resolved.append({
            "label": str(row.get("label") or ref),
            "kind": str(row.get("kind") or ""),
            "path": path,
            "fragment": _fragment(_fetch(spec, path)),
        })
    return resolved


def prompt_section(resolved: list[dict]) -> str:
    """The `## 用户选中` block build_prompt injects. Empty list → empty string."""
    if not resolved:
        return ""
    lines = ["## 用户选中（消息里的 @名字 指的就是这些对象）",
             "修改要落在这些对象上；没被点名的部分保持最小改动。"]
    for item in resolved:
        if item["kind"] == "selector":
            note = ("（%s）" % item["note"]) if item.get("note") else ""
            lines.append(
                "- @%s —— 用户在 3D 视口里点选的区域，已生成选择器 `%s`%s。"
                "这个选择器可直接写进 region / surface / 选择器字段，"
                "它是按点选对象量出来的，不要改写它的数字。"
                % (item["label"], item["selector"], note))
        else:
            lines.append("- @%s（%s，spec 路径 %s）：" %
                         (item["label"], item["kind"], item["path"]))
            lines.append("```yaml")
            lines.append(item["fragment"])
            lines.append("```")
    return "\n".join(lines) + "\n"
