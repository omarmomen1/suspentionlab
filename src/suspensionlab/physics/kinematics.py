"""
physics/kinematics.py
=====================
SuspensionLab PRO — Double-Wishbone Kinematic Solver (Python interface)

Tries to import the compiled C++ extension `kinematics_core` first.
If unavailable, falls back to a pure-Python/NumPy/SciPy implementation that
uses the identical constraint equations and Newton–Raphson logic.

The C++ extension is 100–300× faster and is the production path.
The Python fallback is correct and suitable for development or CI environments
where the C++ build has not been run.

Build the C++ extension:
    cd d:/project/src/kinematics_core
    python build_extension.py

Coordinate system
-----------------
    X : forward  (positive toward front of car)
    Y : outboard (positive away from vehicle centreline)
    Z : up       (positive upward)

Units: hardpoint inputs in mm, angle outputs in degrees, lengths in mm.

References
----------
- Dixon, J.C. "Tires, Suspension and Handling", 2nd Ed., SAE, 1996.
- Milliken, W.F. & Milliken, D.L. "Race Car Vehicle Dynamics", SAE, 1995.
- Blundell, M. & Harty, D. "Multibody Systems Approach to Vehicle Dynamics",
  Elsevier, 2004. Chapter 5: Kinematics of suspension systems.
"""

from __future__ import annotations

import os
import warnings
import math
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

# ── Attempt to import the C++ extension ──────────────────────────────────────
# NOTE: d:\project\src\kinematics_core is on sys.path and resolves as a namespace
# package, so a bare `import kinematics_core` succeeds even before the .pyd is
# compiled.  We therefore verify the compiled KinematicsSolver class exists.
_HAVE_CPP = False
_kc = None

def _try_load_cpp():
    global _HAVE_CPP, _kc, _dll_ctx
    import importlib.util
    import pathlib

    physics_dir = pathlib.Path(__file__).parent

    # On Windows, add the physics directory to the DLL search path so the
    # MinGW runtime DLLs (libgcc, libstdc++, libwinpthread) can be found.
    # Keep the context alive at module level.
    if hasattr(os, "add_dll_directory"):
        try:
            _dll_ctx = os.add_dll_directory(str(physics_dir))
        except (OSError, AttributeError):
            pass

    # Helper: load a .pyd / .so from an explicit path
    def _load_pyd(path: pathlib.Path):
        try:
            spec = importlib.util.spec_from_file_location("kinematics_core", str(path))
            if spec is None:
                return None
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return mod if hasattr(mod, "KinematicsSolver") else None
        except Exception:
            return None

    # 1. Try .pyd / .so in the physics directory (CMake output)
    for pattern in ("kinematics_core*.pyd", "kinematics_core*.so", "kinematics_core*.dylib"):
        for p in physics_dir.glob(pattern):
            mod = _load_pyd(p)
            if mod is not None:
                _kc = mod
                _HAVE_CPP = True
                return

    # 2. Try package-installed version
    try:
        from suspensionlab.physics import kinematics_core as _mod  # type: ignore[import]
        if hasattr(_mod, "KinematicsSolver"):
            _kc = _mod
            _HAVE_CPP = True
            return
    except ImportError:
        pass

    warnings.warn(
        "kinematics_core C++ extension not found. "
        "Using pure-Python fallback (correct but slower). "
        "Build with: python d:/project/src/kinematics_core/build_extension.py",
        ImportWarning,
        stacklevel=3,
    )

_try_load_cpp()


# ─────────────────────────────────────────────────────────────────────────────
# Default hardpoints — right front corner, typical open-wheel Formula car
# Values in mm, coordinate origin near lower-front wishbone pivot.
# ─────────────────────────────────────────────────────────────────────────────

