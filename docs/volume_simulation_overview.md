# Volume Calculation and Removal Simulation - Overview

## Introduction

The volume simulation system provides real-time visualization and analysis of the lens machining process. It uses a volumetric voxel-based approach combined with signed distance fields (SDF) to accurately model material removal during the edging operation.

## System Architecture

### Three-Phase Process

1. **Blank Generation** - Create initial lens blank geometry
2. **Machining Simulation** - Compute material removal based on tool path
3. **Volume Analysis** - Track and analyze volume removal over time

---

## Design Rationale

### Why Voxels?

The system uses a **voxel-based representation** (3D grid of volume elements) rather than mesh-based or analytical approaches for several compelling reasons:

**Advantages of Voxels:**
- **Uniform topology**: Every voxel is the same size and shape, simplifying collision detection to distance checks
- **Trivial volume calculation**: Count voxels and multiply by voxel volume - no complex mesh integration
- **Native VTK support**: Volume rendering in VTK is designed for voxel data, providing efficient GPU-accelerated visualization
- **Robust to complex geometry**: Handles arbitrary tool profiles and lens shapes without mesh degeneracy issues
- **Parallelizable**: Each voxel can be processed independently, enabling vectorized NumPy operations

**Why Not Meshes?**
- Mesh-based approaches (triangle soup, NURBS, even CAD) require expensive mesh-tool intersection algorithms
- Boolean operations (CSG subtraction) on meshes are numerically unstable and slow
- Volume calculations require surface integration, prone to errors with non-manifold geometry
- Mesh quality degrades after multiple cutting operations, requiring remeshing

**Why Not Analytical?**
- Lens geometry with multiple cuts cannot be expressed as simple equations
- Intersection of tool sweep volumes with lens surface is mathematically intractable for complex profiles
- No way to handle variable feed rates or interrupted cuts analytically

### Why Death Times Instead of Regenerating Volumes?

The system computes each voxel's **"death time"** (when it's removed) once, rather than regenerating the entire cut geometry at each animation frame.

**Traditional Approach (Regenerate Each Frame):**
```python
for frame in animation_frames:
    volume = generate_blank()
    for cut in cuts_up_to_frame:
        volume = subtract_tool_from_volume(volume, cut)
    render(volume)
```
- **Cost**: O(frames × cuts × voxels) = O(n³ · t²) for t frames
- **Memory**: Only stores current frame (~13 MB @ 0.5mm resolution)
- **Limitation**: Cannot jump to arbitrary times; must recompute from start

**Death Time Approach (This System):**
```python
death_times = compute_once_for_all_voxels(tool_path)  # O(n³ · t)

for frame in animation_frames:
    visible_voxels = death_times > current_time
    render(visible_voxels)  # O(1) - just threshold operation
```
- **Cost**: O(voxels × time_steps) = O(n³ · t) - computed once
- **Memory**: Stores single death time array (~13 MB @ 0.5mm resolution)
- **Advantage**: **Instant** random access to any time - no recomputation needed

**Key Benefits:**

1. **Temporal Freedom**: Jump backward/forward in time instantly - critical for interactive scrubbing and analysis
2. **One-Time Computation**: After initial simulation, playback is free (just updating VTK transfer function)
3. **Predictive Analysis**: Death times encode the complete machining history, enabling pre-computation of volume removal rates
4. **Memory Efficient**: Only one 3D array regardless of animation length (100 frames or 10,000 frames = same memory)
5. **Bidirectional Playback**: Play animation forward or backward with equal performance

**Why Not Regenerate Every Time?**

Regenerating would require:
- Recomputing tool-voxel collisions for every frame shown (~10 seconds per frame @ 0.5mm)
- Storing intermediate tool positions and performing incremental boolean operations
- Non-interactive performance for 60 FPS animation (600 seconds for 60 frames)
- Cannot analyze "what if" scenarios without complete re-simulation

### Why Frame-Based Encoding (0-1000)?

Death times are stored as **normalized frame indices** (0-1000) rather than absolute time values (seconds).

**Advantages:**
- **Time Remapping**: Adjust feed rates without recomputing voxel deaths - just remap frame→time
- **VTK Compatibility**: Transfer functions work with scalar ranges - (0-1000) is VTK-friendly
- **Feed Rate Independence**: Decouples when material is cut from how fast the tool moves
- **Consistent Range**: Same scalar range for all simulations regardless of cycle time

**Use Case Example:**

Original path takes 45 seconds. Volume analysis shows excessive removal rate in pass 3.

**With Frame Encoding:**
```python
# Slow down pass 3 by adjusting time array
adjusted_times = adjust_time_array_for_volume_constraints(...)
# Death times unchanged! Just map frame→time differently
```

**Without Frame Encoding:**
```python
# Would need to recompute all death times with new feed rates
death_times = recompute_voxel_death_times(new_tool_path)  # Minutes of work
```

### Comparison Summary

