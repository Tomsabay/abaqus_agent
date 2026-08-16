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

    @pytest.fixture(params=["cantilever", "plate_hole", "modal", "explicit_impact",
                            "blast_plate", "steel_frame_blast"])
    def case_spec_path(self, request):
        path = CASES_DIR / request.param / "spec.yaml"
        if path.exists():
            return path
        pytest.skip(f"Case {request.param} not found")

    def test_existing_case_still_valid(self, case_spec_path):
        valid, errors = validate_spec(case_spec_path)
        assert valid, f"Validation failed for {case_spec_path.name}: {errors}"


class TestFeatureSchemaFields:
    """Test that feature-module-specific fields are accepted by schema."""

    def test_a_coupled_step_is_written_as_the_abaqus_method(self):
        """`analysis.step_type: Coupled_Temperature_Displacement` is gone with
        the dialect that carried it. A coupled step is now the method itself,
        which is also the only form that can take that method's own keywords."""
        spec = _make_base_spec()
        spec["steps"] = [{"call": "CoupledTempDisplacementStep",
                          "name": {"literal": "Heat"},
                          "previous": {"literal": "Initial"},
                          "deltmx": 10.0}]
        valid, errors = validate_spec(spec)
        assert valid, f"Coupled step rejected: {errors}"

    def test_a_shell_plate_is_a_section_not_a_shape_name(self):
        """What `geometry.type: shell_plate` used to name. It is a section now,
        so a shell is any surface the feature grammar can draw rather than the
        one rectangular plate the enumerated shape could."""
        spec = _make_base_spec()
        spec["parts"][0]["features"] = [
            {"op": "sketch", "id": "s", "plane": "XY",
             "profile": {"rect": {"corner1": [0.0, 0.0], "corner2": [100.0, 100.0]}}},
            {"call": "BaseShell", "sketch": {"sketch": "s"}},
        ]
        spec["parts"][0]["section"] = {"type": "shell", "material": "Steel",
                                       "thickness": 2.0}
        spec["parts"][0]["mesh"] = {"seed": 10.0, "element": "S4R"}
        spec["parts"][0]["expect"] = {"area": 10000.0, "faces": 1}
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
                {"path": "parts[0].features[1].depth", "values": [100, 200]}
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
        "material": {"name": "Steel", "E": 210000, "nu": 0.3},
        "analysis": {"solver": "standard"},
        "parts": [{
            "name": "Bar",
            "features": [
                {"op": "sketch", "id": "s", "plane": "XY",
                 "profile": {"rect": {"corner1": [0.0, 0.0],
                                      "corner2": [10.0, 10.0]}}},
                {"op": "extrude", "sketch": "s", "depth": 100.0},
            ],
            "section": {"type": "solid", "material": "Steel"},
            "mesh": {"seed": 5.0, "element": "C3D8I"},
        }],
        "assembly": {"instances": [{"name": "Bar-1", "part": "Bar",
                                    "translate": [0.0, 0.0, 0.0]}]},
        "steps": [{"call": "StaticStep", "name": {"literal": "Step-1"},
                   "previous": {"literal": "Initial"}}],
        "outputs": {"kpis": [{"name": "U_tip", "type": "field_min",
                              "component": "U2", "location": "whole_model"}]},
    }
