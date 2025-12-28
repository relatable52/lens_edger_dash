"""
Movement Path Generation

Generates complete machine movement paths for lens edging operations.
Combines multiple operations (roughing passes + beveling) with timing information.

Key Features:
- Generates machine coordinates (X, Z, Theta) for each operation
- Includes timing (speed) for playback synchronization
- Handles transitions between operations with approach/retract sequences
- Supports both roughing (all contours) and beveling (final contour)

Path Structure:
- Home position (spindle retracted, lens far away)
- Approach sequence (lens moves into position, spindle rotates to start angle)
- Operation sequences (cutting along each contour)
- Retract sequence (lens withdraws, spindle returns to home angle)
"""

from dataclasses import dataclass
from typing import List, Dict, Tuple
import numpy as np

from core.cam.kinematics import solve_lens_kinematics_robust


@dataclass
class OperationStep:
    """Single step in the movement path with timing information."""
    operation_type: str  # 'home', 'approach', 'roughing', 'beveling', 'retract'
    pass_index: int = 0  # Which roughing pass (0 for non-roughing)
    x: np.ndarray = None  # Machine X positions (mm)
    z: np.ndarray = None  # Machine Z positions (mm)
    theta: np.ndarray = None  # Machine rotation angles (degrees)
    time: np.ndarray = None  # Cumulative time for each point (seconds)
    speed_mm_per_sec: float = 50.0  # XZ feed rate
    feed_rate_s_per_rev: float = 10.0  # Spindle feed rate
    total_frames: int = 0


@dataclass
class MovementPath:
    """Complete movement path combining all operation steps."""
    steps: List[OperationStep]
    
    def get_full_path(self) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """
        Returns concatenated full path: x, z, theta, time
        
        Returns:
            Tuple of (x, z, theta, time) arrays covering entire operation sequence
        """
        x_list, z_list, theta_list, time_list = [], [], [], []
        cumulative_time = 0.0
        
        for step in self.steps:
            if step.x is not None:
                x_list.append(step.x)
                z_list.append(step.z)
                theta_list.append(step.theta)
                
                # Adjust time offsets
                adjusted_time = step.time + cumulative_time
                time_list.append(adjusted_time)
                cumulative_time = adjusted_time[-1]
        
        return (
            np.concatenate(x_list) if x_list else np.array([]),
            np.concatenate(z_list) if z_list else np.array([]),
            np.concatenate(theta_list) if theta_list else np.array([]),
            np.concatenate(time_list) if time_list else np.array([])
        )
    
    def get_frame_at_time(self, time_sec: float) -> Tuple[float, float, float]:
        """Get (x, z, theta) at specific time."""
        x, z, theta, time = self.get_full_path()
        if len(time) == 0:
            return 0.0, 0.0, 0.0
        
        # Find nearest frame
        idx = np.searchsorted(time, time_sec, side='left')
        idx = np.clip(idx, 0, len(x) - 1)
        return float(x[idx]), float(z[idx]), float(theta[idx])


def _generate_linear_path(
    start: Tuple[float, float, float],
    end: Tuple[float, float, float],
    distance_mm: float,
    speed_mm_per_sec: float = 50.0,
    feed_rate_s_per_rev: float = 10.0,
    operation_type: str = 'approach'
) -> OperationStep:
    """
    Generate linear interpolation path between two points.
    
    Args:
        start: (x, z, theta) starting position
        end: (x, z, theta) ending position
        distance_mm: Euclidean distance for feedrate calculation
        speed_mm_per_sec: XZ plane feedrate
        feed_rate_s_per_rev: Spindle feed rate
        operation_type: Type of operation for identification
        
    Returns:
        OperationStep with interpolated path
    """
    x_start, z_start, theta_start = start
    x_end, z_end, theta_end = end
    
    # Calculate number of frames based on feedrate
    # Use euclidean distance in XZ plane
    if distance_mm > 0:
        duration = distance_mm / speed_mm_per_sec
        n_frames = max(int(duration * 30), 2)  # 30 Hz assumed playback
    else:
        n_frames = 10
    
    # Linear interpolation
    x = np.linspace(x_start, x_end, n_frames)
    z = np.linspace(z_start, z_end, n_frames)
    theta = np.linspace(theta_start, theta_end, n_frames)
    
    # Time array (0 to duration)
    time = np.linspace(0, duration if distance_mm > 0 else 0.1, n_frames)
    
    return OperationStep(
        operation_type=operation_type,
        x=x,
        z=z,
        theta=theta,
        time=time,
        speed_mm_per_sec=speed_mm_per_sec,
        feed_rate_s_per_rev=feed_rate_s_per_rev,
        total_frames=n_frames
    )


