"""
physics/damper_model.py
=======================
SuspensionLab PRO — Structured Damper Model

Provides a physically validated damper model with:
- Separate compression and rebound curves
- Monotonicity validation
- Extrapolation policy (clamp by default)
- Linearisation for frequency-domain analysis
- Vectorised force evaluation for time-domain integration

Sign Convention
---------------
    v > 0  : compression (damper shortening, wheel moving toward body)
    F > 0  : compression force (resists shortening)
    v < 0  : rebound (damper extending)
    F < 0  : rebound force (resists extension)

References
----------
- Dixon, J.C. "The Shock Absorber Handbook", 2nd Ed., Wiley-SAE.
- Milliken, W.F. & Milliken, D.L. "Race Car Vehicle Dynamics", SAE.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from typing import Literal
import numpy as np


# ─────────────────────────────────────────────────────────────────────────────
# DamperCurve — validated single-direction table
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class DamperCurve:
    """A validated velocity-force table for one direction of damper motion.

    Attributes
    ----------
    velocities : np.ndarray
        Damper velocities [m/s]. Must be monotonically increasing.
        Compression curve: all values >= 0.
        Rebound curve: all values <= 0 (use negative velocities).
    forces : np.ndarray
        Damper forces [N]. Must be monotonically increasing in magnitude
        (i.e. more force for more velocity). Compression: F >= 0. Rebound: F <= 0.
    direction : {'compression', 'rebound', 'both'}
        Direction this curve covers.
    extrapolation : {'clamp', 'linear'}
        Policy when queried outside table range. Default: 'clamp' (safest).
    """
    velocities: np.ndarray
    forces: np.ndarray
    direction: Literal["compression", "rebound", "both"] = "both"
    extrapolation: Literal["clamp", "linear"] = "clamp"

    def __post_init__(self) -> None:
        self.velocities = np.asarray(self.velocities, dtype=float)
        self.forces     = np.asarray(self.forces, dtype=float)
        self._validate()

    def _validate(self) -> None:
        """Validate curve integrity."""
        if len(self.velocities) < 2:
            raise ValueError(
                f"DamperCurve '{self.direction}' must have at least 2 data points, "
                f"got {len(self.velocities)}."
            )
        if len(self.velocities) != len(self.forces):
            raise ValueError(
                f"DamperCurve '{self.direction}': velocities and forces arrays must "
                f"have the same length. Got {len(self.velocities)} velocities and "
                f"{len(self.forces)} forces."
            )
        # Check velocity monotonicity
        diffs = np.diff(self.velocities)
        if not np.all(diffs > 0):
            raise ValueError(
                f"DamperCurve '{self.direction}': velocity array must be strictly "
                f"monotonically increasing. Found non-increasing step at indices: "
                f"{np.where(diffs <= 0)[0].tolist()}."
            )
        # Check force monotonicity: |F| should increase with |v|.
        # Sort by |v| first so rebound curves (negative v) are handled correctly.
        abs_v_order = np.argsort(np.abs(self.velocities))
        force_sorted_by_absv = np.abs(self.forces[abs_v_order])
        force_diffs = np.diff(force_sorted_by_absv)
        if not np.all(force_diffs >= 0):
            n_violations = int(np.sum(force_diffs < 0))
            warnings.warn(
                f"DamperCurve '{self.direction}': force magnitude is not monotonically "
                f"increasing with velocity magnitude at {n_violations} point(s). "
                f"This may indicate measurement noise or a non-physical curve. "
                f"Results may be inaccurate.",
                UserWarning,
                stacklevel=2,
            )
        # Direction-specific checks
        if self.direction == "compression" and np.any(self.velocities < 0):
            raise ValueError(
                "DamperCurve 'compression': velocity array must be >= 0. "
                "Use direction='rebound' for negative velocities."
            )
        if self.direction == "rebound" and np.any(self.velocities > 0):
            raise ValueError(
                "DamperCurve 'rebound': velocity array must be <= 0. "
                "Use direction='compression' for positive velocities."
            )

    def evaluate(self, v: float | np.ndarray) -> float | np.ndarray:
        """Evaluate damper force at velocity v [m/s].

        Parameters
        ----------
        v : float or np.ndarray
            Damper velocity [m/s].

        Returns
        -------
        F : float or np.ndarray
            Damper force [N].
        """
        scalar = np.ndim(v) == 0
        v_arr = np.atleast_1d(np.asarray(v, dtype=float))

        if self.extrapolation == "clamp":
            v_q = np.clip(v_arr, self.velocities[0], self.velocities[-1])
            F = np.interp(v_q, self.velocities, self.forces)
        else:  # linear extrapolation
            F = np.interp(v_arr, self.velocities, self.forces,
                          left=None, right=None)
            # np.interp clamps by default; for linear we extend the end slopes
            lo_slope = (self.forces[1]  - self.forces[0])  / max(self.velocities[1]  - self.velocities[0],  1e-12)
            hi_slope = (self.forces[-1] - self.forces[-2]) / max(self.velocities[-1] - self.velocities[-2], 1e-12)
            low_mask  = v_arr < self.velocities[0]
            high_mask = v_arr > self.velocities[-1]
            F[low_mask]  = self.forces[0]  + lo_slope * (v_arr[low_mask]  - self.velocities[0])
            F[high_mask] = self.forces[-1] + hi_slope * (v_arr[high_mask] - self.velocities[-1])

        return float(F[0]) if scalar else F


# ─────────────────────────────────────────────────────────────────────────────
# BiDirectionalDamper — pairs compression + rebound
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class BiDirectionalDamper:
    """A complete damper model with separate compression and rebound curves.

    This is the preferred representation for production use. Provides:
    - Physically distinct compression/rebound characteristics
    - Frequency-domain linearisation at an operating RMS velocity
    - Consistent evaluation interface for both time and frequency domains

    Attributes
    ----------
    compression : DamperCurve
        Curve for v > 0 (compression). velocities must be >= 0.
    rebound : DamperCurve
        Curve for v < 0 (rebound). velocities must be <= 0.
    name : str, optional
        Human-readable damper identifier (e.g. 'Ohlins TTX36 - Setup A').
    """
    compression: DamperCurve
    rebound:     DamperCurve
    name:        str = "unnamed"

    def __post_init__(self) -> None:
        if self.compression.direction not in ("compression", "both"):
            raise ValueError("BiDirectionalDamper.compression must have direction='compression' or 'both'.")
        if self.rebound.direction not in ("rebound", "both"):
            raise ValueError("BiDirectionalDamper.rebound must have direction='rebound' or 'both'.")

    def force(self, v: float | np.ndarray) -> float | np.ndarray:
        """Evaluate damper force [N] at damper velocity v [m/s].

        Automatically routes to compression or rebound curve based on sign of v.
        At v == 0, returns 0 (no force).

        Parameters
        ----------
        v : float or np.ndarray

        Returns
        -------
        F : float or np.ndarray  [N]
        """
        scalar = np.ndim(v) == 0
        v_arr = np.atleast_1d(np.asarray(v, dtype=float))
        F = np.zeros_like(v_arr)

        comp_mask = v_arr > 0
        reb_mask  = v_arr < 0

        if np.any(comp_mask):
            F[comp_mask] = self.compression.evaluate(v_arr[comp_mask])
        if np.any(reb_mask):
            F[reb_mask]  = self.rebound.evaluate(v_arr[reb_mask])

        return float(F[0]) if scalar else F

    def linearise(self, v_rms: float = 0.05) -> tuple[float, str]:
        """Compute equivalent linearised damping coefficient c_eff [Ns/m].

        Uses energy-equivalence linearisation: c_eff is chosen such that
        the energy dissipated per cycle by the linear damper equals that of
        the nonlinear curve over a sinusoidal excitation at amplitude v_rms.

        This is the standard technique described in Dixon (2007) Ch. 9.

        Parameters
        ----------
        v_rms : float
            RMS damper velocity for the operating condition [m/s].
            Default 0.05 m/s (typical road-speed range).
            Set to the computed RMS from a prior time-domain run for best accuracy.

        Returns
        -------
        c_eff : float
            Equivalent linearised damping coefficient [Ns/m].
        note : str
            Human-readable description of the linearisation applied.
        """
        v_rms = max(float(v_rms), 1e-6)
        # Sample the curve at many points over one sinusoidal cycle
        N = 512
        theta = np.linspace(0, 2 * np.pi, N, endpoint=False)
        v_peak = v_rms * np.sqrt(2)  # peak of sinusoid with given RMS
        v_cycle = v_peak * np.sin(theta)
        F_cycle = self.force(v_cycle)

        # Energy dissipated by the nonlinear damper per cycle, computed by
        # PHASE integration:  W = integral_0^2pi  F(v(theta)) * v(theta) d(theta) / omega.
        #
        # NOTE (Wave 5A fix): the previous implementation integrated
        # np.trapezoid(F_cycle, v_cycle), i.e. the closed-loop integral
        # contour F(v) dv, which is identically zero for any single-valued
        # damper characteristic F(v). That collapsed c_eff to ~0 and spiked
        # Quarter-Car Bode Peak TX (measured 687.24 in production testing).
        #
        # Energy per cycle is E = (1/omega) * integral F(v(t)) * v(t) dt-phase.
        # Since the 1/omega factor cancels against the linear reference below,
        # we integrate W_nl = integral_0^2pi F(v(theta)) * v(theta) d(theta):
        try:
            W_nl = np.trapezoid(F_cycle * v_cycle, theta)  # NumPy >= 2.0
        except AttributeError:
            W_nl = np.trapz(F_cycle * v_cycle, theta)       # NumPy < 2.0 fallback

        # A linear damper F = c*v dissipates W_linear = c * pi * v_peak^2 per
        # cycle (integral_0^2pi c*v_peak^2*sin^2(theta) d(theta) = c*pi*v_peak^2).
        # Energy-equivalence: c_eff = W_nl / (pi * v_peak^2).
        #   c_eff = [ integral_0^2pi F(v(theta)) v(theta) d(theta) ] / (pi * v_peak^2)
        c_eff_denom = np.pi * v_peak ** 2
        c_eff = float(W_nl / c_eff_denom) if abs(c_eff_denom) > 1e-12 else 0.0
        c_eff = max(c_eff, 0.0)  # clamp to physical range

        note = (
            f"Frequency-domain uses linearised damping c_eff={c_eff:.1f} Ns/m "
            f"(energy-equivalence linearisation at v_rms={v_rms:.4f} m/s). "
            f"Time-domain uses the full nonlinear curve '{self.name}'. "
            f"Results may differ at large amplitudes."
        )
        return c_eff, note


# ─────────────────────────────────────────────────────────────────────────────
# Utility: build from QuarterCarParams legacy arrays
# ─────────────────────────────────────────────────────────────────────────────

def build_damper_from_params(
    damper_curve_v_comp=None,
    damper_curve_f_comp=None,
    damper_curve_v_reb=None,
    damper_curve_f_reb=None,
    damper_curve_v=None,
    damper_curve_f=None,
    name: str = "custom",
) -> BiDirectionalDamper | None:
    """Construct a BiDirectionalDamper from QuarterCarParams legacy arrays.

    Returns None if no valid curve data is provided.

    Parameters
    ----------
    damper_curve_v_comp : list[float] | None  Compression velocities [m/s] (>= 0)
    damper_curve_f_comp : list[float] | None  Compression forces [N]
    damper_curve_v_reb  : list[float] | None  Rebound velocities [m/s] (<= 0)
    damper_curve_f_reb  : list[float] | None  Rebound forces [N]
    damper_curve_v      : list[float] | None  Unified velocity table (both directions)
    damper_curve_f      : list[float] | None  Unified force table
    name                : str

    Returns
    -------
    BiDirectionalDamper or None
    """
    has_split  = (damper_curve_v_comp is not None and damper_curve_f_comp is not None
                  and damper_curve_v_reb is not None and damper_curve_f_reb is not None
                  and len(damper_curve_v_comp) >= 2 and len(damper_curve_v_reb) >= 2)
    has_unified = (damper_curve_v is not None and damper_curve_f is not None
                   and len(damper_curve_v) >= 2)

    if has_split:
        comp_v = np.asarray(damper_curve_v_comp, dtype=float)
        comp_f = np.asarray(damper_curve_f_comp, dtype=float)
        reb_v  = np.asarray(damper_curve_v_reb,  dtype=float)
        reb_f  = np.asarray(damper_curve_f_reb,  dtype=float)
        # Ensure compression velocities are positive and rebound are negative
        comp_v = np.abs(comp_v)
        reb_v  = -np.abs(reb_v)
        # Sort
        comp_sort = np.argsort(comp_v)
        reb_sort  = np.argsort(reb_v)
        comp_curve = DamperCurve(comp_v[comp_sort], comp_f[comp_sort], direction="compression")
        reb_curve  = DamperCurve(reb_v[reb_sort],  reb_f[reb_sort],   direction="rebound")
        return BiDirectionalDamper(comp_curve, reb_curve, name=name)

    elif has_unified:
        v_all = np.asarray(damper_curve_v, dtype=float)
        f_all = np.asarray(damper_curve_f, dtype=float)
        sort  = np.argsort(v_all)
        v_all = v_all[sort]
        f_all = f_all[sort]

        # Split at v=0
        comp_mask = v_all >= 0
        reb_mask  = v_all <= 0

        if np.sum(comp_mask) < 2 or np.sum(reb_mask) < 2:
            # If only one side has enough points, build a symmetric model
            warnings.warn(
                "Unified damper curve has insufficient points on one side. "
                "Mirroring the available data for the missing direction.",
                UserWarning, stacklevel=2,
            )
            v_pos = np.abs(v_all)
            sort2 = np.argsort(v_pos)
            v_pos = v_pos[sort2]
            f_pos = np.abs(f_all[sort2])
            if v_pos[0] != 0:
                v_pos = np.concatenate([[0.0], v_pos])
                f_pos = np.concatenate([[0.0], f_pos])
            comp_curve = DamperCurve(v_pos, f_pos, direction="compression")
            reb_curve  = DamperCurve(-v_pos[::-1], -f_pos[::-1], direction="rebound")
        else:
            v_comp = v_all[comp_mask]
            f_comp = f_all[comp_mask]
            v_reb  = v_all[reb_mask]
            f_reb  = f_all[reb_mask]
            if v_comp[0] != 0:
                v_comp = np.concatenate([[0.0], v_comp])
                f_comp = np.concatenate([[0.0], f_comp])
            if v_reb[-1] != 0:
                v_reb = np.concatenate([v_reb, [0.0]])
                f_reb = np.concatenate([f_reb, [0.0]])
            comp_curve = DamperCurve(v_comp, f_comp, direction="compression")
            reb_curve  = DamperCurve(v_reb,  f_reb,  direction="rebound")

        return BiDirectionalDamper(comp_curve, reb_curve, name=name)

    return None  # No valid curve data


def linearise_damper_from_params(
    p,  # QuarterCarParams
    v_rms: float = 0.05,
) -> tuple[float, str]:
    """Convenience wrapper: build a BiDirectionalDamper from QuarterCarParams and linearise it.

    Returns
    -------
    c_eff : float  Linearised damping coefficient at wheel [Ns/m]
    note  : str    Description of linearisation
    """
    damper = build_damper_from_params(
        damper_curve_v_comp=p.damper_curve_v_comp,
        damper_curve_f_comp=p.damper_curve_f_comp,
        damper_curve_v_reb=p.damper_curve_v_reb,
        damper_curve_f_reb=p.damper_curve_f_reb,
        damper_curve_v=p.damper_curve_v,
        damper_curve_f=p.damper_curve_f,
    )
    if damper is None:
        return p.c_w, "Linear damper model (constant c_w). Frequency and time domains are consistent."

    c_eff_spring, note = damper.linearise(v_rms=v_rms)
    # Scale: the BiDirectionalDamper force is at the damper body;
    # refer to wheel centre by multiplying by MR**2
    c_eff_wheel = c_eff_spring * (p.MR ** 2)
    note = note.replace(f"c_eff={c_eff_spring:.1f}", f"c_eff={c_eff_wheel:.1f}")
    return c_eff_wheel, note
