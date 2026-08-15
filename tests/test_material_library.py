"""Tests for core/material_library.py and the data it ships.

Two halves. The first exercises the unit parser against numbers computed by
hand, because that is the part where being wrong is silent. The second reads
the shipped JSON and checks it is still the output of this code -- a factor
changed in the module with the data left alone would otherwise pass everything
else in the suite.
"""

from __future__ import annotations

import json
from decimal import Decimal

import pytest

from core import material_library as ml

# Hand-computed, from the definition of the unit system, not from the code
# under test:
#   7850 kg/m^3 = 7850 * 1e-3 tonne / 1e9 mm^3 = 7.85e-9 t/mm^3
#   210000 MPa  = 2.1e11 Pa                    = 210000 MPa   (unchanged)
#   590 J/(kg*K) = 590 * 1e3 mJ / 1e-3 tonne / K = 5.9e8 mJ/(t*K)
#   43 W/(m*K)   = 43 * 1e3 mW / 1e3 mm / K     = 43 mW/(mm*K) (unchanged)
STEEL_DENSITY_MM_MPA_T = 7.85e-09
STEEL_E_MM_MPA_T = 210000.0


# ---------------------------------------------------------------------------
# Unit parsing and conversion
# ---------------------------------------------------------------------------

def test_density_converts_to_tonne_per_mm3():
    parsed = ml.parse_quantity("7850 kg/m^3", "density")
    assert parsed["raw_unit"] == "kg/m^3"
    assert float(parsed["si"]) == 7850.0

    value, unit = ml.convert(parsed["si"], "density")
    assert unit == "t/mm^3"
    # Exact equality on purpose: the conversion runs in Decimal precisely so a
    # power-of-ten scaling does not come back as 7.850000000000001e-09.
    assert value == STEEL_DENSITY_MM_MPA_T


def test_modulus_in_mpa_is_unchanged_by_the_round_trip_through_si():
    parsed = ml.parse_quantity("210000 MPa", "stress")
    assert float(parsed["si"]) == 2.1e11
    value, unit = ml.convert(parsed["si"], "stress")
    assert (value, unit) == (STEEL_E_MM_MPA_T, "MPa")


def test_gigapascal_is_a_thousand_megapascal():
    value, _ = ml.convert(ml.parse_quantity("26.0 GPa", "stress")["si"], "stress")
    assert value == 26000.0


def test_specific_heat_and_conductivity_do_not_share_a_factor():
    """The pair most likely to be waved through together. They differ by 1e6."""
    heat, heat_unit = ml.convert(
        ml.parse_quantity("590 J/kg/K", "specific_heat")["si"], "specific_heat")
    cond, cond_unit = ml.convert(
        ml.parse_quantity("43 W/m/K", "thermal_conductivity")["si"],
        "thermal_conductivity")
    assert (heat, heat_unit) == (5.9e08, "mJ/(t*K)")
    assert (cond, cond_unit) == (43.0, "mW/(mm*K)")


def test_micro_sign_and_greek_mu_parse_the_same():
    micro = ml.parse_quantity("68 µm/m/K", "thermal_expansion")
    greek = ml.parse_quantity("68 μm/m/K", "thermal_expansion")
    assert micro["si"] == greek["si"] == Decimal("68") * Decimal("1E-6")


def test_unknown_unit_is_refused_not_guessed():
    with pytest.raises(ml.MaterialLibraryError) as excinfo:
        ml.parse_quantity("7850 slug/ft^3", "density")
    message = excinfo.value.message
    assert "slug/ft^3" in message
    assert "UNIT_TO_SI" in message      # says where to add it
    assert "kg/m^3" in message          # lists what is recognised


def test_bare_number_where_a_unit_is_required_is_refused():
    with pytest.raises(ml.MaterialLibraryError) as excinfo:
        ml.parse_quantity("7850", "density")
    assert "kg/m^3" in excinfo.value.message


def test_decimal_comma_is_refused_with_both_readings_spelled_out():
    """The refusal that matters most: 2200,00 MPa is 2200 or 220000."""
    with pytest.raises(ml.MaterialLibraryError) as excinfo:
        ml.parse_quantity("2200,00 MPa", "stress")
    message = excinfo.value.message
    assert "2200.00 MPa" in message
    assert "220000 MPa" in message