def _generate_cutting_path(
    kinematics: Dict,
    wheel_x: float,
    wheel_z: float,
    speed_s_per_rev: float,
    speed_mm_per_sec: float = 50.0,
    operation_type: str = 'roughing',
    pass_index: int = 0
) -> OperationStep:
    """
    Generate cutting path from kinematics solution.
    
    Args:
        kinematics: Output from solve_lens_kinematics_robust (contains theta, x_machine, z_machine)
        wheel_x: Wheel center X position
        wheel_z: Wheel center Z position
        speed_s_per_rev: Spindle feed rate (seconds per revolution)
        speed_mm_per_sec: XZ plane feedrate
        operation_type: Type of operation (e.g., 'roughing', 'beveling')
        pass_index: Which pass (for roughing)
        
    Returns:
        OperationStep with complete cutting path
    """
    if not kinematics or len(kinematics.get('x_machine', [])) == 0:
        return OperationStep(operation_type=operation_type, pass_index=pass_index)
    
    # Convert kinematics to global coordinates
    x_machine = np.array(kinematics['x_machine'])
    z_machine = np.array(kinematics['z_machine'])
    theta_machine = np.array(kinematics['theta_machine_deg'])
    
    x = wheel_x - x_machine
    z = wheel_z + z_machine
    theta = theta_machine
    
    # Calculate timing based on spindle speed
    # One full revolution = speed_s_per_rev seconds
    # We assume the theta values go from 0 to 360 degrees
    max_theta = np.max(theta)
    if max_theta > 0:
        revolutions = max_theta / 360.0
        total_time = revolutions * speed_s_per_rev
    else:
        total_time = len(theta) * speed_s_per_rev / 360.0
    
    # Create time array
    time = np.linspace(0, total_time, len(x))
    
    return OperationStep(
        operation_type=operation_type,
        pass_index=pass_index,
        x=x,
        z=z,
        theta=theta,
        time=time,
        speed_mm_per_sec=speed_mm_per_sec,
        feed_rate_s_per_rev=speed_s_per_rev,
        total_frames=len(x)
    )


