import dash_bootstrap_components as dbc
import dash_vtk
from dash import html

from core.models.lenses import LensSimulationData, LensPairSimulationData, OMAJob

controls = dbc.Row([
    dbc.Col(html.H6("3D Estimation View")),
    dbc.Col(dbc.RadioItems(
        options=[
            {"label": "Left", "value": "L"}, 
            {"label": "Right", "value": "R"},
        ],
        value="L", 
        id="view-eye-select", 
        inline=True,
        inputClassName="btn-check",
        labelClassName="btn btn-outline-primary btn-sm",
        labelCheckedClassName="active"
    ), width="auto")
], class_name="mb-2 align-items-center")

view_container = html.Div(
    id="vtk-container-3d-prepare", 
    style={
        "height": "70vh", 
        "width": "100%",
    }
)

main_tab_content = dbc.Card(
    dbc.CardBody([
        controls,
        view_container
    ]), className="mt-3"
)

def layout():
    """Returns the layout of the rough 3D view.
    """
    return main_tab_content

def render_figure(lens_pair_simulation_data: LensPairSimulationData, oma_job: OMAJob, view_mode="L"):
    """
    Renders the scene using pre-calculated geometry from the Store.
    """
    if not lens_pair_simulation_data or not oma_job:
        return html.Div("Waiting for geometry calculation...", className="text-muted p-4")

    children_views = []
    
    # Helper to create actors from data object
    def create_actors_from_data(lens_simulation_data: LensSimulationData, transform_x=0):
        if not lens_simulation_data: return []
        
        data = lens_simulation_data
        actors = []
        
        # 1. Blank Actor (Transparent)
        if view_mode != "Assembly":
            actors.append(
                dash_vtk.GeometryRepresentation(
                    actor={"position": [transform_x, 0, 0]},
                    property={"edgeVisibility": False, "color": [0.8, 0.8, 0.9], "opacity": 0.15},
                    children=[
                        dash_vtk.PolyData(points=data.blank_mesh.points, polys=data.blank_mesh.polys)
                    ]
                )
            )
            
        # 2. Cut Lens Actor (Solid)
        color = [0.2, 0.6, 1.0] if data.side == "L" else [1.0, 0.6, 0.2]
        actors.append(
            dash_vtk.GeometryRepresentation(
                actor={"position": [transform_x, 0, 0]},
                property={"edgeVisibility": False, "color": color, "opacity": 1.0, "specular": 0.5, "specularPower": 20},
                children=[
                    dash_vtk.PolyData(points=data.cut_mesh.points, polys=data.cut_mesh.polys)
                ]
            )
        )
        
        # 3. Bevel Line Actor
        # Generate line indices [2, i, i+1]
        bev_pts = data.bevel_data.points
        n_bev = len(bev_pts) // 3
        bev_lines = []
        for i in range(n_bev):
            bev_lines.extend([2, i, (i + 1) % n_bev])
            
        actors.append(
            dash_vtk.GeometryRepresentation(
                actor={"position": [transform_x, 0, 0], "lineWidth": 4},
                mapper={"colorByArrayName": "RGBColor", "scalarMode": 3},
                children=[
                    dash_vtk.PolyData(
                        points=bev_pts, lines=bev_lines,
                        children=[
                            dash_vtk.PointData([
                                dash_vtk.DataArray(
                                    name="RGBColor", numberOfComponents=3,
                                    values=data.bevel_data.status_colors, type='Uint8Array'
                                )
                            ])
                        ]
                    )
                ]
            )
        )
        return actors

    # --- Scene Logic ---
    fpd_offset = oma_job.fpd / 2.0 if oma_job and oma_job.fpd else 70.0
    
    if view_mode == "Assembly":
        children_views.extend(create_actors_from_data(lens_pair_simulation_data.right, transform_x=fpd_offset))
        children_views.extend(create_actors_from_data(lens_pair_simulation_data.left, transform_x=-fpd_offset))
    elif view_mode == "L":
        children_views.extend(create_actors_from_data(lens_pair_simulation_data.left))
    elif view_mode == "R":
        children_views.extend(create_actors_from_data(lens_pair_simulation_data.right))

    return dash_vtk.View(
        background=[0.25, 0.25, 0.25],
        cameraPosition=[0, -100, 50],
        cameraViewUp=[0, 0, 1],
        children=children_views,
        style={"width": "100%", "height": "100%"}
    )