def test_unit_on_a_dimensionless_value_is_refused():
    with pytest.raises(ml.MaterialLibraryError):
        ml.parse_quantity("0.3 MPa", "dimensionless")


def test_unknown_unit_system_lists_the_supported_ones():
    with pytest.raises(ml.MaterialLibraryError) as excinfo:
        ml.convert(1.0, "stress", units="imperial")
    assert "mm_MPa_t" in excinfo.value.message
    assert "SI_m_kg_s" in excinfo.value.message


def test_si_unit_system_leaves_the_card_values_alone():
    parsed = ml.parse_quantity("7850 kg/m^3", "density")
    assert ml.convert(parsed["si"], "density", units="SI_m_kg_s") == (
        7850.0, "kg/m^3")


# ---------------------------------------------------------------------------
# Card conversion
# ---------------------------------------------------------------------------

def _fcmat(models: dict, licence: str = "CC-BY-3.0") -> dict:
    return {"General": {"Name": "T", "License": licence, "Author": "A",
                        "UUID": "u", "Description": "d"},
            "Models": models}


def _source(name: str = "Test-Steel") -> dict:
    return {"project": "FreeCAD", "name": name, "path": "x/%s.FCMat" % name,
            "commit": "0" * 40, "url": "https://example.invalid/x",
            "retrieved": "2026-08-06"}


def test_card_conversion_end_to_end():
    card = ml.card_from_fcmat(
        _fcmat({"IsotropicLinearElastic": {"YoungsModulus": "210000 MPa",
                                           "PoissonRatio": "0.3"},
                "Density": {"Density": "7850 kg/m^3"}}),
        _source())
    assert card["properties"]["E"]["mm_MPa_t"] == STEEL_E_MM_MPA_T
    assert card["properties"]["density"]["mm_MPa_t"] == STEEL_DENSITY_MM_MPA_T
    assert card["properties"]["density"]["raw"] == "7850 kg/m^3"
    assert card["license"] == "CC-BY-3.0"


def test_property_split_across_differently_named_models_is_still_found():
    """Upstream spells the elastic model three ways; none may be lost."""
    card = ml.card_from_fcmat(
        _fcmat({"Linear Elastic": {"YoungsModulus": "3640 MPa"},
                "LinearElastic": {"PoissonRatio": "0.36"},
                "Density": {"Density": "1240 kg/m^3"}}),
        _source("Test-PLA"))
    assert card["properties"]["E"]["mm_MPa_t"] == 3640.0
    assert card["properties"]["nu"]["si"] == 0.36


def test_same_property_with_two_values_is_refused():
    with pytest.raises(ml.MaterialLibraryError) as excinfo:
        ml.card_from_fcmat(
            _fcmat({"A": {"YoungsModulus": "210000 MPa", "PoissonRatio": "0.3"},
                    "B": {"YoungsModulus": "200000 MPa"}}),
            _source())
    assert "YoungsModulus" in excinfo.value.message


def test_card_without_e_and_nu_cannot_be_a_material():
    with pytest.raises(ml.MaterialLibraryError) as excinfo:
        ml.card_from_fcmat(_fcmat({"Density": {"Density": "1 kg/m^3"}}),
                           _source("Test-Default"))
    assert "E" in excinfo.value.message


def test_poisson_ratio_outside_the_schema_range_is_refused():
    with pytest.raises(ml.MaterialLibraryError) as excinfo:
        ml.card_from_fcmat(
            _fcmat({"E": {"YoungsModulus": "1 MPa", "PoissonRatio": "0.5"}}),
            _source("Test-Rubber"))
    assert "0.5" in excinfo.value.message


def test_unmapped_property_is_reported_with_a_reason():
    card = ml.card_from_fcmat(
        _fcmat({"E": {"YoungsModulus": "1 MPa", "PoissonRatio": "0.3",
                      "UltimateTensileStrength": "310 MPa",
                      "SomethingFreeCADAddedLater": "1 MPa"}}),
        _source())
    reported = {u["fcmat_key"]: u for u in card["unmapped"]}
    assert reported["UltimateTensileStrength"]["raw"] == "310 MPa"
    # An unknown key is reported too, so a future upstream property cannot be
    # dropped just because nobody taught this module about it.
    assert "SPEC_PROPERTIES" in reported["SomethingFreeCADAddedLater"]["reason"]


