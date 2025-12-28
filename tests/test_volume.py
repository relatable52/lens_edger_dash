import dash
from dash import html, dcc, callback, Input, Output
import dash_vtk
from dash_vtk.utils import to_volume_state
import vtk
from vtkmodules.util import numpy_support
import numpy as np

# --- 1. CONFIGURATION ---
LENS_PARAMS = {
    "R1": 500, "R2": 100,
    "diameter": 70, "thickness": 5,
    "resolution": 0.5, # mm/voxel (Lower = higher quality)
    "padding": 5
}
TOOL_PARAMS = {"radius": 3.0, "depth": 1.5}
MAX_TIME_STEPS = 500
MATERIAL_OFFSET = 2000 # Value offset for uncut material

# --- 2. FAST GENERATION WITH NUMPY (Vectorized) ---
def generate_lens_volume():
    """
    Generates the lens volume and 'burns' the tool path into it
    using fast NumPy vectorization instead of loops.
    """
    # Calculate Dimensions
    xy_size = LENS_PARAMS["diameter"] + LENS_PARAMS["padding"]
    z_size = LENS_PARAMS["thickness"] + LENS_PARAMS["padding"]
    
    dim_x = int(np.ceil(xy_size / LENS_PARAMS["resolution"]))
    dim_y = int(np.ceil(xy_size / LENS_PARAMS["resolution"]))
    dim_z = int(np.ceil(z_size / LENS_PARAMS["resolution"]))
    
    spacing = (LENS_PARAMS["resolution"], LENS_PARAMS["resolution"], LENS_PARAMS["resolution"])
    origin = (-(dim_x*spacing[0])/2, -(dim_y*spacing[1])/2, -(dim_z*spacing[2])/2)

    # Create Coordinate Grids (3D Arrays)
    x = np.linspace(origin[0], origin[0] + (dim_x-1)*spacing[0], dim_x)
    y = np.linspace(origin[1], origin[1] + (dim_y-1)*spacing[1], dim_y)
    z = np.linspace(origin[2], origin[2] + (dim_z-1)*spacing[2], dim_z)
    
    # Broadcasting to create 3D coordinate grids
    Z, Y, X = np.meshgrid(z, y, x, indexing='ij')

    # --- A. LENS SHAPE (SDF) ---
    # Cylinder Distance (XY plane)
    dist_cyl = np.sqrt(X**2 + Y**2) - (LENS_PARAMS["diameter"] / 2)
    
    # Sphere 1 Distance (Front)
    z_c1 = LENS_PARAMS["R1"]
    dist_s1 = np.sqrt(X**2 + Y**2 + (Z - z_c1)**2) - LENS_PARAMS["R1"]
    
    # Sphere 2 Distance (Back) - Note inversion logic for cutout
    z_c2 = (LENS_PARAMS["thickness"] / 2) + LENS_PARAMS["R2"]
    dist_s2 = LENS_PARAMS["R2"] - np.sqrt(X**2 + Y**2 + (Z - z_c2)**2)
    
    # Intersection (Max)
    max_dist = np.maximum(dist_cyl, np.maximum(dist_s1, dist_s2))
    
    # Soft Edge Mask (0.0 to 100.0)
    smooth_edge = LENS_PARAMS["resolution"] * 0.8
    # Initialize with Air (0)
    volume_data = np.zeros_like(max_dist, dtype=np.float32)
    
    # Create Mask for inside
    mask_inside = max_dist < -smooth_edge
    mask_edge = (max_dist >= -smooth_edge) & (max_dist <= smooth_edge)
    
    # Set Uncut Material (Offset + Density)
    volume_data[mask_inside] = MATERIAL_OFFSET + 100.0
    
    # Edge interpolation
    t = (max_dist[mask_edge] + smooth_edge) / (2 * smooth_edge)
    volume_data[mask_edge] = MATERIAL_OFFSET + (100.0 * (1.0 - t))

    # --- B. TOOL PATH SIMULATION ---
    # Generate Path (Spiral)
    t_vals = np.linspace(0, 1, MAX_TIME_STEPS)
    max_r = (LENS_PARAMS["diameter"] / 2) + 2
    
    # We simulate the cut by creating "Cut Values" (1 to MAX_TIME_STEPS)
    # Since checking every voxel against every path point is expensive (N*M),
    # we do a simplified rasterization or distance check.
    # For a perfect simulation, we iterate path points.
    
    # To keep Python startup fast, we'll do a simplified loop over the path
    # and use array slicing (much faster than voxel iteration).
    
    print("Simulating cuts...")
    tool_r_sq = TOOL_PARAMS["radius"]**2
    tool_z_depth = (LENS_PARAMS["thickness"]/2) - TOOL_PARAMS["depth"]
    
    # Flatten grids for KD-Tree or simple masking? 
    # Let's use simple masking on the relevant slice.
    
    for i, t in enumerate(t_vals):
        time_step = i + 1
        # Path Math
        r = max_r * (1 - t)
        theta = 6 * 2 * np.pi * t # 6 revolutions
        tx = r * np.cos(theta)
        ty = r * np.sin(theta)
        
        # Find index bounds for the tool (Bounding box)
        ix_min = int(np.clip((tx - TOOL_PARAMS["radius"] - origin[0])/spacing[0], 0, dim_x))
        ix_max = int(np.clip((tx + TOOL_PARAMS["radius"] - origin[0])/spacing[0], 0, dim_x))
        iy_min = int(np.clip((ty - TOOL_PARAMS["radius"] - origin[1])/spacing[1], 0, dim_y))
        iy_max = int(np.clip((ty + TOOL_PARAMS["radius"] - origin[1])/spacing[1], 0, dim_y))
        
        # Slice the volume (Z, Y, X)
        # We assume tool cuts everything ABOVE tool_z_depth
        iz_min = int(np.clip((tool_z_depth - origin[2])/spacing[2], 0, dim_z))
        
        if ix_max <= ix_min or iy_max <= iy_min: continue

        # Extract local coordinates
        local_X = X[iz_min:, iy_min:iy_max, ix_min:ix_max]
        local_Y = Y[iz_min:, iy_min:iy_max, ix_min:ix_max]
        local_Data = volume_data[iz_min:, iy_min:iy_max, ix_min:ix_max]
        
        # Calculate radial distance
        dist_sq = (local_X - tx)**2 + (local_Y - ty)**2
        
        # Mask: Inside tool AND Is Material ( > 0) AND Is not already cut earlier
        # Note: If it's already cut (value < time_step), we leave it.
        # If it's Uncut Material (value > MATERIAL_OFFSET), we cut it.
        cut_mask = (dist_sq <= tool_r_sq) & (local_Data > 0) & (local_Data > time_step)
        
        # Update values to the current timestamp
        local_Data[cut_mask] = time_step

    # --- C. CONVERT TO VTK ---
    vtk_data = vtk.vtkImageData()
    vtk_data.SetDimensions(dim_x, dim_y, dim_z)
    vtk_data.SetSpacing(spacing)
    vtk_data.SetOrigin(origin)
    
    # Flatten and wrap
    flat_data = np.ascontiguousarray(volume_data.flatten())
    vtk_array = numpy_support.numpy_to_vtk(num_array=flat_data, deep=True, array_type=vtk.VTK_FLOAT)
    vtk_array.SetName("Scalars")
    vtk_data.GetPointData().SetScalars(vtk_array)
    
    return vtk_data

