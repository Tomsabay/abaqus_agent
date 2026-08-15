"""The extraction layer used to answer questions it had not been asked.

Three fail-open paths, each measured before this file existed:

  * an unrecognised component fell back to a default index, so ``S12`` came
    back as ``S11`` -- and because the four call sites pass three different
    defaults, the SAME typo returned a different wrong number depending on
    which KPI type it appeared in;
  * ``invariant:`` was compared against the single string ``MISES``, so
    ``TRESCA``/``MAX_PRINCIPAL``/``PRESS`` fell through to ``.magnitude`` --
    four different physical quantities collapsing to one number, none of them
    the one requested;
  * the human-readable ``name`` was a dispatch key that ran AFTER and
    overrode the machine-readable ``field_variable``.

None of the three raised. The CalculiX extractor (``extract_kpis_ccx.py``)
has always refused the first one outright; the strict backend was the
secondary one. These tests pin the primary path to the same contract.

The name-based dispatch is kept as a FALLBACK, not removed: five frozen
cases (cantilever, cantilever_plastic, plate_hole, two_plate_tie,
two_plate_contact) name a KPI ``MISES_*`` and declare neither
``field_variable`` nor ``invariant``. Deleting it would silently move those
five from the Mises invariant to a vector magnitude -- the exact class of
failure this file exists to close.
"""
from __future__ import annotations

import importlib
from types import SimpleNamespace

import pytest

extract_module = importlib.import_module("post.extract_kpis")


class FakeField:
    def __init__(self, values, subsets=None, position_subsets=None):
        self.values = values
        self._subsets = subsets or {}
        self._position_subsets = position_subsets or {}

    def getSubset(self, region=None, position=None):
        target = (self._position_subsets[position] if position is not None
                  else self._subsets[region])
        return target if isinstance(target, FakeField) else FakeField(target)


def _value(**kwargs):
    return SimpleNamespace(**kwargs)


def _odb_with_frame(frame, *, frames=None, node_sets=None, element_sets=None,
                    instances=None):
    return SimpleNamespace(
        steps={"Step-1": SimpleNamespace(frames=frames or [frame])},
        rootAssembly=SimpleNamespace(
            nodeSets=node_sets or {},
            elementSets=element_sets or {},
            instances=instances or {},
        ),
    )


# --- components -------------------------------------------------------------

# 111 and 222 differ so a fallback to index 0 is visibly not index 1.
_TENSOR = [_value(data=(111.0, 222.0, 333.0, 12.0, 0.0, 0.0))]


def _stress_odb():
    return _odb_with_frame(SimpleNamespace(fieldOutputs={"S": FakeField(_TENSOR)}))


@pytest.mark.parametrize("component", ["S12", "S23", "S13"])
def test_a_shear_component_is_refused_not_silently_read_as_a_normal_one(component):
    """S12 came back as S11 -- a shear stress reported as a normal stress."""
    with pytest.raises(KeyError) as excinfo:
        extract_module._extract_single_kpi(
            _stress_odb(),
            {"type": "field_max", "name": "SHEAR", "field_variable": "S",
             "component": component},
        )
    message = str(excinfo.value)
    assert component in message
    # The refusal has to say what IS available or it is not actionable.
    assert "S11" in message and "U2" in message and "RF3" in message


def test_a_strain_component_is_refused():
    """E22 resolved to 0, which is E11 -- the wrong direction of the wrong
    quantity, since the E field was never even selected."""
    with pytest.raises(KeyError, match="E22"):
        extract_module._extract_single_kpi(
            _stress_odb(),
            {"type": "field_max", "name": "STRAIN", "field_variable": "S",
             "component": "E22"},
        )


def test_a_rotation_component_is_refused():
    """UR3 resolved to 1 under nodal_displacement's default -- U2, a
    translation reported as a rotation."""
    odb = _odb_with_frame(
        SimpleNamespace(fieldOutputs={"U": FakeField(
            [_value(data=(1.0, 2.0, 3.0))])}))
    with pytest.raises(KeyError, match="UR3"):
        extract_module._extract_single_kpi(
            odb, {"type": "nodal_displacement", "component": "UR3"})


