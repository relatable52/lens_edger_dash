# Beveling and Roughing Path Generation Implementation

## Overview

This implementation provides a complete system for generating machine movement paths for lens edging operations, combining roughing (material removal) and beveling (edge finishing) with precise timing for playback synchronization.

## New Modules

### `core/cam/movement_path.py`

The core module providing path generation functionality:

#### Key Classes

**`OperationStep`** - Represents a single step in the movement sequence:
- `operation_type`: One of 'home', 'approach', 'roughing', 'beveling', 'retract'
- `pass_index`: Which roughing pass (0 for non-roughing operations)
- `x`, `z`, `theta`: Machine coordinates (arrays of positions)
- `time`: Cumulative time for each point (seconds)
- `speed_mm_per_sec`: XZ plane feedrate
- `feed_rate_s_per_rev`: Spindle feed rate (seconds per revolution)
- `total_frames`: Number of frames in this step

**`MovementPath`** - Combines all operation steps into a complete path:
- `steps`: List of OperationStep objects
- `get_full_path()`: Returns concatenated (x, z, theta, time) arrays
- `get_frame_at_time(time_sec)`: Get machine coordinates at specific time

#### Key Functions

**`generate_full_roughing_path()`** - Generate complete roughing sequence:
- Processes multiple roughing passes
- Each pass has its own contour (radii array)
- Generates approach/retract sequences between passes
- Includes timing based on spindle speed
- Returns a `MovementPath` object

**`generate_full_beveling_path()`** - Generate beveling operation:
- Single pass along final contour
- Uses beveling wheel configuration
- Includes approach/retract sequences
- Synchronized to spindle speed

**`generate_complete_lens_path()`** - Generate entire workflow:
- Combines roughing and beveling automatically
- Handles multiple wheel positions
- Accounts for machine tilt angle
- Returns dict with 'roughing', 'beveling', and 'complete' paths

## Key Features

### 1. **Roughing (All Contours)**
- Process multiple roughing passes
- Each pass removes a layer defined by a contour (radii array)
- Automatically generates transitions between passes
- Linear interpolation for approach/retract phases

### 2. **Beveling (Final Contour)**
- Single pass along the final lens shape
- Uses dedicated beveling wheel
- Properly stitched after roughing

### 3. **Timing and Synchronization**
- All paths include cumulative time values
- Time is based on spindle speed (seconds per revolution)
- Frames can be selected by time for animation
- Supports both time-based and frame-based playback

### 4. **Machine Kinematics Integration**
- Uses existing `solve_lens_kinematics_robust()` for each pass
- Converts kinematics coordinates to global machine coordinates
- Accounts for wheel positions and tilt angle

## Data Structure

Each roughing pass requires:
```python
{
    'radii': np.ndarray,           # Polar radii (one contour)
    'z_map': np.ndarray,            # Z-height map
    'speed_s_per_rev': float        # Spindle feed rate
}
```

Complete path output:
```python
{
    "x": list,               # Machine X positions
    "z": list,               # Machine Z positions
    "theta": list,           # Spindle angles (degrees)
    "time": list,            # Cumulative time (seconds)
    "total_frames": int      # Total number of frames
}
```

## Integration with Simulation

### Updated `callbacks/simulation_logic.py`

The simulation callbacks now:

1. **Path Generation** (`generate_path` callback):
   - Collects roughing results from `store-roughing-results`
   - Extracts final contour from bevel data
   - Calls `generate_complete_lens_path()`
   - Stores path with timing information

2. **Animation Controls**:
   - Slider now represents time (in seconds) instead of 0-100%
   - Maximum slider value = operation duration
   - Advances by 0.1 seconds per interval (10 Hz)

3. **Frame Selection** (`render_simulation_frame` callback):
   - Uses `np.searchsorted()` to find frame by time
   - Fallback to percentage-based lookup for legacy data
   - Updates 3D scene with correct position

4. **Clientside Animation**:
   - JavaScript function maps slider time to frame index
   - Handles both time-based and percentage-based lookups
   - Updates actor positions for lens geometry

## Usage Example

