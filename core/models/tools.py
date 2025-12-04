from dataclasses import dataclass
from typing import List

@dataclass
class GrindingWheel:
    """
    Represents a single tool on the spindle.
    """
    tool_id: str
    name: str
    mesh_filename: str       # Path to .vtk file (or "generated" for dummy)
    
    # Physical placement on the spindle stack
    stack_z_offset: float    # Distance from spindle base to wheel base (mm)
    
    # Visual Dimensions (Truncated Cone)
    height: float
    radius_bottom: float
    radius_top: float
    
    # Cutting Definition (The "Active" part)
    cutting_radius: float    # The mathematical radius used for path generation
    cutting_z_relative: float # Height of the cutting edge relative to the wheel base
    
    def to_dict(self):
        return self.__dict__

@dataclass
class ToolStack:
    """
    Represents the entire spindle assembly.
    """
    tilt_angle_deg: float          # Global tilt of the spindle
    base_position: List[float]     # [x, y, z] of the spindle pivot/base
    wheels: List[GrindingWheel]
    
    def to_dict(self):
        return {
            "tilt_angle_deg": self.tilt_angle_deg,
            "base_position": self.base_position,
            "wheels": [w.to_dict() for w in self.wheels]
        }