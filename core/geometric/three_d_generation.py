import numpy as np
import trimesh

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

def calculate_bevel_z_map(radii_map: np.ndarray, curve_radius: float):
    """Calculate the bevel z depth based on the bevel curve radius

    Args:
        radii_map (np.ndarray): _description_
        curve_radius (float): _description_
    """
    bevel_z_map = curve_radius - np.sqrt(curve_radius**2 - np.minimum(radii_map, curve_radius)**2)
    return bevel_z_map

def calculate_bevel_geometry(radii_map, z_map, front_curve_mm, back_curve_mm, thickness_mm, bevel_pos=0.0, bevel_width=0.0):
    """
    Calculates the 3D path of the bevel tip along the lens edge.
    Checks if the bevel fits within the available edge thickness.
    
    Args:
        bevel_pos (float): Shift from front surface.
        bevel_width (float): Width of the bevel in mm (Safety margin).
    
    Returns:
        points (list): [x,y,z] coordinates for the line.
        scalars (list): 0 = Valid (Green), 1 = Invalid (Red).
    """
    assert 0.0 <= bevel_pos, "bevel_pos must be non-negative"
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
    min_index = np.argmin(z_back_surf-z_front_surf)
    min_offset = z_front_surf[min_index] - z_map[min_index]

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
        desired_z = z_map[i] + min_offset + bevel_pos
        
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
    # Strategy: Create CENTER points (apex) first, then concentric rings
    # This avoids degenerate triangles at the center and ensures watertightness
    
    # Front Center (Apex at 0, 0, 0)
    front_center_idx = 0
    points.extend([0.0, 0.0, 0.0])
    
    # Back Center (Apex at 0, 0, thickness)
    back_center_idx = 1
    points.extend([0.0, 0.0, thickness_mm])
    
    # Front Surface Rings (starting from j=1, j=0 is the center)
    front_ring_start = len(points) // 3  # Mark where front rings begin
    for j in range(1, radial_segments + 1):
        factor = j / radial_segments
        current_radii = edge_radii * factor
        
        zs = get_z_front(current_radii)
        xs = current_radii * cos_a
        ys = current_radii * sin_a
        
        for i in range(num_angles):
            points.extend([xs[i], ys[i], zs[i]])

    # Back Surface Rings (starting from j=1, j=0 is the center)
    back_ring_start = len(points) // 3  # Mark where back rings begin
    for j in range(1, radial_segments + 1):
        factor = j / radial_segments
        current_radii = edge_radii * factor
        
        zs = get_z_back(current_radii)
        xs = current_radii * cos_a
        ys = current_radii * sin_a
        
        for i in range(num_angles):
            points.extend([xs[i], ys[i], zs[i]])

    # --- STEP 2: GENERATE POLYGONS (STITCHING) ---
    
    # A. Front Surface Center Fan (Connect apex to first ring)
    first_ring_start = front_ring_start
    for i in range(num_angles):
        next_i = (i + 1) % num_angles
        p_center = front_center_idx
        p_curr = first_ring_start + i
        p_next = first_ring_start + next_i
        
        # Triangle pointing outward (normal up)
        polys.extend([3, p_center, p_curr, p_next])
    
    # B. Front Surface Rings (Ring j to Ring j+1)
    for j in range(radial_segments - 1):
        ring_curr_start = front_ring_start + j * num_angles
        ring_next_start = front_ring_start + (j + 1) * num_angles
        
        for i in range(num_angles):
            next_i = (i + 1) % num_angles
            
            p1 = ring_curr_start + i
            p2 = ring_curr_start + next_i
            p3 = ring_next_start + next_i
            p4 = ring_next_start + i
            
            # Triangle 1
            polys.extend([3, p1, p2, p3])
            # Triangle 2
            polys.extend([3, p1, p3, p4])

    # C. Back Surface Center Fan (Connect apex to first ring)
    first_back_ring_start = back_ring_start
    for i in range(num_angles):
        next_i = (i + 1) % num_angles
        p_center = back_center_idx
        p_curr = first_back_ring_start + i
        p_next = first_back_ring_start + next_i
        
        # Triangle pointing outward (normal down) - reverse winding
        polys.extend([3, p_center, p_next, p_curr])
    
    # D. Back Surface Rings (Ring j to Ring j+1)
    for j in range(radial_segments - 1):
        ring_curr_start = back_ring_start + j * num_angles
        ring_next_start = back_ring_start + (j + 1) * num_angles
        
        for i in range(num_angles):
            next_i = (i + 1) % num_angles
            
            p1 = ring_curr_start + i
            p2 = ring_curr_start + next_i
            p3 = ring_next_start + next_i
            p4 = ring_next_start + i
            
            # Back surface faces "down", so flip triangle order
            polys.extend([3, p1, p3, p2])
            polys.extend([3, p1, p4, p3])

    # E. Stitch Side Walls (Connecting Front Outer Ring to Back Outer Ring)
    # Front Outer Ring is at index: front_ring_start + (radial_segments-1) * num_angles
    # Back Outer Ring is at index: back_ring_start + (radial_segments-1) * num_angles
    
    front_edge_start = front_ring_start + (radial_segments - 1) * num_angles
    back_edge_start = back_ring_start + (radial_segments - 1) * num_angles
    
    for i in range(num_angles):
        next_i = (i + 1) % num_angles
        
        f_curr = front_edge_start + i
        f_next = front_edge_start + next_i
        b_curr = back_edge_start + i
        b_next = back_edge_start + next_i
        
        # Wall faces outward (side of lens)
        # Correct winding: f_curr -> f_next -> b_next -> b_curr
        # Tri 1: f_curr -> f_next -> b_next
        polys.extend([3, f_curr, f_next, b_next])
        # Tri 2: f_curr -> b_next -> b_curr
        polys.extend([3, f_curr, b_next, b_curr])

    return points, polys

