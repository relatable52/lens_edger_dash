"""
Test script for tool SDF generation and comparison.

Tests both VTK and Trimesh methods, compares runtime and accuracy,
and visualizes the results.
"""

import sys
import os
import time
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.geometric.tool_sdf import (
    get_cached_tool_sdf,
    compute_tool_sdf_vtk,
    compute_tool_sdf_trimesh,
    load_tool_mesh_for_sdf,
    clear_tool_sdf_cache,
    apply_tool_sdf_to_volume
)
from vtkmodules.util import numpy_support


def visualize_sdf_slices(tool_sdf, title="Tool SDF Visualization"):
    """
    Visualize SDF as 2D slices along each axis.
    """
    sdf_grid = tool_sdf.sdf_grid
    
    # Find middle slices
    mid_x = sdf_grid.shape[0] // 2
    mid_y = sdf_grid.shape[1] // 2
    mid_z = sdf_grid.shape[2] // 2
    
    fig, axes = plt.subplots(2, 3, figsize=(15, 10))
    fig.suptitle(title, fontsize=16)
    
    # YZ plane (slice at mid X)
    slice_yz = sdf_grid[mid_x, :, :]
    im1 = axes[0, 0].imshow(slice_yz.T, origin='lower', cmap='RdBu_r', 
                            vmin=-10, vmax=10, aspect='auto')
    axes[0, 0].set_title(f'YZ Plane (X={mid_x})')
    axes[0, 0].set_xlabel('Y index')
    axes[0, 0].set_ylabel('Z index')
    axes[0, 0].axhline(mid_z, color='yellow', linestyle='--', alpha=0.5)
    axes[0, 0].axvline(mid_y, color='yellow', linestyle='--', alpha=0.5)
    plt.colorbar(im1, ax=axes[0, 0], label='Distance (mm)')
    
    # XZ plane (slice at mid Y)
    slice_xz = sdf_grid[:, mid_y, :]
    im2 = axes[0, 1].imshow(slice_xz.T, origin='lower', cmap='RdBu_r',
                            vmin=-10, vmax=10, aspect='auto')
    axes[0, 1].set_title(f'XZ Plane (Y={mid_y})')
    axes[0, 1].set_xlabel('X index')
    axes[0, 1].set_ylabel('Z index')
    axes[0, 1].axhline(mid_z, color='yellow', linestyle='--', alpha=0.5)
    axes[0, 1].axvline(mid_x, color='yellow', linestyle='--', alpha=0.5)
    plt.colorbar(im2, ax=axes[0, 1], label='Distance (mm)')
    
    # XY plane (slice at mid Z)
    slice_xy = sdf_grid[:, :, mid_z]
    im3 = axes[0, 2].imshow(slice_xy.T, origin='lower', cmap='RdBu_r',
                            vmin=-10, vmax=10, aspect='auto')
    axes[0, 2].set_title(f'XY Plane (Z={mid_z})')
    axes[0, 2].set_xlabel('X index')
    axes[0, 2].set_ylabel('Y index')
    axes[0, 2].axhline(mid_y, color='yellow', linestyle='--', alpha=0.5)
    axes[0, 2].axvline(mid_x, color='yellow', linestyle='--', alpha=0.5)
    plt.colorbar(im3, ax=axes[0, 2], label='Distance (mm)')
    
    # Bottom row: Zero-level contours (tool surface)
    # YZ plane
    axes[1, 0].contour(slice_yz.T, levels=[0], colors='red', linewidths=2)
    axes[1, 0].imshow(slice_yz.T, origin='lower', cmap='gray', alpha=0.3, aspect='auto')
    axes[1, 0].set_title('YZ Surface (distance=0)')
    axes[1, 0].set_xlabel('Y index')
    axes[1, 0].set_ylabel('Z index')
    
    # XZ plane
    axes[1, 1].contour(slice_xz.T, levels=[0], colors='red', linewidths=2)
    axes[1, 1].imshow(slice_xz.T, origin='lower', cmap='gray', alpha=0.3, aspect='auto')
    axes[1, 1].set_title('XZ Surface (distance=0)')
    axes[1, 1].set_xlabel('X index')
    axes[1, 1].set_ylabel('Z index')
    
    # XY plane
    axes[1, 2].contour(slice_xy.T, levels=[0], colors='red', linewidths=2)
    axes[1, 2].imshow(slice_xy.T, origin='lower', cmap='gray', alpha=0.3, aspect='auto')
    axes[1, 2].set_title('XY Surface (distance=0)')
    axes[1, 2].set_xlabel('X index')
    axes[1, 2].set_ylabel('Y index')
    
    plt.tight_layout()
    return fig


