"""Hold the translation catalogues to the markup that uses them.

"We support English" is the easy claim and the hard thing to keep true: one
new button with a hardcoded Chinese label and the English UI is quietly 99%
translated forever. Nothing in a screenshot or a passing test suite shows it.

So this counts. Every key the markup or the JS asks for must exist in both
languages; the two catalogues must have identical key sets; and the number of
Chinese-bearing source lines still sitting outside a catalogue is a ratchet —
it may go down, never up, and when it goes down the budget in this file must
come down with it. A budget that drifts above reality is a check that has
stopped checking.

Run:  .venv\\Scripts\\python.exe scripts\\run_i18n_static_check.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# A "page" is now its markup plus whatever it loads. workbench.html was 3616
# lines of markup, stylesheet, catalogue and behaviour in one file; the
# catalogue moved to workbench_i18n.js, and this gate has to follow it or it
# silently starts checking a page with no catalogue at all.
PAGES = {
    "frontend/index.html": ["frontend/index.html",
                            "frontend/index_i18n.js"],
    "frontend/workbench.html": ["frontend/workbench.html",
                                "frontend/workbench_i18n.js",
                                "frontend/workbench_chat.js"],
}

CATALOGUE = re.compile(
    r"/\*\s*i18n:catalogue:start\s*\*/(.*?)/\*\s*i18n:catalogue:end\s*\*/",
    re.S)
REGISTER = re.compile(r"^\s*I18N\.register\(\s*(.*?)\s*\)\s*;?\s*$", re.S)

KEY_ATTR = re.compile(r'data-i18n\s*=\s*"([^"]+)"')
KEY_ATTR_MAP = re.compile(r'data-i18n-attr\s*=\s*"([^"]+)"')
KEY_TITLE = re.compile(r'data-i18n-title\s*=\s*"([^"]+)"')
KEY_CALL = re.compile(r"""\bt\(\s*['"]([^'"]+)['"]""")

CJK = re.compile(r"[一-鿿]")

# Lines that legitimately keep Chinese and are not UI copy. Comments explain
# the code to whoever maintains it; recorded sessions and seeded example
# prompts are DATA — a Chinese recording stays Chinese in the English UI, the
# same way an English log stays English in the Chinese one.
SKIP_LINE = re.compile(
    r"^\s*(//|/\*|\*|<!--)"          # comment openers and continuations
)

# Ratchet. Lower it in the same commit that lowers the real count.
BUDGET = {
    "frontend/index.html": 0,
    "frontend/workbench.html": 0,
}


def _extract_catalogue(text: str, rel: str, problems: list[str]) -> dict:
    match = CATALOGUE.search(text)
    if not match:
        problems.append("%s: no /* i18n:catalogue:start */ ... :end block" % rel)
        return {}
    inner = REGISTER.match(match.group(1).strip())
    if not inner:
        problems.append("%s: catalogue block is not a single I18N.register({...}) call" % rel)
        return {}
    try:
        return json.loads(inner.group(1))
    except json.JSONDecodeError as exc:
        problems.append(
            "%s: catalogue must be JSON-parseable so this check can read it "
            "(double-quoted keys and values, no trailing commas, no JS "
            "expressions) -- %s" % (rel, exc))
        return {}


def _referenced_keys(text: str) -> set[str]:
    keys = set(KEY_ATTR.findall(text)) | set(KEY_TITLE.findall(text))
    keys |= set(KEY_CALL.findall(text))
    for spec in KEY_ATTR_MAP.findall(text):
        for pair in spec.split(","):
            bits = pair.split(":")
            if len(bits) == 2:
                keys.add(bits[1].strip())
    return keys


def _untranslated_lines(text: str) -> list[tuple[int, str]]:
    """Chinese still living in markup or code rather than in the catalogue."""
    match = CATALOGUE.search(text)
    span = match.span() if match else (-1, -1)
    out = []
    offset = 0
    for lineno, line in enumerate(text.splitlines(True), 1):
        start, offset = offset, offset + len(line)
        if span[0] <= start < span[1]:
            continue
        if not CJK.search(line) or SKIP_LINE.match(line):
            continue
        out.append((lineno, line.strip()[:100]))
    return out


def main() -> int:
    problems: list[str] = []
    report: list[str] = []

    for rel, sources in PAGES.items():
        texts = {src: (ROOT / src).read_text(encoding="utf-8")
                 for src in sources}
        text = "\n".join(texts.values())
        catalogue = _extract_catalogue(text, rel, problems)
        zh = catalogue.get("zh", {})
        en = catalogue.get("en", {})

        only_zh = sorted(set(zh) - set(en))
        only_en = sorted(set(en) - set(zh))
        if only_zh:
            problems.append("%s: %d key(s) have no English: %s"
                            % (rel, len(only_zh), ", ".join(only_zh[:8])))
        if only_en:
            problems.append("%s: %d English key(s) have no Chinese: %s"
                            % (rel, len(only_en), ", ".join(only_en[:8])))

        referenced = _referenced_keys(text)
        undefined = sorted(k for k in referenced if k not in zh)
        if undefined:
            problems.append("%s: %d key(s) used but never registered: %s"
                            % (rel, len(undefined), ", ".join(undefined[:8])))

        # A dead key is not a bug, but a pile of them means the catalogue has
        # stopped describing the page.
        dead = sorted(set(zh) - referenced)
        if dead:
            report.append("%s: %d registered key(s) nothing references: %s"
                          % (rel, len(dead), ", ".join(dead[:6])))

        left = []
        for src, src_text in texts.items():
            left += [(src, lineno, sample)
                     for lineno, sample in _untranslated_lines(src_text)]
        budget = BUDGET.get(rel, 0)
        report.append("%s: %d key(s), %d line(s) still carrying Chinese (budget %d)"
                      % (rel, len(zh), len(left), budget))
        if len(left) > budget:
            problems.append("%s: %d untranslated line(s), budget is %d"
                            % (rel, len(left), budget))
            for src, lineno, sample in left[:12]:
                problems.append("    %s:%d  %s" % (src, lineno, sample))
        elif len(left) < budget:
            problems.append(
                "%s: only %d untranslated line(s) but the budget still says %d "
                "-- lower BUDGET in this file so the ratchet holds"
                % (rel, len(left), budget))

    for line in report:
        print("  " + line)

    if problems:
        print("\nRESULT: FAIL")
        for problem in problems:
            print("  - %s" % problem)
    else:
        print("\nRESULT: PASS")
    # The verdict scripts/run_all_real_checks.py reads. It has to be the last
    # parseable JSON object on stdout.
    print(json.dumps({"schema": "i18n_static_check/1",
                      "result": "FAIL" if problems else "PASS",
                      "pages": list(PAGES), "problems": problems},
                     ensure_ascii=False))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
