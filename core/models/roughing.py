from dataclasses import dataclass, field
from typing import List, Literal

from core.models.lenses import MeshData

# Enum for the types of cuts
CutType = Literal["CONCENTRIC", "INTERPOLATION"]

@dataclass
class RoughingPassParam:
    """
    Represents one roughing pass (one row in the UI table).
    Does NOT include the method - that's stored globally in RoughingSettings.
    """
    step_value_mm: float    # Distance to move in from the PREVIOUS cut
    speed_s_per_rev: float  # Processing speed

@dataclass
class RoughingSettings:
    """
    Consolidates all roughing configuration.
    All passes use the SAME cutting method.
    """
    method: CutType                           # CONCENTRIC or INTERPOLATION (all passes use this)
    passes: List[RoughingPassParam] = field(default_factory=list)
    
    def to_dict(self):
        return {
            "method": self.method,
            "passes": [
                {
                    "step_value_mm": p.step_value_mm,
                    "speed_s_per_rev": p.speed_s_per_rev
                }
                for p in self.passes
            ]
        }
    
    @staticmethod
    def from_dict(data: dict):
        if not data:
            return RoughingSettings(method="CONCENTRIC", passes=[])
        
        passes = [
            RoughingPassParam(
                step_value_mm=float(p.get('step_value_mm', 3.0)),
                speed_s_per_rev=float(p.get('speed_s_per_rev', 15))
            )
            for p in data.get('passes', [])
        ]
        
        return RoughingSettings(
            method=data.get('method', 'CONCENTRIC'),
            passes=passes
        )
    
@dataclass
class RoughingPassData:
    """
    Holds the geometry and physics data for a SINGLE roughing step result.
    This is the OUTPUT of the roughing generation process.
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