def visualize_sdf_histogram(tool_sdf, title="SDF Distance Distribution"):
    """
    Plot histogram of SDF values.
    """
    fig, axes = plt.subplots(1, 2, figsize=(12, 4))
    fig.suptitle(title, fontsize=14)
    
    sdf_flat = tool_sdf.sdf_grid.flatten()
    
    # Full range histogram
    axes[0].hist(sdf_flat, bins=100, alpha=0.7, edgecolor='black')
    axes[0].axvline(0, color='red', linestyle='--', linewidth=2, label='Surface (d=0)')
    axes[0].set_xlabel('Signed Distance (mm)')
    axes[0].set_ylabel('Frequency')
    axes[0].set_title('Full Range')
    axes[0].legend()
    axes[0].grid(True, alpha=0.3)
    
    # Zoomed histogram near surface
    mask = np.abs(sdf_flat) < 5  # Within 5mm of surface
    axes[1].hist(sdf_flat[mask], bins=100, alpha=0.7, edgecolor='black', color='orange')
    axes[1].axvline(0, color='red', linestyle='--', linewidth=2, label='Surface (d=0)')
    axes[1].set_xlabel('Signed Distance (mm)')
    axes[1].set_ylabel('Frequency')
    axes[1].set_title('Near Surface (±5mm)')
    axes[1].legend()
    axes[1].grid(True, alpha=0.3)
    
    plt.tight_layout()
    return fig


def compare_sdf_methods(tool_sdf_vtk, tool_sdf_trimesh):
    """
    Compare two SDF methods by computing difference.
    """
    # Both SDFs should have same dimensions if computed with same parameters
    if tool_sdf_vtk.shape != tool_sdf_trimesh.shape:
        print("Warning: SDF grids have different dimensions!")
        print(f"  VTK: {tool_sdf_vtk.shape}")
        print(f"  Trimesh: {tool_sdf_trimesh.shape}")
        return None
    
    diff = np.abs(tool_sdf_vtk.sdf_grid - tool_sdf_trimesh.sdf_grid)
    
    fig, axes = plt.subplots(1, 3, figsize=(15, 4))
    fig.suptitle('VTK vs Trimesh SDF Comparison', fontsize=14)
    
    # Middle slices
    mid_x = diff.shape[0] // 2
    mid_y = diff.shape[1] // 2
    mid_z = diff.shape[2] // 2
    
    # YZ plane difference
    im1 = axes[0].imshow(diff[mid_x, :, :].T, origin='lower', cmap='hot', aspect='auto')
    axes[0].set_title(f'Absolute Difference YZ (X={mid_x})')
    axes[0].set_xlabel('Y index')
    axes[0].set_ylabel('Z index')
    plt.colorbar(im1, ax=axes[0], label='|VTK - Trimesh| (mm)')
    
    # XZ plane difference
    im2 = axes[1].imshow(diff[:, mid_y, :].T, origin='lower', cmap='hot', aspect='auto')
    axes[1].set_title(f'Absolute Difference XZ (Y={mid_y})')
    axes[1].set_xlabel('X index')
    axes[1].set_ylabel('Z index')
    plt.colorbar(im2, ax=axes[1], label='|VTK - Trimesh| (mm)')
    
    # Histogram of differences
    axes[2].hist(diff.flatten(), bins=100, alpha=0.7, edgecolor='black')
    axes[2].set_xlabel('Absolute Difference (mm)')
    axes[2].set_ylabel('Frequency')
    axes[2].set_title('Difference Distribution')
    axes[2].grid(True, alpha=0.3)
    
    # Stats
    print("\n" + "="*60)
    print("SDF COMPARISON STATISTICS")
    print("="*60)
    print(f"Mean absolute difference:    {np.mean(diff):.4f} mm")
    print(f"Max absolute difference:     {np.max(diff):.4f} mm")
    print(f"Std deviation:               {np.std(diff):.4f} mm")
    print(f"95th percentile difference:  {np.percentile(diff, 95):.4f} mm")
    print("="*60)
    
    plt.tight_layout()
    return fig


