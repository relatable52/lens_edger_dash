from core.models.tools import GrindingWheel, ToolStack
from core.geometric.three_d_loader import load_tool_mesh

# Cache the tool mesh so we don't reload disk every frame
TOOL_MESH_CACHE = None
MACHINE_CONFIG = None

def load_machine_config_cached():
    global MACHINE_CONFIG
    if MACHINE_CONFIG is None:
        MACHINE_CONFIG = get_default_machine_config()
    return MACHINE_CONFIG

def load_tool_mesh_cached():
    global TOOL_MESH_CACHE
    global MACHINE_CONFIG
    if TOOL_MESH_CACHE is None:
        machine_config = load_machine_config_cached()
        wheels = machine_config.wheels
        tool_meshes = {}
        for wheel in wheels:
            points, polys = load_tool_mesh(wheel)
            tool_meshes[wheel.tool_id] = (points, polys)
        TOOL_MESH_CACHE = tool_meshes
    return TOOL_MESH_CACHE

def get_default_machine_config():
    """
    Returns the hardcoded configuration of the lens edging machine.
    """
    # Spindle is tilted 15 degrees around Y, Base at (0,0,0)
    tilt = 18.0
    base = [100.0, 0.0, -150.0]
    
    wheels = []
    
    # 1. Roughing Wheel (Glass) - Bottom
    wheels.append(GrindingWheel(
        tool_id="rough_glass",
        name="Roughing (Glass)",
        # Updated to use your real file
        mesh_filename="assets/roughing.vtk", 
        stack_z_offset=10.0,       # Starts 10mm up the shaft
        height=16.8,
        radius_bottom=50.0,
        radius_top=50.0,           # Cylinder
        cutting_radius=63.3,
        cutting_z_relative=8.4    # Middle of the wheel
    ))
    
    # 2. Bevel Wheel (V-Groove) - Middle
    wheels.append(GrindingWheel(
        tool_id="bevel_std",
        name="Standard V-Bevel",
        # Updated to use your real file
        mesh_filename="assets/bevel_rough.vtk",
        stack_z_offset=26.8,       # Stacked above Roughing
        height=17.0,
        radius_bottom=48.0,        # V-shape simulation via cone? 
        radius_top=48.0,           # Actually V-wheels are complex, let's use cylinder viz for now
        cutting_radius=45.0,       # The V-groove is deeper
        cutting_z_relative=7.5
    ))
    
    return ToolStack(tilt, base, wheels)