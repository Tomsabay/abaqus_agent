"""
test_schema.py
--------------
Unit tests for Problem Spec schema validation.
No Abaqus required.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.schema_validator import validate_spec

CASES_DIR = Path(__file__).parent.parent / "cases"


class TestSchemaValidation:
    def test_cantilever_spec_valid(self):
        valid, errors = validate_spec(CASES_DIR / "cantilever" / "spec.yaml")
        assert valid, f"Unexpected errors: {errors}"

    def test_plate_hole_spec_valid(self):
        valid, errors = validate_spec(CASES_DIR / "plate_hole" / "spec.yaml")
        assert valid, f"Unexpected errors: {errors}"

    def test_modal_spec_valid(self):
        valid, errors = validate_spec(CASES_DIR / "modal" / "spec.yaml")
        assert valid, f"Unexpected errors: {errors}"

    def test_explicit_spec_valid(self):
        valid, errors = validate_spec(CASES_DIR / "explicit_impact" / "spec.yaml")
        assert valid, f"Unexpected errors: {errors}"

    def test_missing_meta_invalid(self):
        spec = {
            "geometry": {"type": "cantilever_block"},
            "material": {"name": "S", "E": 210000, "nu": 0.3},
            "analysis": {"solver": "standard", "step_type": "Static"},
            "bc_load": {},
            "outputs": {"kpis": [{"name": "U", "type": "nodal_displacement"}]},
        }
        valid, errors = validate_spec(spec)
        assert not valid
        assert any("meta" in e for e in errors)

    def test_missing_kpis_invalid(self):
        spec = {
            "meta": {"abaqus_release": "2024", "model_name": "Test"},
            "geometry": {"type": "cantilever_block"},
            "material": {"name": "S", "E": 210000, "nu": 0.3},
            "analysis": {"solver": "standard", "step_type": "Static"},
            "bc_load": {},
            "outputs": {"kpis": []},   # empty
        }
        valid, errors = validate_spec(spec)
        assert not valid

    def test_invalid_abaqus_release(self):
        spec = {
            # 2015 predates everything this toolchain supports. (2019 used to be
            # the sentinel here, but the enum was widened to 2019-2026 after the
            # old 2023-2026 range excluded the 2021 actually installed on the
            # recording machine and forced specs to claim a release they had not.)
            "meta": {"abaqus_release": "2015", "model_name": "Test"},  # not in enum
            "geometry": {"type": "cantilever_block"},
            "material": {"name": "S", "E": 210000, "nu": 0.3},
            "analysis": {"solver": "standard", "step_type": "Static"},
            "bc_load": {},
            "outputs": {"kpis": [{"name": "U", "type": "nodal_displacement"}]},
        }
        valid, errors = validate_spec(spec)
        assert not valid

    def test_valid_spec_dict(self):
        spec = {
            "meta": {"abaqus_release": "2024", "model_name": "TestModel"},
            "geometry": {"type": "cantilever_block", "L": 100, "W": 10, "H": 10},
            "material": {"name": "Steel", "E": 210000, "nu": 0.3},
            "analysis": {"solver": "standard", "step_type": "Static", "cpus": 2},
            "bc_load": {"fixed_face": "x=0", "load_face": "x=L",
                        "load_type": "pressure", "value": -1.0},
            "outputs": {"kpis": [{"name": "U_tip", "type": "nodal_displacement"}]},
        }
        valid, errors = validate_spec(spec)
        assert valid, f"Unexpected errors: {errors}"

    def test_inline_physics_contracts_valid(self):
        spec = {
            "meta": {"abaqus_release": "2024", "model_name": "ContractModel"},
            "geometry": {"type": "cantilever_block", "L": 100, "W": 10, "H": 10},
            "material": {"name": "Steel", "E": 210000, "nu": 0.3},
            "analysis": {"solver": "standard", "step_type": "Static"},
            "bc_load": {
                "fixed_face": "x=0",
                "load_face": "x=L",
                "load_type": "pressure",
                "value": -1.0,
            },
            "outputs": {"kpis": [{"name": "U_tip", "type": "nodal_displacement"}]},
            "contracts": [
                {
                    "name": "tip_down",
                    "check": "operator",
                    "kpi": "U_tip",
                    "operator": "<",
                    "value": 0.0,
                    "severity": "error",
                }
            ],
        }
        valid, errors = validate_spec(spec)
        assert valid, f"Inline physics contracts should be valid: {errors}"

    def test_abaqus_2026_release_valid(self):
        """Abaqus 2026 should be accepted by the schema."""
        spec = {
            "meta": {"abaqus_release": "2026", "model_name": "Test2026"},
            "geometry": {"type": "cantilever_block", "L": 100, "W": 10, "H": 10},
            "material": {"name": "Steel", "E": 210000, "nu": 0.3},
            "analysis": {"solver": "standard", "step_type": "Static"},
            "bc_load": {"fixed_face": "x=0", "load_face": "x=L",
                        "load_type": "pressure", "value": -1.0},
            "outputs": {"kpis": [{"name": "U_tip", "type": "nodal_displacement"}]},
        }
        valid, errors = validate_spec(spec)
        assert valid, f"Abaqus 2026 should be valid: {errors}"