def solve_sphere_line_intersection(p1, p2, circle_center, R):
    """
    Finds intersection between a line segment (p1-p2) and a circle.
    p1, p2, circle_center are (r, z) tuples/arrays. R is radius.
    Returns intersection point (r, z) or None if no intersection in segment.
    """
    p1 = np.array(p1)
    p2 = np.array(p2)
    center = np.array(circle_center)
    
    d = p2 - p1
    f = p1 - center
    
    # Quadratic equation: a*t^2 + b*t + c = 0
    a = np.dot(d, d)
    b = 2 * np.dot(f, d)
    c = np.dot(f, f) - R**2
    
    discriminant = b**2 - 4*a*c
    
    if discriminant < 0:
        return None
    
    # We generally want the intersection that implies the surface explicitly 
    # transitions to the tool. 
    t1 = (-b - np.sqrt(discriminant)) / (2*a)
    t2 = (-b + np.sqrt(discriminant)) / (2*a)
    
    # Check if t is within the segment [0, 1]
    # We prefer the intersection closest to p1 (start of tool) for front
    # or logic depends on winding. Let's return the valid one.
    
    valid_t = []
    if 0 <= t1 <= 1: valid_t.append(t1)
    if 0 <= t2 <= 1: valid_t.append(t2)
    
    if not valid_t:
        return None
    
    # Return the intersection point derived from the smallest valid t (first hit)
    t_hit = min(valid_t)
    return p1 + t_hit * d

