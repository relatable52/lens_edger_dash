from dataclasses import dataclass
from typing import List, Literal

from core.models.lenses import MeshData

# Enum for the types of cuts
CutType = Literal["CONCENTRIC", "INTERPOLATION"]

@dataclass
class RoughingPassParam:
    """
    Represents one row in your user's table (C1, C2, etc.)
    """
    method: CutType
    step_value_mm: float  # Distance to move in from the PREVIOUS cut
    speed_s_per_rev: float # Processing speed
    
@dataclass
class RoughingPassData:
    """
    Holds the geometry and physics data for a SINGLE roughing step.
    """
    pass_index: int
    mesh: MeshData          # The 3D visualization
    radii: List[float]      # The 1D profile (useful for 2D plots)
    volume: float           # Calculated volume in mm3
    duration: float         # Estimated time
    
    def to_dict(self):
        return {
            "pass_index": self.pass_index,
            "mesh": self.mesh.to_dict(),
            "radii": self.radii,
            "volume": self.volume,
            "duration": self.duration
        }
    
    @staticmethod
    def from_dict(data: dict):
        if not data: return None
        return RoughingPassData(
            pass_index=data['pass_index'],
            mesh=MeshData.from_dict(data['mesh']),
            radii=data['radii'],
            volume=data['volume'],
            duration=data['duration']
        )