# Volume Simulation - Technical Reference

## Function Documentation

### `generate_lens_volume()`

**Purpose**: Generate the initial lens blank as a volumetric SDF representation.

**Parameters**:
- `front_radius` (float): Front surface radius in mm (positive = convex)
- `back_radius` (float): Back surface radius in mm (positive = concave/meniscus)
- `center_thickness` (float): Lens thickness at center in mm
- `diameter_mm` (float): Maximum lens diameter in mm
- `resolution` (float): Voxel size in mm (default 0.5)

**Returns**: `LensVolumeData` object

**Algorithm**:

```python
# 1. Calculate bounding box
xy_size = diameter_mm + 1  # Add margin
z_size = back_radius - sqrt(back_radius² - (diameter/2)²) + center_thickness + 1

# 2. Create voxel grid
nx = ceil(xy_size / resolution)
nz = ceil(z_size / resolution)

# 3. Set origin (center XY, bottom Z)
origin = [-nx*resolution/2, -ny*resolution/2, 0]

# 4. For each voxel (x, y, z):
for each point in grid:
    # Calculate distances to each primitive
    dist_cylinder = sqrt(x² + y²) - diameter/2
    dist_front_sphere = sqrt(x² + y² + (z - z_front)²) - front_radius
    dist_back_sphere = back_radius - sqrt(x² + y² + (z - z_back)²)
    
    # Intersection SDF
    max_dist = max(dist_cylinder, dist_front_sphere, dist_back_sphere)
    
    # Map to scalar (0-1000)
    if max_dist < -smooth_edge:
        scalar = 1000.0  # Inside
    elif max_dist > smooth_edge:
        scalar = 0.0     # Outside
    else:
        scalar = 1000.0 * (1 - (max_dist + smooth_edge)/(2*smooth_edge))
```

**Key Points**:
- Uses **max** operator for SDF intersection (all conditions must be satisfied)
- Scalars encode material presence (1000) vs air (0)
- Optional smooth edge for anti-aliasing (currently disabled: `smooth_edge = 0`)

---

### `compute_voxel_death_times()`

**Purpose**: Simulate machining by determining when each voxel is removed.

**Parameters**:
- `voxels` (ndarray): 3D array (Z, Y, X) of initial blank scalars
- `voxel_res` (float): Voxel size in mm
- `tool_path` (dict): Tool trajectory with keys:
  - `'x'`, `'z'`, `'theta'`: Position arrays
  - `'time'`: Time array
  - `'pass_segments'`: List of pass metadata
- `tool_stack` (ToolStack): Tool configuration with wheels and tilt

**Returns**: `death_times` (ndarray) - Same shape as input, values are frame-based scalars (0-1000)

**Algorithm**:

#### Step 1: Initialize Death Times
```python
death_times = voxels.copy()  # Start with blank state
num_steps = len(tool_path['time'])
```

#### Step 2: Build Profile Interpolators

For each wheel in the tool stack, create a function `f(h) → radial_offset`:

```python
profile_data = {
    "bevel_std": [
        [-1.797,  9.045],  # [radial_offset, axial_height]
        [0.678,  1.427],
        [0.0, -0.371],     # Cutting edge (apex)
        [1.604, -1.427],
        [4.097, -9.045]
    ],
    "rough_glass": [[-3.09, 9.51], [3.09, -9.51]]
}

# Create interpolator: height → radial offset
profile_funcs[wheel_id] = interp1d(
    profile[:, 1],  # Y (height)
    profile[:, 0],  # Z (radial offset)
    kind='linear',
    bounds_error=False,
    fill_value=-1e9  # Outside profile = no cut
)
```

#### Step 3: Create Coordinate Grid

```python
nz, ny, nx = voxels.shape
z_coords = np.arange(nz) * voxel_res
y_coords = (np.arange(ny) - ny//2) * voxel_res
x_coords = (np.arange(nx) - nx//2) * voxel_res

Z_grid, Y_grid, X_grid = np.meshgrid(z_coords, y_coords, x_coords, indexing='ij')

# Flatten to vectors for vectorized operations
points = np.vstack([X_grid.ravel(), Y_grid.ravel(), Z_grid.ravel()])
```

#### Step 4: Iterate Over Time Steps