def test_material_removal():
    """
    Test the apply_tool_sdf_to_volume function with a simple lens.
    """
    print("\n" + "="*60)
    print("TESTING MATERIAL REMOVAL")
    print("="*60)
    
    # Create a simple spherical lens volume
    resolution = 0.5
    size = 30  # mm
    dim = int(size / resolution)
    
    lens_volume = np.zeros((dim, dim, dim), dtype=np.float32)
    origin = np.array([-size/2, -size/2, -size/2])
    
    # Fill with a sphere
    center = np.array([0, 0, 0])
    radius = 10.0
    
    for ix in range(dim):
        for iy in range(dim):
            for iz in range(dim):
                x = origin[0] + ix * resolution
                y = origin[1] + iy * resolution
                z = origin[2] + iz * resolution
                
                dist = np.sqrt((x-center[0])**2 + (y-center[1])**2 + (z-center[2])**2)
                if dist < radius:
                    lens_volume[ix, iy, iz] = 100.0
    
    initial_material = np.sum(lens_volume > 0)
    print(f"Initial material voxels: {initial_material}")
    
    # Load a tool and compute SDF
    tool_file = Path(__file__).parent.parent / "assets" / "bevel_rough.vtk"
    if not tool_file.exists():
        print(f"Warning: Tool file not found: {tool_file}")
        print("Skipping material removal test")
        return None
    
    tool_sdf = get_cached_tool_sdf(
        tool_id="bevel_test",
        vtk_filename=str(tool_file),
        tool_name="Bevel Wheel",
        resolution=resolution
    )
    
    # Apply tool at center
    tool_position = np.array([0, 0, 0])
    
    start_time = time.time()
    carved_volume = apply_tool_sdf_to_volume(
        lens_volume=lens_volume.copy(),
        lens_origin=origin,
        lens_spacing=resolution,
        tool_sdf=tool_sdf,
        tool_position=tool_position,
        invert_tool=True
    )
    carve_time = time.time() - start_time
    
    final_material = np.sum(carved_volume > 0)
    removed_material = initial_material - final_material
    
    print(f"Final material voxels:   {final_material}")
    print(f"Removed voxels:          {removed_material}")
    print(f"Percentage removed:      {100.0 * removed_material / initial_material:.1f}%")
    print(f"Carving time:            {carve_time:.3f} seconds")
    
    # Visualize before/after
    fig, axes = plt.subplots(2, 3, figsize=(15, 10))
    fig.suptitle('Material Removal Test', fontsize=16)
    
    mid_x = dim // 2
    mid_y = dim // 2
    mid_z = dim // 2
    
    # Before
    axes[0, 0].imshow(lens_volume[mid_x, :, :].T, origin='lower', cmap='gray')
    axes[0, 0].set_title('Before - YZ')
    axes[0, 1].imshow(lens_volume[:, mid_y, :].T, origin='lower', cmap='gray')
    axes[0, 1].set_title('Before - XZ')
    axes[0, 2].imshow(lens_volume[:, :, mid_z].T, origin='lower', cmap='gray')
    axes[0, 2].set_title('Before - XY')
    
    # After
    axes[1, 0].imshow(carved_volume[mid_x, :, :].T, origin='lower', cmap='gray')
    axes[1, 0].set_title('After - YZ')
    axes[1, 1].imshow(carved_volume[:, mid_y, :].T, origin='lower', cmap='gray')
    axes[1, 1].set_title('After - XZ')
    axes[1, 2].imshow(carved_volume[:, :, mid_z].T, origin='lower', cmap='gray')
    axes[1, 2].set_title('After - XY')
    
    plt.tight_layout()
    return fig


