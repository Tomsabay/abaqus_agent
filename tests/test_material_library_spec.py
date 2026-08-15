"""`library:` on a material block -- the numbers come from a card, with a receipt.

Resolution happens at LOAD time, before validation and before the run id is
taken. That is the whole design, and these tests hold each half of it:

  * the schema still sees a material block with real numbers in it, so a library
    material is judged by exactly the rules a hand-written one is;
  * the generator needs no branch, so the deck is byte-identical either way,
    which is what keeps frozen baselines comparable;
  * every number that came from a card is traceable back to the card, and every
    number the spec overrode is reported with BOTH values -- a report that
    cannot tell you which is which is a report you cannot check.
"""
from __future__ import annotations

import copy

import pytest
import yaml

from core import material_library as ml
from core.material_library import MaterialLibraryError, resolve_spec_materials
from tools.schema_validator import validate_spec


def test_a_named_card_becomes_real_numbers():
    spec = {"meta": {"units": "mm_MPa_t"},
            "material": {"library": "CalculiX-Steel"}}
    out, prov = resolve_spec_materials(spec)
    assert out["material"]["E"] == 210000.0
    assert out["material"]["nu"] == 0.3
    assert out["material"]["density"] == 7.9e-09
    assert len(prov) == 1


def test_the_callers_spec_is_not_touched():
    """A run that fails halfway through resolution must leave the spec it was
    handed exactly as it found it."""
    spec = {"meta": {"units": "mm_MPa_t"},
            "material": {"library": "CalculiX-Steel"},
            "materials": [{"library": "Steel-Generic"}]}
    before = copy.deepcopy(spec)
    resolve_spec_materials(spec)
    assert spec == before


def test_the_spec_may_rename_it():
    spec = {"meta": {"units": "mm_MPa_t"},
            "material": {"library": "Aluminum-6061-T6", "name": "Housing"}}
    out, prov = resolve_spec_materials(spec)
    assert out["material"]["name"] == "Housing"
    assert prov[0]["material"] == "Aluminum-6061-T6"   # where it came from
    assert prov[0]["spec_name"] == "Housing"           # what it is called here


def test_an_override_keeps_both_numbers():
    """"Steel, but our yield" is the common case. What must not happen is the
    two numbers becoming indistinguishable afterwards."""
    spec = {"meta": {"units": "mm_MPa_t"},
            "material": {"library": "CalculiX-Steel", "E": 205000.0}}
    out, prov = resolve_spec_materials(spec)
    assert out["material"]["E"] == 205000.0
    override = next(o for o in prov[0]["overrides"] if o["key"] == "E")
    assert override["spec_value"] == 205000.0
    assert override["card_value"] == 210000.0


def test_a_key_the_card_does_not_have_is_recorded_as_such():
    spec = {"meta": {"units": "mm_MPa_t"},
            "material": {"library": "CalculiX-Steel", "yield": 250.0}}
    out, prov = resolve_spec_materials(spec)
    assert out["material"]["yield"] == 250.0
    override = next(o for o in prov[0]["overrides"] if o["key"] == "yield")
    assert override["card_value"] is None


def test_plasticity_is_opt_in():
    """Several cards carry a yield strength, and build_v2 turns `yield` into a
    *Plastic table. Emitting it by default would silently make a linear-elastic
    study elastoplastic."""
    off, prov_off = resolve_spec_materials(
        {"meta": {"units": "mm_MPa_t"},
         "material": {"library": "Aluminum-6061-T6"}})
    assert "yield" not in off["material"]
    assert any("屈服" in entry.get("reason", "")
               for entry in prov_off[0]["not_included"])

    on, _ = resolve_spec_materials(
        {"meta": {"units": "mm_MPa_t"},
         "material": {"library": "Aluminum-6061-T6", "plasticity": True}})
    assert on["material"]["yield"] == 276.0


def test_plasticity_is_a_control_key_not_a_material_property():
    """It must not survive into the block, or build_v2 would meet a key it
    refuses by name."""
    out, _ = resolve_spec_materials(
        {"meta": {"units": "mm_MPa_t"},
         "material": {"library": "Aluminum-6061-T6", "plasticity": True}})
    assert "plasticity" not in out["material"]
    assert "library" not in out["material"]


