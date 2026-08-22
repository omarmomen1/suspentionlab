"""
physics/suspension_aero_coupling.py
=====================================
SuspensionLab PRO — Suspension/Aero/Tire Coupling Model

Implements the coupling loop between:
    Suspension kinematics (spring rates, ARB, motion ratios, ride height)
    → Pitch and roll attitudes from load transfer
    → Front/rear ride height change
    → Aero downforce change via ride-height and pitch sensitivity
    → Updated wheel loads
    → Back to suspension deflection (iterate to convergence)

This is the physics core of Issue 11 (Coupled Vehicle Model) and also
drives the improved load transfer for Issue 8.

Physics references
------------------
- Milliken & Milliken, "Race Car Vehicle Dynamics", SAE 1995. Ch. 16–18.
- Dixon, "Tires, Suspension and Handling", 2nd Ed. SAE 1996. Ch. 6–8.
- Blundell & Harty, "Multibody Systems Approach to Vehicle Dynamics", 2nd Ed. 2015.

Sign conventions
----------------
    Heave   z_h  > 0  : body rises (droop / unloaded)
    Pitch   θ    > 0  : nose-up (rear squats, front rises = under acceleration)
    Roll    φ    > 0  : body rolls right (left-hand corner, outer = right wheels)
    
    Ride height at axle: h = h_ref + z_h ± θ*L/2 ∓ φ*t/2
    (sign convention: more positive = higher ride height = less downforce for
    ground-effect cars with negative cl_rh_sens)
"""

from __future__ import annotations

import math
import warnings
from dataclasses import dataclass, field
from typing import Optional


# ─────────────────────────────────────────────────────────────────────────────
# SuspensionConfig — per-axle spring & ARB stiffness
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class SuspensionConfig:
    """Suspension spring, anti-roll bar, and geometry parameters.

    Attributes
    ----------
    k_spring_front    : float  Front spring rate at the wheel [N/m]
    k_spring_rear     : float  Rear spring rate at the wheel [N/m]
    k_arb_front       : float  Front anti-roll bar rate at the wheel [N/m]
                               (effective roll stiffness contribution per wheel)
    k_arb_rear        : float  Rear anti-roll bar rate at the wheel [N/m]
    motion_ratio_front: float  Front motion ratio = spring travel / wheel travel [-]
    motion_ratio_rear : float  Rear motion ratio [-]
    ride_height_front : float  Reference front ride height [mm]
                               (distance from ground to reference datum at front axle)
    ride_height_rear  : float  Reference rear ride height [mm]

    Notes on roll stiffness
    -----------------------
    Per-axle roll stiffness [Nm/rad]:
        K_phi_front = (k_spring_front + k_arb_front) * track_front² / 2
        K_phi_rear  = (k_spring_rear  + k_arb_rear)  * track_rear²  / 2

    ARB balance = K_phi_front / (K_phi_front + K_phi_rear)
    This determines understeer/oversteer balance under cornering.
    """
    k_spring_front:     float = 35_000.0   # N/m  (35 kN/m typical single-seater)
    k_spring_rear:      float = 45_000.0   # N/m  (stiffer rear = mild understeer)
    k_arb_front:        float = 15_000.0   # N/m
    k_arb_rear:         float = 10_000.0   # N/m
    motion_ratio_front: float = 0.85       # [-]  spring travel / wheel travel
    motion_ratio_rear:  float = 0.90       # [-]
    ride_height_front:  float = 30.0       # mm  at reference (zero load aerodynamics)
    ride_height_rear:   float = 60.0       # mm

    def roll_stiffness_front(self, track_front: float) -> float:
        """Front axle roll stiffness [Nm/rad].

        Parameters
        ----------
        track_front : front track width [m]
        """
        return (self.k_spring_front + self.k_arb_front) * track_front ** 2 / 2.0

    def roll_stiffness_rear(self, track_rear: float) -> float:
        """Rear axle roll stiffness [Nm/rad]."""
        return (self.k_spring_rear + self.k_arb_rear) * track_rear ** 2 / 2.0

    def roll_stiffness_total(self, track_front: float, track_rear: float) -> float:
        """Total roll stiffness [Nm/rad]."""
        return self.roll_stiffness_front(track_front) + self.roll_stiffness_rear(track_rear)

    def arb_balance(self, track_front: float, track_rear: float) -> float:
        """Front ARB balance fraction [-] (0 = all rear, 1 = all front).

        Values above ~0.55 tend toward understeer; below ~0.45 toward oversteer.
        """
        K_f = self.roll_stiffness_front(track_front)
        K_r = self.roll_stiffness_rear(track_rear)
        return K_f / max(K_f + K_r, 1.0)

    def heave_stiffness_front(self) -> float:
        """Front heave stiffness at the wheel [N/m] (springs only, not ARB)."""
        return 2.0 * self.k_spring_front  # 2 wheels

    def heave_stiffness_rear(self) -> float:
        """Rear heave stiffness at the wheel [N/m]."""
        return 2.0 * self.k_spring_rear

    def pitch_stiffness(self, wheelbase: float) -> float:
        """Body pitch stiffness [Nm/rad] about the CoG.

        K_theta = K_heave_front * a² + K_heave_rear * b²
        For symmetric CoG (a=b=L/2): K_theta = (K_f + K_r) * (L/2)²
        """
        a = wheelbase / 2.0  # simplified: CoG at mid-wheelbase
        b = wheelbase / 2.0
        return self.heave_stiffness_front() * a ** 2 + self.heave_stiffness_rear() * b ** 2