def main():
    """
    Main test function.
    """
    print("="*60)
    print("TOOL SDF TESTING AND COMPARISON")
    print("="*60)
    
    # Clear any existing cache
    clear_tool_sdf_cache()
    
    # Find tool mesh file
    tool_file = Path(__file__).parent.parent / "assets" / "bevel_rough.vtk"
    
    if not tool_file.exists():
        print(f"\nERROR: Tool mesh file not found: {tool_file}")
        print("Please ensure the file exists before running this test.")
        return
    
    print(f"\nUsing tool mesh: {tool_file}")
    
    # Test parameters
    resolution = 0.3  # mm per voxel
    padding = 2.0     # mm
    
    # Load mesh once
    print("\n" + "-"*60)
    print("LOADING TOOL MESH")
    print("-"*60)
    polydata = load_tool_mesh_for_sdf(str(tool_file))
    
    # Convert to trimesh format
    vertices = numpy_support.vtk_to_numpy(polydata.GetPoints().GetData())
    polys = polydata.GetPolys()
    cell_array = numpy_support.vtk_to_numpy(polys.GetData())
    faces = cell_array.reshape(-1, 4)[:, 1:]
    
    # Test 1: VTK method
    print("\n" + "-"*60)
    print("TEST 1: VTK METHOD (vtkImplicitPolyDataDistance)")
    print("-"*60)
    
    start_time = time.time()
    tool_sdf_vtk = compute_tool_sdf_vtk(
        polydata=polydata,
        resolution=resolution,
        padding=padding,
        tool_id="bevel_vtk",
        tool_name="Bevel Wheel (VTK)"
    )
    vtk_time = time.time() - start_time
    
    print(f"\nVTK method completed in: {vtk_time:.2f} seconds")
    
    # Test 2: Trimesh method
    # print("\n" + "-"*60)
    # print("TEST 2: TRIMESH METHOD (Ray Casting)")
    # print("-"*60)
    
    # start_time = time.time()
    # tool_sdf_trimesh = compute_tool_sdf_trimesh(
    #     vertices=vertices,
    #     faces=faces,
    #     resolution=resolution,
    #     padding=padding,
    #     tool_id="bevel_trimesh",
    #     tool_name="Bevel Wheel (Trimesh)"
    # )
    # trimesh_time = time.time() - start_time
    
    # print(f"\nTrimesh method completed in: {trimesh_time:.2f} seconds")
    
    # Performance comparison
    # print("\n" + "="*60)
    # print("PERFORMANCE COMPARISON")
    # print("="*60)
    # print(f"VTK Time:      {vtk_time:.2f} seconds")
    # print(f"Trimesh Time:  {trimesh_time:.2f} seconds")
    # print(f"Speedup:       {vtk_time / trimesh_time:.2f}x {'(Trimesh faster)' if trimesh_time < vtk_time else '(VTK faster)'}")
    # print("="*60)
    
    # Visualizations
    print("\nGenerating visualizations...")
    
    # VTK SDF visualization
    fig1 = visualize_sdf_slices(tool_sdf_vtk, "VTK Method - SDF Slices")
    
    # Trimesh SDF visualization
    # fig2 = visualize_sdf_slices(tool_sdf_trimesh, "Trimesh Method - SDF Slices")
    
    # Histograms
    fig3 = visualize_sdf_histogram(tool_sdf_vtk, "VTK Method - Distance Distribution")
    # fig4 = visualize_sdf_histogram(tool_sdf_trimesh, "Trimesh Method - Distance Distribution")
    
    # Comparison
    # fig5 = compare_sdf_methods(tool_sdf_vtk, tool_sdf_trimesh)
    
    # Material removal test
    fig6 = test_material_removal()
    
    # Save figures
    output_dir = Path(__file__).parent / "output"
    output_dir.mkdir(exist_ok=True)
    
    # print(f"\nSaving figures to: {output_dir}")
    # fig1.savefig(output_dir / "sdf_vtk_slices.png", dpi=150, bbox_inches='tight')
    # fig2.savefig(output_dir / "sdf_trimesh_slices.png", dpi=150, bbox_inches='tight')
    # fig3.savefig(output_dir / "sdf_vtk_histogram.png", dpi=150, bbox_inches='tight')
    # fig4.savefig(output_dir / "sdf_trimesh_histogram.png", dpi=150, bbox_inches='tight')
    # if fig5:
    #     fig5.savefig(output_dir / "sdf_comparison.png", dpi=150, bbox_inches='tight')
    # if fig6:
    #     fig6.savefig(output_dir / "material_removal_test.png", dpi=150, bbox_inches='tight')
    
    print("\n" + "="*60)
    print("TEST COMPLETE - Showing plots...")
    print("="*60)
    print("Close the plot windows to exit.")
    
    plt.show()


if __name__ == "__main__":
    main()
