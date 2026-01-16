from dash import Input, Output, State, no_update, clientside_callback, MATCH
import numpy as np

from core.models.lenses import LensPairSimulationData
from core.models.roughing import RoughingPassData
from core.cam.kinematics import solve_lens_kinematics_robust
from core.cam.path_generation import generate_full_simulation_path
from core.cam.movement_path import generate_complete_lens_path
from core.machine_config import load_machine_config_cached
from components import simulation_tab

# Add to layout before register_simulation_callbacks
def add_stores_to_layout(app):
    """Add hidden stores to the app layout for clientside callbacks."""
    from dash import dcc
    return [
        dcc.Store(id='store-active-pass', data={'pass_index': 0, 'is_beveling': False})
    ]

def register_simulation_callbacks(app):

    # --- 1. GENERATE COMPLETE MOVEMENT PATH (Roughing + Beveling) ---
    # Trigger: "Generate Paths" button
    @app.callback(
        Output('store-simulation-path', 'data'),
        Output('store-path-time', 'data'),
        Input('btn-gen-path', 'n_clicks'),
        State('store-mesh-cache', 'data'),
        State('store-roughing-results', 'data'),
        State('view-eye-select', 'value'),
        prevent_initial_call=True
    )
    def generate_path(n_clicks, mesh_cache, roughing_results, side="L"):
        if not mesh_cache:
            return no_update
            
        # 1. Rehydrate Lens Data
        lens_pair = LensPairSimulationData.from_dict(mesh_cache)
        lens = lens_pair.left if side == "L" else lens_pair.right
        bevel_data = lens.bevel_data
        
        if not bevel_data:
            return no_update
        
        # 2. Prepare Roughing Passes (if available)
        roughing_passes = []
        if roughing_results:
            for r in roughing_results:
                roughing_passes.append({
                    'radii': np.array(r['radii']),
                    'z_map': np.zeros_like(r['radii']),  # TODO: Extract from mesh if needed
                    'speed_s_per_rev': r.get('duration', 10.0)
                })
        
        # 3. Load Machine Configuration
        machine = load_machine_config_cached()
        
        # 4. Generate Complete Path (Roughing + Beveling)
        paths = generate_complete_lens_path(
            roughing_passes=roughing_passes,
            final_radii=np.array(bevel_data.radii),
            z_map=np.array(bevel_data.z_map),
            machine_config=machine,
            xyz_feedrate=50.0  # mm/sec
        )
        
        complete_path = paths['complete']
        x, z, theta, time = complete_path.get_full_path()
        
        if len(x) == 0:
            return no_update, no_update

        # 5. Build pass segment metadata from complete path (index-based, time-independent)
        # Track frame indices for each pass to enable time-independent segmentation
        pass_segments = []
        frame_offset = 0
        
        for step in complete_path.steps:
            if step.time is not None and len(step.time) > 0:
                num_frames = len(step.x) if hasattr(step, 'x') else len(step.time)
                
                # Record segment if this is a roughing or beveling step
                if step.operation_type in ['roughing', 'beveling']:
                    pass_segments.append({
                        'start_idx': int(frame_offset),
                        'end_idx': int(frame_offset + num_frames - 1),
                        'pass_index': int(step.pass_index),
                        'operation_type': step.operation_type,
                        'max_volume_rate': None  # Will be populated later from roughing_results
                    })
                
                frame_offset += num_frames

        # 6. Add max_vol constraints from roughing_results to pass_segments
        if roughing_results:
            roughing_idx = 0
            for segment in pass_segments:
                if segment['operation_type'] == 'roughing' and roughing_idx < len(roughing_results):
                    segment['max_volume_rate'] = roughing_results[roughing_idx].get('max_vol', None)
                    roughing_idx += 1

        # 7. Serialize for Stores (Numpy -> List)
        # Path data (spatial, time-independent)
        path_data = {
            "x": x.tolist(),
            "z": z.tolist(),
            "theta": theta.tolist(),
            "total_frames": len(x),
            "pass_segments": pass_segments
        }
        
        # Time data (separate store for independent adjustment)
        time_data = {
            "time": time.tolist()
        }
        
        return path_data, time_data

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
        Output('sim-slider', 'max'),
        Input('store-path-time', 'data'),
        prevent_initial_call=True
    )
    def update_slider_max(time_data):
        """Set slider max to duration of operation in seconds."""
        if not time_data or 'time' not in time_data:
            return 100
        
        time_array = time_data['time']
        if time_array and len(time_array) > 0:
            # Round up to nearest second
            return int(np.ceil(time_array[-1]))
        return 100

    # --- 2B. ADVANCE SLIDER (Clientside) ---
    clientside_callback(
        """
        function(n_intervals, current_val, max_val) {
            if (!max_val) return current_val;
            // Advance by 0.1 seconds per interval (assuming 10Hz interval)
            let new_val = current_val + 0.1;
            if (new_val > max_val) {
                return 0;
            }
            return new_val;
        }
        """,
        Output('sim-slider', 'value'),
        Input('sim-interval', 'n_intervals'),
        State('sim-slider', 'value'),
        State('sim-slider', 'max'),
        prevent_initial_call=True
    )

    # --- 3A. Setup 3D scene (ONLY on path generation, not on slider change) ---
    @app.callback(
        Output('vtk-container-sim', 'children'),
        Input('store-simulation-path', 'data'),
        State('store-mesh-cache', 'data'),
        State('store-roughing-results', 'data'),
        State('view-eye-select', 'value'),
        prevent_initial_call=True
    )
    def render_simulation_frame(path_data, mesh_cache, roughing_results, view_mode):
        """Initialize scene only when path changes, not on every slider update."""
        if not path_data or not mesh_cache:
            return simulation_tab.render_simulation_scene({}, 0, None)
        
        # Determine side based on view mode
        side = "R" if view_mode == "R" else "L"
        
        # Rehydrate Mesh Data
        lens_pair = LensPairSimulationData.from_dict(mesh_cache)

        # Roughing results
        roughing_results = [
            RoughingPassData.from_dict(r) for r in roughing_results
        ]
        
        # Start at frame 0
        return simulation_tab.render_simulation_scene(
            kinematics_path=path_data,
            frame_index=0,
            lens_pair_data=lens_pair,
            roughing_results=roughing_results,
            view_side=side
        )
    
    # --- 3B. ANIMATE SCENE + UPDATE MESH VISIBILITY ---
    clientside_callback(
        """
        function(slider_time, path_data, time_data) {
            // 1. Safety Checks
            if (!path_data || !path_data.x || !time_data || !time_data.time) {
                return window.dash_clientside.no_update;
            }

            // 2. Find frame index based on time
            let frame_idx = 0;
            const time_array = time_data.time;
            if (time_array && time_array.length > 0) {
                for (let i = 0; i < time_array.length; i++) {
                    if (time_array[i] <= slider_time) {
                        frame_idx = i;
                    } else {
                        break;
                    }
                }
            }
            
            // Ensure within bounds
            frame_idx = Math.max(0, Math.min(frame_idx, path_data.x.length - 1));

            // 3. Get coordinates for actor position
            const x = path_data.x[frame_idx];
            const z = path_data.z[frame_idx];
            const theta = path_data.theta[frame_idx];

            // 4. Update actor positions
            const actor_state = {
                position: [x, 0, z],
                orientation: [0, 0, -theta]
            };

            return [actor_state, actor_state];
        }
        """,
        Output('sim-lens-blank-rep', 'actor'),
        Output('sim-lens-cut-rep', 'actor'),
        Input('sim-slider', 'value'),
        State('store-simulation-path', 'data'),
        State('store-path-time', 'data'),
        prevent_initial_call=True
    )

    clientside_callback(
        """
        function(slider_time, path_data, time_data, id_dict) {
            // 1. Safety Checks
            if (!path_data || !path_data.x || !time_data || !time_data.time) {
                return window.dash_clientside.no_update;
            }

            // 2. Find frame index based on time
            let frame_idx = 0;
            const time_array = time_data.time;
            if (time_array && time_array.length > 0) {
                for (let i = 0; i < time_array.length; i++) {
                    if (time_array[i] <= slider_time) {
                        frame_idx = i;
                    } else {
                        break;
                    }
                }
            }
            
            // Ensure within bounds
            frame_idx = Math.max(0, Math.min(frame_idx, path_data.x.length - 1));

            // 3. Get coordinates for actor position
            const x = path_data.x[frame_idx];
            const z = path_data.z[frame_idx];
            const theta = path_data.theta[frame_idx];

            // 4. Update actor positions
            const actor_state = {
                position: [x, 0, z],
                orientation: [0, 0, -theta]
            };

            return actor_state;
        }
        """,
        Output({'type': 'sim-lens-roughing-rep', 'index': MATCH}, 'actor'),
        Input('sim-slider', 'value'),
        State('store-simulation-path', 'data'),
        State('store-path-time', 'data'),
        State({'type': 'sim-lens-roughing-rep', 'index': MATCH}, 'id'),
        prevent_initial_call=True
    )

    # --- 3C. DETERMINE ACTIVE PASS INDEX (Clientside) ---
    clientside_callback(
        """
        function(slider_time, path_data, time_data) {
            if (!path_data || !time_data || !time_data.time) {
                return {pass_index: 0, is_beveling: true};
            }

            const time_array = time_data.time;
            
            // Convert index-based segments to time-based breaks on the fly
            if (!path_data.pass_segments || path_data.pass_segments.length === 0) {
                return {pass_index: 0, is_beveling: true};
            }

            // Find current frame index from slider time
            let frame_idx = 0;
            if (time_array && time_array.length > 0) {
                for (let i = 0; i < time_array.length; i++) {
                    if (time_array[i] <= slider_time) {
                        frame_idx = i;
                    } else {
                        break;
                    }
                }
            }
            
            // Find which segment this frame belongs to
            let current_pass = 0;
            let is_beveling = true;
            
            for (let i = 0; i < path_data.pass_segments.length; i++) {
                const segment = path_data.pass_segments[i];
                if (frame_idx >= segment.start_idx && frame_idx <= segment.end_idx) {
                    current_pass = segment.pass_index;
                    is_beveling = segment.operation_type === 'beveling';
                    break;
                }
            }
            
            // If we're past all segments, use the last one
            if (frame_idx > path_data.pass_segments[path_data.pass_segments.length - 1].end_idx) {
                const last_segment = path_data.pass_segments[path_data.pass_segments.length - 1];
                current_pass = last_segment.pass_index;
                is_beveling = last_segment.operation_type === 'beveling';
            }
            
            return {pass_index: current_pass, is_beveling: is_beveling};
        }
        """,
        Output('store-active-pass', 'data'),
        Input('sim-slider', 'value'),
        State('store-simulation-path', 'data'),
        State('store-path-time', 'data')
    )

    # --- 3D. UPDATE ROUGHING MESH OPACITY FROM STORE (Clientside Pattern-Matching) ---
    clientside_callback(
        """
        function(active_pass_data, id_dict) {
            // 1. Safety Checks
            if (!active_pass_data || !id_dict) {
                return window.dash_clientside.no_update;
            }

            const current_pass = active_pass_data.pass_index;
            const is_beveling = active_pass_data.is_beveling;

            // 2. Define Visual Style (Must include Color/Specular to prevent "Ghosting")
            const roughing_style = {
                color: [0.6, 0.6, 0.65], 
                specular: 0.3,
                specularPower: 15,
                edgeVisibility: false
            };

            // 3. Direct Logic 
            const pass_idx = id_dict.index;
            
            // Check if this specific lens should be visible
            // Convert pass_index from 1-indexed (from kinematics) to 0-indexed (for lens IDs)
            const is_visible = (pass_idx == (current_pass - 1)) && !is_beveling;

            // 4. Return Single Property Object
            return {
                ...roughing_style,
                opacity: is_visible ? 1.0 : 0.0
            };
        }
        """,
        Output({'type': 'sim-lens-roughing-rep', 'index': MATCH}, 'property'),
        Input('store-active-pass', 'data'),
        State({'type': 'sim-lens-roughing-rep', 'index': MATCH}, 'id'),
        prevent_initial_call=True
    )

    # --- 3D. UPDATE FINAL LENS OPACITY DURING ANIMATION ---
    clientside_callback(
        """
        function(active_pass_data) {
            if (!active_pass_data) {
                return window.dash_clientside.no_update;
            }
            
            // Show final lens only during beveling operation
            const is_beveling = active_pass_data.is_beveling;
            
            return {opacity: is_beveling ? 1.0 : 0.0};
        }
        """,
        Output('sim-lens-cut-rep', 'property'),
        Input('store-active-pass', 'data'),
        prevent_initial_call=True
    )