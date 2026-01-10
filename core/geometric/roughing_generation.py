from typing import List, Tuple
import numpy as np
from scipy.spatial import ConvexHull

# Assuming project imports
from core.geometric.three_d_generation import calculate_mesh_volume, generate_lens_mesh 
from core.models.roughing import RoughingPassData, RoughingSettings
from core.models.lenses import MeshData

def get_convex_radii(radii: np.ndarray) -> np.ndarray:
    """
    Takes a polar profile (radii) and returns a modified radii array
    representing the Convex Hull (rubber band wrap) of the shape.
    """
    n = len(radii)
    angles = np.linspace(0, 2 * np.pi, n, endpoint=False)
    
    # 1. Convert Polar to Cartesian
    x = radii * np.cos(angles)
    y = radii * np.sin(angles)
    points = np.column_stack((x, y))
    
    # 2. Compute 2D Convex Hull
    # This gives us the indices of the points that form the "rubber band"
    try:
        hull = ConvexHull(points)
        hull_indices = hull.vertices
    except Exception:
        # Fallback for degenerate shapes (e.g. points all on a line), though unlikely in lens processing
        return radii

    # 3. Sort Hull Vertices by Angle to allow linear processing
    # We gather the (angle, radius) of the hull vertices
    hull_angles = angles[hull_indices]
    hull_radii = radii[hull_indices]
    
    # Sort by angle
    sorted_order = np.argsort(hull_angles)
    hull_angles = hull_angles[sorted_order]
    hull_radii = hull_radii[sorted_order]
    
    # Append the first point to the end to close the loop for interpolation
    hull_angles = np.append(hull_angles, hull_angles[0] + 2*np.pi)
    hull_radii = np.append(hull_radii, hull_radii[0])

    # 4. Resample: Interpolate the hull edges back to the original N angles
    # Since the hull is a set of line segments, we calculate the intersection
    # of the ray at 'angle' with the segment connecting hull vertices.
    
    new_radii = np.zeros_like(radii)
    
    # We use numpy interpolation for the angles, but we need to interpolate 
    # based on the geometric line segment, not just linear value interpolation.
    # However, for dense meshes (N > 360), standard linear interpolation of 
    # (angle vs radius) is a very close approximation to the chord. 
    # For exact precision:
    
    current_hull_idx = 0
    max_hull_idx = len(hull_angles) - 2
    
    for i in range(n):
        theta = angles[i]
        
        # Advance the hull segment pointer if needed
        while current_hull_idx < max_hull_idx and theta > hull_angles[current_hull_idx+1]:
            current_hull_idx += 1
            
        # Get the two vertices of the current hull edge
        a1 = hull_angles[current_hull_idx]
        a2 = hull_angles[current_hull_idx + 1]
        r1 = hull_radii[current_hull_idx]
        r2 = hull_radii[current_hull_idx + 1]
        
        # Exact polar line intersection formula
        # The line passes through (r1, a1) and (r2, a2).
        # We want r at theta.
        # Line eq in polar: r * cos(theta - alpha) = d 
        # Easier approach: Convert vertices to cartesian, intersect ray.
        
        p1x, p1y = r1 * np.cos(a1), r1 * np.sin(a1)
        p2x, p2y = r2 * np.cos(a2), r2 * np.sin(a2) # Note: a2 might be > 2pi, use cos/sin correctly
        
        # Ray vector: (cos theta, sin theta)
        # Intersection of Ray (0,0)->D and Line P1->P2
        # Use cross product logic or simple line intersection
        
        # Denominator for intersection
        denom = (p2y - p1y) * np.cos(theta) - (p2x - p1x) * np.sin(theta)
        
        if abs(denom) < 1e-9:
            new_radii[i] = radii[i] # Fallback
        else:
            numerator = p1x * p2y - p1y * p2x
            new_r = numerator / denom
            new_radii[i] = new_r

    return new_radii


def generate_roughing_operations(
    final_radii: np.ndarray,
    blank_radius: float,
    lens_thickness: float,
    front_curve: float,  
    back_curve: float,
    roughing_settings: RoughingSettings
) -> List[RoughingPassData]:
    
    results = []
    n_points = len(final_radii)
    method = roughing_settings.method
    operations = roughing_settings.passes
    
    # Initialize State
    current_radii = np.full(n_points, blank_radius)
    virtual_circle_radius = blank_radius
    
    # Initial Volume
    b_pts, b_polys = generate_lens_mesh(blank_radius, front_curve, back_curve, lens_thickness)
    current_volume = calculate_mesh_volume(b_pts, b_polys)
    
    # 12 o'clock index
    idx_12h = int(n_points * 0.25) 

    # --- MAIN LOOP ---
    for i, op in enumerate(operations):
        
        if method == "CONCENTRIC":
            # 1. Shrink virtual circle
            virtual_circle_radius -= op.step_value_mm
            
            # 2. Combine Circle + Final Shape
            proposed_radii = np.maximum(final_radii, virtual_circle_radius)
            
            # 3. Apply Convex Hull to ensure machinability
            # This bridges the gaps between the circle and the lens tips
            new_radii = get_convex_radii(proposed_radii)
            
        elif method == "INTERPOLATION":
            # Interpolation logic
            current_r_12h = current_radii[idx_12h]
            final_r_12h = final_radii[idx_12h]
            gap = current_r_12h - final_r_12h
            
            t = 1.0 if gap <= 0 else min(op.step_value_mm / gap, 1.0)
            
            # Linear move towards target
            step_radii = current_radii - (t * (current_radii - final_radii))
            proposed_radii = np.maximum(final_radii, step_radii)
            
            # Ensure convexity here as well if required, though interpolation 
            # usually preserves the convexity of the start/end shapes.
            # Safe to apply if we want strict machinability:
            new_radii = get_convex_radii(proposed_radii)
            
        else:
            new_radii = current_radii

        # Create Pass Data
        pass_data, new_vol = _create_pass_data(
            i + 1, new_radii, current_volume, front_curve, back_curve, lens_thickness, op.speed_s_per_rev
        )
        results.append(pass_data)
        
        current_radii = new_radii
        current_volume = new_vol

    # --- FINAL CONTOUR (FINISHING CUT) ---
    # As requested: "Also for both type of contour you should a final contour"
    # This ensures the final shape is exactly the target shape.
    
    # Check if we need a final cut (if current shape is larger than final)
    max_deviation = np.max(current_radii - final_radii)
    
    if max_deviation > 0.001:
        # Use last operation speed or default
        final_speed = operations[-1].speed_s_per_rev if operations else 10.0
        
        # Note: The final cut might NOT be convex (e.g., if the lens has a dip).
        # Typically finishing passes follow the exact contour, assuming the 
        # roughing wheel has cleared enough space to access it (or a smaller wheel is used).
        # We pass final_radii directly.
        
        final_pass, _ = _create_pass_data(
            len(results) + 1, 
            final_radii, 
            current_volume, 
            front_curve, 
            back_curve, 
            lens_thickness, 
            final_speed
        )
        results.append(final_pass)

    return results

def _create_pass_data(index, radii, prev_vol, fc, bc, th, speed):
    mesh_pts, mesh_polys = generate_lens_mesh(radii, fc, bc, th)
    new_vol = calculate_mesh_volume(mesh_pts, mesh_polys)
    removed = max(0.0, prev_vol - new_vol)
    
    return RoughingPassData(
        pass_index=index,
        mesh=MeshData(points=mesh_pts, polys=mesh_polys),
        radii=radii.tolist(),
        volume=round(removed, 2),
        duration=speed
    ), new_vol