```python
for i in range(0, num_steps, step_size):  # Skip frames for speed
    # Extract tool position
    r_mach = tool_stack.base_position[0] - tool_path['x'][i]
    z_mach = tool_stack.base_position[2] - tool_path['z'][i]
    theta_lens = -radians(tool_path['theta'][i])
    
    # Determine active wheel from pass_segments
    active_wheel = get_active_wheel(i, tool_path['pass_segments'])
    if not active_wheel: continue
```

#### Step 5: Coordinate Transformation

```python
# A. Rotate tool position into lens frame
cos_t = cos(-theta_lens)
sin_t = sin(-theta_lens)

tool_pos_x = r_mach * cos_t
tool_pos_y = r_mach * sin_t
tool_pos_z = z_mach

tool_origin = np.array([[tool_pos_x], [tool_pos_y], [tool_pos_z]])

# B. Vector from tool to each voxel
V_vec = points - tool_origin  # Broadcasting: (3, N) - (3, 1)

# C. Rotate tool axis vector
tilt_rad = radians(tool_stack.tilt_angle_deg)
tool_axis_base = np.array([-sin(tilt_rad), 0, cos(tilt_rad)])

axis_rot_x = tool_axis_base[0] * cos_t - tool_axis_base[1] * sin_t
axis_rot_y = tool_axis_base[0] * sin_t + tool_axis_base[1] * cos_t
axis_rot_z = tool_axis_base[2]

current_tool_axis = np.array([[axis_rot_x], [axis_rot_y], [axis_rot_z]])
```

#### Step 6: Project onto Tool Axis

```python
# Height along tool axis
h_vals = (V_vec[0,:] * current_tool_axis[0] + 
          V_vec[1,:] * current_tool_axis[1] + 
          V_vec[2,:] * current_tool_axis[2])

# Radial distance from tool axis
dist_sq = V_vec[0,:]**2 + V_vec[1,:]**2 + V_vec[2,:]**2
d_vals = sqrt(max(0, dist_sq - h_vals**2))
```

**Geometric Explanation**:
- `V_vec`: 3D vector from tool origin to voxel
- `h_vals`: Projection of V onto tool axis (scalar)
- `d_vals`: Perpendicular distance to tool axis (Pythagorean theorem)

```
         Voxel (P)
        /|
       / |
      /  | d (radial distance)
     /   |
    /θ   |
Tool-----+------ Tool Axis
Origin   |
         |
         h (axial position)
```

#### Step 7: Profile Collision Check

```python
# Adjust h for wheel offsets
eff_h = h_vals - (active_wheel.stack_z_offset + active_wheel.cutting_z_relative)

# Get radial offset from profile at this height
prof_z_offsets = profile_funcs[active_wheel.tool_id](eff_h)

# Calculate tool surface radius at this height
tool_surface_radii = active_wheel.cutting_radius + prof_z_offsets

# Check collision
cut_mask = d_vals - tool_surface_radii
cut_mask = np.clip(cut_mask, a_min=-0.1, a_max=0.1)

# Convert to frame-based scalar
cut_mask = (1 - cut_mask/0.1)/2 * (num_steps - i + 0.5)
```

**Collision Logic**:
- `d_vals < tool_surface_radii`: Voxel is inside tool → CUT
- Uses soft threshold (`±0.1 mm`) for smooth transitions
- Encodes frame index as scalar value (0-1000 range)

#### Step 8: Update Death Times

```python
# Reshape mask to 3D grid
cut_mask_3d = cut_mask.reshape(voxels.shape)

# Calculate frame-based time for this step
current_step_times = 1000 - (cut_mask_3d / num_steps) * 1000

# Update with minimum (earliest cut time wins)
death_times = np.minimum(death_times, current_step_times)
```

**Result**: Each voxel now contains the frame index (normalized to 0-1000) when it was first cut.

---

### `compute_volume_history()`

**Purpose**: Calculate material remaining and removed at each time step.

**Parameters**:
- `death_times` (ndarray): 3D array of voxel death times
- `time_array` (ndarray): Time values to evaluate at
- `voxel_volume_mm3` (float): Volume of one voxel (resolution³)

