from dash import Input, Output, State, ctx, no_update, clientside_callback
import base64

from core.oma_parser import parse_oma_content
from core.models.lenses import LensBlank, LensPair, BevelSettings

def register_sidebar_callback(app):
    # OMA File Upload and Input Management Callback
    @app.callback(
        # OUTPUTS:
        Output('store-oma-job', 'data'),       # The Single Source of Truth
        Output('input-fpd', 'value'),          # Sidebar Inputs
        Output('input-dbl', 'value'),
        Output('input-ipd-l', 'value'),
        Output('input-ipd-r', 'value'),
        Output('input-ocht-l', 'value'),
        Output('input-ocht-r', 'value'),
        Output('upload-text', 'children'),   # Upload Box Text
        
        # INPUTS (Triggers):
        Input('upload-oma', 'contents'),       # 1. File Upload
        Input('input-fpd', 'value'),           # 2. User Edits
        Input('input-dbl', 'value'),
        Input('input-ipd-l', 'value'),
        Input('input-ipd-r', 'value'),
        Input('input-ocht-l', 'value'),
        Input('input-ocht-r', 'value'),
        Input('upload-oma', 'filename'),
        
        # STATE:
        State('store-oma-job', 'data'),        # Current Store State
        prevent_initial_call=True
    )
    def manage_state(
        upload_content, fpd, dbl, ipd_l, ipd_r, ocht_l, ocht_r, uploaded_filename,
        current_store_data
    ):

        trigger_id = ctx.triggered_id

        # --- SCENARIO A: NEW FILE UPLOADED ---
        if trigger_id == 'upload-oma':
            if not upload_content:
                return no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update

            # Parse the file
            content_type, content_string = upload_content.split(',')
            decoded = base64.b64decode(content_string).decode('utf-8')
            job = parse_oma_content(decoded)
            
            if not job.is_valid:
                return no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update

            # Return: New Store Data AND New Input Values
            # (We update inputs here so the sidebar reflects the file's data)
            safe_ipd_l = job.left.ipd if job.left else 0
            safe_ipd_r = job.right.ipd if job.right else 0
            safe_ocht_l = job.left.ocht if job.left else 0
            safe_ocht_r = job.right.ocht if job.right else 0

            return (job.to_dict(), job.fpd, 
                    job.dbl, safe_ipd_l, 
                    safe_ipd_r, safe_ocht_l, 
                    safe_ocht_r, [uploaded_filename])

        # --- SCENARIO B: USER EDITED A FIELD ---
        elif current_store_data is not None:
            
            updated_data = current_store_data.copy()
            
            # Helper function to safely convert to float
            def safe_float(val, default=0.0):
                try:
                    return float(val) if val is not None else default
                except (ValueError, TypeError):
                    return default
            
            # Update Common Params
            updated_data['fpd'] = safe_float(fpd)
            updated_data['dbl'] = safe_float(dbl)
            
            # Update Left Eye Params (if it exists)
            if updated_data.get('left'):
                updated_data['left']['ipd'] = safe_float(ipd_l)
                updated_data['left']['ocht'] = safe_float(ocht_l)
                
            # Update Right Eye Params (if it exists)
            if updated_data.get('right'):
                updated_data['right']['ipd'] = safe_float(ipd_r)
                updated_data['right']['ocht'] = safe_float(ocht_r)
                
            # Return: New Store Data ONLY. 
            # We send `no_update` to inputs to keep the cursor stable while typing.
            return (updated_data, no_update,
                    no_update, no_update, 
                    no_update, no_update, 
                    no_update, no_update)

        return no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update
    
    # Lens Blank Parameter Callbacks
    @app.callback(
        Output('store-lenses-data', 'data'),
        
        # Left Eye Inputs
        Input('l-front-curv', 'value'),
        Input('l-back-curv', 'value'),
        Input('l-center-thk', 'value'),
        Input('l-dia', 'value'),
        
        # Right Eye Inputs
        Input('r-front-curv', 'value'),
        Input('r-back-curv', 'value'),
        Input('r-center-thk', 'value'),
        Input('r-dia', 'value')
    )
    def manage_lens_state(l_fc, l_bc, l_ct, l_dia, r_fc, r_bc, r_ct, r_dia):
        # Default fallback values to prevent crashes if fields are empty
        def safe_float(val, default):
            try:
                return float(val) if val is not None else default
            except ValueError:
                return default

        left_lens = LensBlank(
            front_radius=safe_float(l_fc, 600),
            back_radius=safe_float(l_bc, 600),
            center_thickness=safe_float(l_ct, 5),
            diameter=safe_float(l_dia, 70)
        )
        
        right_lens = LensBlank(
            front_radius=safe_float(r_fc, 600),
            back_radius=safe_float(r_bc, 600),
            center_thickness=safe_float(r_ct, 5),
            diameter=safe_float(r_dia, 70)
        )

        pair = LensPair(left=left_lens, right=right_lens)
        return pair.to_dict()
    
    # Bevel Settings Callbacks
    @app.callback(
        Output('store-bevel-settings', 'data'),
        Input('bevel-type-dropdown', 'value'),
        Input('bevel-curve-dropdown', 'value'),
        Input('bevel-ratio-input', 'value'),
        Input('diopter-input', 'value'),
        Input('input-bevel-pos', 'value')
    )
    def manage_bevel_settings(bevel_type, curve_mode, ratio_val, diopter_val, z_shift):
        """
        Consolidates all bevel inputs into the BevelSettings model.
        """
        # 1. Determine the relevant curve value based on mode
        curve_value = 0.0
        
        if curve_mode == 'ratio':
            # Use slider value (default to 50% if None)
            curve_value = float(ratio_val) if ratio_val is not None else 50.0
        elif curve_mode == 'diopter':
            # Use diopter input (default to 0.0 if None)
            try:
                curve_value = float(diopter_val) if diopter_val is not None else 0.0
            except ValueError:
                curve_value = 0.0
        # For 'oma', the value is ignored, so 0.0 is fine
        
        # 2. Parse Z Shift
        try:
            z_shift_mm = float(z_shift) if z_shift is not None else 0.0
        except ValueError:
            z_shift_mm = 0.0

        # 3. Create Model
        settings = BevelSettings(
            type=bevel_type or "vbevel_no_polishing",
            curve_mode=curve_mode or "ratio",
            curve_value=curve_value,
            z_shift_mm=z_shift_mm
        )

        return settings.to_dict()
    
    clientside_callback(
        """
        function(mode) {
            if (mode === 'ratio') {
                // Show Ratio, Hide Diopter
                return [{'display': 'block'}, {'display': 'none'}];
            } 
            else if (mode === 'diopter') {
                // Hide Ratio, Show Diopter
                return [{'display': 'none'}, {'display': 'block'}];
            } 
            else { 
                // OMA (or others): Hide Both
                return [{'display': 'none'}, {'display': 'none'}];
            }
        }
        """,
        Output('bevel-ratio-container', 'style'),   # Output 1
        Output('bevel-diopter-container', 'style'), # Output 2
        Input('bevel-curve-dropdown', 'value')
    )