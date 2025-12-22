# Quick Start Guide - Beveling & Roughing Path Generation

## Overview

The system now generates complete machine paths with timing for:
- **Roughing**: Multiple passes removing layers to rough contours
- **Beveling**: Final pass applying edge treatment
- **Timing**: Every position is time-stamped for accurate playback

## What Changed

### Before
- Single beveling pass only
- Slider was 0-100% (percentage-based)
- No support for roughing sequences

### After
- Multiple roughing passes + beveling
- Slider is time in seconds
- Automatic approach/retract sequences
- Precise timing for each operation

## How to Use

### Step 1: Configure Roughing Passes
1. Open the "Roughing Contour" tab
2. Set roughing method (Concentric or Interpolation)
3. Click "+" to add passes
4. Set Step (mm) and Speed (s/rev) for each pass

### Step 2: Update Roughing Volumes
1. Click "Update Roughing" button
2. System calculates volumes for each pass
3. Results stored automatically

### Step 3: Generate Movement Paths
1. Click "Generate Toolpaths" button
2. System:
   - Extracts final contour from bevel data
   - Generates roughing passes
   - Generates beveling pass
   - Stitches all together with timing
3. Path now stored in `store-simulation-path` with:
   - `x`, `z`, `theta`: Machine positions
   - `time`: Cumulative time (NEW)
   - `total_frames`: Number of frames

### Step 4: Animate
1. 3D Simulation tab shows lens moving
2. Slider represents time in seconds
3. Play button starts/stops animation
4. Slider tracks operation progress

## Understanding the Path Structure

The generated path contains:

```
Home (0.0s)
  ↓
Approach #1 (1.0s)
  ↓
Roughing Pass 1 (15.0s) ← 360° rotation at speed
  ↓
Approach #2 (0.8s)
  ↓
Roughing Pass 2 (12.0s)
  ↓
Approach #3 (0.8s)
  ↓
Roughing Pass 3 (10.0s)
  ↓
Approach Bevel (1.0s)
  ↓
Beveling Pass (8.0s)
  ↓
Retract (1.5s)
  ↓
Home (50.6s total)
```

## Key Parameters

### Roughing Speed (s/rev)
- How many seconds for one full spindle revolution
- Lower = faster cutting (15-20 s/rev: rough, 10-15: medium, 5-10: fine)
- Controls timing: 1 rev at 10 s/rev = 10 seconds in animation

### Roughing Step (mm)
- Distance to move inward from previous contour
- Method determines how this is applied:
  - **Concentric**: Move circles inward, blend with lens shape
  - **Interpolation**: Linear morph from current to final shape

### XYZ Feedrate (mm/sec)
- Speed of approach and retract movements
- Default: 50 mm/sec
- Controls duration of approach/retract phases

## Timing Example

For a lens with 3 roughing passes:

```
Operation          Duration   Cumulative
Home               0s         0s
Approach #1        1.2s       1.2s
Roughing 1 (15)   15.0s      16.2s   ← 1 rev at 15 s/rev
Approach #2        1.0s       17.2s
Roughing 2 (12)   12.0s      29.2s   ← 1 rev at 12 s/rev
Approach #3        0.8s       30.0s
Roughing 3 (10)   10.0s      40.0s   ← 1 rev at 10 s/rev
Approach Bevel     1.1s       41.1s
Beveling (8)       8.0s       49.1s   ← 1 rev at 8 s/rev
Retract            1.5s       50.6s
```

## Slider Control

Old behavior (percentage):
```
Slider: 0 ───────────── 100
Frame:  0 ───────────── N
```

New behavior (time):
```
Slider: 0.0s ──────── 50.6s
Time:   0.0s ──────── 50.6s
```

Just move slider to specific second, animation jumps to that point in operation.

## Common Issues & Solutions

### Problem: Slider doesn't move far
- **Cause**: Operation finished quickly (only beveling, no roughing)
- **Solution**: Add roughing passes with longer speeds

### Problem: Animation is too fast/slow
- **Cause**: Speed settings don't match actual machine
- **Solution**: Adjust "Speed (s/rev)" in roughing table
  - Higher value = slower (more time per revolution)
  - Lower value = faster

### Problem: No roughing paths visible
- **Cause**: Roughing results not generated
- **Solution**: 
  1. Check "Update Roughing" was clicked
  2. Check store-roughing-results has data
  3. Try different step/speed values

### Problem: Lens doesn't move to right position
- **Cause**: Wheel coordinates or tilt angle wrong
- **Solution**: Check machine_config.py:
  - `base_position`: Machine base location
  - `tilt_angle_deg`: Spindle tilt
  - `wheels[0].cutting_radius`: Roughing wheel radius
  - `wheels[1].cutting_radius`: Beveling wheel radius

## For Developers

### Access Generated Path

```python
# In callbacks:
from core.cam.movement_path import generate_complete_lens_path

paths = generate_complete_lens_path(
    roughing_passes=roughing_passes,
    final_radii=final_radii,
    z_map=z_map,
    machine_config=machine_config,
    xyz_feedrate=50.0
)

complete_path = paths['complete']
x, z, theta, time = complete_path.get_full_path()

# Get position at any time
x_pos, z_pos, theta_pos = complete_path.get_frame_at_time(25.0)
```

### Customize Feedrates

In `simulation_logic.py` generate_path():

```python
paths = generate_complete_lens_path(
    roughing_passes=roughing_passes,
    final_radii=final_radii,
    z_map=z_map,
    machine_config=machine,
    xyz_feedrate=50.0  # Change this for faster/slower approach
)
```

### Export Path

```python
path_dict = {
    "x": x.tolist(),
    "z": z.tolist(),
    "theta": theta.tolist(),
    "time": time.tolist(),
    "total_frames": len(x)
}

import json
json.dump(path_dict, open('lens_path.json', 'w'))
```

## Technical Details

### Time Calculation

**Cutting phase:**
```python
revolutions = max_theta / 360.0
time = revolutions × speed_s_per_rev
```

**Approach/Retract:**
```python
distance = √((x_end-x_start)² + (z_end-z_start)²)
time = distance / feedrate
```

### Coordinate System

Machine coordinates → Global coordinates:
```python
x_global = wheel_x - x_machine
z_global = wheel_z + z_machine
```

Accounts for wheel position and tilt automatically.

### Algorithm

For each roughing pass:
1. Solve kinematics on the pass contour
2. Calculate position/rotation for one full revolution
3. Generate approach from current position
4. Generate cutting phase
5. Generate next approach

Finally, add beveling on final contour.

## Testing

Run examples:
```bash
python examples_movement_path.py
python INTEGRATION_GUIDE.py
```

Check syntax:
```bash
python -m py_compile core/cam/movement_path.py
```

## Files to Know

| File | Purpose |
|------|---------|
| `core/cam/movement_path.py` | Path generation |
| `callbacks/simulation_logic.py` | UI callbacks (updated) |
| `core/machine_config.py` | Machine configuration |
| `core/cam/kinematics.py` | Kinematics solver |
| `examples_movement_path.py` | Example code |

## Next Steps

1. Test with real lens data
2. Verify timing matches actual machine
3. Fine-tune wheel positions if needed
4. Adjust feedrates for optimal results

## Support

For issues or questions, check:
1. `IMPLEMENTATION_NOTES.md` - Detailed technical docs
2. `INTEGRATION_GUIDE.py` - Integration examples
3. `VISUAL_REFERENCE.md` - Diagrams and flow charts
4. `examples_movement_path.py` - Working examples

---

**Version**: 1.0
**Last Updated**: 2025-12-21
**Status**: Ready for testing
