import vtk
from vtkmodules.util import numpy_support
import numpy as np

def generate_truncated_cone(radius_bot, radius_top, height, res=40):
    """ Generates mesh data for a truncated cone (Grinding Wheel). """
    points = []
    polys = []
    
    angles = np.linspace(0, 2*np.pi, res, endpoint=False)
    cos_a = np.cos(angles)
    sin_a = np.sin(angles)
    
    # 1. Generate Points
    # Bottom Ring (Indices 0 to res-1)
    for i in range(res):
        points.extend([radius_bot * cos_a[i], radius_bot * sin_a[i], 0.0])
        
    # Top Ring (Indices res to 2*res-1)
    for i in range(res):
        points.extend([radius_top * cos_a[i], radius_top * sin_a[i], height])
        
    # Caps Centers
    center_bot = len(points) // 3
    points.extend([0, 0, 0])
    center_top = center_bot + 1
    points.extend([0, 0, height])
    
    # 2. Generate Polys
    # Side Walls
    for i in range(res):
        next_i = (i + 1) % res
        b_curr = i
        b_next = next_i
        t_curr = i + res
        t_next = next_i + res
        
        # Two triangles for the quad
        polys.extend([3, b_curr, b_next, t_curr])
        polys.extend([3, b_next, t_next, t_curr])
        
    # Bottom Cap (Fan)
    for i in range(res):
        next_i = (i + 1) % res
        polys.extend([3, center_bot, next_i, i]) # Winding?
        
    # Top Cap (Fan)
    for i in range(res):
        next_i = (i + 1) % res
        polys.extend([3, center_top, i + res, next_i + res])
        
    return points, polys

def load_tool_mesh(wheel_obj):
    """
    Returns (points, polys) for a specific GrindingWheel object.
    """
    if wheel_obj.mesh_filename == "generated":
        return generate_truncated_cone(
            wheel_obj.radius_bottom, 
            wheel_obj.radius_top, 
            wheel_obj.height
        )
    
    # Load from VTK file
    reader = vtk.vtkPolyDataReader()
    reader.SetFileName(wheel_obj.mesh_filename)
    reader.Update()
    polydata = reader.GetOutput()
    points_vtk = polydata.GetPoints().GetData()
    polys_vtk = polydata.GetPolys().GetData()
    points = numpy_support.vtk_to_numpy(points_vtk).flatten().tolist()
    polys = numpy_support.vtk_to_numpy(polys_vtk).flatten().tolist()
    return points, polys