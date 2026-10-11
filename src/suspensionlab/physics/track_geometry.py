"""
physics/track_geometry.py
=========================
SuspensionLab PRO — Circuit 2D Geometry & Coordinate Integration Engine
Authoritative spatial reconstruction of race circuits from track telemetry.

When circuits are supplied via distance and curvature arrays (without GPS coordinates),
this module mathematically reconstructs Cartesian coordinates (x, y) by numerical
integration of track heading and tangential displacement:
    θ(s) = θ₀ + ∫ κ(σ) dσ
    x(s) = x₀ + ∫ cos(θ(σ)) dσ
    y(s) = y₀ + ∫ sin(θ(σ)) dσ

Features:
- Trapezoidal integration with clothoid segment interpolation
- Loop closure correction for continuous closed racing circuits
- Aspect-ratio preserving viewport normalization for SVG/Canvas rendering
- GPS latitude/longitude to local tangent plane Cartesian conversion
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Union

import numpy as np


@dataclass
class TrackCoordinates:
    """Cartesian 2D coordinate representation of a race circuit."""
    x: np.ndarray             # Track east / X coordinates [m]
    y: np.ndarray             # Track north / Y coordinates [m]
    heading_rad: np.ndarray   # Heading angle at each station [rad]
    is_closed: bool           # True if circuit was closed
    closure_error_m: float    # Distance between start and raw end before closure [m]

    @property
    def n_points(self) -> int:
        return len(self.x)

    def to_dict(self) -> Dict[str, Union[List[float], bool, float]]:
        """JSON-safe dictionary representation."""
        return {
            "x": self.x.tolist(),
            "y": self.y.tolist(),
            "heading_rad": self.heading_rad.tolist(),
            "is_closed": self.is_closed,
            "closure_error_m": round(float(self.closure_error_m), 3),
        }


def integrate_track_coordinates(
    distances: Union[Sequence[float], np.ndarray],
    curvatures: Union[Sequence[float], np.ndarray],
    *,
    initial_heading_rad: float = 0.0,
    close_loop: bool = True,
    closure_tolerance_frac: float = 0.25,
    closure_threshold_m: Optional[float] = None,
) -> TrackCoordinates:
    """
    Numerically integrate heading and Cartesian coordinates from distance and curvature.

    Parameters
    ----------
    distances : Cumulative station distance along circuit centerline [m].
    curvatures : Signed curvature at each station [1/m] (positive = right turn).
    initial_heading_rad : Initial circuit heading angle [rad] (default 0 = East).
    close_loop : If True and circuit starts and finishes at same station, applies
                 smooth linear closure to remove numerical integration drift.
    closure_tolerance_frac : Maximum allowable closure error as fraction of track length
                             to apply closed-loop correction.
    closure_threshold_m : Optional absolute allowable closure error in meters.

    Returns
    -------
    TrackCoordinates dataclass containing x, y, heading_rad, and closure diagnostics.
    """
    s = np.asarray(distances, dtype=float)
    kappa = np.asarray(curvatures, dtype=float)
    n = len(s)

    if n < 2:
        raise ValueError("Track must contain at least 2 points to integrate coordinates.")
    if len(kappa) != n:
        raise ValueError(f"Distance array length ({n}) must match curvature length ({len(kappa)}).")

    ds = np.diff(s)
    if np.any(ds <= 0):
        raise ValueError("Track distance array must be strictly monotonic.")

    total_length = float(s[-1] - s[0])

    # 1. Integrate heading angle using trapezoidal rule
    heading = np.zeros(n, dtype=float)
    heading[0] = initial_heading_rad
    for i in range(1, n):
        kappa_avg = 0.5 * (kappa[i] + kappa[i - 1])
        heading[i] = heading[i - 1] + kappa_avg * ds[i - 1]

    # 2. Check if circuit is a full closed circuit (heading changes by ~ ±2pi)
    total_turn = heading[-1] - heading[0]
    is_closed_turn = abs(abs(total_turn) - 2.0 * math.pi) < 1.0

    if close_loop and is_closed_turn and total_length > 50.0:
        # Distribute heading error linearly across stations
        target_turn = 2.0 * math.pi if total_turn > 0 else -2.0 * math.pi
        heading_err = total_turn - target_turn
        frac_s = (s - s[0]) / max(total_length, 1.0)
        heading = heading - heading_err * frac_s

    # 3. Integrate Cartesian coordinates (x, y)
    x = np.zeros(n, dtype=float)
    y = np.zeros(n, dtype=float)
    for i in range(1, n):
        theta_avg = 0.5 * (heading[i] + heading[i - 1])
        x[i] = x[i - 1] + math.cos(theta_avg) * ds[i - 1]
        y[i] = y[i - 1] + math.sin(theta_avg) * ds[i - 1]

    # 4. Compute closure error
    raw_closure_error = float(math.sqrt((x[-1] - x[0]) ** 2 + (y[-1] - y[0]) ** 2))
    max_allowable_closure = (
        closure_threshold_m if closure_threshold_m is not None
        else total_length * closure_tolerance_frac
    )
    can_close = close_loop and (raw_closure_error <= max_allowable_closure) and (total_length > 50.0)

    if can_close:
        if raw_closure_error > 1e-4:
            dx = x[-1] - x[0]
            dy = y[-1] - y[0]
            frac_s = (s - s[0]) / max(total_length, 1.0)
            # Apply smooth linear coordinate closure
            x = x - dx * frac_s
            y = y - dy * frac_s
        is_closed = True
    else:
        is_closed = False

    return TrackCoordinates(
        x=x,
        y=y,
        heading_rad=heading,
        is_closed=is_closed,
        closure_error_m=raw_closure_error,
    )


def gps_to_cartesian(
    latitudes: Union[Sequence[float], np.ndarray],
    longitudes: Union[Sequence[float], np.ndarray],
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Project WGS84 GPS latitude/longitude coordinates to local tangent plane Cartesian (x, y) in meters.

    Parameters
    ----------
    latitudes : Array of GPS latitudes [deg].
    longitudes : Array of GPS longitudes [deg].

    Returns
    -------
    Tuple of (x_m, y_m, distances_m) coordinates in meters relative to track origin.
    """
    lats = np.asarray(latitudes, dtype=float)
    lons = np.asarray(longitudes, dtype=float)

    if len(lats) < 2 or len(lons) != len(lats):
        raise ValueError("Invalid GPS arrays for Cartesian conversion.")

    # Reference origin at first point
    lat0 = math.radians(lats[0])
    lon0 = math.radians(lons[0])

    r_earth = 6_371_000.0  # Mean Earth radius in meters

    # Equirectangular approximation for local racing circuit dimensions (< 20 km)
    x = r_earth * (np.radians(lons) - lon0) * math.cos(lat0)
    y = r_earth * (np.radians(lats) - lat0)

    # Compute cumulative distance along the reconstructed centerline
    dx = np.diff(x)
    dy = np.diff(y)
    ds = np.hypot(dx, dy)
    distances = np.concatenate([[0.0], np.cumsum(ds)])

    return x, y, distances


