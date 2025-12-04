import numpy as np

def offset_radii_map(radii_map, z_map, offset_x, offset_y):
    """
    Offsets a polar radii map by given X and Y offsets and RESAMPLES 
    it to ensure angles remain uniformly spaced (0 to 2pi).
    
    Args:
        radii_map (array): Array of radii at equal angular intervals.
        z_map (array): Array of z-heights.
        offset_x (float): X offset to apply.
        offset_y (float): Y offset to apply.
        
    Returns:
        new_radii_map (array): Adjusted radii map, resampled to uniform angles.
        new_z_map (array): Adjusted z map, resampled to uniform angles.
    """
    # ----- 1. Normalize input -----
    # radii_map may be scalar
    if np.isscalar(radii_map):
        resolution = 360
        radii_map = np.full(resolution, radii_map)

    num_r = len(radii_map)
    num_z = len(z_map)

    # angles for radii and z, separately
    angles_r = np.linspace(0, 2*np.pi, num_r, endpoint=False)
    angles_z = np.linspace(0, 2*np.pi, num_z, endpoint=False)

    # ----- 2. Convert radii to Cartesian -----
    x = radii_map * np.cos(angles_r)
    y = radii_map * np.sin(angles_r)

    # ----- 3. Apply offsets -----
    x_off = x + offset_x
    y_off = y + offset_y

    # ----- 4. Convert back to polar -----
    r_raw = np.sqrt(x_off**2 + y_off**2)
    theta_raw = np.mod(np.arctan2(y_off, x_off), 2*np.pi)

    # ----- 5. Sort by angle (for interpolation) -----
    sort_idx = np.argsort(theta_raw)
    theta_sorted = theta_raw[sort_idx]
    r_sorted = r_raw[sort_idx]

    # ----- 6. Prepare radius padding (wrap around) -----
    theta_pad = np.concatenate(([theta_sorted[-1] - 2*np.pi],
                                theta_sorted,
                                [theta_sorted[0] + 2*np.pi]))

    r_pad = np.concatenate(([r_sorted[-1]], r_sorted, [r_sorted[0]]))

    # ===== 7. Now interpolate Z-map =====
    # First interpolate z_map to the distorted theta grid
    # Step A: z must be padded to avoid edge issues
    z_pad = np.concatenate(([z_map[-1]], z_map, [z_map[0]]))
    angles_z_pad = np.concatenate(([angles_z[-1] - 2*np.pi],
                                   angles_z,
                                   [angles_z[0] + 2*np.pi]))

    # Step B: resample z onto theta_sorted (distorted positions)
    z_on_distorted = np.interp(theta_sorted, angles_z_pad, z_pad)

    # Step C: pad for final interpolation
    z_pad2 = np.concatenate(([z_on_distorted[-1]],
                             z_on_distorted,
                             [z_on_distorted[0]]))

    # ----- 8. Final uniform angle grid -----
    output_angles = angles_r   # same resolution as radii

    new_radii = np.interp(output_angles, theta_pad, r_pad)
    new_zmap  = np.interp(output_angles, theta_pad, z_pad2)

    return new_radii, new_zmap

def create_roughing_radii(radii_map: np.ndarray, offset_mm: float = 2.0):
    """
    Create an offset polar curve using the correct polar derivative.
    Formula: r_new = r + offset / cos(alpha)
    Where alpha is the angle between the normal and the radius vector.
    """
    r = np.asarray(radii_map, dtype=np.float64)
    n = len(r)

    # 1. Calculate angular step size (d_phi)
    # This was the missing piece!
    d_phi = (2 * np.pi) / n 

    # 2. Compute dr/dphi (periodic derivative)
    # Central difference: (next - prev) / (2 * step)
    dr_dphi = (np.roll(r, -1) - np.roll(r, 1)) / (2.0 * d_phi)

    # 3. Calculate the expansion factor directly
    # Geometric Identity: The cosine of the angle (alpha) between the 
    # Normal vector and the Radius vector is:
    # cos(alpha) = r / sqrt(r^2 + (dr/dphi)^2)
    
    # We need: r_offset = r + offset / cos(alpha)
    # So: r_offset = r + offset * (sqrt(r^2 + dr^2) / r)
    
    # Calculate magnitude of the curve vector (hypotenuse)
    hypotenuse = np.sqrt(r**2 + dr_dphi**2)
    
    # Avoid division by zero if radius is 0 (unlikely for lenses, but good practice)
    safe_r = np.clip(r, 1e-6, None)
    
    # Inverse Cosine factor (1 / cos_theta)
    inv_cos_theta = hypotenuse / safe_r

    # 4. Compute offset
    r_offset = r + (offset_mm * inv_cos_theta)

    return r_offset

