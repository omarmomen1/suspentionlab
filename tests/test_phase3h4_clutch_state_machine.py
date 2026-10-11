"""Phase 3H.4 Clutch State Machine Tests.

Verifies:
1. 4-phase dual-clutch state cycle: IN_GEAR -> TORQUE_CUT -> CLUTCH_HANDOVER -> SPEED_SYNC -> IN_GEAR.
2. Clutch states (LOCKED, SLIPPING, OPEN) correspond correctly to each phase.
3. Dual-clutch torque allocation (C1 odd, C2 even).
4. Physical invariant: zero torque duplication (C1 + C2 == T_engine * torque_multiplier).
5. Non-negative clutch capacity.
"""

import json
from pathlib import Path
import pytest

from suspensionlab.physics.transmission_state_machine import (
    EndogenousTransmission,
    ShiftSpec,
    ClutchState,
    ShiftPhase,
)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
JSON_FILE = DATA_DIR / "phase3h4_clutch_state_machine.json"


@pytest.fixture(scope="module")
def clutch_data():
    assert JSON_FILE.exists(), f"Missing deliverable: {JSON_FILE}"
    with open(JSON_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def test_clutch_deliverable_structure(clutch_data):
    """Verify JSON structure and required modeled phases."""
    assert "phases_modeled" in clutch_data
    assert clutch_data["phases_modeled"] == ["IN_GEAR", "TORQUE_CUT", "CLUTCH_HANDOVER", "SPEED_SYNC"]
    assert clutch_data["clutch_states"] == ["LOCKED", "SLIPPING", "OPEN"]
    assert len(clutch_data["window_a_clutch_handover_sample"]) > 0


def test_state_machine_sequential_phase_execution():
    """Verify that a shift executes each phase in order."""
    spec = ShiftSpec(
        upshift_rpm_min=5000.0,
        upshift_rpm_max=6000.0,
        t_torque_cut_s=0.040,
        t_clutch_handover_s=0.070,
        t_speed_sync_s=0.040,
    )
    tx = EndogenousTransmission(spec=spec, initial_gear=2)

    # Initial state
    assert tx.current_state.shift_state == ShiftPhase.IN_GEAR
    assert tx.current_state.clutch_state == ClutchState.LOCKED
    assert tx.current_state.gear == 2

    # Advance until upshift triggered (RPM > 6000 at full throttle)
    w_drive = 75.0  # rad/s, ~24 m/s in gear 2 (ratio 8.528 -> ~6100 RPM)
    st = tx.step(sim_vx=24.0, sim_omega_drive=w_drive, throttle=1.0, brake_bar=0.0, demanded_engine_torque_nm=300.0, dt=0.005)
    assert st.shift_state == ShiftPhase.TORQUE_CUT
    assert st.clutch_state == ClutchState.LOCKED
    assert st.torque_multiplier == pytest.approx(0.10)

    # Step through TORQUE_CUT (40 ms = 8 steps at 5 ms)
    for _ in range(8):
        st = tx.step(sim_vx=24.0, sim_omega_drive=w_drive, throttle=1.0, brake_bar=0.0, demanded_engine_torque_nm=300.0, dt=0.005)
    assert st.shift_state == ShiftPhase.CLUTCH_HANDOVER
    assert st.clutch_state == ClutchState.SLIPPING

    # Step through CLUTCH_HANDOVER (70 ms = 14 steps at 5 ms)
    handover_c1_torques = []
    handover_c2_torques = []
    for _ in range(14):
        st = tx.step(sim_vx=24.0, sim_omega_drive=w_drive, throttle=1.0, brake_bar=0.0, demanded_engine_torque_nm=300.0, dt=0.005)
        handover_c1_torques.append(st.clutch1_torque_nm)
        handover_c2_torques.append(st.clutch2_torque_nm)
    assert st.shift_state == ShiftPhase.SPEED_SYNC

    # Verify handover continuity: C2 (gear 2, offgoing) decreases, C1 (gear 3, oncoming) increases
    assert handover_c1_torques[-1] > handover_c1_torques[0]
    assert handover_c2_torques[-1] < handover_c2_torques[0]

    # Step through SPEED_SYNC (40 ms = 8 steps at 5 ms)
    for _ in range(8):
        st = tx.step(sim_vx=24.0, sim_omega_drive=w_drive, throttle=1.0, brake_bar=0.0, demanded_engine_torque_nm=300.0, dt=0.005)
    assert st.shift_state == ShiftPhase.IN_GEAR
    assert st.clutch_state == ClutchState.LOCKED
    assert st.gear == 3


def test_dual_clutch_torque_conservation_invariant():
    """Verify C1 + C2 == demanded_torque * multiplier across all phases."""
    spec = ShiftSpec()
    tx = EndogenousTransmission(spec=spec, initial_gear=2)

    w_drive = 75.0
    for step_i in range(50):
        st = tx.step(sim_vx=24.0, sim_omega_drive=w_drive, throttle=1.0, brake_bar=0.0, demanded_engine_torque_nm=280.0, dt=0.005)
        # Non-negative capacity
        assert st.clutch1_torque_nm >= 0.0
        assert st.clutch2_torque_nm >= 0.0
        # Exact torque conservation
        expected_t = 280.0 * st.torque_multiplier
        actual_t = st.clutch1_torque_nm + st.clutch2_torque_nm
        assert actual_t == pytest.approx(expected_t, abs=1e-5)


def test_odd_even_clutch_assignment():
    """Verify Clutch 1 is allocated to odd gears and Clutch 2 to even gears."""
    spec = ShiftSpec()
    for g in [1, 3, 5]:
        tx = EndogenousTransmission(spec=spec, initial_gear=g)
        st = tx.step(sim_vx=20.0, sim_omega_drive=40.0, throttle=0.5, brake_bar=0.0, demanded_engine_torque_nm=150.0, dt=0.005)
        assert st.clutch1_torque_nm == pytest.approx(150.0)
        assert st.clutch2_torque_nm == pytest.approx(0.0)

    for g in [2, 4, 6]:
        tx = EndogenousTransmission(spec=spec, initial_gear=g)
        st = tx.step(sim_vx=20.0, sim_omega_drive=40.0, throttle=0.5, brake_bar=0.0, demanded_engine_torque_nm=150.0, dt=0.005)
        assert st.clutch1_torque_nm == pytest.approx(0.0)
        assert st.clutch2_torque_nm == pytest.approx(150.0)
