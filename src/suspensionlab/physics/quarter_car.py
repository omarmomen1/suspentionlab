"""
physics/quarter_car.py
======================
SuspensionLab PRO — Quarter Car Physics Module
2-DOF Linear Quarter Car Model

Model description
-----------------
Sprung mass  m_s : body / chassis
Unsprung mass m_u : wheel assembly, hub, brake, partial suspension

Equations of motion (physical coordinates):
  m_s * z_s'' + c*(z_s' - z_u') + k_w*(z_s - z_u) = 0
  m_u * z_u'' + c*(z_u' - z_s') + k_w*(z_u - z_s) + k_t*(z_u - z_r) = 0

where k_w = k_s * MR² is the wheel rate (spring rate referred to wheel centre).

State-space formulation
-----------------------
State vector  x = [z_s, dz_s, z_u, dz_u]^T
Input         u = z_r  (road displacement)

A = [  0          1          0          0      ]
    [ -k_w/m_s  -c/m_s     k_w/m_s    c/m_s  ]
    [  0          0          0          1      ]
    [  k_w/m_u   c/m_u  -(k_w+k_t)/m_u  -c/m_u]

B = [0, 0, 0, k_t/m_u]^T   (tire spring force on unsprung mass)

For tire damping c_t (optional):
  Add c_t*z_r' contribution to unsprung EOM → B gains c_t term,
  but requires road velocity input.

Engineering assumptions
-----------------------
1. Linear spring and damper throughout.
2. Wheel rate k_w = k_s * MR².  MR = motion ratio (typically 0.7–1.0).
3. Tire modelled as spring + optional damper (c_t usually small, set 0 by default).
4. Road displacement z_r enters only through tire; no direct body excitation.
5. Static equilibrium at z=0; displacements are dynamic perturbations.
6. Gravity acts symmetrically — not included in dynamic equations.
7. Frequency domain: impedance matrix approach (exact analytical solution).
8. Time domain: scipy solve_ivp with BDF (implicit, stiff-suitable), tight tolerances.
9. ISO 2631-1 comfort: Wk frequency weighting applied to sprung acceleration.

References
----------
- Rao, S.S. "Mechanical Vibrations", 6th Ed., Pearson.
- Dixon, J.C. "The Shock Absorber Handbook", Wiley-SAE.
- ISO 2631-1:1997 Mechanical vibration and shock.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from typing import Literal
from enum import Enum

import numpy as np
from scipy.integrate import solve_ivp

class SolverMode(str, Enum):
    FAST = "FAST"
    BALANCED = "BALANCED"
    PRODUCTION = "PRODUCTION"
from scipy.linalg import eigvals
from scipy import signal


# ─────────────────────────────────────────────────────────────────────────────
# Data Contracts
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class QuarterCarParams:
    """All physical parameters for the 2-DOF quarter car model.

    Default parameters are chosen to produce a zeta_s ≈ 0.44 (optimal range) 
    with the default spring/mass configuration.

    Attributes
    ----------
    m_s : float  Sprung mass [kg]
    m_u : float  Unsprung mass [kg]
    k_s : float  Spring rate (coil spring, at spring seat) [N/m]
    c   : float  Damping coefficient (at damper body) [Ns/m]
    k_t : float  Tire vertical stiffness [N/m]
    MR  : float  Motion ratio = wheel travel / spring travel [-]
                 Wheel rate k_w = k_s * MR²
    c_t : float  Tire damping coefficient [Ns/m] (default 0)
    """
    m_s: float = 300.0    # kg
    m_u: float = 35.0     # kg
    k_s: float = 25_000.0 # N/m
    c:   float = 2_050.0  # Ns/m
    k_t: float = 200_000.0# N/m
    MR:  float = 0.85     # -
    c_t: float = 0.0      # Ns/m (tire damping, usually negligible)
    # Advanced nonlinear springs
    k_s_nl: list[float] | None = None  # [k1, k2, k3] for F = k1*z + k2*z^2 + k3*z^3
    z_0: float = 0.0                   # Preload/Weight jacking offset [m]
    
    # Advanced progressive dampers (split comp/rebound)
    damper_curve_v: list[float] | None = None
    damper_curve_f: list[float] | None = None
    damper_curve_v_comp: list[float] | None = None
    damper_curve_f_comp: list[float] | None = None
    damper_curve_v_reb: list[float] | None = None
    damper_curve_f_reb: list[float] | None = None
    
    # Non-linear limits (exponential bump stops)
    bump_stop_jounce: float = 0.1     # m (suspension travel limit in compression)
    bump_stop_rebound: float = -0.1   # m (suspension travel limit in extension)
    bump_stop_rate: float = 0.0       # N/m (stiffness of bump stops, 0 disables)
    bump_stop_exp: float = 50.0       # lambda coefficient for exponential engagement
    
    # Stribeck friction model
    coulomb_friction: float = 0.0     # N (legacy dry friction)
    stribeck_fs: float = 0.0          # N (Static friction peak)
    stribeck_fc: float = 0.0          # N (Kinetic Coulomb friction)
    stribeck_vs: float = 0.01         # m/s (Stribeck velocity)
    stribeck_sigma: float = 0.0       # Ns/m (Viscous friction term)

    def __post_init__(self) -> None:
        import math
        for name, val in self.__dict__.items():
            if val is None or isinstance(val, list) or name in ("bump_stop_rebound",):
                continue
            if isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
                raise ValueError(f"Parameter '{name}' cannot be NaN or infinite.")
            if name in ("m_s", "m_u"):
                if val < 0.1:
                    raise ValueError(
                        f"Parameter '{name}' must be a strictly positive value > 0.1 kg, got {val}. "
                        "Extremely low mass causes math convergence errors."
                    )
                if val > 1e6:
                    raise ValueError(f"Parameter '{name}' is excessively high, got {val}.")
            elif name in ("k_s", "k_t") and val > 1e8:
                raise ValueError(f"Parameter '{name}' is excessively high, got {val}.")
            elif val < 0:
                raise ValueError(f"Parameter '{name}' must be non-negative, got {val}")
        if self.MR <= 0 or self.MR > 1.5:
            raise ValueError(f"Motion ratio MR={self.MR} outside physical range (0, 1.5]")
        if self.stribeck_fs < self.stribeck_fc:
            raise ValueError("Stribeck static friction (fs) cannot be less than kinetic friction (fc).")
        if self.stribeck_vs <= 0.0:
            raise ValueError("Stribeck velocity (vs) must be strictly positive.")

    @property
    def k_w(self) -> float:
        """Wheel rate [N/m]: spring rate referred to wheel centre."""
        return self.k_s * (self.MR ** 2)

    @property
    def c_w(self) -> float:
        """Wheel damping rate [Ns/m]: damper rate referred to wheel centre."""
        return self.c * (self.MR ** 2)


@dataclass
class RoadProfile:
    """Road excitation profile definition.

    profile_type : 'step' | 'sine' | 'pothole' | 'random' | 'impulse'
    amplitude    : bump height or sine amplitude [m]
    frequency    : excitation frequency for sine input [Hz]
    duration     : total simulation time [s]
    """
    profile_type: Literal["step", "sine", "pothole", "random", "impulse", "iso8608"] = "step"
    iso_class:    Literal["A", "B", "C", "D", "E", "F", "G", "H"] = "A"
    amplitude:    float = 0.05   # m
    frequency:    float = 2.0    # Hz  (used for sine / random)
    duration:     float = 5.0    # s
    speed_mps:    float = 20.0   # m/s (used for ISO 8608 temporal PSD scaling)

    def __post_init__(self) -> None:
        valid_profiles = ("step", "sine", "pothole", "random", "impulse", "iso8608")
        if self.profile_type not in valid_profiles:
            self.profile_type = "step"


@dataclass
class QuarterCarResult:
    """Complete analysis results from the quarter car model.

    Modal properties
    ----------------
    omega_n_s   : sprung natural frequency [rad/s]
    omega_n_u   : unsprung natural frequency [rad/s]
    f_n_s       : sprung natural frequency [Hz]
    f_n_u       : unsprung natural frequency [Hz]
    zeta_s      : sprung damping ratio [-]
    zeta_u      : unsprung damping ratio [-]
    c_crit_s    : critical damping, sprung [Ns/m]
    c_crit_u    : critical damping, unsprung [Ns/m]
    k_w         : wheel rate [N/m]

    Frequency domain
    ----------------
    freq_hz         : frequency array [Hz]
    transmissibility_body  : |Z_s / Z_r| [-]
    transmissibility_wheel : |Z_u / Z_r| [-]
    bode_magnitude_db      : 20*log10(|H_s(jw)|) [dB]
    bode_phase_deg         : phase of H_s(jw) [deg]
    peak_transmissibility  : max(transmissibility_body) [-]
    freq_at_peak_tx        : frequency of peak transmissibility [Hz]

    Time domain
    -----------
    time          : time array [s]
    z_s           : sprung mass displacement [m]
    z_u           : unsprung mass displacement [m]
    z_r           : road displacement [m]
    dz_s          : sprung mass velocity [m/s]
    dz_u          : unsprung mass velocity [m/s]
    ddz_s         : sprung mass acceleration [m/s²]
    susp_travel   : suspension travel z_s - z_u [m]
    tire_defl     : tire deflection z_u - z_r [m]
    tire_load_var : dynamic tire load variation k_t*(z_u-z_r) [N]

    Comfort / performance metrics
    -----------------------------
    rms_body_accel      : RMS sprung body acceleration [m/s²] (ISO 2631)
    rms_susp_travel     : RMS suspension travel [m]
    rms_tire_load       : RMS tire load variation [N]
    peak_susp_travel    : peak-to-peak suspension travel [m]
    """
    # Modal
    omega_n_s:          float = 0.0
    omega_n_u:          float = 0.0
    f_n_s:              float = 0.0
    f_n_u:              float = 0.0
    zeta_s:             float = 0.0
    zeta_u:             float = 0.0
    c_crit_s:           float = 0.0
    c_crit_u:           float = 0.0
    k_w:                float = 0.0

    # Frequency domain
    freq_hz:                np.ndarray = field(default_factory=lambda: np.array([]))
    transmissibility_body:  np.ndarray = field(default_factory=lambda: np.array([]))
    transmissibility_wheel: np.ndarray = field(default_factory=lambda: np.array([]))
    bode_magnitude_db:      np.ndarray = field(default_factory=lambda: np.array([]))
    bode_phase_deg:         np.ndarray = field(default_factory=lambda: np.array([]))
    peak_transmissibility:  float = 0.0
    freq_at_peak_tx:        float = 0.0

    # Time domain
    time:           np.ndarray = field(default_factory=lambda: np.array([]))
    z_s:            np.ndarray = field(default_factory=lambda: np.array([]))
    z_u:            np.ndarray = field(default_factory=lambda: np.array([]))
    z_r:            np.ndarray = field(default_factory=lambda: np.array([]))
    dz_s:           np.ndarray = field(default_factory=lambda: np.array([]))
    dz_u:           np.ndarray = field(default_factory=lambda: np.array([]))
    ddz_s:          np.ndarray = field(default_factory=lambda: np.array([]))
    susp_travel:    np.ndarray = field(default_factory=lambda: np.array([]))
    tire_defl:      np.ndarray = field(default_factory=lambda: np.array([]))
    tire_load_var:  np.ndarray = field(default_factory=lambda: np.array([]))

    # Metrics
    rms_body_accel:    float = 0.0
    rms_body_accel_wk: float = 0.0  # ISO 2631-1 Wk frequency-weighted RMS acceleration [m/s²]
    rms_susp_travel:   float = 0.0
    rms_tire_load:     float = 0.0
    peak_susp_travel:  float = 0.0
    comfort_rating:    str   = ""

    # PSD Analysis
    psd_freqs:      np.ndarray = field(default_factory=lambda: np.array([]))
    psd_values:     np.ndarray = field(default_factory=lambda: np.array([]))


# ─────────────────────────────────────────────────────────────────────────────
# State-Space Matrix Builder
# ─────────────────────────────────────────────────────────────────────────────

def build_state_space(p: QuarterCarParams) -> tuple[np.ndarray, np.ndarray]:
    """
    Build the 4×4 system matrix A and input vector B for the quarter car.

    State: x = [z_s, dz_s, z_u, dz_u]

    Returns
    -------
    A : (4,4) ndarray  System matrix
    B : (4,)  ndarray  Input vector (road displacement z_r coefficient)
    """
    k_w = p.k_w
    A = np.array([
        [0.0,          1.0,          0.0,          0.0    ],
        [-k_w/p.m_s,  -p.c_w/p.m_s,   k_w/p.m_s,   p.c_w/p.m_s ],
        [0.0,          0.0,          0.0,          1.0    ],
        [k_w/p.m_u,   p.c_w/p.m_u,  -(k_w+p.k_t)/p.m_u, -(p.c_w + p.c_t)/p.m_u],
    ])
    # Road excitation enters via tire spring (and optional tire damping)
    # ddz_u += (k_t * z_r + c_t * dz_r) / m_u
    # For z_r input: B_disp = k_t/m_u.  Velocity term handled in ODE.
    B = np.array([0.0, 0.0, 0.0, p.k_t / p.m_u])
    return A, B


# ─────────────────────────────────────────────────────────────────────────────
# Modal Analysis — Natural Frequencies & Damping Ratios
# ─────────────────────────────────────────────────────────────────────────────

def compute_modal_properties(p: QuarterCarParams) -> dict:
    """
    Extract natural frequencies and damping ratios from eigenvalues of A.

    For a 2-DOF damped system the eigenvalues come in conjugate pairs:
        λ = σ ± jω_d

    Natural frequency:  ω_n = |λ|
    Damping ratio:      ζ   = -σ / |λ|
    Damped frequency:   ω_d = ω_n * sqrt(1 - ζ²)

    The simpler undamped formulae (used for approximate design):
        ω_n,s = sqrt(k_w / m_s)        [sprung ride mode]
        ω_n,u = sqrt((k_w + k_t) / m_u) [unsprung wheel-hop mode]

    Both approaches are computed.  The eigenvalue method is reported in results.
    """
    A, _ = build_state_space(p)
    eigs = eigvals(A)

    # Separate into two conjugate pairs (sort by imaginary part magnitude)
    complex_eigs = sorted(
        [e for e in eigs if abs(e.imag) > 1e-6],
        key=lambda e: abs(e.imag)
    )

    results = {}

    if len(complex_eigs) >= 4:
        # Mode 1 — lower freq (sprung ride)
        lam1 = complex_eigs[0]
        wn1  = abs(lam1)
        z1   = -lam1.real / wn1

        # Mode 2 — higher freq (unsprung wheel-hop)
        lam2 = complex_eigs[2]
        wn2  = abs(lam2)
        z2   = -lam2.real / wn2
    else:
        # Fallback: undamped analytical solution
        wn1 = np.sqrt(p.k_w / p.m_s)
        wn1_denom = 2.0 * np.sqrt(p.k_w * p.m_s)
        z1  = p.c_w / wn1_denom if wn1_denom > 1e-9 else 0.0
        wn2 = np.sqrt((p.k_w + p.k_t) / p.m_u)
        wn2_denom = 2.0 * np.sqrt((p.k_w + p.k_t) * p.m_u)
        z2  = (p.c_w + p.c_t) / wn2_denom if wn2_denom > 1e-9 else 0.0

    # Critical damping coefficients
    c_crit_s = 2.0 * np.sqrt(p.k_w * p.m_s)
    c_crit_u = 2.0 * np.sqrt((p.k_w + p.k_t) * p.m_u)

    results.update({
        "omega_n_s":  float(wn1),
        "f_n_s":      float(wn1 / (2.0 * np.pi)),
        "zeta_s":     float(np.clip(z1, 0.0, 5.0)),
        "c_crit_s":   float(c_crit_s),
        "omega_n_u":  float(wn2),
        "f_n_u":      float(wn2 / (2.0 * np.pi)),
        "zeta_u":     float(np.clip(z2, 0.0, 5.0)),
        "c_crit_u":   float(c_crit_u),
        "k_w":        float(p.k_w),
    })
    return results


# ─────────────────────────────────────────────────────────────────────────────
# Frequency Domain Analysis — Impedance Matrix Method
# ─────────────────────────────────────────────────────────────────────────────

def _impedance_matrix_tf(
    omega: np.ndarray,
    m_s: float,
    m_u: float,
    k_w: float,
    c: float,
    k_t: float,
    c_t: float,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Compute complex transfer functions H_s = Z_s/Z_r and H_u = Z_u/Z_r
    at angular frequency omega using impedance matrix inversion.

    System in complex domain (Fourier):
        [Z11  Z12] [Z_s]   [ 0  ]
        [Z21  Z22] [Z_u] = [ F  ]

    where:
        Z11 = -m_s*ω² + j*c*ω + k_w
        Z12 = Z21 = -(k_w + j*c*ω)
        Z22 = -m_u*ω² + j*(c+c_t)*ω + (k_w + k_t)
        F   = (k_t + j*c_t*ω) * Z_r     [road force on unsprung]

    Cramer's rule:
        H_s = Z_s/Z_r = -Z12*(k_t + jcω) / det[Z]
        H_u = Z_u/Z_r =  Z11*(k_t + jcω) / det[Z]

    Returns (H_s, H_u) as complex numbers.
    """
    jw = 1j * omega
    jw2 = -(omega ** 2)

    Z11 = m_s * jw2 + c * jw + k_w
    Z12 = -(k_w + c * jw)
    Z22 = m_u * jw2 + (c + c_t) * jw + k_w + k_t
    F_coeff = k_t + c_t * jw   # coefficient of Z_r in forcing

    det_Z = Z11 * Z22 - Z12 * Z12  # Z12 = Z21

    if isinstance(det_Z, np.ndarray):
        # FIXED: Use complex 1e-30+0j to avoid zeroing the imaginary part, which
        # would corrupt the phase of the Bode plot at near-resonance frequencies.
        det_Z = np.where(np.abs(det_Z) < 1e-30, 1e-30 + 0j, det_Z)
    elif abs(det_Z) < 1e-30:
        return complex(0), complex(0)

    H_s = (-Z12 * F_coeff) / det_Z
    H_u = (Z11  * F_coeff) / det_Z
    return H_s, H_u


