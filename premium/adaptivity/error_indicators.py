"""
error_indicators.py
-------------------
LLM-assisted mesh adaptivity strategy recommendation.

Uses analysis context (geometry type, loads, expected behavior)
to recommend optimal adaptive meshing parameters.
"""

from __future__ import annotations


def recommend_adaptivity_strategy(spec: dict) -> dict:
    """
    Recommend adaptive mesh strategy based on analysis context.

    Returns a dict with recommended adaptive_mesh parameters
    that can be merged into the spec.

    Logic:
        - Explicit + large deformation → ALE with frequent sweeps
        - Stress concentration (plate_with_hole) → h-refinement remesh
        - Static with nlgeom → ALE with moderate frequency
        - Default → ALE with standard settings
    """
    geo_type = spec.get("geometry", {}).get("type", "")
    step_type = spec.get("analysis", {}).get("step_type", "")
    nlgeom = spec.get("analysis", {}).get("nlgeom", False)

    recommendation = {
        "enabled": True,
        "method": "ale",
        "frequency": 10,
        "smoothing": "volume",
        "error_target": 0.05,
        "max_iterations": 3,
    }

    if step_type == "Dynamic_Explicit":
        # Explicit dynamics: frequent ALE sweeps for large deformation
        recommendation.update({
            "method": "ale",
            "frequency": 5,
            "smoothing": "volume",
        })
    elif geo_type == "plate_with_hole" or "concentration" in spec.get("meta", {}).get("description", "").lower():
        # Stress concentration: h-refinement for accuracy
        recommendation.update({
            "method": "remesh",
            "error_target": 0.03,
            "max_iterations": 4,
        })
    elif nlgeom:
        # Large deformation static: ALE helps prevent distortion
        recommendation.update({
            "method": "ale",
            "frequency": 10,
            "smoothing": "laplacian",
        })
    elif step_type in ("Coupled_Temperature_Displacement", "Coupled_Thermal_Electrical"):
        # Coupled analysis: moderate ALE for thermal gradient regions
        recommendation.update({
            "method": "ale",
            "frequency": 15,
            "smoothing": "equipotential",
        })

    return {"analysis": {"adaptive_mesh": recommendation}}


def generate_llm_prompt_for_adaptivity(spec: dict, results: dict | None = None) -> str:
    """
    Generate an LLM prompt to get adaptive mesh recommendations.

    Can use previous analysis results to inform the recommendation.
    """
    context = f"""Analysis type: {spec.get('analysis', {}).get('step_type', 'unknown')}
Geometry: {spec.get('geometry', {}).get('type', 'unknown')}
Description: {spec.get('meta', {}).get('description', 'N/A')}
"""

    if results:
        context += f"""
Previous results:
- Max stress: {results.get('max_mises', 'N/A')}
- Max displacement: {results.get('max_disp', 'N/A')}
- Element distortion warnings: {results.get('distortion_warnings', 0)}
"""

    return f"""You are an Abaqus mesh adaptivity expert.
Given the following FEA problem, recommend optimal adaptive mesh parameters.

## Problem Context
{context}

## Task
Recommend adaptive mesh parameters as YAML:
- method: ale | remesh
- frequency: integer (sweep frequency for ALE)
- smoothing: volume | laplacian | equipotential
- error_target: float (0-1, for remeshing)
- max_iterations: integer

## Output (YAML only)
method: <value>
frequency: <value>
smoothing: <value>
error_target: <value>
max_iterations: <value>
reason: "<one sentence explaining why>"
"""