def test_one_typo_cannot_return_three_different_wrong_numbers():
    """The four call sites passed defaults 1 / 0 / 2 / 2, so the same
    unrecognised name resolved to a different index per KPI type. Whatever
    the answer is, it must not depend on which question was asked."""
    for kpi_type in ("field_max", "field_min", "reaction_force_max",
                     "nodal_displacement"):
        odb = _odb_with_frame(SimpleNamespace(fieldOutputs={
            "S": FakeField(_TENSOR),
            "U": FakeField(_TENSOR),
            "RF": FakeField(_TENSOR),
        }))
        with pytest.raises(KeyError, match="S12"):
            extract_module._extract_single_kpi(
                odb, {"type": kpi_type, "name": "X", "field_variable": "S",
                      "component": "S12"})


@pytest.mark.parametrize("component,index", [
    ("U1", 0), ("U2", 1), ("U3", 2),
    ("S11", 0), ("S22", 1), ("S33", 2),
    ("RF1", 0), ("RF2", 1), ("RF3", 2),
])
def test_every_recorded_component_still_resolves(component, index):
    """The seven in use across shipped cases (RF1/RF2/RF3, U1/U2/U3, S22) are
    all in this list, so fail-closed breaks no frozen baseline."""
    assert extract_module._component_index(component) == index


def test_the_component_table_is_the_one_the_refusal_advertises():
    """A refusal that lists names the resolver does not accept is a lie."""
    for name in extract_module._COMPONENT_INDEX:
        assert extract_module._component_index(name) is not None


@pytest.mark.parametrize("name", ["MISES", "TRESCA", "MAX_PRINCIPAL"])
def test_an_invariant_in_the_component_slot_is_told_which_key_to_use(name):
    """The one wrong spelling worth naming, because it is the plausible one.

    MISES is what an engineer calls the number and it is not a component of
    anything. Measured: this exact confusion sat in
    scripts/run_dropped_input_check.py, where `component: MISES` had worked by
    accident for as long as an unknown name still resolved to a default index.
    A refusal that only says "not one of U1, U2, U3 ..." sends that reader
    looking for a component that does not exist.
    """
    with pytest.raises(KeyError) as caught:
        extract_module._component_index(name)
    message = str(caught.value)
    assert "invariant" in message
    assert "invariant: %s" % name in message


# --- invariants -------------------------------------------------------------

# One value carrying every invariant, all different: whichever one comes back
# identifies which branch ran.
_ALL_INVARIANTS = [_value(
    mises=88.0, maxPrincipal=107.0, midPrincipal=3.0, minPrincipal=-7.0,
    tresca=114.0, press=-50.0, inv3=61.0, magnitude=123.456,
    data=(1.0, 2.0, 3.0, 4.0, 5.0, 6.0),
)]


def _invariant_odb():
    return _odb_with_frame(
        SimpleNamespace(fieldOutputs={"S": FakeField(_ALL_INVARIANTS)}))


@pytest.mark.parametrize("invariant,expected", [
    ("MISES", 88.0),
    ("MAX_PRINCIPAL", 107.0),
    ("MIN_PRINCIPAL", -7.0),
    ("MID_PRINCIPAL", 3.0),
    ("TRESCA", 114.0),
    ("PRESS", -50.0),
    ("INV3", 61.0),
])
def test_a_named_invariant_is_read_not_the_magnitude(invariant, expected):
    """All four of the previously-unhandled names returned 123.456."""
    result = extract_module._extract_single_kpi(
        _invariant_odb(),
        {"type": "field_max", "name": "PEAK", "field_variable": "S",
         "invariant": invariant},
    )
    assert result == expected


def test_an_unknown_invariant_is_refused():
    with pytest.raises(ValueError) as excinfo:
        extract_module._extract_single_kpi(
            _invariant_odb(),
            {"type": "field_max", "name": "PEAK", "field_variable": "S",
             "invariant": "VON_MISES"},
        )
    message = str(excinfo.value)
    assert "VON_MISES" in message and "MISES" in message


def test_an_invariant_and_a_component_together_are_refused():
    """Today the component branch wins and the invariant vanishes, so the
    spec says one thing and the number is another."""
    with pytest.raises(ValueError, match="invariant"):
        extract_module._extract_single_kpi(
            _invariant_odb(),
            {"type": "field_max", "name": "PEAK", "field_variable": "S",
             "invariant": "TRESCA", "component": "S22"},
        )


