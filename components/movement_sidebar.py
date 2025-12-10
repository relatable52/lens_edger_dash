import dash_bootstrap_components as dbc
from dash import html, dcc, dash_table


def layout():
    return sidebar

# Roughing Params
roughing_settings = html.Div(
    className="sidebar-section",
    children=[
        dbc.Row([
            dbc.Col(html.H6("Roughing Cycles", className="sidebar-heading"), width=8),
            dbc.Col(
                dbc.Button("+", id="btn-add-roughing", size="sm", className="py-0 px-2"), 
                width=4, className="text-end"
            ),
        ], className="align-items-center mb-1"),
        
        # Method Selector
        dbc.Select(
            id="input-roughing-method",
            options=[
                {"label": "Concentric (Circle)", "value": "CONCENTRIC"},
                {"label": "Interpolation (Morph)", "value": "INTERPOLATION"},
            ],
            value="CONCENTRIC",
            size="sm",
            className="mb-2"
        ),

        # The Table
        dash_table.DataTable(
            id='roughing-table-sidebar',
            columns=[
                {'name': 'Dist', 'id': 'step', 'type': 'numeric', 'editable': True},
                {'name': 'Spd', 'id': 'speed', 'type': 'numeric', 'editable': True},
                {'name': 'Vol', 'id': 'volume', 'type': 'numeric', 'editable': False}, 
            ],
            data=[{'step': 3.0, 'speed': 15, 'volume': 0}],
            row_deletable=True,
            style_table={'overflowX': 'hidden'},
            style_header={'fontSize': '11px', 'fontWeight': 'bold'},
            style_cell={'fontSize': '11px', 'textAlign': 'center'},
        ),
    ]
)

action_buttons = html.Div(
    className="sidebar-footer mt-4",
    children=[
        dbc.Button(
            "Generate Toolpaths", 
            id="btn-gen-path", 
            color="success", 
            size="sm", 
            className="w-100 mb-2 fw-bold"
        ),
        dbc.Button(
            "Download G-Code", 
            id="btn-save", 
            color="secondary", 
            size="sm", 
            className="w-100 border"
        ),
    ]
)

# Main Layout Construction
sidebar = html.Div(
    className="sidebar-container",
    children=[
        # Scrollable Area
        html.Div(
            className="sidebar-content",
            children=[
               roughing_settings
            ]
        ),
        # Sticky Footer
        action_buttons
    ]
)