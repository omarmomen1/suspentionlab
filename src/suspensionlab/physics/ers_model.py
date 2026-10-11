"""
physics/ers_model.py
====================
SuspensionLab PRO — 2026 FIA Energy Recovery System Model

Models the MGU-K (Motor Generator Unit - Kinetic) deployment and
regeneration strategy under 2026 FIA Technical Regulations.

2026 Key rule changes from 2022
--------------------------------
- MGU-K power output raised from 120 kW to ~350 kW
- No 33.3 MJ/lap deployment limit — energy limited by battery capacity
- Effective total peak power: ~500 kW ICE + 350 kW MGU-K = 850 kW
- MGU-H (heat recovery) removed entirely → simpler ERS architecture

Model scope
-----------
This model focuses on the lap-time impact of ERS strategy:
  "Where on the track to deploy, where to harvest, how to budget energy."

It is intentionally decoupled from thermal modelling of the MGU-K and
battery pack (those require more detailed input data than typically available).

References
----------
- FIA Technical Regulations 2026, Article 5 (Power Unit).
- Perez Arancibia et al., "ERS deployment optimisation for F1 hybrid power units",
  Vehicle System Dynamics, 2022.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np


# ─────────────────────────────────────────────────────────────────────────────
# ERSConfig
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ERSConfig:
    """2026 FIA ERS system parameters.

    Attributes
    ----------
    mgu_k_max_power_w     : float  Maximum MGU-K deployment power [W] (2026: ~350 kW)
    mgu_k_max_regen_w     : float  Maximum MGU-K regeneration power [W]
    battery_capacity_j    : float  Deployable energy store capacity [J]
    battery_soc_max       : float  Maximum state of charge [0–1] (avoid overcharge)
    battery_soc_min       : float  Minimum state of charge [0–1] (safety buffer)
    battery_soc_initial   : float  State of charge at lap start [0–1]
    regen_efficiency      : float  Braking energy capture efficiency [0–1]
    deploy_efficiency     : float  Deployment electrical-to-mechanical efficiency [0–1]
    min_speed_deploy_ms   : float  Minimum speed for deployment [m/s]
    min_ax_regen_ms2      : float  Minimum braking deceleration to trigger regen [m/s²]
    """
    mgu_k_max_power_w:      float = 350_000.0   # W (2026: 350 kW primary)
    mgu_k_secondary_power_w:float = 250_000.0   # W (2026: 250 kW secondary)
    mgu_k_max_regen_w:      float = 250_000.0   # W
    battery_capacity_j:     float = 4_000_000.0  # J (4 MJ deployable store)
    max_lap_recharge_j:     float = 7_000_000.0  # J (2026 FIA 7 MJ recharge ceiling)
    battery_soc_max:        float = 0.95
    battery_soc_min:        float = 0.05
    battery_soc_initial:    float = 0.50
    regen_efficiency:       float = 0.88
    deploy_efficiency:      float = 0.94
    min_speed_deploy_ms:    float = 20.0         # m/s (~72 km/h)
    min_ax_regen_ms2:       float = 3.0          # m/s² braking to regen


# ─────────────────────────────────────────────────────────────────────────────
# ERSThermalState
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ERSThermalState:
    """Thermal operational state of battery and MGU-K."""
    battery_temp_c:     float = 45.0
    mguk_temp_c:        float = 65.0
    max_battery_temp_c: float = 60.0
    max_mguk_temp_c:    float = 120.0
    is_derated:         bool  = False

    def update(self, deploy_kw: float, regen_kw: float, dt: float) -> None:
        """Update thermal state with Joule heating and cooling."""
        p_total = deploy_kw + regen_kw
        p_heat_bat = 0.003 * p_total
        p_cool_bat = 0.02 * (self.battery_temp_c - 30.0)
        self.battery_temp_c += (p_heat_bat - p_cool_bat) * dt
        
        p_heat_mguk = 0.015 * p_total
        p_cool_mguk = 0.05 * (self.mguk_temp_c - 30.0)
        self.mguk_temp_c += (p_heat_mguk - p_cool_mguk) * dt
        
        self.is_derated = (self.battery_temp_c > self.max_battery_temp_c) or (self.mguk_temp_c > self.max_mguk_temp_c)



# ─────────────────────────────────────────────────────────────────────────────
# ERSState
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ERSState:
    """Instantaneous ERS operational state."""
    soc:                float = 0.50
    deploy_power_w:     float = 0.0
    regen_power_w:      float = 0.0
    energy_deployed_j:  float = 0.0
    energy_harvested_j: float = 0.0
    thermal:            ERSThermalState = field(default_factory=ERSThermalState)

    @property
    def net_energy_j(self) -> float:
        """Net energy balance this lap [J]. Negative = net drain."""
        return self.energy_harvested_j - self.energy_deployed_j



# ─────────────────────────────────────────────────────────────────────────────
# ERSDeploymentController
# ─────────────────────────────────────────────────────────────────────────────

class ERSDeploymentController:
    """Rule-based ERS deployment / regeneration controller.

    Implements three strategies:
    - 'aggressive' : deploy maximum on all eligible straights; harvest all eligible braking zones
    - 'conservative': deploy only when SOC > 0.65; harvest in heavy braking only
    - 'optimal'    : deploy on highest-v segments first (maximum lap time ROI per joule)
                     Optimal is pre-determined by the lap analyser; this controller
                     receives a deployment_mask array to indicate eligible segments.

    Parameters
    ----------
    strategy : str  'aggressive' | 'conservative' | 'optimal'
    """

    def __init__(self, strategy: str = "optimal"):
        valid = {"aggressive", "conservative", "optimal"}
        if strategy not in valid:
            raise ValueError(f"strategy must be one of {valid}, got {strategy!r}")
        self.strategy = strategy

    def compute(
        self,
        state: ERSState,
        config: ERSConfig,
        v: float,
        ax: float,
        curvature: float,
        dt: float,
        deploy_permitted: bool = True,
        vehicle_mass_kg: float = 800.0,
    ) -> tuple[float, ERSState]:
        """Compute ERS action for one time/distance step.

        Parameters
        ----------
        state            : current ERSState
        config           : ERSConfig
        v                : speed [m/s]
        ax               : longitudinal acceleration [m/s²]
        curvature        : track curvature [1/m]
        dt               : time step [s]
        deploy_permitted : override flag (False = never deploy this segment)
        vehicle_mass_kg  : total vehicle mass [kg] for regen power estimation

        Returns
        -------
        (F_ers_n, new_state)
            F_ers_n  : additional traction force from MGU-K [N] (0 when harvesting)
            new_state: updated ERSState
        """
        soc = state.soc
        P_deploy = 0.0
        P_regen  = 0.0
        F_ers    = 0.0

        is_braking  = ax < -config.min_ax_regen_ms2
        is_straight = curvature < 0.01  # R > 100 m
        can_regen   = is_braking and v > 5.0 and soc < config.battery_soc_max
        can_deploy  = (
            deploy_permitted
            and not is_braking
            and v >= config.min_speed_deploy_ms
            and soc > config.battery_soc_min
            and ax >= -0.5  # not heavy lift-off
        )

        # SOC thresholds differ by strategy
        if self.strategy == "conservative":
            can_deploy = can_deploy and soc > 0.65
        elif self.strategy == "aggressive":
            pass  # use base thresholds

        # Regeneration
        if can_regen:
            # Available braking power from deceleration using configured vehicle mass
            P_brake_avail = abs(ax) * vehicle_mass_kg * v * 0.4  # rough split to rear axle
            P_regen = min(P_brake_avail * config.regen_efficiency, config.mgu_k_max_regen_w)

            # Clamp by remaining battery headroom
            energy_headroom = (config.battery_soc_max - soc) * config.battery_capacity_j
            P_regen = min(P_regen, energy_headroom / max(dt, 1e-6))

        # Deployment
        if can_deploy and not can_regen:
            P_deploy = config.mgu_k_max_power_w * config.deploy_efficiency
            # Clamp by remaining energy
            energy_avail = (soc - config.battery_soc_min) * config.battery_capacity_j
            P_deploy = min(P_deploy, energy_avail / max(dt, 1e-6))
            # Force at wheel
            F_ers = P_deploy / max(v, 1.0)

        # Thermal update and derating
        thermal_st = ERSThermalState(
            battery_temp_c=state.thermal.battery_temp_c,
            mguk_temp_c=state.thermal.mguk_temp_c,
            max_battery_temp_c=state.thermal.max_battery_temp_c,
            max_mguk_temp_c=state.thermal.max_mguk_temp_c,
            is_derated=state.thermal.is_derated,
        )
        thermal_st.update(P_deploy / 1000.0, P_regen / 1000.0, dt)
        if thermal_st.is_derated and P_deploy > 0:
            P_deploy *= 0.65  # Thermal derating under overheating
            F_ers = P_deploy / max(v, 1.0)

        # SOC update
        delta_energy = (P_regen - P_deploy) * dt  # J (positive = charging)
        new_soc = np.clip(soc + delta_energy / config.battery_capacity_j,
                          config.battery_soc_min, config.battery_soc_max)

        new_state = ERSState(
            soc=float(new_soc),
            deploy_power_w=P_deploy,
            regen_power_w=P_regen,
            energy_deployed_j=state.energy_deployed_j + P_deploy * dt,
            energy_harvested_j=state.energy_harvested_j + P_regen * dt,
            thermal=thermal_st,
        )
        return float(F_ers), new_state


# ─────────────────────────────────────────────────────────────────────────────
# ERSLapAnalyzer
# ─────────────────────────────────────────────────────────────────────────────

class ERSLapAnalyzer:
    """Run a full lap ERS analysis and compute energy budget + lap time delta.

    Given a speed and acceleration profile (from the lap simulator), computes:
    - Where deployment occurs segment-by-segment
    - Where regeneration occurs
    - Total energy budget
    - Estimated lap time improvement from ERS deployment

    Parameters
    ----------
    config   : ERSConfig
    strategy : str  'aggressive' | 'conservative' | 'optimal'
    vehicle_mass_kg : float  total vehicle mass for energy estimates
    """

    def __init__(
        self,
        config: Optional[ERSConfig] = None,
        strategy: str = "optimal",
        vehicle_mass_kg: float = 800.0,
    ):
        self.config   = config or ERSConfig()
        self.strategy = strategy
        self.m        = vehicle_mass_kg

    def analyze(
        self,
        distances: np.ndarray,
        speeds_ms: np.ndarray,
        ax_arr: np.ndarray,
        curvatures: np.ndarray,
    ) -> dict:
        """Analyze ERS deployment over a full lap.

        Parameters
        ----------
        distances   : cumulative distance array [m], shape (N,)
        speeds_ms   : speed at each point [m/s], shape (N,)
        ax_arr      : longitudinal acceleration [m/s²], shape (N,)
        curvatures  : curvature [1/m], shape (N,)

        Returns
        -------
        dict with:
            soc_history         : list[float] SOC at each point
            deploy_force_n      : list[float] MGU-K force [N] at each point
            deploy_power_kw     : list[float]
            regen_power_kw      : list[float]
            total_deployed_j    : float
            total_harvested_j   : float
            soc_start           : float
            soc_end             : float
            lap_time_delta_s    : float  (negative = faster)
            deployment_zones    : list[int]  indices where deployed
            regen_zones         : list[int]  indices where harvesting
            peak_deploy_kw      : float
            peak_regen_kw       : float
        """
        cfg = self.config
        n   = len(distances)

        state = ERSState(soc=cfg.battery_soc_initial)
        controller = ERSDeploymentController(strategy=self.strategy)

        # Pre-scan for 'optimal': find highest-speed segments for priority deployment
        if self.strategy == "optimal":
            speed_threshold = float(np.percentile(speeds_ms, 65))
        else:
            speed_threshold = 0.0  # always deploy when eligible

        soc_hist        = np.zeros(n)
        deploy_force    = np.zeros(n)
        deploy_power    = np.zeros(n)
        regen_power     = np.zeros(n)

        for i in range(n):
            ds   = float(distances[i] - distances[i - 1]) if i > 0 else 0.0
            v    = float(speeds_ms[i])
            ax   = float(ax_arr[i])
            curv = float(curvatures[i])
            dt   = ds / max(v, 0.1)

            # Optimal strategy: only deploy on fastest straights
            deploy_ok = (self.strategy != "optimal") or (v >= speed_threshold)

            F_ers, state = controller.compute(
                state, cfg, v, ax, curv, dt, deploy_ok, vehicle_mass_kg=self.m
            )

            soc_hist[i]     = state.soc
            deploy_force[i] = F_ers
            deploy_power[i] = state.deploy_power_w / 1000.0   # kW
            regen_power[i]  = state.regen_power_w  / 1000.0   # kW

        # Lap time delta: ERS increases forward acceleration by a_ers = F_ers / m
        # Over segment of length ds at entry speed v, Δt ≈ -0.5 * (a_ers * dt_seg²) / v
        lap_time_delta = 0.0
        for i in range(1, n):
            ds   = float(distances[i] - distances[i - 1])
            v    = max(float(speeds_ms[i]), 0.1)
            F_e  = deploy_force[i]
            if F_e > 0:
                a_ers = F_e / self.m
                dt_seg = ds / v
                lap_time_delta -= 0.5 * (a_ers * dt_seg ** 2) / max(v, 0.1)


        deploy_zones = [i for i in range(n) if deploy_force[i] > 0]
        regen_zones  = [i for i in range(n) if regen_power[i] > 0.1]

        return {
            "soc_history":           soc_hist.tolist(),
            "deploy_force_n":        deploy_force.tolist(),
            "deploy_power_kw":       deploy_power.tolist(),
            "regen_power_kw":        regen_power.tolist(),
            "total_deployed_j":      float(state.energy_deployed_j),
            "total_harvested_j":     float(state.energy_harvested_j),
            "soc_start":             cfg.battery_soc_initial,
            "soc_end":               float(state.soc),
            "lap_time_delta_s":      round(lap_time_delta, 3),
            "deployment_zones":      deploy_zones,
            "regen_zones":           regen_zones,
            "peak_deploy_kw":        round(float(np.max(deploy_power)), 1),
            "peak_regen_kw":         round(float(np.max(regen_power)),  1),
            "net_energy_j":          float(state.net_energy_j),
            "strategy":              self.strategy,
        }