# --- the name is not a dispatch key -----------------------------------------

def test_an_explicit_field_variable_beats_the_kpi_name():
    """`if "MISES" in name` had no elif, so it overrode the declaration that
    came four lines above it. Only the human-readable label changed and the
    quantity went from plastic strain to Mises stress."""
    odb = _odb_with_frame(SimpleNamespace(fieldOutputs={
        "S": FakeField([_value(mises=999.0, magnitude=999.0)]),
        "PEEQ": FakeField([_value(data=0.05)]),
    }))

    result = extract_module._extract_single_kpi(
        odb,
        {"type": "field_max", "name": "MISES_UTILISATION",
         "field_variable": "PEEQ"},
    )

    assert result == 0.05, "the name must not override field_variable"


def test_an_explicit_invariant_beats_the_kpi_name():
    odb = _odb_with_frame(
        SimpleNamespace(fieldOutputs={"S": FakeField(_ALL_INVARIANTS)}))

    result = extract_module._extract_single_kpi(
        odb,
        {"type": "field_max", "name": "MISES_MAX", "field_variable": "S",
         "invariant": "TRESCA"},
    )

    assert result == 114.0


def test_the_name_still_dispatches_when_nothing_is_declared():
    """Five frozen cases depend on this: MISES_MAX with no field_variable and
    no invariant must still read the Mises invariant of S."""
    odb = _odb_with_frame(
        SimpleNamespace(fieldOutputs={"S": FakeField(_ALL_INVARIANTS)}))

    assert extract_module._extract_single_kpi(
        odb, {"type": "field_max", "name": "MISES_MAX"}) == 88.0


def test_a_peeq_name_still_dispatches_when_nothing_is_declared():
    odb = _odb_with_frame(SimpleNamespace(fieldOutputs={
        "S": FakeField([_value(mises=999.0)]),
        "PEEQ": FakeField([_value(data=0.05)]),
    }))

    assert extract_module._extract_single_kpi(
        odb, {"type": "field_max", "name": "PEEQ_MAX"}) == 0.05


# --- history output regions --------------------------------------------------

def _history_odb():
    step = SimpleNamespace(
        frames=[SimpleNamespace(fieldOutputs={})],
        historyRegions={
            "Node ROOF.1": SimpleNamespace(historyOutputs={
                "U2": SimpleNamespace(data=[(0.0, 0.0), (1.0, 10.0)])}),
            "Node BASE.7": SimpleNamespace(historyOutputs={
                "U2": SimpleNamespace(data=[(0.0, 0.0), (1.0, -500.0)])}),
            "Assembly ASSEMBLY": SimpleNamespace(historyOutputs={
                "ALLPD": SimpleNamespace(data=[(0.0, 0.0), (1.0, 7.5)])}),
        },
    )
    return SimpleNamespace(steps={"Step-1": step}, rootAssembly=SimpleNamespace(
        nodeSets={}, elementSets={}, instances={}))


def test_history_output_honours_location():
    """`location` was never read: asking for the roof peak returned the base
    node's -500 because abs_max ran over every region at once."""
    result = extract_module._extract_single_kpi(
        _history_odb(),
        {"type": "history_output_max", "name": "U2_ROOF_PEAK",
         "variable": "U2", "location": "ROOF", "reducer": "abs_max"},
    )
    assert result == 10.0


def test_history_output_refuses_a_location_that_matches_no_region():
    with pytest.raises(KeyError) as excinfo:
        extract_module._extract_single_kpi(
            _history_odb(),
            {"type": "history_output_max", "name": "X", "variable": "U2",
             "location": "PENTHOUSE"},
        )
    message = str(excinfo.value)
    assert "PENTHOUSE" in message
    assert "ROOF" in message, "the refusal must name the regions that exist"


def test_history_output_without_location_still_aggregates():
    """Three frozen KPIs (blast_plate ALLPD_MAX, steel_frame_blast ALLPD_MAX
    and U2_ROOF_PEAK) carry no location. Requiring one would break them."""
    result = extract_module._extract_single_kpi(
        _history_odb(),
        {"type": "history_output_max", "name": "ALLPD_MAX",
         "variable": "ALLPD"},
    )
    assert result == 7.5
