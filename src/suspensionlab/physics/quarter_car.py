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

where k_w = k_s * MR² is the wheel rate. MR = motion ratio = spring travel / wheel travel (typically 0.7–1.0).

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
2. Wheel rate k_w = k_s * MR².  MR = motion ratio = spring travel / wheel travel (typically 0.7–1.0). A value < 1.0 means the spring compresses less than the wheel travels (e.g. pullrod/pushrod), which is typical.
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
from typing import Any, Dict, List, Literal, Optional, Tuple, Union
from enum import Enum

import numpy as np
from scipy.integrate import solve_ivp

class SolverMode(str, Enum):
    FAST = "FAST"
    BALANCED = "BALANCED"
    PRODUCTION = "PRODUCTION"
from scipy.linalg import eigvals
from scipy import signal

from suspensionlab.physics.contracts import (
    ContactState,
    PhysicsDiagnostics,
    PhysicsProvenance,
    CanonicalRoadProfile,
    compute_dataset_hash,
)


# ─────────────────────────────────────────────────────────────────────────────
# Data Contracts
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class QuarterCarParams:
    """All physical parameters for the 2-DOF quarter car model.

    Default parameters are chosen to produce a zeta_s ≈ 0.28 (optimal range) 
    with the default spring/mass configuration.

    Attributes
    ----------
    m_s : float  Sprung mass [kg]
    m_u : float  Unsprung mass [kg]
    k_s : float  Spring rate (coil spring, at spring seat) [N/m]
    c   : float  Damping coefficient (at damper body) [Ns/m]
    k_t : float  Tire vertical stiffness [N/m]
    MR  : float  Motion ratio = spring travel / wheel travel [-]. Wheel rate k_w = k_s * MR². A value of 0.85 means the spring compresses 85 mm for every 100 mm of wheel travel. Range (0, 1.5].
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
    bump_stop_gap: Optional[float] = None  # m (clearance before bump stop contact)
    
    # Stribeck friction model
    coulomb_friction: float = 0.0     # N (legacy dry friction)
    stribeck_fs: float = 0.0          # N (Static friction peak)
    stribeck_fc: float = 0.0          # N (Kinetic Coulomb friction)
    stribeck_vs: float = 0.01         # m/s (Stribeck velocity)
    stribeck_sigma: float = 0.0       # Ns/m (Viscous friction term)
    enable_contact_loss: bool = True  # Enable nonlinear tire liftoff clamping (Fz >= 0)
    enveloping_config: Optional[Any] = None  # Optional TireEnvelopingConfig for finite patch / carcass enveloping
    _skip_validation: bool = False    # Internal test bypass for degenerate verification cases

    def __post_init__(self) -> None:
        if self.bump_stop_gap is not None:
            gap = abs(float(self.bump_stop_gap))
            self.bump_stop_jounce = gap
            self.bump_stop_rebound = -gap
        if self._skip_validation:
            return
        import math
        for name, val in self.__dict__.items():
            if val is None or isinstance(val, (list, bool)) or name in ("bump_stop_rebound", "enveloping_config"):
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
            if name == "k_s":
                if val < 1000.0:
                    raise ValueError(
                        f"Spring rate 'k_s' must be at least 1,000 N/m (got {val}). "
                        "Zero or sub-critical suspension stiffness creates a singular stiffness matrix "
                        "and leads to infinite static deflection sag exceeding travel limits."
                    )
                if val > 1e8:
                    raise ValueError(f"Spring rate 'k_s' is excessively high, got {val}.")
            elif name == "k_t":
                if val < 10000.0:
                    raise ValueError(
                        f"Tire vertical stiffness 'k_t' must be at least 10,000 N/m (got {val}). "
                        "Zero or sub-critical tire stiffness causes physical carcass collapse to the wheel rim "
                        "and mathematically decouples the unsprung mass from road excitation."
                    )
                if val > 1e8:
                    raise ValueError(f"Tire vertical stiffness 'k_t' is excessively high, got {val}.")
            elif name == "c":
                if val < 0:
                    raise ValueError(
                        f"Damping coefficient 'c' must be non-negative (got {val}). "
                        "Negative damping creates non-conservative energy injection and mathematical divergence."
                    )
            elif val < 0:
                raise ValueError(f"Parameter '{name}' must be non-negative, got {val}")
        if self.MR <= 0 or self.MR > 1.5:
            raise ValueError(f"Motion ratio MR={self.MR} outside physical range (0, 1.5]. MR = spring travel / wheel travel. Typical range: 0.6–1.1.")
        if self.stribeck_fs < self.stribeck_fc:
            raise ValueError("Stribeck static friction (fs) cannot be less than kinetic friction (fc).")
        if self.stribeck_vs <= 0.0:
            raise ValueError("Stribeck velocity (vs) must be strictly positive.")

        # Damper dyno curve sanity: interpolation against a non-monotonic or
        # mismatched velocity axis produces oscillating, physically impossible
        # damper forces that look plausible on a plot. Reject them here.
        for v_name, f_name in (
            ("damper_curve_v", "damper_curve_f"),
            ("damper_curve_v_comp", "damper_curve_f_comp"),
            ("damper_curve_v_reb", "damper_curve_f_reb"),
        ):
            v_arr = getattr(self, v_name)
            f_arr = getattr(self, f_name)
            if v_arr is None:
                continue
            if len(v_arr) < 2:
                raise ValueError(f"{v_name} must contain at least 2 points, got {len(v_arr)}.")
            if any(v_arr[i + 1] <= v_arr[i] for i in range(len(v_arr) - 1)):
                raise ValueError(
                    f"{v_name} must be strictly increasing (duplicate or decreasing "
                    "velocity samples make force interpolation ambiguous)."
                )
            if f_arr is not None and len(f_arr) != len(v_arr):
                raise ValueError(
                    f"{v_name} ({len(v_arr)} pts) and {f_name} ({len(f_arr)} pts) must have equal length."
                )

    @property
    def k_w(self) -> float:
        """Wheel rate [N/m]: spring rate referred to wheel centre.

        k_w = k_s * MR²  where MR = spring travel / wheel travel.
        A lower MR (longer lever arm) reduces the wheel rate for a given spring rate.
        """
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
    bump_stop_force:   np.ndarray = field(default_factory=lambda: np.array([]))
    bump_stop_engaged: bool = False

    # Metrics
    rms_body_accel:    float = 0.0
    rms_body_accel_wk: float = 0.0  # ISO 2631-1 Wk frequency-weighted RMS acceleration [m/s²]
    vdv:               float = 0.0  # ISO 2631-1 Vibration Dose Value [m/s^1.75]
    rms_susp_travel:   float = 0.0
    rms_tire_load:     float = 0.0
    peak_susp_travel:  float = 0.0
    comfort_rating:    str   = ""

    # Damper model metadata
    damper_linearisation_note: str = ""  # Description of how damper was treated in freq domain
    c_eff_used:               float = 0.0  # Effective linearised damping used in freq domain [Ns/m]

    # PSD Analysis
    psd_freqs:      np.ndarray = field(default_factory=lambda: np.array([]))
    psd_values:     np.ndarray = field(default_factory=lambda: np.array([]))

    # Contact & Conservation Diagnostics
    contact_states: List[Any] = field(default_factory=list)
    liftoff_time:   Optional[float] = None
    recontact_time: Optional[float] = None
    minimum_Fz:     float = 0.0
    diagnostics:    Optional[PhysicsDiagnostics] = None
    provenance:     Optional[PhysicsProvenance] = None
    is_valid:       bool = True

    # Enveloping Physics Diagnostics
    z_r_effective:        np.ndarray = field(default_factory=lambda: np.array([]))
    tire_enveloping_mode: str = "POINT_CONTACT"
    Fx_obstacle:          np.ndarray = field(default_factory=lambda: np.array([]))

    @property
    def rms_tire_load_var(self) -> float:
        """Alias for rms_tire_load for consistency with optimization metrics."""
        return self.rms_tire_load


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

    # ── Damper linearisation ──────────────────────────────────────────────
    # If a nonlinear damper curve is present, compute an energy-equivalent
    # linearised c_eff for the frequency domain. The time domain always uses
    # the full nonlinear curve. Both analyses now describe the same setup,
    # but the freq-domain is an approximation noted in the result.
    has_nonlinear_damper = (
        (p.damper_curve_v_comp is not None and p.damper_curve_f_comp is not None)
        or (p.damper_curve_v is not None and p.damper_curve_f is not None)
    )
    if has_nonlinear_damper:
        from suspensionlab.physics.damper_model import linearise_damper_from_params
        c_eff, damper_note = linearise_damper_from_params(p, v_rms=0.05)
    else:
        c_eff = p.c_w
        damper_note = "Linear damper model (constant c_w). Frequency and time domains are consistent."
    # ─────────────────────────────────────────────────────────────────────

    H_s_arr, H_u_arr = _impedance_matrix_tf(
        omega, p.m_s, p.m_u, p.k_w, c_eff, p.k_t, p.c_t
    )

    tx_body  = np.abs(H_s_arr)
    tx_wheel = np.abs(H_u_arr)
    bode_db  = 20.0 * np.log10(np.maximum(tx_body, 1e-12))
    bode_ph  = np.degrees(np.angle(H_s_arr))

    peak_idx = np.argmax(tx_body)
    return {
        "freq_hz":                  freq_hz,
        "transmissibility_body":    tx_body,
        "transmissibility_wheel":   tx_wheel,
        "bode_magnitude_db":        bode_db,
        "bode_phase_deg":           bode_ph,
        "peak_transmissibility":    float(tx_body[peak_idx]),
        "freq_at_peak_tx":          float(freq_hz[peak_idx]),
        "damper_linearisation_note": damper_note,
        "c_eff_used":               float(c_eff),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Road Profile Generator
# ─────────────────────────────────────────────────────────────────────────────

def _road_profile_fn(profile: Union[RoadProfile, CanonicalRoadProfile]):
    """
    Return a callable z_r(t) and its derivative dz_r(t) for the given profile.
    """
    if isinstance(profile, CanonicalRoadProfile):
        speed = 20.0
        t_arr, z_arr, dz_arr = profile.get_time_excitation(vehicle_speed_mps=speed, dt=0.001)
        from scipy.interpolate import interp1d
        _zr_interp = interp1d(t_arr, z_arr, bounds_error=False, fill_value=(z_arr[0], z_arr[-1]))
        _dzr_interp = interp1d(t_arr, dz_arr, bounds_error=False, fill_value=(0.0, 0.0))
        def zr(t): return _zr_interp(np.asarray(t, dtype=float))
        def dzr(t): return _dzr_interp(np.asarray(t, dtype=float))
        return zr, dzr

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
    # Compression: dz_u > dz_s (v_comp > 0) -> engages comp curve, pushes sprung mass UP (F_damper_w < 0 -> -F_damper_w > 0)
    # Extension / Rebound: dz_s > dz_u (v_comp < 0) -> engages reb curve, pulls sprung mass DOWN (F_damper_w > 0 -> -F_damper_w < 0)
    v_comp = (dz_u - dz_s) * p.MR
    if v_comp > 0 and p.damper_curve_v_comp is not None and p.damper_curve_f_comp is not None:
        v_table_c = np.abs(np.asarray(p.damper_curve_v_comp, dtype=float))
        f_table_c = np.abs(np.asarray(p.damper_curve_f_comp, dtype=float))
        F_damper = np.interp(v_comp, v_table_c, f_table_c)
        F_damper_w = -F_damper * p.MR
    elif v_comp < 0 and p.damper_curve_v_reb is not None and p.damper_curve_f_reb is not None:
        v_table_r = np.abs(np.asarray(p.damper_curve_v_reb, dtype=float))
        f_table_r = np.abs(np.asarray(p.damper_curve_f_reb, dtype=float))
        F_damper = np.interp(-v_comp, v_table_r, f_table_r)
        F_damper_w = F_damper * p.MR
    elif p.damper_curve_v is not None and p.damper_curve_f is not None and len(p.damper_curve_v) > 1:
        F_damper = np.interp(v_comp, p.damper_curve_v, p.damper_curve_f)
        F_damper_w = -F_damper * p.MR
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
    # Compression (jounce): z_u > z_s -> pushes sprung mass UP (F_spring_w -= bump_jounce -> -F_spring_w > 0)
    # Extension (rebound): z_s > z_u -> pulls sprung mass DOWN (F_spring_w += bump_rebound -> -F_spring_w < 0)
    if p.bump_stop_rate > 0:
        jounce_gap = abs(p.bump_stop_jounce)
        rebound_gap = abs(p.bump_stop_rebound)
        if (z_u - z_s) > jounce_gap:
            delta_j = (z_u - z_s) - jounce_gap
            if delta_j <= 0.05:
                f_bs = p.bump_stop_rate * (np.exp(p.bump_stop_exp * delta_j) - 1.0)
            else:
                f_cap = p.bump_stop_rate * (np.exp(p.bump_stop_exp * 0.05) - 1.0)
                df_cap = p.bump_stop_rate * p.bump_stop_exp * np.exp(p.bump_stop_exp * 0.05)
                f_bs = f_cap + df_cap * (delta_j - 0.05)
            F_spring_w -= f_bs * p.MR**2
        elif (z_s - z_u) > rebound_gap:
            delta_r = (z_s - z_u) - rebound_gap
            if delta_r <= 0.05:
                f_bs = p.bump_stop_rate * (np.exp(p.bump_stop_exp * delta_r) - 1.0)
            else:
                f_cap = p.bump_stop_rate * (np.exp(p.bump_stop_exp * 0.05) - 1.0)
                df_cap = p.bump_stop_rate * p.bump_stop_exp * np.exp(p.bump_stop_exp * 0.05)
                f_bs = f_cap + df_cap * (delta_r - 0.05)
            F_spring_w += f_bs * p.MR**2

    # Sprung acceleration
    ddz_s = (1.0 / p.m_s) * (-F_damper_w - F_spring_w)

    F_tire = p.k_t * (z_r - z_u) + p.c_t * (dz_r - dz_u)
    # Contact-loss check: total tire load = static weight + dynamic perturbation.
    # In perturbation coordinates (z=0 at static equilibrium), the static tire
    # load equals the total supported weight: (m_s + m_u) * g.
    if p.enable_contact_loss:
        static_tire_load = (p.m_s + p.m_u) * 9.81
        if static_tire_load + F_tire < 0:
            F_tire = -static_tire_load  # Total force clamped to zero (contact lost)

    # Unsprung acceleration
    ddz_u = (1.0 / p.m_u) * (
          F_damper_w
        + F_spring_w
        + F_tire
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
    # Determine profile duration
    if hasattr(profile, "duration"):
        duration = float(profile.duration)
    elif hasattr(profile, "x"):
        speed_ref = 20.0
        if getattr(p, "enveloping_config", None) and hasattr(p.enveloping_config, "speed_mps"):
            speed_ref = p.enveloping_config.speed_mps
        duration = float((profile.x[-1] - profile.x[0]) / max(speed_ref, 0.1))
    elif hasattr(profile, "time"):
        duration = float(profile.time[-1] - profile.time[0])
    else:
        duration = 5.0

    # Determine enveloping mode and effective road excitation
    from suspensionlab.physics.tire_enveloping import (
        TireEnvelopingConfig,
        TireEnvelopingMode,
        TireEnvelopingModel,
        EnvelopedRoadProfile,
    )
    from scipy.interpolate import interp1d

    env_config = getattr(p, "enveloping_config", None)
    enveloped_profile_obj = None

    if isinstance(profile, EnvelopedRoadProfile):
        enveloped_profile_obj = profile
        _w_interp = interp1d(profile.time, profile.w_eff, bounds_error=False, fill_value=(profile.w_eff[0], profile.w_eff[-1]))
        _dw_interp = interp1d(profile.time, profile.dw_eff_dt, bounds_error=False, fill_value=(0.0, 0.0))
        def zr_fn(t): return _w_interp(np.asarray(t, dtype=float))
        def dzr_fn(t): return _dw_interp(np.asarray(t, dtype=float))
        _z_raw_interp = interp1d(profile.time, profile.z_raw, bounds_error=False, fill_value=(profile.z_raw[0], profile.z_raw[-1]))
        def zraw_fn(t): return _z_raw_interp(np.asarray(t, dtype=float))
    elif env_config is not None and env_config.mode != TireEnvelopingMode.POINT_CONTACT:
        model = TireEnvelopingModel(env_config)
        speed = env_config.speed_mps
        if isinstance(profile, CanonicalRoadProfile):
            canon = profile
        else:
            base_zr, _ = _road_profile_fn(profile)
            dt_s = 0.001
            t_s = np.arange(0.0, duration + 0.5, dt_s)
            x_s = speed * t_s
            z_s_road = base_zr(t_s)
            canon = CanonicalRoadProfile(x=x_s, z=z_s_road)

        enveloped_profile_obj = model.filter_road_profile(
            road=canon,
            speed_mps=speed,
            duration_s=duration,
            dt=t_eval_dt,
            Fz_static=(p.m_s + p.m_u) * 9.81,
        )
        _w_interp = interp1d(enveloped_profile_obj.time, enveloped_profile_obj.w_eff, bounds_error=False, fill_value=(enveloped_profile_obj.w_eff[0], enveloped_profile_obj.w_eff[-1]))
        _dw_interp = interp1d(enveloped_profile_obj.time, enveloped_profile_obj.dw_eff_dt, bounds_error=False, fill_value=(0.0, 0.0))
        def zr_fn(t): return _w_interp(np.asarray(t, dtype=float))
        def dzr_fn(t): return _dw_interp(np.asarray(t, dtype=float))
        _z_raw_interp = interp1d(enveloped_profile_obj.time, enveloped_profile_obj.z_raw, bounds_error=False, fill_value=(enveloped_profile_obj.z_raw[0], enveloped_profile_obj.z_raw[-1]))
        def zraw_fn(t): return _z_raw_interp(np.asarray(t, dtype=float))
    else:
        zr_fn, dzr_fn = _road_profile_fn(profile)
        zraw_fn = zr_fn

    t_span  = (0.0, duration)
    t_eval  = np.arange(0.0, duration, t_eval_dt)
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
        max_step=max(0.001, duration / 5000.0),
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
    z_raw_arr = zraw_fn(t)

    if enveloped_profile_obj is not None:
        _fx_interp = interp1d(enveloped_profile_obj.time, enveloped_profile_obj.Fx_env, bounds_error=False, fill_value=0.0)
        Fx_obstacle_arr = _fx_interp(t)
    else:
        Fx_obstacle_arr = np.zeros_like(t)

    # Sprung body acceleration (from EOM, not numerical differentiation)
    v_susp = dz_s - dz_u
    z_susp = z_s - z_u
    
    z_susp_adj = z_susp - p.z_0
    v_damper = v_susp * p.MR
    
    # Progressive Dampers (Split curves)
    # Compression: dz_u > dz_s (v_comp > 0) -> engages comp curve, pushes sprung mass UP (F_damper_w < 0 -> -F_damper_w > 0)
    # Extension / Rebound: dz_s > dz_u (v_comp < 0) -> engages reb curve, pulls sprung mass DOWN (F_damper_w > 0 -> -F_damper_w < 0)
    v_comp = (dz_u - dz_s) * p.MR
    F_damper_w = np.zeros_like(v_susp)
    if p.damper_curve_v_comp is not None and p.damper_curve_f_comp is not None and p.damper_curve_v_reb is not None and p.damper_curve_f_reb is not None:
        v_table_c = np.abs(np.asarray(p.damper_curve_v_comp, dtype=float))
        f_table_c = np.abs(np.asarray(p.damper_curve_f_comp, dtype=float))
        v_table_r = np.abs(np.asarray(p.damper_curve_v_reb, dtype=float))
        f_table_r = np.abs(np.asarray(p.damper_curve_f_reb, dtype=float))
        F_damper_comp = np.interp(np.maximum(0.0, v_comp), v_table_c, f_table_c)
        F_damper_reb = np.interp(np.maximum(0.0, -v_comp), v_table_r, f_table_r)
        F_damper_w = np.where(v_comp > 0, -F_damper_comp * p.MR, F_damper_reb * p.MR)
    elif p.damper_curve_v is not None and p.damper_curve_f is not None and len(p.damper_curve_v) > 1:
        F_damper = np.interp(v_comp, p.damper_curve_v, p.damper_curve_f)
        F_damper_w = -F_damper * p.MR
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
    # Compression (jounce): z_u > z_s -> pushes sprung mass UP (F_spring_w -= bump_jounce -> -F_spring_w > 0)
    # Extension (rebound): z_s > z_u -> pulls sprung mass DOWN (F_spring_w += bump_rebound -> -F_spring_w < 0)
    bump_stop_force = np.zeros_like(z_s)
    if p.bump_stop_rate > 0:
        jounce_gap = abs(p.bump_stop_jounce)
        rebound_gap = abs(p.bump_stop_rebound)
        f_cap = p.bump_stop_rate * (np.exp(p.bump_stop_exp * 0.05) - 1.0)
        df_cap = p.bump_stop_rate * p.bump_stop_exp * np.exp(p.bump_stop_exp * 0.05)

        z_comp = z_u - z_s
        delta_j = np.maximum(0.0, z_comp - jounce_gap)
        f_raw_j = np.where(
            delta_j <= 0.05,
            p.bump_stop_rate * (np.exp(p.bump_stop_exp * delta_j) - 1.0),
            f_cap + df_cap * (delta_j - 0.05)
        )
        bump_jounce = np.where(z_comp > jounce_gap, f_raw_j * p.MR**2, 0.0)

        z_ext = z_s - z_u
        delta_r = np.maximum(0.0, z_ext - rebound_gap)
        f_raw_r = np.where(
            delta_r <= 0.05,
            p.bump_stop_rate * (np.exp(p.bump_stop_exp * delta_r) - 1.0),
            f_cap + df_cap * (delta_r - 0.05)
        )
        bump_rebound = np.where(z_ext > rebound_gap, f_raw_r * p.MR**2, 0.0)

        bump_stop_force = bump_jounce - bump_rebound
        F_spring_w += -bump_jounce + bump_rebound
    
    ddz_s = (1.0 / p.m_s) * (-F_damper_w - F_spring_w)

    susp_travel   = z_s - z_u
    tire_defl     = z_u - z_r_arr
    tire_load_var = p.k_t * tire_defl + p.c_t * (dz_u - dz_r_arr)
    
    static_tire_load = (p.m_s + p.m_u) * 9.81
    if p.enable_contact_loss:
        tire_load_var = np.maximum(tire_load_var, -static_tire_load)

    # Dynamic tire force (upward positive in perturbation coordinates)
    F_tire_dyn = p.k_t * (z_r_arr - z_u) + p.c_t * (dz_r_arr - dz_u)
    if p.enable_contact_loss:
        F_tire_dyn = np.maximum(F_tire_dyn, -static_tire_load)
    total_Fz = static_tire_load + F_tire_dyn

    # ── Contact State & Liftoff / Recontact Tracking ────────────────────────
    contact_states = []
    liftoff_time = None
    recontact_time = None
    liftoff_count = 0
    liftoff_duration = 0.0
    dt_arr = np.diff(t, prepend=t[0])

    is_in_liftoff = False
    for idx, fz_val in enumerate(total_Fz):
        if fz_val <= 1e-3:
            contact_states.append(ContactState.LIFTOFF)
            liftoff_duration += float(dt_arr[idx])
            if not is_in_liftoff:
                if liftoff_time is None:
                    liftoff_time = float(t[idx])
                is_in_liftoff = True
                liftoff_count += 1
        else:
            if is_in_liftoff:
                contact_states.append(ContactState.RECONTACT)
                if recontact_time is None:
                    recontact_time = float(t[idx])
                is_in_liftoff = False
            else:
                contact_states.append(ContactState.CONTACT)

    min_Fz = float(np.min(total_Fz))

    # ── Conservation Diagnostics ───────────────────────────────────────────
    # 1. Force Residual
    ddz_u_eom = (F_damper_w + F_spring_w + F_tire_dyn) / p.m_u
    force_res_s = np.max(np.abs(p.m_s * ddz_s + F_damper_w + F_spring_w))
    
    # 2. Energy Residual: E_kin + E_pot + E_diss - W_ext
    E_kin = 0.5 * p.m_s * (dz_s ** 2) + 0.5 * p.m_u * (dz_u ** 2)
    E_pot = 0.5 * p.k_w * (z_susp_adj ** 2) + 0.5 * p.k_t * (np.maximum(0.0, -tire_defl) ** 2)
    E_total = E_kin + E_pot
    
    diagnostics = PhysicsDiagnostics(
        force_residual_max_n=float(force_res_s),
        moment_residual_max_nm=0.0,
        energy_residual_max_j=float(np.max(np.abs(np.diff(E_total)))) if len(E_total) > 1 else 0.0,
        energy_conservation_ratio=float(np.std(E_total) / (np.max(E_total) + 1e-6)),
        momentum_residual_max_ns=float(np.max(np.abs(p.m_s * dz_s + p.m_u * dz_u))),
        contact_violations_count=int(np.sum(total_Fz < -1e-6)),
        contact_states=contact_states,
        liftoff_time_s=liftoff_time,
        recontact_time_s=recontact_time,
        liftoff_duration_total_s=float(liftoff_duration),
        minimum_Fz_n=min_Fz,
        solver_name=method,
        solver_steps_taken=len(t),
        solver_evaluations=getattr(sol, "nfev", len(t)),
        converged=sol.success,
    )

    provenance = PhysicsProvenance(
        model_version="quarter-car-2dof-v3.0",
        solver=method,
        backend="scipy.integrate.solve_ivp",
        input_dataset_hash=compute_dataset_hash(p),
        parameter_version="canonical-2026",
    )

    return {
        "time":             t,
        "z_s":              z_s,
        "z_u":              z_u,
        "z_r":              z_r_arr,
        "z_r_effective":    z_r_arr,
        "z_r_raw":          z_raw_arr,
        "tire_enveloping_mode": (
            env_config.mode.value if env_config is not None else (
                enveloped_profile_obj.config.mode.value if enveloped_profile_obj is not None else "POINT_CONTACT"
            )
        ),
        "Fx_obstacle":      Fx_obstacle_arr,
        "dz_s":             dz_s,
        "dz_u":             dz_u,
        "ddz_s":            ddz_s,
        "susp_travel":      susp_travel,
        "tire_defl":        tire_defl,
        "tire_load_var":    tire_load_var,
        "contact_states":   contact_states,
        "liftoff_time":     liftoff_time,
        "recontact_time":   recontact_time,
        "minimum_Fz":       min_Fz,
        "diagnostics":      diagnostics,
        "provenance":       provenance,
        "bump_stop_force":  bump_stop_force,
        "bump_stop_engaged": bool(np.any(np.abs(bump_stop_force) > 1.0)),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Performance & Comfort Metrics
# ─────────────────────────────────────────────────────────────────────────────

def calculate_vdv(accel_wk: np.ndarray, fs: float) -> float:
    """Calculate Vibration Dose Value (VDV) [m/s^1.75] per ISO 2631-1.

    VDV = ( \\int_0^T a_wk(t)^4 dt )^(1/4)
    """
    if len(accel_wk) < 2 or fs <= 0.0:
        return 0.0
    dt = 1.0 / fs
    try:
        from scipy.integrate import trapezoid as trapz_fn
    except ImportError:
        try:
            from numpy import trapezoid as trapz_fn
        except ImportError:
            trapz_fn = np.trapz
    integral = float(trapz_fn(accel_wk**4, dx=dt))
    return float(np.maximum(0.0, integral)**0.25)


def _apply_wk_weighting(ddz_s: np.ndarray, dt: float = 0.002, fs: Optional[float] = None) -> np.ndarray:
    """
    Apply ISO 2631-1 Wk frequency weighting to vertical acceleration.
    Uses exact continuous s-domain transfer function from ISO 2631-1:1997 / ISO 8041 Annex A:
      H_wk(s) = H_h(s) * H_l(s) * H_t(s) * H_s(s)
    Evaluated in the frequency domain via rfft/irfft to eliminate bilinear warping near Nyquist.
    """
    if fs is None:
        fs = 1.0 / dt
    
    arr = np.asarray(ddz_s, dtype=np.float64)
    n = len(arr)
    if n < 4:
        return arr.copy()
    
    # Pad to 2*n to prevent circular convolution wrap-around on non-periodic transients
    n_fft = 2 * n
    freqs = np.fft.rfftfreq(n_fft, d=1.0 / fs)
    s = 1j * 2.0 * np.pi * freqs
    
    # ISO 2631-1 Wk exact parameters
    f1, Q1 = 0.4, 1.0 / np.sqrt(2.0)
    f2, Q2 = 100.0, 1.0 / np.sqrt(2.0)
    f3, f4, Q4 = 12.5, 12.5, 0.63
    f5, Q5 = 2.37, 0.91
    f6, Q6 = 3.35, 0.91
    
    w1, w2 = 2.0 * np.pi * f1, 2.0 * np.pi * f2
    w3, w4 = 2.0 * np.pi * f3, 2.0 * np.pi * f4
    w5, w6 = 2.0 * np.pi * f5, 2.0 * np.pi * f6
    
    H_wk = np.zeros(len(freqs), dtype=complex)
    idx_nz = freqs > 0
    snz = s[idx_nz]
    
    H_h = (snz**2) / (snz**2 + (w1 / Q1) * snz + w1**2)
    H_l = (w2**2) / (snz**2 + (w2 / Q2) * snz + w2**2)
    H_t = ((snz + w3) * (w4**2 / w3)) / (snz**2 + (w4 / Q4) * snz + w4**2)
    H_s = (snz**2 + (w5 / Q5) * snz + w5**2) / (snz**2 + (w6 / Q6) * snz + w6**2)
    
    H_wk[idx_nz] = H_h * H_l * H_t * H_s
    
    A = np.fft.rfft(arr, n=n_fft)
    filtered = np.fft.irfft(A * H_wk, n=n_fft)[:n]
    return filtered


def compute_metrics(time_data: dict, p: QuarterCarParams) -> dict:
    """
    Compute scalar engineering metrics from time-domain simulation results.

    ISO 2631-1 comfort boundaries (unweighted RMS body acceleration):
        < 0.315 m/s²  :  Not uncomfortable
        0.315–0.63    :  Slightly uncomfortable
        0.63–1.0      :  Fairly uncomfortable
        1.0–2.0       :  Uncomfortable
        > 2.0         :  Very uncomfortable

    Returns dict with rms_body_accel, rms_body_accel_wk, vdv, rms_susp_travel, rms_tire_load,
    peak_susp_travel, comfort_rating.
    """
    ddz_s        = time_data["ddz_s"]
    susp_travel  = time_data["susp_travel"]
    tire_lv      = time_data["tire_load_var"]

    rms_accel   = float(np.sqrt(np.mean(ddz_s ** 2)))
    
    dt = time_data["time"][1] - time_data["time"][0] if len(time_data["time"]) > 1 else 0.002
    fs = 1.0 / dt
    accel_wk = _apply_wk_weighting(ddz_s, dt=dt, fs=fs)
    rms_body_accel_wk = float(np.sqrt(np.mean(accel_wk**2)))
    vdv = calculate_vdv(accel_wk, fs=fs)

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
        "rms_body_accel":    rms_accel,
        "rms_body_accel_wk": rms_body_accel_wk,
        "vdv":               vdv,
        "rms_susp_travel":   rms_susp,
        "rms_tire_load":     rms_tire,
        "peak_susp_travel":  peak_travel,
        "comfort_rating":    comfort,
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
    strict: bool = False,
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
    is_valid = True
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
        if strict:
            raise
        import warnings
        warnings.warn(f"Time domain simulation failed: {str(e)}")
        # Provide truthful failure metrics (NaN) and invalid status to prevent deceiving optimizers
        metrics = {
            "rms_body_accel": float("nan"),
            "rms_body_accel_wk": float("nan"),
            "rms_susp_travel": float("nan"),
            "rms_tire_load": float("nan"),
            "peak_susp_travel": float("nan"),
            "comfort_rating": "Failed",
        }
        f_psd, p_psd = [], []
        time_data = {
            "time": [0.0], "z_s": [0.0], "z_u": [0.0], "z_r": [0.0],
            "z_r_effective": [0.0], "z_r_raw": [0.0], "tire_enveloping_mode": "POINT_CONTACT",
            "Fx_obstacle": [0.0],
            "dz_s": [0.0], "dz_u": [0.0], "ddz_s": [0.0],
            "susp_travel": [0.0], "tire_defl": [0.0], "tire_load_var": [0.0]
        }
        step = 1
        is_valid = False

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
        damper_linearisation_note = freq_data.get("damper_linearisation_note", ""),
        c_eff_used               = freq_data.get("c_eff_used", 0.0),
        # Time domain (downsampled)
        time          = time_data["time"][::step],
        z_s           = time_data["z_s"][::step],
        z_u           = time_data["z_u"][::step],
        z_r           = time_data["z_r"][::step],
        z_r_effective = time_data.get("z_r_effective", time_data["z_r"])[::step],
        tire_enveloping_mode = time_data.get("tire_enveloping_mode", "POINT_CONTACT"),
        Fx_obstacle   = time_data.get("Fx_obstacle", np.zeros(len(time_data["time"])))[::step],
        dz_s          = time_data["dz_s"][::step],
        dz_u          = time_data["dz_u"][::step],
        ddz_s         = time_data["ddz_s"][::step],
        susp_travel   = time_data["susp_travel"][::step],
        tire_defl     = time_data["tire_defl"][::step],
        tire_load_var = time_data["tire_load_var"][::step],
        bump_stop_force  = time_data.get("bump_stop_force", np.zeros(len(time_data["time"])))[::step],
        bump_stop_engaged = time_data.get("bump_stop_engaged", False),
        # Metrics
        rms_body_accel   = metrics["rms_body_accel"],
        rms_body_accel_wk= metrics["rms_body_accel_wk"],
        vdv              = metrics.get("vdv", 0.0),
        rms_susp_travel  = metrics["rms_susp_travel"],
        rms_tire_load    = metrics["rms_tire_load"],
        peak_susp_travel = metrics["peak_susp_travel"],
        comfort_rating   = metrics["comfort_rating"],
        # PSD
        psd_freqs        = f_psd,
        psd_values       = p_psd,
        # Contact & Conservation Diagnostics
        contact_states   = time_data.get("contact_states", [])[::step],
        liftoff_time     = time_data.get("liftoff_time", None),
        recontact_time   = time_data.get("recontact_time", None),
        minimum_Fz       = time_data.get("minimum_Fz", 0.0),
        diagnostics      = time_data.get("diagnostics", None),
        provenance       = time_data.get("provenance", None),
        is_valid         = is_valid,
    )
    return result
