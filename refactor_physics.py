import os
import re

project_dir = r"C:\Users\omaar\Downloads\project"

# 1. Update models.py
models_path = os.path.join(project_dir, r"src\suspensionlab\shared\models.py")
with open(models_path, "r", encoding="utf-8") as f:
    models_content = f.read()

# Add PAST_DUE
if 'PAST_DUE = "PAST_DUE"' not in models_content:
    old_enum = """class PlanTier(str, Enum):
    FREE = "FREE"
    PRO = "PRO"
    ENTERPRISE = "ENTERPRISE\""""
    new_enum = """class PlanTier(str, Enum):
    FREE = "FREE"
    PRO = "PRO"
    ENTERPRISE = "ENTERPRISE"
    PAST_DUE = "PAST_DUE\""""
    models_content = models_content.replace(old_enum, new_enum)

# Update RoadProfileSchema
old_profile = """class RoadProfileSchema(BaseModel):
    profile_type: Literal["step", "sine", "pothole", "random", "impulse"] = "step"
    amplitude: float = 0.05
    frequency: float = Field(2.0, le=1000.0)
    duration: float = Field(5.0, le=60.0)"""
new_profile = """class RoadProfileSchema(BaseModel):
    profile_type: Literal["step", "sine", "pothole", "random", "impulse", "iso8608"] = "step"
    iso_class: Literal["A", "B", "C", "D", "E", "F", "G", "H"] = "A"
    amplitude: float = 0.05
    frequency: float = Field(2.0, le=1000.0)
    duration: float = Field(5.0, le=60.0)"""
models_content = models_content.replace(old_profile, new_profile)

# Add MonteCarloRequest schema
mc_schema = """
class MonteCarloRequest(BaseModel):
    params: QuarterCarParamsSchema
    profile: RoadProfileSchema
    iterations: int = Field(500, le=1000)
    tolerance_pct: float = Field(5.0, le=20.0)

class MonteCarloResultSchema(BaseModel):
    iterations: int
    tolerance_pct: float
    mean_rms_body_accel_wk: float
    std_rms_body_accel_wk: float
    p95_rms_body_accel_wk: float
    mean_rms_tire_load: float
    std_rms_tire_load: float
"""
if "class MonteCarloRequest" not in models_content:
    models_content += mc_schema

with open(models_path, "w", encoding="utf-8") as f:
    f.write(models_content)

# 2. Update quarter_car.py RoadProfile
qc_path = os.path.join(project_dir, r"src\suspensionlab\physics\quarter_car.py")
with open(qc_path, "r", encoding="utf-8") as f:
    qc_content = f.read()

old_rp = """    profile_type: Literal["step", "sine", "pothole", "random", "impulse"] = "step"
    amplitude:    float = 0.05   # m
    frequency:    float = 2.0    # Hz  (used for sine / random)
    duration:     float = 5.0    # s"""
new_rp = """    profile_type: Literal["step", "sine", "pothole", "random", "impulse", "iso8608"] = "step"
    iso_class:    Literal["A", "B", "C", "D", "E", "F", "G", "H"] = "A"
    amplitude:    float = 0.05   # m
    frequency:    float = 2.0    # Hz  (used for sine / random)
    duration:     float = 5.0    # s"""
qc_content = qc_content.replace(old_rp, new_rp)

# Add iso8608 generator logic inside _generate_road_profile
old_gen = """        elif profile.profile_type == "impulse":
            # 0.05s impulse
            idx = int(0.05 / dt)
            z_r[:idx] = profile.amplitude
            dz_r[0] = profile.amplitude / dt
            dz_r[idx] = -profile.amplitude / dt"""
new_gen = """        elif profile.profile_type == "impulse":
            # 0.05s impulse
            idx = int(0.05 / dt)
            z_r[:idx] = profile.amplitude
            dz_r[0] = profile.amplitude / dt
            dz_r[idx] = -profile.amplitude / dt
            
        elif profile.profile_type == "iso8608":
            iso_classes = {
                "A": 16e-6, "B": 64e-6, "C": 256e-6, "D": 1024e-6,
                "E": 4096e-6, "F": 16384e-6, "G": 65536e-6, "H": 262144e-6
            }
            G_d_n0 = iso_classes.get(profile.iso_class, 16e-6)
            
            df = 1.0 / profile.duration
            f = np.fft.rfftfreq(N, d=dt)
            f[0] = 1e-6 # Avoid div by zero
            
            v = 20.0 # Standard test velocity m/s
            n = f / v
            n0 = 0.1
            
            S_z = G_d_n0 * (n / n0) ** (-2)
            S_t = S_z / v
            
            np.random.seed(42) # Deterministic for consistent UI reloading
            phases = np.random.uniform(0, 2 * np.pi, len(f))
            amplitudes = np.sqrt(S_t * df) * np.exp(1j * phases)
            
            z_raw = np.fft.irfft(amplitudes, n=N) * N
            z_r = z_raw - np.mean(z_raw)
            dz_r = np.gradient(z_r, dt)"""
qc_content = qc_content.replace(old_gen, new_gen)

with open(qc_path, "w", encoding="utf-8") as f:
    f.write(qc_content)

print("Physics and models refactored.")
