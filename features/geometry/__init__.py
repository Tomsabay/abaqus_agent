"""
features.geometry
-----------------
Extended geometry types for Abaqus Agent.

Registers: shell_plate, beam_frame, composite_plate, cohesive_layer
"""

from features.feature_registry import register_geometry
from features.geometry.beam_elements import generate_beam_frame
from features.geometry.cohesive_elements import generate_cohesive_layer
from features.geometry.composite_layup import generate_composite_plate
from features.geometry.shell_elements import generate_shell_plate

register_geometry("shell_plate", generate_shell_plate)
register_geometry("beam_frame", generate_beam_frame)
register_geometry("composite_plate", generate_composite_plate)
register_geometry("cohesive_layer", generate_cohesive_layer)
