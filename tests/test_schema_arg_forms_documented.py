"""Every argument form has to be findable by someone reading the schema.

The schema's `generic_call` description is the only place a spec author learns
that these forms exist. There is no enum to read: the whole point of generic
dispatch is that the METHOD names are open, so the closed part — the fifteen
mappings that mean something to the generator — lives in prose.

Prose does not fail a test when it goes stale, which is how four of them went
missing. `new`, `instance`, `vertex` and `wire_at` were implemented, tested,
shipped and used by real cases while the description enumerated eleven forms
and stopped; `one` was never listed at all. A form nobody can find is a form
nobody uses, and the writer's next move is a hand-written wrapper for the thing
the dialect already does — which is the enumeration this layer exists to avoid.

So the two lists are compared here rather than kept in step by habit. This is
the same three-way shape as tests/test_kpi_type_closed.py, and it exists for
the same reason: that one was written after `eigenvalue` reached the schema and
the dispatch chain but not `odb_lens`, so a spec validated, built, meshed and
SOLVED before being refused.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from runner import arg_forms  # noqa: E402

SCHEMA = json.loads(
    (ROOT / "schema" / "spec_schema.json").read_text(encoding="utf-8"))
DESCRIPTION = SCHEMA["definitions"]["generic_call"]["description"]


def _mentioned(form: str) -> bool:
    """Written as `form` or as `{form: ...}`, which are the two house styles.

    Deliberately not a bare substring test: `set` occurs in "a selector made
    into a named set" and `one` occurs in the word "one" about forty times, so
    a loose match would report full coverage of a description that documents
    nothing.
    """
    return bool(re.search(r"`\{?%s[:`]" % re.escape(form), DESCRIPTION))


@pytest.mark.parametrize("form", arg_forms._ARG_FORMS)
def test_every_argument_form_appears_in_the_schema_description(form):
    assert _mentioned(form), (
        "`%s` is a form the generator resolves and the schema description "
        "does not mention it, so nothing a spec author can read says it "
        "exists" % form)


def test_the_description_documents_no_form_the_generator_does_not_resolve():
    """The other direction, which is how a removed form outlives its code.

    A documented form that resolves to nothing is worse than an undocumented
    one: it reads as supported and fails at generation.
    """
    documented = set(re.findall(r"`\{?([a-z_]+)[:`]", DESCRIPTION))
    # Exactly the five non-form words the pattern reaches today, and no more.
    # A generous allow-list would make this test fail open: every word it
    # forgives is a word a stale form could hide behind, and the point is that
    # a new one has to be looked at by a person once.
    not_a_form = {"call", "as", "expect", "at", "location"}
    unknown = {w for w in documented
               if w not in set(arg_forms._ARG_FORMS) and w not in not_a_form}
    assert not unknown, (
        "the schema description quotes %s in argument-form style, and the "
        "generator resolves no such form. Either it was removed from the code "
        "and left in the prose, or this test's allow-list needs the word."
        % sorted(unknown))


def test_the_count_is_stated_so_a_new_form_trips_something():
    """A parametrised test grows silently; this one does not.

    Adding a sixteenth form makes the parametrised test above pass sixteen
    times without anyone looking at the description. This is the line that
    makes the author come back and read it.
    """
    assert len(arg_forms._ARG_FORMS) == 15, (
        "the number of argument forms changed. Add the new one to the schema "
        "description (the parametrised test above will tell you if it is "
        "missing), then update this count. It is here so that adding a form "
        "cannot be a silent act."
    )


def test_no_form_is_listed_twice_in_the_generator():
    assert len(set(arg_forms._ARG_FORMS)) == len(arg_forms._ARG_FORMS)
