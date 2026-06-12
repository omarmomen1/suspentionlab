from pydantic import BaseModel, Field, model_validator
from typing import Literal, List, Optional, Any, Dict
from enum import Enum

class PlanTier(str, Enum):
    FREE = "FREE"
    PRO = "PRO"
    ENTERPRISE = "ENTERPRISE"
    PAST_DUE = "PAST_DUE"


class QuarterCarParamsSchema(BaseModel):
    m_s:  float = Field(default=300.0,    gt=10.0,    le=5000.0,  description="Sprung mass [kg]")
    m_u:  float = Field(default=35.0,     gt=1.0,     le=500.0,   description="Unsprung mass [kg]")
    k_s:  float = Field(default=25000.0,  gt=100.0,   le=500000.0, description="Spring rate [N/m]")
    c:    float = Field(default=2050.0,   ge=0.0,     le=50000.0, description="Damping [Ns/m]")
    k_t:  float = Field(default=200000.0, gt=10000.0, le=1000000.0, description="Tire stiffness [N/m]")
    MR:   float = Field(default=0.85,     gt=0.1,     le=1.5,     description="Motion ratio [-]")
    c_t:  float = Field(default=0.0,      ge=0.0,     le=5000.0,  description="Tire damping [Ns/m]")
    damper_curve_v: Optional[List[float]] = Field(default=None, max_length=1000, description="Damper velocity points [m/s] — max 1000 entries")
    damper_curve_f: Optional[List[float]] = Field(default=None, max_length=1000, description="Damper force points [N] — max 1000 entries")

    @model_validator(mode="after")
    def validate_params(self) -> "QuarterCarParamsSchema":
        if self.m_u >= self.m_s:
            raise ValueError(
                f"Unsprung mass ({self.m_u} kg) must be less than sprung mass ({self.m_s} kg)."
            )
        # Validate damper LUT consistency
        if (self.damper_curve_v is None) != (self.damper_curve_f is None):
            raise ValueError("damper_curve_v and damper_curve_f must both be provided or both be None.")
        if self.damper_curve_v is not None and len(self.damper_curve_v) != len(self.damper_curve_f):
            raise ValueError("damper_curve_v and damper_curve_f must have the same length.")
        return self


class RoadProfileSchema(BaseModel):
    profile_type: Literal["step", "sine", "pothole", "random", "impulse", "iso8608"] = "step"
    iso_class: Literal["A", "B", "C", "D", "E", "F", "G", "H"] = "A"
    amplitude: float = 0.05
    frequency: float = Field(2.0, le=1000.0)
    duration: float = Field(5.0, le=60.0)
    speed_mps: float = Field(20.0, ge=1.0, le=200.0, description="Vehicle speed for ISO 8608 temporal PSD scaling [m/s]")


# ─── HalfCarParamsSchema MUST be defined before HalfCarSimulateRequest ───────
class HalfCarParamsSchema(BaseModel):
    m_s: float = Field(default=1200.0, gt=50.0, le=50000.0)
    I_y: float = Field(default=1800.0, gt=10.0, le=200000.0)
    m_uf: float = Field(default=40.0, gt=1.0, le=1000.0)
    m_ur: float = Field(default=40.0, gt=1.0, le=1000.0)
    k_sf: float = Field(default=30_000.0, gt=100.0, le=2000000.0)
    k_sr: float = Field(default=35_000.0, gt=100.0, le=2000000.0)
    c_f: float = Field(default=2_500.0, ge=0.0, le=200000.0)
    c_r: float = Field(default=3_000.0, ge=0.0, le=200000.0)
    k_tf: float = Field(default=250_000.0, gt=1000.0, le=10000000.0)
    k_tr: float = Field(default=250_000.0, gt=1000.0, le=10000000.0)
    L: float = Field(default=2.6, gt=0.5, le=20.0)
    a: float = Field(default=1.2, gt=0.1, le=10.0)
    b: float = Field(default=1.4, gt=0.1, le=10.0)
    speed_mps: float = Field(default=20.0, ge=0.0, le=150.0)
    c_tf: float = Field(default=0.0, ge=0.0, le=50000.0)
    c_tr: float = Field(default=0.0, ge=0.0, le=50000.0)
    damper_curve_v_f: Optional[List[float]] = None
    damper_curve_f_f: Optional[List[float]] = None
    damper_curve_v_r: Optional[List[float]] = None
    damper_curve_f_r: Optional[List[float]] = None

    @model_validator(mode="after")
    def mass_ratio_check(self) -> "HalfCarParamsSchema":
        if (self.m_uf + self.m_ur) >= self.m_s:
            raise ValueError(
                f"Total unsprung mass ({self.m_uf + self.m_ur} kg) must be less than sprung mass ({self.m_s} kg)."
            )
        return self


