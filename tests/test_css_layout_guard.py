"""Tests for scripts/check_css_layout.py.

The guard exists because a stylesheet rewrite once kept every selector but
silently dropped `grid-template-columns` from #spec-code, which collapsed the
line-number gutter into its own grid rows. Selector-level checks cannot catch
that; these tests pin the declaration-level behaviour.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from tests.frontend_sources import workbench_text

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "check_css_layout.py"


def _load():
    spec = importlib.util.spec_from_file_location("check_css_layout", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


guard = _load()


def _page(css: str) -> str:
    return f"<!DOCTYPE html><html><head><style>\n{css}\n</style></head><body></body></html>"


def test_extracts_only_layout_declarations():
    rules = guard.extract_rules(_page("""
      #a { display: grid; grid-template-columns: 52px 1fr; color: red; font-size: 12px; }
    """))
    assert rules["#a"] == {"display": "grid", "grid-template-columns": "52px 1fr"}


def test_comma_selectors_are_split_so_merging_rules_is_not_a_false_alarm():
    # Merging '#vp-card {...}' and '#vp-diff-card {...}' into one comma rule
    # must not read as two dropped selectors.
    old = guard.extract_rules(_page("#vp-card { overflow: hidden; } #vp-diff-card { overflow: hidden; }"))
    new = guard.extract_rules(_page("#vp-card, #vp-diff-card { overflow: hidden; }"))
    assert set(old) == set(new) == {"#vp-card", "#vp-diff-card"}
    assert new["#vp-diff-card"]["overflow"] == "hidden"


def test_declarations_merge_across_repeated_selectors():
    rules = guard.extract_rules(_page("#a { display: grid; } #a { overflow: auto; }"))
    assert rules["#a"] == {"display": "grid", "overflow": "auto"}


def test_at_rules_and_keyframe_stops_are_ignored():
    rules = guard.extract_rules(_page("""
      @media (max-width: 100px) { #a { display: none; } }
      @keyframes k { from { left: 0; } to { left: 10px; } }
    """))
    assert "from" not in rules and "to" not in rules
    assert not any(sel.startswith("@") for sel in rules)


def test_comments_do_not_leak_into_values():
    rules = guard.extract_rules(_page("#a { display: grid; /* grid-template-rows: 9px; */ }"))
    assert rules["#a"] == {"display": "grid"}


def test_the_regression_that_motivated_this_guard_is_detectable():
    before = guard.extract_rules(_page("#spec-code { display: grid; grid-template-columns: 52px 1fr; }"))
    after = guard.extract_rules(_page("#spec-code { display: grid; }"))
    dropped = [p for p in before["#spec-code"] if p not in after["#spec-code"]]
    assert dropped == ["grid-template-columns"]


def test_missing_style_block_is_an_explicit_failure():
    with pytest.raises(SystemExit):
        guard.extract_rules("<html><body>no stylesheet</body></html>")


def test_live_workbench_still_defines_its_load_bearing_grids():
    # The stylesheet is frontend/workbench.css since the split; guard.
    # extract_rules wants a <style> block, so hand it one.
    rules = guard.extract_rules(
        "<style>" + workbench_text("css") + "</style>")
    # The gutter grid whose loss started all this.
    assert "grid-template-columns" in rules["#spec-code"]
    assert rules["#spec-code"]["display"] == "grid"
    # Three-pane shell.
    assert rules["#layout"]["display"] == "grid"
    assert rules["#layout"]["grid-template-columns"].count(" ") == 2
    # KPI readouts must use auto-fit; auto-fill leaves a dead phantom column.
    assert "auto-fit" in rules["#kpi-grid"]["grid-template-columns"]
