# Path Generation System - Visual Reference

## Class Hierarchy

```
MovementPath
├── steps: List[OperationStep]
│   ├── OperationStep (home)
│   │   ├── x: [x0]
│   │   ├── z: [z0]
│   │   ├── theta: [0.0]
│   │   └── time: [0.0]
│   │
│   ├── OperationStep (approach)
│   │   ├── x: [x0, ..., x1]
│   │   ├── z: [z0, ..., z1]
│   │   ├── theta: [0.0, ..., θ1]
│   │   └── time: [0.0, ..., t_approach]
│   │
│   ├── OperationStep (roughing pass 1)
│   │   ├── x: [x1, ..., x_final]
│   │   ├── z: [z1, ..., z_final]
│   │   ├── theta: [θ1, ..., 360.0+θ1]
│   │   └── time: [0.0, ..., t_cut1]
│   │
│   ├── OperationStep (approach)
│   │   └── ...
│   │
│   ├── OperationStep (roughing pass 2)
│   │   └── ...
│   │
│   ├── OperationStep (approach)
│   │   └── ...
│   │
│   ├── OperationStep (beveling)
│   │   └── ...
│   │
│   └── OperationStep (retract)
│       └── ...
│
└── Methods:
    ├── get_full_path() → (x, z, theta, time)
    └── get_frame_at_time(t) → (x, z, theta)
```

## Time Accumulation

```
Operation           Duration    Cumulative Time
─────────────────────────────────────────────
Home                0.0s        0.0s
Approach #1         1.2s        1.2s
Roughing Pass 1     15.0s       16.2s
Approach #2         1.0s        17.2s
Roughing Pass 2     12.0s       29.2s
Approach #3         0.8s        30.0s
Roughing Pass 3     10.0s       40.0s
Approach (Bevel)    1.1s        41.1s
Beveling            8.0s        49.1s
Retract             1.5s        50.6s
─────────────────────────────────────────────
Total Operation                 50.6s
```

## Coordinate Transformation

```
Kinematics Output           Global Coordinates
(x_machine, z_machine)      (X_world, Z_world)

x_world = wheel_x - x_machine
z_world = wheel_z + z_machine

Example:
wheel_x = 100.0, wheel_z = -150.0
x_machine = 5.0, z_machine = 3.0
→ x_world = 95.0, z_world = -147.0
```

## Timing Model

### Cutting Phase Timing

```python
# For a full revolution (360°)
revolutions = 360 / 360 = 1.0
time = 1.0 × speed_s_per_rev = speed_s_per_rev seconds

# For multiple revolutions
theta_max = 720°
revolutions = 720 / 360 = 2.0
time = 2.0 × speed_s_per_rev = 2 × speed_s_per_rev seconds

# Time array for N frames
time = linspace(0, total_time, N)
```

### Movement Phase Timing

```python
# Linear approach/retract
distance = sqrt((x_end - x_start)² + (z_end - z_start)²)
time = distance / feedrate_mm_per_sec

# Time array for N frames
time = linspace(0, duration, N)
```

## Algorithm Flow

### generate_full_roughing_path()

```
Input: roughing_passes[], wheel_x, wheel_z, machine_config
Output: MovementPath with all passes stitched together

1. Create HOME step
   └─ Single frame at (-50, 0, 0°)

2. For each roughing_pass:
   a. Solve kinematics(pass.radii) → x_mach, z_mach, theta
   b. Create APPROACH step
      └─ Linear interpolation from current → start position
   c. Create CUTTING step
      └─ Kinematics output with timing
   d. Update current position

3. Create RETRACT step
   └─ Linear interpolation from current → home position

4. Return MovementPath(all_steps)
```

### generate_full_beveling_path()

```
Input: final_radii, z_map, wheel_x, wheel_z, machine_config
Output: MovementPath for beveling only

1. Create HOME step

2. Solve kinematics(final_radii) → x_mach, z_mach, theta

3. Create APPROACH step
   └─ Linear interpolation from home → start position

4. Create CUTTING step
   └─ Kinematics output with timing

5. Create RETRACT step
   └─ Linear interpolation from end → home position

6. Return MovementPath(all_steps)
```

### generate_complete_lens_path()

```
Input: roughing_passes[], final_radii, z_map, machine_config
Output: Dict with 'roughing', 'beveling', 'complete' paths

1. Generate roughing_path = generate_full_roughing_path(...)
2. Generate beveling_path = generate_full_beveling_path(...)
3. Combine:
   complete_steps = roughing_path.steps + beveling_path.steps[1:]
   └─ Skip home from beveling (already at home from roughing)
4. Return:
   {
       'roughing': MovementPath(roughing_path.steps),
       'beveling': MovementPath(beveling_path.steps),
       'complete': MovementPath(complete_steps)
   }
```