# ─────────────────────────────────────────────────────────────────────────────
# CoupledState — instantaneous vehicle equilibrium state
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class CoupledState:
    """Instantaneous coupled vehicle equilibrium state.

    Attributes
    ----------
    heave_mm          : float  Body heave displacement [mm]. Positive = body rises.
    pitch_deg         : float  Body pitch angle [deg]. Positive = nose-up.
    roll_deg          : float  Body roll angle [deg]. Positive = roll right.
    rh_front_mm       : float  Effective front ride height [mm]
    rh_rear_mm        : float  Effective rear ride height [mm]
    Fz_FL, FR, RL, RR : float  Wheel vertical loads [N]
    aero_df_total_n   : float  Total aerodynamic downforce [N]
    aero_df_front_n   : float  Front aero downforce [N]
    aero_df_rear_n    : float  Rear aero downforce [N]
    converged         : bool   Whether the coupling iteration converged
    n_iterations      : int    Number of coupling iterations used
    """
    heave_mm:       float = 0.0
    pitch_deg:      float = 0.0
    roll_deg:       float = 0.0
    rh_front_mm:    float = 30.0
    rh_rear_mm:     float = 60.0
    Fz_FL:          float = 0.0
    Fz_FR:          float = 0.0
    Fz_RL:          float = 0.0
    Fz_RR:          float = 0.0
    aero_df_total_n: float = 0.0
    aero_df_front_n: float = 0.0
    aero_df_rear_n:  float = 0.0
    converged:      bool  = False
    n_iterations:   int   = 0


# ─────────────────────────────────────────────────────────────────────────────
# CoupledVehicleModel — the coupling engine
# ─────────────────────────────────────────────────────────────────────────────

