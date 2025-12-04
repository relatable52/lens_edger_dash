import os

import dash
from dash import html, dcc
import dash_bootstrap_components as dbc

from components import (
    sidebar, 
    two_d_preview_tab,
    three_d_prepare_tab,
    simulation_tab
)
from callbacks import (
    register_preview_callback, 
    register_sidebar_callback, 
    register_simulation_callbacks 
)

# --- APP SETUP ---
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.SPACELAB, "assets/style.css"], external_scripts=[])

# --- CONTROL SIDEBAR (Left Panel) ---
sidebar_content = sidebar.layout()

# --- MAIN TABS AREA ---
tab_1_content = two_d_preview_tab.layout()

tab_2_content = three_d_prepare_tab.layout()

tab_3_content = simulation_tab.layout()

# tab_4_content = dbc.Card(
#     dbc.CardBody([
#         html.H5("Tool Path Simulation"),
#         # Simulation View
#         html.Div(id="vtk-container-simu", style={"height": "60vh", "backgroundColor": "#111"}),
        
#         # Cura-style Player Controls
#         dbc.Row([
#             dbc.Col(dbc.Button("▶", id="sim-play", color="secondary"), width="auto"),
#             # dbc.Col(
#             #     dcc.Slider(
#             #         id="sim-slider", min=0, max=100, step=1, value=0,
#             #         marks={0: 'Start', 30: 'Rough', 70: 'Bevel', 100: 'Finish'},
#             #     ),
#             # )
#         ], class_name="align-items-center mt-3")
#     ]), className="mt-3"
# )

prepare_tab = dbc.Tabs(
    [
        dbc.Tab(tab_1_content, label="2D Layout", label_class_name="small-tab-title", id="tab-2d-preview"),
        dbc.Tab(tab_2_content, label="Estimated 3D View", label_class_name="small-tab-title", id="tab-3d-rough"),
    ], id="prepare-section-tabs"
)

preview_tab = dbc.Tabs(
    [
        dbc.Tab(tab_3_content, label="Motion Simulation", label_class_name="small-tab-title", id="tab-3d-refined"),
        # dbc.Tab(tab_4_content, label="Simulation", label_class_name="small-tab-title", id="tab-simulation"),
    ], id="preview-section-tabs"
)


# --- APP LAYOUT ---
app.layout = dbc.Container([
    dcc.Store(id='store-oma-job'), # Hidden store for OMA Job data
    dcc.Store(id='store-lenses-data'), # Hidden store for lenses data
    dcc.Store(id='store-mesh-cache'), # Hidden store for calculated mesh data
    dcc.Store(id='store-simulation-path'), # Hidden store for full simulation path
    dcc.Interval(id='sim-interval', disabled=True),
    dbc.Row([
        # Sidebar Column
        dbc.Col(sidebar_content, width=3, style={"backgroundColor": "#f8f9fa"}),
        
        # Main Content Column
        dbc.Col([
            dbc.Tabs([
                dbc.Tab(prepare_tab, label="Prepare Design", id="tab-prepare"),
                dbc.Tab(preview_tab, label="Preview & Simulate", id="tab-preview"),
            ], id="main-section-tabs"),
        ], width=9, class_name="p-4")
    ])
], fluid=True)

# --- CALLBACK ---
# Handle both files upload and inputs edits to manage the single source of truth
register_sidebar_callback(app)

# Update the preview based on OMA data and user inputs
register_preview_callback(app)

# Update the simulation
register_simulation_callbacks(app)

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
    app.run(host="0.0.0.0", port=port, debug=False)