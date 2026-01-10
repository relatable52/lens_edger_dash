"""
Generates volumetric representations of lens geometry using signed distance fields.
Used for visualization in volume rendering. Based on front/back surface approach like test_volume.js
"""

from dataclasses import dataclass

import numpy as np
from scipy.interpolate import interp1d

from core.geometric.tool_profiles import V_BEVEL, FLAT, GROOVE
from core.machine_config import load_machine_config_cached
from core.models.tools import ToolStack

TOOL_STACK = load_machine_config_cached()

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
    time_length: float = 1000.0
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

    # print(z_bounds_size)
    
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
    
    # Smooth edge width (like test_volume_2.html)
    smooth_edge = resolution * 0
    
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
                
                # --- Map Distance to Density with Smooth Transitions ---
                # Values: 1000 = full material, 0 = air, 500 = isosurface
                
                if max_dist < -smooth_edge:
                    # Safely inside lens material
                    value = 1000.0
                elif max_dist > smooth_edge:
                    # Safely outside lens (air)
                    value = 1000.0 - time_length
                else:
                    # Smooth transition zone
                    value = 1000.0 - time_length * (max_dist + smooth_edge) / (2 * smooth_edge)
                
                data_array[iter_idx] = value
                iter_idx += 1
    
    return LensVolumeData(
        dimensions=[xy_dim, xy_dim, z_dim],
        spacing=spacing,
        origin=origin,
        scalars=data_array.tolist()
    )