**Returns**: Dictionary with keys:
- `'time'`: Time array (copy of input)
- `'volume_remaining'`: Remaining volume in mm³ at each time
- `'volume_removed'`: Removed volume in mm³ at each time
- `'percentage_complete'`: Completion percentage at each time

**Algorithm**:

```python
# Calculate total workpiece volume
workpiece_voxels = np.sum(death_times < 1000)
initial_volume = workpiece_voxels * voxel_volume_mm3

volume_remaining = []
for t in time_array:
    # Count voxels still alive (not yet cut)
    remaining_voxels = np.sum(death_times > t)
    vol_remaining = remaining_voxels * voxel_volume_mm3
    vol_removed = initial_volume - vol_remaining
    
    volume_remaining.append(vol_remaining)
    volume_removed.append(vol_removed)
    percentage_complete.append((vol_removed / initial_volume) * 100)
```

**Interpretation**:
- `death_times > t`: Voxel hasn't been cut yet at time t
- `death_times ≤ t`: Voxel has been removed by time t
- `death_times >= 1000`: Never part of workpiece (blank exterior)

---

### `calculate_volume_removal_rates()`

**Purpose**: Calculate instantaneous volume removal rate at each frame.

**Parameters**:
- `death_times` (ndarray): Frame-based death times (0-1000)
- `time_array` (ndarray): Time value for each frame
- `voxel_volume_mm3` (float): Voxel volume
- `pass_segments` (list): Pass metadata with `max_volume_rate` constraints

**Returns**: Dictionary with:
- `'frame_indices'`: Frame index array
- `'volume_removed_per_frame'`: Volume cut at each frame (mm³)
- `'max_allowed_rate'`: Maximum rate constraint at each frame (mm³/s)

**Algorithm**:

```python
num_frames = len(time_array)

# Convert death times (0-1000) to frame indices (0-num_frames)
death_frame_indices = (death_times / 1000) * num_frames

# Exclude uncut voxels
cut_mask = death_frame_indices < num_frames
death_frame_indices_cut = death_frame_indices[cut_mask]

# Histogram: count voxels cut in each frame
bin_edges = np.arange(num_frames + 1)
voxel_counts, _ = np.histogram(death_frame_indices_cut.flatten(), bins=bin_edges)

# Convert to volume
volume_per_frame = voxel_counts * voxel_volume_mm3

# Assign max rate per frame from pass_segments
max_allowed_rate = np.full(num_frames, 100.0)  # Default

for segment in pass_segments:
    start = segment['start_idx']
    end = segment['end_idx']
    max_vol = segment.get('max_volume_rate', 100.0)
    max_allowed_rate[start:end+1] = max_vol
```

**Use Case**: Detect if tool is removing material too fast, which could cause:
- Tool breakage
- Poor surface finish
- Machine overload

---

### `adjust_time_array_for_volume_constraints()`

**Purpose**: Slow down tool motion to respect volume removal rate limits.

**Parameters**:
- `time_array` (ndarray): Original time values
- `volume_per_frame` (ndarray): Volume removed per frame
- `max_allowed_rate` (ndarray): Maximum rate per frame (mm³/s)

**Returns**: `adjusted_time` (ndarray) - Modified time array

**Algorithm**:

```python
adjusted_time = np.zeros(num_frames)

for i in range(num_frames):
    if i == 0:
        adjusted_time[i] = 0.0
        continue
    
    # Original time step
    original_dt = time_array[i] - time_array[i-1]
    
    # Actual removal rate with original timing
    if original_dt > 0:
        actual_rate = volume_per_frame[i] / original_dt
    else:
        actual_rate = 0.0
    
    # Check constraint
    max_rate = max_allowed_rate[i]
    
    if actual_rate > max_rate and max_rate > 0:
        # Slow down: increase time to reduce rate
        required_dt = volume_per_frame[i] / max_rate
        adjusted_time[i] = adjusted_time[i-1] + required_dt
    else:
        # Keep original timing
        adjusted_time[i] = adjusted_time[i-1] + original_dt

return adjusted_time
```

**Example**:
- Original: Remove 50 mm³ in 0.2 seconds → 250 mm³/s
- Constraint: Max 100 mm³/s
- Adjusted: Remove 50 mm³ in 0.5 seconds → 100 mm³/s ✓

**Effect**: Stretches out the time axis during high-removal sections, effectively reducing feed rate.

