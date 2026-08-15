"""Where a page's source actually lives, for tests that read it as text.

A page used to be one file, so a test could `read_text()` the .html and search
it. That stopped being true when workbench.html was split: its stylesheet is in
workbench.css, its translation catalogue in workbench_i18n.js, its viewport in
workbench_viewport.js. A test that keeps reading only the .html does not fail
loudly -- it silently stops finding what it was guarding, and reports PASS
about a rule it is no longer checking.

So the mapping lives in one place, and a test asks for what it needs:

    text = workbench_text()          # everything, concatenated
    css  = workbench_text("css")     # only the stylesheet
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"

# kind -> files, in load order.
WORKBENCH = {
    "markup": ["workbench.html"],
    "css": ["design-system.css", "workbench.css"],
    "i18n": ["workbench_i18n.js"],
    "script": ["workbench.html", "workbench_viewport.js"],
}

INDEX = {
    "markup": ["index.html"],
    "css": ["design-system.css", "index.css"],
    "i18n": ["index_i18n.js"],
    "script": ["index.html"],
}


def _read(names: list[str]) -> str:
    return "\n".join((FRONTEND / n).read_text(encoding="utf-8") for n in names)


def _page_text(mapping: dict[str, list[str]], kind: str | None) -> str:
    if kind:
        return _read(mapping[kind])
    seen: list[str] = []
    for names in mapping.values():
        for name in names:
            if name not in seen:
                seen.append(name)
    return _read(seen)


def workbench_text(kind: str | None = None) -> str:
    return _page_text(WORKBENCH, kind)


def index_text(kind: str | None = None) -> str:
    return _page_text(INDEX, kind)


def page_files(rel: str) -> list[Path]:
    """Every file a page is made of, for checks that must name the offender.

    A rule like "no page redefines the design tokens" or "nothing fetches from
    a CDN" applies to the stylesheet and the scripts as much as to the markup,
    and after the split those are different files.
    """
    mapping = WORKBENCH if Path(rel).name == "workbench.html" else INDEX
    seen: list[str] = []
    for names in mapping.values():
        for name in names:
            if name not in seen:
                seen.append(name)
    return [FRONTEND / n for n in seen]


def page_text(rel: str, kind: str | None = None) -> str:
    """By repo-relative path, for tests parametrised over both pages."""
    name = Path(rel).name
    if name == "workbench.html":
        return workbench_text(kind)
    if name == "index.html":
        return index_text(kind)
    raise KeyError(rel)
