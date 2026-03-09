"""
Tests for automatic mesh adaptivity (premium).
No Abaqus installation required.
"""


from premium.adaptivity.ale_mesh import generate_ale_code, generate_ale_explicit_code
from premium.adaptivity.error_indicators import recommend_adaptivity_strategy
from premium.adaptivity.remesh import generate_remesh_code


class TestALEMesh:
    def test_basic_ale(self):
        adaptive = {"enabled": True, "method": "ale", "frequency": 10, "smoothing": "volume"}
        spec = {"meta": {"model_name": "TestModel"}}
        code = generate_ale_code(adaptive, spec)
        assert "AdaptiveMeshDomain" in code
        assert "AdaptiveMeshControl" in code
        assert "frequency=10" in code

    def test_laplacian_smoothing(self):
        adaptive = {"enabled": True, "method": "ale", "frequency": 5, "smoothing": "laplacian"}
        spec = {"meta": {"model_name": "TestModel"}}
        code = generate_ale_code(adaptive, spec)
        assert "MESHSMOOTHING" in code

    def test_explicit_ale(self):
        adaptive = {"enabled": True, "frequency": 5}
        spec = {"meta": {"model_name": "TestModel"}}
        code = generate_ale_explicit_code(adaptive, spec)
        assert "meshSweeps=3" in code
        assert "ExplicitALE" in code


class TestRemesh:
    def test_basic_remesh(self):
        adaptive = {"enabled": True, "method": "remesh", "error_target": 0.05, "max_iterations": 3}
        spec = {"meta": {"model_name": "TestModel"}}
        code = generate_remesh_code(adaptive, spec)
        assert "RemeshingRule" in code
        assert "MISESERI" in code
        assert "errorTarget=0.05" in code


class TestAdaptivityRecommendation:
    def test_explicit_recommends_ale(self):
        spec = {"geometry": {"type": "cantilever_block"}, "analysis": {"step_type": "Dynamic_Explicit"}, "meta": {}}
        rec = recommend_adaptivity_strategy(spec)
        assert rec["analysis"]["adaptive_mesh"]["method"] == "ale"
        assert rec["analysis"]["adaptive_mesh"]["frequency"] == 5

    def test_plate_hole_recommends_remesh(self):
        spec = {"geometry": {"type": "plate_with_hole"}, "analysis": {"step_type": "Static"}, "meta": {}}
        rec = recommend_adaptivity_strategy(spec)
        assert rec["analysis"]["adaptive_mesh"]["method"] == "remesh"

    def test_nlgeom_recommends_laplacian(self):
        spec = {"geometry": {"type": "cantilever_block"}, "analysis": {"step_type": "Static", "nlgeom": True}, "meta": {}}
        rec = recommend_adaptivity_strategy(spec)
        assert rec["analysis"]["adaptive_mesh"]["smoothing"] == "laplacian"
