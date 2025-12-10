import numpy as np

from core.models.lenses import OMAJob, LensPair, LensSimulationData, MeshData, BevelData
from core.geometric.three_d_generation import (
    generate_lens_mesh, 
    offset_radii_map, 
    calculate_bevel_geometry,
    calculate_bevel_z_map,
    generate_bevel_lens_mesh
)

def calculate_lens_geometry(job: OMAJob, lens_pair: LensPair, bevel_pos_percent: float, bevel_width: float = 1.0) -> dict:
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
        radii, _ = offset_radii_map(frame.radii, frame.z_map, -offset_x, -offset_y)
        bevel_z = calculate_bevel_z_map(radii, 104.6)


        # 3. Generate Bevel
        bev_pts, bev_status, bevel_z = calculate_bevel_geometry(
            radii, bevel_z, 
            blank.front_radius, blank.back_radius, blank.center_thickness, 
            bevel_pos_percent=bevel_pos_percent/100.0, 
            bevel_width=bevel_width
        )

        c_pts, c_polys = generate_bevel_lens_mesh(
            radii_map=radii,
            bevel_z_map=bevel_z,
            tool_profile=np.array([
                [-1.51, 9.04],
                [-1, 1.73],
                [-0, 0],
                [-0.7, -1.21],
                [-0.7, -9.27]
            ]),
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

        # 4. Package Data
        sim_data = LensSimulationData(
            side=side_label,
            blank_mesh=MeshData(b_pts, b_polys),
            cut_mesh=MeshData(c_pts, c_polys),
            bevel_data=BevelData(bev_pts, bev_colors, radii, bevel_z)
        )

        # if side_label=="L": print("mesh_cache_bevel_z", sim_data.bevel_data.z_map[1])
        
        results[side_label] = sim_data.to_dict()
        
    return results