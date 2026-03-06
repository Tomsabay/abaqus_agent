"""
Tests for batch parametric sweeps (premium).
No Abaqus installation required.
"""

import pytest

from premium.parametric.doe import generate_samples
from premium.parametric.sweep_engine import generate_sweep_specs, _apply_sample, _set_nested, _get_nested
from premium.parametric.aggregator import compute_sensitivity, _pearson_correlation


class TestDOE:
    def test_full_factorial_2_params(self):
        params = [
            {"path": "geometry.L", "values": [100, 200]},
            {"path": "material.E", "values": [210000, 70000]},
        ]
        samples = generate_samples(params, strategy="full_factorial")
        assert len(samples) == 4  # 2 x 2
        # Check all combinations present
        combos = [(s["geometry.L"], s["material.E"]) for s in samples]
        assert (100, 210000) in combos
        assert (100, 70000) in combos
        assert (200, 210000) in combos
        assert (200, 70000) in combos

    def test_full_factorial_3_levels(self):
        params = [
            {"path": "geometry.L", "values": [100, 150, 200]},
            {"path": "geometry.W", "values": [10, 20]},
        ]
        samples = generate_samples(params, strategy="full_factorial")
        assert len(samples) == 6  # 3 x 2

    def test_latin_hypercube(self):
        params = [
            {"path": "geometry.L", "min": 50, "max": 200, "steps": 10},
            {"path": "material.E", "min": 50000, "max": 250000, "steps": 10},
        ]
        samples = generate_samples(params, strategy="latin_hypercube", n_samples=10)
        assert len(samples) == 10
        # Check all values in range
        for s in samples:
            assert 50 <= s["geometry.L"] <= 200
            assert 50000 <= s["material.E"] <= 250000

    def test_sobol_sequence(self):
        params = [
            {"path": "x", "min": 0, "max": 1, "steps": 5},
            {"path": "y", "min": 0, "max": 1, "steps": 5},
        ]
        samples = generate_samples(params, strategy="sobol", n_samples=8)
        assert len(samples) == 8
        for s in samples:
            assert 0 <= s["x"] <= 1
            assert 0 <= s["y"] <= 1

    def test_one_at_a_time(self):
        params = [
            {"path": "geometry.L", "values": [100, 150, 200]},
            {"path": "material.E", "values": [210000, 70000]},
        ]
        samples = generate_samples(params, strategy="one_at_a_time")
        # baseline + (3-1) + (2-1) = 4
        assert len(samples) == 4
        # First sample is baseline
        assert samples[0]["geometry.L"] == 100
        assert samples[0]["material.E"] == 210000

    def test_min_max_auto_values(self):
        params = [{"path": "x", "min": 0, "max": 10, "steps": 5}]
        samples = generate_samples(params, strategy="full_factorial")
        assert len(samples) == 5
        vals = [s["x"] for s in samples]
        assert min(vals) == 0
        assert max(vals) == 10


class TestSweepEngine:
    def test_generate_sweep_specs(self):
        base_spec = {
            "meta": {"model_name": "Test", "abaqus_release": "2024"},
            "geometry": {"type": "cantilever_block", "L": 100, "W": 10, "H": 10},
            "material": {"name": "Steel", "E": 210000, "nu": 0.3},
            "analysis": {"solver": "standard", "step_type": "Static"},
            "bc_load": {"value": -1},
            "outputs": {"kpis": [{"name": "U_tip", "type": "nodal_displacement"}]},
            "parametric": {
                "parameters": [
                    {"path": "geometry.L", "values": [100, 200]},
                    {"path": "material.E", "values": [210000, 70000]},
                ],
                "strategy": "full_factorial",
            },
        }
        variants = generate_sweep_specs(base_spec)
        assert len(variants) == 4

        # Check variants have unique model names
        names = [v["spec"]["meta"]["model_name"] for v in variants]
        assert len(set(names)) == 4

        # Check parametric section removed from variants
        for v in variants:
            assert "parametric" not in v["spec"]

    def test_apply_sample(self):
        base = {
            "meta": {"model_name": "Test"},
            "geometry": {"L": 100},
            "material": {"E": 210000},
        }
        sample = {"geometry.L": 200, "material.E": 70000}
        result = _apply_sample(base, sample, 0)
        assert result["geometry"]["L"] == 200
        assert result["material"]["E"] == 70000
        assert result["meta"]["model_name"] == "Test_v0000"

    def test_set_nested(self):
        d = {}
        _set_nested(d, "a.b.c", 42)
        assert d["a"]["b"]["c"] == 42

    def test_get_nested(self):
        d = {"a": {"b": {"c": 42}}}
        assert _get_nested(d, "a.b.c") == 42
        assert _get_nested(d, "a.b.d", "default") == "default"


class TestAggregator:
    def test_pearson_correlation_positive(self):
        x = [1.0, 2.0, 3.0, 4.0, 5.0]
        y = [2.0, 4.0, 6.0, 8.0, 10.0]
        assert abs(_pearson_correlation(x, y) - 1.0) < 1e-10

    def test_pearson_correlation_negative(self):
        x = [1.0, 2.0, 3.0, 4.0, 5.0]
        y = [10.0, 8.0, 6.0, 4.0, 2.0]
        assert abs(_pearson_correlation(x, y) - (-1.0)) < 1e-10

    def test_pearson_correlation_zero(self):
        x = [1.0, 2.0, 3.0, 4.0, 5.0]
        y = [5.0, 5.0, 5.0, 5.0, 5.0]
        assert _pearson_correlation(x, y) == 0.0

    def test_compute_sensitivity(self):
        sweep_results = {
            "parameters": [{"path": "geometry.L"}],
            "results": [
                {"status": "COMPLETED", "sample": {"geometry.L": 100}, "kpis": {"U_tip": {"value": -1.0}}},
                {"status": "COMPLETED", "sample": {"geometry.L": 200}, "kpis": {"U_tip": {"value": -8.0}}},
                {"status": "COMPLETED", "sample": {"geometry.L": 300}, "kpis": {"U_tip": {"value": -27.0}}},
            ],
        }
        sensitivity = compute_sensitivity(sweep_results)
        assert "U_tip" in sensitivity
        assert len(sensitivity["U_tip"]) == 1
        assert sensitivity["U_tip"][0]["parameter"] == "geometry.L"
