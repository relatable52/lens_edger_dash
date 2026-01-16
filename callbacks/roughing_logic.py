from dash import Input, Output, State, ctx, no_update
from core.models.roughing import RoughingPassParam, RoughingSettings
import numpy as np
import plotly.graph_objects as go


def register_roughing_callbacks(app):
    """
    Handles roughing configuration management:
    - Adding new roughing passes
    - Updating pass parameters (step, speed)
    - Changing the global cutting method
    - Calculating removed volume for each pass (with mesh-based accuracy)
    - Syncing with data store
    
    All passes use the SAME cutting method (CONCENTRIC or INTERPOLATION).
    """
    
    @app.callback(
        Output('roughing-table-sidebar', 'data', allow_duplicate=True),
        Output('store-roughing-data', 'data'),
        
        Input('btn-add-roughing', 'n_clicks'),
        Input('roughing-table-sidebar', 'data'),
        Input('input-roughing-method', 'value'),
        
        State('roughing-table-sidebar', 'data'),
        State('store-roughing-data', 'data'),
        
        prevent_initial_call=True
    )
    def manage_roughing_passes(add_clicks, table_data, method, current_table_data, current_store):
        """
        Manages the roughing passes table:
        1. When user clicks "Add" button, adds a new pass
        2. When user edits table, validates and stores data (clears volumes to show placeholder)
        3. When user changes method, updates the global method for all passes (clears volumes)
        
        All passes share the same method (CONCENTRIC or INTERPOLATION).
        When table or method changes, volumes are cleared to "?" to indicate recalculation is needed.
        """
        trigger_id = ctx.triggered_id
        
        # Initialize store with default RoughingSettings if empty
        if not current_store:
            roughing_settings = RoughingSettings(method=method or 'CONCENTRIC', passes=[])
            current_store = roughing_settings.to_dict()
        else:
            roughing_settings = RoughingSettings.from_dict(current_store)
        
        # Always sync the method (global for all passes)
        roughing_settings.method = method or 'CONCENTRIC'
        
        # Handle ADD BUTTON click
        if trigger_id == 'btn-add-roughing':
            new_pass_index = len(table_data) + 1
            
            # Create new row based on last row's parameters
            if table_data:
                last_pass = table_data[-1]
                new_row = {
                    'pass_index': new_pass_index,
                    'step': last_pass.get('step', 3.0),
                    'speed': last_pass.get('speed', 15),
                    'max_vol': last_pass.get('max_vol', 100.0)
                }
            else:
                new_row = {
                    'pass_index': new_pass_index,
                    'step': 3.0,
                    'speed': 15,
                    'max_vol': 100.0
                }
            
            new_table_data = table_data + [new_row] if table_data else [new_row]
            
            # Convert table data to RoughingPassParam and sync store
            roughing_settings.passes = [
                RoughingPassParam(
                    step_value_mm=float(row.get('step', 3.0)),
                    speed_s_per_rev=float(row.get('speed', 15)),
                    max_volume_mm3_per_sec=float(row.get('max_vol', 100.0))
                )
                for row in new_table_data
            ]
            return new_table_data, roughing_settings.to_dict()
        
        # Handle TABLE DATA changes (edits or deletions)
        elif trigger_id == 'roughing-table-sidebar':
            # Reindex passes after deletion and reset volumes to placeholder ONLY if user edited step/speed
            if table_data:
                for idx, row in enumerate(table_data, start=1):
                    row['pass_index'] = idx
            
            # Convert table data to RoughingPassParam and sync store
            roughing_settings.passes = [
                RoughingPassParam(
                    step_value_mm=float(row.get('step', 3.0)),
                    speed_s_per_rev=float(row.get('speed', 15)),
                    max_volume_mm3_per_sec=float(row.get('max_vol', 100.0))
                )
                for row in table_data
            ]
            return table_data, roughing_settings.to_dict()
        
        # Handle METHOD change (applies to all passes)
        elif trigger_id == 'input-roughing-method':
            roughing_settings.passes = [
                RoughingPassParam(
                    step_value_mm=float(row.get('step', 3.0)),
                    speed_s_per_rev=float(row.get('speed', 15)),
                    max_volume_mm3_per_sec=float(row.get('max_vol', 100.0))
                )
                for row in table_data
            ]
            return table_data, roughing_settings.to_dict()
                
        return no_update, no_update
    
    
    @app.callback(
        Output('roughing-table-sidebar', 'data', allow_duplicate=True),
        Output('store-roughing-results', 'data'),
        
        Input('btn-update-roughing', 'n_clicks'),
        
        State('store-roughing-data', 'data'),
        State('roughing-table-sidebar', 'data'),
        State('store-oma-job', 'data'),
        State('store-lenses-data', 'data'),
        State('store-eye-select', 'data'),
        
        prevent_initial_call=True
    )
    def update_roughing_volumes(update_clicks, roughing_data, table_data, oma_job_data, lens_data, eye_select):
        """
        Triggered by "Update Roughing" button.
        Calls generate_roughing_operations() to get accurate mesh-based volumes.
        Stores detailed results and updates table with calculated volumes.
        
        Uses:
        - oma_job_data: Contains the final radii (frame shape to cut)
        - lens_data: Contains the blank parameters (diameter, thickness, curves)
        """
        if not roughing_data or not table_data or not oma_job_data or not lens_data:
            return no_update, no_update
        
        try:
            from core.geometric.roughing_generation import generate_roughing_operations
            from core.models.lenses import OMAJob, LensPair
            
            # Extract final radii from OMA job (the frame shape)
            oma_job = OMAJob.from_dict(oma_job_data)
            if not oma_job:
                print("Error: OMA job data is invalid or incomplete.")
                return no_update, no_update
            
            final_radii = np.array(oma_job.left.radii) if eye_select == 'L' else np.array(oma_job.right.radii)
            
            if len(final_radii) == 0:
                print("Error: OMA job contains no radii data.")
                return no_update, no_update
            
            # Extract lens blank parameters from lens_data
            lens_data = LensPair.from_dict(lens_data).left if eye_select == 'L' else LensPair.from_dict(lens_data).right
            blank_radius = lens_data.diameter / 2.0
            lens_thickness = lens_data.center_thickness
            front_curve = lens_data.front_radius
            back_curve = lens_data.back_radius
            
            # Create RoughingSettings from store data
            roughing_settings = RoughingSettings.from_dict(roughing_data)
            
            # Generate roughing operations with actual mesh calculation
            roughing_results = generate_roughing_operations(
                final_radii=final_radii,
                blank_radius=blank_radius,
                lens_thickness=lens_thickness,
                front_curve=front_curve,
                back_curve=back_curve,
                roughing_settings=roughing_settings
            )

            # print("Roughing Results:", [r.volume for r in roughing_results])
            
            # Serialize results for storage
            results_dict = [
                {
                    'pass_index': r.pass_index,
                    'mesh': r.mesh.to_dict(),
                    'radii': r.radii,
                    'volume': r.volume,
                    'duration': r.duration,
                    'max_vol': table_data[i].get('max_vol', None) if i < len(table_data) else None
                }
                for i, r in enumerate(roughing_results)
            ]
            
            return no_update, results_dict
            
        except ValueError as ve:
            print(f"Validation error updating roughing volumes: {ve}")
            return no_update, no_update
        except Exception as e:
            print(f"Error updating roughing volumes: {e}")
            import traceback
            traceback.print_exc()
            return no_update, no_update
    
    
    @app.callback(
        Output('graph-roughing-contour', 'figure'),
        Input('store-roughing-results', 'data'),
        State('store-oma-job', 'data'),
        State('store-eye-select', 'data'),
        prevent_initial_call=True
    )
    def update_roughing_contour_plot(roughing_results, oma_job_data, eye_select):
        """
        Updates the roughing contour 2D plot whenever results are calculated.
        Displays top-down view (x,y) of each roughing pass plus the final lens shape.
        """
        from components.roughing_contour_tab import render_figure
        return render_figure(roughing_results, oma_job_data, eye_select)
    
    
    def get_roughing_operations_list(roughing_store):
        """
        Helper function to convert store data to RoughingPassParam list.
        
        Returns a list of RoughingPassParam objects ready for use with
        core.geometric.roughing_generation.generate_roughing_operations()
        
        Note: The method is NOT included in RoughingPassParam - it's stored
        separately in the RoughingSettings.method field.
        
        Usage in other callbacks:
            from callbacks.roughing_logic import get_roughing_operations_list
            
            @app.callback(...)
            def my_callback(roughing_store_data):
                operations = get_roughing_operations_list(roughing_store_data)
                method = roughing_store_data['method']
                # Use operations and method in roughing_generation
        """
        if not roughing_store or not roughing_store.get('passes'):
            return []
        
        return [
            RoughingPassParam(
                step_value_mm=float(pass_info.get('step_value_mm', 3.0)),
                speed_s_per_rev=float(pass_info.get('speed_s_per_rev', 15)),
                max_volume_mm3_per_sec=float(pass_info.get('max_volume_mm3_per_sec', 100.0))
            )
            for pass_info in roughing_store['passes']
        ]
