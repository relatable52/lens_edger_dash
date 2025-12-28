import dash_vtk
from dash import html, dcc
import dash_bootstrap_components as dbc

def layout():
    """Returns the layout of the simulation tab."""
    return dbc.Card(
        dbc.CardBody([
            html.H6("3D Volume Simulation View"),
            # Volume Container - will be populated by clientside callback
            html.Div(
                id='volume-container-removal', 
                style={
                    "height": "60vh", 
                    "width": "100%",
                    "borderRadius": "4px",
                    "overflow": "hidden",
                    "backgroundColor": "#1a1a1a"
                }
            ),
            # Hidden store for volume data
            dcc.Store(id='store-lens-volume'),
            # Controls
            dbc.Row([
                dbc.Col(dbc.Button("Play/Pause", id="removal-sim-play", color="primary", size="sm"), width="auto"),
                dbc.Col(
                    dcc.Slider(
                        id="removal-sim-slider", min=0, max=100, step=1, value=0,
                        marks=None,
                        tooltip={"placement": "bottom", "always_visible": True}
                    ),
                    className="pt-2"
                )
            ], class_name="align-items-center mt-3 bg-light p-2 rounded")
        ]), className="mt-3"
    )