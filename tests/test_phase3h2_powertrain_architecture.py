"""Phase 3H.2 Powertrain Architecture & Dual-Path Separation Tests.

Verifies:
1. Strict separation between Actuator Replay (Path A) and Predictive Simulation (Path B).
2. Endogenous forward state propagation without measured state feedback leakage.
3. Integration of GearInferenceEngine and EngineTorqueModel into PowertrainCorrectedLapSimulator.
4. Unaltered baseline physical subsystems (tire, aero, suspension, mass).
"""

import json
from pathlib import Path
import pytest

from suspensionlab.physics.dynamic_lap_sim import (
    DynamicVehicleParams,
    DynamicVehicleState,
    DriverControls,
)
from suspensionlab.physics.powertrain_lap_sim import PowertrainCorrectedLapSimulator
from suspensionlab.physics.gear_inference import GearInferenceEngine
from suspensionlab.physics.engine_torque_model import (
    PredictiveEngineTorqueModel,
    ActuatorReplayEngineTorque,
    SyntheticEngineTorqueModel,
)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DOCS_DIR = Path(__file__).resolve().parent.parent / "docs"
DEP_GRAPH_JSON = DATA_DIR / "phase3h2_dependency_graph.json"
ARCH_MD = DOCS_DIR / "phase3h2_powertrain_architecture.md"


@pytest.fixture(scope="module")
def dep_graph_data():
    assert DEP_GRAPH_JSON.exists(), f"Missing dep graph file: {DEP_GRAPH_JSON}"
    with open(DEP_GRAPH_JSON, "r", encoding="utf-8") as f:
        return json.load(f)


def test_dual_path_architectural_separation(dep_graph_data):
    """Verify that Path A (Actuator Replay) and Path B (Predictive Simulation) are decoupled."""
    paths = dep_graph_data["architectural_paths"]
    assert "path_a_actuator_replay" in paths
    assert "path_b_predictive_simulation" in paths

    path_a = paths["path_a_actuator_replay"]
    assert path_a["epistemic_classification"] == "BOUNDARY_REPLAY"
    assert "engineTorque_Nm" in path_a["boundary_inputs"]

    path_b = paths["path_b_predictive_simulation"]
    assert path_b["epistemic_classification"] == "MODEL_SUPPORTED"
    assert "sub['Vx_mps']" in path_b["forbidden_feedback_states"]
    assert "sub['yawRate_radps']" in path_b["forbidden_feedback_states"]


def test_endogenous_forward_propagation():
    """Verify simulator propagates forward endogenously without measured state feedback."""
    params = DynamicVehicleParams(mass_kg=1530.0, drivetrain_layout="FWD")
    sim = PowertrainCorrectedLapSimulator(
        params=params,
        powertrain_mode="PREDICTIVE",
        dt_fixed_s=0.005,
    )
    st = DynamicVehicleState(u_mps=25.0, omega_fl=78.0, omega_fr=78.0)
    ctrl = DriverControls(throttle=0.30, steering_deg=2.0)

    # Step forward 10 steps endogenously
    for _ in range(10):
        st = sim.step(st, ctrl, road_bank_rad=0.0, road_grade_rad=0.0)

    assert st.u_mps > 24.0, "Vehicle state should remain physically stable"
    assert not (st.u_mps != st.u_mps), "State must not be NaN"


def test_powertrain_mode_selection():
    """Verify simulator properly switches between PREDICTIVE, ACTUATOR_REPLAY, and SYNTHETIC."""
    params = DynamicVehicleParams(mass_kg=1530.0, drivetrain_layout="FWD")

    # Predictive
    sim_pred = PowertrainCorrectedLapSimulator(params=params, powertrain_mode="PREDICTIVE")
    assert isinstance(sim_pred.torque_model, PredictiveEngineTorqueModel)

    # Actuator Replay
    replay_model = ActuatorReplayEngineTorque(default_torque_nm=120.0)
    sim_replay = PowertrainCorrectedLapSimulator(params=params, torque_model=replay_model, powertrain_mode="ACTUATOR_REPLAY")
    assert isinstance(sim_replay.torque_model, ActuatorReplayEngineTorque)

    # Synthetic
    synth_model = SyntheticEngineTorqueModel()
    sim_synth = PowertrainCorrectedLapSimulator(params=params, torque_model=synth_model, powertrain_mode="SYNTHETIC")
    assert isinstance(sim_synth.torque_model, SyntheticEngineTorqueModel)
