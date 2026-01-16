from dash import Input, Output, State, no_update, clientside_callback, MATCH, dcc
import numpy as np

from core.models.lenses import LensPairSimulationData
from core.geometric.lens_volume import generate_lens_volume, generate_machined_lens_volume
from core.machine_config import load_machine_config_cached, load_tool_mesh_cached
from core.exporters.path_exporter import format_path_data_to_csv, get_export_filename, get_path_summary

def register_removal_simulation_callbacks(app):
    """
    Registers callbacks related to the removal simulation logic.
    """ 
    # --- 1. ANIMATION CONTROLS ---
    @app.callback(
        Output('removal-sim-interval', 'disabled'),
        Input('removal-sim-play', 'n_clicks'),
        State('removal-sim-interval', 'disabled'),
        prevent_initial_call=True
    )
    def toggle_play(n, current_disabled):
        return not current_disabled

    @app.callback(
        Output('removal-sim-slider', 'max'),
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

    # --- 1B. ADVANCE SLIDER (Clientside) ---
    clientside_callback(
        """
        function(n_intervals, current_val, max_val) {
            if (!max_val) return current_val;
            // Advance by 0.1 seconds per interval (assuming 10Hz interval)
            let new_val = current_val + 0.2;
            if (new_val > max_val) {
                return 0;
            }
            return new_val;
        }
        """,
        Output('removal-sim-slider', 'value'),
        Input('removal-sim-interval', 'n_intervals'),
        State('removal-sim-slider', 'value'),
        State('removal-sim-slider', 'max'),
        prevent_initial_call=True
    )

    # --- 2. GENERATE LENS VOLUME DATA ---
    @app.callback(
        Output('store-lens-volume', 'data'),
        State('store-mesh-cache', 'data'),
        Input('store-simulation-path', 'data'),
        State('store-path-time', 'data'),
        State('view-eye-select', 'value'),
        prevent_initial_call=True
    )
    def generate_lens_volume_data(mesh_cache, simulation_path, time_data, side="L"):
        """Generate volumetric representation of the lens blank."""
        if not mesh_cache or not simulation_path or not time_data:
            return no_update
        
        # Rehydrate lens data
        lens_pair = LensPairSimulationData.from_dict(mesh_cache)
        lens = lens_pair.left if side == "L" else lens_pair.right
        
        if not lens or not lens.blank_front_radius:
            return no_update
        
        # Merge path and time data for volume calculation
        combined_path = {**simulation_path, **time_data}
        
        # Generate volume using lens blank parameters
        volume_data = generate_machined_lens_volume(
            front_radius=lens.blank_front_radius,
            back_radius=lens.blank_back_radius,
            center_thickness=lens.blank_center_thickness,
            diameter_mm=lens.blank_diameter,
            tool_path=combined_path,
            resolution=0.3
        )
        
        # Return serialized data
        return {
            "dimensions": volume_data.dimensions,
            "spacing": volume_data.spacing,
            "origin": volume_data.origin,
            "scalars": volume_data.scalars
        }
    
    # --- 2B. ADJUST TIMING BASED ON VOLUME CONSTRAINTS ---
    @app.callback(
        Output('store-path-time', 'data', allow_duplicate=True),
        Input('store-lens-volume', 'data'),
        State('store-path-time', 'data'),
        State('store-simulation-path', 'data'),
        prevent_initial_call=True
    )
    def adjust_timing_for_volume_constraints(lens_volume_data, time_data, simulation_path):
        """Adjust time array to ensure volume removal rates don't exceed constraints."""
        if not lens_volume_data or not time_data or not simulation_path:
            return no_update
        
        # Import here to avoid circular dependencies
        from core.geometric.lens_volume import calculate_volume_removal_rates, adjust_time_array_for_volume_constraints
        
        # Extract pass_segments with constraints
        pass_segments = simulation_path.get('pass_segments', [])
        if not pass_segments:
            return no_update
        
        # Check if any segment has volume constraints
        has_constraints = any(seg.get('max_volume_rate') is not None for seg in pass_segments)
        if not has_constraints:
            return no_update
        
        # Reconstruct death_times array from volume data
        nx, ny, nz = lens_volume_data['dimensions']
        scalars = np.array(lens_volume_data['scalars'], dtype=np.float32)
        death_times = scalars.reshape((nz, ny, nx))
        
        # Calculate voxel volume
        spacing = lens_volume_data['spacing']
        voxel_volume_mm3 = spacing[0] * spacing[1] * spacing[2]
        
        # Get original time array
        time_array = np.array(time_data['time'])
        
        # Calculate volume removal rates
        rate_info = calculate_volume_removal_rates(
            death_times=death_times,
            time_array=time_array,
            voxel_volume_mm3=voxel_volume_mm3,
            pass_segments=pass_segments
        )
        
        # Adjust timing
        adjusted_time = adjust_time_array_for_volume_constraints(
            time_array=time_array,
            volume_per_frame=rate_info['volume_removed_per_frame'],
            max_allowed_rate=rate_info['max_allowed_rate']
        )
        
        # Check if any adjustment was made
        if np.allclose(adjusted_time, time_array, rtol=1e-6):
            return no_update
        
        # Return updated time data
        return {'time': adjusted_time.tolist()}
    
    # --- 3. INITIALIZE VOLUME RENDERING ---
    clientside_callback(
        """
        function(volume_data) {
            if (!volume_data) return window.dash_clientside.no_update;

            // 1. Ensure the hardware context exists
            if (!window.vtkManager.isInitialized) {
                window.vtkManager.init('volume-container-removal');
            }

            // 2. Simply push the new data to the existing volume
            window.vtkManager.updateData(volume_data);

            return "Volume Updated: " + new Date().toLocaleTimeString();
        }
        """,
        Output('dummy-status-removal', 'children'),
        Input('store-lens-volume', 'data'),
        prevent_initial_call=True
    )

    # --- 4. UPDATE CONTOUR VALUE ON SLIDER CHANGE (Frame-Index Based) ---
    clientside_callback(
        """
        function(slider_value, path_data, time_data) {
            if (slider_value === null || slider_value === undefined) {
                return window.dash_clientside.no_update;
            }
            
            if (!path_data || !time_data || !time_data.time || !window.vtkManager || !window.vtkManager.isInitialized) {
                return window.dash_clientside.no_update;
            }
            
            // Convert slider time to frame index (same logic as transform callback)
            let frame_idx = 0;
            const time_array = time_data.time;
            if (time_array && time_array.length > 0) {
                for (let i = 0; i < time_array.length; i++) {
                    if (time_array[i] <= slider_value) {
                        frame_idx = i;
                    } else {
                        break;
                    }
                }
            }
            
            // Ensure within bounds
            const max_frames = path_data.total_frames || path_data.x.length;
            frame_idx = Math.max(0, Math.min(frame_idx, max_frames - 1));
            
            // Calculate frame-based contour value (0-1000 range)
            const contour_value = (frame_idx / max_frames) * 1000;
            
            // Update contour in VTK scene
            window.vtkManager.setContourValue(contour_value);

            console.log("Frame: " + frame_idx + "/" + max_frames + " Contour: " + contour_value.toFixed(1));
            
            return "Frame: " + frame_idx + " Contour: " + contour_value.toFixed(1);
        }
        """,
        Output('dummy-status-removal', 'children', allow_duplicate=True),
        Input('removal-sim-slider', 'value'),
        State('store-simulation-path', 'data'),
        State('store-path-time', 'data'),
        prevent_initial_call=True
    )

    # --- 5. GENERATE TOOL MESH DATA FOR VTK.JS ---
    @app.callback(
        Output('store-removal-tools', 'data'),
        Input('store-lens-volume', 'data'),
        prevent_initial_call=True
    )
    def generate_tool_data(lens_volume_data):
        """Generate serialized tool mesh data for VTK.js rendering."""
        if not lens_volume_data:
            return no_update
        
        machine = load_machine_config_cached()
        tool_meshes = load_tool_mesh_cached()
        
        # Convert machine tilt to radians for position calculation
        tilt_rad = np.deg2rad(machine.tilt_angle_deg)
        sin_t = np.sin(tilt_rad)
        cos_t = np.cos(tilt_rad)
        
        tools_data = []
        for wheel in machine.wheels:
            if wheel.tool_id not in tool_meshes:
                continue
            
            pts, polys = tool_meshes[wheel.tool_id]
            
            # Calculate global position based on stack offset and tilt
            z_local = wheel.stack_z_offset
            pos_x = machine.base_position[0] - (z_local * sin_t)
            pos_y = machine.base_position[1]
            pos_z = machine.base_position[2] + (z_local * cos_t)
            
            tools_data.append({
                "tool_id": wheel.tool_id,
                "points": pts.tolist() if hasattr(pts, 'tolist') else list(pts),
                "polys": polys.tolist() if hasattr(polys, 'tolist') else list(polys),
                "position": [pos_x, pos_y, pos_z],
                "tilt_angle": machine.tilt_angle_deg
            })
        
        return tools_data

    # --- 6. LOAD TOOL MESHES INTO VTK SCENE ---
    clientside_callback(
        """
        function(tools_data) {
            if (!tools_data) return window.dash_clientside.no_update;
            
            // Wait for vtkManager to be initialized
            if (window.vtkManager && window.vtkManager.isInitialized) {
                window.vtkManager.loadToolMeshes(tools_data);
                window.vtkManager.addGroundPlane();
            } else {
                // Retry after a short delay if not initialized yet
                setTimeout(function() {
                    if (window.vtkManager && window.vtkManager.isInitialized) {
                        window.vtkManager.loadToolMeshes(tools_data);
                        window.vtkManager.addGroundPlane();
                    }
                }, 500);
            }
            
            return "Tools loaded: " + tools_data.length;
        }
        """,
        Output('dummy-status-removal-tools', 'children'),
        Input('store-removal-tools', 'data'),
        prevent_initial_call=True
    )

    # --- 7. UPDATE LENS TRANSFORM BASED ON SLIDER (Movement Animation) ---
    clientside_callback(
        """
        function(slider_time, path_data, time_data) {
            // Safety checks
            if (!path_data || !path_data.x || !time_data || !time_data.time || !window.vtkManager || !window.vtkManager.isInitialized) {
                return window.dash_clientside.no_update;
            }

            // Find frame index based on time
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

            // Get coordinates for lens position
            const x = path_data.x[frame_idx];
            const z = path_data.z[frame_idx];
            const theta = path_data.theta[frame_idx];

            // Update lens transform in VTK scene
            window.vtkManager.updateLensTransform(x, z, -theta);

            return "Transform: x=" + x.toFixed(2) + " z=" + z.toFixed(2) + " θ=" + theta.toFixed(1);
        }
        """,
        Output('dummy-status-removal-transform', 'children'),
        Input('removal-sim-slider', 'value'),
        State('store-simulation-path', 'data'),
        State('store-path-time', 'data'),
        prevent_initial_call=True
    )
    
    # --- DOWNLOAD TOOLPATH DATA ---
    @app.callback(
        Output('download-toolpath', 'data'),
        Input('btn-download-toolpath', 'n_clicks'),
        State('store-simulation-path', 'data'),
        State('store-path-time', 'data'),
        prevent_initial_call=True
    )
    def download_toolpath(n_clicks, path_data, time_data):
        """Export tool path and timing data to CSV file."""
        if not n_clicks or not path_data or not time_data:
            return no_update
        
        # Format data to CSV
        csv_content = format_path_data_to_csv(path_data, time_data)
        
        if not csv_content:
            return no_update
        
        # Get filename with timestamp
        filename = get_export_filename('csv')
        
        # Return download data
        return dict(content=csv_content, filename=filename)
    
    @app.callback(
        Output('btn-download-toolpath', 'disabled'),
        Input('store-simulation-path', 'data'),
        prevent_initial_call=True
    )
    def enable_download_button(path_data):
        """Enable download button after path is generated."""
        return not bool(path_data and path_data.get('x'))
