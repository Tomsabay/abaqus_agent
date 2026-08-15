"""The refuse-before-run keyword gate.

Why this gate exists, measured on ccx 2.23: a deck carrying
``*INCIDENT WAVE INTERACTION, CONWEP`` inside a legal ``*DYNAMIC, EXPLICIT``
step runs to completion, exits 0, writes a full .frd, and reports every
displacement as exactly 0.000000E+00. The console shows only
``*WARNING in calinput. Card image cannot be interpreted``, and
``No analysis was selected`` never appears because the STEP itself was legal.

So an exit-code check cannot catch it and neither can "did we get result
files". Only refusing before the run does. These tests are what keep that true
as the deck generators evolve.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from runner.ccx_deck import build_ccx_deck, write_ccx_deck
from runner.ccx_mesh import cantilever_block_mesh
from runner.ccx_whitelist import DeckRefused, assert_translatable, scan_deck

GEO = {"type": "cantilever_block", "L": 100.0, "W": 10.0, "H": 10.0, "seed_size": 5.0}

CLEAN_DECK = """*HEADING
ok
*NODE, NSET=NALL
1, 0., 0., 0.
*ELEMENT, TYPE=C3D8, ELSET=EALL
1, 1, 1, 1, 1, 1, 1, 1, 1
*MATERIAL, NAME=STEEL
*ELASTIC
210000., 0.3
*SOLID SECTION, ELSET=EALL, MATERIAL=STEEL
*BOUNDARY
FIXED, 1, 3
*STEP
*STATIC
*CLOAD
TIP, 2, -1.
*NODE PRINT, NSET=TIP
U
*END STEP
"""

CONWEP_DECK = CLEAN_DECK.replace(
    "*CLOAD\nTIP, 2, -1.",
    "*INCIDENT WAVE INTERACTION PROPERTY, NAME=BLAST, TYPE=AIR BLAST\n"
    "*INCIDENT WAVE INTERACTION, PROPERTY=BLAST, CONWEP\nSURF, 1., 1., 1.",
)

COHESIVE_DECK = CLEAN_DECK.replace("TYPE=C3D8", "TYPE=COH3D8")


def test_a_clean_deck_passes():
    assert scan_deck(CLEAN_DECK) == []
    assert_translatable(CLEAN_DECK)  # must not raise


def test_conwep_deck_is_refused_before_it_can_be_solved():
    reasons = scan_deck(CONWEP_DECK)
    assert reasons, "the silent-zero-load deck must never reach the solver"
    joined = " ".join(reasons)
    assert "INCIDENTWAVEINTERACTION" in joined.replace(" ", "")
    assert "静默" in joined and "0" in joined
    with pytest.raises(DeckRefused):
        assert_translatable(CONWEP_DECK)


def test_cohesive_element_is_refused_by_name():
    reasons = scan_deck(COHESIVE_DECK)
    assert any("COH3D8" in r for r in reasons)


@pytest.mark.parametrize("element", ["COH3D8", "COH3D6", "COH2D4", "SC8R", "C3D8H", "B33"])
def test_abaqus_only_elements_are_all_refused(element):
    deck = CLEAN_DECK.replace("TYPE=C3D8", "TYPE=%s" % element)
    assert any(element in r for r in scan_deck(deck))


@pytest.mark.parametrize("element", ["C3D20R", "C3D8I", "CPS4", "CAX8", "S4R", "B31"])
def test_verified_elements_are_accepted(element):
    deck = CLEAN_DECK.replace("TYPE=C3D8", "TYPE=%s" % element)
    assert scan_deck(deck) == []


CONTACT_DECK = CLEAN_DECK.replace(
    "*BOUNDARY",
    "*SURFACE INTERACTION, NAME=IFACE\n"
    "*SURFACE BEHAVIOR, PRESSURE-OVERCLOSURE=LINEAR\n"
    "1.e6\n"
    "*FRICTION\n"
    "0.3\n"
    "*CONTACT PAIR, INTERACTION=IFACE, TYPE=SURFACE TO SURFACE\n"
    "SEC, MAIN\n"
    "*BOUNDARY",
)


@pytest.mark.parametrize("card", [
    "*CONTACT PAIR", "*SURFACE INTERACTION", "*SURFACE BEHAVIOR",
    "*FRICTION", "*TIE",
])
def test_contact_cards_are_refused_until_a_baseline_exists(card):
    """ccx implements these; nobody here has compared them to Abaqus.

    That is the dangerous half of the whitelist. An unknown card at least
    produces a warning; a card ccx fully understands produces a complete,
    plausible, unverified answer that is reported exactly like a verified one.
    The two solvers use different contact algorithms, so "it ran" is not
    evidence of anything.
    """
    deck = CLEAN_DECK.replace("*BOUNDARY", card + ", NAME=X\n*BOUNDARY", 1)
    reasons = scan_deck(deck)
    assert any(card in r for r in reasons), reasons


def test_a_full_contact_deck_is_refused_before_the_solve():
    with pytest.raises(DeckRefused):
        assert_translatable(CONTACT_DECK)


def test_contact_output_requests_are_not_caught_by_the_contact_refusal():
    """*CONTACT PRINT / *CONTACT FILE ask for output; they define no physics.

    Refusing them would be the mirror error: blocking a deck over a card that
    cannot change a single number.
    """
    deck = CLEAN_DECK.replace("*NODE PRINT, NSET=TIP\nU",
                              "*CONTACT PRINT\nCSTR\n*CONTACT FILE\nCDIS")
    assert scan_deck(deck) == []


def test_every_unverified_card_has_a_reason_that_says_why_not_just_that():
    from runner.ccx_whitelist import _UNVERIFIED_KEYWORDS, _UNVERIFIED_PROCEDURES

    for card in set(_UNVERIFIED_KEYWORDS) | set(_UNVERIFIED_PROCEDURES):
        deck = CLEAN_DECK.replace("*BOUNDARY", card.upper() + "\n*BOUNDARY", 1)
        reasons = [r for r in scan_deck(deck) if card.upper() in r]
        assert reasons, card
        assert "基准" in reasons[0], (
            "%s is refused without saying it is an unverified-baseline refusal, "
            "which reads as 'CalculiX cannot do this' — a different and false "
            "claim: %s" % (card, reasons[0]))


def test_no_card_is_both_allowed_and_unverified():
    from runner.ccx_whitelist import (
        _ALLOWED_KEYWORDS,
        _UNVERIFIED_KEYWORDS,
        _UNVERIFIED_PROCEDURES,
    )

    unverified = frozenset(_UNVERIFIED_KEYWORDS) | frozenset(_UNVERIFIED_PROCEDURES)
    assert not (_ALLOWED_KEYWORDS & unverified)


def test_no_step_type_the_matrix_refuses_is_reachable_through_a_deck():
    """The two gates read different inputs and must not disagree.

    core/backends.py refuses a procedure by reading `analysis.step_type` off the
    spec. For `geometry.type: custom_inp` the deck IS the model and `analysis:`
    is optional, so the matrix concludes Static and never asks. The deck-side
    gate is the only one that sees what the deck actually runs.
    """
    from core.backends import _STEP_KEYS

    card_for = {
        "Frequency": "*FREQUENCY",
        "Dynamic_Implicit": "*DYNAMIC",
        "Dynamic_Explicit": "*DYNAMIC, EXPLICIT",
        "Coupled_Temperature_Displacement": "*COUPLED TEMPERATURE-DISPLACEMENT",
        "Coupled_Thermal_Electrical": "*COUPLED THERMAL-ELECTRICAL",
    }
    missing = sorted(set(_STEP_KEYS) - set(card_for))
    assert not missing, (
        "the capability matrix refuses %s but this test does not know which "
        "card spells it, so nothing checks that a deck cannot smuggle it in"
        % missing)
    for step_type in _STEP_KEYS:
        deck = CLEAN_DECK.replace("*STATIC", card_for[step_type])
        assert scan_deck(deck), step_type


def test_untranslated_assembly_deck_is_refused_as_an_internal_error():
    deck = "*Part, name=Part-1\n" + CLEAN_DECK
    reasons = scan_deck(deck)
    assert any("展平" in r for r in reasons)


def test_whitespace_inside_a_keyword_cannot_smuggle_a_card_past():
    deck = CLEAN_DECK.replace("*SOLID SECTION", "*SOLID  SECTION")
    assert scan_deck(deck) == []
    sneaky = CLEAN_DECK.replace("*STATIC", "*COUPLED  THERMAL-ELECTRICAL")
    assert scan_deck(sneaky)


def test_comment_lines_are_not_mistaken_for_keywords():
    deck = CLEAN_DECK.replace("*HEADING", "** *INCIDENT WAVE INTERACTION\n*HEADING")
    assert scan_deck(deck) == []


def test_the_generated_cantilever_deck_passes_its_own_gate():
    """The generator and the whitelist must never drift apart."""
    spec = {
        "meta": {"model_name": "Cantilever"},
        "geometry": dict(GEO),
        "material": {"name": "Steel", "E": 210000.0, "nu": 0.3, "density": 7.85e-9},
        "analysis": {"step_type": "Static"},
        "bc_load": {"load_type": "concentrated_force", "value": -1.0, "direction": 2},
        "outputs": {"kpis": []},
    }
    deck = build_ccx_deck(spec, cantilever_block_mesh(GEO), [
        {"name": "U_tip", "type": "nodal_displacement", "location": "tip_center"},
        {"name": "MISES_MAX", "type": "field_max", "location": "whole_model"},
        {"name": "RF", "type": "reaction_force_max", "location": "fixed_face"},
    ])
    assert scan_deck(deck) == []


def test_a_translated_cae_deck_passes_the_gate(tmp_path):
    """Translation output must satisfy the gate, or custom_inp is dead on arrival."""
    from tests.test_ccx_deck import ASSEMBLY_DECK

    src = tmp_path / "src.inp"
    src.write_text(ASSEMBLY_DECK, encoding="utf-8")
    spec = {
        "meta": {"model_name": "M"},
        "geometry": {"type": "custom_inp", "inp_path": str(src)},
        "material": {"name": "Steel", "E": 1.0, "nu": 0.3},
        "analysis": {"step_type": "Static"},
        "bc_load": {"load_type": "concentrated_force", "value": -1.0, "direction": 2},
        "outputs": {"kpis": []},
    }
    inp, _ = write_ccx_deck(spec, tmp_path / "run", [
        {"name": "U_tip", "type": "nodal_displacement", "location": "tip_center"},
    ], source_inp=src)
    assert scan_deck(inp.read_text(encoding="utf-8")) == []