class CoupledVehicleModel:
    """Coupled suspension/aero/tire equilibrium solver.

    Solves the fixed-point iteration:

        loads → deflections → ride heights → aero → loads

    until convergence. Typically converges in 5–10 iterations.

    Parameters
    ----------
    mass_props  : MassProperties  Vehicle mass and geometry
    aero        : AeroMap         Aerodynamic map
    suspension  : SuspensionConfig  Spring/ARB stiffness and ride heights
    g           : float           Gravitational acceleration [m/s²]
    tol         : float           Convergence tolerance on ride height [mm]
    max_iter    : int             Maximum coupling iterations
    """

    def __init__(
        self,
        mass_props,
        aero,
        suspension: SuspensionConfig,
        g: float = 9.81,
        tol: float = 0.05,
        max_iter: int = 20,
    ):
        self.mp  = mass_props
        self.aero = aero
        self.sus  = suspension
        self.g    = g
        self.tol  = tol
        self.max_iter = max_iter

    # ── Public: solve one operating point ────────────────────────────────────

    def solve(
        self,
        v: float,
        ax: float,
        ay: float,
    ) -> CoupledState:
        """Solve coupled equilibrium at speed v, longitudinal ax, lateral ay.

        Parameters
        ----------
        v  : speed [m/s]
        ax : longitudinal acceleration [m/s²], positive = forward
        ay : lateral acceleration [m/s²], unsigned magnitude

        Returns
        -------
        CoupledState with converged wheel loads, ride heights, and aero.
        """
        mp  = self.mp
        sus = self.sus
        g   = self.g
        m   = mp.total_mass

        # Pre-compute geometry
        track_f = mp.track_front
        track_r = mp.track_rear
        K_phi_f = sus.roll_stiffness_front(track_f)
        K_phi_r = sus.roll_stiffness_rear(track_r)
        K_phi   = K_phi_f + K_phi_r

        # Per-axle lateral load transfer fractions (ARB balance)
        # This is the key physics improvement over the naive 50/50 split.
        lat_frac_front = K_phi_f / max(K_phi, 1.0)
        lat_frac_rear  = K_phi_r / max(K_phi, 1.0)

        # Pitch stiffness [Nm/rad]
        L = mp.wheelbase
        a = mp.cog_dist_front   # front axle to CoG
        b = L - a               # rear axle to CoG
        K_heave_f = sus.heave_stiffness_front()
        K_heave_r = sus.heave_stiffness_rear()
        K_theta   = K_heave_f * a ** 2 + K_heave_r * b ** 2

        # Total heave stiffness
        K_heave = K_heave_f + K_heave_r

        # Initialise ride heights from reference
        rh_f = sus.ride_height_front
        rh_r = sus.ride_height_rear

        converged = False
        n_iter    = 0
        state     = CoupledState()

        for n_iter in range(1, self.max_iter + 1):
            # Step 1: Aero at current ride heights
            rh_mean = 0.5 * (rh_f + rh_r)
            theta_deg = state.pitch_deg
            cl_eff = (self.aero.cl_base
                      + self.aero.cl_rh_sens * rh_mean
                      + self.aero.cl_pitch_sens * theta_deg)
            cl_eff = max(cl_eff, 0.0)  # downforce cannot be negative (lift becomes drag)

            q_dyn = 0.5 * self.aero.rho_air * self.aero.frontal_area * v ** 2
            df_total = cl_eff * q_dyn
            df_front = df_total * self.aero.cop_fraction
            df_rear  = df_total * (1.0 - self.aero.cop_fraction)

            # Step 2: Static wheel loads (no dynamics yet)
            Fz0_f = m * g * mp.weight_dist_front
            Fz0_r = m * g * mp.weight_dist_rear

            # Step 3: Load transfer
            # Longitudinal: ax > 0 (accel) → rear gets more load
            dFz_long = m * ax * mp.h_cog / L

            # Lateral: proper per-axle split via ARB balance
            # Front axle lateral load transfer
            dFz_lat_f = lat_frac_front * m * ay * mp.h_cog / track_f
            # Rear axle lateral load transfer
            dFz_lat_r = lat_frac_rear  * m * ay * mp.h_cog / track_r

            # Step 4: Per-wheel loads
            Fz_FL = max(Fz0_f / 2.0 + df_front / 2.0 - dFz_long / 2.0 - dFz_lat_f / 2.0, 0.0)
            Fz_FR = max(Fz0_f / 2.0 + df_front / 2.0 - dFz_long / 2.0 + dFz_lat_f / 2.0, 0.0)
            Fz_RL = max(Fz0_r / 2.0 + df_rear  / 2.0 + dFz_long / 2.0 - dFz_lat_r / 2.0, 0.0)
            Fz_RR = max(Fz0_r / 2.0 + df_rear  / 2.0 + dFz_long / 2.0 + dFz_lat_r / 2.0, 0.0)

            # Step 5: Body attitude from suspension deflection
            # Total vertical load on each axle
            Fz_front_total = Fz_FL + Fz_FR
            Fz_rear_total  = Fz_RL + Fz_RR

            # Heave: body sinks under load
            # dz_heave = -dF_aero_total / K_heave  (aero pushes body down)
            F_aero_total = df_total
            heave_mm = -(F_aero_total / K_heave) * 1000.0  # mm, negative = body sinks

            # Pitch from longitudinal acceleration
            # Torque about CoG: front = -dFz_long*a, rear = +dFz_long*b
            # Net pitch moment ≈ dFz_long * (a+b)/2 approximation
            # More accurate: θ = -ax * m * h_cog / K_theta
            # +θ = nose-up (forward accel → rear squats → nose up)
            if K_theta > 1.0:
                pitch_rad = ax * m * mp.h_cog / K_theta
            else:
                pitch_rad = 0.0
            pitch_deg = math.degrees(pitch_rad)

            # Roll from lateral acceleration
            # φ = ay * m * h_cog / K_phi
            if K_phi > 1.0:
                roll_rad = ay * m * mp.h_cog / K_phi
            else:
                roll_rad = 0.0
            roll_deg = math.degrees(roll_rad)

            # Step 6: New ride heights
            # Nose-up pitch → front ride height increases, rear decreases
            rh_f_new = sus.ride_height_front + heave_mm + pitch_rad * a * 1000.0
            rh_r_new = sus.ride_height_rear  + heave_mm - pitch_rad * b * 1000.0

            # Clamp: ride height cannot be negative (car bottoming out)
            rh_f_new = max(rh_f_new, 0.0)
            rh_r_new = max(rh_r_new, 0.0)

            # Step 7: Check convergence
            delta_rh = abs(rh_f_new - rh_f) + abs(rh_r_new - rh_r)
            rh_f = rh_f_new
            rh_r = rh_r_new

            # Update state for next iteration
            state.pitch_deg = pitch_deg

            if delta_rh < self.tol:
                converged = True
                break

        state = CoupledState(
            heave_mm=heave_mm,
            pitch_deg=pitch_deg,
            roll_deg=roll_deg,
            rh_front_mm=rh_f,
            rh_rear_mm=rh_r,
            Fz_FL=Fz_FL,
            Fz_FR=Fz_FR,
            Fz_RL=Fz_RL,
            Fz_RR=Fz_RR,
            aero_df_total_n=df_total,
            aero_df_front_n=df_front,
            aero_df_rear_n=df_rear,
            converged=converged,
            n_iterations=n_iter,
        )
        return state

    # ── Setup sensitivity analysis ────────────────────────────────────────────

    def sensitivity_to_arb(
        self,
        v: float,
        ay: float,
        delta_arb_front: float = 5_000.0,
    ) -> dict:
        """Compute sensitivity of front/rear load transfer to ARB change.

        Parameters
        ----------
        v               : speed [m/s]
        ay              : lateral acceleration [m/s²]
        delta_arb_front : change in front ARB rate to perturb [N/m]

        Returns
        -------
        dict with keys:
            baseline_arb_balance  : baseline front ARB balance fraction
            perturbed_arb_balance : perturbed front ARB balance fraction
            delta_lat_transfer_front_n : change in front lateral load transfer [N]
            delta_lat_transfer_rear_n  : change in rear lateral load transfer [N]
            understeer_tendency   : 'more' | 'less' | 'unchanged'
        """
        sus_base = self.sus
        m    = self.mp.total_mass
        h    = self.mp.h_cog
        tf   = self.mp.track_front
        tr   = self.mp.track_rear

        K_phi_f_base = sus_base.roll_stiffness_front(tf)
        K_phi_r_base = sus_base.roll_stiffness_rear(tr)
        K_phi_base   = K_phi_f_base + K_phi_r_base

        lat_frac_f_base = K_phi_f_base / max(K_phi_base, 1.0)
        dFz_lat_f_base  = lat_frac_f_base * m * ay * h / tf

        # Perturbed
        k_arb_f_new = sus_base.k_arb_front + delta_arb_front
        K_phi_f_new = (sus_base.k_spring_front + k_arb_f_new) * tf ** 2 / 2.0
        K_phi_new   = K_phi_f_new + K_phi_r_base
        lat_frac_f_new  = K_phi_f_new / max(K_phi_new, 1.0)
        dFz_lat_f_new   = lat_frac_f_new * m * ay * h / tf

        delta_lt_f = dFz_lat_f_new - dFz_lat_f_base

        # More front load transfer → more front tire saturation → understeer
        understeer = "more" if delta_lt_f > 10 else ("less" if delta_lt_f < -10 else "unchanged")

        return {
            "baseline_arb_balance":         round(lat_frac_f_base, 4),
            "perturbed_arb_balance":         round(lat_frac_f_new,  4),
            "delta_lat_transfer_front_n":    round(delta_lt_f, 1),
            "delta_lat_transfer_rear_n":     round(-delta_lt_f, 1),  # conservation
            "understeer_tendency":           understeer,
        }

    def sensitivity_to_ride_height(
        self,
        v: float,
        delta_rh_mm: float = 5.0,
    ) -> dict:
        """Compute sensitivity of aero downforce to front ride height change.

        Parameters
        ----------
        v           : speed [m/s]
        delta_rh_mm : ride height perturbation [mm] (positive = raise front)

        Returns
        -------
        dict with aero change and load distribution change.
        """
        q_dyn = 0.5 * self.aero.rho_air * self.aero.frontal_area * v ** 2
        dCL_drh = self.aero.cl_rh_sens  # ΔCL/mm

        delta_df = dCL_drh * delta_rh_mm * q_dyn  # N change in total downforce
        delta_df_front = delta_df * self.aero.cop_fraction
        delta_df_rear  = delta_df * (1.0 - self.aero.cop_fraction)

        return {
            "delta_rh_front_mm":          delta_rh_mm,
            "delta_downforce_total_n":     round(delta_df, 1),
            "delta_downforce_front_n":     round(delta_df_front, 1),
            "delta_downforce_rear_n":      round(delta_df_rear, 1),
            "note": ("Lowering front ride height increases downforce on a ground-effect car "
                     "(cl_rh_sens > 0). Rear ride height is more sensitive on modern cars."),
        }
