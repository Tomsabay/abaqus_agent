"""
premium.geometry
----------------
Extended geometry types for Abaqus Agent (premium).

Registers: shell_plate, beam_frame, composite_plate, cohesive_layer
"""

from premium.feature_registry import register_geometry
from premium.geometry.shell_elements import generate_shell_plate
from premium.geometry.beam_elements import generate_beam_frame
from premium.geometry.composite_layup import generate_composite_plate
from premium.geometry.cohesive_elements import generate_cohesive_layer

register_geometry("shell_plate", "geometry_ext", generate_shell_plate)
register_geometry("beam_frame", "geometry_ext", generate_beam_frame)
register_geometry("composite_plate", "geometry_ext", generate_composite_plate)
register_geometry("cohesive_layer", "geometry_ext", generate_cohesive_layer)
