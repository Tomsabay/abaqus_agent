"""
premium.coupling
----------------
Multi-physics coupling support for Abaqus Agent (premium).

Registers coupled step types and thermal/electrical KPI extractors.
"""

from premium.feature_registry import register_step, register_kpi
from premium.coupling.coupled_steps import (
    generate_coupled_temp_disp_step,
    generate_coupled_thermal_electrical_step,
)
from premium.coupling.coupled_outputs import (
    extract_temperature_max,
    extract_heat_flux_max,
    extract_thermal_gradient,
)

register_step("Coupled_Temperature_Displacement", "coupling", generate_coupled_temp_disp_step)
register_step("Coupled_Thermal_Electrical", "coupling", generate_coupled_thermal_electrical_step)
register_kpi("temperature_max", "coupling", extract_temperature_max)
register_kpi("heat_flux_max", "coupling", extract_heat_flux_max)
register_kpi("thermal_gradient", "coupling", extract_thermal_gradient)
