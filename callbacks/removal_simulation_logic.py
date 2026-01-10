from dash import Input, Output, State, no_update, clientside_callback, MATCH
import numpy as np

from core.models.lenses import LensPairSimulationData
from core.geometric.lens_volume import generate_lens_volume, generate_machined_lens_volume

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
        Input('store-simulation-path', 'data'),
        prevent_initial_call=True
    )
    def update_slider_max(path_data):
        """Set slider max to duration of operation in seconds."""
        if not path_data or 'time' not in path_data:
            return 100
        
        time_data = path_data['time']
        if time_data and len(time_data) > 0:
            # Round up to nearest second
            return int(np.ceil(time_data[-1]))
        return 100

    # --- 1B. ADVANCE SLIDER (Clientside) ---
    clientside_callback(
        """
        function(n_intervals, current_val, max_val) {
            if (!max_val) return current_val;
            // Advance by 0.1 seconds per interval (assuming 10Hz interval)
            let new_val = current_val + 0.5;
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
        State('view-eye-select', 'value'),
        prevent_initial_call=True
    )
    def generate_lens_volume_data(mesh_cache, simulation_path, side="L"):
        """Generate volumetric representation of the lens blank."""
        if not mesh_cache:
            return no_update
        
        # Rehydrate lens data
        lens_pair = LensPairSimulationData.from_dict(mesh_cache)
        lens = lens_pair.left if side == "L" else lens_pair.right
        
        if not lens or not lens.blank_front_radius:
            return no_update
        
        # Generate volume using lens blank parameters
        volume_data = generate_machined_lens_volume(
            front_radius=lens.blank_front_radius,
            back_radius=lens.blank_back_radius,
            center_thickness=lens.blank_center_thickness,
            diameter_mm=lens.blank_diameter,
            tool_path=simulation_path,
            resolution=0.3
        )
        
        # Return serialized data
        return {
            "dimensions": volume_data.dimensions,
            "spacing": volume_data.spacing,
            "origin": volume_data.origin,
            "scalars": volume_data.scalars
        }
    
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

    # --- 4. UPDATE CONTOUR VALUE ON SLIDER CHANGE ---
    clientside_callback(
        """
        function(slider_value, slider_max) {
            if (slider_value === null || slider_value === undefined) {
                return window.dash_clientside.no_update;
            }
            
            if (window.vtkManager && window.vtkManager.isInitialized) {
                window.vtkManager.setContourValue(slider_value, slider_max);
            }

            console.log("Updated contour to: " + (1000 - slider_max + slider_value));
            
            return "Contour: " + (1000 - slider_max + slider_value);
        }
        """,
        Output('dummy-status-removal', 'children', allow_duplicate=True),
        Input('removal-sim-slider', 'value'),
        State('removal-sim-slider', 'max'),
        prevent_initial_call=True
    )
    