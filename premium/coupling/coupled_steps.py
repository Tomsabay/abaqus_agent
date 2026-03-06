"""
coupled_steps.py
----------------
Step code generators for multi-physics coupled analyses.

Supports:
  - Coupled Temperature-Displacement (thermo-mechanical)
  - Coupled Thermal-Electrical
"""

from __future__ import annotations


def generate_coupled_temp_disp_step(
    ana: dict, bc: dict, model_name: str, out: dict
) -> str:
    """
    Generate CAE code for a Coupled Temperature-Displacement step.

    This is used for thermo-mechanical problems:
    welding, thermal stress, heat treatment, etc.
    """
    time_period = ana.get("time_period", 1.0)
    steady = ana.get("steady_state", False)
    init_temp = ana.get("initial_temperature", 20.0)
    nlgeom = "ON" if ana.get("nlgeom", False) else "OFF"
    load_val = bc.get("value", -1.0)
    thermal_bc = bc.get("thermal_bc", {})

    # Step creation
    if steady:
        step_code = f"""
mdb.models['{model_name}'].CoupledTempDisplacementStep(
    name='Step-1', previous='Initial',
    response=STEADY_STATE,
    timePeriod={time_period},
    initialInc={time_period/10},
    minInc={time_period/1e6},
    maxInc={time_period},
    deltmx=50.0,
    nlgeom={nlgeom},
    description='Steady-state coupled temperature-displacement')
"""
    else:
        step_code = f"""
mdb.models['{model_name}'].CoupledTempDisplacementStep(
    name='Step-1', previous='Initial',
    response=TRANSIENT,
    timePeriod={time_period},
    initialInc={time_period/100},
    minInc={time_period/1e6},
    maxInc={time_period/10},
    deltmx=10.0,
    nlgeom={nlgeom},
    description='Transient coupled temperature-displacement')
"""

    # Initial temperature
    init_temp_code = f"""
# Initial temperature field
mdb.models['{model_name}'].Temperature(
    name='InitTemp', createStepName='Initial',
    region=mdb.models['{model_name}'].rootAssembly.instances['Part-1-1'].sets['ALL'],
    distributionType=UNIFORM,
    crossSectionDistribution=CONSTANT_THROUGH_THICKNESS,
    magnitudes=({init_temp},))
"""

    # Mechanical BC
    mech_bc_code = f"""
# Mechanical boundary conditions
a = mdb.models['{model_name}'].rootAssembly
mdb.models['{model_name}'].EncastreBC(
    name='Fixed', createStepName='Initial',
    region=a.instances['Part-1-1'].sets['FIXED_END'])
"""

    # Mechanical load
    mech_load_code = f"""
# Mechanical load
mdb.models['{model_name}'].Pressure(
    name='Load-1', createStepName='Step-1',
    region=a.instances['Part-1-1'].sets['LOAD_END'],
    magnitude={abs(load_val)},
    distributionType=UNIFORM)
"""

    # Thermal BC
    thermal_bc_code = _generate_thermal_bc(thermal_bc, model_name)

    # Field output
    output_code = f"""
# Field outputs for coupled analysis
mdb.models['{model_name}'].fieldOutputRequests['F-Output-1'].setValues(
    variables=('S', 'E', 'U', 'RF', 'NT', 'HFL', 'TEMP', 'THE'))
"""

    return (
        step_code + init_temp_code + mech_bc_code +
        mech_load_code + thermal_bc_code + output_code
    )


