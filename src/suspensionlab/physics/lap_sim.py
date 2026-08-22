"""
physics/lap_sim.py
==================
SuspensionLab PRO — Quasi-Steady-State Lap Time Simulator

Physics fidelity
----------------
Multi-body QSS model with per-wheel load transfer and combined-slip Pacejka
tires. This is the industry-standard approach used in OptimumLap, ATLAS, and
similar professional tools.

NOT modelled (transient dynamics):
    - Sprung mass oscillation (use the quarter-car module for that)
    - Steering transient / yaw oscillation
    - Tyre warm-up / thermal model
    - Differential lock-up dynamics

IS modelled:
    - 4-wheel individual vertical loads (longitudinal + lateral load transfer)
    - Per-wheel combined-slip Pacejka forces (friction ellipse)
    - Aerodynamic downforce with front/rear balance and ride-height sensitivity
    - Full powertrain: torque curve, gear ratios, drivetrain efficiency, shift time
    - Brake bias with per-axle friction check
    - GGV (g-g-v) envelope pre-computation for fast solve-loop lookup
    - Track banking, gradient, and elevation effects
    - Power-limited terminal velocity on straights (NO arbitrary speed cap)

Sign conventions
----------------
    ax > 0  : forward acceleration (throttle)
    ax < 0  : braking deceleration
    ay > 0  : lateral (cornering), unsigned for symmetric tires
    Fz > 0  : upward (compression)

Load transfer equations
-----------------------
    dFz_long = m * ax * h_cog / L          [front↔rear]
    dFz_lat  = m * ay * h_cog / track      [inner↔outer]

    Fz_FL = Fz0_FL + dFz_aero_front/2 - dFz_long/2 - dFz_lat/2
    Fz_FR = Fz0_FR + dFz_aero_front/2 - dFz_long/2 + dFz_lat/2
    Fz_RL = Fz0_RL + dFz_aero_rear/2  + dFz_long/2 - dFz_lat/2
    Fz_RR = Fz0_RR + dFz_aero_rear/2  + dFz_long/2 + dFz_lat/2

    Positive ay → right-hand corner → outer wheels FR, RR get more load.

References
----------
- Milliken & Milliken, "Race Car Vehicle Dynamics", SAE 1995.
- Pacejka, "Tyre and Vehicle Dynamics", 3rd Ed., Elsevier 2012.
- Segers, "Analysis Techniques for Racecar Data Acquisition", SAE 2008.
- Beckman, "The Physics of Racing", Chapters 1–5, 1991.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np
from scipy.interpolate import RegularGridInterpolator

from suspensionlab.physics.magic_formula import (
    TireCoeffs,
    _calc_tire_forces_fast,
)
from suspensionlab.physics.suspension_aero_coupling import (
    SuspensionConfig,
    CoupledVehicleModel,
    CoupledState,
)


# ─────────────────────────────────────────────────────────────────────────────
# Sub-model dataclasses
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class MassProperties:
    """Vehicle mass and geometric properties.

    Attributes
    ----------
    total_mass      : float  Total vehicle mass (driver + fuel) [kg]
    h_cog           : float  CoG height [m]
    wheelbase       : float  Front-to-rear axle distance [m]
    cog_dist_front  : float  Longitudinal CoG position from FRONT axle [m].
                             Weight distribution: front = b/L, rear = a/L where
                             a = cog_dist_front, b = wheelbase - cog_dist_front.
    track_front     : float  Front track width (wheel centre to wheel centre) [m]
    track_rear      : float  Rear track width [m]
    """
    total_mass:     float = 800.0    # kg  (typical sports prototype)
    h_cog:          float = 0.30     # m
    wheelbase:      float = 2.70     # m
    cog_dist_front: float = 1.35     # m  (50:50 balance by default)
    track_front:    float = 1.55     # m
    track_rear:     float = 1.52     # m

    @property
    def a(self) -> float:
        """Distance from front axle to CoG [m]."""
        return self.cog_dist_front

    @property
    def b(self) -> float:
        """Distance from rear axle to CoG [m]."""
        return self.wheelbase - self.cog_dist_front

    @property
    def weight_dist_front(self) -> float:
        """Static front weight distribution fraction."""
        return self.b / self.wheelbase

    @property
    def weight_dist_rear(self) -> float:
        """Static rear weight distribution fraction."""
        return self.a / self.wheelbase

    @property
    def track_mean(self) -> float:
        """Mean track width [m]."""
        return 0.5 * (self.track_front + self.track_rear)


@dataclass
class AeroMap:
    """Aerodynamic map with front/rear balance and ride-height sensitivity.

    All coefficients are referenced to frontal area A; downforce = 0.5 * rho * CL * A * v².

    Attributes
    ----------
    cl_base         : float  Lift coefficient (downforce positive) at reference ride height
    cd_base         : float  Drag coefficient at reference ride height
    frontal_area    : float  Vehicle frontal area [m²]
    cop_fraction    : float  Centre of pressure as fraction of wheelbase from front [0–1].
                             0.45 = CoP is 45% from front (typical front-heavy aero balance).
    rho_air         : float  Air density [kg/m³]
    cl_rh_sens      : float  ΔCL per mm of ride-height reduction [1/mm].
                             Negative ride height → more downforce → positive sensitivity.
                             Typical ground-effect car: 0.01–0.05 per mm.
    cl_pitch_sens   : float  ΔCL per degree of nose-down pitch [1/deg].
                             Not used in QSS; reserved for transient extension.
    """
    cl_base:      float = 1.80    # typical mid-downforce single-seater
    cd_base:      float = 0.95
    frontal_area: float = 1.70    # m²
    cop_fraction: float = 0.45    # CoP 45% from front
    rho_air:      float = 1.225   # kg/m³ (sea level, 15°C)
    cl_rh_sens:   float = 0.0     # ΔCL/mm, 0 = no ground effect
    cl_pitch_sens: float = 0.0    # ΔCL/deg

    def _effective_cl(self, ride_height_mm: float = 0.0) -> float:
        """CL adjusted for ride height offset from reference."""
        return self.cl_base + self.cl_rh_sens * ride_height_mm

    def downforce_total(self, v: float, ride_height_mm: float = 0.0) -> float:
        """Total aerodynamic downforce [N] at speed v [m/s]."""
        cl = self._effective_cl(ride_height_mm)
        return 0.5 * self.rho_air * cl * self.frontal_area * v ** 2

    def downforce_front(self, v: float, ride_height_mm: float = 0.0) -> float:
        """Front axle aero downforce [N]."""
        return self.downforce_total(v, ride_height_mm) * self.cop_fraction

    def downforce_rear(self, v: float, ride_height_mm: float = 0.0) -> float:
        """Rear axle aero downforce [N]."""
        return self.downforce_total(v, ride_height_mm) * (1.0 - self.cop_fraction)

    def drag(self, v: float) -> float:
        """Aerodynamic drag force [N] at speed v [m/s]."""
        return 0.5 * self.rho_air * self.cd_base * self.frontal_area * v ** 2


@dataclass
class PowertrainModel:
    """Engine torque curve, gear ratios, and drivetrain parameters.

    Attributes
    ----------
    gear_ratios         : list[float]  Overall gear ratios (engine → wheel), including final drive.
                                       E.g., [14.2, 10.5, 8.1, 6.5, 5.2, 4.3] for a 6-speed.
                                       Final drive already included.
    torque_curve_rpm    : list[float]  Engine RPM breakpoints [rpm]
    torque_curve_nm     : list[float]  Engine torque at each breakpoint [Nm]
    rev_limit           : float        Maximum engine RPM (hard cut) [rpm]
    wheel_radius        : float        Driven wheel rolling radius [m]
    drivetrain_loss     : float        Fraction of torque lost in drivetrain [0–1].
                                       Typical: 0.10–0.15 (10–15% loss).
    shift_time_s        : float        Time lost per gear shift [s].
                                       Used to penalise acceleration in shift zones.
    max_brake_force_n   : float        Maximum total brake force [N].
    brake_front_bias    : float        Fraction of total brake force to front axle [0–1].
    """
    gear_ratios:      List[float] = field(default_factory=lambda: [13.5, 9.8, 7.4, 5.9, 4.8, 4.0])
    torque_curve_rpm: List[float] = field(default_factory=lambda: [2000, 4000, 6000, 8000, 10000, 12000])
    torque_curve_nm:  List[float] = field(default_factory=lambda: [290, 310, 315, 300, 270, 220])
    rev_limit:        float = 12000.0    # rpm
    wheel_radius:     float = 0.305      # m
    drivetrain_loss:  float = 0.12       # fraction
    shift_time_s:     float = 0.050      # s
    max_brake_force_n: float = 28_000.0  # N
    brake_front_bias: float = 0.65       # fraction

    def engine_torque(self, rpm: float) -> float:
        """Interpolate engine torque [Nm] at given rpm."""
        rpm = np.clip(rpm, self.torque_curve_rpm[0], self.rev_limit)
        return float(np.interp(rpm, self.torque_curve_rpm, self.torque_curve_nm))

    def select_gear(self, v: float) -> int:
        """Return best gear index (0-based) for speed v [m/s].

        Selects the highest gear where engine RPM stays at or below rev_limit.
        Returns 0 (first gear) if below minimum feasible speed.
        """
        if v <= 0:
            return 0
        v = max(v, 0.01)
        best_gear = 0
        for i, gr in enumerate(self.gear_ratios):
            rpm = v / self.wheel_radius * gr * (60.0 / (2.0 * np.pi))
            if rpm <= self.rev_limit:
                best_gear = i
        return best_gear

    def engine_rpm_at(self, v: float, gear: int) -> float:
        """Engine RPM at wheel speed v [m/s] in given gear."""
        gr = self.gear_ratios[gear]
        return v / self.wheel_radius * gr * (60.0 / (2.0 * np.pi))

    def max_drive_force(self, v: float) -> float:
        """Maximum traction force at wheels [N] at speed v [m/s]."""
        if v <= 0:
            return 0.0
        gear = self.select_gear(v)
        rpm = self.engine_rpm_at(v, gear)
        T_engine = self.engine_torque(rpm)
        gr = self.gear_ratios[gear]
        F_wheel = T_engine * gr * (1.0 - self.drivetrain_loss) / self.wheel_radius
        return max(F_wheel, 0.0)

    def max_power_w(self) -> float:
        """Peak power at the wheels [W]."""
        rpms = np.array(self.torque_curve_rpm)
        torques = np.array(self.torque_curve_nm)
        powers = torques * rpms * (2.0 * np.pi / 60.0) * (1.0 - self.drivetrain_loss)
        return float(np.max(powers))


# ─────────────────────────────────────────────────────────────────────────────
# TrackSegment
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class TrackSegment:
    """One sample point along a track.

    Attributes
    ----------
    distance    : float  Cumulative distance from start [m]
    curvature   : float  Signed curvature 1/R [1/m]. Magnitude used for speed limit;
                         sign can indicate left/right but tires are symmetric here.
    elevation   : float  Absolute elevation [m] (used for gradient calculation)
    bank_angle  : float  Track banking [rad]. Positive = banked to the inside (adds normal force).
    sector      : int    Sector number (1-based) this point belongs to.
    """
    distance:   float = 0.0
    curvature:  float = 0.0
    elevation:  float = 0.0
    bank_angle: float = 0.0
    sector:     int   = 1


# ─────────────────────────────────────────────────────────────────────────────
# LapSimVehicle
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class LapSimVehicle:
    """Complete vehicle definition for the QSS lap simulator.

    Composed of sub-models for mass, aero, powertrain, and tires.
    Include a SuspensionConfig to enable proper ARB-balance load transfer
    and suspension/aero coupling (Issue 8 + 11).
    Call `build_ggv()` after construction to pre-compute the GGV envelope.
    """
    mass_props:  MassProperties   = field(default_factory=MassProperties)
    aero:        AeroMap          = field(default_factory=AeroMap)
    powertrain:  PowertrainModel  = field(default_factory=PowertrainModel)
    tire_coeffs: TireCoeffs       = field(default_factory=TireCoeffs)
    suspension:  SuspensionConfig = field(default_factory=SuspensionConfig)

    # Enable coupled aero-suspension iteration in solve_lap
    # Set True when cl_rh_sens != 0 for ground-effect cars.
    use_coupling: bool = False

    # Pre-computed GGV table (filled by build_ggv)
    _ggv_speeds:   np.ndarray | None = field(default=None, repr=False)
    _ggv_ay_max:   np.ndarray | None = field(default=None, repr=False)   # (Nv,)
    _ggv_ax_accel: np.ndarray | None = field(default=None, repr=False)   # (Nv, Nay) with ay fraction
    _ggv_ax_brake: np.ndarray | None = field(default=None, repr=False)   # (Nv, Nay)
    _ggv_ay_frac:  np.ndarray | None = field(default=None, repr=False)   # (Nay,) 0..1

    # ── Legacy scalar properties (for backwards compatibility) ────────────────
    @property
    def mass(self) -> float:
        return self.mass_props.total_mass

    @property
    def aero_cl(self) -> float:
        return self.aero.cl_base

    @property
    def aero_cd(self) -> float:
        return self.aero.cd_base

    # ── Wheel load computation ────────────────────────────────────────────────

    def wheel_loads(
        self,
        v: float,
        ax: float,
        ay: float,
        ride_height_mm: float = 0.0,
        bank_rad: float = 0.0,
        rh_front_mm: Optional[float] = None,
        rh_rear_mm: Optional[float] = None,
    ) -> tuple[float, float, float, float]:
        """Compute individual wheel vertical loads [N].

        Uses proper per-axle ARB-balance lateral load transfer split.
        The front/rear split is determined by the ARB and spring roll
        stiffness ratio — not an arbitrary 50/50 split.

        Parameters
        ----------
        v             : vehicle speed [m/s]
        ax            : longitudinal acceleration [m/s²] (+ve = forward)
        ay            : lateral acceleration magnitude [m/s²] (unsigned)
        ride_height_mm: deprecated; use rh_front_mm / rh_rear_mm instead
        bank_rad      : track banking [rad] (+ve = inside higher)
        rh_front_mm   : front ride height for aero [mm] (None = reference)
        rh_rear_mm    : rear ride height for aero [mm] (None = reference)

        Returns
        -------
        Fz_FL, Fz_FR, Fz_RL, Fz_RR  [N]
        """
        mp  = self.mass_props
        sus = self.suspension
        m   = mp.total_mass
        g   = 9.81

        # Static loads
        Fz0_front = m * g * mp.weight_dist_front
        Fz0_rear  = m * g * mp.weight_dist_rear

        # Aero downforce: use per-axle ride heights when provided
        rh_f = rh_front_mm if rh_front_mm is not None else ride_height_mm
        rh_r = rh_rear_mm  if rh_rear_mm  is not None else ride_height_mm
        rh_mean = 0.5 * (rh_f + rh_r)
        df_front = self.aero.downforce_front(v, rh_mean)
        df_rear  = self.aero.downforce_rear(v, rh_mean)

        # Longitudinal load transfer: ax>0 = accel → rear gets more
        dFz_long = m * ax * mp.h_cog / mp.wheelbase

        # ── Lateral load transfer — per-axle via ARB balance (KEY FIX) ──────
        # Instead of splitting 50/50 using mean track, use the roll stiffness
        # ratio to determine how much load transfer occurs at each axle.
        # This correctly models the understeer/oversteer effect of ARB changes.
        K_phi_f = sus.roll_stiffness_front(mp.track_front)
        K_phi_r = sus.roll_stiffness_rear(mp.track_rear)
        K_phi   = K_phi_f + K_phi_r

        if K_phi > 1.0:
            lat_frac_f = K_phi_f / K_phi
            lat_frac_r = K_phi_r / K_phi
        else:
            lat_frac_f = 0.5
            lat_frac_r = 0.5

        # Per-axle lateral load transfer [N per wheel-pair]
        # Total lateral load transfer = m * ay * h_cog / track
        # Split by axle using roll stiffness fraction
        dFz_lat_f = lat_frac_f * m * ay * mp.h_cog / mp.track_front
        dFz_lat_r = lat_frac_r * m * ay * mp.h_cog / mp.track_rear

        # Banking: adds to effective normal force on outer wheels
        bank_correction_f = m * g * np.sin(abs(bank_rad)) * lat_frac_f * 0.5
        bank_correction_r = m * g * np.sin(abs(bank_rad)) * lat_frac_r * 0.5
        if bank_rad < 0:
            bank_correction_f = -bank_correction_f
            bank_correction_r = -bank_correction_r

        # Per-wheel loads (positive ay = right-hand corner → outer = FR, RR)
        Fz_FL = Fz0_front/2.0 + df_front/2.0 - dFz_long/2.0 - dFz_lat_f/2.0 - bank_correction_f
        Fz_FR = Fz0_front/2.0 + df_front/2.0 - dFz_long/2.0 + dFz_lat_f/2.0 + bank_correction_f
        Fz_RL = Fz0_rear /2.0 + df_rear /2.0 + dFz_long/2.0 - dFz_lat_r/2.0 - bank_correction_r
        Fz_RR = Fz0_rear /2.0 + df_rear /2.0 + dFz_long/2.0 + dFz_lat_r/2.0 + bank_correction_r

        # Clamp: wheels cannot pull down on the track
        Fz_FL = max(Fz_FL, 0.0)
        Fz_FR = max(Fz_FR, 0.0)
        Fz_RL = max(Fz_RL, 0.0)
        Fz_RR = max(Fz_RR, 0.0)

        return Fz_FL, Fz_FR, Fz_RL, Fz_RR

    def coupled_state(
        self,
        v: float,
        ax: float,
        ay: float,
    ) -> CoupledState:
        """Compute full coupled equilibrium state (suspension + aero + loads).

        Uses the CoupledVehicleModel to iterate ride height → aero → loads
        to convergence. Accurate for ground-effect cars (cl_rh_sens != 0)
        and under high longitudinal / lateral accelerations.

        Parameters
        ----------
        v  : speed [m/s]
        ax : longitudinal acceleration [m/s²]
        ay : lateral acceleration [m/s²] (magnitude)

        Returns
        -------
        CoupledState with wheel loads, ride heights, attitudes, aero.
        """
        model = CoupledVehicleModel(
            mass_props=self.mass_props,
            aero=self.aero,
            suspension=self.suspension,
        )
        return model.solve(v, ax, ay)

    def arb_sensitivity(
        self,
        v: float = 50.0,
        ay: float = 20.0,
        delta_arb_front_nm: float = 5_000.0,
    ) -> dict:
        """Return understeer/oversteer sensitivity to front ARB stiffening.

        Parameters
        ----------
        v                   : representative cornering speed [m/s]
        ay                  : lateral acceleration [m/s²]
        delta_arb_front_nm  : ARB stiffness perturbation [N/m]

        Returns
        -------
        dict with balance fractions and load transfer changes.
        """
        model = CoupledVehicleModel(
            mass_props=self.mass_props,
            aero=self.aero,
            suspension=self.suspension,
        )
        return model.sensitivity_to_arb(v, ay, delta_arb_front_nm)

    def ride_height_sensitivity(
        self,
        v: float = 60.0,
        delta_rh_mm: float = 5.0,
    ) -> dict:
        """Return aero sensitivity to front ride height change.

        Parameters
        ----------
        v           : speed [m/s]
        delta_rh_mm : ride height perturbation [mm]

        Returns
        -------
        dict with downforce change and load distribution.
        """
        model = CoupledVehicleModel(
            mass_props=self.mass_props,
            aero=self.aero,
            suspension=self.suspension,
        )
        return model.sensitivity_to_ride_height(v, delta_rh_mm)

    # ── Per-wheel tire forces ─────────────────────────────────────────────────

    def _tire_max_fy(self, Fz: float) -> float:
        """Peak lateral force [N] from a single tire at load Fz."""
        if Fz <= 0.0:
            return 0.0
        c = self.tire_coeffs.to_array()
        # Use alpha at peak (typically 6–10 deg → 0.10–0.18 rad)
        # Scan a few values and return max |Fy|
        best = 0.0
        for alpha in np.linspace(0.04, 0.35, 20):
            _, fy = _calc_tire_forces_fast(Fz, alpha, 0.0, 0.0, c)
            if abs(fy) > best:
                best = abs(fy)
        return best

    def _tire_max_fx(self, Fz: float) -> float:
        """Peak longitudinal force [N] from a single tire at load Fz."""
        if Fz <= 0.0:
            return 0.0
        c = self.tire_coeffs.to_array()
        best = 0.0
        for kappa in np.linspace(0.02, 0.35, 20):
            fx, _ = _calc_tire_forces_fast(Fz, 0.0, kappa, 0.0, c)
            if abs(fx) > best:
                best = abs(fx)
        return best

    def _tire_fx_with_combined(self, Fz: float, Fy_actual: float) -> float:
        """Available Fx [N] on a tire already generating Fy_actual lateral force.

        Uses friction ellipse: Fx_avail = Fx_peak * sqrt(1 - (Fy/Fy_peak)^2)
        """
        if Fz <= 0.0:
            return 0.0
        Fy_peak = self._tire_max_fy(Fz)
        Fx_peak = self._tire_max_fx(Fz)
        if Fy_peak < 1.0:
            return Fx_peak
        ratio = min(abs(Fy_actual) / Fy_peak, 1.0)
        return Fx_peak * np.sqrt(max(1.0 - ratio ** 2, 0.0))

    # ── Limit calculations ────────────────────────────────────────────────────

    def ay_max(self, v: float, bank_rad: float = 0.0) -> float:
        """Maximum lateral acceleration [m/s²] at speed v.

        Iterates load transfer: ay changes Fz_outer, which changes Fy_max.
        Converges in ~10 iterations.
        """
        mp = self.mass_props
        m  = mp.total_mass

        ay = 10.0  # initial guess [m/s²]
        for _ in range(15):
            Fz_FL, Fz_FR, Fz_RL, Fz_RR = self.wheel_loads(v, 0.0, ay, bank_rad=bank_rad)
            # Outer wheels (FR, RR) generate lateral force
            Fy_FL = self._tire_max_fy(Fz_FL)
            Fy_FR = self._tire_max_fy(Fz_FR)
            Fy_RL = self._tire_max_fy(Fz_RL)
            Fy_RR = self._tire_max_fy(Fz_RR)
            Fy_total = Fy_FL + Fy_FR + Fy_RL + Fy_RR
            ay_new = Fy_total / (m + 1e-9)
            if abs(ay_new - ay) < 0.01:
                break
            ay = 0.5 * ay + 0.5 * ay_new

        return max(float(ay), 0.0)

    def ax_max_accel(self, v: float, ay: float) -> float:
        """Maximum forward acceleration [m/s²] accounting for combined slip and drivetrain."""
        mp = self.mass_props
        m  = mp.total_mass
        drag = self.aero.drag(v)

        # Drive is rear-wheel only (typical RWD); split front/rear as needed
        Fz_FL, Fz_FR, Fz_RL, Fz_RR = self.wheel_loads(v, 0.0, ay)
        Fy_rear_share = ay * m / 2.0  # simplified: rear carries half lateral

        Fx_RL = self._tire_fx_with_combined(Fz_RL, Fy_rear_share / 2.0)
        Fx_RR = self._tire_fx_with_combined(Fz_RR, Fy_rear_share / 2.0)
        Fx_tire_max = Fx_RL + Fx_RR  # rear-wheel drive limit

        # Powertrain limit
        F_drive = self.powertrain.max_drive_force(v)

        # Take minimum of tire grip and powertrain
        Fx_net = min(F_drive, Fx_tire_max) - drag
        ax = Fx_net / (m + 1e-9)
        return max(float(ax), -drag / (m + 1e-9))  # can't accelerate more than drag allows on a flat road

    def ax_max_brake(self, v: float, ay: float) -> float:
        """Maximum braking deceleration [m/s²] (returned as positive value).

        Applies brake bias; checks per-axle tire friction limits.
        """
        mp = self.mass_props
        pt = self.powertrain
        m  = mp.total_mass
        drag = self.aero.drag(v)

        # Load transfer at some fraction of max braking (iterate once)
        ax_brake_guess = 0.8 * 9.81  # m/s² initial guess
        Fz_FL, Fz_FR, Fz_RL, Fz_RR = self.wheel_loads(v, -ax_brake_guess, ay)

        # Lateral share per axle
        ay_front_share = ay * m * mp.weight_dist_front
        ay_rear_share  = ay * m * mp.weight_dist_rear

        # Available Fx per wheel (combined slip)
        Fx_FL = self._tire_fx_with_combined(Fz_FL, ay_front_share / 2.0)
        Fx_FR = self._tire_fx_with_combined(Fz_FR, ay_front_share / 2.0)
        Fx_RL = self._tire_fx_with_combined(Fz_RL, ay_rear_share  / 2.0)
        Fx_RR = self._tire_fx_with_combined(Fz_RR, ay_rear_share  / 2.0)

        # Apply brake bias: front bias fraction of total brake force
        F_brake_front_max = Fx_FL + Fx_FR
        F_brake_rear_max  = Fx_RL + Fx_RR

        # Total brake force limited by the weaker of: front-biased limit or tire limit
        # With front_bias = 0.65: front = 0.65*F_total, rear = 0.35*F_total
        # Rear locks first if rear tire limit < rear share: F_total < F_rear_max / (1 - front_bias)
        # Front locks first if front tire limit < front share: F_total < F_front_max / front_bias
        bias = pt.brake_front_bias
        F_total_from_rear  = F_brake_rear_max  / max(1.0 - bias, 0.01)
        F_total_from_front = F_brake_front_max / max(bias, 0.01)
        F_total_from_pedal = pt.max_brake_force_n

        F_brake = min(F_total_from_rear, F_total_from_front, F_total_from_pedal)
        ax = (F_brake + drag) / (m + 1e-9)  # drag assists braking
        return max(float(ax), 0.0)

    def terminal_velocity(self) -> float:
        """Power-limited terminal velocity [m/s] on a flat straight.

        Solves: F_drive(v) = F_drag(v) using bisection.
        This replaces the old arbitrary v_apex = 100.0 m/s hack.
        """
        # Power limit: P = F_drag * v → v = (2P / (rho * Cd * A))^(1/3)
        P_max = self.powertrain.max_power_w()
        rho   = self.aero.rho_air
        Cd    = self.aero.cd_base
        A     = self.aero.frontal_area
        v_power = (2.0 * P_max / (rho * Cd * A)) ** (1.0 / 3.0)

        # Traction limit: bisect on F_drive(v) = F_drag(v)
        def residual(v: float) -> float:
            return self.powertrain.max_drive_force(v) - self.aero.drag(v)

        # Check if traction-limited at low speed
        if residual(v_power) < 0:
            # Terminal is traction-limited somewhere below v_power
            v_lo, v_hi = 5.0, v_power
            for _ in range(40):
                v_mid = 0.5 * (v_lo + v_hi)
                if residual(v_mid) > 0:
                    v_lo = v_mid
                else:
                    v_hi = v_mid
            return float(v_hi)
        return float(v_power)

    # ── GGV envelope builder ──────────────────────────────────────────────────

    def build_ggv(self, n_speeds: int = 40, n_ay: int = 20) -> np.ndarray:
        """Pre-compute the GGV (g-g-v) envelope.

        For each of n_speeds speed points and n_ay lateral fraction points,
        computes (ay_max, ax_max_accel, ax_max_brake). Results are stored on
        the vehicle object and returned as a (n_speeds, 3) array for diagnostics.

        Parameters
        ----------
        n_speeds : number of speed points (5 m/s to terminal velocity)
        n_ay     : number of ay fraction points (0 to 1)

        Returns
        -------
        ggv : (n_speeds, n_ay+2) array with columns:
              [v [m/s], ay_max [m/s²], ax_accel@ay=0, ax_accel@ay=0.5*ay_max,
               ax_accel@ay=ay_max, ax_brake@ay=0, ...]
        """
        v_term = self.terminal_velocity()
        v_arr  = np.linspace(5.0, min(v_term * 1.05, 120.0), n_speeds)
        ay_frac = np.linspace(0.0, 1.0, n_ay)

        ay_max_arr   = np.zeros(n_speeds)
        ax_accel_arr = np.zeros((n_speeds, n_ay))
        ax_brake_arr = np.zeros((n_speeds, n_ay))

        for i, v in enumerate(v_arr):
            ay_lim = self.ay_max(v)
            ay_max_arr[i] = ay_lim
            for j, frac in enumerate(ay_frac):
                ay = frac * ay_lim
                ax_accel_arr[i, j] = self.ax_max_accel(v, ay)
                ax_brake_arr[i, j] = self.ax_max_brake(v, ay)

        self._ggv_speeds   = v_arr
        self._ggv_ay_max   = ay_max_arr
        self._ggv_ay_frac  = ay_frac
        self._ggv_ax_accel = ax_accel_arr
        self._ggv_ax_brake = ax_brake_arr

        # Build 2D interpolators for fast lookup during solve_lap
        self._ggv_accel_interp = RegularGridInterpolator(
            (v_arr, ay_frac), ax_accel_arr, method="linear",
            bounds_error=False, fill_value=None
        )
        self._ggv_brake_interp = RegularGridInterpolator(
            (v_arr, ay_frac), ax_brake_arr, method="linear",
            bounds_error=False, fill_value=None
        )

        return np.column_stack([v_arr, ay_max_arr, ax_accel_arr[:, 0]])

    def _lookup_ax_accel(self, v: float, ay: float) -> float:
        """Lookup max acceleration from GGV table [m/s²]."""
        if self._ggv_ax_accel is None:
            return self.ax_max_accel(v, ay)
        ay_lim = float(np.interp(v, self._ggv_speeds, self._ggv_ay_max))
        ay_frac = np.clip(ay / max(ay_lim, 0.001), 0.0, 1.0)
        v_c = np.clip(v, self._ggv_speeds[0], self._ggv_speeds[-1])
        return float(self._ggv_accel_interp([[v_c, ay_frac]])[0])

    def _lookup_ax_brake(self, v: float, ay: float) -> float:
        """Lookup max braking deceleration from GGV table [m/s²]."""
        if self._ggv_ax_brake is None:
            return self.ax_max_brake(v, ay)
        ay_lim = float(np.interp(v, self._ggv_speeds, self._ggv_ay_max))
        ay_frac = np.clip(ay / max(ay_lim, 0.001), 0.0, 1.0)
        v_c = np.clip(v, self._ggv_speeds[0], self._ggv_speeds[-1])
        return float(self._ggv_brake_interp([[v_c, ay_frac]])[0])

    def _ay_max_lookup(self, v: float) -> float:
        """Lookup max lateral acceleration from GGV table [m/s²]."""
        if self._ggv_ay_max is None:
            return self.ay_max(v)
        return float(np.interp(v, self._ggv_speeds, self._ggv_ay_max,
                                left=self._ggv_ay_max[0],
                                right=self._ggv_ay_max[-1]))


# ─────────────────────────────────────────────────────────────────────────────
# LapSimResult
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class LapSimResult:
    """Full result from a QSS lap simulation."""
    # Scalars
    total_time:     float = 0.0   # [s]
    max_speed_kmh:  float = 0.0
    min_speed_kmh:  float = 0.0
    avg_speed_kmh:  float = 0.0
    energy_used_kj: float = 0.0   # engine energy (fuel heat or kWh)
    avg_power_kw:   float = 0.0
    arb_balance:    float = 0.0   # front ARB balance fraction [-]

    # Per-sector (sector boundaries defined by TrackSegment.sector)
    sector_times: List[float] = field(default_factory=list)

    # Arrays (length N = number of track segments)
    distances:          np.ndarray = field(default_factory=lambda: np.array([]))
    speeds:             np.ndarray = field(default_factory=lambda: np.array([]))
    lateral_g:          np.ndarray = field(default_factory=lambda: np.array([]))
    longitudinal_g:     np.ndarray = field(default_factory=lambda: np.array([]))
    curvatures:         np.ndarray = field(default_factory=lambda: np.array([]))
    gear_number:        np.ndarray = field(default_factory=lambda: np.array([]))
    drive_force_n:      np.ndarray = field(default_factory=lambda: np.array([]))
    aero_downforce_n:   np.ndarray = field(default_factory=lambda: np.array([]))
    aero_drag_n:        np.ndarray = field(default_factory=lambda: np.array([]))
    # Per-wheel loads: shape (4, N) order [FL, FR, RL, RR]
    wheel_loads_n:      np.ndarray = field(default_factory=lambda: np.zeros((4, 0)))
    # Suspension/attitude telemetry (new — Issue 8 & 11)
    pitch_deg:          np.ndarray = field(default_factory=lambda: np.array([]))
    roll_deg:           np.ndarray = field(default_factory=lambda: np.array([]))
    ride_height_front:  np.ndarray = field(default_factory=lambda: np.array([]))
    ride_height_rear:   np.ndarray = field(default_factory=lambda: np.array([]))

    # GGV data (for visualisation)
    ggv_speeds:    np.ndarray = field(default_factory=lambda: np.array([]))
    ggv_ay_max:    np.ndarray = field(default_factory=lambda: np.array([]))
    ggv_ax_accel:  np.ndarray = field(default_factory=lambda: np.array([]))  # (Nv, Nay)
    ggv_ax_brake:  np.ndarray = field(default_factory=lambda: np.array([]))

    # ERS telemetry (populated when ers_config provided to solve_lap)
    ers_soc:            np.ndarray = field(default_factory=lambda: np.array([]))
    ers_deploy_force_n: np.ndarray = field(default_factory=lambda: np.array([]))
    ers_deploy_kw:      np.ndarray = field(default_factory=lambda: np.array([]))
    ers_regen_kw:       np.ndarray = field(default_factory=lambda: np.array([]))
    ers_lap_time_delta_s: float = 0.0

    # Tire thermal telemetry (populated when tire_thermal_config provided)
    tire_temp_fl:   np.ndarray = field(default_factory=lambda: np.array([]))
    tire_temp_fr:   np.ndarray = field(default_factory=lambda: np.array([]))
    tire_temp_rl:   np.ndarray = field(default_factory=lambda: np.array([]))
    tire_temp_rr:   np.ndarray = field(default_factory=lambda: np.array([]))
    tire_mu_scale:  np.ndarray = field(default_factory=lambda: np.array([]))  # mean scale

    # Model metadata
    terminal_velocity_kmh: float = 0.0
    model_version: str = "QSS-4W-ARB-COUPLED-v3"


# ─────────────────────────────────────────────────────────────────────────────
# Track parsing utilities
# ─────────────────────────────────────────────────────────────────────────────

def parse_track_from_gps(
    latitudes: List[float],
    longitudes: List[float],
    elevations: Optional[List[float]] = None,
    smooth_sigma: float = 5.0,
) -> List[TrackSegment]:
    """Convert GPS coordinates to track segments with smooth curvature.

    Uses Mercator projection + Savitzky-Golay smoothing before finite-difference
    curvature estimation. Raw GPS curvature is very noisy.

    Parameters
    ----------
    latitudes, longitudes : GPS coordinates [decimal degrees]
    elevations            : optional elevation [m] per point
    smooth_sigma          : half-width of Gaussian smoothing kernel (points).
                            Higher = smoother curvature, less detail.
    """
    from scipy.ndimage import gaussian_filter1d

    lat_ref = np.radians(latitudes[0])
    R_earth = 6_371_000.0

    x = np.array([(lon - longitudes[0]) * np.cos(lat_ref) * R_earth * np.pi / 180.0
                   for lon in longitudes])
    y = np.array([(lat - latitudes[0]) * R_earth * np.pi / 180.0
                   for lat in latitudes])

    # Smooth the XY coordinates to reduce GPS noise before computing curvature
    if smooth_sigma > 0:
        x = gaussian_filter1d(x, sigma=smooth_sigma)
        y = gaussian_filter1d(y, sigma=smooth_sigma)

    dx  = np.gradient(x)
    dy  = np.gradient(y)
    ddx = np.gradient(dx)
    ddy = np.gradient(dy)

    ds = np.sqrt(dx ** 2 + dy ** 2)
    ds = np.maximum(ds, 1e-6)

    # Curvature κ = |x'y'' - y'x''| / (x'^2 + y'^2)^(3/2)
    curvature = np.abs(dx * ddy - dy * ddx) / (ds ** 3 + 1e-12)
    # Additional smoothing on curvature itself
    if smooth_sigma > 0:
        curvature = gaussian_filter1d(curvature, sigma=smooth_sigma * 0.5)
    curvature = np.clip(curvature, 0.0, 0.5)  # 1/R max = 0.5 m^-1 → R_min = 2 m

    cum_dist = np.cumsum(ds)
    elev = np.asarray(elevations, dtype=float) if elevations is not None else np.zeros(len(latitudes))

    return [
        TrackSegment(
            distance=float(cum_dist[i]),
            curvature=float(curvature[i]),
            elevation=float(elev[i] if i < len(elev) else 0.0),
        )
        for i in range(len(latitudes))
    ]


def parse_track_from_curvature(
    distances: List[float],
    curvatures: List[float],
    elevations: Optional[List[float]] = None,
    bank_angles: Optional[List[float]] = None,
    sectors: Optional[List[int]] = None,
) -> List[TrackSegment]:
    """Create track from pre-computed curvature data."""
    n = len(distances)
    elev  = elevations  or [0.0] * n
    banks = bank_angles or [0.0] * n
    sects = sectors     or [1]   * n
    return [
        TrackSegment(distance=d, curvature=abs(k), elevation=e, bank_angle=b, sector=s)
        for d, k, e, b, s in zip(distances, curvatures, elev, banks, sects)
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Core solver
# ─────────────────────────────────────────────────────────────────────────────

def solve_lap(
    vehicle: LapSimVehicle,
    segments: List[TrackSegment],
    *,
    build_ggv: bool = True,
    v_start: float | None = None,
    ers_config=None,       # Optional[ERSConfig] — live 2026 ERS integration
    ers_strategy: str = "optimal",
    tire_thermal_config=None,  # Optional[TireThermalConfig] — live µ scaling
) -> LapSimResult:
    """Quasi-Steady-State forward-backward integration lap solver.

    Algorithm
    ---------
    1. Pre-compute GGV envelope (if not already built).
    2. Compute apex speed at each point:
       - Corners: solve v² * |κ| = ay_max_lookup(v) iteratively.
       - Straights (|κ| < 1e-4): terminal velocity from powertrain/drag balance.
    3. Forward pass (acceleration): propagate from each apex forward.
    4. Backward pass (braking): propagate from each apex backward.
    5. Speed envelope = min(forward, backward, apex).
    6. Assemble time, gear, wheel loads, aero at each segment.
       - If ers_config provided: add MGU-K deployment force to drive force.
       - If tire_thermal_config provided: track tyre temperatures, scale µ.

    Parameters
    ----------
    vehicle           : LapSimVehicle (call build_ggv() first for performance)
    segments          : list of TrackSegment
    build_ggv         : if True and GGV not built, build it (adds ~1-3 s one-time)
    v_start           : initial speed [m/s]; default = apex speed of first segment
    ers_config        : Optional ERSConfig — enables 2026 MGU-K injection
    ers_strategy      : 'optimal' | 'aggressive' | 'conservative' (default 'optimal')
    tire_thermal_config : Optional TireThermalConfig — enables tyre temperature tracking

    Returns
    -------
    LapSimResult
    """
    n = len(segments)
    if n < 2:
        return LapSimResult()

    # Build GGV if needed
    if build_ggv and vehicle._ggv_ay_max is None:
        vehicle.build_ggv()

    # Arrays
    dist = np.array([s.distance for s in segments])
    curv = np.abs(np.array([s.curvature for s in segments]))
    elev = np.array([s.elevation  for s in segments])
    bank = np.array([s.bank_angle for s in segments])

    # Track gradient: sin(grade) = dh/ds
    grad = np.gradient(elev, dist + 1e-9)
    grad = np.clip(grad, -0.30, 0.30)  # cap at ±30% grade (sanity)

    g   = 9.81
    m   = vehicle.mass_props.total_mass
    v_t = vehicle.terminal_velocity()

    # ── Step 1: Apex speed ───────────────────────────────────────────────────
    v_apex = np.zeros(n)
    for i in range(n):
        k = curv[i]
        if k < 1e-4:
            # Straight: speed limited by terminal velocity and gradient
            # Uphill reduces terminal velocity; downhill increases it (capped at v_t * 1.1)
            grade_penalty = g * grad[i] / max(vehicle.aero.drag(v_t) / m, 0.01)
            v_apex[i] = max(v_t * (1.0 - grade_penalty * 0.1), 5.0)
        else:
            # Corner: solve v² * k = ay_max(v) for v
            # Use fixed-point iteration with lookup table
            v = float(np.sqrt(vehicle._ay_max_lookup(30.0) / (k + 1e-9)))
            v = np.clip(v, 1.0, v_t)
            for _ in range(12):
                ay_lim = vehicle._ay_max_lookup(v)
                # Reduce ay for banking: banked track adds normal force
                ay_eff = ay_lim + g * np.sin(abs(bank[i]))
                v_new = np.sqrt(ay_eff / (k + 1e-9))
                v_new = np.clip(v_new, 1.0, v_t)
                if abs(v_new - v) < 0.05:
                    break
                v = 0.6 * v + 0.4 * v_new
            v_apex[i] = float(v)

    # ── Step 2: Forward pass (acceleration) ─────────────────────────────────
    v_fwd = np.copy(v_apex)
    if v_start is not None:
        v_fwd[0] = min(v_apex[0], v_start)

    for i in range(1, n):
        ds = max(dist[i] - dist[i - 1], 0.1)
        v  = v_fwd[i - 1]
        ay = v ** 2 * curv[i - 1]

        ax_accel = vehicle._lookup_ax_accel(v, ay)
        # Subtract gradient deceleration
        ax_net = ax_accel - g * grad[i]
        ax_net = max(ax_net, -9.81)  # can't exceed full gravity deceleration

        if ax_net > 0.0:
            v_next = np.sqrt(v ** 2 + 2.0 * ax_net * ds)
        else:
            # Net deceleration on a long uphill — can still coast forward
            discriminant = v ** 2 + 2.0 * ax_net * ds
            v_next = np.sqrt(max(discriminant, 0.01))

        v_fwd[i] = min(v_fwd[i], v_next)

    # ── Step 3: Backward pass (braking) ─────────────────────────────────────
    v_bwd = np.copy(v_fwd)
    for i in range(n - 2, -1, -1):
        ds = max(dist[i + 1] - dist[i], 0.1)
        v  = v_bwd[i + 1]
        ay = v ** 2 * curv[i + 1]

        ax_brake = vehicle._lookup_ax_brake(v, ay)
        # On a downhill, braking is harder (gravity adds to speed); uphill assists
        ax_brake_net = ax_brake - g * grad[i]  # grade reduces effective braking going uphill

        v_prev = np.sqrt(v ** 2 + 2.0 * max(ax_brake_net, 0.1) * ds)
        v_bwd[i] = min(v_bwd[i], v_prev)

    v_final = v_bwd

    # ── Step 4: Telemetry assembly ───────────────────────────────────────────
    dt            = np.zeros(n)
    lat_g         = np.zeros(n)
    long_g        = np.zeros(n)
    gear_arr      = np.zeros(n, dtype=int)
    drive_f       = np.zeros(n)
    aero_down     = np.zeros(n)
    aero_drag_arr = np.zeros(n)
    wheel_loads   = np.zeros((4, n))
    pitch_arr     = np.zeros(n)
    roll_arr      = np.zeros(n)
    rh_front_arr  = np.zeros(n)
    rh_rear_arr   = np.zeros(n)
    energy_j      = 0.0

    # ── ERS setup ────────────────────────────────────────────────────────────
    _ers_ctrl    = None
    _ers_state   = None
    ers_soc_arr         = np.zeros(n)
    ers_deploy_force_arr = np.zeros(n)
    ers_deploy_kw_arr   = np.zeros(n)
    ers_regen_kw_arr    = np.zeros(n)
    if ers_config is not None:
        from suspensionlab.physics.ers_model import ERSDeploymentController, ERSState
        _ers_ctrl  = ERSDeploymentController(strategy=ers_strategy)
        _ers_state = ERSState(soc=float(getattr(ers_config, "battery_soc_initial", 0.5)))

    # ── Tire thermal setup ────────────────────────────────────────────────────
    _tire_state = None
    tire_temp_fl_arr = np.zeros(n)
    tire_temp_fr_arr = np.zeros(n)
    tire_temp_rl_arr = np.zeros(n)
    tire_temp_rr_arr = np.zeros(n)
    tire_mu_arr      = np.ones(n)
    if tire_thermal_config is not None:
        from suspensionlab.physics.tire_thermal import TireThermalState
        _tire_state = TireThermalState()

    # Coupling model (used if vehicle.use_coupling=True or cl_rh_sens!=0)
    _use_coupling = vehicle.use_coupling or (vehicle.aero.cl_rh_sens != 0.0)
    _coupler: Optional[CoupledVehicleModel] = None
    if _use_coupling:
        _coupler = CoupledVehicleModel(
            mass_props=vehicle.mass_props,
            aero=vehicle.aero,
            suspension=vehicle.suspension,
        )

    # Pre-compute ARB balance for result metadata
    mp  = vehicle.mass_props
    sus = vehicle.suspension
    arb_bal = sus.arb_balance(mp.track_front, mp.track_rear)

    for i in range(1, n):
        ds    = max(dist[i] - dist[i - 1], 1e-3)
        v_avg = max(0.5 * (v_final[i] + v_final[i - 1]), 0.1)
        dt[i] = ds / v_avg

        dv = v_final[i] - v_final[i - 1]
        ax = dv / max(dt[i], 1e-6)
        ay = v_avg ** 2 * curv[i]

        lat_g[i]  = ay / g
        long_g[i] = ax / g

        g_num = vehicle.powertrain.select_gear(v_avg)
        gear_arr[i] = g_num + 1  # 1-based

        F_drive = vehicle.powertrain.max_drive_force(v_avg) if ax > 0 else 0.0

        # ── ERS injection ────────────────────────────────────────────────────
        if _ers_ctrl is not None and _ers_state is not None:
            F_ers, _ers_state = _ers_ctrl.compute(
                _ers_state, ers_config, v=v_avg, ax=ax, curvature=curv[i], dt=dt[i]
            )
            F_drive += F_ers
            ers_soc_arr[i]          = _ers_state.soc
            ers_deploy_force_arr[i] = F_ers
            ers_deploy_kw_arr[i]    = max(F_ers * v_avg / 1000.0, 0.0)
            ers_regen_kw_arr[i]     = max(-F_ers * v_avg / 1000.0, 0.0)

        drive_f[i] = F_drive

        if _coupler is not None:
            # Full coupled state: iterates ride height ↔ aero ↔ loads
            cs = _coupler.solve(v_avg, ax, ay)
            Fz_FL, Fz_FR, Fz_RL, Fz_RR = cs.Fz_FL, cs.Fz_FR, cs.Fz_RL, cs.Fz_RR
            aero_down[i]      = cs.aero_df_total_n
            pitch_arr[i]      = cs.pitch_deg
            roll_arr[i]       = cs.roll_deg
            rh_front_arr[i]   = cs.rh_front_mm
            rh_rear_arr[i]    = cs.rh_rear_mm
            aero_drag_arr[i]  = vehicle.aero.drag(v_avg)
        else:
            # Fast analytical path: no ride-height iteration
            # Compute fast pitch/roll approximation for telemetry
            K_theta  = sus.pitch_stiffness(mp.wheelbase)
            K_phi_f  = sus.roll_stiffness_front(mp.track_front)
            K_phi_r  = sus.roll_stiffness_rear(mp.track_rear)
            K_phi    = K_phi_f + K_phi_r
            pitch_rad = ax * mp.total_mass * mp.h_cog / max(K_theta, 1.0)
            roll_rad  = ay * mp.total_mass * mp.h_cog / max(K_phi, 1.0)
            pitch_arr[i]     = np.degrees(pitch_rad)
            roll_arr[i]      = np.degrees(roll_rad)
            rh_front_arr[i]  = sus.ride_height_front + pitch_rad * mp.cog_dist_front * 1000.0
            rh_rear_arr[i]   = sus.ride_height_rear  - pitch_rad * mp.b * 1000.0

            Fz_FL, Fz_FR, Fz_RL, Fz_RR = vehicle.wheel_loads(
                v_avg, ax, ay, bank_rad=float(bank[i])
            )
            aero_d  = vehicle.aero.downforce_total(v_avg)
            aero_dr = vehicle.aero.drag(v_avg)
            aero_down[i]     = aero_d
            aero_drag_arr[i] = aero_dr


        wheel_loads[0, i] = Fz_FL
        wheel_loads[1, i] = Fz_FR
        wheel_loads[2, i] = Fz_RL
        wheel_loads[3, i] = Fz_RR

        # ── Tire thermal tracking ─────────────────────────────────────────────
        if _tire_state is not None and tire_thermal_config is not None:
            Fz_arr = np.array([Fz_FL, Fz_FR, Fz_RL, Fz_RR])
            Fx_arr = np.array([F_drive / 4.0] * 4) if ax > 0 else np.array([-F_drive / 4.0] * 4)
            Fy_arr = np.zeros(4)
            _tire_state = _tire_state.step(
                tire_thermal_config,
                Fz=Fz_arr, Fx=Fx_arr, Fy=Fy_arr,
                v=v_avg, ax=ax, ay=ay, dt=float(dt[i]),
            )
            temps = _tire_state.temperatures()
            tire_temp_fl_arr[i] = temps[0]
            tire_temp_fr_arr[i] = temps[1]
            tire_temp_rl_arr[i] = temps[2]
            tire_temp_rr_arr[i] = temps[3]
            tire_mu_arr[i]      = float(np.mean(_tire_state.mu_scale(tire_thermal_config)))

        # Energy: F_drive * ds (only during acceleration)
        if ax > 0 and F_drive > 0:
            energy_j += F_drive * ds

    total_time = float(np.sum(dt))

    # Sector times
    sector_ids  = [s.sector for s in segments]
    max_sector  = max(sector_ids)
    sector_dt   = [0.0] * (max_sector + 1)
    for i, sid in enumerate(sector_ids):
        sector_dt[sid] += dt[i]
    sector_times = [sector_dt[s] for s in range(1, max_sector + 1)]

    # GGV data for result payload
    ggv_speeds = vehicle._ggv_speeds if vehicle._ggv_speeds is not None else np.array([])
    ggv_ay_max = vehicle._ggv_ay_max if vehicle._ggv_ay_max is not None else np.array([])
    ggv_ax_acc = vehicle._ggv_ax_accel[:, 0] if vehicle._ggv_ax_accel is not None else np.array([])
    ggv_ax_brk = vehicle._ggv_ax_brake[:, 0] if vehicle._ggv_ax_brake is not None else np.array([])

    # ERS summary — estimate lap time improvement from ERS energy
    ers_dt = 0.0
    if ers_config is not None and np.any(ers_deploy_force_arr != 0):
        # Correct estimate: ΔT / T_lap ≈ -ΔE_ers / E_total_drive (1st order)
        # ΔE_ers = net work done by ERS over the lap [J]
        # E_total = total drive energy without ERS
        ers_E     = float(np.sum(np.maximum(ers_deploy_force_arr, 0) * np.diff(dist, prepend=dist[0])))
        E_total   = float(energy_j) if float(energy_j) > 0 else 1.0
        # Fraction of extra energy as % of total — apply to lap time
        ers_dt = -total_time * (ers_E / max(E_total + ers_E, 1.0))
        # Cap at physically plausible values (max ±20s on any lap)
        ers_dt = float(np.clip(ers_dt, -20.0, 0.0))

    return LapSimResult(
        total_time=total_time,
        sector_times=sector_times,
        distances=dist,
        speeds=v_final,
        lateral_g=lat_g,
        longitudinal_g=long_g,
        curvatures=curv,
        gear_number=gear_arr.astype(float),
        drive_force_n=drive_f,
        aero_downforce_n=aero_down,
        aero_drag_n=aero_drag_arr,
        wheel_loads_n=wheel_loads,
        pitch_deg=pitch_arr,
        roll_deg=roll_arr,
        ride_height_front=rh_front_arr,
        ride_height_rear=rh_rear_arr,
        arb_balance=float(arb_bal),
        max_speed_kmh=float(np.max(v_final) * 3.6),
        min_speed_kmh=float(np.min(v_final) * 3.6),
        avg_speed_kmh=float(np.mean(v_final) * 3.6),
        energy_used_kj=float(energy_j / 1000.0),
        avg_power_kw=float(energy_j / max(total_time, 1.0) / 1000.0),
        terminal_velocity_kmh=float(v_t * 3.6),
        ggv_speeds=ggv_speeds,
        ggv_ay_max=ggv_ay_max,
        ggv_ax_accel=ggv_ax_acc,
        ggv_ax_brake=ggv_ax_brk,
        # ERS telemetry
        ers_soc=ers_soc_arr,
        ers_deploy_force_n=ers_deploy_force_arr,
        ers_deploy_kw=ers_deploy_kw_arr,
        ers_regen_kw=ers_regen_kw_arr,
        ers_lap_time_delta_s=round(ers_dt, 4),
        # Tire thermal telemetry
        tire_temp_fl=tire_temp_fl_arr,
        tire_temp_fr=tire_temp_fr_arr,
        tire_temp_rl=tire_temp_rl_arr,
        tire_temp_rr=tire_temp_rr_arr,
        tire_mu_scale=tire_mu_arr,
    )
