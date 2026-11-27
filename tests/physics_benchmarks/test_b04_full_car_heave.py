"""B-04 Full-car heave mode on a symmetric car.

With four identical corners and a symmetric layout, pure heave reduces exactly
to a quarter car carrying m_s/4. The solver's heave eigenvalue must match the
exact coupled quarter-car roots, and the heave eigenvector must carry ~0 pitch
and roll (symmetry).
"""
import math

import numpy as np
import pytest

from suspensionlab.physics.full_car import FullCarParams, build_full_car_state_space

TOL_PCT = 0.5
SYM_TOL = 1e-6


def _params():
    return FullCarParams(
        m_s=1200.0, I_x=380.0, I_y=1500.0, m_uf=40.0, m_ur=40.0,
        k_sf=35000.0, k_sr=35000.0, c_f=2200.0, c_r=2200.0,
        k_arb_f=8500.0, k_arb_r=8500.0, k_tf=220000.0, k_tr=220000.0,
        L=2.6, a=1.3, b=1.3, tw_f=1.55, tw_r=1.55, speed_mps=20.0,
    )


def test_b04_symmetric_heave_mode_matches_hand_calculation(record):
    p = _params()
    A = build_full_car_state_space(p)[0]
    vals, vecs = np.linalg.eig(A)
    # Heave mode = oscillatory eigenvector whose body part is dominated by z_s.
    best = None
    for i, v in enumerate(vals):
        if v.imag <= 1e-3:
            continue
        body = np.abs(vecs[:3, i])
        scaled = body * np.array([1.0, p.L / 2.0, (p.tw_f + p.tw_r) / 4.0])
        if int(np.argmax(scaled)) != 0:
            continue
        if best is None or abs(v) < abs(vals[best]):
            best = i
    assert best is not None
    f_solver = abs(vals[best]) / (2 * math.pi)

    # Hand calculation: quarter car with m_s/4 per corner.
    kw, cw = p.k_sf * p.MR_f ** 2, p.c_f * p.MR_f ** 2
    ms, mu, kt = p.m_s / 4.0, p.m_uf, p.k_tf
    a = np.polynomial.Polynomial([kw, cw, ms])
    b = np.polynomial.Polynomial([kw + kt, cw, mu])
    g = np.polynomial.Polynomial([kw, cw])
    roots = (a * b - g * g).roots()
    f_exact = min(abs(r) for r in roots if r.imag > 1e-6) / (2 * math.pi)
    delta = abs(f_solver - f_exact) / f_exact * 100

    v = vecs[:3, best]
    ref = abs(v[0])
    pitch_ratio = float(abs(v[1]) * p.L / 2 / ref)
    roll_ratio = float(abs(v[2]) * p.tw_f / 2 / ref)
    record(
        name="Full-car heave mode (symmetric)",
        measured={"solver_heave_hz": round(f_solver, 4), "hand_calc_heave_hz": round(f_exact, 4),
                  "delta_pct": round(delta, 5), "pitch_leakage": pitch_ratio, "roll_leakage": roll_ratio},
        tolerance={"delta_pct": TOL_PCT, "symmetry_leakage": SYM_TOL},
        reference="Symmetric 4-corner heave equals a quarter car carrying m_s/4 (exact).",
    )
    assert delta < TOL_PCT
    assert pitch_ratio < SYM_TOL and roll_ratio < SYM_TOL
