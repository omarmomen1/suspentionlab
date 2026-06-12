import os

filepath = r"C:\Users\omaar\Downloads\project\src\suspensionlab\physics\magic_formula.py"
with open(filepath, "r", encoding="utf-8") as f:
    content = f.read()

# Add pKx3
old_pkx2 = """    pKx1: float = 22.0
    pKx2: float = 0.4"""
new_pkx2 = """    pKx1: float = 22.0
    pKx2: float = 0.4
    pKx3: float = 0.4"""
content = content.replace(old_pkx2, new_pkx2)

# Update Kx
old_kx = "    Kx = Fz * (coeffs.pKx1 + coeffs.pKx2 * dfz) * np.exp(coeffs.pKx2 * dfz)"
new_kx = "    Kx = Fz * (coeffs.pKx1 + coeffs.pKx2 * dfz) * np.exp(coeffs.pKx3 * dfz)"
content = content.replace(old_kx, new_kx)

# Update Combined slip
old_combined = """    # 3. Combined Slip Weighting (Friction Ellipse)
    # Very simplified combined slip using weighting functions
    weight_x = np.cos(coeffs.rCx1 * np.arctan(coeffs.rBx1 * alpha_rad))
    weight_y = np.cos(coeffs.rCy1 * np.arctan(coeffs.rBy1 * kappa))

    Fx = Fx0 * weight_x
    Fy = Fy0 * weight_y"""

new_combined = """    # 3. Combined Slip Weighting (Normalized Slip Vector)
    # Rigorous combined slip scaling to prevent friction bounds violations
    sigma = np.sqrt(kappa**2 + alpha_rad**2)
    
    if sigma > 0:
        weight_x = abs(kappa) / sigma
        weight_y = abs(alpha_rad) / sigma
        
        Fx = Fx0 * weight_x
        Fy = Fy0 * weight_y
    else:
        Fx = Fx0
        Fy = Fy0"""
content = content.replace(old_combined, new_combined)

with open(filepath, "w", encoding="utf-8") as f:
    f.write(content)

print("Magic formula refactored.")
