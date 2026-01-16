"""
Tool path export utilities for lens edger CAM software.
Formats path and timing data for export to CSV or JSON.
"""
import csv
import io
import json
from datetime import datetime
from typing import Dict, List, Optional


def format_path_data_to_csv(path_data: Dict, time_data: Dict) -> str:
    """
    Format tool path and timing data into CSV format.
    
    Args:
        path_data: Dictionary containing 'x', 'z', 'theta', 'pass_segments'
        time_data: Dictionary containing 'time' array
        
    Returns:
        CSV formatted string
    """
    if not path_data or not time_data:
        return ""
    
    x_array = path_data.get('x', [])
    z_array = path_data.get('z', [])
    theta_array = path_data.get('theta', [])
    time_array = time_data.get('time', [])

    # Validate arrays have same length
    if not (len(x_array) == len(z_array) == len(theta_array) == len(time_array)):
        return ""
    
    # Create CSV string
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Write header
    writer.writerow([
        'frame_index', 'time_sec', 'x_mm', 'z_mm', 'theta_deg',
    ])
    
    # Write data rows
    for i in range(len(x_array)):        
        writer.writerow([
            i,
            f"{time_array[i]:.6f}",
            f"{x_array[i]:.6f}",
            f"{z_array[i]:.6f}",
            f"{theta_array[i]:.6f}"
        ])
    
    return output.getvalue()


def format_path_data_to_json(path_data: Dict, time_data: Dict) -> str:
    """
    Format tool path and timing data into JSON format.
    
    Args:
        path_data: Dictionary containing 'x', 'z', 'theta', 'pass_segments'
        time_data: Dictionary containing 'time' array
        
    Returns:
        JSON formatted string
    """
    if not path_data or not time_data:
        return "{}"
    
    export_data = {
        'metadata': {
            'export_date': datetime.now().isoformat(),
            'total_frames': path_data.get('total_frames', len(path_data.get('x', []))),
            'total_duration_sec': time_data.get('time', [0])[-1] if time_data.get('time') else 0
        },
        'path': {
            'x': path_data.get('x', []),
            'z': path_data.get('z', []),
            'theta': path_data.get('theta', []),
            'time': time_data.get('time', [])
        },
        'pass_segments': path_data.get('pass_segments', [])
    }
    
    return json.dumps(export_data, indent=2)


def get_export_filename(file_format: str = 'csv') -> str:
    """
    Generate filename for export with timestamp.
    
    Args:
        file_format: File format ('csv' or 'json')
        
    Returns:
        Filename string
    """
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    return f"toolpath_{timestamp}.{file_format}"


def get_path_summary(path_data: Dict, time_data: Dict) -> Dict:
    """
    Calculate summary statistics for tool path.
    
    Args:
        path_data: Dictionary containing 'x', 'z', 'theta', 'pass_segments'
        time_data: Dictionary containing 'time' array
        
    Returns:
        Dictionary with summary statistics
    """
    if not path_data or not time_data:
        return {}
    
    time_array = time_data.get('time', [])
    pass_segments = path_data.get('pass_segments', [])
    
    total_duration = time_array[-1] if time_array else 0
    num_passes = len(pass_segments)
    
    roughing_passes = [p for p in pass_segments if p.get('operation_type') == 'roughing']
    beveling_passes = [p for p in pass_segments if p.get('operation_type') == 'beveling']
    
    max_volume_rate = max(
        [p.get('max_volume_rate', 0) for p in pass_segments],
        default=0
    )
    
    return {
        'total_duration_sec': total_duration,
        'total_duration_min': total_duration / 60,
        'total_frames': len(time_array),
        'num_passes': num_passes,
        'num_roughing_passes': len(roughing_passes),
        'num_beveling_passes': len(beveling_passes),
        'max_volume_rate_mm3_s': max_volume_rate
    }
