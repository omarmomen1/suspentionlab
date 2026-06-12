import csv
import io
import math

def parse_telemetry_csv(content: str) -> dict:
    """
    Parses generic telemetry CSV files (e.g. from AiM, MoTeC).
    Attempts to identify common channels: Time, Speed, LatG, LongG, YawRate.
    Returns a dictionary of arrays.
    """
    lines = content.splitlines()
    
    # Heuristically find the header row (the first row with 'time' or 'sec')
    header_idx = -1
    for i, line in enumerate(lines[:30]):
        line_lower = line.lower()
        if 'time' in line_lower or 'sec' in line_lower:
            header_idx = i
            break
            
    if header_idx == -1:
        # Fallback: assume first row is header
        header_idx = 0
        
    headers = [h.strip().lower() for h in lines[header_idx].split(',')]
    
    # Map common column names to our standard keys
    col_map = {}
    for i, h in enumerate(headers):
        if 'time' in h or 'sec' in h:
            col_map['time'] = i
        elif 'speed' in h or 'v_x' in h or 'kmh' in h:
            col_map['speed'] = i
        elif 'latg' in h or 'lat_g' in h or 'a_y' in h or 'g force lat' in h:
            col_map['lat_g'] = i
        elif 'longg' in h or 'long_g' in h or 'a_x' in h or 'g force long' in h:
            col_map['long_g'] = i
        elif 'yaw' in h or 'omega_z' in h:
            col_map['yaw_rate'] = i

    data = {
        'time': [],
        'speed': [],
        'lat_g': [],
        'long_g': [],
        'yaw_rate': []
    }
    
    reader = csv.reader(lines[header_idx+1:])
    for row in reader:
        if not row:
            continue
            
        try:
            if 'time' in col_map and len(row) > col_map['time']:
                data['time'].append(float(row[col_map['time']]))
            if 'speed' in col_map and len(row) > col_map['speed']:
                data['speed'].append(float(row[col_map['speed']]))
            if 'lat_g' in col_map and len(row) > col_map['lat_g']:
                data['lat_g'].append(float(row[col_map['lat_g']]))
            if 'long_g' in col_map and len(row) > col_map['long_g']:
                data['long_g'].append(float(row[col_map['long_g']]))
            if 'yaw_rate' in col_map and len(row) > col_map['yaw_rate']:
                data['yaw_rate'].append(float(row[col_map['yaw_rate']]))
        except ValueError:
            pass # Skip rows with non-numeric data
            
    return data
