"""
Tool SDF Generation Module

Converts VTK tool meshes into signed distance fields (SDFs) for volumetric
material removal simulation.
"""

import numpy as np
import vtk
from vtkmodules.util import numpy_support
from typing import Tuple, Optional, Dict
import trimesh


class ToolSDF:
    """
    Signed Distance Field representation of a grinding tool.
    
    Stores a discretized 3D grid where each voxel contains the signed distance
    to the nearest point on the tool surface. Negative values = inside tool,
    positive = outside, zero = on surface.
    """
    
    def __init__(
        self,
        sdf_grid: np.ndarray,
        origin: np.ndarray,
        spacing: float,
        tool_id: str,
        tool_name: str
    ):
        """
        Initialize ToolSDF with precomputed distance field.
        
        Args:
            sdf_grid: 3D numpy array of signed distances
            origin: [x, y, z] origin of the grid in world space (mm)
            spacing: Grid resolution (mm per voxel)
            tool_id: Unique identifier for the tool
            tool_name: Human-readable name
        """
        self.sdf_grid = sdf_grid
        self.origin = np.array(origin)
        self.spacing = spacing
        self.tool_id = tool_id
        self.tool_name = tool_name
        self.shape = sdf_grid.shape
        
    def get_dimensions(self) -> Tuple[int, int, int]:
        """Return (dimX, dimY, dimZ) of the SDF grid."""
        return self.shape
    
    def get_bounds(self) -> Tuple[float, float, float, float, float, float]:
        """Return (xmin, xmax, ymin, ymax, zmin, zmax) in world coordinates."""
        dims = self.get_dimensions()
        xmin, ymin, zmin = self.origin
        xmax = xmin + (dims[0] - 1) * self.spacing
        ymax = ymin + (dims[1] - 1) * self.spacing
        zmax = zmin + (dims[2] - 1) * self.spacing
        return (xmin, xmax, ymin, ymax, zmin, zmax)
    
    def to_dict(self) -> Dict:
        """Serialize to dictionary for caching."""
        return {
            'sdf_grid': self.sdf_grid.tolist(),
            'origin': self.origin.tolist(),
            'spacing': self.spacing,
            'tool_id': self.tool_id,
            'tool_name': self.tool_name,
            'shape': self.shape
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'ToolSDF':
        """Deserialize from dictionary."""
        return cls(
            sdf_grid=np.array(data['sdf_grid']),
            origin=np.array(data['origin']),
            spacing=data['spacing'],
            tool_id=data['tool_id'],
            tool_name=data['tool_name']
        )


def compute_tool_sdf_vtk(
    polydata: vtk.vtkPolyData,
    resolution: float = 0.2,
    padding: float = 2.0,
    tool_id: str = "unknown",
    tool_name: str = "Unknown Tool"
) -> ToolSDF:
    """
    Compute signed distance field from VTK PolyData using vtkImplicitPolyDataDistance.
    
    This is the most accurate method for arbitrary tool meshes.
    
    Args:
        polydata: VTK PolyData representing the tool mesh
        resolution: Grid spacing in mm (smaller = more accurate but slower)
        padding: Extra space around tool bounds in mm
        tool_id: Unique identifier for caching
        tool_name: Human-readable name
        
    Returns:
        ToolSDF object containing the discretized distance field
        
    Note:
        - Requires watertight mesh for proper signed distance
        - Negative = inside tool, positive = outside
    """
    
    # Get bounding box of the tool mesh
    bounds = polydata.GetBounds()  # (xmin, xmax, ymin, ymax, zmin, zmax)
    
    # Expand bounds with padding
    xmin, xmax = bounds[0] - padding, bounds[1] + padding
    ymin, ymax = bounds[2] - padding, bounds[3] + padding
    zmin, zmax = bounds[4] - padding, bounds[5] + padding
    
    # Calculate grid dimensions
    dim_x = int(np.ceil((xmax - xmin) / resolution)) + 1
    dim_y = int(np.ceil((ymax - ymin) / resolution)) + 1
    dim_z = int(np.ceil((zmax - zmin) / resolution)) + 1
    
    print(f"Computing SDF for {tool_name}...")
    print(f"  Bounds: X=[{xmin:.2f}, {xmax:.2f}], Y=[{ymin:.2f}, {ymax:.2f}], Z=[{zmin:.2f}, {zmax:.2f}]")
    print(f"  Grid: {dim_x} × {dim_y} × {dim_z} = {dim_x * dim_y * dim_z:,} voxels")
    print(f"  Resolution: {resolution} mm/voxel")
    
    # Create implicit function for distance calculation
    implicit_distance = vtk.vtkImplicitPolyDataDistance()
    implicit_distance.SetInput(polydata)
    
    # Allocate SDF grid
    sdf_grid = np.zeros((dim_x, dim_y, dim_z), dtype=np.float32)
    
    # Compute signed distance for each voxel
    # Vectorized approach for better performance
    total_voxels = dim_x * dim_y * dim_z
    batch_size = 10000  # Process in batches to show progress
    
    # Generate all grid coordinates
    x_coords = xmin + np.arange(dim_x) * resolution
    y_coords = ymin + np.arange(dim_y) * resolution
    z_coords = zmin + np.arange(dim_z) * resolution
    
    point_idx = 0
    for iz, z in enumerate(z_coords):
        for iy, y in enumerate(y_coords):
            for ix, x in enumerate(x_coords):
                # Compute signed distance using VTK
                distance = implicit_distance.EvaluateFunction([x, y, z])
                sdf_grid[ix, iy, iz] = distance
                
                point_idx += 1
                
                # Progress indicator
                if point_idx % 100000 == 0:
                    percent = 100.0 * point_idx / total_voxels
                    print(f"  Progress: {percent:.1f}% ({point_idx:,}/{total_voxels:,} voxels)")
    
    print(f"  SDF computation complete!")
    print(f"  Distance range: [{sdf_grid.min():.3f}, {sdf_grid.max():.3f}] mm")
    
    return ToolSDF(
        sdf_grid=sdf_grid,
        origin=np.array([xmin, ymin, zmin]),
        spacing=resolution,
        tool_id=tool_id,
        tool_name=tool_name
    )


def compute_tool_sdf_trimesh(
    vertices: np.ndarray,
    faces: np.ndarray,
    resolution: float = 0.2,
    padding: float = 2.0,
    tool_id: str = "unknown",
    tool_name: str = "Unknown Tool"
) -> ToolSDF:
    """
    Compute approximate signed distance field using Trimesh.
    
    Faster alternative to VTK method, but less accurate for complex shapes.
    Uses ray casting for inside/outside and closest point for distance.
    
    Args:
        vertices: Nx3 array of mesh vertices
        faces: Mx3 array of triangle face indices
        resolution: Grid spacing in mm
        padding: Extra space around tool bounds in mm
        tool_id: Unique identifier
        tool_name: Human-readable name
        
    Returns:
        ToolSDF object
    """
    
    # Create trimesh object
    mesh = trimesh.Trimesh(vertices=vertices, faces=faces)
    
    if not mesh.is_watertight:
        print(f"Warning: {tool_name} mesh is not watertight. SDF may be inaccurate.")
        # Attempt repair
        mesh.fill_holes()
        mesh.fix_normals()
    
    # Get bounding box
    bounds = mesh.bounds  # [[xmin, ymin, zmin], [xmax, ymax, zmax]]
    
    xmin, ymin, zmin = bounds[0] - padding
    xmax, ymax, zmax = bounds[1] + padding
    
    # Calculate grid dimensions
    dim_x = int(np.ceil((xmax - xmin) / resolution)) + 1
    dim_y = int(np.ceil((ymax - ymin) / resolution)) + 1
    dim_z = int(np.ceil((zmax - zmin) / resolution)) + 1
    
    print(f"Computing SDF for {tool_name} (Trimesh method)...")
    print(f"  Grid: {dim_x} × {dim_y} × {dim_z} = {dim_x * dim_y * dim_z:,} voxels")
    
    # Generate grid points
    x = np.linspace(xmin, xmax, dim_x)
    y = np.linspace(ymin, ymax, dim_y)
    z = np.linspace(zmin, zmax, dim_z)
    
    xx, yy, zz = np.meshgrid(x, y, z, indexing='ij')
    points = np.stack([xx.ravel(), yy.ravel(), zz.ravel()], axis=-1)
    
    print(f"  Computing contains (inside/outside)...")
    # Check which points are inside the mesh
    contains = mesh.contains(points)
    
    print(f"  Computing closest point distances...")
    # Compute unsigned distance to nearest surface point
    _, distances, _ = trimesh.proximity.closest_point(mesh, points)
    
    # Create signed distances: negative inside, positive outside
    signed_distances = np.where(contains, -distances, distances)
    
    # Reshape to grid
    sdf_grid = signed_distances.reshape(dim_x, dim_y, dim_z).astype(np.float32)
    
    print(f"  SDF computation complete!")
    print(f"  Distance range: [{sdf_grid.min():.3f}, {sdf_grid.max():.3f}] mm")
    
    return ToolSDF(
        sdf_grid=sdf_grid,
        origin=np.array([xmin, ymin, zmin]),
        spacing=resolution,
        tool_id=tool_id,
        tool_name=tool_name
    )


def load_tool_mesh_for_sdf(vtk_filename: str) -> vtk.vtkPolyData:
    """
    Load a VTK tool mesh file and prepare it for SDF computation.
    
    Args:
        vtk_filename: Path to .vtk file
        
    Returns:
        vtkPolyData object
        
    Raises:
        FileNotFoundError: If file doesn't exist
        RuntimeError: If file cannot be read
    """
    import os
    
    if not os.path.exists(vtk_filename):
        raise FileNotFoundError(f"Tool mesh file not found: {vtk_filename}")
    
    reader = vtk.vtkPolyDataReader()
    reader.SetFileName(vtk_filename)
    reader.Update()
    
    polydata = reader.GetOutput()
    
    if polydata.GetNumberOfPoints() == 0:
        raise RuntimeError(f"Failed to read tool mesh from {vtk_filename}")
    
    print(f"Loaded tool mesh: {polydata.GetNumberOfPoints()} points, "
          f"{polydata.GetNumberOfCells()} cells")
    
    return polydata


def transform_tool_sdf(
    tool_sdf: ToolSDF,
    position: np.ndarray,
    rotation_deg: float = 0.0,
    tilt_deg: float = 0.0
) -> Tuple[np.ndarray, np.ndarray, float]:
    """
    Transform tool SDF grid to world coordinates based on tool pose.
    
    Returns the transformed grid's origin and bounds for carving operations.
    Note: This doesn't rotate the SDF grid itself (expensive), but returns
    the transformation parameters needed for interpolation during carving.
    
    Args:
        tool_sdf: ToolSDF object in local coordinates
        position: [x, y, z] tool position in world space
        rotation_deg: Rotation around tool axis (degrees)
        tilt_deg: Tool tilt angle (degrees)
        
    Returns:
        (transformed_origin, rotation_matrix, spacing)
        
    Note:
        For actual carving, use apply_tool_sdf_to_volume() which handles
        the interpolation and transformation during subtraction.
    """
    
    # For now, return basic transformation
    # Full 3D rotation of SDF grids is computationally expensive
    # Better to interpolate during carving operation
    
    position = np.array(position)
    transformed_origin = tool_sdf.origin + position
    
    # Build rotation matrix (future enhancement)
    rotation_matrix = np.eye(3)
    
    return transformed_origin, rotation_matrix, tool_sdf.spacing


def apply_tool_sdf_to_volume(
    lens_volume: np.ndarray,
    lens_origin: np.ndarray,
    lens_spacing: float,
    tool_sdf: ToolSDF,
    tool_position: np.ndarray,
    tool_rotation_deg: float = 0.0,
    invert_tool: bool = True
) -> np.ndarray:
    """
    Apply tool SDF to lens volume for material removal (CSG subtraction).
    
    Performs: lens_volume = lens_volume ∩ ¬tool (if invert_tool=True)
    
    Args:
        lens_volume: 3D array of lens material (100 = material, 0 = air)
        lens_origin: [x, y, z] origin of lens volume
        lens_spacing: Resolution of lens volume
        tool_sdf: ToolSDF object
        tool_position: [x, y, z] tool center in world space
        tool_rotation_deg: Rotation around tool axis
        invert_tool: If True, remove material where tool SDF < 0 (inside tool)
        
    Returns:
        Modified lens volume with material removed
    """
    
    # Get lens grid dimensions
    dim_x, dim_y, dim_z = lens_volume.shape
    
    # Transform tool origin to world space
    tool_world_origin = tool_sdf.origin + tool_position
    
    # Find overlap region between lens volume and tool SDF
    # This is a bounding box optimization
    
    lens_xmin, lens_ymin, lens_zmin = lens_origin
    lens_xmax = lens_xmin + (dim_x - 1) * lens_spacing
    lens_ymax = lens_ymin + (dim_y - 1) * lens_spacing
    lens_zmax = lens_zmin + (dim_z - 1) * lens_spacing
    
    tool_bounds = tool_sdf.get_bounds()
    tool_xmin = tool_bounds[0] + tool_position[0]
    tool_xmax = tool_bounds[1] + tool_position[0]
    tool_ymin = tool_bounds[2] + tool_position[1]
    tool_ymax = tool_bounds[3] + tool_position[1]
    tool_zmin = tool_bounds[4] + tool_position[2]
    tool_zmax = tool_bounds[5] + tool_position[2]
    
    # Check if tool intersects lens volume at all
    if (tool_xmax < lens_xmin or tool_xmin > lens_xmax or
        tool_ymax < lens_ymin or tool_ymin > lens_ymax or
        tool_zmax < lens_zmin or tool_zmin > lens_zmax):
        # No intersection, return unchanged
        return lens_volume
    
    # Calculate overlap indices in lens volume
    ix_min = max(0, int(np.floor((tool_xmin - lens_xmin) / lens_spacing)))
    ix_max = min(dim_x - 1, int(np.ceil((tool_xmax - lens_xmin) / lens_spacing)))
    iy_min = max(0, int(np.floor((tool_ymin - lens_ymin) / lens_spacing)))
    iy_max = min(dim_y - 1, int(np.ceil((tool_ymax - lens_ymin) / lens_spacing)))
    iz_min = max(0, int(np.floor((tool_zmin - lens_zmin) / lens_spacing)))
    iz_max = min(dim_z - 1, int(np.ceil((tool_zmax - lens_zmin) / lens_spacing)))
    
    # Sample tool SDF at lens voxel locations (with interpolation if needed)
    for iz in range(iz_min, iz_max + 1):
        for iy in range(iy_min, iy_max + 1):
            for ix in range(ix_min, ix_max + 1):
                # World coordinates of this lens voxel
                world_x = lens_xmin + ix * lens_spacing
                world_y = lens_ymin + iy * lens_spacing
                world_z = lens_zmin + iz * lens_spacing
                
                # Transform to tool local coordinates
                tool_local_x = world_x - tool_world_origin[0]
                tool_local_y = world_y - tool_world_origin[1]
                tool_local_z = world_z - tool_world_origin[2]
                
                # Find corresponding index in tool SDF
                tool_ix = int(np.round(tool_local_x / tool_sdf.spacing))
                tool_iy = int(np.round(tool_local_y / tool_sdf.spacing))
                tool_iz = int(np.round(tool_local_z / tool_sdf.spacing))
                
                # Check bounds
                if (0 <= tool_ix < tool_sdf.shape[0] and
                    0 <= tool_iy < tool_sdf.shape[1] and
                    0 <= tool_iz < tool_sdf.shape[2]):
                    
                    # Get signed distance at this point
                    distance = tool_sdf.sdf_grid[tool_ix, tool_iy, tool_iz]
                    
                    # Remove material where tool is present (distance < 0)
                    if invert_tool:
                        if distance < 0:
                            lens_volume[ix, iy, iz] = 0  # Remove material
                    else:
                        if distance >= 0:
                            lens_volume[ix, iy, iz] = 0
    
    return lens_volume


# Cache for computed tool SDFs
_tool_sdf_cache: Dict[str, ToolSDF] = {}


def get_cached_tool_sdf(
    tool_id: str,
    vtk_filename: str,
    tool_name: str,
    resolution: float = 0.2,
    padding: float = 2.0,
    method: str = "vtk"
) -> ToolSDF:
    """
    Get or compute tool SDF with caching.
    
    Args:
        tool_id: Unique identifier for caching
        vtk_filename: Path to tool mesh file
        tool_name: Human-readable name
        resolution: Grid resolution in mm
        padding: Padding around tool in mm
        method: "vtk" (accurate) or "trimesh" (faster)
        
    Returns:
        ToolSDF object (from cache or newly computed)
    """
    
    cache_key = f"{tool_id}_{resolution}_{padding}_{method}"
    
    if cache_key in _tool_sdf_cache:
        print(f"Using cached SDF for {tool_name}")
        return _tool_sdf_cache[cache_key]
    
    print(f"Computing new SDF for {tool_name}...")
    
    if method == "vtk":
        polydata = load_tool_mesh_for_sdf(vtk_filename)
        tool_sdf = compute_tool_sdf_vtk(
            polydata, resolution, padding, tool_id, tool_name
        )
    elif method == "trimesh":
        polydata = load_tool_mesh_for_sdf(vtk_filename)
        # Convert to numpy arrays - DIRECT conversion, no intermediate vtkPoints
        vertices = numpy_support.vtk_to_numpy(polydata.GetPoints().GetData())
        
        # Extract faces
        polys = polydata.GetPolys()
        cell_array = numpy_support.vtk_to_numpy(polys.GetData())
        faces = cell_array.reshape(-1, 4)[:, 1:]  # Remove cell size prefix
        
        tool_sdf = compute_tool_sdf_trimesh(
            vertices, faces, resolution, padding, tool_id, tool_name
        )
    else:
        raise ValueError(f"Unknown method: {method}. Use 'vtk' or 'trimesh'.")
    
    _tool_sdf_cache[cache_key] = tool_sdf
    return tool_sdf


def clear_tool_sdf_cache():
    """Clear the tool SDF cache to free memory."""
    global _tool_sdf_cache
    _tool_sdf_cache.clear()
    print("Tool SDF cache cleared")