def test_material_name_that_abaqus_would_not_take_is_refused():
    with pytest.raises(ml.MaterialLibraryError):
        ml.card_from_fcmat(
            _fcmat({"E": {"YoungsModulus": "1 MPa", "PoissonRatio": "0.3"}}),
            _source("Aluminum 6061-T6"))


# ---------------------------------------------------------------------------
# The shipped library
# ---------------------------------------------------------------------------

def test_every_shipped_card_is_present_and_permissively_licensed():
    cards = ml.list_materials()
    assert len(cards) == 17
    assert {c["license"] for c in cards} == {"CC-BY-3.0", "CC-BY-4.0"}
    steel = next(c for c in cards if c["name"] == "CalculiX-Steel")
    assert "E=210000 MPa" in steel["summary"]


def test_shipped_reinforcement_card_matches_the_hand_computed_values():
    block, prov = ml.load_material("Reinforcement-FIB-B500")
    assert block["E"] == STEEL_E_MM_MPA_T
    assert block["density"] == STEEL_DENSITY_MM_MPA_T
    assert prov["properties"]["density"]["raw"] == "7850 kg/m^3"
    assert prov["properties"]["E"]["raw"] == "210000 MPa"
    assert prov["license"] == "CC-BY-3.0"
    assert prov["source"]["commit"]


def test_shipped_cards_match_recomputed_conversion():
    """The data on disk must still be what this code produces.

    Catches the case a stale generated file makes invisible: someone corrects a
    factor in UNIT_SYSTEMS and does not rebuild data/materials/freecad.
    """
    for name in (c["name"] for c in ml.list_materials()):
        card = ml._index()[name]
        for key, entry in card["properties"].items():
            recomputed, unit = ml.convert(entry["si"], entry["dimension"])
            assert recomputed == entry["mm_MPa_t"], (name, key)
            assert unit == entry["mm_MPa_t_unit"], (name, key)


def test_shipped_cards_reparse_from_their_own_raw_strings():
    """raw + parsed_unit must reproduce si, or the audit trail is decorative."""
    for name in (c["name"] for c in ml.list_materials()):
        card = ml._index()[name]
        entries = dict(card["properties"], **(card["plasticity"] or {}))
        for key, entry in entries.items():
            again = ml.parse_quantity(entry["raw"], entry["dimension"])
            assert float(again["si"]) == entry["si"], (name, key)


def test_every_loaded_block_validates_against_the_real_spec_schema():
    """The point of the library: what it hands back is a legal material block.

    Validated against schema/spec_schema.json itself rather than a copy of its
    rules, so a schema change that the library stops satisfying fails here
    instead of at the first run someone tries.
    """
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads(
        (ml.DATA_DIR.parent.parent / "schema" / "spec_schema.json")
        .read_text(encoding="utf-8"))
    material_schema = schema["properties"]["material"]
    assert material_schema.get("additionalProperties") is False

    for name in (c["name"] for c in ml.list_materials()):
        block, _ = ml.load_material(name, include_plasticity=True)
        jsonschema.validate(block, material_schema)


def test_plasticity_is_opt_in_and_named_when_left_out():
    block, prov = ml.load_material("Aluminum-6061-T6")
    assert "yield" not in block
    left_out = {n["fcmat_key"] for n in prov["not_included"]}
    assert "YieldStrength" in left_out

    with_plastic, _ = ml.load_material("Aluminum-6061-T6",
                                       include_plasticity=True)
    # `yield`, not `yield_stress`: runner/build_v2.py refuses the latter by name.
    assert with_plastic["yield"] == 276.0


def test_lookup_is_forgiving_about_spelling_but_not_about_identity():
    by_stem, _ = ml.load_material("Steel-Generic")
    by_case, _ = ml.load_material("steel_generic")
    assert by_stem == by_case


def test_upstream_display_name_resolves_too():
    block, _ = ml.load_material("Aluminum 6061-T6")
    assert block["name"] == "Aluminum-6061-T6"


def test_unknown_material_is_refused_with_close_matches():
    with pytest.raises(ml.MaterialLibraryError) as excinfo:
        ml.load_material("Steal-Genneric")
    message = excinfo.value.message
    assert "Steal-Genneric" in message
    assert "Steel-Generic" in message


