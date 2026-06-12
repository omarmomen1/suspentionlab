import os

filepath = r"C:\Users\omaar\Downloads\project\src\suspensionlab\physics\handling_model.py"
with open(filepath, "r", encoding="utf-8") as f:
    content = f.read()

# Update max(v_x, 0.1) with a comment
old_v_x = """    # Prevent divide by zero at standstill
    v_x = max(v_x, 0.1)"""
new_v_x = """    # Prevent divide by zero at standstill
    # LIMITATION: Model is valid for speeds above ~2 km/h. Does not support reverse or complete stop.
    v_x = max(v_x, 0.1)"""
content = content.replace(old_v_x, new_v_x)

# 2. Quasi-Static Load Transfer 2-step iteration
old_load = """    # Approximate accelerations for load transfer (using previous state or simple estimation)
    # To avoid algebraic loops, we estimate a_x and a_y kinematically 
    a_x_est = (throttle * max_accel) - (brake * max_decel) - (F_aero_d / p.m)
    a_y_est = v_x * omega_z # Steady state turn
    
    delta_Fz_long = (p.m * a_x_est * p.h_cg) / L
    
    Fz_f_total = (W_total * p.b / L) - delta_Fz_long
    Fz_r_total = (W_total * p.a / L) + delta_Fz_long
    
    delta_Fz_lat_f = (p.m * a_y_est * p.h_cg / p.tw_f) * p.roll_dist
    delta_Fz_lat_r = (p.m * a_y_est * p.h_cg / p.tw_r) * (1 - p.roll_dist)

    Fz_fl = max(Fz_f_total / 2 - delta_Fz_lat_f, 10.0)
    Fz_fr = max(Fz_f_total / 2 + delta_Fz_lat_f, 10.0)
    Fz_rl = max(Fz_r_total / 2 - delta_Fz_lat_r, 10.0)
    Fz_rr = max(Fz_r_total / 2 + delta_Fz_lat_r, 10.0)

    # 3. Tire Forces
    Fx_fl, Fy_fl = calc_tire_forces(Fz_fl, alpha_fl, kappa_f, 0.0, p.tire_coeffs)
    Fx_fr, Fy_fr = calc_tire_forces(Fz_fr, alpha_fr, kappa_f, 0.0, p.tire_coeffs)
    Fx_rl, Fy_rl = calc_tire_forces(Fz_rl, alpha_rl, kappa_r, 0.0, p.tire_coeffs)
    Fx_rr, Fy_rr = calc_tire_forces(Fz_rr, alpha_rr, kappa_r, 0.0, p.tire_coeffs)

    # Resolve front forces to body frame (steering angle)
    cos_d, sin_d = np.cos(delta), np.sin(delta)
    Fx_fl_b = Fx_fl * cos_d - Fy_fl * sin_d
    Fy_fl_b = Fx_fl * sin_d + Fy_fl * cos_d
    Fx_fr_b = Fx_fr * cos_d - Fy_fr * sin_d
    Fy_fr_b = Fx_fr * sin_d + Fy_fr * cos_d

    # Total body forces
    Sum_Fx = Fx_fl_b + Fx_fr_b + Fx_rl + Fx_rr - F_aero_d
    Sum_Fy = Fy_fl_b + Fy_fr_b + Fy_rl + Fy_rr
    
    # Yaw moment:
    # Mz = a * Fy_front - b * Fy_rear - (tw/2) * Fx_left + (tw/2) * Fx_right
    Sum_Mz = (p.a * (Fy_fl_b + Fy_fr_b) - p.b * (Fy_rl + Fy_rr) 
              - (p.tw_f / 2) * (Fx_fl_b - Fx_fr_b) 
              - (p.tw_r / 2) * (Fx_rl - Fx_rr))"""

new_load = """    # 2. Quasi-Static Load Transfer (2-step Predictor-Corrector to break algebraic loop)
    # Step 1: Predictor (Kinematic estimate)
    a_x_est = (throttle * max_accel) - (brake * max_decel) - (F_aero_d / p.m)
    a_y_est = v_x * omega_z # Steady state turn
    
    cos_d, sin_d = np.cos(delta), np.sin(delta)
    
    for _ in range(2):
        delta_Fz_long = (p.m * a_x_est * p.h_cg) / L
        
        Fz_f_total = (W_total * p.b / L) - delta_Fz_long
        Fz_r_total = (W_total * p.a / L) + delta_Fz_long
        
        delta_Fz_lat_f = (p.m * a_y_est * p.h_cg / p.tw_f) * p.roll_dist
        delta_Fz_lat_r = (p.m * a_y_est * p.h_cg / p.tw_r) * (1 - p.roll_dist)

        Fz_fl = max(Fz_f_total / 2 - delta_Fz_lat_f, 10.0)
        Fz_fr = max(Fz_f_total / 2 + delta_Fz_lat_f, 10.0)
        Fz_rl = max(Fz_r_total / 2 - delta_Fz_lat_r, 10.0)
        Fz_rr = max(Fz_r_total / 2 + delta_Fz_lat_r, 10.0)

        # 3. Tire Forces
        Fx_fl, Fy_fl = calc_tire_forces(Fz_fl, alpha_fl, kappa_f, 0.0, p.tire_coeffs)
        Fx_fr, Fy_fr = calc_tire_forces(Fz_fr, alpha_fr, kappa_f, 0.0, p.tire_coeffs)
        Fx_rl, Fy_rl = calc_tire_forces(Fz_rl, alpha_rl, kappa_r, 0.0, p.tire_coeffs)
        Fx_rr, Fy_rr = calc_tire_forces(Fz_rr, alpha_rr, kappa_r, 0.0, p.tire_coeffs)

        # Resolve front forces to body frame (steering angle)
        Fx_fl_b = Fx_fl * cos_d - Fy_fl * sin_d
        Fy_fl_b = Fx_fl * sin_d + Fy_fl * cos_d
        Fx_fr_b = Fx_fr * cos_d - Fy_fr * sin_d
        Fy_fr_b = Fx_fr * sin_d + Fy_fr * cos_d

        # Total body forces
        Sum_Fx = Fx_fl_b + Fx_fr_b + Fx_rl + Fx_rr - F_aero_d
        Sum_Fy = Fy_fl_b + Fy_fr_b + Fy_rl + Fy_rr
        
        # Step 2: Corrector (Update accelerations from actual forces)
        a_x_est = Sum_Fx / p.m
        a_y_est = Sum_Fy / p.m

    # Yaw moment:
    Sum_Mz = (p.a * (Fy_fl_b + Fy_fr_b) - p.b * (Fy_rl + Fy_rr) 
              - (p.tw_f / 2) * (Fx_fl_b - Fx_fr_b) 
              - (p.tw_r / 2) * (Fx_rl - Fx_rr))"""
content = content.replace(old_load, new_load)

with open(filepath, "w", encoding="utf-8") as f:
    f.write(content)

print("Handling model refactored.")