| Approach | Computation | Memory | Random Access | Feed Rate Adjustment |
|----------|-------------|--------|---------------|---------------------|
| **Regenerate Per Frame** | O(n³·t²) | ~13 MB | ❌ Sequential only | ❌ Full recompute |
| **Death Times (ours)** | O(n³·t) | ~13 MB | ✅ Instant | ✅ Remap only |
| **Mesh Boolean** | O(m·t²) | ~5 MB | ❌ Sequential only | ❌ Full recompute |
| **Analytical** | N/A | Minimal | ❌ Not feasible | ❌ Not feasible |

*n = voxels per dimension, t = time steps, m = mesh triangles*

---

## Phase 1: Blank Generation

### Purpose
Generate the initial lens blank (starting "puck") as a 3D volumetric grid before any machining occurs.

### Method: Signed Distance Fields (SDF)

The lens blank is modeled using three geometric primitives:

```
Lens Interior = Cylinder ∩ Front_Sphere ∩ (NOT Back_Sphere)
```

#### Geometric Components

1. **Cylinder** (Outer Boundary)
   - Radius: `diameter_mm / 2`
   - Defines the maximum radial extent
   - SDF: `dist_cyl = √(x² + y²) - radius`

2. **Front Sphere** (Convex Surface)
   - Radius: `front_radius`
   - Center at: `(0, 0, front_radius)`
   - SDF: `dist_front = √(x² + y² + (z - z_center)²) - front_radius`

3. **Back Sphere** (Concave/Meniscus Surface)
   - Radius: `back_radius`
   - Center at: `(0, 0, center_thickness + back_radius)`
   - SDF: `dist_back = back_radius - √(x² + y² + (z - z_center)²)` (inverted)

#### SDF Intersection Logic

The point is inside the lens material if it satisfies ALL conditions:
- Inside cylinder: `dist_cyl < 0`
- Inside front sphere: `dist_front < 0`
- Outside back sphere: `dist_back < 0`

Using SDF math, intersection is computed as:
```python
combined_distance = max(dist_cyl, dist_front, dist_back)
```

A negative combined distance means the point is inside the material.

### Scalar Encoding

Each voxel stores a scalar value representing its state:
- **1000.0** = Full material (will be machined)
- **0.0** = Air/void (outside blank)
- **Intermediate** = Smooth transition zone (optional anti-aliasing)

### Output

`LensVolumeData` object containing:
- `dimensions`: Grid size `[nx, ny, nz]`
- `spacing`: Voxel size `[dx, dy, dz]` in mm
- `origin`: Grid origin `[x0, y0, z0]` in mm
- `scalars`: Flattened density array (C-order: X varies fastest)

---

## Phase 2: Machining Simulation

### Purpose
Simulate the material removal process by determining when each voxel is "cut" by the tool.

### Core Concept: Voxel Death Times

Each voxel is assigned a "death time" - the moment it is removed by the cutting tool. This enables:
- Time-based visualization (animate the machining process)
- Volume tracking (material remaining vs. removed)
- Rate analysis (volume removal rate over time)

### Algorithm Overview

For each time step in the tool path:

1. **Tool Position**: Determine tool location in machine coordinates `(r, z, θ)`
2. **Coordinate Transform**: Convert to lens frame accounting for rotation
3. **Active Tool**: Identify which wheel is cutting (roughing or beveling)
4. **Collision Detection**: Check if tool surface intersects each voxel
5. **Update Death Times**: Record earliest collision time for each voxel

### Coordinate Transformation

#### Machine to Lens Frame

The tool position in cylindrical machine coordinates `(r_mach, z_mach, θ_mach)` is transformed to the lens's Cartesian frame accounting for the lens rotation:

```python
# Tool position in lens frame (lens is rotating)
x_tool = r_mach * cos(-θ_lens)
y_tool = r_mach * sin(-θ_lens)
z_tool = z_mach
```

The **tool axis direction** also rotates with the angular position:
```python
# Tool tilt vector rotates with tool position
tilt_rad = radians(tilt_angle)
tool_axis_base = [-sin(tilt_rad), 0, cos(tilt_rad)]

# Rotate by -θ_lens
axis_x = tool_axis_base[0] * cos(-θ) - tool_axis_base[1] * sin(-θ)
axis_y = tool_axis_base[0] * sin(-θ) + tool_axis_base[1] * cos(-θ)
axis_z = tool_axis_base[2]
```

### Tool Profile Collision Detection

#### Profile Definition

Each wheel has a 2D profile defining its shape:
- **Y-axis**: Axial height along tool (parallel to tool axis)
- **Z-axis**: Radial offset from nominal cutting radius

Example (V-bevel profile):
```
[Radial_Offset, Axial_Height]
[-1.797,  9.045]  # Top edge
[ 0.678,  1.427]  # V-shoulder (top)
[ 0.0,   -0.371]  # V-apex (cutting edge)
[ 1.604, -1.427]  # V-shoulder (bottom)
[ 4.097, -9.045]  # Bottom edge
```

#### Voxel-Tool Geometry

For each voxel at position `P = (x, y, z)`:

1. **Vector from tool to voxel**: `V = P - P_tool`

2. **Projection onto tool axis**: 
   ```
   h = V · tool_axis
   ```
   This gives the axial position along the tool.

3. **Radial distance from tool axis**:
   ```
   d = √(|V|² - h²)
   ```
   This is the perpendicular distance to the tool centerline.

4. **Tool surface radius at height h**:
   ```
   h_relative = h - (wheel_z_offset + cutting_z_relative)
   radial_offset = profile_interpolator(h_relative)
   surface_radius = cutting_radius + radial_offset
   ```

5. **Collision check**:
   ```
   if d < surface_radius:
       voxel is cut at this time step
   ```

### Frame-Based Encoding

Instead of storing absolute time values, death times are encoded as **frame indices** normalized to 0-1000:

```python
death_frame = (frame_index / total_frames) * 1000
```

This enables:
- Frame-synchronized visualization
- Easy time remapping for feed rate adjustments
- Consistent scalar range for VTK rendering

### Optimization Strategies

1. **Time Stepping**: Process every Nth frame (e.g., step=5) for speed
2. **Vectorization**: Use NumPy broadcasting for all voxels simultaneously
3. **Early Termination**: Skip frames where no wheel is active
4. **Profile Caching**: Pre-compute interpolation functions once

---

## Phase 3: Volume Analysis

### Volume History Tracking

Calculate material state at each point in time:

```python
volume_remaining(t) = count(death_times > t) * voxel_volume
volume_removed(t) = total_volume - volume_remaining(t)
percentage_complete(t) = (volume_removed / total_volume) * 100
```

### Volume Removal Rate Analysis

Calculate instantaneous removal rate:

```python
# Count voxels cut in each frame
voxel_counts = histogram(death_times, bins=frame_indices)
volume_per_frame = voxel_counts * voxel_volume

# Rate depends on time per frame
removal_rate = volume_per_frame / delta_time
```

### Constraint Enforcement

Different machining passes have different maximum removal rates:
- **Roughing**: Higher rates allowed (e.g., 100 mm³/s)
- **Beveling**: Lower rates for quality (e.g., 20 mm³/s)

If simulated rate exceeds constraint:
```python
required_dt = volume_per_frame / max_allowed_rate
adjusted_time[i] = adjusted_time[i-1] + required_dt
```

This automatically slows down the tool motion to respect physical limits.

---

## Integration with VTK Rendering

### Scalar Field Interpretation

The volume data uses **frame-based scalars** (0-1000) where:
- **1000**: Uncut material (initial blank)
- **500**: Material cut at frame 500 (50% through operation)
- **0**: Material cut at frame 0 (beginning) or never part of blank

### VTK Volume Rendering Setup

1. **Transfer Function**: Maps scalar values to opacity
   - High scalars (near 1000): Transparent (will be cut later)
   - Current frame scalar: Opaque (cutting edge)
   - Low scalars: Fully transparent (already removed)

2. **Temporal Animation**: 
   - Slider controls current frame
   - Transfer function updates to show material state at that frame
   - Creates "progressive reveal" of machining process

### Advantages of This Approach

1. **Single Volume**: Only one 3D array needed, not separate snapshots
2. **Arbitrary Playback**: Can jump to any time without recomputation
3. **Memory Efficient**: Fixed size regardless of animation length
4. **Bidirectional**: Can play forward or backward equally well

---

## Performance Considerations

### Resolution Trade-offs

| Resolution | Voxels (80mm lens) | Memory | Computation Time |
|------------|-------------------|---------|------------------|
| 1.0 mm     | ~400K             | ~1.6 MB | ~1 second        |
| 0.5 mm     | ~3.2M             | ~13 MB  | ~10 seconds      |
| 0.25 mm    | ~25M              | ~100 MB | ~2 minutes       |

### Recommended Settings

- **Interactive Preview**: 1.0 mm resolution
- **Quality Visualization**: 0.5 mm resolution
- **High-Accuracy Analysis**: 0.25 mm resolution

### Computational Complexity

- **Blank Generation**: O(n³) where n = voxels per dimension
- **Machining Simulation**: O(n³ · t) where t = time steps
- **Volume Analysis**: O(n³) per query, but can be cached

---

## Applications

### 1. Process Visualization
- Animate the complete machining operation
- Identify problematic cutting sequences
- Validate tool path correctness

### 2. Volume Analysis
- Track material removal progress
- Ensure complete lens formation
- Detect under-cutting or over-cutting

### 3. Feed Rate Optimization
- Compute actual removal rates
- Adjust timing to respect constraints
- Predict total cycle time

### 4. Quality Assurance
- Verify final lens geometry
- Check for surface defects
- Validate against specification

---

## References

- **Signed Distance Fields**: Inigo Quilez, "Distance Functions" (iquilezles.org)
- **Volume Rendering**: VTK User's Guide, Volume Rendering Chapter
- **Coordinate Transforms**: Robotics kinematics (Craig's *Introduction to Robotics*)
