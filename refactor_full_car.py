import os

project_dir = r"C:\Users\omaar\Downloads\project"

# 1. Update full_car.py
full_car_path = os.path.join(project_dir, r"src\suspensionlab\physics\full_car.py")
with open(full_car_path, "r", encoding="utf-8") as f:
    content = f.read()

# Replace calculate_full_car_kpis
old_kpis = """def calculate_full_car_kpis(params: FullCarParams, res: dict) -> dict:
    \"\"\"Calculate natural frequencies and RMS values.\"\"\"
    A, _, _, _ = build_full_car_state_space(params)
    eigenvalues = np.linalg.eigvals(A)
    
    # Filter eigenvalues for frequency (imaginary > 0)
    omega = np.sort(np.imag(eigenvalues[np.imag(eigenvalues) > 1e-3]))
    
    # Extract frequencies in Hz
    # Typically: heave, pitch, roll, front hop, rear hop
    # We will pick the 5 lowest unique frequencies roughly
    f_n = omega / (2 * np.pi)
    
    # Safely pad if fewer than 5 modes found
    f_n_sorted = np.sort(f_n)
    while len(f_n_sorted) < 5:
        f_n_sorted = np.append(f_n_sorted, 0.0)
        
    res["f_n_heave"] = float(f_n_sorted[0])
    res["f_n_roll"] = float(f_n_sorted[1])
    res["f_n_pitch"] = float(f_n_sorted[2])
    res["f_n_uf"] = float(f_n_sorted[3])
    res["f_n_ur"] = float(f_n_sorted[4])"""

new_kpis = """def calculate_full_car_kpis(params: FullCarParams, res: dict) -> dict:
    \"\"\"Calculate natural frequencies and RMS values.\"\"\"
    A, _, _, _ = build_full_car_state_space(params)
    vals, vecs = np.linalg.eig(A)
    
    idx = np.where(np.imag(vals) > 1e-3)[0]
    vals = vals[idx]
    vecs = vecs[:, idx]
    
    modes = {"heave": 0.0, "pitch": 0.0, "roll": 0.0, "uf": 0.0, "ur": 0.0}
    for i in range(len(vals)):
        freq = float(np.imag(vals[i]) / (2 * np.pi))
        mode_shape = np.abs(vecs[:7, i])
        max_idx = int(np.argmax(mode_shape))
        
        if max_idx == 0:
            modes["heave"] = freq
        elif max_idx == 1:
            modes["pitch"] = freq
        elif max_idx == 2:
            modes["roll"] = freq
        elif max_idx in [3, 4]:
            modes["uf"] = max(modes["uf"], freq)
        elif max_idx in [5, 6]:
            modes["ur"] = max(modes["ur"], freq)
            
    res["f_n_heave"] = modes["heave"]
    res["f_n_roll"] = modes["roll"]
    res["f_n_pitch"] = modes["pitch"]
    res["f_n_uf"] = modes["uf"]
    res["f_n_ur"] = modes["ur"]"""
content = content.replace(old_kpis, new_kpis)

# Fix Roll Stiffness Math and remove cg_lateral_accel
old_roll_1 = "K_roll_f = 0.5 * params.k_sf * params.tw_f**2 + params.k_arb_f * params.tw_f**2"
new_roll_1 = "K_roll_f = 0.5 * params.k_sf * params.tw_f**2 + 0.5 * params.k_arb_f * params.tw_f**2"
content = content.replace(old_roll_1, new_roll_1)

old_roll_2 = "K_roll_r = 0.5 * params.k_sr * params.tw_r**2 + params.k_arb_r * params.tw_r**2"
new_roll_2 = "K_roll_r = 0.5 * params.k_sr * params.tw_r**2 + 0.5 * params.k_arb_r * params.tw_r**2"
content = content.replace(old_roll_2, new_roll_2)

old_lat_accel = """    # CG lateral acceleration (kinematic approx: a_y = phi_ddot * h_cg ... but we lack h_cg)
    # The prompt requested cg_lateral_accel. Since we simulate roll based on road inputs or ARB, 
    # we can just use roll acceleration as a proxy, or assume 1g lateral input.
    # Without lateral force input, cg_lateral_accel = 0.
    res["cg_lateral_accel"] = np.zeros_like(time_out).tolist()"""
content = content.replace(old_lat_accel, "")

with open(full_car_path, "w", encoding="utf-8") as f:
    f.write(content)


# 2. Update models.py
models_path = os.path.join(project_dir, r"src\suspensionlab\shared\models.py")
with open(models_path, "r", encoding="utf-8") as f:
    models_content = f.read()

# remove cg_lateral_accel: list[float]
models_content = "\n".join([line for line in models_content.split("\n") if "cg_lateral_accel" not in line])

with open(models_path, "w", encoding="utf-8") as f:
    f.write(models_content)

print("Full car refactored.")
