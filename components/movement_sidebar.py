import dash_bootstrap_components as dbc
from dash import html, dcc, dash_table


def layout():
    return sidebar


# ============================================================================
# ROUGHING SETTINGS TABLE
# ============================================================================
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
        dbc.Row([
            dbc.Col([
                html.Label("Method:", className="form-label fw-bold", style={"fontSize": "11px"}),
                dbc.Select(
                    id="input-roughing-method",
                    options=[
                        {"label": "Concentric (Circle)", "value": "CONCENTRIC"},
                        {"label": "Interpolation (Morph)", "value": "INTERPOLATION"},
                    ],
                    value="CONCENTRIC",
                    size="sm",
                )
            ], width=12)
        ], className="mb-2"),

        # The Table
        dash_table.DataTable(
            id='roughing-table-sidebar',
            columns=[
                {'name': 'Pass', 'id': 'pass_index', 'type': 'numeric', 'editable': False, 'presentation': 'markdown'},
                {'name': 'Step (mm)', 'id': 'step', 'type': 'numeric', 'editable': True},
                {'name': 'Speed (s/rev)', 'id': 'speed', 'type': 'numeric', 'editable': True},
            ],
            data=[
                {'pass_index': 1, 'step': 3.0, 'speed': 15}
            ],
            row_deletable=True,
            row_selectable=False,
            style_table={
                'overflowX': 'auto',
                'maxHeight': '250px',
                'overflowY': 'auto'
            },
            style_header={
                'fontSize': '10px',
                'fontWeight': 'bold',
                'backgroundColor': '#f8f9fa',
                'textAlign': 'center',
                'borderBottom': '2px solid #dee2e6'
            },
            style_cell={
                'fontSize': '11px',
                'textAlign': 'center',
                'padding': '6px',
                'minWidth': '50px'
            },
            style_cell_conditional=[
                {
                    'if': {'column_id': 'pass_index'},
                    'backgroundColor': '#f8f9fa',
                    'fontWeight': 'bold'
                }
            ],
            style_data={
                'border': '1px solid #dee2e6'
            }
        ),
        
        # Info box
        html.Div(
            className="mt-2 p-2",
            style={
                'backgroundColor': '#f0f7ff',
                'border': '1px solid #b3d9ff',
                'borderRadius': '4px',
                'fontSize': '10px',
                'color': '#004085'
            },
            children=[
                html.P(
                    "Step: Distance from previous contour. Speed: Processing speed. Volume: Material removed per pass.",
                    className="mb-0"
                )
            ]
        ),

        # Hidden stores
        dcc.Store(id='store-roughing-data', data={'method': 'CONCENTRIC', 'passes': []}),
        dcc.Store(id='store-roughing-results', data=[])  # Stores RoughingPassData results from mesh calculation
    ]
)

action_buttons = html.Div(
    className="sidebar-footer mt-4",
    children=[
        dbc.Button(
            "Update Roughing", 
            id="btn-update-roughing", 
            color="primary", 
            size="sm", 
            className="w-100 border"
        ),
        dbc.Button(
            "Generate Toolpaths", 
            id="btn-gen-path", 
            color="primary", 
            size="sm", 
            className="w-100 mb-2 fw-bold"
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