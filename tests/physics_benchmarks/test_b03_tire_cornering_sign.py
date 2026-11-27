"""B-03 Tire cornering sign (Wave 5A PKY1 fix).

A standard PAC2002 .tir stores PKY1 = -15.0. Cornering stiffness must still be
positive and peak grip must equal the .tir's PDY1 friction coefficient at nominal load (1.0 G
here; the 1.10 G figure quoted in the spec does not follow from this file: PDY1 = 1.0, dfz = 0). A full fit against Calspan TTC data
needs a licensed dataset that is not in this repository: that part is reported
as IN_PROGRESS, not as validated.
"""
import numpy as np
import pytest

from suspensionlab.physics.magic_formula import calc_tire_forces
from suspensionlab.physics.tir_parser import parse_tir_file

TIR = """
[MDI_HEADER]
FILE_TYPE = 'tir'
[VERTICAL]
FNOMIN = 4000.0
[LATERAL_COEFFICIENTS]
PCY1 = 1.3
PDY1 = 1.0
PDY2 = -0.1
PKY1 = -15.0
PKY2 = 1.5
PKY3 = 0.0
"""


def test_b03_negative_pky1_gives_positive_stiffness_and_about_pdy1_g(record):
    c = parse_tir_file(TIR)
    assert c.pKy1 == pytest.approx(-15.0)
    a = 0.02
    fy_pos = calc_tire_forces(4000.0, a, 0.0, 0.0, c)[1]
    fy_neg = calc_tire_forces(4000.0, -a, 0.0, 0.0, c)[1]
    stiffness = fy_pos / a
    peak_g = max(calc_tire_forces(4000.0, float(x), 0.0, 0.0, c)[1] for x in np.linspace(0, 0.3, 120)) / 4000.0
    record(
        name="Tire cornering sign",
        measured={"pky1": -15.0, "cornering_stiffness_n_per_rad": round(stiffness, 1),
                  "peak_grip_g": round(peak_g, 3)},
        tolerance={"peak_grip_g": [0.98, 1.02], "expected_peak_grip_g": 1.0},
        reference="Wave 5A abs(PKY1) fix. Peak grip is the model output for this synthetic .tir, "
                  "not a measurement.",
        pending={"calspan_ttc_fit": "IN_PROGRESS",
                 "reason": "Needs a licensed Calspan TTC dataset; not in this repository."},
    )
    assert fy_pos > 0 > fy_neg
    assert stiffness > 0
    assert 0.98 <= peak_g <= 1.02  # = PDY1 at Fz = FNOMIN
