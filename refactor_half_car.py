import os

filepath = r"C:\Users\omaar\Downloads\project\src\suspensionlab\physics\half_car.py"
with open(filepath, "r", encoding="utf-8") as f:
    content = f.read()

# 1. Add _compute_forces function
helper_code = """
def _compute_forces(p: HalfCarParams, z_s, dz_s, theta, dtheta, z_uf, dz_uf, z_ur, dz_ur):
    z_sf = z_s - p.a * theta
    z_sr = z_s + p.b * theta
    dz_sf = dz_s - p.a * dtheta
    dz_sr = dz_s + p.b * dtheta

    v_susp_f = dz_uf - dz_sf
    if p.damper_curve_v_f is not None and p.damper_curve_f_f is not None and len(p.damper_curve_v_f) > 1:
        F_damper_f = np.interp(v_susp_f, p.damper_curve_v_f, p.damper_curve_f_f)
    else:
        F_damper_f = p.c_f * v_susp_f
        
    v_susp_r = dz_ur - dz_sr
    if p.damper_curve_v_r is not None and p.damper_curve_f_r is not None and len(p.damper_curve_v_r) > 1:
        F_damper_r = np.interp(v_susp_r, p.damper_curve_v_r, p.damper_curve_f_r)
    else:
        F_damper_r = p.c_r * v_susp_r
        
    F_sf = p.k_sf * (z_uf - z_sf) + F_damper_f
    F_sr = p.k_sr * (z_ur - z_sr) + F_damper_r
    
    return F_sf, F_sr, z_sf, z_sr

def _half_car_ode(t, x, p: HalfCarParams, zr_fn, dzr_fn, t_delay: float):
"""
content = content.replace("def _half_car_ode(t, x, p: HalfCarParams, zr_fn, dzr_fn, t_delay: float):", helper_code)

# 2. Update _half_car_ode
ode_old = """    # Suspension deflections (compression is positive)
    z_sf = z_s - p.a * theta
    z_sr = z_s + p.b * theta
    dz_sf = dz_s - p.a * dtheta
    dz_sr = dz_s + p.b * dtheta

    # Forces
    v_susp_f = dz_uf - dz_sf
    if p.damper_curve_v_f is not None and p.damper_curve_f_f is not None and len(p.damper_curve_v_f) > 1:
        F_damper_f = np.interp(v_susp_f, p.damper_curve_v_f, p.damper_curve_f_f)
    else:
        F_damper_f = p.c_f * v_susp_f
        
    v_susp_r = dz_ur - dz_sr
    if p.damper_curve_v_r is not None and p.damper_curve_f_r is not None and len(p.damper_curve_v_r) > 1:
        F_damper_r = np.interp(v_susp_r, p.damper_curve_v_r, p.damper_curve_f_r)
    else:
        F_damper_r = p.c_r * v_susp_r
        
    F_sf = p.k_sf * (z_uf - z_sf) + F_damper_f
    F_sr = p.k_sr * (z_ur - z_sr) + F_damper_r

    # Accelerations"""
ode_new = """    F_sf, F_sr, _, _ = _compute_forces(p, z_s, dz_s, theta, dtheta, z_uf, dz_uf, z_ur, dz_ur)

    # Accelerations"""
content = content.replace(ode_old, ode_new)

# 3. Update simulate_time_response
sim_old = """    # Reconstruct accelerations
    z_sf = z_s - p.a * theta
    z_sr = z_s + p.b * theta
    dz_sf = dz_s - p.a * dtheta
    dz_sr = dz_s + p.b * dtheta

    F_sf = p.k_sf * (z_uf - z_sf) + p.c_f * (dz_uf - dz_sf)
    F_sr = p.k_sr * (z_ur - z_sr) + p.c_r * (dz_ur - dz_sr)

    ddz_s = (F_sf + F_sr) / p.m_s
    ddtheta = (-p.a * F_sf + p.b * F_sr) / p.I_y
    
    # The user requested susp_travel_f = z_uf - z_rf (which represents tire deflection here)
    susp_travel_f = z_uf - z_rf_arr
    susp_travel_r = z_ur - z_rr_arr"""
sim_new = """    # Reconstruct accelerations
    F_sf, F_sr, z_sf, z_sr = _compute_forces(p, z_s, dz_s, theta, dtheta, z_uf, dz_uf, z_ur, dz_ur)

    ddz_s = (F_sf + F_sr) / p.m_s
    ddtheta = (-p.a * F_sf + p.b * F_sr) / p.I_y
    
    susp_travel_f = z_sf - z_uf
    susp_travel_r = z_sr - z_ur"""
content = content.replace(sim_old, sim_new)

with open(filepath, "w", encoding="utf-8") as f:
    f.write(content)

print("Half car refactored.")
