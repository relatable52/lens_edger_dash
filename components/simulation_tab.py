import dash_vtk
from dash import html, dcc
import dash_bootstrap_components as dbc
import numpy as np

from core.machine_config import load_machine_config_cached, load_tool_mesh_cached
from core.models.lenses import LensPairSimulationData
from core.models.roughing import RoughingPassData

def layout():
    """Returns the layout of the simulation tab."""
    return dbc.Card(
        dbc.CardBody([
            html.H6("3D Simulation View"),
            # VTK Container
            html.Div(
                id='vtk-container-sim', 
                style={
                    "height": "60vh", 
                    "width": "100%",
                    "borderRadius": "4px",
                    "overflow": "hidden",
                    "backgroundColor": "#1a1a1a"
                }
            ),
            # Controls
             # Controls
            dbc.Row([
                dbc.Col(dbc.Button("Play/Pause", id="sim-play", color="primary", size="sm"), width="auto"),
                dbc.Col(
                    dcc.Slider(
                        id="sim-slider", min=0, max=100, step=1, value=0,
                        marks=None,
                        tooltip={"placement": "bottom", "always_visible": True}
                    ),
                    className="pt-2"
                )
            ], class_name="align-items-center mt-3 bg-light p-2 rounded")
        ]), className="mt-3"
    )

def render_simulation_scene(
    kinematics_path: dict, 
    frame_index: int,
    lens_pair_data: LensPairSimulationData,
    roughing_results: list[RoughingPassData]=None,
    view_side: str = "L"
):
    """
    Renders the simulation frame: Stationary Tools + All Moving Geometry (Roughing + Final Lens).
    Meshes are pre-loaded with opacity controlled by clientside callback during animation.
    
    Args:
        kinematics_path: Path data with x, z, theta, time arrays
        frame_index: Current frame index
        lens_pair_data: Lens geometry data
        roughing_results: List of roughing results for visualization
        view_side: "L" or "R"
    """
    # 1. Load Static Assets
    machine = load_machine_config_cached()
    tool_meshes = load_tool_mesh_cached()
    
    children_views = []

    # --- A. RENDER TOOL STACK (Stationary) ---
    # Convert machine tilt to radians
    tilt_rad = np.deg2rad(machine.tilt_angle_deg)
    sin_t = np.sin(tilt_rad)
    cos_t = np.cos(tilt_rad)

    for wheel in machine.wheels:
        if wheel.tool_id not in tool_meshes:
            continue
            
        pts, polys = tool_meshes[wheel.tool_id]
        
        # Calculate Global Position based on stack offset and tilt
        z_local = wheel.stack_z_offset
        pos_x = machine.base_position[0] - (z_local * sin_t)
        pos_y = machine.base_position[1]
        pos_z = machine.base_position[2] + (z_local * cos_t)

        children_views.append(
            dash_vtk.GeometryRepresentation(
                actor={
                    "position": [pos_x, pos_y, pos_z],
                    "orientation": [0, -machine.tilt_angle_deg, 0],
                    "color": [0.7, 0.7, 0.7], 
                },
                children=[dash_vtk.PolyData(points=pts, polys=polys)]
            )
        )

    # --- B. LOAD ALL MOVING GEOMETRY (Meshes with dynamic opacity) ---
    if kinematics_path and 'total_frames' in kinematics_path and lens_pair_data:
        
        # 1. Get Current Pose (for initial position)
        idx = min(frame_index, kinematics_path['total_frames'] - 1)
        lens_x = kinematics_path['x'][idx]
        lens_z = kinematics_path['z'][idx]
        lens_rot = kinematics_path['theta'][idx]

        # 2. Get Geometry for the specific side
        lens_data = lens_pair_data.left if view_side == "L" else lens_pair_data.right
        
        if lens_data:
            # Load all roughing pass meshes with pattern-matching IDs
            if roughing_results:
                for pass_idx, roughing_result in enumerate(roughing_results):
                    if roughing_result.mesh is not None:
                        mesh_data = roughing_result.mesh
                        
                        # First pass starts visible, others hidden
                        initial_opacity = 1.0 if pass_idx == 0 else 0.0
                        
                        children_views.append(
                            dash_vtk.GeometryRepresentation(
                                id={'type': 'sim-lens-roughing-rep', 'index': pass_idx},
                                actor={
                                    "position": [lens_x, 0, lens_z],
                                    "orientation": [0, 0, -lens_rot],
                                },
                                property={
                                    "edgeVisibility": False,
                                    "specular": 0.3,
                                    "specularPower": 15,
                                    "opacity": initial_opacity,
                                    "color": [0.6, 0.6, 0.65],  # Gray for roughing
                                },
                                children=[
                                    dash_vtk.PolyData(
                                        points=mesh_data.points, 
                                        polys=mesh_data.polys
                                    )
                                ]
                            )
                        )
            
            # Load final cut lens (initially hidden during roughing)
            color = [0.2, 0.6, 1.0] if view_side == "L" else [1.0, 0.6, 0.2]
            children_views.append(
                dash_vtk.GeometryRepresentation(
                    id="sim-lens-cut-rep",
                    actor={
                        "position": [lens_x, 0, lens_z],
                        "orientation": [0, 0, -lens_rot],
                    },
                    property={
                        "edgeVisibility": False, 
                        "specular": 0.5, 
                        "specularPower": 20,
                        "opacity": 0.0,  # Hidden during roughing
                        "color": color,
                    },
                    children=[
                        dash_vtk.PolyData(
                            points=lens_data.cut_mesh.points, 
                            polys=lens_data.cut_mesh.polys
                        )
                    ]
                )
            )

            # Load blank lens
            children_views.append(
                dash_vtk.GeometryRepresentation(
                    id = "sim-lens-blank-rep",
                    actor={
                        "position": [lens_x, 0, lens_z],
                        "orientation": [0, 0, -lens_rot],
                    },
                    property={
                        "edgeVisibility": False,
                        "color": [0.8, 0.8, 0.9],
                        "opacity": 0.15
                    },
                    children=[
                        dash_vtk.PolyData(
                            points=lens_data.blank_mesh.points, 
                            polys=lens_data.blank_mesh.polys
                        )
                    ]
                )
            )

    # --- C. Reference Ground Plane ---
    children_views.append(
        dash_vtk.GeometryRepresentation(
            property = {
                "edgeVisibility": False,
                "color": [0.7, 0.7, 0.7], 
                "opacity": 0.4
            },
            children=dash_vtk.PolyData(
                points = [200, 200, -200, 200, -200, -200, -200, -200, -200, -200, 200, -200],
                polys = [4, 0, 1, 2, 3]
            )
        )
    )

    # --- D. SCENE SETUP ---
    return dash_vtk.View(
        background=[0.1, 0.1, 0.12],
        cameraPosition=[0, -300, 100],
        cameraViewUp=[0, 0, 1],
        children=children_views,
        style={"width": "100%", "height": "100%"}
    )