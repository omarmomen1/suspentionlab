"""
tests/test_fmi_and_hil.py
=========================
Tests for FMI 2.0/3.0 Model Description XML Export and Real-Time HIL Deadline Monitoring (Findings 73, 74).
"""

import pytest
import xml.etree.ElementTree as ET

from suspensionlab.physics.fmi_exporter import (
    create_quarter_car_fmi_description,
    FMIModelDescription,
    FMIVariable,
)
from suspensionlab.physics.hil_interface import (
    DeterministicHILRunner,
    CANTelemetryFrame,
    HILPerformanceProfile,
)


def test_fmi_model_description_xml_generation():
    fmi_desc = create_quarter_car_fmi_description("QuarterCarRideModel")
    xml_str = fmi_desc.generate_xml()

    assert "fmiModelDescription" in xml_str
    assert "QuarterCarRideModel" in xml_str
    assert "CoSimulation" in xml_str
    assert "ModelVariables" in xml_str

    # Parse XML to verify standard structure
    root = ET.fromstring(xml_str)
    assert root.attrib["fmiVersion"] == "2.0"
    assert root.attrib["modelName"] == "QuarterCarRideModel"

    # Verify parameters and outputs exist
    scalar_vars = root.findall(".//ScalarVariable")
    var_names = [v.attrib["name"] for v in scalar_vars]
    assert "m_s" in var_names
    assert "k_s" in var_names
    assert "z_road" in var_names
    assert "susp_travel" in var_names


def test_deterministic_hil_runner_deadline_monitor():
    from suspensionlab.physics.quarter_car import QuarterCarParams, build_state_space
    import numpy as np

    runner = DeterministicHILRunner(target_frequency_hz=1000.0) # 1 kHz -> 1000 us deadline
    p = QuarterCarParams(m_s=300.0, m_u=35.0, k_s=25000.0, c=2000.0, k_t=200000.0)
    A, B = build_state_space(p)
    state = np.zeros(4)

    # Real discrete state space update step for HIL 1 kHz execution
    def physics_hil_step(sim_t: float, dt: float):
        nonlocal state
        zr = 0.02 if sim_t >= 0.01 else 0.0
        # Discrete step: x(t+dt) = x(t) + (A*x + B*u)*dt
        dx = A @ state + B * zr
        state = state + dx * dt

    profile = runner.execute_session(physics_hil_step, duration_s=0.05) # 50 steps
    assert isinstance(profile, HILPerformanceProfile)
    assert profile.total_steps == 50
    assert profile.dt_target_us == 1000.0
    assert profile.wcet_us > 0.0
    assert profile.mean_execution_us < 1000.0
    assert profile.is_hard_realtime_compliant
    assert np.any(state != 0.0)  # State actually evolved



def test_can_telemetry_frame_packing():
    frame = CANTelemetryFrame.pack_corner_telemetry(
        can_id=0x301,
        timestamp_us=123456,
        travel_mm=24.55,
        velocity_mm_s=180.2,
        normal_load_n=4250.0,
    )
    assert frame.can_id == 0x301
    assert frame.timestamp_us == 123456
    assert len(frame.payload_bytes) == 8
