"""
Integration Guide: Using Roughing Results in Path Generation

This shows how the existing roughing generation system flows into
the new movement path generation system.
"""

# WORKFLOW DIAGRAM:
#
# 1. User inputs roughing parameters (method, step, speed)
#    ↓ [roughing_logic.py: manage_roughing_passes]
#
# 2. Store roughing configuration
#    ↓ [store-roughing-data]
#
# 3. User clicks "Update Roughing"
#    ↓ [roughing_logic.py: update_roughing_volumes]
#
# 4. Generate roughing operations with mesh calculation
#    ↓ [core/geometric/roughing_generation.py: generate_roughing_operations]
#    ↓ [RoughingPassData]
#
# 5. Store results (volume, duration, radii, mesh)
#    ↓ [store-roughing-results]
#
# 6. User clicks "Generate Toolpaths"
#    ↓ [btn-gen-path]
#
# 7. NEW: Generate complete movement paths
#    ↓ [simulation_logic.py: generate_path]
#    ↓ [core/cam/movement_path.py: generate_complete_lens_path]
#
# 8. Store full paths with timing
#    ↓ [store-simulation-path] (now includes 'time' array)
#
# 9. Animate using time-based playback
#    ↓ [simulation_logic.py: render_simulation_frame + clientside callback]
#    ↓ [3D simulation view]


# DATA FLOW EXAMPLES:

# Example 1: From Roughing Results to Path Generation
# ===================================================

def example_flow():
    import numpy as np
    from core.models.roughing import RoughingPassData, RoughingSettings
    from core.cam.movement_path import generate_complete_lens_path
    from core.machine_config import load_machine_config_cached
    
    # --- STEP 1: Roughing results come from store-roughing-results ---
    # This is already computed by roughing_logic.update_roughing_volumes()
    
    roughing_results = [
        {
            'pass_index': 1,
            'radii': [40.0, 40.1, 40.2, ...],  # First pass contour
            'volume': 125.45,                   # mm^3 removed
            'duration': 15.0,                   # seconds per revolution
            'mesh': {...}                       # 3D mesh data
        },
        {
            'pass_index': 2,
            'radii': [42.0, 42.1, 42.2, ...],  # Second pass contour
            'volume': 89.23,
            'duration': 12.0,
            'mesh': {...}
        },
    ]
    
    # --- STEP 2: Extract data for movement path generation ---
    roughing_passes = []
    for result in roughing_results:
        roughing_passes.append({
            'radii': np.array(result['radii']),
            'z_map': np.zeros(len(result['radii'])),  # TODO: Extract from mesh
            'speed_s_per_rev': result['duration']      # This is the timing!
        })
    
    # --- STEP 3: Get final contour from OMA job/bevel data ---
    # This comes from store-mesh-cache -> bevel_data
    
    final_radii = np.array([45.0, 45.1, 45.2, ...])  # Target lens shape
    z_map = np.zeros_like(final_radii)
    
    # --- STEP 4: Generate complete movement path ---
    machine = load_machine_config_cached()
    
    paths = generate_complete_lens_path(
        roughing_passes=roughing_passes,
        final_radii=final_radii,
        z_map=z_map,
        machine_config=machine,
        xyz_feedrate=50.0  # mm/sec
    )
    
    # --- STEP 5: Store complete paths with timing ---
    # This goes to store-simulation-path
    
    complete_path = paths['complete']
    x, z, theta, time = complete_path.get_full_path()
    
    simulation_path_data = {
        "x": x.tolist(),
        "z": z.tolist(),
        "theta": theta.tolist(),
        "time": time.tolist(),           # NEW: Include timing!
        "total_frames": len(x)
    }
    
    return simulation_path_data


# Example 2: Roughing Speed Drives Path Timing
# ============================================