def test_one_name_claimed_by_two_cards_refuses_and_names_both(tmp_path, monkeypatch):
    """An alias two cards claim must resolve to neither.

    Both FreeCAD cards here call themselves "Steel" in ``General.Name`` while
    living in different files. Handing back whichever one the directory listing
    reached first would be a material the caller did not ask for, with nothing
    in the output saying so.
    """
    for stem in ("Steel-A", "Steel-B"):
        card = ml.card_from_fcmat(
            {"General": {"Name": "Steel", "License": "CC-BY-3.0"},
             "Models": {"E": {"YoungsModulus": "1 MPa", "PoissonRatio": "0.3"}}},
            _source(stem))
        (tmp_path / ("%s.json" % stem)).write_text(
            json.dumps(card, ensure_ascii=False), encoding="utf-8")

    monkeypatch.setattr(ml, "CARD_DIR", tmp_path)
    ml._index.cache_clear()
    ml._aliases.cache_clear()
    try:
        with pytest.raises(ml.MaterialLibraryError) as excinfo:
            ml.load_material("steel")
        message = excinfo.value.message
        assert "Steel-A" in message and "Steel-B" in message
        # Not the not-found refusal. The difflib fallback happens to name both
        # cards too, so only this distinguishes the two paths: "no such
        # material" would send the caller hunting for a typo in a name that is
        # in the library twice over.
        assert "材料库里没有" not in message
        # The unambiguous name still resolves, so the refusal is about the
        # collision and not about the cards being unusable.
        assert ml.load_material("Steel-B")[0]["name"] == "Steel-B"
    finally:
        ml._index.cache_clear()
        ml._aliases.cache_clear()


def test_shear_modulus_note_states_the_base_of_its_percentage():
    """A percentage with an unstated base is a number nobody can re-derive.

    Hand-computed from PET-Generic's own two numbers: E = 3150 MPa, nu = 0.36,
    so E/(2(1+nu)) = 3150/2.72 = 1158.09 MPa against the card's 38.5 MPa.
    That gap is 96.7% of the implied value and 2908% of the card's own -- same
    disagreement, two answers, so the note has to say which one it means.
    """
    note = next(n for n in ml._index()["PET-Generic"]["notes"] if "剪切模量" in n)
    assert "96.7%" in note
    assert "以推出来的值为基准" in note


def test_unknown_material_without_close_matches_points_at_the_listing():
    with pytest.raises(ml.MaterialLibraryError) as excinfo:
        ml.load_material("zzzzzzzz")
    assert "list_materials()" in excinfo.value.message


def test_si_unit_system_reproduces_the_upstream_numbers():
    block, prov = ml.load_material("CalculiX-Steel", units="SI_m_kg_s")
    assert block["density"] == 7900.0
    assert block["E"] == 2.1e11
    assert prov["properties"]["density"]["unit"] == "kg/m^3"


def test_provenance_carries_an_attribution_line_per_card():
    for name in (c["name"] for c in ml.list_materials()):
        _, prov = ml.load_material(name)
        line = prov["attribution"]
        assert prov["license"] in line
        assert "FreeCAD" in line
        assert prov["source"]["url"] in line


def test_provenance_json_agrees_with_what_shipped():
    report = json.loads((ml.DATA_DIR / "provenance.json").read_text(encoding="utf-8"))
    accepted = {r["card"] for r in report["cards"] if r["verdict"] == "accepted"}
    assert accepted == {c["name"] for c in ml.list_materials()}
    assert report["counts"]["accepted"] == len(accepted)
    # Every refusal says why, so the 123 cards that did not ship are auditable
    # without re-running the fetch.
    assert all(r.get("reason") for r in report["cards"]
               if r["verdict"] == "refused")


# ---------------------------------------------------------------------------
# Spec integration
# ---------------------------------------------------------------------------

def _library_spec(material: dict) -> dict:
    return {"meta": {"abaqus_release": "2021", "model_name": "m",
                     "units": "mm_MPa_t"},
            "material": material}


