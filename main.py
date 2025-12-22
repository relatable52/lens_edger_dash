import os

import dash
from dash import html, dcc
import dash_bootstrap_components as dbc

from components import (
    prepare_sidebar,
    movement_sidebar, 
    two_d_preview_tab,
    three_d_prepare_tab,
    simulation_tab,
    roughing_contour_tab
)
from callbacks import (
    register_preview_callback, 
    register_sidebar_callback, 
    register_simulation_callbacks,
    register_roughing_callbacks
)

# --- APP SETUP ---
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.SPACELAB, "assets/style.css"], external_scripts=[])
server = app.server

# --- CONTROL SIDEBAR (Left Panel) ---
prepare_sidebar_content = prepare_sidebar.layout()
movement_sidebar_content = movement_sidebar.layout()

# --- MAIN TABS AREA ---
tab_1_content = two_d_preview_tab.layout()

tab_2_content = three_d_prepare_tab.layout()

tab_3_content = roughing_contour_tab.layout()

tab_4_content = simulation_tab.layout()

prepare_tab = dbc.Row([
    dbc.Col(prepare_sidebar_content, width=3),
    dbc.Col(
        dbc.Tabs(
            [
                dbc.Tab(tab_1_content, label="2D Layout", label_class_name="small-tab-title", id="tab-2d-preview"),
                dbc.Tab(tab_2_content, label="Estimated 3D View", label_class_name="small-tab-title", id="tab-3d-rough"),
            ], id="prepare-section-tabs"
        ),
        width=9, class_name="p-4"
    )
])

preview_tab = dbc.Row([
    dbc.Col(movement_sidebar_content, width=3),
    dbc.Col(
        dbc.Tabs(
            [
                dbc.Tab(tab_3_content, label="Roughing Contour", label_class_name="small-tab-title", id="tab-roughing-contour"),
                dbc.Tab(tab_4_content, label="Motion Simulation", label_class_name="small-tab-title", id="tab-3d-refined"),
            ], id="preview-section-tabs"
        ),
        width=9, class_name="p-4"
    ) 
])


# --- APP LAYOUT ---
app.layout = dbc.Container([
    dcc.Store(id='store-oma-job'), # Hidden store for OMA Job data
    dcc.Store(id='store-lenses-data'), # Hidden store for lenses data
    dcc.Store(id='store-mesh-cache'), # Hidden store for calculated mesh data
    dcc.Store(id='store-bevel-settings'), # Hidden store for bevel settings
    dcc.Store(id='store-simulation-path'), # Hidden store for full simulation path
    dcc.Store(id='store-eye-select', data='L'), # Hidden store for eye selection
    # dcc.Store(id='store-roughing-results'), # Hidden store for roughing results
    dcc.Store(id='store-active-pass', data={'pass_index': 0, 'is_beveling': False}), # Active mesh pass for animation
    dcc.Interval(id='sim-interval', disabled=True, interval=100), # Interval for simulation updates
    dbc.Tabs([
        dbc.Tab(prepare_tab, label="Prepare Design", id="tab-prepare"),
        dbc.Tab(preview_tab, label="Preview & Simulate", id="tab-preview"),
    ], id="main-section-tabs"),
], fluid=True)

# --- CALLBACK ---
# Handle both files upload and inputs edits to manage the single source of truth
register_sidebar_callback(app)

# Update the preview based on OMA data and user inputs
register_preview_callback(app)

# Update the simulation
register_simulation_callbacks(app)

# Handle roughing cycle management
register_roughing_callbacks(app)

# @app.callback(
#     Output("btn-save", "disabled"),
#     Input("btn-gen-path", "n_clicks"),
#     prevent_initial_call=True
# )
# def on_generate(n):
#     # This would trigger the calculation logic
#     return False

if __name__ == "__main__":
    # Get the PORT from the environment (default to 8050 if not set)
    port = int(os.environ.get("PORT", 8050))
    
    # Host must be 0.0.0.0 to be accessible externally
    app.run(host="0.0.0.0", port=port, debug=True)