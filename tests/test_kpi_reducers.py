"""Reducers must compute what was asked, or refuse.

The defect fixed here was a one-line catch-all. ``_reduce_values`` ended with
``return max(vals)``, so any reducer it did not recognise — ``sum``, or a
typo — came back as a maximum: right units, right sign, plausible magnitude,
different question. On a reaction force summed over a face that is the
difference between "the friction force is 120 N" and "the busiest node carries
9 N".

The second half is agreement. odb_lens/recipe.py gates the reducer name before
the extractor ever runs, and its list had gone stale (no ``sum``), so a spec
that the extractor could serve was rejected up front. A gate and an engine that
disagree about the same enum will always disagree in one of the two harmful
directions.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from odb_lens.recipe import SUPPORTED_REDUCERS, validate_recipe  # noqa: E402
from post.extract_kpis import _reduce_values  # noqa: E402

VALUES = [3.0, -7.0, 1.0, 5.0]


@pytest.mark.parametrize("reducer,want", [
    ("max", 5.0),
    ("min", -7.0),
    ("sum", 2.0),
    ("mean", 0.5),
    ("last", 5.0),
    ("abs_max", -7.0),
])
def test_each_reducer_computes_its_own_answer(reducer, want):
    assert _reduce_values(VALUES, reducer, "max") == pytest.approx(want)


def test_the_default_applies_only_when_no_reducer_is_given():
    assert _reduce_values(VALUES, None, "min") == -7.0
    assert _reduce_values(VALUES, "", "sum") == 2.0


@pytest.mark.parametrize("bogus", ["total", "SUMM", "average", "maximum", "μ"])
def test_an_unknown_reducer_is_fatal_rather_than_a_silent_max(bogus):
    """This is the whole point. `total` is what someone reaching for `sum`
    types, and it used to return the maximum without a word."""
    with pytest.raises(ValueError) as caught:
        _reduce_values(VALUES, bogus, "max")
    message = str(caught.value)
    assert bogus in message, message
    assert "sum" in message, "the message must list what IS available: %s" % message


def test_an_empty_selection_still_refuses():
    """Pre-existing guard, kept: 0.0 once shipped as a real KPI."""
    with pytest.raises(ValueError):
        _reduce_values([], "sum", "max")


def test_case_is_not_significant():
    assert _reduce_values(VALUES, "SUM", "max") == pytest.approx(2.0)


# ---------------------------------------------------------------------------
# The gate and the engine must know the same words
# ---------------------------------------------------------------------------

def test_every_gated_reducer_is_one_the_extractor_implements():
    for reducer in SUPPORTED_REDUCERS:
        # Must not raise. The value is irrelevant; being understood is not.
        _reduce_values(VALUES, reducer, "max")


def test_every_reducer_the_extractor_implements_passes_the_gate():
    """The direction that bit: `sum` worked in the extractor and was refused
    by the recipe validator, so the KPI never reached it."""
    implemented = set()
    for candidate in ("max", "min", "sum", "mean", "last", "abs_max"):
        try:
            _reduce_values(VALUES, candidate, "max")
        except ValueError:
            continue
        implemented.add(candidate)

    assert implemented == set(SUPPORTED_REDUCERS), (
        "extractor implements %s; odb_lens gates %s"
        % (sorted(implemented), sorted(SUPPORTED_REDUCERS)))


def test_the_recipe_validator_accepts_a_summed_reaction_force():
    ok, errors = validate_recipe([{
        "name": "FRICTION_FORCE", "type": "reaction_force_max",
        "location": "BC_HOLDZ", "component": "RF3", "reducer": "sum"}])
    assert ok, errors


def test_the_recipe_validator_still_rejects_a_made_up_reducer():
    ok, errors = validate_recipe([{
        "name": "X", "type": "field_max", "reducer": "total"}])
    assert not ok and any("total" in e for e in errors), errors