def test_library_key_validates_raw_and_still_resolves_to_numbers():
    """The load order is load-bearing, so it is pinned against the real schema.

    An earlier version of this test asserted the opposite -- that the schema
    REJECTED a spec still carrying ``library:``, on the grounds that
    orchestrator.__init__ expands before validate_spec runs. That reasoning was
    right about the order and wrong about the consequence: the orchestrator is
    not the only thing that validates. The workbench preview and the schema CLI
    both read a spec straight off disk and check it, and refusing a key the
    dialect allows makes the editor red-line a perfectly good file.

    So the schema takes ``library:`` (anyOf: either a library name, or the
    name+E+nu it always required), and what is pinned here is the pair of
    guarantees that matters: the raw form validates, and the resolved form is
    the same numbers a hand-written block would have carried.
    """
    validate_spec = pytest.importorskip("tools.schema_validator").validate_spec

    raw = _library_spec({"library": "Steel-Generic"})
    errors = validate_spec(raw)[1]
    # The stub spec has no geometry or steps, so it does not validate either
    # way; what matters is that the MATERIAL block is not one of the
    # complaints. `nu` names nothing else in the schema, so it is a clean
    # marker for "the material block was not understood".
    assert not [e for e in errors if "library" in e or "'nu'" in e], errors

    resolved, _ = ml.resolve_spec_materials(raw)
    assert "library" not in resolved["material"]
    after = validate_spec(resolved)[1]
    assert not [e for e in after if "library" in e or "'nu'" in e], after
    # 200000 MPa and 7900 kg/m^3 in Steel-Generic.FCMat, converted by hand:
    # 7900 * 1e-3 t / 1e9 mm^3 = 7.9e-9 t/mm^3.
    assert resolved["material"]["E"] == 200000.0
    assert resolved["material"]["density"] == 7.9e-09


def test_a_material_block_with_neither_a_library_nor_the_numbers_is_refused():
    """Relaxing `required` into an anyOf must not relax it away.

    Worth recording what the relaxation costs: jsonschema reports an anyOf
    miss as "... is not valid under any of the given schemas" and prints the
    offending block, instead of the "'nu' is a required property" it used to
    give. The block is still named, so the message is actionable, but it is
    less specific than it was -- the price of the material block having two
    legal shapes.
    """
    validate_spec = pytest.importorskip("tools.schema_validator").validate_spec
    ok, errors = validate_spec(_library_spec({"name": "Nameless"}))
    assert not ok
    assert any("Nameless" in e for e in errors), errors


def test_a_key_written_beside_library_overrides_the_card_and_says_so():
    """An override is allowed, but both numbers have to survive into the report.

    A spec that silently replaced a card value would leave the provenance
    claiming a FreeCAD number the run never used -- attribution pointing at
    data that did not reach the model.
    """
    spec = _library_spec({"library": "Steel-Generic", "name": "Bushing",
                          "E": 195000.0})
    resolved, prov = ml.resolve_spec_materials(spec)
    assert resolved["material"]["name"] == "Bushing"
    assert resolved["material"]["E"] == 195000.0

    override = next(o for o in prov[0]["overrides"] if o["key"] == "E")
    assert (override["spec_value"], override["card_value"]) == (195000.0, 200000.0)
    assert prov[0]["spec_path"] == "material"


def test_the_original_spec_dict_is_not_edited_by_resolution():
    """A resolution that fails halfway must leave the caller's spec untouched."""
    spec = _library_spec({"library": "Steel-Generic"})
    ml.resolve_spec_materials(spec)
    assert spec["material"] == {"library": "Steel-Generic"}


def test_library_plasticity_is_opt_in_at_the_spec_level_too():
    spec = _library_spec({"library": "Aluminum-6061-T6"})
    without, _ = ml.resolve_spec_materials(spec)
    assert "yield" not in without["material"]

    spec = _library_spec({"library": "Aluminum-6061-T6", "plasticity": True})
    with_plastic, prov = ml.resolve_spec_materials(spec)
    assert with_plastic["material"]["yield"] == 276.0
    assert prov[0]["plasticity_requested"] is True


def test_unknown_library_material_is_refused_at_spec_resolution():
    with pytest.raises(ml.MaterialLibraryError) as excinfo:
        ml.resolve_spec_materials(_library_spec({"library": "Steal-Genneric"}))
    assert "Steel-Generic" in excinfo.value.message


def test_missing_library_directory_says_how_to_rebuild(tmp_path, monkeypatch):
    monkeypatch.setattr(ml, "CARD_DIR", tmp_path / "nope")
    ml._index.cache_clear()
    ml._aliases.cache_clear()
    try:
        with pytest.raises(ml.MaterialLibraryError) as excinfo:
            ml.list_materials()
        assert "build_library.py" in excinfo.value.message
    finally:
        ml._index.cache_clear()
        ml._aliases.cache_clear()