---

### `generate_machined_lens_volume()`

**Purpose**: Complete workflow combining blank generation and machining simulation.

**Parameters**:
- Lens geometry parameters (front_radius, back_radius, etc.)
- `tool_path` (dict): Complete tool trajectory
- `tool_stack` (ToolStack): Tool configuration
- `resolution` (float): Voxel size

**Returns**: `LensVolumeData` with machined lens scalars

**Workflow**:

```python
def generate_machined_lens_volume(...):
    # Step 1: Generate blank
    blank_data = generate_lens_volume(
        front_radius, back_radius, center_thickness, 
        diameter_mm, resolution
    )
    
    # Step 2: Reshape to 3D grid
    nx, ny, nz = blank_data.dimensions
    voxels = np.array(blank_data.scalars).reshape((nz, ny, nx))
    
    # Step 3: Simulate machining (compute death times)
    machined_voxels = compute_voxel_death_times(
        voxels=voxels,
        voxel_res=resolution,
        tool_path=tool_path,
        tool_stack=tool_stack
    )
    
    # Step 4: Return as LensVolumeData
    return LensVolumeData(
        dimensions=blank_data.dimensions,
        spacing=blank_data.spacing,
        origin=blank_data.origin,
        scalars=machined_voxels.flatten().tolist()
    )
```

**Usage Pattern**:
```python
# Generate simulation
volume_data = generate_machined_lens_volume(
    front_radius=100.0,
    back_radius=150.0,
    center_thickness=5.0,
    diameter_mm=80.0,
    tool_path=my_tool_path,
    resolution=0.5
)

# Pass to VTK for rendering
vtk_volume = create_vtk_image_data(volume_data)
```

---

## Data Structures

### `LensVolumeData`

Dataclass for volumetric data compatible with VTK.

```python
@dataclass
class LensVolumeData:
    dimensions: list   # [nx, ny, nz] voxel counts
    spacing: list      # [dx, dy, dz] physical size per voxel (mm)
    origin: list       # [x0, y0, z0] grid start position (mm)
    scalars: list      # Flattened array, C-order: X varies fastest
```

**VTK Integration**:
```python
vtk_image = vtk.vtkImageData()
vtk_image.SetDimensions(dimensions)
vtk_image.SetSpacing(spacing)
vtk_image.SetOrigin(origin)

scalars_vtk = vtk.vtkFloatArray()
scalars_vtk.SetNumberOfComponents(1)
for value in scalars:
    scalars_vtk.InsertNextValue(value)
vtk_image.GetPointData().SetScalars(scalars_vtk)
```

### Tool Path Dictionary

Expected structure:

```python
tool_path = {
    'x': [x0, x1, x2, ...],      # Radial position (mm)
    'z': [z0, z1, z2, ...],      # Axial position (mm)
    'theta': [θ0, θ1, θ2, ...],  # Angular position (degrees)
    'time': [t0, t1, t2, ...],   # Time stamps (seconds)
    'pass_segments': [
        {
            'start_idx': 0,
            'end_idx': 1000,
            'operation_type': 'roughing',
            'max_volume_rate': 100.0  # mm³/s
        },
        {
            'start_idx': 1001,
            'end_idx': 2500,
            'operation_type': 'beveling',
            'max_volume_rate': 20.0
        },
        ...
    ]
}
```

### Tool Stack Configuration

From `ToolStack` class in `core/models/tools.py`:

```python
tool_stack = ToolStack(
    base_position=[r_base, 0, z_base],  # Machine coordinates
    tilt_angle_deg=18.0,                 # Tool tilt toward lens axis
    wheels=[
        Wheel(
            tool_id="rough_glass",
            cutting_radius=50.0,         # mm
            stack_z_offset=0.0,          # Offset in stack
            cutting_z_relative=0.0       # Cutting edge position
        ),
        Wheel(
            tool_id="bevel_std",
            cutting_radius=38.0,
            stack_z_offset=30.0,
            cutting_z_relative=-5.0
        )
    ]
)
```

---

## Mathematical Derivations

### SDF Intersection Formula

For multiple implicit surfaces with SDFs `d₁, d₂, d₃`:

- **Union** (OR): `d = min(d₁, d₂, d₃)`
  - Point inside if inside ANY surface
  
