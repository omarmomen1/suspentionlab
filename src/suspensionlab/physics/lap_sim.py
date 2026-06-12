"""
physics/lap_sim.py
==================
SuspensionLab PRO — Point-Mass Lap Time Simulator

Uses a quasi-steady-state point-mass approach:
1. Import track as a series of segments (curvature + distance)
2. Calculate maximum cornering speed from tire grip (Magic Formula)
3. Forward/backward integration for acceleration/braking zones
4. Predict sector and total lap times

This is the GGV-diagram method used by professional race engineers.

References:
- Milliken & Milliken, "Race Car Vehicle Dynamics"
- Optimum Lap methodology (public literature)
"""

from __future__ import annotations

import numpy as np
from dataclasses import dataclass, field
from typing import List, Optional
from scipy.optimize import minimize_scalar

from suspensionlab.physics.magic_formula import calc_tire_forces, TireCoeffs


@dataclass
class TrackSegment:
    distance: float       # cumulative distance from start [m]
    curvature: float      # 1/radius [1/m], 0 = straight
    elevation: float = 0.0  # elevation change [m]
    bank_angle: float = 0.0  # track banking [rad]


@dataclass
class LapSimVehicle:
    mass: float = 1200.0          # total mass [kg]
    aero_cl: float = 1.5          # lift coefficient (downforce positive)
    aero_cd: float = 0.9          # drag coefficient
    frontal_area: float = 1.8     # frontal area [m^2]
    cog_height: float = 0.35      # center of gravity height [m]
    wheelbase: float = 2.6        # wheelbase [m]
    weight_dist_front: float = 0.47  # front weight distribution
    tire_radius: float = 0.33     # tire radius [m]
    max_power: float = 350_000.0  # peak engine power [W]
    max_brake_force: float = 25_000.0  # max braking force [N]
    tire_coeffs: TireCoeffs = field(default_factory=TireCoeffs)
    rho_air: float = 1.225        # air density [kg/m^3]

    def aero_downforce(self, v: float) -> float:
        return 0.5 * self.rho_air * self.aero_cl * self.frontal_area * v**2

    def aero_drag(self, v: float) -> float:
        return 0.5 * self.rho_air * self.aero_cd * self.frontal_area * v**2

    def max_lateral_g(self, v: float) -> float:
        """Maximum lateral acceleration from tire grip + aero."""
        Fz_total = self.mass * 9.81 + self.aero_downforce(v)
        
        def obj(alpha):
            _, Fy = calc_tire_forces(
                Fz=Fz_total / 4,
                alpha_rad=alpha,
                kappa=0.0,
                coeffs=self.tire_coeffs,
            )
            return -abs(Fy)
            
        res = minimize_scalar(obj, bounds=(0.02, 0.30), method='bounded')
        total_lateral = -res.fun * 4
        return total_lateral / (self.mass + 1e-9)

    def max_longitudinal_accel(self, v: float) -> float:
        """Max forward acceleration at given speed [m/s^2]."""
        if v < 1.0:
            v = 1.0
        power_limited = self.max_power / (self.mass * v)
        Fz_total = self.mass * 9.81 + self.aero_downforce(v)
        
        def obj(kappa):
            Fx, _ = calc_tire_forces(
                Fz=Fz_total / 4,
                alpha_rad=0.0,
                kappa=kappa,
                coeffs=self.tire_coeffs,
            )
            return -abs(Fx)
            
        res = minimize_scalar(obj, bounds=(0.02, 0.30), method='bounded')
        traction_limited = -res.fun * 4 / self.mass
        drag_decel = self.aero_drag(v) / self.mass
        return min(power_limited, traction_limited) - drag_decel

    def max_braking_decel(self, v: float) -> float:
        """Max braking deceleration (positive value) [m/s^2]."""
        Fz_total = self.mass * 9.81 + self.aero_downforce(v)
        
        def obj(kappa):
            Fx, _ = calc_tire_forces(
                Fz=Fz_total / 4,
                alpha_rad=0.0,
                kappa=-kappa, # Test negative slip
                coeffs=self.tire_coeffs,
            )
            return -abs(Fx)
            
        res = minimize_scalar(obj, bounds=(0.02, 0.30), method='bounded')
        tire_limited = -res.fun * 4 / self.mass
        aero_assist = self.aero_drag(v) / self.mass
        return tire_limited + aero_assist


@dataclass
class LapSimResult:
    total_time: float = 0.0              # total lap time [s]
    sector_times: List[float] = field(default_factory=list)
    distances: np.ndarray = field(default_factory=lambda: np.array([]))
    speeds: np.ndarray = field(default_factory=lambda: np.array([]))
    lateral_g: np.ndarray = field(default_factory=lambda: np.array([]))
    longitudinal_g: np.ndarray = field(default_factory=lambda: np.array([]))
    max_speed_kmh: float = 0.0
    min_speed_kmh: float = 0.0
    avg_speed_kmh: float = 0.0
    energy_used_kj: float = 0.0


