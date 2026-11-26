"""B-02 Damper cycle energy via Wave 5A's phase integral.

linearise() must return c_eff = c for a linear damper and (c_c + c_r)/2 for a
bilinear (different compression and rebound slopes) damper.
"""
import pytest

from suspensionlab.physics.damper_model import BiDirectionalDamper, DamperCurve

TOL_REL = 1e-3


def _damper(c_comp, c_reb, vmax=2.0):
    comp = DamperCurve(velocities=[0.0, vmax], forces=[0.0, c_comp * vmax], direction="compression")
    reb = DamperCurve(velocities=[-vmax, 0.0], forces=[-c_reb * vmax, 0.0], direction="rebound")
    return BiDirectionalDamper(compression=comp, rebound=reb, name="benchmark")


def test_b02_linear_damper_c_eff_equals_c(record):
    c = 2000.0
    c_eff, _ = _damper(c, c).linearise(v_rms=0.05)
    err = abs(c_eff - c) / c
    record(name="Damper cycle energy, linear", measured={"c_eff": round(c_eff, 4), "c": c, "rel_err": err},
           tolerance={"rel": TOL_REL}, reference="Exact: W = c*pi*v_peak^2 per cycle")
    assert err < TOL_REL


def test_b02_bilinear_damper_c_eff_is_mean_of_slopes(record):
    c_c, c_r = 1500.0, 3000.0
    c_eff, _ = _damper(c_c, c_r).linearise(v_rms=0.05)
    expected = (c_c + c_r) / 2
    err = abs(c_eff - expected) / expected
    record(name="Damper cycle energy, bilinear",
           measured={"c_eff": round(c_eff, 4), "expected_mean": expected, "rel_err": err},
           tolerance={"rel": TOL_REL}, reference="Exact: (c_c + c_r)/2 from the half-cycle energy split")
    assert err < TOL_REL
    # Wave 5A regression guard: the old contour integral collapsed c_eff to ~0.
    assert c_eff > 0.5 * expected
