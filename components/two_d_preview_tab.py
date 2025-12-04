import dash_bootstrap_components as dbc
from dash import html, dcc
import plotly.graph_objects as go

from core.models.lenses import OMAJob
from core.geometric.two_d_generation import get_assembly_contours, get_optical_centers, get_bounding_boxes

def layout():
    """
    Returns the layout for the 2D Preview Tab.
    """
    return dbc.Card(
        dbc.CardBody([
            html.H6("2D Top-Down Preview"),
            dcc.Graph(id="graph-2d-layout", style={"height": "70vh"}) # Plotly Graph
        ]), className="mt-3"
    )

def render_figure(oma_job: OMAJob) -> go.Figure:
    """
    Renders a 2D top-down preview of the lens and frame layout.
    
    Args:
        oma_job (OMAJob): The parsed OMA job data.
    """
    fig = go.Figure()

    if oma_job is None or not oma_job.is_valid:
        fig.update_layout(title="No valid OMA job loaded.")
        return fig
    
    # Get Calculations
    contours = get_assembly_contours(oma_job)
    ocs = get_optical_centers(oma_job, contours)
    bounding_boxes = get_bounding_boxes(oma_job)
    color = {
        "L": "blue",
        "R": "orange"
    }

    # Draw Frames (Left and Right)
    for side, data in contours.items():
        # Frame Shape
        fig.add_trace(go.Scatter(
            x=data['x'], y=data['y'],
            mode='lines',
            name=f'{side} Frame',
            line=dict(color=color[side], width=2)
        ))
        
        # Geometric Center Marker
        cx, cy = data['center']
        fig.add_trace(go.Scatter(
            x=[cx], y=[cy], mode='markers',
            marker=dict(symbol='cross', size=10, color='gray'),
            showlegend=False,
            hoverinfo='text', text=f'{side} Box Center'
        ))

    # Draw Optical Centers (The Pupil position) 
    for side, (px, py) in ocs.items():
        # Marker for Pupil
        fig.add_trace(go.Scatter(
            x=[px], y=[py], mode='markers',
            name=f'{side} Optical Center',
            marker=dict(symbol='circle-cross', size=12, color=color[side], line=dict(width=2))
        ))

    # Bounding box
    for side, (vx,vy, w, h) in bounding_boxes.items():
        fig.add_shape(type="rect",
            x0=vx, y0=vy, x1=vx+w, y1=vy+h,
            line=dict(color="gray", width=1, dash="dash"),
        )

    # Annotations (DBL and FPD)
    # FPD Line  
    fig.add_shape(type="line",
        x0=-oma_job.fpd/2, y0=0, x1=oma_job.fpd/2, y1=0,
        line=dict(color="black", width=2, dash="dot")
    )
    fig.add_annotation(x=0, y=0, text=f"FPD: {oma_job.fpd}mm", showarrow=False, yshift=10)
    
    # DBL Line (Approximate visualization)
    # We assume DBL is the gap between the box edges for visualization
    # Ideally, we calculate min/max x of contours, but simple math is fine for UI
    half_dbl = oma_job.dbl / 2
    fig.add_shape(type="line",
        x0=-half_dbl, y0=-10, x1=half_dbl, y1=-10,
        line=dict(color="black", width=2, dash="dot")
    )
    fig.add_annotation(x=0, y=-10, text=f"DBL: {oma_job.dbl}mm", showarrow=False, yshift=-10)

    # Styling
    fig.update_layout(
        template="plotly_white",
        xaxis=dict(scaleanchor="y", scaleratio=1, title="Width (mm)"), # Lock aspect ratio 1:1
        yaxis=dict(title="Height (mm)"),
        showlegend=True,
        margin=dict(l=20, r=20, t=40, b=20)
    )
    
    return fig