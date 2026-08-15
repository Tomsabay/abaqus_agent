"""The translation catalogues must parse, and must cover what the pages use.

This exists because a broken catalogue is silent everywhere else. While
writing these translations a stray `"` went into an English string:

    "copilot.replay.outro": "... hit "Download Alpha package", install ..."

which is invalid JSON *and* invalid JavaScript, so `I18N.register({...})` —
the first statement in a ~4000-line inline script — would have thrown at parse
time and taken every event handler on the page with it. The full pytest suite
passed anyway: 1182 tests, none of which read the catalogue.

Hermetic. The browser-level checks live in scripts/run_i18n_ui_check.py.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import run_i18n_static_check as gate  # noqa: E402

PAGES = gate.PAGES


@pytest.fixture(scope="module", params=list(PAGES))
def page(request):
    rel = request.param
    # A page is its markup plus what it loads: workbench.html keeps its
    # catalogue in workbench_i18n.js since the split, and reading only the
    # .html would find no catalogue at all rather than fail on its contents.
    text = "\n".join((ROOT / src).read_text(encoding="utf-8")
                     for src in PAGES[rel])
    problems: list[str] = []
    catalogue = gate._extract_catalogue(text, rel, problems)
    assert problems == [], problems
    return rel, text, catalogue


def test_catalogue_parses_and_covers_both_languages(page):
    rel, _text, catalogue = page
    zh, en = catalogue.get("zh", {}), catalogue.get("en", {})

    assert zh, "%s registered no Chinese" % rel
    assert set(zh) == set(en), (
        "%s: %d key(s) in only one language, e.g. %s"
        % (rel, len(set(zh) ^ set(en)), sorted(set(zh) ^ set(en))[:6]))
    assert all(v.strip() for v in zh.values()), rel
    assert all(v.strip() for v in en.values()), rel


def test_every_key_the_page_uses_is_registered(page):
    rel, text, catalogue = page
    referenced = gate._referenced_keys(text)
    undefined = sorted(k for k in referenced if k not in catalogue.get("zh", {}))

    assert undefined == [], (
        "%s asks for %d key(s) nobody registered: %s"
        % (rel, len(undefined), undefined[:8]))


def test_no_chinese_is_left_outside_the_catalogue(page):
    """The ratchet, as a test rather than only as a script."""
    rel, text, _catalogue = page
    left = gate._untranslated_lines(text)
    budget = gate.BUDGET[rel]

    assert len(left) <= budget, (
        "%s has %d line(s) carrying Chinese outside the catalogue (budget %d); "
        "first: %s" % (rel, len(left), budget, left[:3]))


STAND_IN = re.compile(r"window\.I18N = window\.I18N \|\|.*?\n\}\)\(\);", re.S)


def test_the_stand_in_merges_catalogues_rather_than_replacing(page):
    """Every page calls register() twice, so the stand-in must merge.

    The second call is loadBackendMessages(), which registers the strings the
    server composes. The stand-in used to do `d = c || {}` -- an assignment --
    so that second call threw the page's whole catalogue away, and with
    /static/i18n.js missing every label rendered as its raw key. Measured in
    Chromium on 2026-08-09 against the old code: 24 raw labels on /, 14 on
    /workbench. The browser gate said "survives a missing i18n.js, still
    Chinese" throughout, because the server-composed strings are Chinese too.
    """
    rel, text, _catalogue = page

    calls = text.count("I18N.register(")
    assert calls >= 2, (
        "%s registers a catalogue only %d time(s); if that is now the only "
        "call, this test's premise changed -- check before relaxing it"
        % (rel, calls))

    match = STAND_IN.search(text)
    assert match, "%s: cannot find the stand-in engine" % rel
    stand_in = match.group(0)

    assert re.search(r"\bd\s*=\s*c\b", stand_in) is None, (
        "%s: the stand-in replaces its whole dictionary on register(); with "
        "%d register() calls on the page, all but the last are lost"
        % (rel, calls))
    assert "d[lang] = d[lang] || {}" in stand_in, (
        "%s: the stand-in must merge per language, the way i18n.js does" % rel)


def test_the_shared_engine_is_present_and_loaded_defensively(page):
    """A missing /static/i18n.js must not be able to kill the page."""
    rel, text, _catalogue = page

    assert '<script src="/static/i18n.js"></script>' in text, rel
    # The stand-in that runs when that file did not load. Without it the
    # catalogue registration throws a ReferenceError and every handler on the
    # page goes with it.
    assert "window.I18N = window.I18N ||" in text, (
        "%s has no fallback for a missing /static/i18n.js" % rel)
    assert (ROOT / "frontend" / "i18n.js").is_file()
