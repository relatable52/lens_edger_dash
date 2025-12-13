import dash_bootstrap_components as dbc
from dash import html, dcc, dash_table

# Helper to reduce repetition and ensure consistency
def make_input_group(label, id, placeholder, value=None, container_style={}, **input_props):
    return dbc.InputGroup(
        [   
            dbc.InputGroupText(label, style={"fontSize": "0.75rem"}),
            dbc.Input(
                id=id, 
                placeholder=placeholder, 
                value=value, 
                size="sm", 
                **input_props # Pass extra props like type="number", min=0 here
            ),
        ],
        class_name="mb-2 shadow-sm",
        size="sm",
        style=container_style
    )

def layout():
    return sidebar

# Section: File Upload
file_upload = html.Div(
    className="sidebar-section",
    children=[
        html.H6("Input Data", className="sidebar-heading"),
        dcc.Upload(
            id='upload-oma',
            className='upload-box',
            children=html.Div([
                'Drag & Drop .OMA'
            ], id="upload-text"),
        ),
    ]
)

# Section: Frame Params
frame_parameters = html.Div(
    className="sidebar-section",
    children=[
        html.H6("Frame Parameters", className="sidebar-heading"),
        dbc.Row([
            dbc.Col(make_input_group("FPD", "input-fpd", "70.75"), width=6),
            dbc.Col(make_input_group("DBL", "input-dbl", "18.8"), width=6),
        ]),
        
        # L/R Label
        html.Div("Left / Right Specifics", className="text-muted small mb-1 mt-1"),
        
        # Combined L/R Rows for tightness
        dbc.Row([
            dbc.Col(make_input_group("IPD L", "input-ipd-l", "IPD L"), width=6),
            dbc.Col(make_input_group("IPD R", "input-ipd-r", "IPD R"), width=6),
        ], class_name="g-2 mb-2"), # g-2 = smaller gutter between cols
        
        dbc.Row([
            dbc.Col(make_input_group("OCHT L", "input-ocht-l", "OCHT L"), width=6),
            dbc.Col(make_input_group("OCHT R", "input-ocht-r", "OCHT R"), width=6),
        ], class_name="g-2"),
    ]
)

# Section: Lens Blank
def lens_tab_content(prefix):
    return html.Div([
        make_input_group("Front R", f"{prefix}-front-curv", None, value = 523),
        make_input_group("Back R", f"{prefix}-back-curv", None, value = 87),
        make_input_group("Center Thk", f"{prefix}-center-thk", None, value = 2),
        make_input_group("Diameter", f"{prefix}-dia", None, value = 70),
    ])

lens_blank_parameters = html.Div(
    className="sidebar-section",
    children=[
        html.H6("Lens Blank Definition", className="sidebar-heading"),
        dbc.Tabs([
            dbc.Tab(lens_tab_content("l"), label="Left Eye", tab_style={"fontSize": "0.8rem"}),
            dbc.Tab(lens_tab_content("r"), label="Right Eye", tab_style={"fontSize": "0.8rem"}),
        ], className="nav-fill small-tabs"),
    ]
)

# Section: Bevel
bevel_settings = html.Div(
    className="sidebar-section",
    children=[
        html.H6("Bevel Settings", className="sidebar-heading"),
        
        # A. Bevel Type
        dbc.Label("Bevel Type", html_for="bevel-type-dropdown", className="small text-muted"),
        dcc.Dropdown(
            id="bevel-type-dropdown",
            options=[
                {"label": "Flat without polishing", "value": "flat_no_polishing"},
                {"label": "Flat with polishing", "value": "flat_polishing"},
                {"label": "V-Bevel without polishing", "value": "vbevel_no_polishing"},
                {"label": "V-Bevel with polishing", "value": "vbevel_polishing"},
                {"label": "Groove", "value": "groove"},
            ],
            value="vbevel_no_polishing",
            clearable=False,
            className="mb-3 input-group-text-sm",
        ),

        # B. Curve Mode
        dbc.Label("Bevel Curve", html_for="bevel-curve-dropdown", className="small text-muted"),
        dcc.Dropdown(
            id="bevel-curve-dropdown",
            options=[
                {"label": "Ratio", "value": "ratio"},
                {"label": "Diopter", "value": "diopter"},
                {"label": "From OMA", "value": "oma"},
            ],
            value="ratio",
            clearable=False,
            className="mb-2 input-group-text-sm",
        ),

        # C. Curve Inputs (Ratio & Diopter)
        html.Div(id='bevel-curve-inputs', children=[
            
            # 1. Ratio Input Container (Visible by default)
            html.Div(
                id="bevel-ratio-container",
                children=[
                    make_input_group(
                        "Ratio (%)", "bevel-ratio-input", "50", 
                        value=50, type="number", min=0, max=100, step=1
                    )
                ]
            ),

            # 2. Diopter Input Container (Hidden by default)
            html.Div(
                id="bevel-diopter-container",
                style={"display": "none"}, # Start hidden
                children=[
                    make_input_group(
                        "Diopter", "diopter-input", "0.0", 
                        value=0.0, type="number", step=0.25
                    )
                ]
            )
        ]),

        # D. Vertical Shift
        html.Div([
            dbc.Label("Bevel Shift", html_for="input-bevel-pos", className="small text-muted"),
            make_input_group("Vertical Shift (mm)", "input-bevel-pos", "0.0", type="number")
        ])
    ]
)

# Footer: Actions
action_buttons = html.Div(
    className="sidebar-footer",
    children=[
        dbc.Button("Update Lens Shape", id="btn-update-shape", color="primary", size="sm", className="w-100 mb-2 fw-bold"),
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
                file_upload,
                html.Hr(className="my-3"),
                frame_parameters,
                html.Hr(className="my-3"),
                lens_blank_parameters,
                html.Hr(className="my-3"),
                bevel_settings,
            ]
        ),
        # Sticky Footer
        action_buttons
    ]
)