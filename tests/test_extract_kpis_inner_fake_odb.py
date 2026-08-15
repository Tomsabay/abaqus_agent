from __future__ import annotations

import importlib
from types import SimpleNamespace

import pytest

from post.kpi_recipes import KPI_RECIPES, SUPPORTED_KPI_TYPES

extract_module = importlib.import_module("post.extract_kpis")


def test_kpi_recipe_gallery_uses_supported_extraction_types():
    recipe_types = {
        kpi["type"]
        for recipe in KPI_RECIPES
        for kpi in recipe["kpi_spec"]
    }
    assert recipe_types == SUPPORTED_KPI_TYPES
    assert {"cantilever", "plate_hole", "modal", "explicit_impact"}.issubset(
        {recipe["case"] for recipe in KPI_RECIPES}
    )


class FakeField:
    def __init__(self, values, subsets=None, position_subsets=None):
        self.values = values
        self._subsets = subsets or {}
        self._position_subsets = position_subsets or {}

    def getSubset(self, region=None, position=None):
        # Mirrors the real API surface the extractor uses: getSubset(region=...)
        # and getSubset(position=ELEMENT_NODAL) are separate calls, and the
        # ordering between them is load-bearing (a region subset chained into a
        # position subset silently loses the region on real ODBs). A subset
        # entry may itself be a FakeField so tests can model that chain
        # faithfully instead of raising where the real API would not.
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


def _instance(*, node_sets=None, element_sets=None):
    return SimpleNamespace(
        nodeSets=node_sets or {},
        elementSets=element_sets or {},
    )


def test_extract_nodal_displacement_uses_subset_and_component_minimum():
    tip_region = object()
    field = FakeField(
        [_value(data=(0.0, 99.0, 0.0))],
        subsets={
            tip_region: [
                _value(data=(0.0, -1.5, 0.0)),
                _value(data=(0.0, -3.25, 0.0)),
            ]
        },
    )
    odb = _odb_with_frame(
        SimpleNamespace(fieldOutputs={"U": field}),
        node_sets={"TIP": tip_region},
    )

    result = extract_module._extract_single_kpi(
        odb,
        {"type": "nodal_displacement", "component": "U2", "location": "TIP"},
    )

    assert result == -3.25


def test_extract_nodal_displacement_resolves_benchmark_tip_center_alias():
    tip_region = object()
    field = FakeField(
        [_value(data=(0.0, 99.0, 0.0))],
        subsets={tip_region: [_value(data=(0.0, -2.75, 0.0))]},
    )
    odb = _odb_with_frame(
        SimpleNamespace(fieldOutputs={"U": field}),
        node_sets={"TIP_NODES": tip_region},
    )

    result = extract_module._extract_single_kpi(
        odb,
        {"type": "nodal_displacement", "component": "U2", "location": "tip_center"},
    )

    assert result == -2.75


def test_extract_field_max_mises_uses_stress_field():
    odb = _odb_with_frame(
        SimpleNamespace(
            fieldOutputs={
                "S": FakeField(
                    [
                        _value(mises=12.0),
                        _value(mises=32.5),
                        _value(mises=18.0),
                    ]
                )
            }
        )
    )

    result = extract_module._extract_single_kpi(odb, {"type": "field_max", "name": "max_mises"})

    assert result == 32.5


def test_extract_field_max_mises_uses_location_subset():
    hole_region = object()
    field = FakeField(
        [_value(mises=100.0)],
        subsets={
            hole_region: [
                _value(mises=24.0),
                _value(mises=33.5),
            ]
        },
    )
    odb = _odb_with_frame(
        SimpleNamespace(fieldOutputs={"S": field}),
        element_sets={"HOLE_EDGE": hole_region},
    )

    result = extract_module._extract_single_kpi(
        odb,
        {"type": "field_max", "name": "MISES_HOLE_EDGE", "location": "hole_edge_set"},
    )

    assert result == 33.5


