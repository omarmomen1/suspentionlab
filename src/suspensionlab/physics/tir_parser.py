import re
from typing import Optional
from .magic_formula import TireCoeffs

def parse_tir_file(content: str) -> TireCoeffs:
    """
    Parses a standard .tir (Tyre Property File) and maps the Pacejka coefficients
    to the TireCoeffs dataclass. Falls back to default values for missing coefficients.
    
    Format example:
    PCY1 = 1.3507 $Shape factor Cfy for lateral forces
    """
    coeffs = TireCoeffs()
    
    # Map of .tir keys (uppercase) to TireCoeffs attributes
    mapping = {
        # Lateral
        'PCY1': 'pCy1',
        'PDY1': 'pDy1',
        'PEY1': 'pEy1',
        'PKY1': 'pKy1',
        'PKY2': 'pKy2',
        
        # Longitudinal
        'PCX1': 'pCx1',
        'PDX1': 'pDx1',
        'PEX1': 'pEx1',
        'PKX1': 'pKx1',
        'PKX2': 'pKx2',
        
        # Combined
        'RBX1': 'rBx1',
        'RBY1': 'rBy1',
        'RCX1': 'rCx1',
        'RCY1': 'rCy1',
    }
    
    for line in content.splitlines():
        line = line.strip()
        
        # Ignore comments and section headers
        if not line or line.startswith('$') or line.startswith('!') or line.startswith('['):
            continue
            
        # Parse key = value
        # e.g. "PCY1 = 1.3507 $Shape factor"
        parts = line.split('=')
        if len(parts) >= 2:
            key_part = parts[0].strip().upper()
            
            # The value might have a comment attached to it with '$' or '!'
            val_part = parts[1].split('$')[0].split('!')[0].strip()
            
            if key_part in mapping:
                try:
                    val_float = float(val_part)
                    setattr(coeffs, mapping[key_part], val_float)
                except ValueError:
                    # If it fails to parse as float, just skip it
                    pass
                    
    return coeffs
