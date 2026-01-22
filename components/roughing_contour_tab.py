import dash_bootstrap_components as dbc
from dash import html, dcc
import plotly.graph_objects as go
import numpy as np


def layout():
    """
    Returns the layout for the Roughing Contour Tab.
    """
    return dbc.Card(
        dbc.CardBody([
            html.H6("Roughing Contour (2D Top-Down)"),
            dcc.Graph(id="graph-roughing-contour", style={"height": "70vh"})
        ]), className="mt-3"
    )


def render_figure(roughing_results: list, oma_job_data: dict = None, eye_select: str = 'L') -> go.Figure:
    """
    Renders a 2D top-down view of the lens shape after each roughing pass.
    Also plots the final lens shape as a reference.
    
    Args:
        roughing_results: List of dicts from store-roughing-results, each containing:
                         - pass_index: int
                         - radii: list of radius values at uniform angles
                         - volume: float
        oma_job_data: OMA job dict containing the final lens shape (left eye radii)
    """
    fig = go.Figure()
    
    if not roughing_results:
        fig.update_layout(title="No roughing results. Click 'Update Roughing' to calculate.")
        return fig
    
    # Color scheme for passes
    colors = [
        "#1f77b4",  # blue
        "#ff7f0e",  # orange
        "#2ca02c",  # green
        "#d62728",  # red
        "#9467bd",  # purple
        "#8c564b",  # brown
        "#e377c2",  # pink
        "#7f7f7f",  # gray
    ]
    
    # Plot final lens shape first (so it appears in background)
    # if oma_job_data:
    #     try:
    #         from core.models.lenses import OMAJob
    #         oma_job = OMAJob.from_dict(oma_job_data)
    #         if oma_job and oma_job.left:
    #             final_radii = np.array(oma_job.left.radii) if eye_select == 'L' else np.array(oma_job.right.radii)
    #             num_points = len(final_radii)
    #             angles = np.linspace(0, 2*np.pi, num_points, endpoint=False)
                
    #             x_final = final_radii * np.cos(angles)
    #             y_final = final_radii * np.sin(angles)
                
    #             # Close the loop
    #             x_final = np.append(x_final, x_final[0])
    #             y_final = np.append(y_final, y_final[0])
                
    #             fig.add_trace(go.Scatter(
    #                 x=x_final,
    #                 y=y_final,
    #                 mode='lines',
    #                 name='Final Lens Shape',
    #                 line=dict(color="black", width=3, dash="dash"),
    #                 hovertemplate='<b>Final Lens Shape</b><br>X: %{x:.2f} mm<br>Y: %{y:.2f} mm<extra></extra>'
    #             ))
    #     except Exception as e:
    #         print(f"Warning: Could not plot final lens shape: {e}")
    
    # Plot each roughing pass
    for i, result in enumerate(roughing_results):
        if not result or 'radii' not in result:
            continue
        
        radii = np.array(result.get('radii', []))
        pass_index = result.get('pass_index', i + 1)
        volume = result.get('volume', 0)
        
        if len(radii) == 0:
            continue
        
        # Convert polar (radii, angles) to cartesian (x, y)
        num_points = len(radii)
        angles = np.linspace(0, 2*np.pi, num_points, endpoint=False)
        
        x = radii * np.cos(angles)
        y = radii * np.sin(angles)
        
        # Close the loop
        x = np.append(x, x[0])
        y = np.append(y, y[0])
        
        color = colors[i % len(colors)]
        
        fig.add_trace(go.Scatter(
            x=x,
            y=y,
            mode='lines',
            name=f'Pass {pass_index if pass_index < len(roughing_results) else "Final"} (Vol: {volume:.1f} mm³)',
            line=dict(color=color, width=2),
            hovertemplate='<b>Pass %{fullData.name}</b><br>X: %{x:.2f} mm<br>Y: %{y:.2f} mm<extra></extra>'
        ))
    
    fig.update_layout(
        template="plotly_white",
        title="Roughing Pass Contours (Top-Down View)",
        xaxis=dict(title="X (mm)", scaleanchor="y", scaleratio=1),
        yaxis=dict(title="Y (mm)"),
        showlegend=True,
        hovermode='closest',
        margin=dict(l=50, r=50, t=50, b=50)
    )
    
    return fig
