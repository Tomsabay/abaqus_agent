"""The KPI type list is closed, and the two copies of it cannot drift.

`outputs.kpis[].type` used to be an unconstrained string. An unknown one
validated, built, meshed, SOLVED, and only then raised "Unknown kpi type" from
inside the Abaqus kernel -- so a typo cost a full solve and returned an error
message from a Python 2.7 process rather than from the validator.

An enum is the right shape here and the wrong shape one layer over. A KPI type
is not an Abaqus API surface this project is trying not to second-guess; it is
the name of a branch in post/extract_kpis.py, so the closed list is a statement
about what this project can read. What makes that safe rather than brittle is
the test below: the schema's enum is compared against the dispatch chain
itself, so adding a branch without publishing it -- or publishing a type with
no branch behind it -- fails here instead of at someone's solve.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

EXTRACTOR = ROOT / "post" / "extract_kpis.py"
SCHEMA = ROOT / "schema" / "spec_schema.json"


def _dispatch_branches() -> list[str]:
    source = EXTRACTOR.read_text(encoding="utf-8")
    return re.findall(r'kpi_type == "([a-z_]+)"', source)


def _schema_node() -> dict:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    return (schema["properties"]["outputs"]["properties"]["kpis"]
            ["items"]["properties"]["type"])


def test_the_schema_enum_is_exactly_what_the_extractor_dispatches():
    branches = _dispatch_branches()
    assert branches, "found no `kpi_type == \"...\"` branches to compare against"
    published = _schema_node().get("enum")
    assert published is not None, (
        "outputs.kpis[].type has no enum, so an unknown type reaches the "
        "Abaqus kernel and costs a full solve before saying so")
    assert sorted(published) == sorted(branches), (
        "the schema and the extractor disagree.\n"
        "  only in the schema    : %s\n"
        "  only in the extractor : %s"
        % (sorted(set(published) - set(branches)),
           sorted(set(branches) - set(published))))


def test_the_odb_lens_gate_knows_the_same_types():
    """The third copy, and the one that proved the danger is not theoretical.

    `odb_lens.recipe.SUPPORTED_TYPES` is checked at the EXTRACT stage. When
    `eigenvalue` was added to the extractor and to the schema but not here, a
    *BUCKLE spec validated, built, meshed and solved -- and was refused
    afterwards, by the layer meant to be the cheap gate, with "kpis[0].type is
    unsupported: eigenvalue" arriving after the solve had been paid for.
    """
    from odb_lens.recipe import SUPPORTED_TYPES

    branches = _dispatch_branches()
    assert sorted(SUPPORTED_TYPES) == sorted(branches), (
        "odb_lens and the extractor disagree.\n"
        "  only in odb_lens  : %s\n"
        "  only in extractor : %s"
        % (sorted(set(SUPPORTED_TYPES) - set(branches)),
           sorted(set(branches) - set(SUPPORTED_TYPES))))


def test_every_kpi_key_the_extractor_reads_can_be_set_in_a_spec():
    """`additionalProperties: false` makes an unpublished key unreachable.

    Found by re-reading rather than by a test, which is why this one exists:
    `contour_integral_j` shipped reading `zero_tolerance` with a default and a
    hermetic test exercising the override, and no spec could set it — the
    validator answered "Additional properties are not allowed". A knob the code
    honours and the schema refuses is indistinguishable from no knob at all,
    and it fails at the validator with a message about a typo rather than about
    the feature.
    """
    source = EXTRACTOR.read_text(encoding="utf-8")
    read = set(re.findall(r'kpi\.get\(\s*"([a-z_]+)"', source))
    read |= set(re.findall(r'kpi\[\s*"([a-z_]+)"\s*\]', source))

    # Not a spec key. odb_lens recipes pass arbitrary keys through to the
    # extractor (odb_lens/recipe.py:_normalize_kpi copies the dict), and
    # `step_name` is the recipe-side spelling of `step`, kept as a fallback for
    # recipes written against the older name. A spec says `step`.
    read -= {"step_name"}

    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    published = set(schema["properties"]["outputs"]["properties"]["kpis"]
                    ["items"]["properties"])
    assert not (read - published), (
        "the extractor reads %s, and a spec setting it is refused by the "
        "schema" % sorted(read - published))


def test_no_type_is_published_twice():
    published = _schema_node()["enum"]
    assert len(published) == len(set(published))


def test_an_unknown_type_is_refused_by_the_validator():
    """The point of the whole exercise: before Abaqus, not inside it."""
    from tools.schema_validator import validate_spec

    spec = {
        "meta": {"abaqus_release": "2021", "model_name": "M",
                 "units": "mm_MPa_t"},
        "material": {"name": "S", "E": 210000.0, "nu": 0.3,
                     "density": 7.85e-9},
        "parts": [], "assembly": {"instances": []}, "steps": [],
        "outputs": {"kpis": [{"name": "K", "type": "field_minimum"}]},
    }
    valid, errors = validate_spec(spec)
    assert not valid
    assert any("field_minimum" in e for e in errors), errors


def test_every_shipped_case_still_validates():
    """A fail-closed list is only safe if it was checked against what ships.

    Twelve specs, five distinct types between them; this is what stops the
    enum from being tightened on a machine where nobody ran the cases.
    """
    import yaml

    from tools.schema_validator import validate_spec

    cases = sorted((ROOT / "cases").glob("*/spec.yaml"))
    assert len(cases) >= 10, "expected the shipped cases to be present"
    for path in cases:
        spec = yaml.safe_load(path.read_text(encoding="utf-8"))
        valid, errors = validate_spec(spec)
        assert valid, "%s no longer validates: %s" % (path.name, errors[:3])


def test_the_buckling_type_is_published():
    assert "eigenvalue" in _schema_node()["enum"]


def test_the_eigenvalue_reader_refuses_a_frame_with_no_eigenvalue():
    """It must not fall back, because the plausible fallbacks are both wrong.

    Measured on Abaqus 2021: for a *BUCKLE frame whose eigenvalue is 10785,
    frameValue is 1.0 (the mode ordinal) and frequency is None. A reader that
    guessed from either would hand back a number that is not a buckling load
    and looks entirely reasonable.
    """
    source = EXTRACTOR.read_text(encoding="utf-8")
    assert "def _eigenvalue_of(" in source
    body = source.split("def _eigenvalue_of(", 1)[1].split("\ndef ", 1)[0]
    assert "raise ValueError" in body
    assert "frameValue is the mode ordinal" in body
