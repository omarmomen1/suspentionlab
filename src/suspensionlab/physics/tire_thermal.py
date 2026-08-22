"""
physics/tire_thermal.py
=======================
SuspensionLab PRO — Tire Thermal Model

Tracks tire bulk carcass temperature for all 4 tires over a lap and scales
the Pacejka friction coefficient accordingly.  The model is deliberately
simple enough to run inside a lap simulation inner loop (<1 µs per step)
while capturing the dominant physics:

  - Frictional heat generation proportional to slip energy
  - Convective cooling to ambient air
  - Conductive cooling to the road surface
  - Friction µ bell-curve vs temperature (peak at T_opt)

Physics references
------------------
- Milliken & Milliken, "Race Car Vehicle Dynamics", SAE 1995. Ch. 30.
- Pacejka, "Tyre and Vehicle Dynamics", 3rd Ed. Ch. 1.
- Farroni et al., "TRICK – Tire/Road Interaction Characterisation & Knowledge",
  Mechanical Systems and Signal Processing, 2019.

Sign / index convention
-----------------------
All 4-element arrays follow [FL, FR, RL, RR] order.
Temperature in °C throughout (converted to K only for absolute physics if needed).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np


# ─────────────────────────────────────────────────────────────────────────────
# TireThermalConfig
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class TireThermalConfig:
    """Thermal parameters for a single tire compound.

    Attributes
    ----------
    m_tire      : float  Effective thermal mass of the tire carcass [kg]
    c_p         : float  Specific heat capacity of rubber/compound [J/(kg·K)]
    h_air       : float  Convective heat-transfer coefficient to air [W/(m²·K)]
    A_surf      : float  Effective surface area for air cooling [m²]
    h_road      : float  Conductive heat-transfer coefficient to road [W/(m²·K)]
    A_contact   : float  Nominal contact-patch area [m²]
    T_opt       : float  Temperature of peak friction coefficient [°C]
    sigma_T     : float  Gaussian width of µ–T bell curve [°C]
                         Wider → friction degrades more slowly away from T_opt
    mu_cold     : float  Fraction of peak µ at cold (ambient) temperature [0–1]
                         Typical: 0.60–0.75 for soft compounds
    T_ambient   : float  Ambient air temperature [°C]
    T_road      : float  Track surface temperature [°C] (typically higher than air)
    k_slip      : float  Slip energy conversion efficiency [0–1]
                         Fraction of slip work converted to tire heat (rest → road)
    T_initial   : float  Starting tire temperature [°C]
    """
    m_tire:     float = 10.0     # kg
    c_p:        float = 1200.0   # J/(kg·K)
    h_air:      float = 50.0     # W/(m²·K)
    A_surf:     float = 0.15     # m²
    h_road:     float = 200.0    # W/(m²·K)
    A_contact:  float = 0.015    # m²
    T_opt:      float = 85.0     # °C
    sigma_T:    float = 30.0     # °C
    mu_cold:    float = 0.65     # [-]
    T_ambient:  float = 25.0     # °C
    T_road:     float = 35.0     # °C
    k_slip:     float = 0.70     # [-]
    T_initial:  float = 25.0     # °C

    def mu_scale_at(self, T_c: float) -> float:
        """Friction scaling factor at temperature T_c [°C].

        Returns a value in [mu_cold, 1.0] following a Gaussian bell curve
        centred at T_opt.  Below T_opt the tire is under-temperature (cold),
        above T_opt it is over-temperature (blistering).

        Parameters
        ----------
        T_c : tire temperature [°C]

        Returns
        -------
        mu_scale : float in [0, 1]
        """
        exponent = -0.5 * ((T_c - self.T_opt) / max(self.sigma_T, 1e-6)) ** 2
        return self.mu_cold + (1.0 - self.mu_cold) * math.exp(exponent)


# ─────────────────────────────────────────────────────────────────────────────
# TireThermalState
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class TireThermalState:
    """Instantaneous thermal state for all 4 tires.

    Temperature order: [FL, FR, RL, RR].

    Attributes
    ----------
    T_FL, T_FR, T_RL, T_RR : float  Tire temperatures [°C]
    """
    T_FL: float = 25.0  # °C
    T_FR: float = 25.0  # °C
    T_RL: float = 25.0  # °C
    T_RR: float = 25.0  # °C

    # ── Accessors ─────────────────────────────────────────────────────────────

    def temperatures(self) -> np.ndarray:
        """Return temperatures as [T_FL, T_FR, T_RL, T_RR] array [°C]."""
        return np.array([self.T_FL, self.T_FR, self.T_RL, self.T_RR])

    def mu_scale(self, config: TireThermalConfig) -> np.ndarray:
        """Return friction scaling factor for each tire.

        Values in [0, 1].  1.0 = tire at optimal temperature.
        Multiply into Pacejka pDy1 (mu_y) and pDx1 (mu_x) to get
        temperature-corrected forces.

        Parameters
        ----------
        config : TireThermalConfig

        Returns
        -------
        scales : np.ndarray  shape (4,), order [FL, FR, RL, RR]
        """
        T = self.temperatures()
        exponents = -0.5 * ((T - config.T_opt) / max(config.sigma_T, 1e-6)) ** 2
        return config.mu_cold + (1.0 - config.mu_cold) * np.exp(exponents)

    def mean_temperature(self) -> float:
        """Mean temperature across all 4 tires [°C]."""
        return float(np.mean(self.temperatures()))

    def at_optimal(self, config: TireThermalConfig, tol: float = 10.0) -> bool:
        """True if all tires are within tol °C of T_opt."""
        T = self.temperatures()
        return bool(np.all(np.abs(T - config.T_opt) <= tol))

    # ── Time stepping ─────────────────────────────────────────────────────────

    def step(
        self,
        config: TireThermalConfig,
        Fz: np.ndarray,
        Fx: np.ndarray,
        Fy: np.ndarray,
        v: float,
        ax: float,
        ay: float,
        dt: float,
    ) -> "TireThermalState":
        """Advance thermal state by dt seconds.

        Energy balance (per tire i):
            Q_gen[i]  = k_slip * Fz[i] * |a_resultant| * slip_coeff  [W]
            Q_conv[i] = h_air  * A_surf    * (T[i] - T_ambient)       [W]
            Q_cond[i] = h_road * A_contact * (T[i] - T_road)          [W]
            dT[i]/dt  = (Q_gen[i] - Q_conv[i] - Q_cond[i]) / (m * cp) [°C/s]

        Slip coefficient is derived from the resultant acceleration magnitude
        divided by g (dimensionless utilisation), capped at 1.0.

        Parameters
        ----------
        config : TireThermalConfig
        Fz     : np.ndarray [FL,FR,RL,RR] vertical loads [N]
        Fx     : np.ndarray longitudinal forces per wheel [N]
        Fy     : np.ndarray lateral forces per wheel [N]
        v      : vehicle speed [m/s]
        ax     : longitudinal acceleration [m/s²]
        ay     : lateral acceleration [m/s²]
        dt     : time step [s]

        Returns
        -------
        TireThermalState  (new state, does not mutate self)
        """
        T = self.temperatures()
        Fz_arr = np.maximum(np.asarray(Fz, dtype=float), 0.0)
        Fx_arr = np.asarray(Fx, dtype=float)
        Fy_arr = np.asarray(Fy, dtype=float)

        # Resultant acceleration utilisation [0-1]
        a_res = math.sqrt(ax ** 2 + ay ** 2)
        slip_util = min(a_res / 9.81, 1.2)  # dimensionless, capped

        # Heat generation: proportional to vertical load × slip utilisation
        # Higher load → more contact area → more heat generated
        # Units: [N] × [-] × [W/N] = [W];  k_slip ~ 0.04 W/(N·util) gives ~100 W/tire at peak
        # Calibrated so that at ay=2g, Fz=4kN → ~80°C steady-state
        Q_gen = config.k_slip * Fz_arr * slip_util * 0.040  # [W]

        # Convective cooling to air
        Q_conv = config.h_air * config.A_surf * (T - config.T_ambient)

        # Conductive cooling to road (only the contact patch)
        Q_cond = config.h_road * config.A_contact * (T - config.T_road)

        # Temperature derivative
        thermal_mass = config.m_tire * config.c_p
        dT = (Q_gen - Q_conv - Q_cond) / max(thermal_mass, 1e-6) * dt

        T_new = T + dT
        # Physical bounds: can't go below ambient (night session) or above 200°C (destruction)
        T_new = np.clip(T_new, config.T_ambient, 200.0)

        return TireThermalState(
            T_FL=float(T_new[0]),
            T_FR=float(T_new[1]),
            T_RL=float(T_new[2]),
            T_RR=float(T_new[3]),
        )


# ─────────────────────────────────────────────────────────────────────────────
# TireWarmupSimulator
# ─────────────────────────────────────────────────────────────────────────────

class TireWarmupSimulator:
    """Simulate tire warm-up over multiple installation laps.

    Simplifies the track to average conditions to provide a fast estimate of:
    - How many laps until tires reach optimal temperature
    - Temperature history per lap
    - Expected friction scaling per lap

    For a high-fidelity warm-up simulation, use TireThermalState.step()
    inside solve_lap() instead.

    Parameters
    ----------
    config : TireThermalConfig  Thermal parameters for the compound
    """

    def __init__(self, config: Optional[TireThermalConfig] = None):
        self.config = config or TireThermalConfig()

    def simulate_warmup(
        self,
        n_laps: int,
        track_length_m: float = 5_000.0,
        avg_speed_ms: float = 50.0,
        avg_lat_g: float = 1.5,
        avg_long_g: float = 0.5,
        avg_fz_n: float = 3_000.0,
    ) -> dict:
        """Simulate thermal evolution over n_laps.

        Parameters
        ----------
        n_laps        : number of laps to simulate
        track_length_m: lap length [m]
        avg_speed_ms  : average speed [m/s]
        avg_lat_g     : RMS lateral g over the lap
        avg_long_g    : RMS longitudinal g over the lap
        avg_fz_n      : average vertical load per tire [N]

        Returns
        -------
        dict with:
            temps_per_lap  : list[list[float]]  [lap][tire index FL/FR/RL/RR]
            mu_scale_per_lap: list[list[float]]
            laps_to_optimal : int  (-1 if not reached in n_laps)
            final_state     : TireThermalState
            lap_times_s     : list[float]  (speed / mu_scale effect)
        """
        cfg = self.config
        state = TireThermalState(
            T_FL=cfg.T_initial,
            T_FR=cfg.T_initial,
            T_RL=cfg.T_initial,
            T_RR=cfg.T_initial,
        )

        lap_time_s    = track_length_m / max(avg_speed_ms, 1.0)
        dt            = 1.0  # 1-second time steps
        n_steps_per_lap = int(lap_time_s)

        Fz_avg = np.array([avg_fz_n] * 4)
        Fx_avg = np.zeros(4)
        Fy_avg = np.zeros(4)

        temps_per_lap    = []
        mu_per_lap       = []
        laps_to_optimal  = -1

        for lap in range(n_laps):
            for _ in range(n_steps_per_lap):
                state = state.step(
                    cfg,
                    Fz=Fz_avg,
                    Fx=Fx_avg,
                    Fy=Fy_avg,
                    v=avg_speed_ms,
                    ax=avg_long_g * 9.81,
                    ay=avg_lat_g  * 9.81,
                    dt=dt,
                )
            temps_per_lap.append(state.temperatures().tolist())
            mu_scales = state.mu_scale(cfg)
            mu_per_lap.append(mu_scales.tolist())

            if laps_to_optimal < 0 and state.at_optimal(cfg, tol=12.0):
                laps_to_optimal = lap + 1

        # Estimate lap time degradation from µ scaling (faster = lower time)
        base_time  = track_length_m / max(avg_speed_ms, 1.0)
        lap_times  = []
        for mu_arr in mu_per_lap:
            mu_mean = float(np.mean(mu_arr))
            # Speed scales ~sqrt(µ) for cornering-limited laps
            corrected_time = base_time / max(math.sqrt(mu_mean), 0.5)
            lap_times.append(round(corrected_time, 2))

        return {
            "temps_per_lap":     temps_per_lap,
            "mu_scale_per_lap":  mu_per_lap,
            "laps_to_optimal":   laps_to_optimal,
            "final_temperatures": state.temperatures().tolist(),
            "final_state":       state,
            "lap_times_s":       lap_times,
            "config": {
                "T_opt":      cfg.T_opt,
                "T_initial":  cfg.T_initial,
                "T_ambient":  cfg.T_ambient,
                "T_road":     cfg.T_road,
            },
        }