DEFAULT_HARDPOINTS: dict[str, list[float]] = {
    # Upper wishbone inboard pivots (chassis side)
    "UWI_fwd": [-50.0,  80.0, 300.0],
    "UWI_aft": [ 50.0,  80.0, 300.0],
    "UWO":     [  0.0, 650.0, 295.0],   # upper ball joint on upright

    # Lower wishbone inboard pivots
    "LWI_fwd": [-80.0,  80.0, 155.0],
    "LWI_aft": [ 80.0,  80.0, 155.0],
    "LWO":     [  0.0, 720.0, 145.0],   # lower ball joint on upright

    # Tierod (steering)
    "TRI":     [  0.0, 150.0, 220.0],   # inboard (rack)
    "TRO":     [-15.0, 710.0, 205.0],   # outboard (steering arm on upright)

    # Wheel
    "WC":      [  0.0, 760.0, 220.0],   # wheel centre (neutral)
    "CP":      [  0.0, 760.0,   0.0],   # contact patch (ground plane)

    # Pushrod / spring-damper attachment
    "PRI":     [-20.0, 300.0, 390.0],   # inboard rocker pivot (chassis)
    "PRO":     [-15.0, 690.0, 250.0],   # outboard attachment on upright
}


# ─────────────────────────────────────────────────────────────────────────────
# Output dataclass (mirrors C++ KinematicPoint)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class KinematicPoint:
    wheel_travel_mm:       float = 0.0
    camber_deg:            float = 0.0
    toe_deg:               float = 0.0
    caster_deg:            float = 0.0
    kpi_deg:               float = 0.0
    track_change_mm:       float = 0.0
    wheelbase_change_mm:   float = 0.0
    roll_center_height_mm: float = 0.0
    motion_ratio:          float = 0.0
    scrub_radius_mm:       float = 0.0
    converged:             bool  = False