def get_single_slice_contour(r_edge, z_edge, tool_profile, 
                             front_curve, back_curve, thickness, 
                             n_arc_steps=5, n_tool_steps=20):
    """
    Calculates the (r, z) coordinates for ONE slice of the lens.
    
    Args:
        r_edge: The radius distance where the tool apex sits.
        z_edge: The Z height where the tool apex sits.
        tool_profile: The standard tool shape (N, 2) relative to (0,0).
    """
    
    # 1. Setup Centers
    # Front Apex at (0,0), Center at (0, -FrontR)
    front_center = (0, front_curve)
    # Back Apex at (0, -Thick), Center at (0, -Thick - BackR)
    # Note: Assuming standard meniscus/concave back where center is below.
    # If the back curve is flatter than front, this setup works for standard lenses.
    back_center = (0, thickness + back_curve)

    # 2. Transform Tool to Global Space
    tool_global = tool_profile + [r_edge, z_edge]
    
    # 3. Find Front Intersection
    front_int = None
    tool_start_idx = 0
    
    # Scan tool segments Top -> Bottom
    for k in range(len(tool_global) - 1):
        hit = solve_sphere_line_intersection(tool_global[k], tool_global[k+1], front_center, front_curve)
        if hit is not None:
            front_int = hit
            tool_start_idx = k + 1 
            break
            
    if front_int is None:
        print("Warning: Tool did not intersect Front Surface! Lens might be too thin or tool too far out.")
        return None

    # 4. Find Back Intersection
    back_int = None
    tool_end_idx = len(tool_global) - 1
    
    # Scan tool segments Bottom -> Top
    for k in range(len(tool_global) - 2, -1, -1):
        hit = solve_sphere_line_intersection(tool_global[k], tool_global[k+1], back_center, back_curve)
        if hit is not None:
            back_int = hit
            tool_end_idx = k
            break
            
    if back_int is None:
        print("Warning: Tool did not intersect Back Surface!")
        return None

    # --- Construct the Contour Arrays ---
    contour_r = []
    contour_z = []

    # A. Front Arc (Center -> Intersection)
    # We skip r=0 here, assuming the "Center Fan" will handle the very middle in 3D,
    # or we can include it. Let's include r=0 for the 2D plot visualization.
    r_target = front_int[0]
    for i in range(1, n_arc_steps+1):
        factor = i / (n_arc_steps+1) 
        r = r_target * factor
        # Z = -R + sqrt(R^2 - r^2)
        z = front_curve - np.sqrt(front_curve**2 - r**2)
        contour_r.append(r)
        contour_z.append(z)
    
    # B. Tool Section (Resampled)
    # Extract raw points between intersections
    raw_tool_pts = [front_int]
    if tool_start_idx <= tool_end_idx:
        raw_tool_pts.extend(tool_global[tool_start_idx : tool_end_idx+1])
    else:
        raw_tool_pts.extend(tool_global[tool_start_idx -1 : tool_end_idx: -1])
    raw_tool_pts.append(back_int)
    
    # Resample tool to fixed step count
    raw_tool = np.array(raw_tool_pts)
    dists = np.linalg.norm(raw_tool[1:] - raw_tool[:-1], axis=1)
    cum_dist = np.insert(np.cumsum(dists), 0, 0)
    target_dists = np.linspace(0, cum_dist[-1], n_tool_steps)
    
    interp_r = np.interp(target_dists, cum_dist, raw_tool[:,0])
    interp_z = np.interp(target_dists, cum_dist, raw_tool[:,1])

    for k in range(n_tool_steps):
        contour_r.append(interp_r[k]); contour_z.append(interp_z[k])

    # C. Back Arc (Intersection -> Center)
    r_start = back_int[0]
    for i in range(1, n_arc_steps + 1):
        factor = i / (n_arc_steps + 1)
        r = r_start * (1.0 - factor) # Go backwards from Edge to Center
        
        # Z = -Thick - R + sqrt(R^2 - r^2)
        # Using the standard sphere equation centered at -Thick-R
        safe_r = min(r, back_curve)
        z = (thickness + back_curve) - np.sqrt(back_curve**2 - safe_r**2)
        
        contour_r.append(r)
        contour_z.append(z)
        
    return np.array(contour_r), np.array(contour_z)