def test_extract_field_max_displacement_component_defaults_to_u_field():
    odb = _odb_with_frame(
        SimpleNamespace(
            fieldOutputs={
                "S": FakeField([_value(data=(999.0, 0.0, 0.0))]),
                "U": FakeField(
                    [
                        _value(data=(0.25, 0.0, 0.0)),
                        _value(data=(0.75, 0.0, 0.0)),
                    ]
                ),
            }
        )
    )

    result = extract_module._extract_single_kpi(
        odb,
        {"type": "field_max", "name": "U_X_MAX", "component": "U1"},
    )

    assert result == 0.75


def test_extract_field_min_uses_requested_component():
    odb = _odb_with_frame(
        SimpleNamespace(
            fieldOutputs={
                "U": FakeField(
                    [
                        _value(data=(0.0, 1.0, -0.5)),
                        _value(data=(0.0, 2.0, -4.0)),
                    ]
                )
            }
        )
    )

    result = extract_module._extract_single_kpi(
        odb,
        {"type": "field_min", "field_variable": "U", "component": "U3"},
    )

    assert result == -4.0


def test_extract_field_min_uses_location_subset():
    tip_region = object()
    field = FakeField(
        [_value(data=(0.0, -99.0, 0.0))],
        subsets={tip_region: [_value(data=(0.0, -6.0, 0.0))]},
    )
    odb = _odb_with_frame(
        SimpleNamespace(fieldOutputs={"U": field}),
        node_sets={"TIP_NODES": tip_region},
    )

    result = extract_module._extract_single_kpi(
        odb,
        {
            "type": "field_min",
            "field_variable": "U",
            "component": "U2",
            "location": "tip_center",
        },
    )

    assert result == -6.0


def test_extract_field_min_resolves_top_face_alias():
    top_region = object()
    field = FakeField(
        [_value(data=(0.0, 0.0, -99.0))],
        subsets={top_region: [_value(data=(0.0, 0.0, -2.0))]},
    )
    odb = _odb_with_frame(
        SimpleNamespace(fieldOutputs={"U": field}),
        node_sets={"LOAD_END": top_region},
    )

    result = extract_module._extract_single_kpi(
        odb,
        {
            "type": "field_min",
            "field_variable": "U",
            "component": "U3",
            "location": "top_face",
        },
    )

    assert result == -2.0


def test_extract_reaction_force_max_uses_absolute_component():
    odb = _odb_with_frame(
        SimpleNamespace(
            fieldOutputs={
                "RF": FakeField(
                    [
                        _value(data=(0.0, 0.0, -14.0)),
                        _value(data=(0.0, 0.0, 9.5)),
                    ]
                )
            }
        )
    )

    result = extract_module._extract_single_kpi(
        odb,
        {"type": "reaction_force_max", "component": "RF3"},
    )

    assert result == 14.0


def test_extract_reaction_force_max_resolves_fixed_face_alias():
    fixed_region = object()
    field = FakeField(
        [_value(data=(0.0, 0.0, -99.0))],
        subsets={fixed_region: [_value(data=(0.0, 0.0, -12.0))]},
    )
    odb = _odb_with_frame(
        SimpleNamespace(fieldOutputs={"RF": field}),
        node_sets={"FIXED_END": fixed_region},
    )

    result = extract_module._extract_single_kpi(
        odb,
        {"type": "reaction_force_max", "component": "RF3", "location": "fixed_face"},
    )

    assert result == 12.0


def test_extract_eigenfrequency_uses_requested_mode_frame():
    frames = [
        SimpleNamespace(fieldOutputs={}, frequency=12.5),
        SimpleNamespace(fieldOutputs={}, frequency=47.25),
        SimpleNamespace(fieldOutputs={}, frequency=88.0),
    ]
    odb = _odb_with_frame(frames[-1], frames=frames)

    result = extract_module._extract_single_kpi(
        odb,
        {"type": "eigenfrequency", "location": "mode_2"},
    )

    assert result == 47.25


