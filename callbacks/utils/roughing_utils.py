"""
Utility functions for roughing cycle management and volume calculations.

This module bridges the UI callbacks with the core geometric engine.
"""

from typing import List, Optional
import numpy as np

from core.models.roughing import RoughingPassParam, RoughingSettings


def roughing_params_from_store(roughing_store_data: dict) -> tuple[List[RoughingPassParam], str]:
    """
    Convert roughing data from dcc.Store to RoughingPassParam objects and method.
    
    Args:
        roughing_store_data: Dict from store-roughing-data with format:
            {
                'method': 'CONCENTRIC',
                'passes': [
                    {'step_value_mm': 3.0, 'speed_s_per_rev': 15},
                    ...
                ]
            }
        
    Returns:
        Tuple of (List[RoughingPassParam], method_str)
        
    Example:
        operations, method = roughing_params_from_store(roughing_store_data)
        results = generate_roughing_operations(
            final_radii, blank_radius, lens_thickness, 
            front_curve, back_curve, 
            operations, method  # Pass method along
        )
    """
    if not roughing_store_data or not roughing_store_data.get('passes'):
        return [], 'CONCENTRIC'
    
    method = roughing_store_data.get('method', 'CONCENTRIC')
    
    operations = []
    for pass_info in roughing_store_data['passes']:
        op = RoughingPassParam(
            step_value_mm=float(pass_info.get('step_value_mm', 3.0)),
            speed_s_per_rev=float(pass_info.get('speed_s_per_rev', 15))
        )
        operations.append(op)
    
    return operations, method


def roughing_settings_from_store(roughing_store_data: dict) -> RoughingSettings:
    """
    Convert store data to a RoughingSettings model object.
    
    Args:
        roughing_store_data: Dict from store-roughing-data
        
    Returns:
        RoughingSettings instance with method and passes
    """
    return RoughingSettings.from_dict(roughing_store_data)


def estimate_roughing_volume(
    step_value_mm: float,
    speed_value: float,
    blank_diameter_mm: float,
    final_diameter_mm: float,
    pass_index: int,
    total_passes: int
) -> float:
    """
    Estimate the removed volume for a roughing pass based on geometry.
    
    This is a simplified model for real-time UI feedback.
    For exact volumes, integrate with the full geometric calculation engine.
    
    Args:
        step_value_mm: Step distance from previous contour
        speed_value: Processing speed parameter
        blank_diameter_mm: Original blank diameter
        final_diameter_mm: Final lens diameter after all passes
        pass_index: Which pass (1, 2, 3...)
        total_passes: Total number of passes
        
    Returns:
        Estimated volume in mm³
    """
    # Base volume: cylinder of step height and radius of current pass
    # Approximate radius at this pass (interpolated between blank and final)
    progress_ratio = pass_index / total_passes if total_passes > 0 else 0
    current_radius = blank_diameter_mm / 2
    final_radius = final_diameter_mm / 2
    
    # Approximate radius at this pass
    approx_radius = current_radius - (current_radius - final_radius) * progress_ratio
    
    # Volume = π * r² * h (approximate cylinder)
    # Where h is related to step value
    estimated_volume = np.pi * (approx_radius ** 2) * step_value_mm * 0.8
    
    # Scale by speed factor
    estimated_volume *= (speed_value / 15.0)  # Normalize to default speed of 15
    
    return max(0.0, round(estimated_volume, 2))


def validate_roughing_parameters(roughing_data: dict) -> tuple[bool, str]:
    """
    Validate roughing parameters for sanity.
    
    Args:
        roughing_data: Dict from store-roughing-data
        
    Returns:
        (is_valid, error_message)
    """
    if not roughing_data or not roughing_data.get('passes'):
        return False, "No roughing passes defined"
    
    passes = roughing_data['passes']
    method = roughing_data.get('method', 'CONCENTRIC')
    
    if len(passes) == 0:
        return False, "At least one roughing pass is required"
    
    # Validate method
    if method not in ['CONCENTRIC', 'INTERPOLATION']:
        return False, f"Invalid method: {method}"
    
    total_step = 0
    for i, pass_info in enumerate(passes, 1):
        step = float(pass_info.get('step_value_mm', 0))
        speed = float(pass_info.get('speed_s_per_rev', 0))
        
        if step <= 0:
            return False, f"Pass {i}: Step value must be > 0"
        
        if speed <= 0:
            return False, f"Pass {i}: Speed must be > 0"
        
        if step > 50:  # Sanity check: step shouldn't be more than 50mm
            return False, f"Pass {i}: Step value seems too large ({step}mm)"
        
        total_step += step
    
    return True, "OK"


def estimate_roughing_duration(roughing_data: dict) -> float:
    """
    Estimate total roughing time in seconds.
    
    Args:
        roughing_data: Dict from store-roughing-data
        
    Returns:
        Estimated duration in seconds
    """
    if not roughing_data or not roughing_data.get('passes'):
        return 0.0
    
    passes = roughing_data['passes']
    
    # Simple model: time = sum of (speed per pass + overhead)
    total_time = 0.0
    for pass_info in passes:
        speed = float(pass_info.get('speed_s_per_rev', 15))
        # Assume each pass takes roughly speed_s_per_rev seconds plus 5 second overhead
        total_time += speed + 5.0
    
    return round(total_time, 1)


def calculate_cumulative_removal(
    roughing_volumes: List[float]
) -> List[float]:
    """
    Calculate cumulative volume removed across all passes.
    
    Args:
        roughing_volumes: List of volumes removed per pass
        
    Returns:
        List of cumulative volumes after each pass
    """
    cumulative = []
    total = 0.0
    
    for vol in roughing_volumes:
        total += vol
        cumulative.append(round(total, 2))
    
    return cumulative
