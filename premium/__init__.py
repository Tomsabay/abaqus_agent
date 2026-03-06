"""
premium
-------
Premium features for Abaqus Agent (paid tier).

Features:
  - coupling    : Multi-Physics Coupling
  - adaptivity  : Automatic Mesh Adaptivity
  - parametric  : Batch Parametric Sweeps
  - geometry_ext: Extended Geometry Types
  - autorepair  : Advanced Failure Auto-Repair
"""

from premium.licensing import feature_gate

__all__ = ["feature_gate"]