def test_a_hand_written_block_is_left_exactly_alone():
    spec = {"meta": {"units": "mm_MPa_t"},
            "material": {"name": "Mine", "E": 1.0, "nu": 0.3},
            "materials": [{"name": "Other", "E": 2.0, "nu": 0.2}]}
    out, prov = resolve_spec_materials(spec)
    assert out["material"] == spec["material"]
    assert out["materials"] == spec["materials"]
    assert prov == []


def test_a_mixed_materials_list_resolves_only_the_library_entries():
    spec = {"meta": {"units": "mm_MPa_t"},
            "materials": [{"library": "Steel-Generic"},
                          {"name": "Hand", "E": 5.0, "nu": 0.25}]}
    out, prov = resolve_spec_materials(spec)
    assert out["materials"][0]["E"] == 200000.0
    assert out["materials"][1] == {"name": "Hand", "E": 5.0, "nu": 0.25}
    assert [entry["spec_path"] for entry in prov] == ["materials[0]"]


def test_an_unknown_name_is_refused_with_candidates():
    """Never approximated. A material that is nearly steel is not steel."""
    with pytest.raises(MaterialLibraryError) as excinfo:
        resolve_spec_materials({"material": {"library": "Stee"}})
    message = str(excinfo.value)
    assert "Stee" in message
    assert "Steel-Generic" in message


def test_a_library_value_that_is_not_a_name_is_refused():
    with pytest.raises(MaterialLibraryError) as excinfo:
        resolve_spec_materials({"material": {"library": ["CalculiX-Steel"]}})
    assert "material" in str(excinfo.value)


def test_the_provenance_carries_the_attribution_the_licence_asks_for():
    """These cards are CC-BY. An attribution that only exists in a README is an
    attribution nobody who reads the results ever sees."""
    _, prov = resolve_spec_materials(
        {"meta": {"units": "mm_MPa_t"},
         "material": {"library": "Aluminum-6061-T6"}})
    entry = prov[0]
    assert entry["license"].startswith("CC-BY")
    assert "FreeCAD" in entry["attribution"]
    assert entry["source"].get("url")


def test_units_come_from_the_spec_meta():
    """The same card in two unit systems is two different sets of numbers, and
    getting it from anywhere but the spec's own declaration is guessing."""
    mm, _ = resolve_spec_materials(
        {"meta": {"units": "mm_MPa_t"}, "material": {"library": "CalculiX-Steel"}})
    si, _ = resolve_spec_materials(
        {"meta": {"units": "SI_m_kg_s"}, "material": {"library": "CalculiX-Steel"}})
    assert mm["material"]["density"] == pytest.approx(7.9e-09)
    assert si["material"]["density"] == pytest.approx(7900.0)


# --- the schema half -------------------------------------------------------

def test_a_library_only_block_validates_against_the_schema():
    """Resolution runs before validation, but a raw spec off disk still passes
    through the validator -- the workbench preview and the schema CLI both do
    it. A key the dialect allows must not be rejected there."""
    spec = yaml.safe_load(open("cases/cantilever/spec.yaml", encoding="utf-8"))
    spec["material"] = {"library": "CalculiX-Steel"}
    ok, errors = validate_spec(spec)
    assert ok, errors


def test_a_block_with_neither_a_library_nor_the_numbers_is_still_refused():
    spec = yaml.safe_load(open("cases/cantilever/spec.yaml", encoding="utf-8"))
    spec["material"] = {"name": "Nameless"}
    ok, errors = validate_spec(spec)
    assert not ok


def test_a_resolved_library_material_still_satisfies_the_schema():
    spec = yaml.safe_load(open("cases/cantilever/spec.yaml", encoding="utf-8"))
    spec["material"] = {"library": "CalculiX-Steel", "name": "Steel"}
    resolved, _ = resolve_spec_materials(spec)
    ok, errors = validate_spec(resolved)
    assert ok, errors


def test_every_shipped_card_can_become_a_material_block():
    """The library's own promise. A card that cannot be used is a card that
    should not be listed."""
    template = yaml.safe_load(open("cases/cantilever/spec.yaml", encoding="utf-8"))
    for entry in ml.list_materials():
        spec = copy.deepcopy(template)
        spec["material"] = {"library": entry["name"], "name": "Mat"}
        resolved, prov = resolve_spec_materials(spec)
        ok, errors = validate_spec(resolved)
        assert ok, (entry["name"], errors)
        assert prov[0]["attribution"]