@dataclass
class KinematicsCurves:
    points: list[KinematicPoint] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to dict of lists — compatible with JSON serialisation."""
        keys = [
            "wheel_travel_mm", "camber_deg", "toe_deg", "caster_deg",
            "kpi_deg", "track_change_mm", "wheelbase_change_mm",
            "roll_center_height_mm", "motion_ratio", "scrub_radius_mm",
            "converged",
        ]
        out: dict[str, list] = {k: [] for k in keys}
        for pt in self.points:
            for k in keys:
                out[k].append(getattr(pt, k))
        return out


# ─────────────────────────────────────────────────────────────────────────────
# Pure-Python fallback solver (identical math, slower)
# ─────────────────────────────────────────────────────────────────────────────

def _rotation(phi_x: float, phi_y: float, phi_z: float) -> np.ndarray:
    """Build 3×3 rotation matrix R = Rz(φz)·Ry(φy)·Rx(φx)."""
    cx, sx = math.cos(phi_x), math.sin(phi_x)
    cy, sy = math.cos(phi_y), math.sin(phi_y)
    cz, sz = math.cos(phi_z), math.sin(phi_z)
    return np.array([
        [ cy*cz,  cz*sx*sy - cx*sz,  cx*cz*sy + sx*sz],
        [ cy*sz,  cx*cz + sx*sy*sz, -cz*sx + cx*sy*sz],
        [-sy,     cy*sx,             cx*cy            ],
    ], dtype=float)


def _residual_py(x: np.ndarray, z_WC: float, hp: dict) -> np.ndarray:
    """5-element residual F(x) for the double-wishbone constraints."""
    x_WC, y_WC, phi_x, phi_y, phi_z = x
    R = _rotation(phi_x, phi_y, phi_z)
    r_WC = np.array([x_WC, y_WC, z_WC])

    uwo = r_WC + R @ hp["d_UWO"]
    lwo = r_WC + R @ hp["d_LWO"]
    tro = r_WC + R @ hp["d_TRO"]

    def sqdist(a: np.ndarray, b: np.ndarray) -> float:
        d = a - b
        return float(d @ d)

    return np.array([
        sqdist(uwo, hp["UWI_fwd"]) - hp["L_UWO_fwd_sq"],
        sqdist(uwo, hp["UWI_aft"]) - hp["L_UWO_aft_sq"],
        sqdist(lwo, hp["LWI_fwd"]) - hp["L_LWO_fwd_sq"],
        sqdist(lwo, hp["LWI_aft"]) - hp["L_LWO_aft_sq"],
        sqdist(tro, hp["TRI"]    ) - hp["L_TRO_sq"],
    ], dtype=float)


def _jacobian_py(x: np.ndarray, z_WC: float, hp: dict) -> np.ndarray:
    """5×5 numerical Jacobian via central finite differences."""
    H = np.array([1e-4, 1e-4, 1e-6, 1e-6, 1e-6])
    J = np.zeros((5, 5))
    for j in range(5):
        xp, xm = x.copy(), x.copy()
        xp[j] += H[j]
        xm[j] -= H[j]
        J[:, j] = (_residual_py(xp, z_WC, hp) - _residual_py(xm, z_WC, hp)) / (2.0 * H[j])
    return J


def _newton_py(x: np.ndarray, z_WC: float, hp: dict) -> tuple[np.ndarray, bool]:
    """Newton–Raphson with 60 iterations maximum."""
    x = x.copy()
    for _ in range(60):
        F = _residual_py(x, z_WC, hp)
        if np.dot(F, F) < 1e-8:
            return x, True
        J = _jacobian_py(x, z_WC, hp)
        try:
            dx = np.linalg.solve(J, -F)
        except np.linalg.LinAlgError:
            break
        x += dx
        if np.dot(dx, dx) < 1e-24:
            return x, True
    return x, np.dot(_residual_py(x, z_WC, hp), _residual_py(x, z_WC, hp)) < 1e-8


def _pushrod_len_py(x: np.ndarray, z_WC: float, hp: dict) -> float:
    x_WC, y_WC, phi_x, phi_y, phi_z = x
    R = _rotation(phi_x, phi_y, phi_z)
    pro = np.array([x_WC, y_WC, z_WC]) + R @ hp["d_PRO"]
    d = pro - hp["PRI"]
    return float(math.sqrt(d @ d))


def _roll_center_py(x: np.ndarray, z_WC: float, hp: dict) -> float:
    x_WC, y_WC, phi_x, phi_y, phi_z = x
    R = _rotation(phi_x, phi_y, phi_z)
    r = np.array([x_WC, y_WC, z_WC])

    uwo = r + R @ hp["d_UWO"]
    lwo = r + R @ hp["d_LWO"]
    cp  = r + R @ hp["d_CP"]

    lwi_mid = 0.5 * (hp["LWI_fwd"] + hp["LWI_aft"])
    uwi_mid = 0.5 * (hp["UWI_fwd"] + hp["UWI_aft"])

    # Y–Z plane (indices 1, 2)
    p1y, p1z = lwi_mid[1], lwi_mid[2]
    d1y, d1z = lwo[1] - p1y, lwo[2] - p1z
    p2y, p2z = uwi_mid[1], uwi_mid[2]
    d2y, d2z = uwo[1] - p2y, uwo[2] - p2z

    det = d1y * (-d2z) - d1z * (-d2y)
    if abs(det) < 1e-6:
        return 0.0

    rhs_y = p2y - p1y
    rhs_z = p2z - p1z
    t1 = (rhs_y * (-d2z) - rhs_z * (-d2y)) / det

    ic_y = p1y + t1 * d1y
    ic_z = p1z + t1 * d1z

    cp_y = cp[1]
    denom = ic_y - cp_y
    if abs(denom) < 1e-6:
        return ic_z
    return -cp_y * ic_z / denom


def _scrub_py(x: np.ndarray, z_WC: float, hp: dict) -> float:
    x_WC, y_WC, phi_x, phi_y, phi_z = x
    R = _rotation(phi_x, phi_y, phi_z)
    r = np.array([x_WC, y_WC, z_WC])

    uwo = r + R @ hp["d_UWO"]
    lwo = r + R @ hp["d_LWO"]
    cp  = r + R @ hp["d_CP"]

    kp = uwo - lwo
    kp_n = kp / (np.linalg.norm(kp) + 1e-12)
    if abs(kp_n[2]) < 1e-9:
        return 0.0
    t = -lwo[2] / kp_n[2]
    sa_y = lwo[1] + t * kp_n[1]
    return float(cp[1] - sa_y)


def _extract_py(x: np.ndarray, dz_mm: float, z_WC: float,
                hp: dict, prev_pr: float, dz_step: float, ok: bool) -> KinematicPoint:
    """Extract all kinematic outputs from a solved state vector."""
    x_WC, y_WC, phi_x, phi_y, phi_z = x
    R = _rotation(phi_x, phi_y, phi_z)
    r = np.array([x_WC, y_WC, z_WC])

    # Spin axis = second column of R
    spin = R[:, 1]
    camber_deg = math.degrees(math.atan2(spin[2], spin[1]))
    toe_deg    = math.degrees(math.atan2(spin[0], spin[1]))

    # Kingpin axis
    uwo = r + R @ hp["d_UWO"]
    lwo = r + R @ hp["d_LWO"]
    kp  = (uwo - lwo) / (np.linalg.norm(uwo - lwo) + 1e-12)
    kpi_deg    = math.degrees(math.atan2(kp[1], kp[2]))
    caster_deg = math.degrees(math.atan2(-kp[0], kp[2]))

    track_change     = y_WC - hp["WC0"][1]
    wheelbase_change = x_WC - hp["WC0"][0]
    rc_height  = _roll_center_py(x, z_WC, hp)
    scrub      = _scrub_py(x, z_WC, hp)

    # Motion ratio
    pr_len = _pushrod_len_py(x, z_WC, hp)
    mr = abs((pr_len - prev_pr) / dz_step) if abs(dz_step) > 1e-9 and prev_pr >= 0 else 0.0

    return KinematicPoint(
        wheel_travel_mm       = dz_mm,
        camber_deg            = camber_deg,
        toe_deg               = toe_deg,
        caster_deg            = caster_deg,
        kpi_deg               = kpi_deg,
        track_change_mm       = track_change,
        wheelbase_change_mm   = wheelbase_change,
        roll_center_height_mm = rc_height,
        motion_ratio          = mr,
        scrub_radius_mm       = scrub,
        converged             = ok,
    )


def _solve_py(hp_raw: dict, z_min: float, z_max: float, n: int) -> KinematicsCurves:
    """Pure-Python sweep solver."""
    WC0 = np.array(hp_raw["WC"])
    hp = {
        "WC0":        WC0,
        "UWI_fwd":    np.array(hp_raw["UWI_fwd"]),
        "UWI_aft":    np.array(hp_raw["UWI_aft"]),
        "LWI_fwd":    np.array(hp_raw["LWI_fwd"]),
        "LWI_aft":    np.array(hp_raw["LWI_aft"]),
        "TRI":         np.array(hp_raw["TRI"]),
        "PRI":         np.array(hp_raw["PRI"]),
        "d_UWO":       np.array(hp_raw["UWO"]) - WC0,
        "d_LWO":       np.array(hp_raw["LWO"]) - WC0,
        "d_TRO":       np.array(hp_raw["TRO"]) - WC0,
        "d_CP":        np.array(hp_raw["CP"])  - WC0,
        "d_PRO":       np.array(hp_raw["PRO"]) - WC0,
        "L_UWO_fwd_sq": float(np.sum((np.array(hp_raw["UWO"]) - np.array(hp_raw["UWI_fwd"]))**2)),
        "L_UWO_aft_sq": float(np.sum((np.array(hp_raw["UWO"]) - np.array(hp_raw["UWI_aft"]))**2)),
        "L_LWO_fwd_sq": float(np.sum((np.array(hp_raw["LWO"]) - np.array(hp_raw["LWI_fwd"]))**2)),
        "L_LWO_aft_sq": float(np.sum((np.array(hp_raw["LWO"]) - np.array(hp_raw["LWI_aft"]))**2)),
        "L_TRO_sq":     float(np.sum((np.array(hp_raw["TRO"]) - np.array(hp_raw["TRI"]))**2)),
    }

    dz_step = (z_max - z_min) / max(n - 1, 1)
    # Warm-up: march from neutral to z_min
    x = np.array([WC0[0], WC0[1], 0.0, 0.0, 0.0])
    wsteps = max(5, n // 4)
    for i in range(wsteps):
        z_WC = WC0[2] + z_min * (i + 1) / wsteps
        x, _ = _newton_py(x, z_WC, hp)

    prev_pr = _pushrod_len_py(x, WC0[2] + z_min, hp)

    curves = KinematicsCurves()
    for i in range(n):
        dz   = z_min + i * dz_step
        z_WC = WC0[2] + dz
        x, ok = _newton_py(x, z_WC, hp)
        pt = _extract_py(x, dz, z_WC, hp, prev_pr, dz_step, ok)
        pr_new = _pushrod_len_py(x, z_WC, hp)
        prev_pr = pr_new
        curves.points.append(pt)

    return curves


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def solve_kinematics(
    hardpoints: dict,
    z_min_mm: float = -80.0,
    z_max_mm: float =  80.0,
    n_steps:  int   = 33,
) -> KinematicsCurves:
    """
    Solve double-wishbone corner kinematics over a wheel-travel sweep.

    Parameters
    ----------
    hardpoints : dict
        Dictionary with keys: UWI_fwd, UWI_aft, UWO, LWI_fwd, LWI_aft, LWO,
        TRI, TRO, WC, CP, PRI, PRO.  Each value is [x, y, z] in mm.
    z_min_mm   : float  Droop limit (negative)  [mm]
    z_max_mm   : float  Bump limit  (positive)   [mm]
    n_steps    : int    Number of steps          (default 33)

    Returns
    -------
    KinematicsCurves
        Use .to_dict() to get JSON-serialisable dict of lists.
    """
    if _HAVE_CPP:
        hp = _kc.HardpointSet.from_dict(hardpoints)
        solver = _kc.KinematicsSolver(hp)
        cpp_curves = solver.solve(z_min_mm, z_max_mm, n_steps)
        d = cpp_curves.to_dict()

        # Convert C++ output to Python KinematicsCurves
        curves = KinematicsCurves()
        n = len(d["wheel_travel_mm"])
        for i in range(n):
            curves.points.append(KinematicPoint(
                wheel_travel_mm       = d["wheel_travel_mm"][i],
                camber_deg            = d["camber_deg"][i],
                toe_deg               = d["toe_deg"][i],
                caster_deg            = d["caster_deg"][i],
                kpi_deg               = d["kpi_deg"][i],
                track_change_mm       = d["track_change_mm"][i],
                wheelbase_change_mm   = d["wheelbase_change_mm"][i],
                roll_center_height_mm = d["roll_center_height_mm"][i],
                motion_ratio          = d["motion_ratio"][i],
                scrub_radius_mm       = d["scrub_radius_mm"][i],
                converged             = d["converged"][i],
            ))
        return curves
    else:
        return _solve_py(hardpoints, z_min_mm, z_max_mm, n_steps)


def backend_info() -> dict:
    """Return information about which backend is active."""
    return {
        "backend": "C++ (kinematics_core)" if _HAVE_CPP else "Python (scipy fallback)",
        "cpp_available": _HAVE_CPP,
        "default_hardpoints": DEFAULT_HARDPOINTS,
    }
