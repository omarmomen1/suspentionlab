"""Phase 3H.1 Gear-Ratio Integrity Tests.

Verifies:
1. Physical kinematic transmission ratio derivation from measured engine and wheel RPM.
2. Dynamic rolling radius derivation and carcass deflection.
3. Telemetry channel `GearRatio` semantics, constant value, and 2.40x quotient.
4. Gear-state clamping defect identification (6th gear vs 3rd gear).
5. Subsystem gearbox ratio decomposition (VW Golf GTI DQ250 3rd gear).
"""

import json
from pathlib import Path
import pytest

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
GEAR_AUDIT_FILE = DATA_DIR / "phase3h1_gear_ratio_audit.json"


@pytest.fixture(scope="module")
def gear_audit_data():
    assert GEAR_AUDIT_FILE.exists(), f"Missing audit file: {GEAR_AUDIT_FILE}"
    with open(GEAR_AUDIT_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def test_measured_kinematic_transmission_ratio(gear_audit_data):
    """Verify that the physical kinematic transmission ratio N_total = omega_engine / omega_wheel is 5.6426 +- 0.02."""
    kinematics = gear_audit_data["kinematic_ratio_derivation"]
    mean_ratio = kinematics["mean_inferred_n_total"]
    std_ratio = kinematics["std_inferred_n_total"]

    assert 5.62 <= mean_ratio <= 5.66, f"Expected N_total ~5.6426, got {mean_ratio}"
    assert std_ratio < 0.05, f"Kinematic ratio should be tightly bound across locked clutch, got std {std_ratio}"
    assert gear_audit_data["subsystem_ratio_decomposition"]["actual_operating_gear"] == 3


def test_dynamic_rolling_radius(gear_audit_data):
    """Verify effective rolling radius R_eff = Vx / omega_wheel ~ 0.3170 m with ~0.88% carcass deflection."""
    signals = gear_audit_data["signals_summary"]
    r_eff = signals["mean_dynamic_rolling_radius_m"]
    carcass_deflection = signals["carcass_deflection_pct"]

    assert 0.315 <= r_eff <= 0.320, f"Expected dynamic radius ~0.3170 m, got {r_eff}"
    assert 0.5 <= carcass_deflection <= 1.5, f"Expected carcass deflection ~0.88%, got {carcass_deflection}%"


def test_telemetry_gear_ratio_constant_and_quotient(gear_audit_data):
    """Verify telemetry channel GearRatio is 13.585 and yields the 2.4076x quotient to physical ratio."""
    can_provenance = gear_audit_data["telemetry_channel_gearratio_provenance"]
    assert can_provenance["channel_value_in_subset"] == pytest.approx(13.585, abs=1e-3)
    assert can_provenance["quotient_over_physical_ratio"] == pytest.approx(2.4076, abs=0.01)
    assert can_provenance["channel_provenance_status"] in ["MODEL_SUPPORTED", "UNIDENTIFIABLE"]


def test_gear_clamping_discrepancy(gear_audit_data):
    """Verify simulator commanded gear index 13 was clamped to 6th gear (ratio 4.200) instead of 3rd gear."""
    clamping = gear_audit_data["gear_state_audit"]
    assert clamping["simulator_commanded_gear"] == 13
    assert clamping["simulator_clamped_gear_index"] == 5
    assert clamping["simulator_clamped_effective_gear"] == 6
    assert clamping["simulator_applied_gear_ratio"] == 4.200


def test_subsystem_gearbox_decomposition(gear_audit_data):
    """Verify VW Golf GTI DQ250 6-speed DSG 3rd gear kinematics match physical measurements to <0.1%."""
    decomp = gear_audit_data["subsystem_ratio_decomposition"]
    assert "Golf VII GTI" in decomp["vehicle_platform"]
    assert "DQ250" in decomp["vehicle_platform"]
    assert decomp["gearbox_gear_ratio"] == pytest.approx(1.3314, abs=1e-4)
    assert decomp["final_drive_ratio"] == pytest.approx(4.2381, abs=1e-4)
    assert decomp["total_wheel_ratio"] == pytest.approx(5.6427, abs=1e-3)
    assert decomp["ratio_relative_difference_pct"] < 0.1