def calculate_bevel_geometry(radii_map, z_map, front_curve_mm, back_curve_mm, thickness_mm, bevel_pos_percent=0.5, bevel_width=1.0):
    """
    Calculates the 3D path of the bevel tip along the lens edge.
    Checks if the bevel fits within the available edge thickness.
    
    Args:
        bevel_pos_percent (float): 0.0 = Front Surface, 1.0 = Back Surface.
        bevel_width (float): Width of the bevel in mm (Safety margin).
    
    Returns:
        points (list): [x,y,z] coordinates for the line.
        scalars (list): 0 = Valid (Green), 1 = Invalid (Red).
    """
    assert 0.0 <= bevel_pos_percent <= 1.0, "bevel_pos_percent must be between 0.0 and 1.0"
    assert len(radii_map) == len(z_map), "radii_map and z_map must have the same length"

    if np.isscalar(radii_map):
        n_pts = 360
        radii = np.full(n_pts, radii_map)
    else:
        n_pts = len(radii_map)
        radii = np.array(radii_map)
        
    angles = np.linspace(0, 2*np.pi, n_pts, endpoint=False)
    cos_a = np.cos(angles)
    sin_a = np.sin(angles)
    
    points = []
    status = []
    
    # Half width is the required margin on each side of the tip
    margin = bevel_width / 2.0

    z_front_surf = front_curve_mm - np.sqrt(front_curve_mm**2 - np.minimum(radii, front_curve_mm)**2)
    z_back_surf = back_curve_mm + thickness_mm - np.sqrt(back_curve_mm**2 - np.minimum(radii, back_curve_mm)**2) 
    min_offset = np.max(z_front_surf - z_map)
    max_offset = np.min(z_back_surf - z_map)

    output_z = []
    
    for i in range(n_pts):
        r = radii[i]
        
        # 1. Calculate Z boundaries at this radius
        safe_r_front = np.minimum(r, front_curve_mm)
        z_front_surf = front_curve_mm - np.sqrt(front_curve_mm**2 - safe_r_front**2)
        
        safe_r_back = np.minimum(r, back_curve_mm)
        z_back_surf = back_curve_mm + thickness_mm - np.sqrt(back_curve_mm**2 - safe_r_back**2)
        
        # 2. Determine Valid Range for the Bevel Tip
        # The tip must be at least 'margin' away from front and back surfaces
        z_valid_max = z_back_surf - margin
        z_valid_min = z_front_surf + margin
        
        # 3. Calculate Desired Z
        # Map 0% -> z_front_surf, 100% -> z_back_surf
        desired_z = z_map[i] + min_offset + bevel_pos_percent * (max_offset - min_offset)
        
        # 4. Check Validity
        is_valid = True
        if desired_z > z_valid_max:
            # Poking through front
            is_valid = False
            desired_z = z_valid_max + 0.1 # Visual cue: push it out slightly
        elif desired_z < z_valid_min:
            # Poking through back
            is_valid = False
            desired_z = z_valid_min - 0.1
            
        # Also check if lens is physically too thin for the bevel
        if z_valid_max < z_valid_min:
            is_valid = False # Lens edge is thinner than bevel width!
            
        # 5. Store Point
        x = r * cos_a[i]
        y = r * sin_a[i]
        points.extend([x, y, desired_z])
        output_z.append(desired_z)
        
        # Color: 0.0 for Good (Green), 1.0 for Bad (Red)
        status.append(0.0 if is_valid else 1.0)
        
    return points, status, np.array(output_z)

