import dash_bootstrap_components as dbc
from dash import html, dcc

# 1. Helper to reduce repetition and ensure consistency
def make_input_group(label, id, placeholder, value=None):
    return dbc.InputGroup(
        [   
            dbc.InputGroupText(label, style={"fontSize": "0.75rem"}),
            dbc.Input(id=id, type="number", placeholder=placeholder, value=value, size="sm"),
        ],
        class_name="mb-2 shadow-sm",
        size="sm"
    )

def layout():
    return sidebar

# 2. Section: File Upload
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

# 3. Section: Frame Params
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

# 4. Section: Lens Blank
def lens_tab_content(prefix):
    return html.Div([
        make_input_group("Front R", f"{prefix}-front-curv", None, value = 1000),
        make_input_group("Back R", f"{prefix}-back-curv", None, value = 500),
        make_input_group("Center Thk", f"{prefix}-center-thk", None, value = 3),
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

# 5. Section: Bevel
bevel_settings = html.Div(
    className="sidebar-section",
    children=[
        html.H6("Bevel Settings (only frame curve for now)", className="sidebar-heading"),
        html.Label("Bevel Shift", className="small text-muted mt-1"),
        dcc.Slider(
            id="input-bevel-pos",
            min=0, max=100, step=5, value=50,
            marks={0: 'Front', 100: 'Back'},
            tooltip={"placement": "bottom", "always_visible": True}
        )
    ]
)

# 6. Footer: Actions
action_buttons = html.Div(
    className="sidebar-footer",
    children=[
        dbc.Button("Generate Paths", id="btn-gen-path", color="primary", size="sm", className="w-100 mb-2 fw-bold"),
        dbc.Button("Download G-Code", id="btn-save", color="light", size="sm", className="w-100 border"),
    ]
)

# 7. Main Layout Construction
sidebar = html.Div(
    id="sidebar-container",
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