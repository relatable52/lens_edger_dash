from dash import Input, Output, State

from components import two_d_preview_tab, three_d_prepare_tab
from core.models.lenses import OMAJob, LensPair, LensPairSimulationData, BevelSettings
from .utils.three_d_prepare_logic import calculate_lens_geometry
    
def register_preview_callback(app):

    # Register callback to update 2D preview graph
    @app.callback(
        Output('graph-2d-layout', 'figure'),
        Input('store-oma-job', 'data'),
        prevent_initial_call=True
    )
    def update_2d_graph(data_dict):
        job = OMAJob.from_dict(data_dict) if data_dict else None
        return two_d_preview_tab.render_figure(job)
    
    # Register callback to calculate and cache Lens Pair Simulation Data
    @app.callback(
        Output('store-mesh-cache', 'data'),
        State('store-oma-job', 'data'),
        State('store-lenses-data', 'data'),
        State('store-bevel-settings', 'data'),
        Input('btn-update-shape', 'n_clicks'),
        prevent_initial_call=True
    )
    def calculate_geometry(oma_dict, lens_dict, bevel_settings, n_clicks):
        if not oma_dict or not lens_dict:
            return None
            
        job = OMAJob.from_dict(oma_dict)
        lens_pair = LensPair.from_dict(lens_dict)
        bevel_settings = BevelSettings.from_dict(bevel_settings) if bevel_settings else None
        # This function runs the heavy math once
        return calculate_lens_geometry(job, lens_pair, bevel_settings)
    
    # Register callback to update Lens Blank Preview
    @app.callback(
        Output('vtk-container-3d-prepare', 'children'),
        Output('store-eye-select', 'data'),
        Input('store-mesh-cache', 'data'),
        Input('store-oma-job', 'data'),
        Input('view-eye-select', 'value'),
        prevent_initial_call=True
    )
    def update_3d_view(mesh_cache, oma_job, view_mode):
        lens_pair_sim_data = LensPairSimulationData.from_dict(mesh_cache) if mesh_cache else None
        oma_job = OMAJob.from_dict(oma_job) if oma_job else None
        return three_d_prepare_tab.render_figure(lens_pair_sim_data, oma_job, view_mode), view_mode