def generate_full_roughing_path(
    roughing_passes: List[Dict],
    tool_radius: float,
    tilt_angle_deg: float,
    wheel_x: float,
    wheel_z: float,
    home_x: float = -50.0,
    home_z: float = 0.0,
    approach_distance: float = 50.0,
    xyz_feedrate: float = 50.0
) -> MovementPath:
    """
    Generate complete roughing path for all passes.
    
    Each pass is independently solved for kinematics, then stitched together
    with approach/retract sequences between passes.
    
    Args:
        roughing_passes: List of dicts containing:
            - radii: Final contour radii for this pass (np.ndarray)
            - z_map: Z-height map (np.ndarray)
            - speed_s_per_rev: Spindle feed rate
        tool_radius: Roughing wheel cutting radius
        tilt_angle_deg: Wheel tilt angle
        wheel_x: Wheel center X position
        wheel_z: Wheel center Z position
        home_x: Home position X
        home_z: Home position Z
        approach_distance: Distance for approach phase
        xyz_feedrate: XYZ feedrate in mm/sec
        
    Returns:
        MovementPath with all roughing passes stitched together
    """
    steps = []
    
    if not roughing_passes or len(roughing_passes) == 0:
        return MovementPath(steps)
    
    # 1. HOME POSITION
    steps.append(OperationStep(
        operation_type='home',
        x=np.array([home_x]),
        z=np.array([home_z]),
        theta=np.array([0.0]),
        time=np.array([0.0]),
        total_frames=1
    ))
    
    current_x = home_x
    current_z = home_z
    current_theta = 0.0
    
    # 2. PROCESS EACH ROUGHING PASS
    for pass_index, pass_data in enumerate(roughing_passes):
        radii = np.array(pass_data['radii'])
        z_map = np.array(pass_data['z_map']) if 'z_map' in pass_data else np.zeros_like(radii)
        speed = pass_data.get('speed_s_per_rev', 10.0)
        
        # Solve kinematics for this pass
        kinematics = solve_lens_kinematics_robust(
            radii=radii,
            z_map=z_map,
            tool_radius=tool_radius,
            tool_tilt_angle_deg=tilt_angle_deg
        )
        
        if not kinematics or len(kinematics['x_machine']) == 0:
            continue
        
        # Get start position of this cut
        start_x = wheel_x - kinematics['x_machine'][0]
        start_z = wheel_z + kinematics['z_machine'][0]
        start_theta = kinematics['theta_machine_deg'][0]
        
        # APPROACH to start position
        approach_dist = np.sqrt(
            (start_x - current_x)**2 + (start_z - current_z)**2
        )
        
        steps.append(_generate_linear_path(
            start=(current_x, current_z, current_theta),
            end=(start_x, start_z, start_theta),
            distance_mm=approach_dist,
            speed_mm_per_sec=xyz_feedrate,
            feed_rate_s_per_rev=speed,
            operation_type='approach'
        ))
        
        # CUTTING PASS
        steps.append(_generate_cutting_path(
            kinematics=kinematics,
            wheel_x=wheel_x,
            wheel_z=wheel_z,
            speed_s_per_rev=speed,
            speed_mm_per_sec=xyz_feedrate,
            operation_type='roughing',
            pass_index=pass_index + 1
        ))
        
        # Update current position
        current_x = wheel_x - kinematics['x_machine'][-1]
        current_z = wheel_z + kinematics['z_machine'][-1]
        current_theta = kinematics['theta_machine_deg'][-1]
    
    # 3. RETRACT TO HOME
    retract_dist = np.sqrt((home_x - current_x)**2 + (home_z - current_z)**2)
    steps.append(_generate_linear_path(
        start=(current_x, current_z, current_theta),
        end=(home_x, home_z, 0.0),
        distance_mm=retract_dist,
        speed_mm_per_sec=xyz_feedrate,
        operation_type='retract'
    ))
    
    return MovementPath(steps)


def generate_full_beveling_path(
    final_radii: np.ndarray,
    z_map: np.ndarray,
    tool_radius: float,
    tilt_angle_deg: float,
    wheel_x: float,
    wheel_z: float,
    speed_s_per_rev: float = 10.0,
    home_x: float = -50.0,
    home_z: float = 0.0,
    xyz_feedrate: float = 50.0
) -> MovementPath:
    """
    Generate beveling path for the final contour.
    
    The beveling wheel traces the final lens contour once.
    
    Args:
        final_radii: Final contour radii (np.ndarray)
        z_map: Z-height map (np.ndarray)
        tool_radius: Bevel wheel cutting radius
        tilt_angle_deg: Wheel tilt angle
        wheel_x: Wheel center X position
        wheel_z: Wheel center Z position
        speed_s_per_rev: Spindle feed rate (seconds per revolution)
        home_x: Home position X
        home_z: Home position Z
        xyz_feedrate: XYZ feedrate in mm/sec
        
    Returns:
        MovementPath with beveling operation
    """
    steps = []
    
    # 1. HOME POSITION
    steps.append(OperationStep(
        operation_type='home',
        x=np.array([home_x]),
        z=np.array([home_z]),
        theta=np.array([0.0]),
        time=np.array([0.0]),
        total_frames=1
    ))
    
    # 2. SOLVE KINEMATICS FOR BEVELING
    kinematics = solve_lens_kinematics_robust(
        radii=final_radii,
        z_map=z_map,
        tool_radius=tool_radius,
        tool_tilt_angle_deg=tilt_angle_deg
    )
    
    if not kinematics or len(kinematics['x_machine']) == 0:
        return MovementPath(steps)
    
    # Get start position
    start_x = wheel_x - kinematics['x_machine'][0]
    start_z = wheel_z + kinematics['z_machine'][0]
    start_theta = kinematics['theta_machine_deg'][0]
    
    # 3. APPROACH
    approach_dist = np.sqrt(start_x**2 + start_z**2)
    if approach_dist > 0.1:
        steps.append(_generate_linear_path(
            start=(home_x, home_z, 0.0),
            end=(start_x, start_z, start_theta),
            distance_mm=approach_dist,
            speed_mm_per_sec=xyz_feedrate,
            feed_rate_s_per_rev=speed_s_per_rev,
            operation_type='approach'
        ))
    
    # 4. CUTTING PASS (beveling)
    steps.append(_generate_cutting_path(
        kinematics=kinematics,
        wheel_x=wheel_x,
        wheel_z=wheel_z,
        speed_s_per_rev=speed_s_per_rev,
        speed_mm_per_sec=xyz_feedrate,
        operation_type='beveling',
        pass_index=1
    ))
    
    # 5. RETRACT
    end_x = wheel_x - kinematics['x_machine'][-1]
    end_z = wheel_z + kinematics['z_machine'][-1]
    end_theta = kinematics['theta_machine_deg'][-1]
    
    retract_dist = np.sqrt(
        (home_x - end_x)**2 + (home_z - end_z)**2
    )
    if retract_dist > 0.1:
        steps.append(_generate_linear_path(
            start=(end_x, end_z, end_theta),
            end=(home_x, home_z, 0.0),
            distance_mm=retract_dist,
            speed_mm_per_sec=xyz_feedrate,
            operation_type='retract'
        ))
    
    return MovementPath(steps)