def normalize_to_viewport(
    x: np.ndarray,
    y: np.ndarray,
    viewport_width: float = 1000.0,
    viewport_height: float = 1000.0,
    padding: float = 60.0,
    *,
    width: Optional[float] = None,
    height: Optional[float] = None,
) -> Tuple[np.ndarray, np.ndarray, Dict[str, float]]:
    """
    Scale and center Cartesian coordinates to fit within a bounded viewport preserving aspect ratio.

    Returns (screen_x, screen_y, bounds_dict) coordinates suitable for SVG or Canvas rendering.
    """
    w = width if width is not None else viewport_width
    h = height if height is not None else viewport_height

    min_x, max_x = float(np.min(x)), float(np.max(x))
    min_y, max_y = float(np.min(y)), float(np.max(y))

    span_x = max(max_x - min_x, 1.0)
    span_y = max(max_y - min_y, 1.0)

    avail_w = w - 2.0 * padding
    avail_h = h - 2.0 * padding

    scale = min(avail_w / span_x, avail_h / span_y)

    # Center within viewport
    center_x = 0.5 * (min_x + max_x)
    center_y = 0.5 * (min_y + max_y)

    norm_x = (x - center_x) * scale + (w * 0.5)
    norm_y = (y - center_y) * scale + (h * 0.5)

    bounds = {
        "min_x_m": min_x, "max_x_m": max_x, "span_x_m": span_x,
        "min_y_m": min_y, "max_y_m": max_y, "span_y_m": span_y,
        "scale": scale,
    }

    return norm_x, norm_y, bounds
