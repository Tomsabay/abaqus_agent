"""
coupled_materials.py
--------------------
Material property code generators for multi-physics analyses.

Extends the base elastic material with thermal, electrical,
and expansion properties needed for coupled simulations.
"""

from __future__ import annotations


def generate_thermal_material_code(mat: dict, model_name: str) -> str:
    """
    Generate additional material property code for coupled analyses.

    Adds conductivity, specific heat, and expansion to existing material.
    """
    mat_name = mat["name"]
    code_parts = []

    # Thermal conductivity
    if "conductivity" in mat:
        code_parts.append(f"""
mdb.models['{model_name}'].materials['{mat_name}'].Conductivity(
    table=(({mat['conductivity']},),))
""")

    # Specific heat
    if "specific_heat" in mat:
        code_parts.append(f"""
mdb.models['{model_name}'].materials['{mat_name}'].SpecificHeat(
    table=(({mat['specific_heat']},),))
""")

    # Thermal expansion
    if "expansion_coeff" in mat:
        code_parts.append(f"""
mdb.models['{model_name}'].materials['{mat_name}'].Expansion(
    table=(({mat['expansion_coeff']},),))
""")

    # Electrical conductivity
    if "electrical_conductivity" in mat:
        code_parts.append(f"""
mdb.models['{model_name}'].materials['{mat_name}'].ElectricalConductivity(
    table=(({mat['electrical_conductivity']},),))
""")

    # Inelastic heat fraction (for coupled thermo-mechanical)
    if mat.get("yield_stress") and mat.get("conductivity"):
        code_parts.append(f"""
mdb.models['{model_name}'].materials['{mat_name}'].InelasticHeatFraction(fraction=0.9)
""")

    return "\n".join(code_parts) if code_parts else "# No additional thermal/electrical properties\n"


def needs_thermal_properties(spec: dict) -> bool:
    """Check if the analysis type requires thermal material properties."""
    step_type = spec.get("analysis", {}).get("step_type", "")
    return step_type in (
        "Coupled_Temperature_Displacement",
        "Coupled_Thermal_Electrical",
    )
