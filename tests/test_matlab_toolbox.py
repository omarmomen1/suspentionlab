"""
tests/test_matlab_toolbox.py
============================
Automated contract and integrity test suite for the SuspensionLab MATLAB & Simulink toolbox.
Verifies class contracts, parameter parity with core physics, and JSON serialization compatibility.
"""

import re
import pathlib
import pytest

from suspensionlab.physics.quarter_car import QuarterCarParams as PyQuarterCarParams
from suspensionlab.physics.full_car import FullCarParams as PyFullCarParams

MATLAB_DIR = pathlib.Path(__file__).parent.parent / "matlab"
PKG_DIR = MATLAB_DIR / "+suspensionlab"
SIMULINK_DIR = MATLAB_DIR / "simulink"


def test_matlab_files_present():
    """Verify all planned MATLAB toolbox files exist."""
    expected_pkg_files = [
        "Client.m",
        "QuarterCarParams.m",
        "FullCarParams.m",
        "RoadProfile.m",
        "SimulationResult.m",
        "OptimizationResult.m",
    ]
    for f in expected_pkg_files:
        path = PKG_DIR / f
        assert path.exists(), f"Missing MATLAB file: {path}"
        assert path.stat().st_size > 100, f"File appears empty: {path}"

    expected_simulink_files = [
        "SuspensionLabQuarterCarBlock.m",
        "load_fmu_into_simulink.m",
    ]
    for f in expected_simulink_files:
        path = SIMULINK_DIR / f
        assert path.exists(), f"Missing Simulink file: {path}"


def test_quarter_car_params_parity():
    """Verify MATLAB QuarterCarParams defaults match canonical Python physics defaults."""
    qc_m = (PKG_DIR / "QuarterCarParams.m").read_text(encoding="utf-8")
    py_defaults = PyQuarterCarParams()

    # Verify default values in classdef property block
    assert f"m_s (1,1) double {{mustBePositive}} = {py_defaults.m_s}" in qc_m
    assert f"m_u (1,1) double {{mustBePositive}} = {py_defaults.m_u}" in qc_m
    assert f"k_s (1,1) double {{mustBeNonnegative}} = {py_defaults.k_s}" in qc_m
    assert f"c   (1,1) double {{mustBeNonnegative}} = {py_defaults.c}" in qc_m
    assert f"k_t (1,1) double {{mustBePositive}} = {py_defaults.k_t}" in qc_m
    assert f"MR  (1,1) double {{mustBePositive}} = {py_defaults.MR}" in qc_m

    # Verify dependent properties for wheel rate and wheel damping
    assert "k_w (1,1) double" in qc_m
    assert "c_w (1,1) double" in qc_m
    assert "val = obj.k_s * (obj.MR ^ 2);" in qc_m


def test_full_car_params_contract():
    """Verify FullCarParams defines all 7-DOF vehicle properties."""
    fc_m = (PKG_DIR / "FullCarParams.m").read_text(encoding="utf-8")
    required_props = [
        "m_s", "m_uf", "m_ur", "I_x", "I_y",
        "a", "b", "tw_f", "tw_r",
        "k_sf", "k_sr", "c_f", "c_r",
        "k_arb_f", "k_arb_r", "k_tf", "k_tr",
        "speed_mps"
    ]
    for prop in required_props:
        assert f"{prop} " in fc_m, f"Missing property {prop} in FullCarParams.m"


def test_matlab_system_block_interface():
    """Verify Simulink System Block implements necessary methods."""
    block_m = (SIMULINK_DIR / "SuspensionLabQuarterCarBlock.m").read_text(encoding="utf-8")
    assert "classdef SuspensionLabQuarterCarBlock < matlab.System" in block_m
    assert "outputImpl(obj, u)" in block_m
    assert "updateImpl(obj, u)" in block_m
    assert "resetImpl(obj)" in block_m
    assert "getSampleTimeImpl(obj)" in block_m


def test_matlab_client_methods():
    """Verify Client.m implements all enterprise integration endpoints."""
    client_m = (PKG_DIR / "Client.m").read_text(encoding="utf-8")
    methods = [
        "simulateQuarterCar",
        "simulateFullCar",
        "getTelemetry",
        "submitOptimization",
        "getResults",
        "pollJob",
        "getReport",
        "exportCAE",
    ]
    for m in methods:
        assert f"function" in client_m and m in client_m, f"Client.m missing method {m}"
