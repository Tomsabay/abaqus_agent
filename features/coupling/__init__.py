"""
features.coupling
-----------------
Multi-physics coupling support for Abaqus Agent.

Registers coupled step types and thermal/electrical KPI extractors.
"""

from features.coupling.coupled_outputs import (
    extract_heat_flux_max,
    extract_temperature_max,
    extract_thermal_gradient,
)
from features.coupling.coupled_steps import (
    generate_coupled_temp_disp_step,
    generate_coupled_thermal_electrical_step,
)
from features.feature_registry import register_kpi, register_step

register_step("Coupled_Temperature_Displacement", generate_coupled_temp_disp_step)
register_step("Coupled_Thermal_Electrical", generate_coupled_thermal_electrical_step)
register_kpi("temperature_max", extract_temperature_max)
register_kpi("heat_flux_max", extract_heat_flux_max)
register_kpi("thermal_gradient", extract_thermal_gradient)
