"""
Tests for premium geometry types.
Verifies that generated CAE scripts contain correct Abaqus keywords.
No Abaqus installation required.
"""

import pytest

from premium.geometry.shell_elements import generate_shell_plate
from premium.geometry.beam_elements import generate_beam_frame
from premium.geometry.composite_layup import generate_composite_plate
from premium.geometry.cohesive_elements import generate_cohesive_layer


class TestShellPlate:
    def test_basic_shell(self):
        geo = {"type": "shell_plate", "L": 200, "W": 100, "thickness": 2.0, "seed_size": 10}
        code = generate_shell_plate(geo, "TestModel")
        assert "BaseShell" in code
        assert "S4R" in code
        assert "ShellSection" in code or "HomogeneousShellSection" in code
        assert "200" in code
        assert "100" in code

    def test_shell_with_hole(self):
        geo = {"type": "shell_plate", "L": 200, "W": 100, "thickness": 2.0, "R": 10, "seed_size": 5}
        code = generate_shell_plate(geo, "TestModel")
        assert "CircleByCenterPerimeter" in code

    def test_shell_default_thickness(self):
        geo = {"type": "shell_plate", "L": 100, "W": 50}
        code = generate_shell_plate(geo, "TestModel")
        assert "thickness" in code.lower()


class TestBeamFrame:
    def test_simple_beam(self):
        geo = {"type": "beam_frame", "L": 100, "seed_size": 10}
        code = generate_beam_frame(geo, "TestModel")
        assert "WirePolyLine" in code
        assert "B31" in code
        assert "BeamSection" in code

    def test_rectangular_profile(self):
        geo = {"type": "beam_frame", "L": 100, "profile": {"type": "rectangular", "width": 20, "height": 30}}
        code = generate_beam_frame(geo, "TestModel")
        assert "RectangularProfile" in code

    def test_circular_profile(self):
        geo = {"type": "beam_frame", "L": 100, "profile": {"type": "circular", "radius": 10}}
        code = generate_beam_frame(geo, "TestModel")
        assert "CircularProfile" in code

    def test_i_beam_profile(self):
        geo = {"type": "beam_frame", "L": 100, "profile": {"type": "I_beam", "height": 30, "flange_width": 20, "flange_thickness": 2, "web_thickness": 1.5}}
        code = generate_beam_frame(geo, "TestModel")
        assert "IProfile" in code

    def test_pipe_profile(self):
        geo = {"type": "beam_frame", "L": 100, "profile": {"type": "pipe", "radius": 10, "wall_thickness": 1}}
        code = generate_beam_frame(geo, "TestModel")
        assert "PipeProfile" in code

    def test_frame_with_points(self):
        geo = {
            "type": "beam_frame", "L": 100,
            "points": [[0, 0, 0], [100, 0, 0], [50, 50, 0]],
            "connections": [[0, 1], [1, 2], [2, 0]],
        }
        code = generate_beam_frame(geo, "TestModel")
        assert "pts" in code
        assert "conns" in code


class TestCompositePlate:
    def test_basic_composite(self):
        geo = {
            "type": "composite_plate", "L": 200, "W": 100,
            "layup": [
                {"material": "CFRP", "thickness": 0.125, "orientation": 0},
                {"material": "CFRP", "thickness": 0.125, "orientation": 90},
            ],
        }
        code = generate_composite_plate(geo, "TestModel")
        assert "CompositeLayup" in code
        assert "CompositePly" in code
        assert "CFRP" in code
        assert "S4R" in code

    def test_default_layup(self):
        geo = {"type": "composite_plate", "L": 100, "W": 50}
        code = generate_composite_plate(geo, "TestModel")
        assert "Ply-1" in code
        assert "Ply-2" in code

    def test_ply_orientations(self):
        geo = {
            "type": "composite_plate", "L": 100, "W": 100,
            "layup": [
                {"material": "Carbon", "thickness": 0.2, "orientation": 45},
                {"material": "Carbon", "thickness": 0.2, "orientation": -45},
            ],
        }
        code = generate_composite_plate(geo, "TestModel")
        assert "orientationValue=45" in code
        assert "orientationValue=-45" in code


class TestCohesiveLayer:
    def test_basic_cohesive(self):
        geo = {"type": "cohesive_layer", "L": 100, "W": 50, "H": 10, "cohesive_thickness": 0.01}
        code = generate_cohesive_layer(geo, "TestModel")
        assert "COH3D8" in code
        assert "CohesiveSection" in code
        assert "TRACTION_SEPARATION" in code
        assert "Bottom" in code
        assert "Top" in code
        assert "Tie" in code

    def test_default_cohesive_thickness(self):
        geo = {"type": "cohesive_layer", "L": 100, "W": 50}
        code = generate_cohesive_layer(geo, "TestModel")
        assert "0.01" in code  # default cohesive thickness
