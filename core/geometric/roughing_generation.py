from typing import List

import numpy as np

from core.geometric.three_d_generation import calculate_mesh_volume, generate_lens_mesh, 
from core.models.roughing import RoughingPassData, RoughingPassParam
from core.models.lenses import MeshData

def generate_roughing_operations(
    final_radii: np.ndarray,
    blank_radius: float,
    lens_thickness: float,
    front_curve: float,  
    back_curve: float, 
    operations: List[RoughingPassParam]
) -> List[RoughingPassData]:
    
    results = []
    n_points = len(final_radii)
    
    # 1. Initialize current state as the Blank (perfect circle)
    current_radii = np.full(n_points, blank_radius)
    
    # Calculate initial Blank Volume (Reference point)
    # We generate the blank mesh just to get its volume
    b_pts, b_polys = generate_lens_mesh(
        blank_radius, front_curve, back_curve, lens_thickness
    )
    current_volume = calculate_mesh_volume(b_pts, b_polys)
    
    # Identify 12 o'clock index (assuming 0 is 3 o'clock, 90 deg is 12 o'clock)
    idx_12h = int(n_points * 0.25) 

    for i, op in enumerate(operations):
        
        # --- A. GENERATE PATH GEOMETRY (1D) ---
        if op.method == "CONCENTRIC":
            # Look at max radius of PREVIOUS pass and subtract step
            current_max_r = np.max(current_radii)
            target_circle_r = current_max_r - op.step_value_mm
            
            # Apply Safety Mask: Never cut deeper than the final lens
            new_radii = np.maximum(final_radii, target_circle_r)
            
        elif op.method == "INTERPOLATION":
            # Calculate gap at 12 o'clock
            current_r_12h = current_radii[idx_12h]
            final_r_12h = final_radii[idx_12h]
            total_gap_12h = current_r_12h - final_r_12h
            
            # Determine interpolation factor (t)
            if total_gap_12h <= 0:
                 t = 1.0
            else:
                 t = op.step_value_mm / total_gap_12h
            
            t = min(t, 1.0)
            
            # Linear Interpolation
            new_radii = current_radii - (t * (current_radii - final_radii))
            new_radii = np.maximum(final_radii, new_radii)
        
        else:
            # Fallback if method is unknown, maintain current shape
            new_radii = current_radii

        # --- B. GENERATE 3D MESH ---
        # Now we convert the 1D radii array into a full 3D object
        # This allows us to visualize the roughing step in the UI
        mesh_pts, mesh_polys = generate_lens_mesh(
            new_radii, 
            front_curve, 
            back_curve, 
            lens_thickness
        )

        # --- C. CALCULATE PHYSICS (Exact Volume) ---
        # Calculate volume of the new shape
        new_volume = calculate_mesh_volume(mesh_pts, mesh_polys)
        
        # Calculate how much material was removed in THIS step
        removed_vol = current_volume - new_volume
        
        # Avoid negative volumes due to floating point noise if shape didn't change
        removed_vol = max(0.0, removed_vol)

        # Duration estimation
        duration = op.speed_s_per_rev 
        
        # --- D. STORE RESULT ---
        # We package everything into RoughingPassData
        results.append(RoughingPassData(
            pass_index=i + 1,
            mesh=MeshData(points=mesh_pts, polys=mesh_polys),
            radii=new_radii.tolist(),
            volume=round(removed_vol, 2), # Volume removed in this step
            duration=duration
        ))
        
        # Update state for next loop
        current_radii = new_radii
        current_volume = new_volume

    return results