```python
from core.cam.movement_path import generate_complete_lens_path
from core.machine_config import load_machine_config_cached
import numpy as np

# Prepare roughing passes
roughing_passes = [
    {
        'radii': np.array([40.0] * 360),
        'z_map': np.zeros(360),
        'speed_s_per_rev': 15.0
    },
    {
        'radii': np.array([42.0] * 360),
        'z_map': np.zeros(360),
        'speed_s_per_rev': 12.0
    },
]

# Final contour
final_radii = 45.0 * np.ones(360)
z_map = np.zeros(360)

# Generate paths
machine = load_machine_config_cached()
paths = generate_complete_lens_path(
    roughing_passes=roughing_passes,
    final_radii=final_radii,
    z_map=z_map,
    machine_config=machine,
    xyz_feedrate=50.0
)

# Get complete path with timing
complete_path = paths['complete']
x, z, theta, time = complete_path.get_full_path()

# Get position at specific time
x_pos, z_pos, theta_pos = complete_path.get_frame_at_time(10.5)
```

## Animation Playback

For animation/simulation:

1. **Time-Based**: Recommended approach
   ```python
   # Slider represents time in seconds
   # Find frame using numpy.searchsorted()
   frame_idx = np.searchsorted(time_array, slider_value, side='left')
   x_pos = x[frame_idx]
   z_pos = z[frame_idx]
   theta_pos = theta[frame_idx]
   ```

2. **Playback Loop** (30 Hz):
   ```python
   frame_time = 1.0 / 30.0  # 33ms per frame
   current_time = 0.0
   
   while current_time <= total_time:
       frame_pos = path.get_frame_at_time(current_time)
       # Update 3D scene with frame_pos
       current_time += frame_time
   ```

## Path Structure

The complete path consists of:

1. **Home Position**: Spindle retracted, lens far away
2. **For Each Roughing Pass**:
   - Approach: Linear interpolation to cut start position
   - Cutting: Full revolution along contour at spindle speed
   - (Implicit next approach for next pass)
3. **Beveling Pass**:
   - Approach: Linear interpolation to start position
   - Cutting: Final contour pass at beveling speed
4. **Retract**: Return to home position

## Timing Calculation

- **Cutting phase**: Based on `speed_s_per_rev` and total rotation angle
  - Example: 360° at 10 s/rev = 10 seconds
  - Example: 720° at 10 s/rev = 20 seconds

- **Movement phase** (approach/retract): Based on `xyz_feedrate`
  - Example: 50 mm distance at 50 mm/sec = 1 second
  - Interpolated linearly across frames

## Configuration

Machine configuration is loaded from `core/machine_config.py`:
- Wheel positions (stack offsets)
- Tool radii and tilt angles
- Base position and orientation

Example wheel configuration:
```python
wheels[0]  # Roughing wheel
wheels[1]  # Bevel wheel

wheel.cutting_radius      # Effective cutting radius
wheel.stack_z_offset      # Position in tool stack
wheel.cutting_z_relative  # Z offset for cutting point
```

## Performance Considerations

- Path generation is performed once per "Generate Paths" button click
- Kinematics solving happens for each roughing pass (vectorized)
- Time complexity: O(passes × points_per_contour)
- Memory usage: All arrays are numpy arrays (efficient)

## Future Enhancements

1. **Adaptive Feedrate**: Vary speed based on contour complexity
2. **Tool Deflection**: Compensate for tool wear/deflection
3. **Multi-Tool Support**: Handle tool changes during operation
4. **Collision Detection**: Warn if paths interfere with geometry
5. **Path Optimization**: Minimize tool changes and retracts

## Files Modified

- `core/cam/movement_path.py` (NEW)
- `callbacks/simulation_logic.py` (UPDATED)
  - Import of `generate_complete_lens_path`
  - Updated `generate_path` callback
  - Updated slider animation logic
  - Updated time-based frame selection

## Testing

Run the example script to verify functionality:
```bash
python examples_movement_path.py
```

This will demonstrate:
- Roughing path generation with multiple passes
- Beveling operation
- Complete workflow combining both
- Time-based playback simulation
