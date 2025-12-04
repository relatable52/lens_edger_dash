import numpy as np

def solve_lens_kinematics_robust(radii, z_map, tool_radius, tool_tilt_angle_deg, tool_z_offset=0):
    """
    Calculates Machine X/Z/Theta using the "Max-Projection" collision method.
    This is slower than analytic methods but robust against sharp corners and bad data.
    
    Args:
        radii (array): Polar radii of the lens.
        z_map (array): Z-heights of the lens.
        tool_radius (float): Major axis of the ellipse (Physical radius).
        tool_tilt_angle_deg (float): Tilt angle creating the minor axis.
        
    Returns:
        dict: Kinematics arrays.
    """
    n_pts = len(radii)
    # Define the Lens Point Cloud (Polar -> Cartesian)
    angles_lens = np.linspace(0, 2*np.pi, n_pts, endpoint=False)
    lens_x = radii * np.cos(angles_lens)
    lens_y = radii * np.sin(angles_lens)
    
    # Define Tool Ellipse Parameters
    # a = Major Axis (Radius), b = Minor Axis (Radius * cos(tilt))
    a = tool_radius
    b = tool_radius * np.cos(np.deg2rad(tool_tilt_angle_deg))
    
    # We define the resolution of the MACHINE rotation.
    # Usually 3600 steps (0.1 degrees) for precision.
    n_machine_steps = len(radii)
    theta_machine = np.linspace(0, 2*np.pi, n_machine_steps, endpoint=False)
    
    # Output arrays
    machine_x_path = []
    machine_z_path = []
    
    # --- VECTORIZED LOOP ---
    # We iterate through every Machine Rotation Angle
    for theta_m in theta_machine:
        
        # 1. Rotate the Lens Point Cloud to the current Machine Angle
        # Rotation Matrix:
        # x' = x*cos(t) - y*sin(t)
        # y' = x*sin(t) + y*cos(t)
        # Note: We rotate by -theta_m because machine rotates CW relative to lens
        cos_t = np.cos(-theta_m)
        sin_t = np.sin(-theta_m)
        
        x_rot = lens_x * cos_t - lens_y * sin_t
        y_rot = lens_x * sin_t + lens_y * cos_t
        
        # 2. Filter points that are physically cuttable
        # If a point's Y height is larger than the tool's minor axis (b), 
        # the tool physically cannot touch it (it passes under/over).
        valid_mask = np.abs(y_rot) < a
        
        if not np.any(valid_mask):
            # Fallback: Lens is huge or tool is tiny?
            machine_x_path.append(tool_radius + 100) # Safe retract
            machine_z_path.append(tool_z_offset)
            continue
            
        # 3. Calculate "Required Tool Center" for every valid point
        # X_c = x_point + a * sqrt(1 - y^2/b^2)
        # This is the "Projection" logic
        term_sq = 1.0 - (y_rot[valid_mask]**2 / a**2)
        # Clip negative zero errors
        term_sq[term_sq < 0] = 0
        
        x_centers = x_rot[valid_mask] + b * np.sqrt(term_sq)
        
        # 4. The actual machine position is determined by the point 
        # that pushes the tool furthest out.
        max_idx_local = np.argmax(x_centers)
        current_machine_x = x_centers[max_idx_local]
        
        machine_x_path.append(current_machine_x)
        
        # 5. Calculate Z (Simple Mapping for now)
        # We need the Z-height of the SPECIFIC POINT that is touching the tool.
        # We need to find which original index 'i' corresponds to max_idx_local
        valid_indices = np.where(valid_mask)[0]
        contact_point_idx = valid_indices[max_idx_local]
        
        # Tangency adjustment for Z on tilted wheel:
        tilt_z_comp = (current_machine_x - x_rot[max_idx_local]) * np.tan(np.deg2rad(tool_tilt_angle_deg))
        
        current_machine_z = tool_z_offset - z_map[contact_point_idx] - tilt_z_comp
        # if(theta_m < theta_machine[1]): print("z_map_contact", z_map[contact_point_idx])
        machine_z_path.append(current_machine_z)

    # print("machine_z_path", machine_z_path[0])

    return {
        "theta_machine_deg": np.degrees(theta_machine),
        "x_machine": np.array(machine_x_path),
        "z_machine": np.array(machine_z_path)
    }