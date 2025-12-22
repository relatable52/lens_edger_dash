"""
Example: Using the Movement Path Generation System

This demonstrates how to use the beveling and roughing path generation
with proper timing for playback and machine simulation.
"""

import numpy as np
from core.cam.movement_path import (
    generate_full_roughing_path,
    generate_full_beveling_path,
    generate_complete_lens_path,
    MovementPath
)
from core.machine_config import load_machine_config_cached


def example_roughing_with_timing():
    """
    Generate a complete roughing sequence with multiple passes and timing.
    """
    # Define roughing passes
    # Each pass represents one contour to remove
    roughing_passes = [
        {
            'radii': np.array([40.0, 40.1, 40.2, 40.1, 40.0]),  # First pass contour
            'z_map': np.zeros(5),
            'speed_s_per_rev': 15.0  # 15 seconds per revolution
        },
        {
            'radii': np.array([42.0, 42.1, 42.2, 42.1, 42.0]),  # Second pass
            'z_map': np.zeros(5),
            'speed_s_per_rev': 12.0
        },
    ]
    
    machine = load_machine_config_cached()
    roughing_wheel = machine.wheels[0]
    
    # Generate roughing path
    path = generate_full_roughing_path(
        roughing_passes=roughing_passes,
        tool_radius=roughing_wheel.cutting_radius,
        tilt_angle_deg=machine.tilt_angle_deg,
        wheel_x=100.0,
        wheel_z=-150.0,
        home_x=-50.0,
        home_z=0.0,
        xyz_feedrate=50.0
    )
    
    # Extract full path with timing
    x, z, theta, time = path.get_full_path()
    
    print(f"Roughing Path:")
    print(f"  Total frames: {len(x)}")
    print(f"  Total duration: {time[-1]:.2f} seconds")
    print(f"  Number of passes: {len(roughing_passes)}")
    
    # Get position at specific time
    x_at_10s, z_at_10s, theta_at_10s = path.get_frame_at_time(10.0)
    print(f"  Position at t=10s: X={x_at_10s:.2f}, Z={z_at_10s:.2f}, Theta={theta_at_10s:.2f}°")
    
    return path


def example_beveling_operation():
    """
    Generate a beveling operation for the final contour.
    """
    # Final contour shape
    n_points = 360
    angles = np.linspace(0, 2*np.pi, n_points, endpoint=False)
    final_radii = 45.0 + 2.0 * np.cos(8 * angles)  # Wavy contour
    z_map = 0.5 * np.sin(angles)  # Some curvature
    
    machine = load_machine_config_cached()
    bevel_wheel = machine.wheels[1] if len(machine.wheels) > 1 else machine.wheels[0]
    
    # Generate beveling path
    path = generate_full_beveling_path(
        final_radii=final_radii,
        z_map=z_map,
        tool_radius=bevel_wheel.cutting_radius,
        tilt_angle_deg=machine.tilt_angle_deg,
        wheel_x=100.0,
        wheel_z=-150.0,
        speed_s_per_rev=10.0,
        home_x=-50.0,
        home_z=0.0,
        xyz_feedrate=50.0
    )
    
    x, z, theta, time = path.get_full_path()
    
    print(f"\nBeveling Path:")
    print(f"  Total frames: {len(x)}")
    print(f"  Total duration: {time[-1]:.2f} seconds")
    print(f"  Contour points: {len(final_radii)}")
    
    return path


def example_complete_workflow():
    """
    Generate complete path combining roughing AND beveling.
    This is the real-world workflow.
    """
    # Roughing passes (all contours to remove material)
    roughing_passes = [
        {
            'radii': np.array([40.0] * 360),
            'z_map': np.zeros(360),
            'speed_s_per_rev': 15.0
        },
        {
            'radii': np.array([42.0] * 360),
            'z_map': np.zeros(360),
            'speed_s_per_rev': 12.0
        },
        {
            'radii': np.array([44.0] * 360),
            'z_map': np.zeros(360),
            'speed_s_per_rev': 10.0
        },
    ]
    
    # Final contour (what we want to achieve)
    final_radii = 45.0 * np.ones(360)
    z_map = np.zeros(360)
    
    machine = load_machine_config_cached()
    
    # Generate complete path
    paths = generate_complete_lens_path(
        roughing_passes=roughing_passes,
        final_radii=final_radii,
        z_map=z_map,
        machine_config=machine,
        xyz_feedrate=50.0
    )
    
    complete_path = paths['complete']
    x, z, theta, time = complete_path.get_full_path()
    
    print(f"\nComplete Workflow (Roughing + Beveling):")
    print(f"  Total frames: {len(x)}")
    print(f"  Total duration: {time[-1]:.2f} seconds")
    print(f"  Operations:")
    for step in complete_path.steps:
        if step.operation_type != 'home':
            print(f"    - {step.operation_type} (pass {step.pass_index}): {step.total_frames} frames, {step.feed_rate_s_per_rev:.1f}s/rev")
    
    # Demonstrate time-based frame selection for animation
    print(f"\n  Frame positions at key times:")
    for t in [0, 5.0, 10.0, 15.0, time[-1]]:
        if t <= time[-1]:
            x_pos, z_pos, theta_pos = complete_path.get_frame_at_time(t)
            print(f"    t={t:6.2f}s: X={x_pos:7.2f}, Z={z_pos:7.2f}, Theta={theta_pos:7.2f}°")


def example_time_based_playback():
    """
    Demonstrate how to use timing for animation/playback.
    """
    roughing_passes = [
        {
            'radii': np.array([40.0] * 180),
            'z_map': np.zeros(180),
            'speed_s_per_rev': 10.0
        },
    ]
    
    final_radii = 45.0 * np.ones(180)
    z_map = np.zeros(180)
    
    machine = load_machine_config_cached()
    
    paths = generate_complete_lens_path(
        roughing_passes=roughing_passes,
        final_radii=final_radii,
        z_map=z_map,
        machine_config=machine,
        xyz_feedrate=50.0
    )
    
    complete_path = paths['complete']
    x, z, theta, time = complete_path.get_full_path()
    
    # Simulate animation loop - 30 Hz playback
    print(f"\nTime-Based Playback (first 5 seconds at 30 Hz):")
    frame_time = 1.0 / 30.0  # 30 FPS
    current_time = 0.0
    
    while current_time <= min(5.0, time[-1]):
        x_pos, z_pos, theta_pos = complete_path.get_frame_at_time(current_time)
        print(f"  {current_time:.3f}s -> X={x_pos:7.2f}, Z={z_pos:7.2f}, Theta={theta_pos:7.2f}°")
        current_time += frame_time


if __name__ == "__main__":
    print("=" * 70)
    print("Movement Path Generation Examples")
    print("=" * 70)
    
    example_roughing_with_timing()
    example_beveling_operation()
    example_complete_workflow()
    example_time_based_playback()
    
    print("\n" + "=" * 70)
    print("Examples completed successfully!")
    print("=" * 70)