def generate_complete_lens_path(
    roughing_passes: List[Dict],
    final_radii: np.ndarray,
    z_map: np.ndarray,
    machine_config,
    roughing_speed_override: float = None,
    beveling_speed_override: float = None,
    xyz_feedrate: float = 50.0
) -> Dict[str, MovementPath]:
    """
    Generate complete path for entire lens edging operation.
    
    Combines roughing and beveling into one complete operation sequence.
    
    Args:
        roughing_passes: List of roughing pass data dicts
        final_radii: Final contour radii
        z_map: Z-height map
        machine_config: ToolStack instance with machine configuration
        roughing_speed_override: Override default roughing speed (optional)
        beveling_speed_override: Override default beveling speed (optional)
        xyz_feedrate: XYZ feedrate in mm/sec
        
    Returns:
        Dict with keys 'roughing', 'beveling', 'complete'
    """
    # Extract machine parameters
    roughing_wheel = machine_config.wheels[0]  # First wheel is roughing
    bevel_wheel = machine_config.wheels[1] if len(machine_config.wheels) > 1 else None
    
    tilt_rad = np.deg2rad(machine_config.tilt_angle_deg)
    sin_t = np.sin(tilt_rad)
    cos_t = np.cos(tilt_rad)
    
    # Calculate wheel positions
    z_offset_rough = roughing_wheel.stack_z_offset + roughing_wheel.cutting_z_relative
    wheel_x_rough = machine_config.base_position[0] - (z_offset_rough * sin_t)
    wheel_z_rough = machine_config.base_position[2] + (z_offset_rough * cos_t)
    
    # Generate roughing path
    roughing_path = generate_full_roughing_path(
        roughing_passes=roughing_passes,
        tool_radius=roughing_wheel.cutting_radius,
        tilt_angle_deg=machine_config.tilt_angle_deg,
        wheel_x=wheel_x_rough,
        wheel_z=wheel_z_rough,
        xyz_feedrate=xyz_feedrate
    )
    
    # Generate beveling path
    beveling_path = None
    if bevel_wheel is not None:
        z_offset_bevel = bevel_wheel.stack_z_offset + bevel_wheel.cutting_z_relative
        wheel_x_bevel = machine_config.base_position[0] - (z_offset_bevel * sin_t)
        wheel_z_bevel = machine_config.base_position[2] + (z_offset_bevel * cos_t)
        
        beveling_path = generate_full_beveling_path(
            final_radii=final_radii,
            z_map=z_map,
            tool_radius=bevel_wheel.cutting_radius,
            tilt_angle_deg=machine_config.tilt_angle_deg,
            wheel_x=wheel_x_bevel,
            wheel_z=wheel_z_bevel,
            speed_s_per_rev=beveling_speed_override or 10.0,
            xyz_feedrate=xyz_feedrate
        )
    
    # Combine into complete path
    complete_steps = roughing_path.steps.copy()
    if beveling_path:
        # Skip the home position from beveling path (already at home from roughing)
        complete_steps.extend(beveling_path.steps[1:])
    
    complete_path = MovementPath(complete_steps)
    
    return {
        'roughing': roughing_path,
        'beveling': beveling_path,
        'complete': complete_path
    }