def compute_frequency_response(
    p: QuarterCarParams,
    f_min: float = 0.1,
    f_max: float = 50.0,
    n_points: int = 600,
) -> dict:
    """
    Compute transmissibility, Bode magnitude and phase over a log-spaced
    frequency range.

    Parameters
    ----------
    p        : QuarterCarParams
    f_min    : minimum frequency [Hz]
    f_max    : maximum frequency [Hz]
    n_points : number of frequency points

    Returns
    -------
    dict with keys:
        freq_hz, transmissibility_body, transmissibility_wheel,
        bode_magnitude_db, bode_phase_deg,
        peak_transmissibility, freq_at_peak_tx
    """
    freq_hz = np.logspace(np.log10(f_min), np.log10(f_max), n_points)
    omega   = 2.0 * np.pi * freq_hz

    H_s_arr, H_u_arr = _impedance_matrix_tf(
        omega, p.m_s, p.m_u, p.k_w, p.c_w, p.k_t, p.c_t
    )

    tx_body  = np.abs(H_s_arr)
    tx_wheel = np.abs(H_u_arr)
    bode_db  = 20.0 * np.log10(np.maximum(tx_body, 1e-12))
    bode_ph  = np.degrees(np.angle(H_s_arr))

    peak_idx = np.argmax(tx_body)
    return {
        "freq_hz":                freq_hz,
        "transmissibility_body":  tx_body,
        "transmissibility_wheel": tx_wheel,
        "bode_magnitude_db":      bode_db,
        "bode_phase_deg":         bode_ph,
        "peak_transmissibility":  float(tx_body[peak_idx]),
        "freq_at_peak_tx":        float(freq_hz[peak_idx]),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Road Profile Generator
# ─────────────────────────────────────────────────────────────────────────────

def _road_profile_fn(profile: RoadProfile):
    """
    Return a callable z_r(t) and its derivative dz_r(t) for the given profile.

    Profiles
    --------
    step     : Heaviside step of amplitude A at t=0.5s
    sine     : A*sin(2π*f*t)
    pothole  : negative half-sine depression between t=0.3–0.65s
    random   : sum of harmonics with decaying amplitude (deterministic)
    impulse  : narrow Gaussian approximation, centred at t=0.3s
    """
    A  = profile.amplitude
    f  = profile.frequency

    if profile.profile_type == "step":
        def zr(t):   return np.where(t >= 0.5, A, 0.0)
        def dzr(t):  return np.zeros_like(np.asarray(t, dtype=float))

    elif profile.profile_type == "sine":
        def zr(t):   return A * np.sin(2.0 * np.pi * f * t)
        def dzr(t):  return A * 2.0 * np.pi * f * np.cos(2.0 * np.pi * f * t)

    elif profile.profile_type == "pothole":
        def zr(t):
            t = np.asarray(t, dtype=float)
            inside = (t >= 0.30) & (t <= 0.65)
            out = np.zeros_like(t)
            out[inside] = -A * np.sin(np.pi * (t[inside] - 0.30) / 0.35)
            return out
        def dzr(t):
            t = np.asarray(t, dtype=float)
            inside = (t >= 0.30) & (t <= 0.65)
            out = np.zeros_like(t)
            out[inside] = -A * (np.pi / 0.35) * np.cos(np.pi * (t[inside] - 0.30) / 0.35)
            return out

    elif profile.profile_type == "random":
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
        
        # Use the profile's speed_mps so temporal PSD scales correctly with vehicle speed
        v = max(profile.speed_mps, 1.0)  # m/s — avoid division by zero
        
        dt = 0.002
        duration = profile.duration + 2.0  # Pad duration
        N = int(duration / dt)
        if N % 2 != 0: N += 1
        
        n0 = 0.1  # reference spatial frequency [cycle/m] per ISO 8608
        
        # Seed for reproducible but non-periodic road based on class + speed + duration
        # FIXED: Use hash-based seed to avoid seed collisions from integer truncation.
        # e.g., class A (G_d_n0=16e-6) at 20m/s for 5s and class A at 10m/s for 15s
        # would produce the same int(16.0 + 5.0 + 20.0) = 41 seed without the hash.
        seed_val = abs(hash((G_d_n0, duration, v))) % (2**31)
        rng = np.random.default_rng(seed=seed_val)
        
        # Temporal PSD of road velocity: S_v(f) = G_d_n0 * v * (2*pi*n0)^2
        # This ensures correct amplitude scaling at any speed
        S_v = G_d_n0 * v * (2.0 * np.pi * n0) ** 2
        
        # FIXED: White noise variance for discrete white noise with PSD S_v sampled at fs=1/dt:
        # sigma^2 = S_v * fs = S_v / dt
        # Previous formula used S_v * fs/2 (Nyquist), underestimating amplitude by sqrt(2).
        sigma_v = np.sqrt(S_v / dt)
        v_noise = rng.normal(0.0, sigma_v, N)
        
        # Leaky integrator to prevent infinite DC drift
        # H(z) = dt / (1 - alpha*z^-1), alpha = 1 - wc*dt
        # Correct gain at DC = dt/(1-alpha) = dt/(wc*dt) = 1/wc — we want unit gain at passband
        # so we normalize the filter output by wc = 2*pi*f_c
        f_c = 0.1   # Hz cutoff
        w_c = 2.0 * np.pi * f_c
        alpha = 1.0 - w_c * dt
        
        from scipy import signal as sp_signal
        b_filt = [dt]
        a_filt = [1.0, -alpha]
        z_r_raw = sp_signal.lfilter(b_filt, a_filt, v_noise)
        # Filter is 1/(s + wc) which acts as an integrator 1/s for f >> f_c. 
        # Output must be multiplied by w_c to restore unit gain in passband.
        z_r_arr = z_r_raw * w_c
        
        t_arr = np.linspace(0, duration, N)
        dz_r_arr = np.gradient(z_r_arr, dt)
        
        from scipy.interpolate import interp1d
        _zr_interp  = interp1d(t_arr, z_r_arr,  bounds_error=False, fill_value=(z_r_arr[0],  z_r_arr[-1]))
        _dzr_interp = interp1d(t_arr, dz_r_arr, bounds_error=False, fill_value=(0.0, 0.0))
        
        def zr(t):  return _zr_interp(np.asarray(t, dtype=float))
        def dzr(t): return _dzr_interp(np.asarray(t, dtype=float))

    elif profile.profile_type == "impulse":
        # Narrow Gaussian impulse: A * exp(-(t-0.3)^2 / (2*σ²)), σ = 0.02s
        sigma = 0.02
        t0    = 0.30
        def zr(t):
            t = np.asarray(t, dtype=float)
            return A * np.exp(-0.5 * ((t - t0) / sigma) ** 2)
        def dzr(t):
            t = np.asarray(t, dtype=float)
            return A * (-(t - t0) / sigma**2) * np.exp(-0.5 * ((t - t0) / sigma) ** 2)

    else:
        raise ValueError(f"Unknown profile type: {profile.profile_type}")

    return zr, dzr


# ─────────────────────────────────────────────────────────────────────────────
# ODE Right-Hand Side (for solve_ivp)
# ─────────────────────────────────────────────────────────────────────────────

def _quarter_car_ode(t, x, p: QuarterCarParams, zr_fn, dzr_fn):
    """
    Right-hand side of the quarter car state equations for solve_ivp.

    x = [z_s, dz_s, z_u, dz_u]

    Returns dx/dt = [dz_s, ddz_s, dz_u, ddz_u]
    """
    z_s, dz_s, z_u, dz_u = x
    z_r  = float(zr_fn(np.array([t]))[0])
    dz_r = float(dzr_fn(np.array([t]))[0])

    v_susp = dz_s - dz_u
    z_susp = z_s - z_u
    
    z_susp_adj = z_susp - p.z_0
    v_damper = v_susp * p.MR
    
    # Progressive Dampers (Split curves)
    if v_damper > 0 and p.damper_curve_v_comp is not None and p.damper_curve_f_comp is not None:
        F_damper = np.interp(v_damper, p.damper_curve_v_comp, p.damper_curve_f_comp)
        F_damper_w = F_damper * p.MR
    elif v_damper < 0 and p.damper_curve_v_reb is not None and p.damper_curve_f_reb is not None:
        F_damper = np.interp(v_damper, p.damper_curve_v_reb, p.damper_curve_f_reb)
        F_damper_w = F_damper * p.MR
    elif p.damper_curve_v is not None and p.damper_curve_f is not None and len(p.damper_curve_v) > 1:
        F_damper = np.interp(v_damper, p.damper_curve_v, p.damper_curve_f)
        F_damper_w = F_damper * p.MR
    else:
        F_damper_w = p.c_w * v_susp
        
    # Stribeck Friction + Coulomb
    if p.stribeck_fs > 0 or p.stribeck_fc > 0:
        fric = (p.stribeck_fc + (p.stribeck_fs - p.stribeck_fc) * np.exp(-(v_susp / p.stribeck_vs)**2)) * np.tanh(v_susp / 0.01) + p.stribeck_sigma * v_susp
        F_damper_w += fric * p.MR
    elif p.coulomb_friction > 0:
        F_damper_w += p.coulomb_friction * np.tanh(v_susp / 0.01) * p.MR
        
    # Nonlinear Springs
    if p.k_s_nl is not None and len(p.k_s_nl) >= 3:
        z_spring = z_susp_adj * p.MR
        F_spring = p.k_s_nl[0] * z_spring + p.k_s_nl[1] * (z_spring**2) + p.k_s_nl[2] * (z_spring**3)
        F_spring_w = F_spring * p.MR
    else:
        F_spring_w = p.k_w * z_susp_adj
    
    # Exponential Bump Stops
    if p.bump_stop_rate > 0:
        if z_susp > p.bump_stop_jounce:
            dz = min(z_susp - p.bump_stop_jounce, 0.05)
            F_spring_w += p.bump_stop_rate * (np.exp(p.bump_stop_exp * dz) - 1.0) * p.MR**2
        elif z_susp < p.bump_stop_rebound:
            dz_reb = min(p.bump_stop_rebound - z_susp, 0.05)
            F_spring_w -= p.bump_stop_rate * (np.exp(p.bump_stop_exp * dz_reb) - 1.0) * p.MR**2

    # Sprung acceleration
    ddz_s = (1.0 / p.m_s) * (-F_damper_w - F_spring_w)

    # Unsprung acceleration
    ddz_u = (1.0 / p.m_u) * (
          F_damper_w
        + F_spring_w
        - p.k_t * (z_u - z_r)
        - p.c_t  * (dz_u - dz_r)
    )

    return [dz_s, ddz_s, dz_u, ddz_u]


# ─────────────────────────────────────────────────────────────────────────────
# Time Domain Simulation
# ─────────────────────────────────────────────────────────────────────────────

def simulate_time_response(
    p: QuarterCarParams,
    profile: RoadProfile,
    t_eval_dt: float = 0.001,
    solver_mode: SolverMode = SolverMode.BALANCED,
) -> dict:
    """
    Integrate the 2-DOF quarter car ODE using scipy solve_ivp.

    Parameters
    ----------
    p          : QuarterCarParams
    profile    : RoadProfile
    t_eval_dt  : time step for output [s] (default 2 ms → 500 Hz)
    solver_mode: SolverMode (FAST, BALANCED, PRODUCTION)

    Returns
    -------
    dict with time, z_s, z_u, z_r, dz_s, dz_u, ddz_s,
    susp_travel, tire_defl, tire_load_var
    """
    zr_fn, dzr_fn = _road_profile_fn(profile)

    t_span  = (0.0, profile.duration)
    t_eval  = np.arange(0.0, profile.duration, t_eval_dt)
    x0      = [0.0, 0.0, 0.0, 0.0]   # start at static equilibrium

    # Solver mappings based on performance benchmarks
    if solver_mode == SolverMode.FAST:
        method = "LSODA"
        rtol = 1e-3
        atol = 1e-6
    elif solver_mode == SolverMode.BALANCED:
        method = "LSODA"
        rtol = 1e-5
        atol = 1e-8
    else:  # PRODUCTION
        method = "BDF"
        rtol = 1e-7
        atol = 1e-10

    sol = solve_ivp(
        fun=_quarter_car_ode,
        t_span=t_span,
        y0=x0,
        method=method,
        t_eval=t_eval,
        args=(p, zr_fn, dzr_fn),
        rtol=rtol,
        atol=atol,
        max_step=max(0.001, profile.duration / 5000.0),
        dense_output=False,
    )

    if not sol.success:
        from suspensionlab.physics.exceptions import MathConvergenceError
        raise MathConvergenceError(
            f"ODE solver failed to converge: {sol.message}. "
            "Try reducing bump amplitude, increasing damping, or shortening duration."
        )

    t   = sol.t
    z_s  = sol.y[0]
    dz_s = sol.y[1]
    z_u  = sol.y[2]
    dz_u = sol.y[3]

    # Reconstruct road profile and derivatives on solution time grid
    z_r_arr  = zr_fn(t)
    dz_r_arr = dzr_fn(t)

    # Sprung body acceleration (from EOM, not numerical differentiation)
    v_susp = dz_s - dz_u
    z_susp = z_s - z_u
    
    z_susp_adj = z_susp - p.z_0
    v_damper = v_susp * p.MR
    
    # Progressive Dampers (Split curves)
    F_damper_w = np.zeros_like(v_susp)
    if p.damper_curve_v_comp is not None and p.damper_curve_f_comp is not None and p.damper_curve_v_reb is not None and p.damper_curve_f_reb is not None:
        F_damper_comp = np.interp(v_damper, p.damper_curve_v_comp, p.damper_curve_f_comp)
        F_damper_reb = np.interp(v_damper, p.damper_curve_v_reb, p.damper_curve_f_reb)
        F_damper = np.where(v_damper > 0, F_damper_comp, F_damper_reb)
        F_damper_w = F_damper * p.MR
    elif p.damper_curve_v is not None and p.damper_curve_f is not None and len(p.damper_curve_v) > 1:
        F_damper = np.interp(v_damper, p.damper_curve_v, p.damper_curve_f)
        F_damper_w = F_damper * p.MR
    else:
        F_damper_w = p.c_w * v_susp
        
    # Stribeck Friction + Coulomb
    if p.stribeck_fs > 0 or p.stribeck_fc > 0:
        fric = (p.stribeck_fc + (p.stribeck_fs - p.stribeck_fc) * np.exp(-(v_susp / p.stribeck_vs)**2)) * np.tanh(v_susp / 0.01) + p.stribeck_sigma * v_susp
        F_damper_w += fric * p.MR
    elif p.coulomb_friction > 0:
        F_damper_w += p.coulomb_friction * np.tanh(v_susp / 0.01) * p.MR
        
    # Nonlinear Springs
    if p.k_s_nl is not None and len(p.k_s_nl) >= 3:
        z_spring = z_susp_adj * p.MR
        F_spring = p.k_s_nl[0] * z_spring + p.k_s_nl[1] * (z_spring**2) + p.k_s_nl[2] * (z_spring**3)
        F_spring_w = F_spring * p.MR
    else:
        F_spring_w = p.k_w * z_susp_adj
    
    # Exponential Bump Stops
    if p.bump_stop_rate > 0:
        bump_jounce = np.where(z_susp > p.bump_stop_jounce, p.bump_stop_rate * (np.exp(p.bump_stop_exp * (z_susp - p.bump_stop_jounce)) - 1.0) * p.MR**2, 0.0)
        bump_rebound = np.where(z_susp < p.bump_stop_rebound, -p.bump_stop_rate * (np.exp(p.bump_stop_exp * (p.bump_stop_rebound - z_susp)) - 1.0) * p.MR**2, 0.0)
        F_spring_w += bump_jounce + bump_rebound
    
    ddz_s = (1.0 / p.m_s) * (-F_damper_w - F_spring_w)

    susp_travel   = z_s - z_u
    tire_defl     = z_u - z_r_arr
    tire_load_var = p.k_t * tire_defl + p.c_t * (dz_u - dz_r_arr)

    return {
        "time":          t,
        "z_s":           z_s,
        "z_u":           z_u,
        "z_r":           z_r_arr,
        "dz_s":          dz_s,
        "dz_u":          dz_u,
        "ddz_s":         ddz_s,
        "susp_travel":   susp_travel,
        "tire_defl":     tire_defl,
        "tire_load_var": tire_load_var,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Performance & Comfort Metrics
# ─────────────────────────────────────────────────────────────────────────────

def _apply_wk_weighting(ddz_s: np.ndarray, dt: float) -> np.ndarray:
    """
    Apply ISO 2631-1 Wk frequency weighting to vertical acceleration.
    Uses exact bilinear-transformed IIR filter coefficients from ISO 2631-1:1997 Annex B.
    """
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
    
    return signal.sosfiltfilt(sos, ddz_s)

def compute_metrics(time_data: dict, p: QuarterCarParams) -> dict:
    """
    Compute scalar engineering metrics from time-domain simulation results.

    ISO 2631-1 comfort boundaries (unweighted RMS body acceleration):
        < 0.315 m/s²  :  Not uncomfortable
        0.315–0.63    :  Slightly uncomfortable
        0.63–1.0      :  Fairly uncomfortable
        1.0–2.0       :  Uncomfortable
        > 2.0         :  Very uncomfortable

    Returns dict with rms_body_accel, rms_body_accel_wk, rms_susp_travel, rms_tire_load,
    peak_susp_travel, comfort_rating.
    """
    ddz_s        = time_data["ddz_s"]
    susp_travel  = time_data["susp_travel"]
    tire_lv      = time_data["tire_load_var"]

    rms_accel   = float(np.sqrt(np.mean(ddz_s ** 2)))
    
    dt = time_data["time"][1] - time_data["time"][0] if len(time_data["time"]) > 1 else 0.002
    rms_body_accel_wk = float(np.sqrt(np.mean(_apply_wk_weighting(ddz_s, dt)**2)))

    rms_susp    = float(np.sqrt(np.mean(susp_travel ** 2)))
    rms_tire    = float(np.sqrt(np.mean(tire_lv ** 2)))
    peak_travel = float(np.ptp(susp_travel))   # peak-to-peak

    # ISO 2631-1 comfort rating
    if rms_body_accel_wk < 0.315:
        comfort = "NOT UNCOMFORTABLE"
    elif rms_body_accel_wk < 0.630:
        comfort = "SLIGHTLY UNCOMFORTABLE"
    elif rms_body_accel_wk < 1.000:
        comfort = "FAIRLY UNCOMFORTABLE"
    elif rms_body_accel_wk < 2.000:
        comfort = "UNCOMFORTABLE"
    else:
        comfort = "VERY UNCOMFORTABLE"

    return {
        "rms_body_accel":   rms_accel,
        "rms_body_accel_wk": rms_body_accel_wk,
        "rms_susp_travel":  rms_susp,
        "rms_tire_load":    rms_tire,
        "peak_susp_travel": peak_travel,
        "comfort_rating":   comfort,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Main Analysis Entry Point
# ─────────────────────────────────────────────────────────────────────────────

def run_quarter_car_analysis(
    p: QuarterCarParams,
    profile: RoadProfile,
    f_min: float = 0.1,
    f_max: float = 50.0,
    n_freq: int = 600,
    solver_mode: SolverMode = SolverMode.BALANCED,
) -> QuarterCarResult:
    """
    Run the complete 2-DOF quarter car analysis pipeline.

    Steps
    -----
    1. Modal analysis  — eigenvalue extraction
    2. Frequency domain — transmissibility, Bode plots
    3. Time domain     — ODE integration
    4. Metrics         — RMS comfort, suspension travel, tire load

    Parameters
    ----------
    p       : QuarterCarParams   — vehicle parameters
    profile : RoadProfile        — road excitation definition
    f_min   : float              — frequency sweep minimum [Hz]
    f_max   : float              — frequency sweep maximum [Hz]
    n_freq  : int                — number of frequency points

    Returns
    -------
    QuarterCarResult  — populated dataclass with all results
    """
    # 1. Modal
    modal = compute_modal_properties(p)

    # 2. Frequency domain
    freq_data = compute_frequency_response(p, f_min=f_min, f_max=f_max, n_points=n_freq)

    # 3. Time domain
    t_eval_dt = 0.005 if solver_mode == SolverMode.FAST else 0.001

    time_data = None
    metrics = None
    try:
        time_data = simulate_time_response(p, profile, t_eval_dt=t_eval_dt, solver_mode=solver_mode)
        metrics = compute_metrics(time_data, p)
        
        # 5. PSD Analysis (Backend)
        from scipy.signal import welch
        dt = time_data["time"][1] - time_data["time"][0] if len(time_data["time"]) > 1 else 0.002
        fs = 1.0 / dt
        f_psd, p_psd = welch(time_data["ddz_s"], fs, nperseg=min(len(time_data["ddz_s"]), 1024))
        
        # 6. Downsample time domain data to ~2000 points maximum to prevent payload bloat
        N_total = len(time_data["time"])
        step = max(1, N_total // 2000)
    except Exception as e:
        import warnings
        warnings.warn(f"Time domain simulation failed: {str(e)}")
        # Provide fallback metrics
        metrics = {
            "rms_body_accel": 0.0,
            "rms_body_accel_wk": 0.0,
            "rms_susp_travel": 0.0,
            "rms_tire_load": 0.0,
            "peak_susp_travel": 0.0,
            "comfort_rating": "Failed",
        }
        f_psd, p_psd = [], []
        time_data = {
            "time": [0.0], "z_s": [0.0], "z_u": [0.0], "z_r": [0.0],
            "dz_s": [0.0], "dz_u": [0.0], "ddz_s": [0.0],
            "susp_travel": [0.0], "tire_defl": [0.0], "tire_load_var": [0.0]
        }
        step = 1

    result = QuarterCarResult(
        # Modal
        omega_n_s   = modal["omega_n_s"],
        omega_n_u   = modal["omega_n_u"],
        f_n_s       = modal["f_n_s"],
        f_n_u       = modal["f_n_u"],
        zeta_s      = modal["zeta_s"],
        zeta_u      = modal["zeta_u"],
        c_crit_s    = modal["c_crit_s"],
        c_crit_u    = modal["c_crit_u"],
        k_w         = modal["k_w"],
        # Frequency domain
        freq_hz                = freq_data["freq_hz"],
        transmissibility_body  = freq_data["transmissibility_body"],
        transmissibility_wheel = freq_data["transmissibility_wheel"],
        bode_magnitude_db      = freq_data["bode_magnitude_db"],
        bode_phase_deg         = freq_data["bode_phase_deg"],
        peak_transmissibility  = freq_data["peak_transmissibility"],
        freq_at_peak_tx        = freq_data["freq_at_peak_tx"],
        # Time domain (downsampled)
        time          = time_data["time"][::step],
        z_s           = time_data["z_s"][::step],
        z_u           = time_data["z_u"][::step],
        z_r           = time_data["z_r"][::step],
        dz_s          = time_data["dz_s"][::step],
        dz_u          = time_data["dz_u"][::step],
        ddz_s         = time_data["ddz_s"][::step],
        susp_travel   = time_data["susp_travel"][::step],
        tire_defl     = time_data["tire_defl"][::step],
        tire_load_var = time_data["tire_load_var"][::step],
        # Metrics
        rms_body_accel   = metrics["rms_body_accel"],
        rms_body_accel_wk= metrics["rms_body_accel_wk"],
        rms_susp_travel  = metrics["rms_susp_travel"],
        rms_tire_load    = metrics["rms_tire_load"],
        peak_susp_travel = metrics["peak_susp_travel"],
        comfort_rating   = metrics["comfort_rating"],
        # PSD
        psd_freqs        = f_psd,
        psd_values       = p_psd,
    )
    return result
