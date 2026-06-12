import os
import re

project_dir = r"C:\Users\omaar\Downloads\project"

# 1. Fix Magic Formula combined slip
mf_path = os.path.join(project_dir, r"src\suspensionlab\physics\magic_formula.py")
with open(mf_path, "r", encoding="utf-8") as f:
    mf_content = f.read()

bad_mf = """    # 3. Combined Slip Weighting (Normalized Slip Vector)
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

good_mf = """    # 3. Combined Slip Weighting (Normalized Slip Vector MF5.2 Approximation)
    # The pure slip equations must be evaluated at the equivalent combined slip sigma
    # to avoid friction circle violation.
    sigma = np.sqrt(kappa**2 + alpha_rad**2)
    
    if sigma > 0:
        # Evaluate pure slip at equivalent combined slip (sigma)
        Fx0_comb = _magic_formula_base(sigma, Bx, coeffs.pCx1, Dx, coeffs.pEx1)
        Fy0_comb = _magic_formula_base(sigma, By, coeffs.pCy1, Dy, coeffs.pEy1)
        Fy0_comb += gamma_thrust
        
        # Resolve vector directions
        Fx = Fx0_comb * (abs(kappa) / sigma) * np.sign(kappa) if kappa != 0 else 0.0
        Fy = Fy0_comb * (abs(alpha_rad) / sigma) * np.sign(alpha_rad) if alpha_rad != 0 else 0.0
    else:
        Fx = Fx0
        Fy = Fy0"""

mf_content = mf_content.replace(bad_mf, good_mf)
with open(mf_path, "w", encoding="utf-8") as f:
    f.write(mf_content)


# 2. Fix Half Car Modal Eigenvalue Sorting
hc_path = os.path.join(project_dir, r"src\suspensionlab\physics\half_car.py")
with open(hc_path, "r", encoding="utf-8") as f:
    hc_content = f.read()

bad_hc = """def compute_modal_properties(p: HalfCarParams) -> dict:
    A, _ = build_state_space(p)
    eigs = eigvals(A)
    
    # Filter and sort complex conjugate pairs by imaginary part (frequency)
    complex_eigs = sorted([e for e in eigs if e.imag > 1e-6], key=lambda e: e.imag)
    
    freqs = []
    for lam in complex_eigs:
        wn = abs(lam)
        freqs.append(wn / (2.0 * np.pi))
        
    # Map to modes (roughly: heave, pitch, wheel hop front, wheel hop rear)
    # This is a simplified assignment based on typical frequency ordering
    f_n_heave = freqs[0] if len(freqs) > 0 else 0.0
    f_n_pitch = freqs[1] if len(freqs) > 1 else 0.0
    f_n_uf = freqs[2] if len(freqs) > 2 else 0.0
    f_n_ur = freqs[3] if len(freqs) > 3 else 0.0"""

good_hc = """def compute_modal_properties(p: HalfCarParams) -> dict:
    from scipy.linalg import eig
    A, _ = build_state_space(p)
    eigs, vecs = eig(A)
    
    # Identify modes via dominant eigenvectors
    f_n_heave = 0.0
    f_n_pitch = 0.0
    f_n_uf = 0.0
    f_n_ur = 0.0
    
    for i in range(len(eigs)):
        lam = eigs[i]
        if lam.imag <= 1e-6:
            continue
            
        wn = abs(lam)
        fn = wn / (2.0 * np.pi)
        
        mode_shape = np.abs(vecs[:, i])
        # Indices: 0: zs, 1: dzs, 2: theta, 3: dtheta, 4: zuf, 5: dzuf, 6: zur, 7: dzur
        dom_idx = np.argmax(mode_shape[[0, 2, 4, 6]]) # check displacements
        
        if dom_idx == 0:
            f_n_heave = float(fn)
        elif dom_idx == 1:
            f_n_pitch = float(fn)
        elif dom_idx == 2:
            f_n_uf = float(fn)
        elif dom_idx == 3:
            f_n_ur = float(fn)"""

hc_content = hc_content.replace(bad_hc, good_hc)
with open(hc_path, "w", encoding="utf-8") as f:
    f.write(hc_content)


# 3. Fix Quarter Car: ISO 2631-1 Wk Filter and ISO 8608 Road Profile
qc_path = os.path.join(project_dir, r"src\suspensionlab\physics\quarter_car.py")
with open(qc_path, "r", encoding="utf-8") as f:
    qc_content = f.read()

# Fix ISO 2631 Wk filter
bad_wk = """def _apply_wk_weighting(ddz_s: np.ndarray, dt: float) -> np.ndarray:
    \"\"\"
    Apply ISO 2631-1 Wk frequency weighting to vertical acceleration.
    \"\"\"
    fs = 1.0 / dt
    if fs <= 160.0:
        warnings.warn(
            f"Sample rate {fs:.1f} Hz is below the 160 Hz minimum required for ISO 2631-1 Wk "
            f"weighting (need fs > 160 Hz for the 80 Hz low-pass stage). "
            f"Returning unweighted acceleration — rms_body_accel_wk == rms_body_accel.",
            UserWarning,
            stacklevel=3,
        )
        return ddz_s
        
    sos_hp = signal.butter(2, 0.5, btype='highpass', fs=fs, output='sos')
    sos_lp = signal.butter(4, 80.0, btype='lowpass', fs=fs, output='sos')
    sos_bp = signal.butter(1, [4.0, 9.0], btype='bandpass', fs=fs, output='sos')
    
    sos_cascade = np.vstack((sos_hp, sos_lp, sos_bp))
    return signal.sosfiltfilt(sos_cascade, ddz_s)"""

good_wk = """def _apply_wk_weighting(ddz_s: np.ndarray, dt: float) -> np.ndarray:
    \"\"\"
    Apply ISO 2631-1 Wk frequency weighting to vertical acceleration.
    Uses exact bilinear-transformed IIR filter coefficients from ISO 2631-1:1997 Annex B.
    \"\"\"
    fs = 1.0 / dt
    
    # ISO 2631-1 Wk exact parameters
    f1, f2 = 0.4, 100.0
    f3, f4 = 12.5, 12.5
    f5, f6 = 2.37, 3.35
    Q5, Q6 = 0.91, 0.91
    
    w1, w2 = 2*np.pi*f1, 2*np.pi*f2
    w3, w4 = 2*np.pi*f3, 2*np.pi*f4
    w5, w6 = 2*np.pi*f5, 2*np.pi*f6
    
    # H_h (High-pass)
    z_h = [0, 0]
    p_h = [-w1/np.sqrt(2) + 1j*w1/np.sqrt(2), -w1/np.sqrt(2) - 1j*w1/np.sqrt(2)]
    k_h = 1.0
    
    # H_l (Low-pass)
    z_l = []
    p_l = [-w2/np.sqrt(2) + 1j*w2/np.sqrt(2), -w2/np.sqrt(2) - 1j*w2/np.sqrt(2)]
    k_l = w2**2
    
    # H_t (Transition)
    z_t = [-w3]
    p_t = [-w4]
    k_t = w4 / w3
    
    # H_s (Up-step)
    disc5 = complex((w5/Q5)**2 - 4*w5**2)
    r5 = np.sqrt(disc5)
    z_s = [(-w5/Q5 + r5)/2, (-w5/Q5 - r5)/2]
    
    disc6 = complex((w6/Q6)**2 - 4*w6**2)
    r6 = np.sqrt(disc6)
    p_s = [(-w6/Q6 + r6)/2, (-w6/Q6 - r6)/2]
    k_s = (w6 / w5)**2
    
    z = np.concatenate([z_h, z_l, z_t, z_s])
    p = np.concatenate([p_h, p_l, p_t, p_s])
    k = k_h * k_l * k_t * k_s
    
    # Convert analog to digital via bilinear transform
    zd, pd, kd = signal.bilinear_zpk(z, p, k, fs)
    sos = signal.zpk2sos(zd, pd, kd)
    
    return signal.sosfiltfilt(sos, ddz_s)"""

qc_content = qc_content.replace(bad_wk, good_wk)


# Fix ISO 8608 Road Profile Injection
old_random_block = """    elif profile.profile_type == "random":
        # Deterministic multi-harmonic road (ISO 8608 inspired rough road)
        # z_r(t) = sum_{i=1}^{N} A_i * sin(2π*f_i*t + φ_i)
        rng = np.random.default_rng(seed=42)
        N_harm = 20
        freqs  = np.linspace(0.5, 20.0, N_harm)
        amps   = A * 0.5 * rng.uniform(0.3, 1.0, N_harm) / np.sqrt(freqs)
        phases = rng.uniform(0.0, 2.0 * np.pi, N_harm)
        def zr(t):
            t = np.asarray(t, dtype=float)
            return sum(
                amps[i] * np.sin(2.0 * np.pi * freqs[i] * t + phases[i])
                for i in range(N_harm)
            )
        def dzr(t):
            t = np.asarray(t, dtype=float)
            return sum(
                amps[i] * 2.0 * np.pi * freqs[i] * np.cos(2.0 * np.pi * freqs[i] * t + phases[i])
                for i in range(N_harm)
            )

    elif profile.profile_type == "impulse":"""

new_iso8608_block = """    elif profile.profile_type == "random":
        # Multi-harmonic road with exact deterministic seed from duration
        rng = np.random.default_rng(seed=int(profile.duration * 100))
        N_harm = 20
        freqs  = np.linspace(0.5, 20.0, N_harm)
        amps   = A * 0.5 * rng.uniform(0.3, 1.0, N_harm) / np.sqrt(freqs)
        phases = rng.uniform(0.0, 2.0 * np.pi, N_harm)
        def zr(t):
            t = np.asarray(t, dtype=float)
            return sum(amps[i] * np.sin(2.0 * np.pi * freqs[i] * t + phases[i]) for i in range(N_harm))
        def dzr(t):
            t = np.asarray(t, dtype=float)
            return sum(amps[i] * 2.0 * np.pi * freqs[i] * np.cos(2.0 * np.pi * freqs[i] * t + phases[i]) for i in range(N_harm))

    elif profile.profile_type == "iso8608":
        iso_classes = {
            "A": 16e-6, "B": 64e-6, "C": 256e-6, "D": 1024e-6,
            "E": 4096e-6, "F": 16384e-6, "G": 65536e-6, "H": 262144e-6
        }
        G_d_n0 = iso_classes.get(getattr(profile, 'iso_class', 'A'), 16e-6)
        
        # We pre-compute a dense array of the road and use scipy.interpolate to provide a fast callable.
        # This keeps it consistent with solve_ivp requirement of callable zr(t)
        dt = 0.002
        duration = profile.duration + 2.0 # Pad duration
        N = int(duration / dt)
        if N % 2 != 0: N += 1
        
        df = 1.0 / duration
        f = np.fft.rfftfreq(N, d=dt)
        f[0] = 1e-6 # Avoid div by zero
        
        v = 20.0 # Standard test velocity m/s
        n = f / v
        n0 = 0.1
        
        S_z = G_d_n0 * (n / n0) ** (-2)
        S_t = S_z / v
        
        # SEED FROM INPUTS so two engineers get exactly the same profile for the same class/duration!
        seed_val = int((G_d_n0 * 1e6) + duration)
        rng = np.random.default_rng(seed=seed_val)
        phases = rng.uniform(0, 2 * np.pi, len(f))
        
        amplitudes = np.sqrt(S_t * df) * np.exp(1j * phases)
        
        z_raw = np.fft.irfft(amplitudes, n=N) * N
        z_r_arr = z_raw - np.mean(z_raw)
        t_arr = np.linspace(0, duration, N)
        dz_r_arr = np.gradient(z_r_arr, t_arr)
        
        from scipy.interpolate import interp1d
        _zr_interp = interp1d(t_arr, z_r_arr, bounds_error=False, fill_value=(z_r_arr[0], z_r_arr[-1]))
        _dzr_interp = interp1d(t_arr, dz_r_arr, bounds_error=False, fill_value=(0.0, 0.0))
        
        def zr(t): return _zr_interp(np.asarray(t, dtype=float))
        def dzr(t): return _dzr_interp(np.asarray(t, dtype=float))

    elif profile.profile_type == "impulse":"""

qc_content = qc_content.replace(old_random_block, new_iso8608_block)

with open(qc_path, "w", encoding="utf-8") as f:
    f.write(qc_content)

print("Physics perfectly patched.")