def parse_track_from_gps(
    latitudes: List[float],
    longitudes: List[float],
    elevations: Optional[List[float]] = None,
) -> List[TrackSegment]:
    """
    Convert GPS coordinates to track segments with curvature.
    Uses finite differences on XY projection (Mercator approximation).
    """
    lat_ref = np.radians(latitudes[0])
    R_earth = 6_371_000.0

    x = np.array([(lon - longitudes[0]) * np.cos(lat_ref) * R_earth * np.pi / 180
                  for lon in longitudes])
    y = np.array([(lat - latitudes[0]) * R_earth * np.pi / 180
                  for lat in latitudes])

    dx = np.gradient(x)
    dy = np.gradient(y)
    ddx = np.gradient(dx)
    ddy = np.gradient(dy)

    ds = np.sqrt(dx**2 + dy**2)
    ds = np.maximum(ds, 1e-6)

    # Curvature = |x'y'' - y'x''| / (x'^2 + y'^2)^(3/2)
    curvature = np.abs(dx * ddy - dy * ddx) / (ds**3 + 1e-12)

    cum_dist = np.cumsum(ds)
    elev = np.array(elevations) if elevations else np.zeros(len(latitudes))

    segments = []
    for i in range(len(latitudes)):
        segments.append(TrackSegment(
            distance=cum_dist[i],
            curvature=float(curvature[i]),
            elevation=float(elev[i]) if i < len(elev) else 0.0,
        ))
    return segments


def parse_track_from_curvature(
    distances: List[float],
    curvatures: List[float],
) -> List[TrackSegment]:
    """Create track from pre-computed curvature data."""
    return [
        TrackSegment(distance=d, curvature=k)
        for d, k in zip(distances, curvatures)
    ]


def solve_lap(vehicle: LapSimVehicle, segments: List[TrackSegment]) -> LapSimResult:
    """
    Forward-Backward Integration Solver (GGV-diagram method) for quasi-steady lap simulation.
    """
    n = len(segments)
    if n == 0:
        return LapSimResult()

    dist = np.array([seg.distance for seg in segments])
    curv = np.array([seg.curvature for seg in segments])
    
    # 1. Apex speed (max cornering speed from lateral grip)
    v_apex = np.zeros(n)
    for i in range(n):
        k = curv[i]
        if k < 1e-4:
            v_apex[i] = 100.0  # arbitrary high speed for straights (360 km/h)
        else:
            v = 20.0 # initial guess
            for _ in range(5):
                a_lat = vehicle.max_lateral_g(v) * 9.81
                v_new = np.sqrt(a_lat / k)
                v = 0.5 * v + 0.5 * v_new
            v_apex[i] = v

    # 2. Forward pass (acceleration)
    v_fwd = np.copy(v_apex)
    for i in range(1, n):
        ds = dist[i] - dist[i-1]
        v_current = v_fwd[i-1]
        a_long = vehicle.max_longitudinal_accel(v_current) * 9.81
        v_next_accel = np.sqrt(v_current**2 + 2 * a_long * ds)
        v_fwd[i] = min(v_fwd[i], v_next_accel)

    # 3. Backward pass (braking)
    v_bwd = np.copy(v_fwd)
    for i in range(n-2, -1, -1):
        ds = dist[i+1] - dist[i]
        v_current = v_bwd[i+1]
        a_brake = vehicle.max_braking_decel(v_current) * 9.81
        v_prev_brake = np.sqrt(v_current**2 + 2 * a_brake * ds)
        v_bwd[i] = min(v_bwd[i], v_prev_brake)
        
    # The final speed is the envelope
    v_final = v_bwd
    
    # Calculate times and telemetry
    dt = np.zeros(n)
    lat_g = np.zeros(n)
    long_g = np.zeros(n)
    
    for i in range(1, n):
        ds = dist[i] - dist[i-1]
        v_avg = 0.5 * (v_final[i] + v_final[i-1])
        dt[i] = ds / max(v_avg, 1.0)
        
        dv = v_final[i] - v_final[i-1]
        long_g[i] = (dv / dt[i]) / 9.81
        lat_g[i] = (v_final[i]**2 * curv[i]) / 9.81

    total_time = np.sum(dt)
    
    return LapSimResult(
        total_time=float(total_time),
        sector_times=[float(total_time)],
        distances=dist,
        speeds=v_final,
        lateral_g=lat_g,
        longitudinal_g=long_g,
        max_speed_kmh=float(np.max(v_final) * 3.6),
        min_speed_kmh=float(np.min(v_final) * 3.6),
        avg_speed_kmh=float(np.mean(v_final) * 3.6)
    )
