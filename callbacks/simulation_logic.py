from dash import Input, Output, State, ctx, no_update
import numpy as np

from core.models.lenses import OMAJob, LensPairSimulationData
from core.cam.kinematics import solve_lens_kinematics_robust
from core.cam.path_generation import generate_full_simulation_path
from core.machine_config import load_machine_config_cached
from components import simulation_tab

def register_simulation_callbacks(app):

    # --- 1. GENERATE KINEMATICS (Heavy Calculation) ---
    # Trigger: "Generate Paths" button
    @app.callback(
        Output('store-simulation-path', 'data'),
        Input('btn-gen-path', 'n_clicks'),
        State('store-mesh-cache', 'data'),
        State('view-eye-select', 'value'),
        prevent_initial_call=True
    )
    def generate_path(n_clicks, mesh_cache, side = "L"):
        if not mesh_cache:
            return no_update
            
        # 1. Rehydrate Job
        lens_pair = LensPairSimulationData.from_dict(mesh_cache)
        lens = lens_pair.left if side == "L" else lens_pair.right
        bevel_data = lens.bevel_data
        
        if not bevel_data:
            return no_update

        # 2. Run Kinematics Solver
        machine = load_machine_config_cached()
        wheel = machine.wheels[0]
        tool_radius = wheel.cutting_radius

        # print("input_z_map", bevel_data.z_map[0])
        
        kinematics = solve_lens_kinematics_robust(
            radii=bevel_data.radii,
            z_map=bevel_data.z_map,
            tool_radius=tool_radius,
            tool_tilt_angle_deg=abs(machine.tilt_angle_deg)
        )
        
        # 3. Stitch Approach Path
        tilt_rad = np.deg2rad(machine.tilt_angle_deg)
        sin_t = np.sin(tilt_rad)
        cos_t = np.cos(tilt_rad)
        z_local = wheel.stack_z_offset + wheel.cutting_z_relative
        wheel_x = machine.base_position[0] - (z_local * sin_t)
        wheel_z = machine.base_position[2] + (z_local * cos_t)
        full_path = generate_full_simulation_path(
            kinematics,
            wheel_x = wheel_x,
            wheel_z = wheel_z,
            home_x=-50,
            home_z=0,
            approach_steps=1
        )
        
        if not full_path:
            return no_update
        
        # print("full_path", full_path['z'][10])

        # 4. Serialize for Store (Numpy -> List)
        return {
            "x": full_path['x'].tolist(),
            "z": full_path['z'].tolist(),
            "theta": full_path['theta'].tolist(),
            "total_frames": full_path['total_frames']
        }

   # --- 2. ANIMATION CONTROLS ---
    @app.callback(
        Output('sim-interval', 'disabled'),
        Input('sim-play', 'n_clicks'),
        State('sim-interval', 'disabled'),
        prevent_initial_call=True
    )
    def toggle_play(n, current_disabled):
        return not current_disabled

    @app.callback(
        Output('sim-slider', 'value'),
        Input('sim-interval', 'n_intervals'),
        State('sim-slider', 'value'),
        prevent_initial_call=True
    )
    def advance_slider(n, current_val):
        new_val = current_val + 1
        if new_val > 100: return 0
        return new_val

    # --- 3. RENDER SCENE ---
    @app.callback(
        Output('vtk-container-sim', 'children'),
        Input('sim-slider', 'value'),
        Input('store-simulation-path', 'data'),
        State('store-mesh-cache', 'data'),
        State('view-eye-select', 'value'),
        prevent_initial_call=True
    )
    def render_simulation_frame(slider_val, path_data, mesh_cache, view_mode):
        if not path_data or not mesh_cache:
            # Return empty or loading state
            return simulation_tab.render_simulation_scene({}, 0, None)
            
        # Determine side based on view mode (consistent with generate_path)
        side = "R" if view_mode == "R" else "L"
        
        # Map Slider to Frame Index
        total_frames = path_data.get('total_frames', 100)
        # Safe integer conversion
        frame_idx = int((slider_val / 100.0) * (total_frames - 1))
        
        # Rehydrate Mesh Data
        lens_pair = LensPairSimulationData.from_dict(mesh_cache)
        
        return simulation_tab.render_simulation_scene(
            kinematics_path=path_data,
            frame_index=frame_idx,
            lens_pair_data=lens_pair,
            view_side=side
        )