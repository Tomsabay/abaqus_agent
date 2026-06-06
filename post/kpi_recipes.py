"""Built-in ODB Lens KPI recipes."""

from __future__ import annotations

from typing import Any

SUPPORTED_KPI_TYPES = {
    "nodal_displacement",
    "field_max",
    "field_min",
    "reaction_force_max",
    "eigenfrequency",
    "derived_stress_concentration",
}

KPI_RECIPES: list[dict[str, Any]] = [
    {
        "id": "cantilever-tip-displacement",
        "case": "cantilever",
        "title": "Cantilever tip displacement",
        "description": "Read vertical displacement from the tip node set.",
        "kpi_spec": [
            {
                "name": "U_tip",
                "type": "nodal_displacement",
                "component": "U2",
                "location": "tip",
            }
        ],
    },
    {
        "id": "cantilever-fixed-reaction",
        "case": "cantilever",
        "title": "Cantilever fixed-end reaction",
        "description": "Read maximum absolute reaction force at the fixed end.",
        "kpi_spec": [
            {
                "name": "RF_fixed",
                "type": "reaction_force_max",
                "component": "RF2",
                "location": "fixed_face",
            }
        ],
    },
    {
        "id": "plate-hole-max-mises",
        "case": "plate_hole",
        "title": "Plate-hole max Mises stress",
        "description": "Read maximum Mises stress around the hole edge.",
        "kpi_spec": [
            {
                "name": "MISES_HOLE_EDGE",
                "type": "field_max",
                "field_variable": "S",
                "location": "hole_edge_set",
            }
        ],
    },
    {
        "id": "plate-hole-stress-concentration",
        "case": "plate_hole",
        "title": "Plate-hole stress concentration",
        "description": "Read the hole-edge stress concentration proxy from stress field output.",
        "kpi_spec": [
            {
                "name": "SCF",
                "type": "derived_stress_concentration",
                "location": "hole_edge_set",
            }
        ],
    },
    {
        "id": "modal-first-three-frequencies",
        "case": "modal",
        "title": "First three modal frequencies",
        "description": "Read eigenfrequencies from the first three modal frames.",
        "kpi_spec": [
            {"name": "freq_1", "type": "eigenfrequency", "location": "mode_1"},
            {"name": "freq_2", "type": "eigenfrequency", "location": "mode_2"},
            {"name": "freq_3", "type": "eigenfrequency", "location": "mode_3"},
        ],
    },
    {
        "id": "explicit-impact-peak-displacement",
        "case": "explicit_impact",
        "title": "Explicit impact peak displacement",
        "description": "Read displacement extrema from an impact/load-end node set.",
        "kpi_spec": [
            {
                "name": "U_impact_min",
                "type": "field_min",
                "field_variable": "U",
                "component": "U3",
                "location": "top_face",
            },
            {
                "name": "U_impact_max",
                "type": "field_max",
                "field_variable": "U",
                "component": "U3",
                "location": "top_face",
            },
        ],
    },
]


def list_kpi_recipes(case: str = "", kpi_type: str = "") -> dict[str, Any]:
    normalized_case = case.strip().lower()
    normalized_type = kpi_type.strip()
    items = []
    for recipe in KPI_RECIPES:
        if normalized_case and recipe["case"].lower() != normalized_case:
            continue
        if normalized_type and normalized_type not in _recipe_types(recipe):
            continue
        items.append(_with_metadata(recipe))
    return {
        "schema_version": "1.0",
        "workflow": "kpi-recipe-gallery",
        "supported_kpi_types": sorted(SUPPORTED_KPI_TYPES),
        "items": items,
        "total": len(items),
    }


def get_kpi_recipe(recipe_id: str) -> dict[str, Any]:
    for recipe in KPI_RECIPES:
        if recipe["id"] == recipe_id:
            return _with_metadata(recipe)
    raise KeyError(f"KPI recipe not found: {recipe_id}")


def _with_metadata(recipe: dict[str, Any]) -> dict[str, Any]:
    item = dict(recipe)
    item["kpi_types"] = sorted(_recipe_types(recipe))
    item["real_env_verified"] = False
    item["verification_boundary"] = (
        "Recipe shape is source-supported and fake-ODB tested where covered; "
        "it does not prove real Abaqus ODB extraction on this machine."
    )
    return item


def _recipe_types(recipe: dict[str, Any]) -> set[str]:
    return {entry["type"] for entry in recipe["kpi_spec"]}