class SimulateRequest(BaseModel):
    params: QuarterCarParamsSchema
    profile: RoadProfileSchema


class HalfCarSimulateRequest(BaseModel):
    params: HalfCarParamsSchema
    profile: RoadProfileSchema


class QuarterCarResultSchema(BaseModel):
    # Modal
    omega_n_s: float
    omega_n_u: float
    f_n_s: float
    f_n_u: float
    zeta_s: float
    zeta_u: float
    c_crit_s: float
    c_crit_u: float
    k_w: float

    # Frequency domain
    freq_hz: List[float]
    transmissibility_body: List[float]
    transmissibility_wheel: List[float]
    bode_magnitude_db: List[float]
    bode_phase_deg: List[float]
    peak_transmissibility: float
    freq_at_peak_tx: float

    # Time domain
    time: List[float]
    z_s: List[float]
    z_u: List[float]
    z_r: List[float]
    dz_s: List[float]
    dz_u: List[float]
    ddz_s: List[float]
    susp_travel: List[float]
    tire_defl: List[float]
    tire_load_var: List[float]

    # Metrics
    rms_body_accel: float
    rms_body_accel_wk: float = 0.0  # ISO 2631-1 Wk frequency-weighted RMS [m/s²]
    rms_susp_travel: float
    rms_tire_load: float
    peak_susp_travel: float
    comfort_rating: str = ""

    # Integrity
    params_hash: str = ""  # SHA-256 of input params — used to verify result-param binding

    # PSD
    psd_freqs: List[float] = []
    psd_values: List[float] = []

    # Optional dictionary for additional arbitrary metrics
    metrics: Dict[str, Any] = {}


class OptimizeRequest(BaseModel):
    params: QuarterCarParamsSchema
    profile: RoadProfileSchema
    objective_type: str = "Balanced"
    max_travel: float = 0.05


class OptimizationResponse(BaseModel):
    optimal_ks: float
    optimal_c: float
    success: bool


class QuarterCarKPIs(BaseModel):
    """Lightweight subset of QuarterCarResult used purely for analytics."""
    f_n_s: float
    f_n_u: float
    zeta_s: float
    rms_body_accel: float
    peak_susp_travel: float
    peak_transmissibility: float
    freq_at_peak_tx: float
    metrics: Dict[str, Any] = {}


class RaceEngineerRequest(BaseModel):
    kpis: QuarterCarKPIs


class RecommendationSchema(BaseModel):
    category: str
    diagnosis: str
    finding: str
    action: str
    severity: str
    confidence: float


class RaceEngineerResponse(BaseModel):
    critical_flags: bool
    recommendations: List[RecommendationSchema]


class VerdictRequest(BaseModel):
    kpis: QuarterCarKPIs
    optimizer_output: OptimizationResponse
    params: Optional[QuarterCarParamsSchema] = None


class VerdictResponse(BaseModel):
    status: str
    headline: str
    message: str
    action: str
    score: int
    score_label: str


