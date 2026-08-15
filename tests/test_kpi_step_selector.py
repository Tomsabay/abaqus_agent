"""`step:` on a KPI used to be read from zero, so `step: 1` measured step TWO.

That is the exact failure this project exists to stop. On a three-step assembly,
a gravity-step reaction read out of the clamped step comes back as 257 N instead
of 17.7 N -- a perfectly plausible number, from the wrong physics, with nothing
to say so. Only the last step failed loudly, by running off the end of the list.

The second bug in the same three lines: `odb.steps` is an Abaqus Repository, not
a dict, and `1 in odb.steps` does not return False -- it raises "String Expected
as dictionary Key". So a numeric selector never reached the numeric branch at
all. The fake below reproduces both behaviours, which is the only way a hermetic
test can hold this: the suite never opens a real ODB.
"""
from __future__ import annotations

import pytest

from post.extract_kpis import _select_step


class FakeRepository:
    """Enough of an Abaqus Repository to catch what a dict would hide.

    Measured behaviour it reproduces:
      * `1 in repo` raises rather than returning False;
      * keys() preserves the order the steps were created in.
    """

    def __init__(self, names):
        self._names = list(names)

    def keys(self):
        return list(self._names)

    def __contains__(self, key):
        if not isinstance(key, str):
            raise TypeError("String Expected as dictionary Key")
        return key in self._names

    def __getitem__(self, key):
        if not isinstance(key, str):
            raise TypeError("String Expected as dictionary Key")
        return "STEP:" + key


class FakeOdb:
    def __init__(self, names):
        self.steps = FakeRepository(names)


THREE = ["SelfWeight", "Clamp", "Push"]


def test_a_number_counts_from_one():
    odb = FakeOdb(THREE)
    assert _select_step(odb, {"step": 1}) == "STEP:SelfWeight"
    assert _select_step(odb, {"step": 2}) == "STEP:Clamp"
    assert _select_step(odb, {"step": 3}) == "STEP:Push"


def test_a_numeric_string_counts_from_one_too():
    assert _select_step(FakeOdb(THREE), {"step": "2"}) == "STEP:Clamp"


def test_a_number_does_not_raise_about_dictionary_keys():
    """The membership test has to be guarded by the type. Without the guard
    every numeric selector dies with a message naming neither step nor KPI."""
    try:
        _select_step(FakeOdb(THREE), {"step": 1})
    except TypeError as exc:  # pragma: no cover - the bug being guarded
        pytest.fail("numeric selector hit the repository membership test: %s" % exc)


def test_a_name_wins_over_everything():
    assert _select_step(FakeOdb(THREE), {"step": "Push"}) == "STEP:Push"


def test_step_name_is_read_as_well_as_step():
    assert _select_step(FakeOdb(THREE), {"step_name": "Clamp"}) == "STEP:Clamp"


def test_no_selector_means_the_last_step():
    assert _select_step(FakeOdb(THREE), {}) == "STEP:Push"
    assert _select_step(FakeOdb(THREE), {"step": ""}) == "STEP:Push"


def test_past_the_end_is_refused_with_the_real_names():
    with pytest.raises(KeyError) as excinfo:
        _select_step(FakeOdb(THREE), {"step": 4})
    message = str(excinfo.value)
    assert "4" in message and "3 step" in message
    assert "SelfWeight" in message and "Push" in message
    assert "numbering starts at 1" in message


def test_zero_is_refused_rather_than_read_as_the_first_step():
    """Zero is what a 0-based spec would write, so it must not quietly work --
    a spec written against the old convention has to be told, not silently
    given a different step than it asked for."""
    with pytest.raises(KeyError):
        _select_step(FakeOdb(THREE), {"step": 0})


def test_a_name_that_is_not_there_is_refused_with_the_real_names():
    with pytest.raises(KeyError) as excinfo:
        _select_step(FakeOdb(THREE), {"step": "Squeeze"})
    message = str(excinfo.value)
    assert "Squeeze" in message and "SelfWeight" in message


def test_a_boolean_is_not_an_ordinal():
    """True is an int in Python. A spec that writes `step: true` has made a
    mistake and must hear about it, not silently measure step one."""
    with pytest.raises(KeyError):
        _select_step(FakeOdb(THREE), {"step": True})
