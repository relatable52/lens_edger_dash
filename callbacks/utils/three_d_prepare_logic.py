import numpy as np

from core.models.lenses import OMAJob, LensPair, LensSimulationData, MeshData, BevelData, BevelSettings
# 1. Import your profiles
from core.geometric.tool_profiles import V_BEVEL, FLAT, GROOVE
from core.geometric.three_d_generation import (
    generate_lens_mesh, 
    offset_radii_map, 
    calculate_bevel_geometry,
    calculate_bevel_z_map,
    generate_bevel_lens_mesh
)

def calculate_lens_geometry(job: OMAJob, lens_pair: LensPair, bevel_settings: BevelSettings, bevel_width: float = 0) -> dict:
    """
    Generates the full 3D geometry for both lenses and returns a dictionary
    ready for dcc.Store.
    """
    results = {}
    
    sides = [('L', job.left, lens_pair.left), ('R', job.right, lens_pair.right)]
    
    half_fpd = job.fpd / 2.0

    for side_label, frame, blank in sides:
        if not frame:
            continue
            
        # 1. Generate Blank Mesh (The Ghost)
        b_pts, b_polys = generate_lens_mesh(
            blank.diameter/2.0, blank.front_radius, blank.back_radius, blank.center_thickness
        )
        
        # 2. Generate Cut Mesh (Offset logic)
        offset_x = frame.ipd - half_fpd if side_label == "R" else - frame.ipd + half_fpd
        offset_y = frame.ocht - (frame.vbox / 2.0)
        
        # Apply offsets to frame data to center it on the lens blank
        radii, oma_z_map = offset_radii_map(frame.radii, frame.z_map, -offset_x, -offset_y)
        
        # --- 3. CALCULATE BASE BEVEL CURVE (Z-MAP) ---
        if bevel_settings.curve_mode == 'oma':
            # Use the offset OMA Z-values directly
            bevel_z = oma_z_map
            
        else:
            # We need to determine the radius of the sphere that defines the bevel curve
            target_radius = 1e9 # Default to effectively flat if 0 diopter
            
            if bevel_settings.curve_mode == 'diopter':
                # Formula: R = 523 / D
                d_val = bevel_settings.curve_value
                if abs(d_val) > 1e-3: # Avoid divide by zero
                    target_radius = 523.0 / d_val
                    
            elif bevel_settings.curve_mode == 'ratio':
                # 1. Get Diopters of Blank Surfaces
                d_front = 523.0 / blank.front_radius if blank.front_radius != 0 else 0.0
                d_back = 523.0 / blank.back_radius if blank.back_radius != 0 else 0.0
                
                # 2. Interpolate Diopters (0% = Front, 100% = Back)
                ratio = bevel_settings.curve_value / 100.0
                d_target = d_front + ratio * (d_back - d_front)
                
                # 3. Convert Target Diopter back to Radius
                if abs(d_target) > 1e-3:
                    target_radius = 523.0 / d_target

            # Generate the Z-map based on the calculated spherical radius
            bevel_z = calculate_bevel_z_map(radii, target_radius)

        # --- 4. Generate Bevel Geometry (Applying Shift & Limits) ---
        bev_pts, bev_status, final_bevel_z = calculate_bevel_geometry(
            radii, bevel_z, 
            blank.front_radius, blank.back_radius, blank.center_thickness, 
            bevel_pos=bevel_settings.z_shift_mm, 
            bevel_width=bevel_width
        )

        # --- 5. SELECT TOOL PROFILE ---
        # Map string type to numpy array
        if "flat" in bevel_settings.type:
            selected_profile = FLAT
        elif "vbevel" in bevel_settings.type:
            selected_profile = V_BEVEL
        elif "groove" in bevel_settings.type:
            selected_profile = GROOVE
        else:
            selected_profile = V_BEVEL # Fallback

        # --- 6. Generate Final Cut Mesh ---
        c_pts, c_polys = generate_bevel_lens_mesh(
            radii_map=radii,
            bevel_z_map=final_bevel_z, # Use the final shifted Z
            tool_profile=selected_profile, # <--- USE SELECTED PROFILE
            front_curve=blank.front_radius,
            back_curve=blank.back_radius,
            thickness=blank.center_thickness
        )
        
        # Color Processing (Green/Red)
        bev_colors = []
        for status in bev_status:
            if status == 0.0:
                bev_colors.extend([0, 255, 0]) # Green
            else:
                bev_colors.extend([255, 0, 0]) # Red

        # 7. Package Data
        sim_data = LensSimulationData(
            side=side_label,
            blank_mesh=MeshData(b_pts, b_polys),
            cut_mesh=MeshData(c_pts, c_polys),
            bevel_data=BevelData(bev_pts, bev_colors, radii, final_bevel_z),
            blank_front_radius=blank.front_radius,
            blank_back_radius=blank.back_radius,
            blank_center_thickness=blank.center_thickness,
            blank_diameter=blank.diameter
        )

        results[side_label] = sim_data.to_dict()
    return results