def test_extract_eigenfrequency_skips_base_state_frame():
    """Real frequency ODBs put a 0 Hz base state at frames[0]; mode_1 must
    read the first actual mode, not the base state."""
    frames = [
        SimpleNamespace(fieldOutputs={}, frequency=0.0, mode=0),
        SimpleNamespace(fieldOutputs={}, frequency=209.56, mode=1),
        SimpleNamespace(fieldOutputs={}, frequency=415.97, mode=2),
    ]
    odb = _odb_with_frame(frames[-1], frames=frames)

    assert extract_module._extract_single_kpi(
        odb, {"type": "eigenfrequency", "location": "mode_1"}) == 209.56
    assert extract_module._extract_single_kpi(
        odb, {"type": "eigenfrequency", "location": "mode_2"}) == 415.97


def test_extract_eigenfrequency_base_state_without_mode_attr():
    """Same base-state layout but frames lack the .mode attribute — the
    positional fallback must still skip the 0 Hz frame."""
    frames = [
        SimpleNamespace(fieldOutputs={}, frequency=0.0),
        SimpleNamespace(fieldOutputs={}, frequency=100.0),
        SimpleNamespace(fieldOutputs={}, frequency=200.0),
    ]
    odb = _odb_with_frame(frames[-1], frames=frames)

    assert extract_module._extract_single_kpi(
        odb, {"type": "eigenfrequency", "location": "mode_1"}) == 100.0


def test_extract_derived_stress_concentration_uses_element_subset():
    hole_region = object()
    field = FakeField(
        [_value(mises=5.0)],
        subsets={
            hole_region: [
                _value(mises=28.0),
                _value(mises=41.0),
            ]
        },
    )
    odb = _odb_with_frame(
        SimpleNamespace(fieldOutputs={"S": field}),
        element_sets={"HOLE": hole_region},
    )

    result = extract_module._extract_single_kpi(
        odb,
        {"type": "derived_stress_concentration", "location": "hole"},
    )

    assert result == 41.0


def test_extract_derived_stress_concentration_resolves_hole_edge_set_alias():
    hole_region = object()
    field = FakeField(
        [_value(mises=5.0)],
        subsets={hole_region: [_value(mises=37.0)]},
    )
    odb = _odb_with_frame(
        SimpleNamespace(fieldOutputs={"S": field}),
        element_sets={"HOLE_EDGE": hole_region},
    )

    result = extract_module._extract_single_kpi(
        odb,
        {"type": "derived_stress_concentration", "location": "hole_edge_set"},
    )

    assert result == 37.0


# ---------------------------------------------------------------------------
# Location honesty. The layout every real ODB in this repo actually has:
# sets on the instance, rootAssembly holding only the auto sets. The old
# assembly-only search could never find them, and its None fell through to
# the whole field — "stress at the hole edge" silently became "max stress
# anywhere in the model", with errors: []. Measured on plate_hole: 100.03 MPa
# requested vs 295.57 MPa reported, a 2.95x overstatement.
# ---------------------------------------------------------------------------


def test_resolve_region_finds_instance_level_set():
    hole_region = object()
    field = FakeField(
        [_value(mises=295.57)],
        subsets={hole_region: [_value(mises=100.03)]},
    )
    odb = _odb_with_frame(
        SimpleNamespace(fieldOutputs={"S": field}),
        element_sets={},  # the measured real layout: nothing useful on assembly
        instances={"PART-1-1": _instance(element_sets={"HOLE_EDGE": hole_region})},
    )

    result = extract_module._extract_single_kpi(
        odb,
        {"type": "field_max", "name": "MISES_HOLE_EDGE", "location": "hole_edge_set"},
    )

    assert result == 100.03, "the instance-level set must be honoured, not the whole model"


def test_unresolvable_location_raises_instead_of_whole_model():
    field = FakeField([_value(mises=295.57)])
    odb = _odb_with_frame(
        SimpleNamespace(fieldOutputs={"S": field}),
        element_sets={"OTHER_SET": object()},
        instances={"PART-1-1": _instance(element_sets={"ANOTHER": object()})},
    )

    with pytest.raises(KeyError) as exc:
        extract_module._extract_single_kpi(
            odb,
            {"type": "field_max", "name": "MISES_X", "location": "hole_edge_set"},
        )

    message = str(exc.value)
    assert "hole_edge_set" in message
    assert "OTHER_SET" in message and "ANOTHER" in message, (
        "the refusal must name what exists so the user can fix the spec")


