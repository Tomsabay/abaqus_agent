"""Guard a stylesheet rewrite against silent layout regressions.

Restyling frontend/workbench.html means replacing a ~700-line <style> block
wholesale. Checking that every selector survived is not enough: a rule can
keep its name and quietly lose the one declaration that made the layout
work. That is exactly what happened once — #spec-code lost
`grid-template-columns: 52px 1fr`, so the line-number gutter collapsed into
its own grid rows and the YAML listing rendered at double height with the
numbers stranded on the right.

This compares layout-critical declarations between a reference revision of
the file and the working copy, and reports anything dropped.

Usage:
  .venv/Scripts/python.exe scripts/check_css_layout.py                 # vs HEAD
  .venv/Scripts/python.exe scripts/check_css_layout.py --ref <git-rev>
  .venv/Scripts/python.exe scripts/check_css_layout.py --ref-file a.html

Exit 0 when nothing was lost, 1 when something was, 2 on a usage error.
Changed-but-present values are reported as notes, not failures: narrowing a
column on purpose is normal, losing the column definition is not.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / "frontend" / "workbench.html"

# Declarations whose absence changes where things sit, not how they look.
LAYOUT_PROPS = frozenset({
    "display", "position", "overflow", "overflow-x", "overflow-y",
    "grid-template-columns", "grid-template-rows", "grid-template-areas",
    "grid-column", "grid-row", "flex", "flex-direction", "flex-wrap",
    "top", "right", "bottom", "left", "inset", "z-index",
    "width", "height", "min-width", "min-height", "max-width", "max-height",
})

# Values that legitimately get retuned while the declaration stays present.
TUNABLE = frozenset({
    "width", "height", "min-width", "min-height", "max-width", "max-height",
    "top", "right", "bottom", "left", "z-index",
})


def extract_rules(html: str) -> dict[str, dict[str, str]]:
    """Map 'selector' -> {layout property: value} for one inline stylesheet."""
    try:
        start = html.index("<style>") + len("<style>")
        end = html.index("</style>", start)
    except ValueError:
        raise SystemExit("no inline <style> block found")
    css = re.sub(r"/\*.*?\*/", "", html[start:end], flags=re.S)

    rules: dict[str, dict[str, str]] = {}
    for raw_sel, body in re.findall(r"([^{}]+)\{([^{}]*)\}", css):
        for sel in raw_sel.split(","):
            sel = " ".join(sel.split())
            # at-rules and keyframe stops carry no layout contract worth diffing
            if not sel or sel.startswith("@") or sel in {"from", "to"} or sel.endswith("%"):
                continue
            props: dict[str, str] = {}
            for decl in body.split(";"):
                if ":" not in decl:
                    continue
                name, _, value = decl.partition(":")
                name = name.strip().lower()
                if name in LAYOUT_PROPS:
                    props[name] = " ".join(value.split())
            if props:
                rules.setdefault(sel, {}).update(props)
    return rules


def read_ref(args: argparse.Namespace) -> str:
    if args.ref_file:
        return Path(args.ref_file).read_text(encoding="utf-8")
    rel = TARGET.relative_to(ROOT).as_posix()
    proc = subprocess.run(
        ["git", "show", f"{args.ref}:{rel}"],
        cwd=ROOT, capture_output=True, text=True,
        encoding="utf-8", errors="replace", stdin=subprocess.DEVNULL,
    )
    if proc.returncode != 0:
        raise SystemExit(f"cannot read {rel} at {args.ref}: {proc.stderr.strip()}")
    return proc.stdout


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ref", default="HEAD", help="git revision to compare against")
    ap.add_argument("--ref-file", help="compare against this file instead of a revision")
    args = ap.parse_args()

    if not TARGET.is_file():
        print(f"target missing: {TARGET}")
        return 2

    old = extract_rules(read_ref(args))
    new = extract_rules(TARGET.read_text(encoding="utf-8"))

    lost: list[str] = []
    notes: list[str] = []
    for sel, props in old.items():
        current = new.get(sel)
        if current is None:
            lost.append(f"selector dropped: {sel}  ({', '.join(sorted(props))})")
            continue
        for prop, value in props.items():
            if prop not in current:
                lost.append(f"{sel} :: lost {prop}: {value}")
            elif current[prop] != value and prop not in TUNABLE:
                notes.append(f"{sel} :: {prop}: {value} -> {current[prop]}")

    print(f"reference: {args.ref_file or args.ref}")
    print(f"rules carrying layout declarations: {len(old)} -> {len(new)}")
    if notes:
        print(f"\nretuned ({len(notes)}, not failures):")
        for n in notes:
            print(f"  {n}")
    if lost:
        print(f"\nLOST ({len(lost)}):")
        for item in lost:
            print(f"  {item}")
        print("\nFAIL: a layout declaration disappeared in the rewrite.")
        return 1
    print("\nPASS: no layout declaration was dropped.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
