"""
Tests for multi-physics coupling (premium).
Verifies generated step code and material code.
No Abaqus installation required.
"""


from premium.coupling.coupled_materials import (
    generate_thermal_material_code,
    needs_thermal_properties,
)
from premium.coupling.coupled_steps import (
    generate_coupled_temp_disp_step,
    generate_coupled_thermal_electrical_step,
)


class TestCoupledTempDisp:
    def test_steady_state(self):
        ana = {"step_type": "Coupled_Temperature_Displacement", "time_period": 1.0, "steady_state": True}
        bc = {"value": -1.0}
        code = generate_coupled_temp_disp_step(ana, bc, "TestModel", {})
        assert "CoupledTempDisplacementStep" in code
        assert "STEADY_STATE" in code
        assert "EncastreBC" in code
        assert "NT" in code or "HFL" in code

    def test_transient(self):
        ana = {"step_type": "Coupled_Temperature_Displacement", "time_period": 10.0, "steady_state": False}
        bc = {"value": -5.0}
        code = generate_coupled_temp_disp_step(ana, bc, "TestModel", {})
        assert "TRANSIENT" in code

    def test_thermal_bc_temperature(self):
        ana = {"step_type": "Coupled_Temperature_Displacement", "time_period": 1.0}
        bc = {"value": -1.0, "thermal_bc": {"type": "temperature", "face": "LOAD_END", "value": 200}}
        code = generate_coupled_temp_disp_step(ana, bc, "TestModel", {})
        assert "TemperatureBC" in code
        assert "200" in code

    def test_thermal_bc_convection(self):
        ana = {"step_type": "Coupled_Temperature_Displacement", "time_period": 1.0}
        bc = {"value": -1.0, "thermal_bc": {"type": "convection", "face": "LOAD_END", "film_coeff": 50, "sink_temperature": 25}}
        code = generate_coupled_temp_disp_step(ana, bc, "TestModel", {})
        assert "FilmCondition" in code

    def test_nlgeom(self):
        ana = {"step_type": "Coupled_Temperature_Displacement", "time_period": 1.0, "nlgeom": True}
        bc = {"value": -1.0}
        code = generate_coupled_temp_disp_step(ana, bc, "TestModel", {})
        assert "nlgeom=ON" in code


class TestCoupledThermalElectrical:
    def test_steady_state(self):
        ana = {"step_type": "Coupled_Thermal_Electrical", "time_period": 1.0, "steady_state": True}
        bc = {"value": 5.0}
        code = generate_coupled_thermal_electrical_step(ana, bc, "TestModel", {})
        assert "CoupledThermalElectricalStep" in code
        assert "ElectricalPotentialBC" in code
        assert "EPOT" in code or "ECD" in code

    def test_transient(self):
        ana = {"step_type": "Coupled_Thermal_Electrical", "time_period": 10.0, "steady_state": False}
        bc = {"value": 10.0}
        code = generate_coupled_thermal_electrical_step(ana, bc, "TestModel", {})
        assert "TRANSIENT" in code


class TestCoupledMaterials:
    def test_thermal_material(self):
        mat = {"name": "Steel", "E": 210000, "nu": 0.3, "conductivity": 50.0, "specific_heat": 460.0, "expansion_coeff": 1.2e-5}
        code = generate_thermal_material_code(mat, "TestModel")
        assert "Conductivity" in code
        assert "SpecificHeat" in code
        assert "Expansion" in code

    def test_electrical_material(self):
        mat = {"name": "Copper", "E": 120000, "nu": 0.34, "electrical_conductivity": 5.96e7}
        code = generate_thermal_material_code(mat, "TestModel")
        assert "ElectricalConductivity" in code

    def test_no_thermal_properties(self):
        mat = {"name": "Steel", "E": 210000, "nu": 0.3}
        code = generate_thermal_material_code(mat, "TestModel")
        assert "No additional" in code or code.strip() == ""

    def test_needs_thermal_properties(self):
        spec_coupled = {"analysis": {"step_type": "Coupled_Temperature_Displacement"}}
        spec_static = {"analysis": {"step_type": "Static"}}
        assert needs_thermal_properties(spec_coupled)
        assert not needs_thermal_properties(spec_static)
