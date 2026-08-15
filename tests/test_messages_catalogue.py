"""Guards for the bilingual message catalogue.

The catalogue is the one place a refusal's wording lives, so the ways it can
rot are worth naming: an entry that gains Chinese and never gains English; an
English string whose `{placeholder}` was translated along with the prose, so
`.format()` raises or silently leaves a literal `{env}` on screen; a key the
code asks for that nobody ever wrote.

None of these would fail a solve, which is why none of them would be noticed.
"""

import re

import pytest

from core import messages as M

PLACEHOLDER = re.compile(r"\{(\w+)\}")


def test_every_entry_has_both_languages():
    incomplete = {
        key: sorted(entry)
        for key, entry in M.CATALOGUE.items()
        if set(entry) != {"zh", "en"} or not all(v.strip() for v in entry.values())
    }
    assert incomplete == {}, "entries missing a language: %r" % incomplete


def test_placeholders_match_across_languages():
    """`{env}` must survive translation; a renamed one breaks .format()."""
    mismatched = {}
    for key, entry in M.CATALOGUE.items():
        zh = set(PLACEHOLDER.findall(entry["zh"]))
        en = set(PLACEHOLDER.findall(entry["en"]))
        if zh != en:
            mismatched[key] = {"zh": sorted(zh), "en": sorted(en)}
    assert mismatched == {}, "placeholder drift: %r" % mismatched


def test_no_entry_is_the_same_string_in_both_languages():
    """A copy-pasted 'translation' is the quiet way half the UI stays Chinese."""
    untranslated = [key for key, entry in M.CATALOGUE.items()
                    if entry["zh"].strip() == entry["en"].strip()]
    assert untranslated == [], untranslated


@pytest.mark.parametrize("header,expected", [
    ("zh-CN,zh;q=0.9,en;q=0.8", "zh"),
    ("en-GB,en;q=0.9", "en"),
    ("ZH", "zh"),
    ("fr-FR,fr;q=0.9,en;q=0.5", "en"),   # first tag we understand wins
    ("", None),                          # falls through to env/system
])
def test_resolve_lang_reads_accept_language_shapes(header, expected, monkeypatch):
    monkeypatch.delenv(M.ENV_LANG, raising=False)
    resolved = M.resolve_lang(header)
    if expected is None:
        assert resolved in M.SUPPORTED
    else:
        assert resolved == expected


def test_env_overrides_system_but_not_an_explicit_request(monkeypatch):
    monkeypatch.setenv(M.ENV_LANG, "en")
    assert M.resolve_lang() == "en"
    assert M.resolve_lang("zh-CN") == "zh"


def test_render_interpolates_and_falls_back_without_raising():
    assert "ABAQUS_AGENT_ABAQUS_CMD" in M.render(
        "backend.select.abaqus_not_found", "en", env="ABAQUS_AGENT_ABAQUS_CMD")

    # An unknown key returns the producer's own prose rather than the key: a
    # stale key must not turn a refusal into "backend.select.something".
    assert M.render("no.such.key", "en", fallback="中文兜底") == "中文兜底"

    # And with neither, the key itself — ugly, but never an exception in the
    # middle of somebody's solve.
    assert M.render("also.missing", "en") == "also.missing"


def test_catalogue_for_returns_a_flat_map_in_one_language():
    en = M.catalogue_for("en")
    zh = M.catalogue_for("zh")
    assert set(en) == set(zh) == set(M.CATALOGUE)
    assert (en["backend.select.abaqus_not_found"]
            != zh["backend.select.abaqus_not_found"])
    assert all(isinstance(v, str) and v for v in en.values())


def test_the_no_abaqus_refusal_is_actionable_in_both_languages():
    """The one sentence a visitor without Abaqus ever sees.

    Until 2026-08-15 they got a CalculiX fallback or a walkthrough instead;
    now this text IS the product's answer, so it has to name both ways out
    (PATH or the variable) rather than only stating the problem.
    """
    for lang in ("en", "zh"):
        text = M.render("backend.select.abaqus_not_found", lang,
                        env="ABAQUS_AGENT_ABAQUS_CMD")
        assert "ABAQUS_AGENT_ABAQUS_CMD" in text, lang
        assert "PATH" in text, lang


def test_no_key_still_offers_a_second_solver():
    """A leftover CalculiX sentence would promise a backend that is gone."""
    stale = [k for k in M.CATALOGUE if k.startswith("ccx.")]
    assert stale == [], stale

    for key, entry in M.CATALOGUE.items():
        for lang, text in entry.items():
            assert "CalculiX" not in text, f"{key}/{lang}: {text}"
            assert "calculix" not in text.lower(), f"{key}/{lang}: {text}"