class HalfCarResultSchema(BaseModel):
    f_n_heave: float
    f_n_pitch: float
    f_n_uf: float
    f_n_ur: float

    time: List[float]
    z_s: List[float]
    theta: List[float]
    z_uf: List[float]
    z_ur: List[float]
    z_rf: List[float]
    z_rr: List[float]
    dz_s: List[float]
    dtheta: List[float]
    ddz_s: List[float]
    ddtheta: List[float]
    susp_travel_f: List[float]
    susp_travel_r: List[float]
    tire_load_f: List[float]
    tire_load_r: List[float]

    rms_heave_accel: float
    rms_pitch_accel: float
    rms_susp_travel_f: float
    rms_susp_travel_r: float
    rms_tire_load_f: float
    rms_tire_load_r: float


class FullCarParamsSchema(BaseModel):
    m_s: float = Field(default=1200.0, gt=50.0, le=50000.0)
    I_x: float = Field(default=400.0, gt=10.0, le=100000.0)
    I_y: float = Field(default=1800.0, gt=10.0, le=200000.0)
    m_uf: float = Field(default=40.0, gt=1.0, le=1000.0)
    m_ur: float = Field(default=40.0, gt=1.0, le=1000.0)
    k_sf: float = Field(default=30_000.0, gt=100.0, le=2000000.0)
    k_sr: float = Field(default=35_000.0, gt=100.0, le=2000000.0)
    c_f: float = Field(default=2_500.0, ge=0.0, le=200000.0)
    c_r: float = Field(default=3_000.0, ge=0.0, le=200000.0)
    k_arb_f: float = Field(default=20_000.0, ge=0.0, le=1000000.0)
    k_arb_r: float = Field(default=10_000.0, ge=0.0, le=1000000.0)
    k_tf: float = Field(default=250_000.0, gt=1000.0, le=10000000.0)
    k_tr: float = Field(default=250_000.0, gt=1000.0, le=10000000.0)
    L: float = Field(default=2.6, gt=0.5, le=20.0)
    a: float = Field(default=1.2, gt=0.1, le=10.0)
    b: float = Field(default=1.4, gt=0.1, le=10.0)
    tw_f: float = Field(default=1.6, gt=0.5, le=5.0)
    tw_r: float = Field(default=1.6, gt=0.5, le=5.0)
    speed_mps: float = Field(default=20.0, ge=0.0, le=150.0)
    c_tf: float = Field(default=0.0, ge=0.0, le=50000.0)
    c_tr: float = Field(default=0.0, ge=0.0, le=50000.0)
    road_asymmetry: float = Field(default=0.3, ge=0.0, le=1.0, description="Fraction of left-side amplitude applied to right side")
    damper_curve_v_f: Optional[List[float]] = None
    damper_curve_f_f: Optional[List[float]] = None
    damper_curve_v_r: Optional[List[float]] = None
    damper_curve_f_r: Optional[List[float]] = None

    @model_validator(mode="after")
    def mass_ratio_check(self) -> "FullCarParamsSchema":
        if (self.m_uf + self.m_ur) >= self.m_s:
            raise ValueError(
                f"Total unsprung mass ({self.m_uf + self.m_ur} kg) must be less than sprung mass ({self.m_s} kg)."
            )
        return self


class FullCarResultSchema(BaseModel):
    f_n_heave: float
    f_n_pitch: float
    f_n_roll: float
    f_n_uf: float
    f_n_ur: float

    time: List[float]

    # Body States
    z_s: List[float]
    theta: List[float]
    phi: List[float]

    # Unsprung States (FL, FR, RL, RR)
    z_ufl: List[float]
    z_ufr: List[float]
    z_url: List[float]
    z_urr: List[float]

    # Road Inputs
    z_rfl: List[float]
    z_rfr: List[float]
    z_rrl: List[float]
    z_rrr: List[float]

    # Body Velocities/Accelerations
    dz_s: List[float]
    dtheta: List[float]
    dphi: List[float]
    ddz_s: List[float]
    ddtheta: List[float]
    ddphi: List[float]

    # Metrics
    rms_heave_accel: float
    rms_pitch_accel: float
    rms_roll_accel: float

    # Advanced KPIs
    lateral_load_transfer_f: List[float]
    lateral_load_transfer_r: List[float]
    roll_stiffness_dist: float
    rms_tire_load_fl: float
    rms_tire_load_fr: float
    rms_tire_load_rl: float
    rms_tire_load_rr: float

    # PSD
    psd_freqs: List[float] = []
    psd_values: List[float] = []


