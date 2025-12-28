"""
Generates volumetric representations of lens geometry using signed distance fields.
Used for visualization in volume rendering. Based on front/back surface approach like test_volume.js
"""

import numpy as np
from dataclasses import dataclass


@dataclass
class LensVolumeData:
    """Represents volumetric lens data for VTK rendering."""
    dimensions: list  # [x, y, z] dimensions of the grid
    spacing: list     # Physical size of each voxel [dx, dy, dz]
    origin: list      # Starting position of the grid [x0, y0, z0]
    scalars: list     # Flattened array of scalar values (densities)


def generate_lens_volume(
    front_radius: float,
    back_radius: float,
    center_thickness: float,
    diameter_mm: float,
    resolution: float = 0.5,
) -> LensVolumeData:
    """
    Generate a volumetric representation of a lens blank using a signed distance field approach.
    
    The lens is modeled with:
    - Front surface: sphere of radius front_radius
    - Back surface: sphere of radius back_radius (for meniscus/concave)
    - Outer boundary: cylinder of diameter diameter_mm
    
    This approach matches the test_volume.js file logic.
    
    Args:
        front_radius: Front surface radius (mm) - positive for convex
        back_radius: Back surface radius (mm) - positive for concave (meniscus)
        center_thickness: Center thickness of the lens (mm)
        diameter_mm: Maximum lens diameter (mm)
        resolution: Voxel size (mm), controls quality vs performance
    
    Returns:
        LensVolumeData with grid dimensions, spacing, origin, and scalar values
    """
    
    # Calculate grid dimensions
    xy_bounds_size = diameter_mm + 1
    z_bounds_size = back_radius - np.sqrt(back_radius**2 - (diameter_mm/2.0)**2) + center_thickness + 1

    print(z_bounds_size)
    
    xy_dim = int(np.ceil(xy_bounds_size / resolution))
    z_dim = int(np.ceil(z_bounds_size / resolution))
    
    # Create the data array
    data_array = np.zeros(xy_dim * xy_dim * z_dim, dtype=np.float32)
    
    # Set up spacing and origin
    spacing = [resolution, resolution, resolution]
    origin = [
        -(xy_dim * spacing[0]) / 2,
        -(xy_dim * spacing[1]) / 2,
        0,
    ]
    
    # Pre-calculate sphere centers
    # Front sphere center (at the top of the lens)
    z_center_front = front_radius
    # Back sphere center (at the bottom, accounting for thickness and radius)
    z_center_back = center_thickness + back_radius
    
    # Populate the volume
    iter_idx = 0
    for z_idx in range(z_dim):
        phys_z = origin[2] + z_idx * spacing[2]
        
        for y_idx in range(xy_dim):
            phys_y = origin[1] + y_idx * spacing[1]
            
            for x_idx in range(xy_dim):
                phys_x = origin[0] + x_idx * spacing[0]
                
                # --- Distance Field Calculation (like test_volume.js) ---
                
                # 1. Distance to Cylinder (XY Plane)
                # d = distance from center - radius
                dist_from_center = np.sqrt(phys_x**2 + phys_y**2)
                dist_cyl = dist_from_center - (diameter_mm / 2.0)
                
                # 2. Distance to Front Sphere (Convex surface)
                # d = distance from sphere center - radius
                dist_sphere1 = np.sqrt(
                    phys_x**2 + phys_y**2 + (phys_z - z_center_front)**2
                ) - front_radius
                
                # 3. Distance to Back Sphere (Concave/Meniscus)
                # For the "inside" logic: we want to be OUTSIDE this sphere
                # d = radius - distance_from_center (inverted)
                dist_to_sphere2_center = np.sqrt(
                    phys_x**2 + phys_y**2 + (phys_z - z_center_back)**2
                )
                dist_sphere2 = back_radius - dist_to_sphere2_center
                
                # INTERSECTION: The point is inside the lens if it is:
                # Inside Cyl AND Inside Sphere1 AND Outside Sphere2
                # In Signed Distance Fields (SDF), Intersection = max(d1, d2, d3)
                max_dist = np.max([dist_cyl, dist_sphere1, dist_sphere2])
                
                # --- Map Distance to Density ---
                # If maxDist is negative, we are inside. If positive, outside.
                # We map this to 0..100 with a small transition zone for smoothness.
                
                if max_dist < 0:
                    # Safely inside lens material
                    value = 100.0
                else:
                    # Safely outside lens
                    value = 0
                
                data_array[iter_idx] = value
                iter_idx += 1
    
    return LensVolumeData(
        dimensions=[xy_dim, xy_dim, z_dim],
        spacing=spacing,
        origin=origin,
        scalars=data_array.tolist()
    )
