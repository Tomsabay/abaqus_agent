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
    def __init__(self, values, subsets=None):
        self.values = values
        self._subsets = subsets or {}

    def getSubset(self, region):
        return FakeField(self._subsets[region])


def _value(**kwargs):
    return SimpleNamespace(**kwargs)


def _odb_with_frame(frame, *, frames=None, node_sets=None, element_sets=None):
    return SimpleNamespace(
        steps={"Step-1": SimpleNamespace(frames=frames or [frame])},
        rootAssembly=SimpleNamespace(
            nodeSets=node_sets or {},
            elementSets=element_sets or {},
        ),
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


def test_extract_field_min_raises_when_field_is_missing():
    odb = _odb_with_frame(SimpleNamespace(fieldOutputs={}))

    with pytest.raises(KeyError, match="Field 'U' not in frame"):
        extract_module._extract_single_kpi(odb, {"type": "field_min"})