def generate_bevel_lens_mesh(
        radii_map, bevel_z_map, tool_profile, 
        front_curve, back_curve, thickness, 
        resolution=360
):
    if not np.isscalar(radii_map): resolution = len(radii_map)
    # 1. Normalize Inputs
    if np.isscalar(radii_map): radii_map = np.full(resolution, radii_map)
    if np.isscalar(bevel_z_map): bevel_z_map = np.full(resolution, bevel_z_map)
    
    angles = np.linspace(0, 2*np.pi, resolution, endpoint=False)
    cos_a = np.cos(angles)
    sin_a = np.sin(angles)
    
    points = []
    polys = []
    
    # --- 2. Add Center Points (Indices 0 and 1) ---
    # Index 0: Front Center (Apex)
    points.extend([0.0, 0.0, 0.0]) 
    
    # Index 1: Back Center (Apex)
    # Note: Logic assumes Front Apex is 0, Back Apex is -thickness
    points.extend([0.0, 0.0, thickness]) 
    
    OFFSET = 2 # The start index for slice data
    
    # --- 3. Generate All Slices (Points) ---
    # We need to know how many points are in one slice to do the math later
    slice_len = 0 
    
    for i in range(resolution):
        # Generate 2D contour
        rr, zz = get_single_slice_contour(radii_map[i], bevel_z_map[i], tool_profile,
                                          front_curve, back_curve, thickness)
        
        # Capture the length of the slice (should be constant for all i)
        if i == 0:
            slice_len = len(rr)
        
        # Convert to 3D and Add
        for k in range(len(rr)):
            px = rr[k] * cos_a[i]
            py = rr[k] * sin_a[i]
            pz = zz[k]
            points.extend([px, py, pz])

    # --- 4. Generate Polygons ---
    for i in range(resolution):
        curr_i = i
        next_i = (i + 1) % resolution
        
        # Helper variables for start indices of the slices
        # Start of Slice i (Points block starts at OFFSET)
        s_curr = OFFSET + curr_i * slice_len
        s_next = OFFSET + next_i * slice_len
        
        # A. Front Center Cap (Fan)
        # Connect Point 0 to the FIRST point of Slice i and Slice i+1
        # First point of slice is index 0 within the slice
        p1_fan = 0
        p2_fan = s_curr + 0
        p3_fan = s_next + 0
        
        # Winding: 0 -> Next -> Curr usually faces UP
        polys.extend([3, p1_fan, p3_fan, p2_fan])
        
        # B. Back Center Cap (Fan)
        # Connect Point 1 to the LAST point of Slice i and Slice i+1
        last_idx = slice_len - 1
        p1_fan_b = 1
        p2_fan_b = s_curr + last_idx
        p3_fan_b = s_next + last_idx
        
        # Winding: 1 -> Curr -> Next usually faces DOWN (outward from bottom)
        polys.extend([3, p1_fan_b, p2_fan_b, p3_fan_b])
        
        # C. Side Ribbons (Quads along the contour)
        # Iterate through the slice points, connecting j to j+1
        for j in range(slice_len - 1):
            # Four corners of the quad
            p1 = s_curr + j
            p2 = s_next + j
            p3 = s_next + j + 1
            p4 = s_curr + j + 1
            
            # Triangle 1
            polys.extend([3, p1, p2, p3])
            # Triangle 2
            polys.extend([3, p1, p3, p4])
            
    return points, polys
def calculate_mesh_volume(points, polys):
    """
    Args:
        points: Flat list [x1, y1, z1, x2, y2, z2, ...]
        polys: VTK-style flat list [3, p1, p2, p3, 3, p1, p3, p4, ...]
    """
    # 1. Convert flat points list to (N, 3) numpy array
    vertices = np.array(points).reshape(-1, 3)

    # 2. Convert VTK polys list to (M, 3) faces array
    # The list looks like [3, a, b, c, 3, d, e, f...]
    # We reshape to (M, 4) and drop the first column (which is always 3)
    faces = np.array(polys).reshape(-1, 4)[:, 1:]

    # 3. Create the mesh object
    mesh = trimesh.Trimesh(vertices=vertices, faces=faces)

    # 4. Check if watertight (volume is undefined for open meshes)
    if not mesh.is_watertight:
        print("Warning: Mesh is not watertight! Volume result may be wrong.")
    
    return mesh.volume

if __name__ == "__main__":
   # Your Tool Profile (from previous prompt)
    tool_profile = np.array([
        [1.58, 9.0],   # Top End
        [1.58, 1.0],   # Top Shoulder
        [0.0, 0.0],    # Apex
        [1.40, -0.7],  # Bot Shoulder
        [1.40, -9.7]   # Bot End
    ])

    # Simulation Parameters
    R_EDGE = 35.0      # Lens radius where we are cutting
    Z_EDGE = 3.5      # Position of the bevel tip (roughly middle of 5mm lens)
    FRONT_C = 500.0    # 200mm Front Radius (approx +2.5 Diopter)
    BACK_C = 200.0     # 200mm Back Radius
    THICK = 5.0        # 5mm Center Thickness

    # Run Generator
    r, z = get_single_slice_contour(R_EDGE, Z_EDGE, tool_profile, 
                                   FRONT_C, BACK_C, THICK)

    import matplotlib.pyplot as plt

    plt.figure(figsize=(10, 6))
    
    plt.plot(r, z, 'b-o', label='Generated Contour', markersize=3)

    plt.grid(True)
    plt.show()