def test_whole_model_location_short_circuits_without_any_set():
    """whole_model must not require an ALL set to exist.

    NODE_SET_ALIASES has no whole_model entry, so resolving it through the
    alias tables breaks every nodal-field KPI that legitimately wants the
    whole model (plate_hole U_X_MAX, blast_plate U_MAX_DEFLECTION — both
    frozen baselines). The unsubsetted field IS the whole model.
    """
    field = FakeField([
        _value(data=(0.0501, 0.0, 0.0)),
        _value(data=(0.0123, 0.0, 0.0)),
    ])
    odb = _odb_with_frame(
        SimpleNamespace(fieldOutputs={"U": field}),
        # deliberately NO sets anywhere, not even ALL
        instances={"PART-1-1": _instance()},
    )

    result = extract_module._extract_single_kpi(
        odb,
        {"type": "field_max", "name": "U_X_MAX", "component": "U1",
         "location": "whole_model"},
    )

    assert result == 0.0501


def test_mises_field_max_applies_region_after_position(monkeypatch):
    """Position first, then region — the reverse order loses the region.

    Measured on the real plate_hole ODB: region-then-position came back with
    the whole model's 2504 values instead of the hole edge's 20.
    """
    import sys

    monkeypatch.setitem(
        sys.modules, "abaqusConstants", SimpleNamespace(ELEMENT_NODAL="EN"))

    hole_region = object()
    # Correct order: position → whole-model ELEMENT_NODAL field, whose region
    # subset narrows to the hole edge (100.03).
    en_whole = FakeField(
        [_value(mises=295.57), _value(mises=100.03)],
        subsets={hole_region: [_value(mises=100.03)]},
    )
    # Wrong order: region → IP subset whose chained position call silently
    # comes back as the WHOLE MODEL (the measured real behaviour: 20 values
    # ballooned to 2504) — not an exception the except could excuse.
    region_ip = FakeField(
        [_value(mises=264.14)],
        position_subsets={"EN": [_value(mises=295.57), _value(mises=100.03)]},
    )
    field = FakeField(
        [_value(mises=264.14)],
        position_subsets={"EN": en_whole},
        subsets={hole_region: region_ip},
    )
    odb = _odb_with_frame(
        SimpleNamespace(fieldOutputs={"S": field}),
        instances={"PART-1-1": _instance(element_sets={"HOLE_EDGE": hole_region})},
    )

    result = extract_module._extract_single_kpi(
        odb,
        {"type": "field_max", "name": "MISES_HOLE_EDGE", "location": "hole_edge_set"},
    )

    assert result == 100.03, (
        "region-then-position would have reported the whole-model 295.57")


def test_a_stress_component_is_read_at_the_same_position_as_mises(monkeypatch):
    """Two KPIs of the same field have to come from the same place.

    Measured on a plate with a hole: the same peak read as Mises came back
    3.0966 (element nodal) and as S22 came back 2.8420 (integration point) --
    an 8.2% gap between two numbers that are the same quantity at a
    traction-free point. Neither was wrong for its position; they simply were
    not comparable, and nothing in the output said so. Integration points sit
    INSIDE the element, so they systematically under-report a surface peak,
    which is exactly where a stress concentration lives.
    """
    import sys

    monkeypatch.setitem(
        sys.modules, "abaqusConstants", SimpleNamespace(ELEMENT_NODAL="EN"))

    field = FakeField(
        [_value(data=(0.0, 2.842, 0.0))],                       # integration pt
        position_subsets={"EN": [_value(data=(0.0, 3.113, 0.0))]},  # nodal
    )
    odb = _odb_with_frame(SimpleNamespace(fieldOutputs={"S": field}))

    result = extract_module._extract_single_kpi(
        odb,
        {"type": "field_max", "name": "HOOP_S22", "field_variable": "S",
         "component": "S22"},
    )

    assert result == 3.113, "the component branch still reads integration points"


