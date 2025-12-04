import sys
import os

# --- Path Fix ---
# Add the parent directory (project root) to sys.path
# This allows imports like 'from core...' to work when running this script directly
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import numpy as np
import plotly.graph_objects as go
# Updated import to match your 'core' folder structure
from core.cam.kinematics import solve_lens_kinematics_robust

def generate_dummy_lens_data(n_points=360):
    """ Creates a 'Rounded Square' shape for testing sharp corners. """
    angles = np.linspace(0, 2*np.pi, n_points, endpoint=False)
    
    # Superellipse formula for a rect-like shape
    # |x/a|^n + |y/b|^n = 1
    a, b = 25, 15
    n = 4 
    
    # Convert parametric superellipse to polar r(theta)
    # This is a bit tricky, simpler way:
    # r = ( |cos(t)/a|^n + |sin(t)/b|^n )^(-1/n)
    denom = (np.abs(np.cos(angles)/a)**n + np.abs(np.sin(angles)/b)**n)
    radii = denom**(-1.0/n)
    
    # Dummy Z map: Saddle shape
    z_map = 5 * np.sin(2 * angles)
    
    return radii, z_map, angles

def test_kinematics_animation():
    # 1. Setup Parameters
    radii, z_map, lens_angles = generate_dummy_lens_data()
    
    TOOL_RADIUS = 50.0
    TOOL_TILT = 30.0 # Steep tilt to make the ellipse effect obvious
    TOOL_Z_OFFSET = 100
    
    # 2. Run the Solver
    print("Running Kinematics Solver...")
    kinematics = solve_lens_kinematics_robust(
        radii, z_map, TOOL_RADIUS, TOOL_TILT, TOOL_Z_OFFSET
    )
    
    theta_machine_deg = kinematics['theta_machine_deg']
    x_machine = kinematics['x_machine']
    
    print("Generating Animation...")
    
    # 3. Create Animation Frames
    frames = []
    steps = len(theta_machine_deg)
    # Downsample for smoother playback performance (every 5th degree)
    indices = range(0, steps, 5) 
    
    # Pre-calculate Tool Ellipse (Centered at 0,0)
    # Tool profile is ellipse with major=R, minor=R*cos(tilt)
    tool_minor = TOOL_RADIUS * np.cos(np.deg2rad(TOOL_TILT))
    t_angles = np.linspace(0, 2*np.pi, 100)
    tool_x_base = tool_minor * np.cos(t_angles)
    tool_y_base = TOOL_RADIUS * np.sin(t_angles)
    
    for i in indices:
        rot_deg = theta_machine_deg[i]
        rot_rad = np.deg2rad(rot_deg)
        machine_x_pos = x_machine[i]
        
        # A. Rotate Lens (Workpiece)
        # Note: Machine rotates lens CW, so we apply -rot_deg for visualization? 
        # Actually, usually 'theta_machine' defines the spindle position.
        # Let's rotate the lens points by the calculated angle.
        lens_x = radii * np.cos(lens_angles + rot_rad)
        lens_y = radii * np.sin(lens_angles + rot_rad)
        
        # B. Move Tool (Spindle X-Axis)
        # Tool is always at Y=0, X = machine_x_pos
        current_tool_x = tool_x_base + machine_x_pos
        current_tool_y = tool_y_base
        
        frames.append(go.Frame(
            data=[
                # Trace 0: The Lens
                go.Scatter(x=lens_x, y=lens_y, mode='lines', line=dict(color='blue')),
                # Trace 1: The Tool
                go.Scatter(x=current_tool_x, y=current_tool_y, mode='lines', line=dict(color='red')),
                # Trace 2: Tool Center Marker
                go.Scatter(x=[machine_x_pos], y=[0], mode='markers', marker=dict(symbol='x', size=10, color='red'))
            ],
            name=str(i)
        ))

    # 4. Setup Layout & Initial State
    fig = go.Figure(
        data=[
            go.Scatter(x=[], y=[], name="Lens", line=dict(color='blue')),
            go.Scatter(x=[], y=[], name="Tool", line=dict(color='red', width=2)),
            go.Scatter(x=[], y=[], name="Spindle Center", mode='markers')
        ],
        layout=go.Layout(
            title="Kinematics Validation: 2D Cutting Plane",
            xaxis=dict(range=[-50, 150], scaleanchor="y", scaleratio=1),
            yaxis=dict(range=[-60, 60]),
            updatemenus=[{
                "type": "buttons",
                "buttons": [{"label": "Play", "method": "animate", "args": [None]}]
            }]
        ),
        frames=frames
    )
    
    # Initialize with first frame data
    fig.update_traces(
        x=radii * np.cos(lens_angles + np.deg2rad(theta_machine_deg[0])),
        y=radii * np.sin(lens_angles + np.deg2rad(theta_machine_deg[0])),
        selector=0
    )
    
    fig.show()

if __name__ == "__main__":
    test_kinematics_animation()