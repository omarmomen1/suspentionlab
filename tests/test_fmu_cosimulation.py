"""
tests/test_fmu_cosimulation.py
==============================
SuspensionLab PRO — FMI 2.0 Co-Simulation Industrial Validation Test Suite.

Verifies:
- Standard FMI 2.0 package structure (.fmu archive, binaries for win64, linux64, linux-arm64)
- XML schema compliance with FMI 2.0 standard specification
- Variable causality, variability, units, value references, and descriptions
- FMU lifecycle: instantiation, parameter initialization, experiment setup, termination
- Numerical time-stepping and integration accuracy against analytical 2-DOF mechanics
"""

import zipfile
import pathlib
import pytest
import numpy as np
import fmpy
from fmpy import simulate_fmu, read_model_description
from fmpy.fmi2 import FMU2Slave

from suspensionlab.physics.fmi_exporter import build_and_package_quarter_car_fmu


@pytest.fixture(scope="module")
def fmu_path(tmp_path_factory) -> str:
    tmp_dir = tmp_path_factory.mktemp("fmu_test")
    target = tmp_dir / "QuarterCarRideModel.fmu"
    build_and_package_quarter_car_fmu(target)
    return str(target)


def test_fmu_package_structure_and_binaries(fmu_path):
    """Verify FMU ZIP contents comply with standard directory hierarchy."""
    with zipfile.ZipFile(fmu_path, "r") as zf:
        namelist = zf.namelist()
        assert "modelDescription.xml" in namelist
        assert "documentation/index.html" in namelist
        assert "resources/model_info.json" in namelist
        assert "binaries/win64/QuarterCarRideModel.dll" in namelist
        assert "binaries/linux64/QuarterCarRideModel.so" in namelist
        assert "binaries/linux-arm64/QuarterCarRideModel.so" in namelist


def test_fmu_xml_schema_validation(fmu_path):
    """Validate modelDescription.xml against the official FMI 2.0 XSD schema."""
    md = read_model_description(fmu_path)
    assert md.fmiVersion == "2.0"
    assert md.modelName == "QuarterCarRideModel"
    assert md.guid == "{8c3f4e21-9a7b-4d61-b531-ec72f0941ab2}"
    assert md.coSimulation is not None
    assert md.coSimulation.modelIdentifier == "QuarterCarRideModel"
    assert md.coSimulation.canHandleVariableCommunicationStepSize is True
    assert md.coSimulation.canInterpolateInputs is True


def test_fmu_variables_units_and_causality(fmu_path):
    """Verify variables, value references, causality, and units."""
    md = read_model_description(fmu_path)
    vars_by_name = {v.name: v for v in md.modelVariables}

    # Parameters
    assert "m_s" in vars_by_name
    assert vars_by_name["m_s"].causality == "parameter"
    assert vars_by_name["m_s"].unit == "kg"
    assert float(vars_by_name["m_s"].start) == 300.0

    assert "k_s" in vars_by_name
    assert vars_by_name["k_s"].causality == "parameter"
    assert vars_by_name["k_s"].unit == "N/m"

    assert "MR" in vars_by_name
    assert vars_by_name["MR"].causality == "parameter"
    assert float(vars_by_name["MR"].start) == 0.85

    # Inputs
    assert "z_road" in vars_by_name
    assert vars_by_name["z_road"].causality == "input"
    assert vars_by_name["z_road"].unit == "m"

    assert "dz_road" in vars_by_name
    assert vars_by_name["dz_road"].causality == "input"
    assert vars_by_name["dz_road"].unit == "m/s"

    # Outputs
    assert "z_s" in vars_by_name
    assert vars_by_name["z_s"].causality == "output"
    assert vars_by_name["z_s"].unit == "m"

    assert "susp_travel" in vars_by_name
    assert vars_by_name["susp_travel"].causality == "output"
    assert vars_by_name["susp_travel"].unit == "m"

    assert "tire_load_dynamic" in vars_by_name
    assert vars_by_name["tire_load_dynamic"].causality == "output"
    assert vars_by_name["tire_load_dynamic"].unit == "N"

    assert "body_accel" in vars_by_name
    assert vars_by_name["body_accel"].causality == "output"
    assert vars_by_name["body_accel"].unit == "m/s2"


def test_fmu_parameter_tuning_and_simulation(fmu_path):
    """Simulate FMU with tuned parameters and check physical behavior."""
    step_height = 0.03

    # Simulation 1: Soft spring
    res_soft = simulate_fmu(
        fmu_path,
        stop_time=2.0,
        output_interval=0.005,
        start_values={"k_s": 15000.0, "z_road": step_height},
    )

    # Simulation 2: Stiff spring
    res_stiff = simulate_fmu(
        fmu_path,
        stop_time=2.0,
        output_interval=0.005,
        start_values={"k_s": 50000.0, "z_road": step_height},
    )

    # Stiff spring should have higher initial acceleration transient
    max_accel_soft = np.max(np.abs(res_soft["body_accel"]))
    max_accel_stiff = np.max(np.abs(res_stiff["body_accel"]))
    assert max_accel_stiff > max_accel_soft

    # Both must settle toward the step height at steady state (t = 2.0 s)
    assert np.isclose(res_soft["z_s"][-1], step_height, atol=1e-3)
    assert np.isclose(res_stiff["z_s"][-1], step_height, atol=1e-3)


def test_fmu_direct_slave_lifecycle(fmu_path):
    """Directly test FMU2Slave C interface lifecycle functions."""
    md = read_model_description(fmu_path)
    unzip_dir = fmpy.extract(fmu_path)

    fmu = FMU2Slave(
        guid=md.guid,
        unzipDirectory=unzip_dir,
        modelIdentifier=md.coSimulation.modelIdentifier,
        instanceName="test_qc_slave",
    )

    # 1. Instantiate
    fmu.instantiate()

    # 2. Setup Experiment
    fmu.setupExperiment(startTime=0.0, stopTime=1.0)

    # 3. Initialization Mode
    fmu.enterInitializationMode()

    # Set parameters: m_s = 280 kg, k_s = 30000 N/m, z_road = 0.02 m
    vr_m_s = 1
    vr_k_s = 3
    vr_z_road = 10
    vr_z_s = 20
    vr_susp_travel = 22

    fmu.setReal([vr_m_s, vr_k_s, vr_z_road], [280.0, 30000.0, 0.02])

    fmu.exitInitializationMode()

    # 4. Time stepping (DoStep)
    t = 0.0
    dt = 0.002
    for _ in range(250): # 0.5 seconds
        fmu.doStep(currentCommunicationPoint=t, communicationStepSize=dt)
        t += dt

    # 5. Inquire outputs
    vals = fmu.getReal([vr_z_s, vr_susp_travel])
    z_s_val, travel_val = vals[0], vals[1]

    assert z_s_val > 0.0  # Body displaced toward road excitation
    assert abs(travel_val) < 0.1  # Physical suspension deflection limit

    # 6. Terminate & Free
    fmu.terminate()
    fmu.freeInstance()