class FullCarSimulateRequest(BaseModel):
    params: FullCarParamsSchema
    profile: RoadProfileSchema


class TireCoeffsSchema(BaseModel):
    pCy1: float = 1.30
    pDy1: float = 1.05
    pEy1: float = -0.50
    pKy1: float = 15.0
    pKy2: float = 2.0
    pCx1: float = 1.60
    pDx1: float = 1.10
    pEx1: float = 0.30
    pKx1: float = 22.0
    pKx2: float = 0.4
    rBx1: float = 10.0
    rBy1: float = 10.0
    rCx1: float = 1.0
    rCy1: float = 1.0

class HandlingParamsSchema(BaseModel):
    m: float = Field(default=1200.0, gt=50.0, le=50000.0, description="Vehicle mass [kg]")
    I_z: float = Field(default=2000.0, gt=100.0, le=100000.0, description="Yaw moment of inertia [kg·m²]")
    h_cg: float = Field(default=0.4, gt=0.05, le=5.0, description="CG height [m]")
    roll_dist: float = Field(default=0.55, ge=0.0, le=1.0, description="Front roll stiffness fraction")
    tire_coeffs: Optional[TireCoeffsSchema] = None

class TelemetryDataSchema(BaseModel):
    time: List[float]
    speed: List[float]
    lat_g: List[float]
    long_g: List[float]
    yaw_rate: List[float]


class HandlingRequest(BaseModel):
    params: HandlingParamsSchema
    maneuver_type: str = "Step Steer (J-Turn)"
    v_init_kph: float = 100.0


class HandlingResultSchema(BaseModel):
    time: List[float]
    v_x: List[float]
    v_y: List[float]
    yaw_rate: List[float]
    X: List[float]
    Y: List[float]
    Psi: List[float]
    a_x: List[float]
    a_y: List[float]
    slip_angle: List[float]


class ActiveParamsSchema(BaseModel):
    m_s: float = Field(default=300.0, gt=10.0, le=5000.0)
    m_u: float = Field(default=35.0, gt=1.0, le=500.0)
    k_s: float = Field(default=25000.0, gt=100.0, le=500000.0)
    k_t: float = Field(default=200000.0, gt=10000.0, le=1000000.0)
    MR: float = Field(default=0.85, gt=0.1, le=1.5)
    c_sky: float = Field(default=4000.0, ge=0.0, le=50000.0)
    c_min: float = Field(default=500.0, ge=0.0, le=50000.0)

    @model_validator(mode="after")
    def mass_ratio_check(self) -> "ActiveParamsSchema":
        if self.m_u >= self.m_s:
            raise ValueError(
                f"Unsprung mass ({self.m_u} kg) must be less than sprung mass ({self.m_s} kg)."
            )
        return self


class ActiveRequest(BaseModel):
    params: ActiveParamsSchema
    bump_height: float = 0.05


class ActiveResultSchema(BaseModel):
    time: List[float]
    active_ddz_s: List[float]
    active_susp_travel: List[float]
    active_rms_accel: float
    passive_ddz_s: List[float]
    passive_susp_travel: List[float]
    passive_rms_accel: float


class SweepRequest(BaseModel):
    var_x: Literal["Spring Rate (ks)", "Damping (c)", "Tire Stiffness (kt)"]
    var_y: Literal["Spring Rate (ks)", "Damping (c)", "Tire Stiffness (kt)"]
    objective: str
    grid_res: int = Field(default=20, ge=2, le=100)


class SweepResultSchema(BaseModel):
    X: List[List[float]]
    Y: List[List[float]]
    Z: List[List[float]]
    min_x: float
    min_y: float
    min_z: float

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

class JobResponse(BaseModel):
    job_id: str
    status: str
