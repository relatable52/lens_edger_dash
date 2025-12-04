from dataclasses import dataclass
from typing import Optional, List

import numpy as np

@dataclass
class FrameSide:
    """
    Represents the shape and parameters for a single eye (Left or Right).
    """
    side_name: str         # 'L' or 'R'
    radii: np.ndarray      # Array of radius values (mm)
    z_map: np.ndarray      # Array of z-height values (mm)
    ipd: float = 0.0       # Monocular PD
    ocht: float = 0.0      # Optical Center Height
    hbox: float = 0.0      # Horizontal Box size
    vbox: float = 0.0      # Vertical Box size
    
    def __repr__(self):
        return f"<FrameSide {self.side_name} | Pts: {len(self.radii)} | IPD: {self.ipd}>"
    
    def to_dict(self):
        return {
            "side_name": self.side_name,
            "radii": self.radii.tolist(),
            "z_map": self.z_map.tolist(),
            "ipd": self.ipd,
            "ocht": self.ocht,
            "hbox": self.hbox,
            "vbox": self.vbox
        }
    
    @staticmethod
    def from_dict(data: dict):
        if not data:
            return None
        return FrameSide(
            side_name=data['side_name'],
            radii=np.array(data['radii']),
            z_map=np.array(data['z_map']),
            ipd=data['ipd'],
            ocht=data['ocht'],
            hbox=data['hbox'],
            vbox=data['vbox']
        )

@dataclass
class OMAJob:
    """
    Represents the full parsed OMA job containing both eyes and common bridge data.
    """
    job_id: str
    fpd: float            # Frame Pupil Distance
    dbl: float            # Distance Between Lenses
    left: Optional[FrameSide] = None
    right: Optional[FrameSide] = None

    @property
    def is_valid(self):
        return self.left is not None and self.right is not None
    
    def __repr__(self):
        return f"<OMAJob ID: {self.job_id} | FPD: {self.fpd} | DBL: {self.dbl} | Valid: {self.is_valid}>"
    
    def to_dict(self):
        return {
            "job_id": self.job_id,
            "fpd": self.fpd,
            "dbl": self.dbl,
            "left": self.left.to_dict() if self.left else None,
            "right": self.right.to_dict() if self.right else None
        }
    
    @staticmethod
    def from_dict(data: dict):
        if not data:
            return None
        return OMAJob(
            job_id=data['job_id'],
            fpd=data['fpd'],
            dbl=data['dbl'],
            left=FrameSide.from_dict(data['left']),
            right=FrameSide.from_dict(data['right'])
        )
    
@dataclass
class LensBlank:
    """
    Represents the lens blank parameters for an eye.
    """
    front_radius: float   # Front surface radius (mm)
    back_radius: float    # Back surface radius (mm)
    center_thickness: float # Center thickness (mm)
    diameter: float       # Diameter of the blank (mm)
    
    def __repr__(self):
        return f"<LensBlank FR: {self.front_radius}mm, BR: {self.back_radius}mm, CT: {self.center_thickness}mm, Dia: {self.diameter}mm>"

    def to_dict(self):
        return {
            "front_radius": self.front_radius,
            "back_radius": self.back_radius,
            "center_thickness": self.center_thickness,
            "diameter": self.diameter
        }
    
    @staticmethod
    def from_dict(data: dict):
        if not data:
            return None
        return LensBlank(
            front_radius=data['front_radius'],
            back_radius=data['back_radius'],
            center_thickness=data['center_thickness'],
            diameter=data['diameter']
        )

@dataclass
class LensPair:
    """
    Represents a pair of lens blanks for Left and Right eyes.
    """
    left: LensBlank
    right: LensBlank

    def to_dict(self):
        return {
            "left": self.left.to_dict(),
            "right": self.right.to_dict()
        }
    
    @staticmethod
    def from_dict(data: dict):
        if not data:
            return None
        return LensPair(
            left=LensBlank(**data['left']),
            right=LensBlank(**data['right'])
        )

@dataclass
class MeshData:
    """
    Holds the raw geometric data for a 3D object to be rendered by VTK.
    """
    points: List[float]
    polys: List[int]
    
    def to_dict(self):
        return {"points": self.points, "polys": self.polys}
    
    @staticmethod
    def from_dict(data: dict):
        if not data: return None
        return MeshData(points=data['points'], polys=data['polys'])

@dataclass
class BevelData:
    """
    Holds the 3D line data for the bevel path.
    """
    points: List[float]
    status_colors: List[int] # RGB flattened list [r,g,b, r,g,b...]
    radii: np.ndarray
    z_map: np.ndarray
    
    def to_dict(self):
        return {
            "points": self.points, 
            "status_colors": self.status_colors,
            "radii": self.radii.tolist(),
            "z_map": self.z_map.tolist()
        }

    @staticmethod
    def from_dict(data: dict):
        if not data: return None
        return BevelData(
            points=data['points'], 
            status_colors=data['status_colors'],
            radii=np.array(data["radii"]),
            z_map=np.array(data["z_map"])
        )

@dataclass
class LensSimulationData:
    """
    The complete geometric state of a single lens after processing.
    """
    side: str # 'L' or 'R'
    blank_mesh: MeshData
    cut_mesh: MeshData
    bevel_data: BevelData
    
    def to_dict(self):
        return {
            "side": self.side,
            "blank_mesh": self.blank_mesh.to_dict(),
            "cut_mesh": self.cut_mesh.to_dict(),
            "bevel_data": self.bevel_data.to_dict()
        }

    @staticmethod
    def from_dict(data: dict):
        if not data: return None
        return LensSimulationData(
            side=data['side'],
            blank_mesh=MeshData.from_dict(data['blank_mesh']),
            cut_mesh=MeshData.from_dict(data['cut_mesh']),
            bevel_data=BevelData.from_dict(data['bevel_data'])
        )
    
@dataclass
class LensPairSimulationData:
    """
    Holds the simulation data for both lenses.
    """
    left: Optional[LensSimulationData] = None
    right: Optional[LensSimulationData] = None

    def to_dict(self):
        return {
            "L": self.left.to_dict() if self.left else None,
            "R": self.right.to_dict() if self.right else None
        }
    
    @staticmethod
    def from_dict(data: dict):
        if not data:
            return None
        return LensPairSimulationData(
            left=LensSimulationData.from_dict(data['L']),
            right=LensSimulationData.from_dict(data['R'])
        )