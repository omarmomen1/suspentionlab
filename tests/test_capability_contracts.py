"""
tests/test_capability_contracts.py
==================================
Unit tests for the Model Capability Contract system and quantitative confidence engine.
"""

import pytest
from suspensionlab.physics.capability_contract import (
    CONTRACTS,
    get_capability_contract,
    list_contracts,
    ModelCapabilityContract,
    ValidatedRange,
)


def test_all_models_have_registered_contracts():
    required_models = [
        "QuarterCar",
        "HalfCar",
        "FullCar",
        "Kinematics",
        "TireModel",
        "Handling",
        "LapSim",
        "ActiveQuarterCar",
    ]
    for model_name in required_models:
        contract = get_capability_contract(model_name)
        assert isinstance(contract, ModelCapabilityContract)
        assert contract.model_name == model_name
        assert len(contract.assumptions) > 0
        assert len(contract.known_limitations) > 0
        assert len(contract.recommended_use_cases) > 0
        assert contract.validation_status in ("VALIDATED", "CONDITIONAL", "EXPERIMENTAL")


def test_quarter_car_confidence_assessment():
    qc = get_capability_contract("QuarterCar")
    
    # 1. Nominal valid parameters with nonlinear damper and high correlation
    res = qc.assess_confidence(
        operating_params={"frequency_hz": 1.2, "travel_mm": 15.0, "sprung_mass_kg": 300.0},
        has_nonlinear_damper=True,
        has_telemetry_correlation=0.92,
    )
    assert res["confidence_score"] >= 95.0
    assert res["confidence_band"] == "High"
    assert len(res["warnings"]) == 0

    # 2. Out-of-range frequency and travel
    res_out = qc.assess_confidence(
        operating_params={"frequency_hz": 45.0, "travel_mm": 120.0, "sprung_mass_kg": 300.0},
        has_nonlinear_damper=False,
        has_telemetry_correlation=0.45,
    )
    assert res_out["confidence_score"] < 60.0
    assert res_out["confidence_band"] in ("Medium", "Low")
    assert len(res_out["warnings"]) >= 2


def test_list_contracts_serializable():
    contracts_list = list_contracts()
    assert len(contracts_list) >= 8
    for item in contracts_list:
        assert "model_name" in item
        assert "capabilities" in item
        assert "validated_ranges" in item
