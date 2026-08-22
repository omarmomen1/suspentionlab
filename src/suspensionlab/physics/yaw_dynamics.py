"""
physics/yaw_dynamics.py
========================
SuspensionLab PRO — Yaw Moment Analysis & Transient Bicycle Model

Implements:
1. Milliken Moment Method (MMM) — the standard F1 tool for analysing
   vehicle stability and control balance at steady state
2. 2-DOF transient bicycle model — for qualifying simulation and
   dynamic stability analysis

The MMM diagram plots yaw moment Mz vs lateral force Fy as the vehicle
sideslip angle β and steer angle δ are swept.  A well-balanced car has
its control lines (constant δ) and stability lines (constant β) arranged
symmetrically around the origin.

Physics references
------------------
- Milliken, W.F. & Milliken, D.L. "Race Car Vehicle Dynamics", SAE 1995.
  Ch. 5 (Steady State), Ch. 6 (MMM), Ch. 7 (Transient).
- Dixon, J.C. "Tires, Suspension and Handling", 2nd Ed. SAE 1996. Ch. 7.
- Guiggiani, M. "The Science of Vehicle Dynamics", Springer 2014. Ch. 6–8.

Sign conventions
----------------
    β  (sideslip) > 0  : body points left relative to velocity vector
    r  (yaw rate)  > 0  : counter-clockwise (left-hand turn)
    δ  (steer)     > 0  : steer left (positive = left turn)
    Mz             > 0  : yaw moment tending to turn car left
    a              : distance from front axle to CoG
    b              : distance from rear axle to CoG  (b = L - a)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional, Tuple

import numpy as np


# ─────────────────────────────────────────────────────────────────────────────
# BicycleModelParams
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class BicycleModelParams:
    """Single-track (bicycle) model vehicle parameters.

    Cornering stiffnesses are the total per-axle values (both wheels combined).
    At the linearised level, C_alpha is the slope of Fy vs slip angle (rad).

    Attributes
    ----------
    mass            : float  Total vehicle mass [kg]
    Iz              : float  Yaw moment of inertia about vertical axis [kg·m²]
    wheelbase       : float  L = a + b [m]
    cog_dist_front  : float  a — distance from front axle to CoG [m]
    C_alpha_front   : float  Front axle cornering stiffness (linearised) [N/rad]
    C_alpha_rear    : float  Rear axle cornering stiffness (linearised) [N/rad]
    """
    mass:           float = 800.0
    Iz:             float = 1200.0      # kg·m²
    wheelbase:      float = 2.70        # m
    cog_dist_front: float = 1.35        # a [m]
    C_alpha_front:  float = 120_000.0   # N/rad
    C_alpha_rear:   float = 140_000.0   # N/rad

    @property
    def b(self) -> float:
        """Distance from rear axle to CoG [m]."""
        return self.wheelbase - self.cog_dist_front

    @property
    def a(self) -> float:
        """Distance from front axle to CoG [m] (alias for cog_dist_front)."""
        return self.cog_dist_front


# ─────────────────────────────────────────────────────────────────────────────
# MMMResult
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class MMMResult:
    """Result of a Milliken Moment Method computation.

    Attributes
    ----------
    beta_deg     : np.ndarray  Sideslip angles [deg], shape (n_beta,)
    delta_deg    : np.ndarray  Steer angles [deg], shape (n_delta,)
    Fy_total     : np.ndarray  Total lateral force [N], shape (n_beta, n_delta)
    Mz_total     : np.ndarray  Total yaw moment [N·m], shape (n_beta, n_delta)
    understeer_gradient : float  K_us [deg/g] (positive = US, negative = OS)
    neutral_steer_speed : float  V_char [m/s] (inf if neutral/oversteer)
    stability_index     : float  Signed balance index
    """
    beta_deg:            np.ndarray = field(default_factory=lambda: np.array([]))
    delta_deg:           np.ndarray = field(default_factory=lambda: np.array([]))
    Fy_total:            np.ndarray = field(default_factory=lambda: np.zeros((1, 1)))
    Mz_total:            np.ndarray = field(default_factory=lambda: np.zeros((1, 1)))
    understeer_gradient: float = 0.0
    neutral_steer_speed: float = float("inf")
    stability_index:     float = 0.0


# ─────────────────────────────────────────────────────────────────────────────
# YawMomentAnalyzer
# ─────────────────────────────────────────────────────────────────────────────

class YawMomentAnalyzer:
    """Compute the Milliken Moment Method diagram for a vehicle.

    Uses the linearised bicycle model to sweep sideslip (β) and steer (δ),
    computing the resulting total lateral force and yaw moment at each point.

    Parameters
    ----------
    params : BicycleModelParams
    """

    def __init__(self, params: BicycleModelParams):
        self.p = params

    def understeer_gradient(self) -> float:
        """Understeer gradient K_us [deg/g].

        K_us > 0 : understeer (need more steer above characteristic speed)
        K_us < 0 : oversteer (need less steer, unstable above critical speed)
        K_us = 0 : neutral steer

        From equilibrium: K_us = m/L * (b/C_αr - a/C_αf)  [rad/(m/s²)]
        Converted to deg/g: multiply by (180/π × g)
        """
        p = self.p
        K_us_rad = p.mass / p.wheelbase * (p.b / p.C_alpha_rear - p.a / p.C_alpha_front)
        return K_us_rad * 9.81 * (180.0 / math.pi)  # deg/g

    def neutral_steer_speed(self) -> float:
        """Characteristic (neutral steer) speed [m/s].

        Only meaningful for understeer vehicles (K_us > 0).
        At this speed, the steer angle required equals the Ackermann angle.
        Above this speed, the car becomes increasingly difficult to steer.
        Returns math.inf for oversteer or neutral vehicles.
        """
        p = self.p
        K_us_rad = p.mass / p.wheelbase * (p.b / p.C_alpha_rear - p.a / p.C_alpha_front)
        if K_us_rad <= 1e-9:
            return math.inf
        return math.sqrt(9.81 * p.wheelbase / K_us_rad)

    def compute_mmm(
        self,
        v: float,
        beta_range: Tuple[float, float] = (-10.0, 10.0),
        delta_range: Tuple[float, float] = (-5.0, 5.0),
        n_beta: int = 21,
        n_delta: int = 11,
    ) -> MMMResult:
        """Compute the full Milliken Moment Method diagram at speed v.

        For each (β, δ) pair, the equilibrium yaw rate is found, then
        tire slip angles and forces are computed.

        Parameters
        ----------
        v           : speed [m/s]
        beta_range  : (min, max) sideslip angle sweep [deg]
        delta_range : (min, max) steer angle sweep [deg]
        n_beta      : number of β points
        n_delta     : number of δ points

        Returns
        -------
        MMMResult
        """
        p  = self.p
        Cf = p.C_alpha_front
        Cr = p.C_alpha_rear
        L  = p.wheelbase
        a  = p.a
        b  = p.b
        m  = p.mass
        g  = 9.81

        beta_arr  = np.linspace(beta_range[0],  beta_range[1],  n_beta)
        delta_arr = np.linspace(delta_range[0], delta_range[1], n_delta)

        Fy_mat = np.zeros((n_beta, n_delta))
        Mz_mat = np.zeros((n_beta, n_delta))

        K_us_rad = m / L * (b / Cr - a / Cf)

        for i, beta_d in enumerate(beta_arr):
            for j, delta_d in enumerate(delta_arr):
                beta_r  = math.radians(beta_d)
                delta_r = math.radians(delta_d)

                # Equilibrium yaw rate (from steady-state bicycle model solution)
                # r_eq = v * delta / (L * (1 + K_us * v²/g))
                denom = L * (1.0 + K_us_rad * v ** 2 / g)
                if abs(denom) < 1e-6:
                    r_eq = 0.0
                else:
                    r_eq = v * delta_r / denom

                # Slip angles
                alpha_f = delta_r - beta_r - (a / max(v, 0.1)) * r_eq
                alpha_r = -beta_r + (b / max(v, 0.1)) * r_eq

                # Lateral forces
                Fyf = Cf * alpha_f
                Fyr = Cr * alpha_r

                # Clamp to friction limit (Fz0 ~ 3500 N per axle, µ ~ 1.5)
                Fy_lim = 1.5 * m * g / 2.0
                Fyf = np.clip(Fyf, -Fy_lim, Fy_lim)
                Fyr = np.clip(Fyr, -Fy_lim, Fy_lim)

                Fy_mat[i, j] = Fyf + Fyr
                Mz_mat[i, j] = a * Fyf - b * Fyr

        K_us_deg = self.understeer_gradient()
        V_char   = self.neutral_steer_speed()

        return MMMResult(
            beta_deg=beta_arr,
            delta_deg=delta_arr,
            Fy_total=Fy_mat,
            Mz_total=Mz_mat,
            understeer_gradient=round(K_us_deg, 3),
            neutral_steer_speed=round(V_char, 2) if V_char < 1e6 else float("inf"),
            stability_index=round(K_us_deg, 3),
        )


# ─────────────────────────────────────────────────────────────────────────────
# TransientState
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class TransientState:
    """2-DOF bicycle model state.

    Attributes
    ----------
    beta : float  Sideslip angle [rad]
    r    : float  Yaw rate [rad/s]
    t    : float  Simulation time [s]
    """
    beta: float = 0.0
    r:    float = 0.0
    t:    float = 0.0


# ─────────────────────────────────────────────────────────────────────────────
# TransientYawSolver
# ─────────────────────────────────────────────────────────────────────────────

class TransientYawSolver:
    """2-DOF bicycle model transient solver.

    Equations of motion:
        m·v·(dβ/dt + r) = F_yf + F_yr
        Iz·(dr/dt)       = a·F_yf − b·F_yr

    Rearranging:
        dβ/dt = (F_yf + F_yr)/(m·v) − r
        dr/dt = (a·F_yf − b·F_yr)/Iz

    where:
        F_yf = C_αf · (δ − β − a·r/v)
        F_yr = C_αr · (−β + b·r/v)

    Integration uses classic RK4 for accuracy.

    Parameters
    ----------
    params : BicycleModelParams
    """

    def __init__(self, params: BicycleModelParams):
        self.p = params

    def _derivatives(
        self,
        beta: float,
        r: float,
        delta: float,
        v: float,
    ) -> Tuple[float, float]:
        """Compute [dβ/dt, dr/dt] from current state and inputs."""
        p  = self.p
        Cf = p.C_alpha_front
        Cr = p.C_alpha_rear
        v  = max(v, 0.5)  # avoid division by zero at standstill

        alpha_f = delta - beta - p.a * r / v
        alpha_r = -beta + p.b * r / v

        Fyf = Cf * alpha_f
        Fyr = Cr * alpha_r

        d_beta = (Fyf + Fyr) / (p.mass * v) - r
        d_r    = (p.a * Fyf - p.b * Fyr) / p.Iz

        return d_beta, d_r

    def step(
        self,
        state: TransientState,
        delta: float,
        v: float,
        dt: float,
    ) -> TransientState:
        """Advance state by dt using RK4 integration.

        Parameters
        ----------
        state : current TransientState
        delta : steer angle [rad]
        v     : vehicle speed [m/s]
        dt    : time step [s]

        Returns
        -------
        TransientState  (new state, does not mutate self)
        """
        β0 = state.beta
        r0 = state.r

        # RK4
        k1β, k1r = self._derivatives(β0,             r0,             delta, v)
        k2β, k2r = self._derivatives(β0 + 0.5*dt*k1β, r0 + 0.5*dt*k1r, delta, v)
        k3β, k3r = self._derivatives(β0 + 0.5*dt*k2β, r0 + 0.5*dt*k2r, delta, v)
        k4β, k4r = self._derivatives(β0 +     dt*k3β, r0 +     dt*k3r, delta, v)

        β_new = β0 + dt / 6.0 * (k1β + 2*k2β + 2*k3β + k4β)
        r_new = r0 + dt / 6.0 * (k1r + 2*k2r + 2*k3r + k4r)

        return TransientState(beta=β_new, r=r_new, t=state.t + dt)

    def simulate_corner(
        self,
        v: float,
        radius: float,
        t_total: float = 3.0,
        dt: float = 0.005,
    ) -> dict:
        """Simulate a vehicle entering steady-state cornering.

        Computes the required steer angle for steady-state cornering at
        radius R and speed v, then applies it as a step input from t=0.

        Parameters
        ----------
        v       : cornering speed [m/s]
        radius  : corner radius [m] (positive = left-hand)
        t_total : simulation duration [s]
        dt      : integration time step [s]

        Returns
        -------
        dict with: t, beta_deg, r_rads, Fy_n, Mz_nm, settled_at_t
        """
        p  = self.p
        L  = p.wheelbase
        g  = 9.81

        K_us_rad = p.mass / L * (p.b / p.C_alpha_rear - p.a / p.C_alpha_front)
        # Required steer angle for steady-state cornering
        delta_ss = L / radius + K_us_rad * v ** 2 / (g * radius)

        n_steps = int(t_total / dt)
        t_arr   = np.zeros(n_steps)
        β_arr   = np.zeros(n_steps)
        r_arr   = np.zeros(n_steps)
        Fy_arr  = np.zeros(n_steps)
        Mz_arr  = np.zeros(n_steps)

        state = TransientState(beta=0.0, r=0.0, t=0.0)
        settled_at = t_total  # default: never settled

        for i in range(n_steps):
            t_arr[i] = state.t
            β_arr[i] = math.degrees(state.beta)
            r_arr[i] = state.r

            α_f = delta_ss - state.beta - p.a * state.r / max(v, 0.1)
            α_r = -state.beta + p.b * state.r / max(v, 0.1)
            Fy_arr[i] = p.C_alpha_front * α_f + p.C_alpha_rear * α_r
            Mz_arr[i] = p.a * p.C_alpha_front * α_f - p.b * p.C_alpha_rear * α_r

            state = self.step(state, delta_ss, v, dt)

            # Detect settling: yaw rate within 2% of steady-state
            r_ss = v / radius
            if settled_at == t_total and abs(state.r - r_ss) < 0.02 * abs(r_ss) and state.t > 0.2:
                settled_at = state.t

        return {
            "t":             t_arr.tolist(),
            "beta_deg":      β_arr.tolist(),
            "r_rads":        r_arr.tolist(),
            "Fy_n":          Fy_arr.tolist(),
            "Mz_nm":         Mz_arr.tolist(),
            "settled_at_t":  round(settled_at, 3),
            "r_steady_state": round(v / radius, 4),
            "delta_steer_deg": round(math.degrees(delta_ss), 3),
        }

    def time_to_steady_state(self, v: float, radius: float) -> float:
        """Analytical time constant for yaw response [s].

        Uses the dominant eigenvalue of the linearised system.
        Smaller time constant = faster, more responsive vehicle.

        Parameters
        ----------
        v      : speed [m/s]
        radius : corner radius [m]

        Returns
        -------
        Time constant τ [s]
        """
        metrics = compute_stability_metrics(self.p, v)
        return metrics["time_constant_s"]


# ─────────────────────────────────────────────────────────────────────────────
# compute_stability_metrics
# ─────────────────────────────────────────────────────────────────────────────

def compute_stability_metrics(params: BicycleModelParams, v: float) -> dict:
    """Compute full set of yaw stability metrics at speed v.

    Uses the eigenvalues of the 2-DOF bicycle model state matrix to compute
    natural frequency, damping ratio, and time constant.

    Parameters
    ----------
    params : BicycleModelParams
    v      : speed [m/s]

    Returns
    -------
    dict with:
        understeer_gradient_deg_per_g  : float  K_us [deg/g]
        neutral_steer_speed_kmh        : float  V_char [km/h] (inf if OS/neutral)
        stability_index                : float  +ve = US, -ve = OS
        yaw_natural_freq_hz            : float  ωn / (2π) [Hz]
        yaw_damping_ratio              : float  ζ [-]
        handling_class                 : str    'understeer'/'neutral'/'oversteer'
        time_constant_s                : float  1/|Re(λ_dominant)| [s]
    """
    try:
        import scipy.linalg as la
        _have_scipy = True
    except ImportError:
        _have_scipy = False

    p  = params
    Cf = p.C_alpha_front
    Cr = p.C_alpha_rear
    a  = p.a
    b  = p.b
    m  = p.mass
    Iz = p.Iz
    L  = p.wheelbase
    g  = 9.81
    v  = max(v, 1.0)  # avoid singularity

    # Linearised state matrix A for [β, r] state vector
    # dβ/dt = -(Cf+Cr)/(mv)·β + (-(aCf-bCr)/(mv²)-1)·r + Cf/(mv)·δ
    # dr/dt = -(aCf-bCr)/Iz·β - (a²Cf+b²Cr)/(Iz·v)·r  + a*Cf/Iz·δ
    A11 = -(Cf + Cr) / (m * v)
    A12 = -(a * Cf - b * Cr) / (m * v ** 2) - 1.0
    A21 = -(a * Cf - b * Cr) / Iz
    A22 = -(a ** 2 * Cf + b ** 2 * Cr) / (Iz * v)

    A = np.array([[A11, A12], [A21, A22]])

    if _have_scipy:
        eigvals = la.eigvals(A)
    else:
        # Characteristic polynomial: λ² - tr(A)λ + det(A) = 0
        tr_A  = A11 + A22
        det_A = A11 * A22 - A12 * A21
        disc  = tr_A ** 2 - 4.0 * det_A
        if disc >= 0:
            eigvals = np.array([
                (-tr_A + math.sqrt(disc)) / 2.0,
                (-tr_A - math.sqrt(disc)) / 2.0,
            ], dtype=complex)
        else:
            real_part = -tr_A / 2.0
            imag_part = math.sqrt(-disc) / 2.0
            eigvals = np.array([
                complex(real_part, imag_part),
                complex(real_part, -imag_part),
            ])

    # Find dominant eigenvalue (smallest negative real part = slowest mode)
    real_parts = np.real(eigvals)
    imag_parts = np.imag(eigvals)

    # Natural frequency and damping from eigenvalues
    # λ = -ζωn ± iωd, ωd = ωn√(1-ζ²)
    omega_n_arr = np.abs(eigvals)
    if len(omega_n_arr) > 0 and omega_n_arr[0] > 1e-6:
        omega_n = float(omega_n_arr[0])
        zeta    = float(-real_parts[0] / omega_n) if omega_n > 1e-6 else 1.0
    else:
        omega_n = 0.0
        zeta    = 1.0

    # Time constant from slowest mode
    slowest_real = max(np.real(eigvals), key=lambda x: -x)  # least negative real
    tau = 1.0 / max(abs(slowest_real), 0.01)

    # Understeer gradient
    K_us_rad = m / L * (b / Cr - a / Cf)
    K_us_deg = K_us_rad * g * (180.0 / math.pi)

    # Neutral steer speed
    if K_us_rad > 1e-9:
        V_char = math.sqrt(g * L / K_us_rad)
    else:
        V_char = math.inf

    if K_us_deg > 0.5:
        handling_class = "understeer"
    elif K_us_deg < -0.5:
        handling_class = "oversteer"
    else:
        handling_class = "neutral"

    return {
        "understeer_gradient_deg_per_g": round(K_us_deg, 3),
        "neutral_steer_speed_kmh":       round(V_char * 3.6, 1) if V_char < 1e6 else None,
        "stability_index":               round(K_us_deg, 3),
        "yaw_natural_freq_hz":           round(omega_n / (2 * math.pi), 3),
        "yaw_damping_ratio":             round(zeta, 3),
        "handling_class":                handling_class,
        "time_constant_s":               round(tau, 3),
    }