- **Intersection** (AND): `d = max(d₁, d₂, d₃)`
  - Point inside if inside ALL surfaces
  
- **Subtraction** (A - B): `d = max(d₁, -d₂)`
  - Point inside A but NOT inside B

**Lens Blank Example**:
```
Lens = Cylinder ∩ Front_Sphere ∩ (NOT Back_Sphere)
     = Cylinder ∩ Front_Sphere ∩ (Back_Sphere inverted)

d_final = max(d_cyl, d_front, d_back_inverted)
```

Where `d_back_inverted = -d_back_standard = radius - distance`.

### Voxel-Tool Distance Calculation

Given:
- Tool origin: **O**
- Tool axis (unit vector): **â**
- Voxel position: **P**

Calculate distance from **P** to the tool axis line:

```
V = P - O                    (Vector from tool to voxel)
h = V · â                    (Projection onto axis)
d² = |V|² - h²               (Perpendicular distance²)
d = √(|V|² - h²)
```

**Proof** (Pythagorean theorem):
```
|V|² = h² + d²

Where:
- |V| = total distance from O to P
- h = component along axis
- d = component perpendicular to axis
```

### Profile Radius Calculation

The tool surface is defined by:
```
Surface_Radius(h) = Cutting_Radius + Profile_Offset(h)
```

Where:
- `Cutting_Radius`: Nominal tool radius (e.g., 50 mm)
- `Profile_Offset(h)`: Deviation from nominal at height h (from wheel profile)

For a V-bevel:
- At apex: `Profile_Offset = 0` → Surface_Radius = Cutting_Radius
- At shoulder: `Profile_Offset = +0.678 mm` → slightly larger radius
- Outside profile: `Profile_Offset = -∞` → no collision possible

---

## Optimization Techniques

### 1. Frame Skipping

Instead of processing every frame:
```python
for i in range(0, num_steps, skip):  # skip = 5 or 10
    ...
```

**Trade-off**:
- Faster computation (5x speedup with skip=5)
- Slight accuracy loss (voxels between frames may be missed)
- Acceptable for visualization, questionable for precise volume analysis

### 2. Vectorization

Use NumPy broadcasting instead of loops:

**Bad** (Loop over voxels):
```python
for iz in range(nz):
    for iy in range(ny):
        for ix in range(nx):
            distance = calculate_distance(x[ix], y[iy], z[iz])
```

**Good** (Vectorized):
```python
X, Y, Z = np.meshgrid(x, y, z, indexing='ij')
distances = calculate_distance_vectorized(X, Y, Z)  # All at once
```

Speedup: 10-100x depending on grid size.

### 3. Profile Pre-computation

Build interpolation functions once:
```python
# At initialization (once)
profile_funcs = {}
for wheel in tool_stack.wheels:
    profile_funcs[wheel.tool_id] = interp1d(...)

# In loop (many times)
radial_offset = profile_funcs[wheel.tool_id](h_values)  # Fast lookup
```

### 4. Memory Management

For large grids (0.25 mm resolution):
- 25 million voxels × 4 bytes (float32) = 100 MB
- Consider chunking or sparse representations for very high resolution
- Use `dtype=np.float32` instead of `float64` to halve memory

---

## Validation and Testing

### Unit Tests

1. **Blank Generation**:
   - Compare volume against analytical sphere formulas
   - Check symmetry (lens should be rotationally symmetric)
   - Verify edge cases (flat surfaces, sphere = 0, etc.)

2. **Death Time Computation**:
   - Test with known simple paths (straight line, circle)
   - Verify no voxels die before time=0
   - Check that all workpiece voxels eventually die

3. **Volume Conservation**:
   - `volume_removed(t) + volume_remaining(t) = constant`
   - Check monotonicity: removed volume should never decrease

### Visual Validation

1. **VTK Rendering**: View the animated machining process
2. **Cross-sections**: Slice the volume at Z planes to inspect geometry
3. **Profile Comparison**: Compare final lens shape to CAD model

---

## Common Issues and Solutions

### Issue: Voxels Not Being Cut

**Symptoms**: Large regions of `death_times = 1000` (never cut)

**Causes**:
1. Tool profile not covering the region
2. Coordinate transformation error
3. Wheel offset misconfiguration