## Playback Mechanism

### Slider to Frame Mapping

```
Slider Value (seconds)     Time Lookup
0.0 ┼─────────────────────────┼ 50.6
    │                         │
    ├─→ searchsorted(time[], slider)
    │   └─→ frame_index
    │
    └─→ x[frame_index]
        z[frame_index]
        theta[frame_index]
```

### Animation Loop

```
for current_time in np.arange(0, total_time, dt):
    ├─ frame_idx = searchsorted(time[], current_time)
    ├─ x = x[frame_idx]
    ├─ z = z[frame_idx]
    ├─ theta = theta[frame_idx]
    └─ render_scene(x, z, theta)
        └─ Updates VTK actor position
```

## Data Size Example

For a typical lens edging operation:

```
Operation           Points  Frames  Time (s)  Memory
──────────────────────────────────────────────────
Roughing Pass 1     360     720     15.0      3.6 KB
Roughing Pass 2     360     480     12.0      2.4 KB
Roughing Pass 3     360     400     10.0      2.0 KB
Beveling            360     320     8.0       1.6 KB
Approaches (×3)     -       900     3.2       3.6 KB
Retract             -       60      1.5       0.3 KB
──────────────────────────────────────────────────
Total               -       ~3900   ~50       ~13 KB

Memory for full path (x, z, theta, time):
≈ 3900 frames × 4 fields × 8 bytes = ~125 KB
```

## Speed vs Time Example

```
Speed Setting       360° Rotation Time
───────────────────────────────────
5 s/rev            5 seconds
10 s/rev           10 seconds
15 s/rev           15 seconds
20 s/rev           20 seconds

For 720° (2 revolutions):
5 s/rev  → 10 seconds
10 s/rev → 20 seconds
```

## Contour Processing

```
Each Roughing Pass Input:

radii = [r₀, r₁, r₂, ..., r₃₅₉]

Visual representation (top-down):

         r₀
         │
    r₃₅₉─┼─r₁
         │
         ·

Polar to Cartesian:
angle_i = i × (2π / N)
x_i = r_i × cos(angle_i)
y_i = r_i × sin(angle_i)

Kinematics Solver:
For each rotation angle θ:
  ├─ Rotate contour by -θ
  ├─ Find points reachable by elliptical tool
  ├─ Calculate tool center position
  └─ Output: (x_machine, z_machine)
```

## Integration Points

```
Frontend (Dash)
    ↓
    └─ "Update Roughing" button
        ↓ [roughing_logic.update_roughing_volumes()]
        ↓
        └─ store-roughing-results
            ├─ pass 1: {radii, volume, duration, mesh}
            ├─ pass 2: {radii, volume, duration, mesh}
            └─ pass 3: {radii, volume, duration, mesh}
                ↓
            "Generate Toolpaths" button
                ↓ [simulation_logic.generate_path()]
                ↓ [movement_path.generate_complete_lens_path()]
                ↓
                └─ store-simulation-path
                    ├─ x: [100.0, 99.9, ..., 95.2]
                    ├─ z: [-150.0, -149.8, ..., -145.1]
                    ├─ theta: [0.0, 0.1, ..., 720.0]
                    ├─ time: [0.0, 0.001, ..., 50.6]
                    └─ total_frames: 3847
                        ↓
                    Simulation Slider (0 to 50.6 seconds)
                        ↓ [render_simulation_frame()]
                        ↓
                        └─ 3D VTK Scene
                            └─ Animated lens movement
```

## Error Handling

```
Empty roughing_passes
    └─ Return MovementPath with only HOME step

Missing kinematics solution
    └─ Skip that pass, continue to next

Zero duration/frames
    └─ Use defaults (e.g., 1 frame, dt=1/30)

Invalid contours
    └─ Caught by solve_lens_kinematics_robust()
```

## Performance Characteristics

```
Operation                           Time Complexity
─────────────────────────────────────────────────
Path generation                     O(P × N)
  P = number of passes
  N = points per contour

Frame lookup (get_frame_at_time)    O(log F)
  F = total frames
  Uses searchsorted()

Full path concatenation             O(P × N)

Total for typical job (3P, 360N):   ~2ms
```

## File Dependencies

```
movement_path.py
├── Imports:
│   ├── numpy (data structures)
│   ├── dataclasses (OperationStep, MovementPath)
│   └── kinematics.solve_lens_kinematics_robust()
│
└── Used by:
    ├── simulation_logic.py
    └── (future: export_to_gcode.py, machine_control.py)
```
