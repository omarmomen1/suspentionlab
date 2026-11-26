"""B-01 Quarter-car eigenanalysis.

Compares the production solver eigenvalues (compute_modal_properties) with the
exact roots of the coupled 2-DOF characteristic polynomial. The uncoupled
sqrt(k_w/m_s)/2pi estimate ignores tire stiffness and unsprung mass; it is
documented here as an approximation, not as the exact 2-DOF answer.
"""
import math

import numpy as np
import pytest

from suspensionlab.physics.quarter_car import QuarterCarParams, compute_modal_properties

TOL_PCT = 0.5


def _exact_coupled_modes(p):
    ms, mu, kw, cw, kt, ct = p.m_s, p.m_u, p.k_w, p.c_w, p.k_t, p.c_t
    # det(sI - A) = (ms s^2 + cw s + kw)(mu s^2 + (cw+ct) s + kw+kt) - (cw s + kw)^2
    a = np.polynomial.Polynomial([kw, cw, ms])
    b = np.polynomial.Polynomial([kw + kt, cw + ct, mu])
    g = np.polynomial.Polynomial([kw, cw])
    roots = (a * b - g * g).roots()
    cplx = sorted([r for r in roots if r.imag > 1e-6], key=lambda r: abs(r))
    return [(abs(r) / (2 * math.pi), float(-r.real / abs(r))) for r in cplx]


def test_b01_solver_matches_exact_coupled_characteristic_roots(record):
    p = QuarterCarParams()
    m = compute_modal_properties(p)
    (f_body, z_body), (f_hop, z_hop) = _exact_coupled_modes(p)
    d_body = abs(m["f_n_s"] - f_body) / f_body * 100
    d_hop = abs(m["f_n_u"] - f_hop) / f_hop * 100
    uncoupled = math.sqrt(p.k_w / p.m_s) / (2 * math.pi)
    record(
        name="Quarter-car eigenanalysis",
        measured={
            "solver_body_hz": round(m["f_n_s"], 4),
            "exact_coupled_body_hz": round(f_body, 4),
            "solver_hop_hz": round(m["f_n_u"], 3),
            "exact_coupled_hop_hz": round(f_hop, 3),
            "body_delta_pct": round(d_body, 5),
            "hop_delta_pct": round(d_hop, 5),
            "uncoupled_sqrt_kw_over_ms_hz": round(uncoupled, 4),
        },
        tolerance={"coupled_delta_pct": TOL_PCT},
        reference="Roots of the coupled 2-DOF characteristic polynomial (exact). Uncoupled "
                  "sqrt(k_w/m_s)/2pi is an approximation that neglects tire stiffness and unsprung mass.",
    )
    assert d_body < TOL_PCT and d_hop < TOL_PCT
    # The approximation is reported, never passed off as exact.
    assert uncoupled == pytest.approx(1.235, abs=0.001)
    assert abs(uncoupled - f_body) > 1e-3  # coupled and uncoupled genuinely differ