def generate_lens_mesh(radii_map, front_curve_mm, back_curve_mm, thickness_mm, resolution=360):
    """
    Generates a 3D Mesh (points, polys) for a lens with spherical surfaces.
    Uses concentric rings to approximate the surface curvature.
    
    Args:
        radii_map (array): Radius at each angle. If scalar, assumes circular blank.
        front_curve_mm (float): Radius of curvature for front surface.
        back_curve_mm (float): Radius of curvature for back surface.
        thickness_mm (float): Center thickness.
        resolution (int): Number of angular steps (if generating from scalar).
        
    Returns:
        (points, polys): Arrays formatted for VTK.
    """
    # 1. Handle Input Types (Scalar vs Array)
    if np.isscalar(radii_map):
        # Circular Blank Generation
        angles = np.linspace(0, 2*np.pi, resolution, endpoint=False)
        edge_radii = np.full(resolution, radii_map)
    else:
        # Frame Shape Generation
        n_pts = len(radii_map)
        angles = np.linspace(0, 2*np.pi, n_pts, endpoint=False)
        edge_radii = np.array(radii_map)

    # Number of concentric rings to visualize curvature (more = smoother surface)
    radial_segments = 10 
    
    points = []
    polys = []
    
    num_angles = len(angles)
    
    # Pre-calculate Cos/Sin for angles
    cos_a = np.cos(angles)
    sin_a = np.sin(angles)

    # --- HELPER: Z-Calculation ---
    def get_z_front(r):
        # Sphere centered at (0, 0, -R). Apex at (0,0,0).
        # Z = sqrt(R^2 - r^2) - R  (Negative values as r increases)
        safe_r = np.minimum(r, front_curve_mm)
        return front_curve_mm - np.sqrt(front_curve_mm**2 - safe_r**2)

    def get_z_back(r):
        # Sphere centered at (0, 0, -R - thickness). Apex at (0,0, -thickness).
        safe_r = np.minimum(r, back_curve_mm)
        return back_curve_mm + thickness_mm - np.sqrt(back_curve_mm**2 - safe_r**2)

    # --- STEP 1: GENERATE POINTS ---
    # We generate "Layers" of rings. 
    # Structure: [Front_Ring_0, Front_Ring_1... Front_Ring_N] then [Back_Ring_0 ... Back_Ring_N]
    
    # Front Surface Vertices
    for j in range(radial_segments + 1):
        factor = j / radial_segments
        current_radii = edge_radii * factor
        
        zs = get_z_front(current_radii)
        xs = current_radii * cos_a
        ys = current_radii * sin_a
        
        for i in range(num_angles):
            points.extend([xs[i], ys[i], zs[i]])

    # Back Surface Vertices
    # Note: We generate these separately to make stitching easier logic-wise
    start_idx_back = len(points) // 3
    for j in range(radial_segments + 1):
        factor = j / radial_segments
        current_radii = edge_radii * factor
        
        zs = get_z_back(current_radii)
        xs = current_radii * cos_a
        ys = current_radii * sin_a
        
        for i in range(num_angles):
            points.extend([xs[i], ys[i], zs[i]])

    # --- STEP 2: GENERATE POLYGONS (STITCHING) ---
    
    # A. Stitch Front Surface (Ring j to Ring j+1)
    # Each ring has `num_angles` points.
    for j in range(radial_segments):
        ring_curr_start = j * num_angles
        ring_next_start = (j + 1) * num_angles
        
        for i in range(num_angles):
            next_i = (i + 1) % num_angles
            
            # Indices for the quad (p1, p2, p3, p4)
            p1 = ring_curr_start + i
            p2 = ring_curr_start + next_i
            p3 = ring_next_start + next_i
            p4 = ring_next_start + i
            
            # Triangle 1
            polys.extend([3, p1, p2, p3])
            # Triangle 2
            polys.extend([3, p1, p3, p4])

    # B. Stitch Back Surface (Ring j to Ring j+1)
    # Similar to front, but we usually want to reverse winding order for normals to point out?
    # VTK usually renders double-sided by default, but let's keep standard winding.
    for j in range(radial_segments):
        ring_curr_start = start_idx_back + j * num_angles
        ring_next_start = start_idx_back + (j + 1) * num_angles
        
        for i in range(num_angles):
            next_i = (i + 1) % num_angles
            
            p1 = ring_curr_start + i
            p2 = ring_curr_start + next_i
            p3 = ring_next_start + next_i
            p4 = ring_next_start + i
            
            # Back surface faces "down", so flip triangle order compared to front
            polys.extend([3, p1, p3, p2])
            polys.extend([3, p1, p4, p3])

    # C. Stitch Side Walls (Connecting Front Outer Ring to Back Outer Ring)
    # Front Outer Ring is at index: radial_segments * num_angles
    # Back Outer Ring is at index: start_idx_back + radial_segments * num_angles
    
    front_edge_start = radial_segments * num_angles
    back_edge_start = start_idx_back + radial_segments * num_angles
    
    for i in range(num_angles):
        next_i = (i + 1) % num_angles
        
        f_curr = front_edge_start + i
        f_next = front_edge_start + next_i
        b_curr = back_edge_start + i
        b_next = back_edge_start + next_i
        
        # Wall Quad (f_curr, f_next, b_next, b_curr)
        # Tri 1
        polys.extend([3, f_curr, b_curr, b_next])
        # Tri 2
        polys.extend([3, f_curr, b_next, f_next])

    return points, polys


if __name__ == "__main__":
    # Test roughing radii generation
    import matplotlib.pyplot as plt

    test_radii = np.sin(np.linspace(0, 2*np.pi, 360)) * 40 + 50
    rough_radii = create_roughing_radii(test_radii, offset_mm=2.0)

    # Plotting for verification
    angles = np.linspace(0, 2*np.pi, 360, endpoint=False)
    x_orig = test_radii * np.cos(angles)
    y_orig = test_radii * np.sin(angles)
    x_rough = rough_radii * np.cos(angles)
    y_rough = rough_radii * np.sin(angles)
    print(test_radii)
    print(rough_radii)
    plt.figure()
    plt.plot(x_orig, y_orig, label='Original Radii')
    plt.plot(x_rough, y_rough, label='Roughing Radii')
    plt.axis('equal')
    plt.legend()
    plt.show()