# --- 3. INITIALIZE APP & DATA ---
print("Generating Volume...")
vtk_image = generate_lens_volume()
volume_state = to_volume_state(vtk_image) # Converts to format Dash understands
print("Volume Ready.")

app = dash.Dash(__name__)

# --- 4. LAYOUT ---
app.layout = html.Div([
    html.Div([
        html.H3("Lens Machining Simulation"),
        html.Label("Time Step:"),
        dcc.Slider(
            id='time-slider',
            min=0, max=MAX_TIME_STEPS, step=5, value=0,
            marks={0: 'Start', MAX_TIME_STEPS: 'End'},
            tooltip={"placement": "bottom", "always_visible": True}
        ),
    ], style={'width': '30%', 'padding': '20px', 'position': 'absolute', 'zIndex': '100', 'backgroundColor': 'rgba(255,255,255,0.8)'}),
    
    html.Div(
        dash_vtk.View(
            id="vtk-view",
            background=[0.1, 0.1, 0.1], # Dark background
            children=[
                dash_vtk.Volume(
                    state=volume_state,
                    children=[
                        dash_vtk.VolumeRepresentation(
                            id="vol-rep",
                            colorDataRange=[0, MATERIAL_OFFSET + 100],
                            property={
                                "shade": True,
                                "ambient": 0.3,
                                "diffuse": 0.8,
                                "specular": 0.2,
                                "specularPower": 10.0,
                            }
                        )
                    ]
                )
            ]
        ),
        style={"height": "100vh", "width": "100vw"}
    )
])

# --- 5. CALLBACKS ---
@callback(
    Output("vol-rep", "property"),
    Input("time-slider", "value"),
    prevent_initial_call=False
)
def update_opacity(time_value):
    """
    Updates the scalarOpacity transfer function based on time.
    Logic:
    - 0 to time_value: Opacity 0 (Cut away)
    - time_value to MAX_TIME: Opacity 0 (Future cut path, currently Air)
    - > MAX_TIME: Opacity 0.3 (Uncut Material)
    """
    
    # We construct the PiecewiseFunction points array: [x, y, x, y, ...]
    # x = scalar value, y = opacity (0.0 to 1.0)
    
    # 1. Start with transparency for air (0)
    opacity_points = [0, 0.0]
    
    # 2. Mask out cut material (everything below current time is invisible)
    if time_value > 0:
        opacity_points.extend([time_value, 0.0])
        
    # 3. Create a step to reveal the future/permanent material
    # A tiny offset (0.1) creates a sharp transition
    opacity_points.extend([time_value + 0.1, 0.3])
    
    # 4. Ensure permanent material (OFFSET + Density) is visible
    opacity_points.extend([MATERIAL_OFFSET + 100, 0.3])

    return {
        "shade": True,
        "ambient": 0.3, 
        "diffuse": 0.8,
        "specular": 0.2,
        "scalarOpacity": { "type": "vtkPiecewiseFunction", "points": opacity_points },
        # Define Color: Blueish for glass
        "rgbTransferFunction": {
            "type": "vtkColorTransferFunction",
            "nodes": [
                [0, 0, 0, 0, 0.5, 0.0],
                [MATERIAL_OFFSET, 0, 0.8, 1.0, 0.5, 0.0], 
                [MATERIAL_OFFSET + 100, 0, 0.8, 1.0, 0.5, 0.0]
            ]
        }
    }

if __name__ == "__main__":
    app.run(debug=False)