def speed_timing_relationship():
    """
    Demonstrates how the 'duration' field from roughing results
    becomes 'speed_s_per_rev' in the path generation.
    """
    
    # From roughing_logic.update_roughing_volumes():
    # 
    # RoughingPassData contains:
    #   duration: float = estimated time
    #
    # This gets stored as:
    #   result['duration']
    #
    # Which becomes:
    #   pass_data['speed_s_per_rev']
    #
    # Which drives timing in movement_path.py:
    #   total_time = revolutions * speed_s_per_rev
    #   time = np.linspace(0, total_time, len(x))
    
    import numpy as np
    from core.cam.movement_path import _generate_cutting_path
    
    kinematics = {
        'theta_machine_deg': np.linspace(0, 360, 360),
        'x_machine': np.random.rand(360) * 5,
        'z_machine': np.random.rand(360) * 5
    }
    
    # Speed controls timing
    speed_s_per_rev = 10.0  # 10 seconds per full revolution
    
    step = _generate_cutting_path(
        kinematics=kinematics,
        wheel_x=100.0,
        wheel_z=-150.0,
        speed_s_per_rev=speed_s_per_rev,
        operation_type='roughing'
    )
    
    # Result has timing array that respects the speed
    print(f"360° cut at {speed_s_per_rev}s/rev:")
    print(f"  Duration: {step.time[-1]:.2f} seconds")
    print(f"  Frames: {step.total_frames}")
    print(f"  First few times: {step.time[:5]}")


# Example 3: Multiple Passes, Sequential Timing
# =============================================

def multiple_passes_timing():
    """
    Shows how multiple roughing passes get stitched with proper timing.
    """
    
    import numpy as np
    from core.cam.movement_path import generate_full_roughing_path
    from core.machine_config import load_machine_config_cached
    
    # Three passes with different speeds
    roughing_passes = [
        {
            'radii': np.full(360, 40.0),
            'z_map': np.zeros(360),
            'speed_s_per_rev': 15.0  # Fast first pass
        },
        {
            'radii': np.full(360, 42.0),
            'z_map': np.zeros(360),
            'speed_s_per_rev': 12.0  # Medium second pass
        },
        {
            'radii': np.full(360, 44.0),
            'z_map': np.zeros(360),
            'speed_s_per_rev': 10.0  # Slow finishing pass
        },
    ]
    
    machine = load_machine_config_cached()
    wheel = machine.wheels[0]
    
    path = generate_full_roughing_path(
        roughing_passes=roughing_passes,
        tool_radius=wheel.cutting_radius,
        tilt_angle_deg=machine.tilt_angle_deg,
        wheel_x=100.0,
        wheel_z=-150.0,
        xyz_feedrate=50.0
    )
    
    # Each pass appears as a step in the path
    print("Step breakdown:")
    cumulative_time = 0.0
    for i, step in enumerate(path.steps):
        step_duration = step.time[-1] if len(step.time) > 0 else 0
        print(f"  {i}: {step.operation_type:10s} - {step.total_frames:4d} frames, {step_duration:7.2f}s, cumsum: {cumulative_time + step_duration:7.2f}s")
        cumulative_time += step_duration


# Example 4: Playback - Time-Based Animation
# ==========================================

def animation_playback():
    """
    How to use the generated path for animation playback.
    """
    
    from core.cam.movement_path import MovementPath, OperationStep
    import numpy as np
    
    # Create a simple path
    step = OperationStep(
        operation_type='roughing',
        x=np.linspace(100, 110, 100),
        z=np.linspace(-150, -140, 100),
        theta=np.linspace(0, 360, 100),
        time=np.linspace(0, 10, 100),  # 10 second operation
        total_frames=100
    )
    
    path = MovementPath(steps=[step])
    
    # Animation loop - query path at specific times
    print("Animation playback (time-based):")
    
    # 30 Hz playback
    fps = 30
    frame_time = 1.0 / fps
    
    current_time = 0.0
    total_duration = 10.0
    
    frame_count = 0
    while current_time <= total_duration:
        x, z, theta = path.get_frame_at_time(current_time)
        
        if frame_count % 30 == 0:  # Print every 1 second
            print(f"  Frame {frame_count:3d} @ t={current_time:6.3f}s: X={x:7.2f}, Z={z:7.2f}, Theta={theta:7.2f}°")
        
        current_time += frame_time
        frame_count += 1
    
    print(f"  Total frames: {frame_count}")


if __name__ == "__main__":
    print("Integration Guide Examples\n")
    print("=" * 70)
    
    print("\n1. Data Flow from Roughing to Paths:")
    print("-" * 70)
    result = example_flow()
    print(f"Generated path with {result['total_frames']} frames")
    print(f"Duration: {result['time'][-1]:.2f} seconds")
    
    print("\n2. Speed-Timing Relationship:")
    print("-" * 70)
    speed_timing_relationship()
    
    print("\n3. Multiple Passes Sequential Timing:")
    print("-" * 70)
    multiple_passes_timing()
    
    print("\n4. Animation Playback:")
    print("-" * 70)
    animation_playback()
    
    print("\n" + "=" * 70)
    print("Integration examples completed!")