def compute_voxel_death_times(voxels, voxel_res, tool_path, tool_stack: ToolStack):
    """
    Computes the death time for each voxel.
    
    Args:
        voxels: 3D numpy array (Z, Y, X) or (X, Y, Z) representing the lens.
        voxel_res: float, size of one voxel in mm.
        tool_path: dict containing 'r', 'z', 'theta', 'time', 'pass_data'.
        tool_stack: The ToolStack object containing wheels and tilt.
        machine_config: Config object containing tilt angle (if not in tool_stack).
    
    Returns:
        death_times: Numpy array of same shape as voxels. 
                     Values are time of cut, or np.inf if never cut.
    """
    
    # 1. Initialize Death Time Array
    death_times = voxels
    time_length = tool_path['time'][-1]
    
    # 2. Pre-calculate Profile Interpolators for each wheel
    #    Maps 'Y' (height along tool) to 'Z' (radial offset from cutting edge)
    profile_funcs = {} 
    
    # Define your profiles manually or load them
    # Note: These correspond to the arrays you provided
    profiles_data = {
        "bevel_std": np.array([
            [-1.797,  9.045],  # Top Edge
            [0.678,  1.427],  # V-Shoulder (Top)
            [0.0, -0.371],  # V-Apex
            [1.604, -1.427],  # V-Shoulder (Bottom)
            [4.097, -9.045]   # Bottom Edge
        ]),
        # "bevel_std": np.array([[-2.5, 9.51], [2.5, -9.51]]), # Simplified flat profile for bevel
        "rough_glass": np.array([[-3.09, 9.51], [3.09, -9.51]]), # Simplified flat profile for roughing
        # Add GROOVE or FLAT as needed
    }

    for wheel in tool_stack.wheels:
        if wheel.tool_id in profiles_data:
            prof = profiles_data[wheel.tool_id]
            # Profile columns: [Radial_Offset (Z), Axial_Height (Y)]
            # We want to find Radial_Offset given Axial_Height.
            # Sort by Y (axis) to ensure monotonic increasing for interpolation
            sorted_indices = np.argsort(prof[:, 1])
            p_sorted = prof[sorted_indices]
            
            # Create interpolator: f(h) -> radial_offset
            # bounds_error=False, fill_value=-np.inf means if we are above/below the wheel height, 
            # the radius is effectively 0 (or negative infinite) so we don't cut.
            profile_funcs[wheel.tool_id] = interp1d(
                p_sorted[:, 1], 
                p_sorted[:, 0], 
                kind='linear', 
                bounds_error=False, 
                fill_value=-1e9
            )

    # 3. Create Coordinate Grid (Voxel Frame)
    # Assumes voxels are centered at (0,0,0) or you need an offset
    # Adjust origin logic to match your numpy array setup
    nz, ny, nx = voxels.shape
    z_coords = np.arange(nz) * voxel_res
    y_coords = (np.arange(ny) - ny//2) * voxel_res
    x_coords = (np.arange(nx) - nx//2) * voxel_res
    
    # Create meshgrid of actual coordinates
    # Note: indexing='ij' for matrix indexing
    Z_grid, Y_grid, X_grid = np.meshgrid(z_coords, y_coords, x_coords, indexing='ij')

    # Flatten for vectorized operation (optional, helps if fitting in memory)
    # Or keep as 3D. Let's work with flattened vectors for clarity on math.
    points_lens_frame = np.vstack((X_grid.ravel(), Y_grid.ravel(), Z_grid.ravel()))
    
    # Pre-calculate Tool Tilt Vector (Unit vector)
    # Tilt is typically around the Y-axis (if Z is lens axis and X is radial)
    # Adjust based on your specific machine kinematics definition.
    # Assuming tilt is toward the lens axis in the X-Z plane.
    tilt_rad = np.radians(tool_stack.tilt_angle_deg) 
    # Vector of tool axis in the Machine Frame (assuming tool at rest is along Z)
    # If tilt=0, tool axis is (0,0,1). If tilted 18 deg towards X...
    tool_axis_vec = np.array([-np.sin(tilt_rad), 0, np.cos(tilt_rad)])

    # 4. Iterate over Time Steps
    # To speed this up, don't run every millisecond. Downsample time or group by pass.
    
    num_steps = len(tool_path['time'])
    
    for i in range(0, num_steps, 5): # Step skip optimization (adjust as needed)
        t = tool_path['time'][i]
        r_mach = tool_stack.base_position[0] - tool_path['x'][i]
        z_mach = tool_stack.base_position[2] - tool_path['z'][i]
        theta_lens = -np.radians(tool_path['theta'][i])

        # print("Hehe", r_mach, z_mach)
        
        # Determine active wheel based on time or pass_data
        # Simple logic: check which pass 't' falls into
        active_wheel = None
        for p_data in tool_path['pass_time_breaks']:
            if p_data['start_time'] <= t <= p_data['end_time']:
                # Find the wheel object from the stack
                active_wheel = tool_stack.wheels[0] if p_data['operation_type'] == 'roughing' else tool_stack.wheels[1]
                break
        
        if not active_wheel: continue
        if active_wheel.tool_id not in profile_funcs: continue

        # --- Coordinate Transformation ---
        
        # A. Inverse Lens Rotation
        # We rotate the TOOL position by -theta around the Lens Z-axis.
        # Original Tool Pos (Machine Frame): [r, 0, z] (Assuming standard polar machine coords)
        # Rotated Tool Pos (Lens Frame):
        # x_t = r * cos(-theta)
        # y_t = r * sin(-theta)
        # z_t = z
        cos_t = np.cos(-theta_lens)
        sin_t = np.sin(-theta_lens)
        
        tool_pos_x = r_mach * cos_t
        tool_pos_y = r_mach * sin_t
        tool_pos_z = z_mach
        
        tool_origin = np.array([[tool_pos_x], [tool_pos_y], [tool_pos_z]])

        # B. Calculate Vector from Tool Origin to Every Voxel
        # V_vec = P_voxel - P_tool
        # Use broadcasting
        V_vec = points_lens_frame - tool_origin
        
        # C. Project onto Tool Axis (Calculate 'h')
        # Since the tool axis also rotates with the frame relative to the lens?
        # WAIT: The "tilt toward main axis" constraint means the tilt direction 
        # rotates WITH the tool's angular position.
        # So the tool axis vector must also be rotated by -theta.
        
        # Rotated Tool Axis Vector
        axis_rot_x = tool_axis_vec[0] * cos_t - tool_axis_vec[1] * sin_t
        axis_rot_y = tool_axis_vec[0] * sin_t + tool_axis_vec[1] * cos_t
        axis_rot_z = tool_axis_vec[2]
        current_tool_axis = np.array([[axis_rot_x], [axis_rot_y], [axis_rot_z]])

        # Dot product: h = V . Axis
        h_vals = (V_vec[0,:] * current_tool_axis[0] + 
                  V_vec[1,:] * current_tool_axis[1] + 
                  V_vec[2,:] * current_tool_axis[2])
        
        # D. Calculate Radial Distance from Tool Axis ('d')
        # d^2 = |V|^2 - h^2
        dist_sq = (V_vec[0,:]**2 + V_vec[1,:]**2 + V_vec[2,:]**2)
        d_vals = np.sqrt(np.maximum(0, dist_sq - h_vals**2))
        
        # --- Profile Check ---
        
        # Adjust 'h' based on wheel offsets
        # The profile is defined relative to the Cutting Edge center.
        # h_vals is distance from the Stack Base along the axis.
        # We need h relative to the specific wheel's cutting center.
        
        # Formula: h_profile = h_measured - (stack_offset + cutting_z_relative)
        # Note: Check your specific datum definitions.
        # Usually stack_offset is base-to-wheel-origin.
        # cutting_z_relative is wheel-origin-to-cutting-edge.
        
        eff_h = h_vals - (active_wheel.stack_z_offset + active_wheel.cutting_z_relative)
        
        # Get allowed radius at this height from profile
        # This returns the Z-offset from the profile (e.g., -1.5)
        prof_z_offsets = profile_funcs[active_wheel.tool_id](eff_h)
        print(eff_h[12], prof_z_offsets[12])
        
        # Calculate the actual physical radius of the tool surface at this height
        # Surface_Radius = Cutting_Radius + Profile_Z_Offset
        tool_surface_radii = active_wheel.cutting_radius + prof_z_offsets

        # print(d_vals[12], tool_surface_radii[12], d_vals[12] - tool_surface_radii[12])
        
        # Check Collision: If voxel distance < tool surface radius, it is cut
        # Use a mask to update only valid cuts
        cut_mask = d_vals - tool_surface_radii
        cut_mask = np.clip(cut_mask, a_min=-0.1, a_max=0.1)
        cut_mask = (1 - cut_mask/0.1)/2*(time_length - t + 0.5)

        # print((cut_mask > 400).sum())
        
        # Reshape mask to 3D grid
        cut_mask_3d = cut_mask.reshape(voxels.shape)
        
        # Update Death Time
        # We use minimum: if it was already cut at t=5, and now t=10, keep 5.
        # But we only update where cut_mask is True.
        
        # Create a temporary array for this step's time
        current_step_times = np.full(voxels.shape, 1000, dtype=np.float32)
        current_step_times = current_step_times - cut_mask_3d
        
        death_times = np.minimum(death_times, current_step_times)

    return death_times

def generate_machined_lens_volume(
    front_radius,
    back_radius,
    center_thickness,
    diameter_mm,
    tool_path,
    tool_stack=TOOL_STACK,
    resolution=0.5
) -> LensVolumeData:
    """
    1. Generates the initial lens blank volume.
    2. Simulates the machining process based on tool path.
    3. Returns a LensVolumeData object ready for VTK.
    """
    
    # --- PART 1: Generate Initial Blank ---
    # We use your existing logic to get the starting "Puck"
    blank_data = generate_lens_volume(
        front_radius, back_radius, center_thickness, diameter_mm, resolution
    )
    
    # Reshape the flat scalars into a 3D grid for spatial math
    # Dimensions: [X, Y, Z] -> Numpy shape: (Z, Y, X)
    nx, ny, nz = blank_data.dimensions
    voxels = np.array(blank_data.scalars, dtype=np.float32).reshape((nz, ny, nx))
    
    # --- PART 2: Machining (SDF Subtraction) ---
    # We use the voxel grid from the blank as the starting material
    # The compute_voxel_death_times function will modify these densities
    machined_voxels = compute_voxel_death_times(
        voxels=voxels,
        voxel_res=resolution,
        tool_path=tool_path,
        tool_stack=tool_stack
    )
    
    # --- PART 3: Return as LensVolumeData ---
    return LensVolumeData(
        dimensions=blank_data.dimensions,
        spacing=blank_data.spacing,
        origin=blank_data.origin,
        scalars=machined_voxels.flatten().tolist()
    )