def test_a_displacement_component_is_not_moved_to_element_nodal(monkeypatch):
    """U has no ELEMENT_NODAL position, and asking for one would either raise
    or return something that is not the displacement."""
    import sys

    monkeypatch.setitem(
        sys.modules, "abaqusConstants", SimpleNamespace(ELEMENT_NODAL="EN"))

    # No position_subsets at all: if the extractor asked, this would KeyError.
    field = FakeField([_value(data=(0.0, -3.25, 0.0))])
    odb = _odb_with_frame(SimpleNamespace(fieldOutputs={"U": field}))

    result = extract_module._extract_single_kpi(
        odb,
        {"type": "field_max", "field_variable": "U", "component": "U2"},
    )

    assert result == -3.25


def test_field_min_on_a_stress_uses_the_same_position_rule(monkeypatch):
    """A spec that reads S22 min and S22 max must get both from one place."""
    import sys

    monkeypatch.setitem(
        sys.modules, "abaqusConstants", SimpleNamespace(ELEMENT_NODAL="EN"))

    field = FakeField(
        [_value(data=(0.0, -1.0, 0.0))],
        position_subsets={"EN": [_value(data=(0.0, -1.4, 0.0))]},
    )
    odb = _odb_with_frame(SimpleNamespace(fieldOutputs={"S": field}))

    result = extract_module._extract_single_kpi(
        odb,
        {"type": "field_min", "field_variable": "S", "component": "S22"},
    )

    assert result == -1.4


def test_empty_selection_raises_not_zero():
    """0.0 for an empty selection once shipped as a real KPI.

    steel_frame_blast run 1ee6589b reported U2_MAX_LATERAL: 0.0 with
    errors: [] — a fabricated number in frozen evidence.
    """
    with pytest.raises(ValueError, match="no values selected"):
        extract_module._reduce_values([], None, "max")


def test_field_min_on_stress_variable_prefers_element_sets():
    """field_min hardcoded "node"; its var_name can be S (a stress trough)."""
    stress_region = object()
    field = FakeField(
        [_value(data=(-50.0, 0.0, 0.0))],
        subsets={stress_region: [_value(data=(-120.0, 0.0, 0.0))]},
    )
    odb = _odb_with_frame(
        SimpleNamespace(fieldOutputs={"S": field}),
        instances={"PART-1-1": _instance(
            element_sets={"HOLE_EDGE": stress_region},
            # a node set with the same name must NOT win for a stress field
            node_sets={"HOLE_EDGE": object()},
        )},
    )

    result = extract_module._extract_single_kpi(
        odb,
        {"type": "field_min", "name": "S11_MIN", "component": "S11",
         "location": "hole_edge"},
    )

    assert result == -120.0


def test_history_output_missing_variable_raises_not_zero():
    step = SimpleNamespace(
        frames=[SimpleNamespace(fieldOutputs={})],
        historyRegions={
            "Assembly ASSEMBLY": SimpleNamespace(
                historyOutputs={"ALLKE": SimpleNamespace(data=[(0.0, 1.0)])}),
        },
    )
    odb = SimpleNamespace(steps={"Step-1": step}, rootAssembly=SimpleNamespace(
        nodeSets={}, elementSets={}, instances={}))

    with pytest.raises(ValueError, match="no values selected"):
        extract_module._extract_single_kpi(
            odb,
            {"type": "history_output_max", "name": "U2_MAX_LATERAL",
             "variable": "DOES_NOT_EXIST"},
        )


def test_extract_field_min_raises_when_field_is_missing():
    odb = _odb_with_frame(SimpleNamespace(fieldOutputs={}))

    with pytest.raises(KeyError, match="Field 'U' not in frame"):
        extract_module._extract_single_kpi(odb, {"type": "field_min"})
