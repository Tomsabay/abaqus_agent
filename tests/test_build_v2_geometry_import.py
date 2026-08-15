"""Reading a part out of a geometry file, and the one that comes back hollow.

Everything asserted here was measured first, on Abaqus 2021, by exporting one
10 x 10 x 100 bar out of CAE and reading it back three ways
(artifacts/probe_import):

    openStep   1 cell,  volume 10000.0,  6 faces,  8 vertices
    openAcis   1 cell,  volume 10000.0,  6 faces,  8 vertices
    openIges   0 cells, volume     0.0,  6 faces, 24 vertices, and NO exception

IGES has no solid entity in the flavour Abaqus writes, so what comes back is
six unstitched faces. `getVolume()` answers 0.0 rather than raising, and a part
with no cells then takes `p.Set(name='ALL', cells=p.cells)` and a
SectionAssignment over that empty set without a word -- the same shape as every
other silent failure in this layer. The FACE COUNT IS THE SAME as the solid's,
which is why the rule below is `volume` or `cells` specifically rather than
"state an expect block".
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from runner import build_v2  # noqa: E402
from runner import spec_base


@pytest.fixture
def geometry(tmp_path) -> Path:
    """A file that exists. Its contents never reach Abaqus in these tests."""
    path = tmp_path / "bar.step"
    path.write_text("ISO-10303-21;\n", encoding="utf-8")
    return path


def _spec(**part_overrides) -> dict:
    part = {
        "name": "Bar",
        "import": {"open": {"call": "openStep",
                            "fileName": {"file": "bar.step"}}},
        "expect": {"volume": 10000.0, "cells": 1},
        "section": {"type": "solid", "material": "Steel"},
        "mesh": {"seed": 25.0, "element": "C3D8R"},
    }
    part.update(part_overrides)
    return {
        "meta": {"abaqus_release": "2021", "model_name": "Imported",
                 "units": "mm_MPa_t"},
        "material": {"name": "Steel", "E": 210000.0, "nu": 0.3,
                     "density": 7.85e-9},
        "parts": [part],
        "assembly": {"instances": [{"name": "B", "part": "Bar",
                                    "translate": [0.0, 0.0, 0.0]}]},
        "steps": [{"call": "StaticStep", "name": {"literal": "One"},
                   "previous": {"literal": "Initial"}}],
        "conditions": [],
        "outputs": {"kpis": [{"name": "U", "type": "field_min",
                              "location": "whole_model", "component": "U2"}]},
    }


def _emit(spec: dict, spec_dir) -> str:
    return build_v2.generate_script(spec, spec_dir=spec_dir)


def _refuse(spec: dict, spec_dir) -> str:
    with pytest.raises(spec_base.SpecError) as excinfo:
        build_v2.generate_script(spec, spec_dir=spec_dir)
    return str(excinfo.value)


def _line(text: str, needle: str) -> str:
    for line in text.splitlines():
        if needle in line:
            return line
    return ""


def _opened_path(text: str) -> Path:
    """The fileName the emitted opener call was given, as a path.

    Read back rather than string-matched: the script embeds it through repr(),
    so backslashes are doubled, and Path.resolve() case-normalises parts of a
    Windows path. Comparing paths compares what actually matters.
    """
    line = _line(text, "_gcall(mdb, ")
    marker = "'fileName': "
    start = line.index(marker) + len(marker)
    quote = line[start]
    end = start + 1
    chunk = []
    while line[end] != quote:
        if line[end] == "\\":
            end += 1
        chunk.append(line[end])
        end += 1
    return Path("".join(chunk))


# --- the call -------------------------------------------------------------

def test_the_opener_the_spec_names_is_the_one_called(geometry):
    text = _emit(_spec(), geometry.parent)
    assert "_gcall(mdb, 'openStep'" in text
    assert "_gcall(m, 'PartFromGeometryFile'" in text
    assert _opened_path(text) == geometry.resolve()


def test_any_opener_is_reachable_without_a_branch_per_format(geometry):
    """Six formats, six methods, six sets of keywords, and no enum here.

    openIges alone takes msbo, trimCurve and topology; openStep takes
    scaleFromFile. Naming the method is what makes a format this generator has
    never heard of importable.
    """
    for opener in ("openIges", "openAcis", "openVda", "openParasolid"):
        spec = _spec(**{"import": {"open": {
            "call": opener, "fileName": {"file": "bar.step"},
            "scaleFromFile": "OFF"}}})
        text = _emit(spec, geometry.parent)
        assert "_gcall(mdb, %r" % opener in text
        assert "'scaleFromFile': OFF" in text


def test_extra_keywords_reach_partfromgeometryfile(geometry):
    spec = _spec(**{"import": {
        "open": {"call": "openStep", "fileName": {"file": "bar.step"}},
        "part": {"combine": {"bool": False}, "scale": 0.001}}})
    line = _line(_emit(spec, geometry.parent), "PartFromGeometryFile")
    assert "'combine': False" in line
    assert "'scale': 0.001" in line


def test_the_part_is_named_by_the_spec_not_by_the_file(geometry):
    line = _line(_emit(_spec(), geometry.parent), "PartFromGeometryFile")
    assert "'name': 'Bar'" in line


def test_name_and_geometryfile_cannot_be_overridden(geometry):
    for key in ("name", "geometryFile"):
        spec = _spec(**{"import": {
            "open": {"call": "openStep", "fileName": {"file": "bar.step"}},
            "part": {key: "something"}}})
        assert "is not settable here" in _refuse(spec, geometry.parent)


# --- the rule the IGES measurement forced ---------------------------------

def test_an_import_without_volume_or_cells_is_refused(geometry):
    message = _refuse(_spec(expect={"faces": 6}), geometry.parent)
    assert "expect.volume" in message and "expect.cells" in message
    assert "0 cells and volume 0.0" in message, (
        "the refusal has to carry the measurement, because 'state an expect "
        "block' does not explain why a face count will not do")


def test_faces_alone_cannot_tell_the_solid_from_the_shell():
    """The reason the rule is not 'any expect key'.

    Six faces came back through IGES and six through STEP. A spec stating
    `faces: 6` would pass on a part with no volume, no cells, an empty section
    assignment and no solid elements.
    """
    assert build_v2._IMPORT_EXPECT_KEYS == ("volume", "cells")
    assert "faces" not in build_v2._IMPORT_EXPECT_KEYS


def test_either_key_alone_is_enough(geometry):
    for expect in ({"volume": 10000.0}, {"cells": 1}):
        assert "PartFromGeometryFile" in _emit(_spec(expect=expect),
                                               geometry.parent)


# --- import and features are exclusive ------------------------------------

def test_a_part_cannot_be_imported_and_built(geometry):
    spec = _spec(features=[{"op": "sketch", "id": "o", "plane": "XY",
                            "profile": {"rect": {"corner1": [0.0, 0.0],
                                                 "corner2": [1.0, 1.0]}}}])
    assert "both `import:` and `features:`" in _refuse(spec, geometry.parent)


def test_a_part_with_neither_is_refused_by_the_schema():
    """Not by the generator -- this is the shape check, and the schema owns it."""
    schema = json.loads(
        (ROOT / "schema" / "spec_schema.json").read_text(encoding="utf-8"))
    part = schema["properties"]["parts"]["items"]
    assert {"required": ["features"]} in part["oneOf"]
    assert {"required": ["import"]} in part["oneOf"]
    assert "features" not in part["required"]


def test_the_opener_cannot_bind_or_redirect_itself(geometry):
    """Both keys would have been overwritten without a word.

    `as:` by the internal alias the branch binds, `target:` by the fixed `mdb`.
    A dropped key is the defect this layer keeps finding elsewhere, so it does
    not get introduced by the branch that reads geometry.
    """
    for key, value in (("as", "mine"), ("target", {"attr": "keywordBlock"})):
        spec = _spec(**{"import": {"open": {
            "call": "openStep", "fileName": {"file": "bar.step"},
            key: value}}})
        message = _refuse(spec, geometry.parent)
        assert "`%s:` is not settable here" % key in message


def test_an_import_missing_its_opener_is_refused(geometry):
    spec = _spec(**{"import": {"part": {"combine": {"bool": False}}}})
    assert "must be a call mapping" in _refuse(spec, geometry.parent)


# --- {file:} --------------------------------------------------------------

def test_a_relative_path_resolves_against_the_spec(geometry):
    nested = geometry.parent / "geom"
    nested.mkdir()
    moved = nested / "bar.step"
    moved.write_text("ISO-10303-21;\n", encoding="utf-8")
    spec = _spec(**{"import": {"open": {
        "call": "openStep", "fileName": {"file": "geom/bar.step"}}}})
    assert _opened_path(_emit(spec, geometry.parent)) == moved.resolve()


def test_a_missing_file_is_refused_before_abaqus_starts(geometry):
    spec = _spec(**{"import": {"open": {
        "call": "openStep", "fileName": {"file": "absent.step"}}}})
    message = _refuse(spec, geometry.parent)
    assert "does not exist" in message
    assert "no licence is taken" in message


def test_a_relative_path_with_no_spec_on_disk_is_refused(geometry):
    assert "no spec file to be relative TO" in _refuse(_spec(), None)


def test_an_absolute_path_needs_no_spec_directory(geometry):
    spec = _spec(**{"import": {"open": {
        "call": "openStep", "fileName": {"file": str(geometry.resolve())}}}})
    assert _opened_path(_emit(spec, None)) == geometry.resolve()


def test_a_file_mapping_carrying_anything_else_is_refused(geometry):
    spec = _spec(**{"import": {"open": {
        "call": "openStep",
        "fileName": {"file": "bar.step", "expect": "=1"}}}})
    assert "names a file and nothing else" in _refuse(spec, geometry.parent)


def test_imported_files_lists_what_the_cache_has_to_hash(geometry):
    assert build_v2.imported_files(_spec(), geometry.parent) == [
        str(geometry.resolve())]


def test_a_spec_with_no_import_has_nothing_to_hash(geometry):
    spec = _spec()
    spec["parts"][0].pop("import")
    spec["parts"][0]["features"] = [
        {"op": "sketch", "id": "o", "plane": "XY",
         "profile": {"rect": {"corner1": [0.0, 0.0], "corner2": [10.0, 10.0]}}},
        {"op": "extrude", "sketch": "o", "depth": 100.0}]
    assert build_v2.imported_files(spec, geometry.parent) == []


# --- the rest of the part still applies ------------------------------------

def test_an_imported_part_still_gets_its_section_and_mesh(geometry):
    text = _emit(_spec(), geometry.parent)
    assert "m.HomogeneousSolidSection(name='SEC_Bar'" in text
    assert "p.generateMesh()" in text
    assert "p.seedPart(size=25.0" in text


def test_validation_walks_the_import_branch_too(geometry):
    """`validate_references` used to reach into part['features'] unguarded.

    A spec carrying only `import:` died with a bare KeyError: 'features',
    naming neither the part nor the key.
    """
    resolved = build_v2._resolve_file_args(_spec(expect={"faces": 6}),
                                           geometry.parent)[0]
    with pytest.raises(spec_base.SpecError):
        build_v2.validate_references(resolved)
