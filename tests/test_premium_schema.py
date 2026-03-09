"""
Tests to verify the extended schema is backward-compatible.
All existing benchmark cases must still validate successfully.
No Abaqus installation required.
"""

from pathlib import Path

import pytest

from tools.schema_validator import validate_spec

CASES_DIR = Path(__file__).parent.parent / "cases"


class TestSchemaBackwardCompatibility:
    """Ensure existing free-tier specs still validate after schema extension."""

    @pytest.fixture(params=["cantilever", "plate_hole", "modal", "explicit_impact"])
    def case_spec_path(self, request):
        path = CASES_DIR / request.param / "spec.yaml"
        if path.exists():
            return path
        pytest.skip(f"Case {request.param} not found")

    def test_existing_case_still_valid(self, case_spec_path):
        valid, errors = validate_spec(case_spec_path)
        assert valid, f"Validation failed for {case_spec_path.name}: {errors}"


class TestPremiumSchemaFields:
    """Test that premium-specific fields are accepted by schema."""

    def test_coupled_step_type_accepted(self):
        spec = _make_base_spec()
        spec["analysis"]["step_type"] = "Coupled_Temperature_Displacement"
        valid, errors = validate_spec(spec)
        assert valid, f"Coupled step type rejected: {errors}"

    def test_shell_plate_geometry_accepted(self):
        spec = _make_base_spec()
        spec["geometry"]["type"] = "shell_plate"
        spec["geometry"]["thickness"] = 2.0
        valid, errors = validate_spec(spec)
        assert valid, f"Shell plate rejected: {errors}"

    def test_adaptive_mesh_accepted(self):
        spec = _make_base_spec()
        spec["analysis"]["adaptive_mesh"] = {
            "enabled": True, "method": "ale", "frequency": 10
        }
        valid, errors = validate_spec(spec)
        assert valid, f"Adaptive mesh rejected: {errors}"

    def test_parametric_accepted(self):
        spec = _make_base_spec()
        spec["parametric"] = {
            "parameters": [
                {"path": "geometry.L", "values": [100, 200]}
            ],
            "strategy": "full_factorial",
        }
        valid, errors = validate_spec(spec)
        assert valid, f"Parametric rejected: {errors}"

    def test_thermal_material_accepted(self):
        spec = _make_base_spec()
        spec["material"]["conductivity"] = 50.0
        spec["material"]["specific_heat"] = 460.0
        spec["material"]["expansion_coeff"] = 1.2e-5
        valid, errors = validate_spec(spec)
        assert valid, f"Thermal material rejected: {errors}"

    def test_max_retries_accepted(self):
        spec = _make_base_spec()
        spec["analysis"]["max_retries"] = 3
        valid, errors = validate_spec(spec)
        assert valid, f"max_retries rejected: {errors}"


def _make_base_spec() -> dict:
    """Create a minimal valid spec for testing."""
    return {
        "meta": {"abaqus_release": "2024", "model_name": "TestModel"},
        "geometry": {"type": "cantilever_block", "L": 100, "W": 10, "H": 10},
        "material": {"name": "Steel", "E": 210000, "nu": 0.3},
        "analysis": {"solver": "standard", "step_type": "Static"},
        "bc_load": {"value": -1},
        "outputs": {"kpis": [{"name": "U_tip", "type": "nodal_displacement"}]},
    }