**Debug Steps**:
```python
# Print tool position for one frame
print(f"Tool at: ({tool_pos_x}, {tool_pos_y}, {tool_pos_z})")

# Check profile limits
print(f"Profile height range: {profile[:, 1].min()} to {profile[:, 1].max()}")

# Visualize tool axis
print(f"Tool axis: {current_tool_axis}")
```

### Issue: Excessive Computation Time

**Symptoms**: `compute_voxel_death_times()` takes minutes

**Solutions**:
1. Reduce resolution (use 1.0 mm for testing)
2. Increase frame skip (step=10 instead of step=5)
3. Reduce tool path length (test with fewer passes)
4. Profile the code to find bottlenecks

### Issue: Incorrect Volume Values

**Symptoms**: Volume history shows negative or increasing remaining volume

**Causes**:
1. Incorrect voxel volume calculation
2. Death times not properly initialized
3. Blank includes non-workpiece voxels

**Fix**:
```python
# Ensure voxel volume matches resolution
voxel_volume = resolution ** 3

# Initialize death times correctly
death_times = voxels.copy()  # Start with blank state

# Filter workpiece voxels
workpiece_mask = death_times < 1000
```

---

## Future Enhancements

### 1. Adaptive Resolution

Use higher resolution only near the tool:
- Coarse grid globally (1.0 mm)
- Fine grid near cutting zone (0.25 mm)
- Octree or sparse representation

### 2. Multi-Threading

Parallelize time step iteration:
```python
from multiprocessing import Pool

def process_frame(i):
    return compute_collision_for_frame(i)

with Pool(8) as p:
    results = p.map(process_frame, range(num_steps))
```

### 3. GPU Acceleration

Port voxel-tool distance calculation to GPU (CUDA/OpenCL):
- 100-1000x speedup potential
- Requires rewriting in CUDA Python or similar

### 4. Continuous Collision Detection

Instead of sampling frames, analytically solve for collision times:
- More accurate, no missed voxels
- Significantly more complex mathematics
- Worth it for certification/validation applications

---

## Coordinate System Reference

### Machine Frame
- **Origin**: Machine base (spindle center at home position)
- **R-axis**: Radial distance from spindle (always positive)
- **Z-axis**: Vertical (parallel to spindle axis)
- **θ-axis**: Rotation angle (0° = "front" of lens)

### Lens Frame
- **Origin**: Lens center (geometric center of blank)
- **X-axis**: Right (in plane of lens face)
- **Y-axis**: Up (in plane of lens face)
- **Z-axis**: Optical axis (perpendicular to front surface)

### Tool Frame
- **Origin**: Tool stack base (mounting point)
- **Axial**: Along tool centerline (tilted by 18°)
- **Radial**: Perpendicular to tool centerline

### Transforms

**Machine → Lens**:
```python
# Account for lens rotation θ
x_lens = r_mach * cos(-θ)
y_lens = r_mach * sin(-θ)
z_lens = z_mach
```

**Tool Axis → Lens Frame**:
```python
# Tool axis rotates with machine θ and has fixed tilt
tilt = 18°
axis_base = [-sin(tilt), 0, cos(tilt)]

# Rotate by -θ_lens
axis_lens = rotate_z(axis_base, -θ_lens)
```

---

## References and Further Reading

1. **Signed Distance Fields**
   - Quilez, I. "Distance Functions" - https://iquilezles.org/articles/distfunctions/
   - Hart, J. C. "Sphere Tracing" (1996)

2. **Volume Rendering**
   - VTK User's Guide, Volume Rendering Chapter
   - Levoy, M. "Display of Surfaces from Volume Data" (1988)

3. **Collision Detection**
   - Ericson, C. "Real-Time Collision Detection" (2004), Chapter 5
   - Gilbert, E. "A fast procedure for computing the distance between complex objects" (1988)

4. **Lens Edging**
   - ANSI Z80.1 - Prescription Ophthalmic Lenses Standard
   - Jalie, M. "Ophthalmic Lenses & Dispensing" (3rd ed.)

5. **Computational Geometry**
   - de Berg, M. et al. "Computational Geometry: Algorithms and Applications" (3rd ed.)
   - O'Rourke, J. "Computational Geometry in C" (2nd ed.)
