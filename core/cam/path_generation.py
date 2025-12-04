import numpy as np

def generate_full_simulation_path(kinematics, wheel_x, wheel_z, home_x=150.0, home_z=0.0, approach_steps=30):
    """
    Stitches the 'Home -> Approach -> Cut' trajectory for simulation.
    
    Args:
        kinematics (dict): Result from solve_lens_kinematics_robust.
        home_x (float): Resting position of the spindle X-axis.
        home_z (float): Resting position of the spindle Z-axis.
        approach_steps (int): Number of frames for the approach animation.
        
    Returns:
        dict: Arrays for x, z, theta, and total_frames.
    """
    # 1. Get Start Position of the actual cut
    if not kinematics or len(kinematics['x_machine']) == 0:
        return {}

    start_x = wheel_x - kinematics['x_machine'][0] 
    start_z = wheel_z + kinematics['z_machine'][0]
    start_theta = kinematics['theta_machine_deg'][0]
    
    # 2. Generate Linear Interpolation from Home to Start
    # Home: Lens is far away (X=150), usually Z=0 or aligned
    approach_x = np.linspace(home_x, start_x, approach_steps)
    approach_z = np.linspace(home_z, start_z, approach_steps)
    approach_theta = np.linspace(0, start_theta, approach_steps) 
    
    # 3. Concatenate with the cutting path
    full_x = np.concatenate([approach_x, wheel_x - kinematics['x_machine']])
    full_z = np.concatenate([approach_z, wheel_z + kinematics['z_machine']])
    full_theta = np.concatenate([approach_theta, kinematics['theta_machine_deg']])
    
    return {
        "x": full_x,
        "z": full_z,
        "theta": full_theta,
        "total_frames": len(full_x)
    }