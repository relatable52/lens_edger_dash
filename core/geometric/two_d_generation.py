import numpy as np
from core.models.lenses import OMAJob, FrameSide

def polar_to_cartesian(radii: np.ndarray):
    """ Converts polar coordinates to Cartesian coordinates. """
    num_points = len(radii)

    angles = np.linspace(0, 2 * np.pi, num_points, endpoint=False)
    x = radii * np.cos(angles)
    y = radii * np.sin(angles)
    
    x = np.append(x, x[0])
    y = np.append(y, y[0])
    return x, y

def get_assembly_contours(job: OMAJob):
    """
    Returns the X and Y coordinates for Left and Right eyes 
    positioned correctly relative to the bridge center (0,0).
    """
    center_offset_x = job.fpd / 2.0
    
    contours = {}
    
    # --- Right Eye Processing ---
    rx_local, ry_local = polar_to_cartesian(job.right.radii)
    # Shift X by +FPD/2
    contours['R'] = {
        'x': rx_local + center_offset_x,
        'y': ry_local, 
        'center': (center_offset_x, 0)
    }

    # --- Left Eye Processing ---
    lx_local, ly_local = polar_to_cartesian(job.left.radii)
    # Mirroring logic: 
    # Usually OMA stores Left eye as if looking from front, but sometimes mirrored.
    # Assuming standard "As worn" or "As viewed from front". 
    # Left eye center is at -FPD/2.
    contours['L'] = {
        'x': lx_local - center_offset_x,
        'y': ly_local,
        'center': (-center_offset_x, 0)
    }
    
    return contours

def get_optical_centers(job: OMAJob, contours):
    """
    Calculates the position of the Pupil (Optical Center) relative to (0,0).
    Formula: 
       X_pupil = +/- IPD (Monocular)
       Y_pupil = OCHT - (VBOX / 2)  (Assuming Center is 0, so bottom is -VBOX/2)
    """
    ocs = {}
    
    # Right Eye
    if job.right and 'R' in contours:
        # Pupil X is simply the Monocular IPD to the right
        px = job.right.ipd
        # Pupil Y: Convert OCHT (from bottom) to Y (from center)
        py = job.right.ocht - (job.right.vbox / 2.0)
        ocs['R'] = (px, py)
        
    # Left Eye
    if job.left and 'L' in contours:
        px = -job.left.ipd # To the left
        py = job.left.ocht - (job.left.vbox / 2.0)
        ocs['L'] = (px, py)
        
    return ocs

def get_bounding_boxes(job: OMAJob):
    """ Return the left and right bounding box from OMA data

    Args:
        job (OMAJob): OMA data
    """
    bouding_boxes = {}

    # Right eye
    if job.right:
        vx = job.fpd/2 - job.right.hbox/2 # Right lens bottom left corner
        vy = -job.right.vbox/2
        w = job.right.hbox
        h = job.right.vbox
        bouding_boxes['R'] = (vx, vy, w, h)
    # Left eye
    if job.left:
        vx = -job.fpd/2 - job.left.hbox/2 # Left lens bottom left corner
        vy = -job.left.vbox/2
        w = job.left.hbox
        h = job.left.vbox
        bouding_boxes['L'] = (vx, vy, w, h)

    return bouding_boxes