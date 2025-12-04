import numpy as np
from core.models.lenses import OMAJob, FrameSide

def parse_oma_content(content_string: str) -> OMAJob:
    """
    Parses raw OMA file content into a structured OMAJob object.
    
    Args:
        content_string (str): The raw text content of the .oma file.
        
    Returns:
        OMAJob: The populated data object.
    """
    lines = content_string.splitlines()
    
    # -- 1. Temporary Storage Dictionaries --
    # We parse into this structure first, then convert to Dataclasses
    # Assuming standard order or prompts logic: 1st block = Left, 2nd block = Right
    # (Note: Actual OMA specs vary, but we follow the prompt's implied order)
    parsed_sides = [
        {'R': [], 'Z': [], 'IPD': 0.0, 'OCHT': 0.0, 'HBOX': 0.0, 'VBOX': 0.0}, # Index 0 (Left)
        {'R': [], 'Z': [], 'IPD': 0.0, 'OCHT': 0.0, 'HBOX': 0.0, 'VBOX': 0.0}  # Index 1 (Right)
    ]
    common_data = {'FPD': 0.0, 'DBL': 0.0, 'JOB': "Unknown"}
    
    current_block_idx = -1
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        # -- Global Parameters --
        if line.startswith('JOB='):
            common_data['JOB'] = line.split('=')[1].replace('"', '')
        elif line.startswith('FPD='):
            common_data['FPD'] = float(line.split('=')[1])
        elif line.startswith('DBL='):
            common_data['DBL'] = float(line.split('=')[1])
            
        # -- Block Switching --
        # TRCFMT signals the start of a new trace block
        elif line.startswith('REQ=') or line.startswith('TRCFMT='):
            # Only increment if it's TRCFMT, or if REQ is the very start
            if line.startswith('TRCFMT='):
                current_block_idx += 1
        
        # -- Trace Data (R and Z) --
        elif line.startswith('R=') and 0 <= current_block_idx < 2:
            raw_vals = line[2:].strip().split(';')
            # Filter empty strings, convert to float, convert 1/100mm to mm
            vals = [float(x)/100.0 for x in raw_vals if x.strip()]
            parsed_sides[current_block_idx]['R'].extend(vals)
            
        elif line.startswith('Z=') and 0 <= current_block_idx < 2:
            raw_vals = line[2:].strip().split(';')
            vals = [float(x)/100.0 for x in raw_vals if x.strip()]
            parsed_sides[current_block_idx]['Z'].extend(vals)

        # -- Side Specific Parameters --
        # These fields (IPD, OCHT, etc) often come as "VAL;VAL" (Left;Right)
        # We need to distribute them to the temp dictionaries
        elif line.startswith(('IPD=', 'OCHT=', 'HBOX=', 'VBOX=')):
            key, val_str = line.split('=')
            vals = [float(v) for v in val_str.split(';') if v.strip()]
            
            # If 2 values exist, assign to [0] (Left) and [1] (Right)
            if len(vals) >= 2:
                parsed_sides[0][key] = vals[0]
                parsed_sides[1][key] = vals[1]
            # If only 1 value, assign to both (symmetric assumption)
            elif len(vals) == 1:
                parsed_sides[0][key] = vals[0]
                parsed_sides[1][key] = vals[0]

    # -- 2. Convert to Data Models --
    
    # Helper to build FrameSide object
    def build_side(idx, name):
        data = parsed_sides[idx]
        if not data['R']: # If no data found
            return None
        return FrameSide(
            side_name=name,
            radii=np.array(data['R'], dtype=np.float64),
            z_map=np.array(data['Z'], dtype=np.float64),
            ipd=data['IPD'],
            ocht=data['OCHT'],
            hbox=data['HBOX'],
            vbox=data['VBOX']
        )

    left_side = build_side(0, 'L')
    right_side = build_side(1, 'R')

    return OMAJob(
        job_id=common_data['JOB'],
        fpd=common_data['FPD'],
        dbl=common_data['DBL'],
        left=left_side,
        right=right_side
    )