def generate_coupled_thermal_electrical_step(
    ana: dict, bc: dict, model_name: str, out: dict
) -> str:
    """
    Generate CAE code for a Coupled Thermal-Electrical step.

    Used for Joule heating, resistive welding, thermoelectric problems.
    """
    time_period = ana.get("time_period", 1.0)
    steady = ana.get("steady_state", True)
    init_temp = ana.get("initial_temperature", 20.0)

    if steady:
        step_code = f"""
mdb.models['{model_name}'].CoupledThermalElectricalStep(
    name='Step-1', previous='Initial',
    response=STEADY_STATE,
    timePeriod={time_period},
    initialInc={time_period/10},
    minInc={time_period/1e6},
    maxInc={time_period},
    deltmx=50.0,
    description='Steady-state coupled thermal-electrical')
"""
    else:
        step_code = f"""
mdb.models['{model_name}'].CoupledThermalElectricalStep(
    name='Step-1', previous='Initial',
    response=TRANSIENT,
    timePeriod={time_period},
    initialInc={time_period/100},
    minInc={time_period/1e6},
    maxInc={time_period/10},
    deltmx=10.0,
    description='Transient coupled thermal-electrical')
"""

    bc_code = f"""
# Initial temperature
mdb.models['{model_name}'].Temperature(
    name='InitTemp', createStepName='Initial',
    region=mdb.models['{model_name}'].rootAssembly.instances['Part-1-1'].sets['ALL'],
    distributionType=UNIFORM,
    crossSectionDistribution=CONSTANT_THROUGH_THICKNESS,
    magnitudes=({init_temp},))

a = mdb.models['{model_name}'].rootAssembly

# Electrical ground (zero potential on fixed face)
mdb.models['{model_name}'].ElectricalPotentialBC(
    name='Ground', createStepName='Initial',
    region=a.instances['Part-1-1'].sets['FIXED_END'],
    magnitude=0.0)

# Applied voltage on load face
mdb.models['{model_name}'].ElectricalPotentialBC(
    name='Voltage', createStepName='Step-1',
    region=a.instances['Part-1-1'].sets['LOAD_END'],
    magnitude={abs(bc.get('value', 1.0))})
"""

    # Thermal BC if specified
    thermal_bc = bc.get("thermal_bc", {})
    thermal_code = _generate_thermal_bc(thermal_bc, model_name)

    output_code = f"""
# Field outputs for coupled thermal-electrical
mdb.models['{model_name}'].fieldOutputRequests['F-Output-1'].setValues(
    variables=('NT', 'HFL', 'TEMP', 'EPOT', 'ECD', 'JOH'))
"""

    return step_code + bc_code + thermal_code + output_code


def _generate_thermal_bc(thermal_bc: dict, model_name: str) -> str:
    """Generate thermal boundary condition code."""
    if not thermal_bc:
        return "# No additional thermal BC\n"

    bc_type = thermal_bc.get("type", "temperature")
    face = thermal_bc.get("face", "LOAD_END")
    value = thermal_bc.get("value", 100.0)

    if bc_type == "temperature":
        return f"""
# Prescribed temperature
mdb.models['{model_name}'].TemperatureBC(
    name='ThermalBC', createStepName='Step-1',
    region=mdb.models['{model_name}'].rootAssembly.instances['Part-1-1'].sets['{face}'],
    magnitude={value},
    distributionType=UNIFORM)
"""
    elif bc_type == "heat_flux":
        return f"""
# Surface heat flux
mdb.models['{model_name}'].SurfaceHeatFlux(
    name='HeatFlux', createStepName='Step-1',
    region=mdb.models['{model_name}'].rootAssembly.instances['Part-1-1'].sets['{face}'],
    magnitude={value})
"""
    elif bc_type == "convection":
        film = thermal_bc.get("film_coeff", 25.0)
        sink = thermal_bc.get("sink_temperature", 20.0)
        return f"""
# Film condition (convection)
mdb.models['{model_name}'].FilmCondition(
    name='Convection', createStepName='Step-1',
    surface=mdb.models['{model_name}'].rootAssembly.instances['Part-1-1'].sets['{face}'],
    definition=EMBEDDED_COEFF,
    filmCoeff={film},
    sinkTemperature={sink},
    sinkAmplitude='',
    sinkDistributionType=UNIFORM,
    filmCoeffAmplitude='')
"""
    elif bc_type == "radiation":
        sink = thermal_bc.get("sink_temperature", 20.0)
        return f"""
# Radiation to ambient
mdb.models['{model_name}'].RadiationToAmbient(
    name='Radiation', createStepName='Step-1',
    surface=mdb.models['{model_name}'].rootAssembly.instances['Part-1-1'].sets['{face}'],
    radiationType=AMBIENT,
    distributionType=UNIFORM,
    emissivity=0.9,
    ambientTemperature={sink})
"""
    return ""
