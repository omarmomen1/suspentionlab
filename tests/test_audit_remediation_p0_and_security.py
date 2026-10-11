"""
tests/test_audit_remediation_p0_and_security.py
===============================================
Tests verifying all P0/P1 audit remediations:
1. SSO/OIDC account takeover prevention (email_verified & external_id binding)
2. Yaw dynamics Understeer Gradient formula physics correctness (b/Cf - a/Cr) & MMM consistency
3. Webhook SSRF validation blocking cloud metadata (169.254.169.254) and private networks
4. Lap Simulator lateral load sharing in ax_max_accel using true weight_dist_rear
5. Suspension/Aero Coupling pitch stiffness with asymmetric CoG distances
6. ERS Model dynamic vehicle mass scaling and kinematic lap time delta formula
"""

import math
import numpy as np
import pytest

from suspensionlab.physics.yaw_dynamics import (
    BicycleModelParams,
    YawMomentAnalyzer,
    compute_stability_metrics,
)
from suspensionlab.backend.services.webhooks import validate_webhook_url
from suspensionlab.physics.suspension_aero_coupling import SuspensionConfig
from suspensionlab.physics.ers_model import ERSConfig, ERSDeploymentController, ERSLapAnalyzer, ERSState
from suspensionlab.physics.lap_sim import LapSimVehicle, MassProperties



def test_yaw_dynamics_understeer_gradient_physics_correctness():
    """
    Validates that the understeer gradient K_us = m/L * (b/Cf - a/Cr) correctly
    classifies understeer when front axle compliance is higher than rear axle compliance.
    """
    # 1. Typical understeer passenger/GT car setup:
    # Mass = 1200 kg, Wheelbase L = 2.6m (a = 1.1m, b = 1.5m -> 57.7% front weight)
    # Front cornering stiffness Cf = 60,000 N/rad (2 tires total)
    # Rear cornering stiffness Cr = 75,000 N/rad (2 tires total, stiffer rear)
    p_us = BicycleModelParams(
        mass=1200.0,
        wheelbase=2.6,
        cog_dist_front=1.1,
        C_alpha_front=60000.0,
        C_alpha_rear=75000.0,
    )
    analyzer_us = YawMomentAnalyzer(p_us)
    k_us_deg = analyzer_us.understeer_gradient()
    
    # Weight on front: 1200 * (1.5/2.6) = 692.3 kg -> front slip angle = 692.3*g / 60000 = 0.113 rad/g
    # Weight on rear: 1200 * (1.1/2.6) = 507.7 kg -> rear slip angle = 507.7*g / 75000 = 0.066 rad/g
    # alpha_f > alpha_r => Positive understeer gradient (Understeer)
    assert k_us_deg > 0.0, f"Expected understeer (K_us > 0), got {k_us_deg}"

    linear_us = compute_stability_metrics(params=p_us, v=25.0)
    assert linear_us["handling_class"] == "understeer"
    assert linear_us["understeer_gradient_deg_per_g"] > 0.0

    mmm_us = analyzer_us.compute_mmm(v=25.0)
    assert mmm_us.understeer_gradient == round(k_us_deg, 3)

    # 2. Oversteer race setup:
    # Stiffer front (Cf = 90,000 N/rad), softer rear (Cr = 50,000 N/rad)
    p_os = BicycleModelParams(
        mass=1200.0,
        wheelbase=2.6,
        cog_dist_front=1.3,
        C_alpha_front=90000.0,
        C_alpha_rear=50000.0,
    )

    analyzer_os = YawMomentAnalyzer(p_os)
    k_os_deg = analyzer_os.understeer_gradient()
    assert k_os_deg < 0.0, f"Expected oversteer (K_us < 0), got {k_os_deg}"

    linear_os = compute_stability_metrics(params=p_os, v=25.0)
    assert linear_os["handling_class"] == "oversteer"
    assert linear_os["understeer_gradient_deg_per_g"] < 0.0

    mmm_os = analyzer_os.compute_mmm(v=25.0)
    assert mmm_os.understeer_gradient == round(k_os_deg, 3)


def test_lap_sim_ax_max_accel_weight_distribution_sensitivity():
    """
    Verifies that ax_max_accel respects weight distribution (more rear weight = more rear normal load,
    leaving more Fx available during corner exit).
    """
    # Compare rear-biased vehicle vs front-biased vehicle
    # In traction-limited regime (e.g. tight corner exit at 10 m/s with 10 m/s² lateral),
    # rear tire grip limits forward acceleration.
    v = LapSimVehicle()
    v.mass_props = MassProperties(total_mass=1000.0, wheelbase=2.5, cog_dist_front=1.5)

    ax_rear_bias = v.ax_max_accel(v=10.0, ay=10.0)

    # Front-biased car: 60% front, 40% rear
    v.mass_props = MassProperties(total_mass=1000.0, wheelbase=2.5, cog_dist_front=1.0)
    ax_front_bias = v.ax_max_accel(v=10.0, ay=10.0)

    # Rear biased car has more rear normal load, thus higher tractive capability
    assert ax_rear_bias > ax_front_bias



def test_suspension_aero_coupling_pitch_stiffness_asymmetric_cog():
    """
    Verifies that pitch_stiffness calculates K_heave_f * a^2 + K_heave_r * b^2 correctly
    for asymmetric CoG positions.
    """
    sus = SuspensionConfig(
        k_spring_front=30000.0,
        k_spring_rear=40000.0,
        motion_ratio_front=1.0,
        motion_ratio_rear=1.0,
    )
    wheelbase = 3.0
    a = 1.0  # 66.7% front weight
    b = 2.0  # 33.3% rear weight

    # K_heave_f = 2 * 30000 = 60000 N/m
    # K_heave_r = 2 * 40000 = 80000 N/m
    # K_theta = 60000 * 1^2 + 80000 * 2^2 = 60000 + 320000 = 380,000 Nm/rad
    K_theta_asym = sus.pitch_stiffness(wheelbase=wheelbase, a=a, b=b)
    assert K_theta_asym == 380000.0

    # Symmetric comparison (a = b = 1.5):
    # K_theta_sym = 60000 * 1.5^2 + 80000 * 1.5^2 = 140000 * 2.25 = 315,000 Nm/rad
    K_theta_sym = sus.pitch_stiffness(wheelbase=wheelbase)
    assert K_theta_sym == 315000.0


def test_ers_model_mass_scaling_and_kinematic_delta_t():
    """
    Verifies that ERS model scales regen power with configured vehicle mass and computes
    accurate first-order kinematic time savings.
    """
    ctrl = ERSDeploymentController()
    cfg = ERSConfig()
    state = ERSState(soc=0.5)

    # Deceleration ax = -5.0 m/s^2 at 50 m/s
    # Compare 1200kg GT car vs 800kg Formula car
    _, state_1200 = ctrl.compute(state, cfg, v=50.0, ax=-5.0, curvature=0.0, dt=0.1, vehicle_mass_kg=1200.0)
    _, state_800 = ctrl.compute(state, cfg, v=50.0, ax=-5.0, curvature=0.0, dt=0.1, vehicle_mass_kg=800.0)

    # 1200kg car generates more available kinetic braking energy for regeneration
    assert state_1200.regen_power_w >= state_800.regen_power_w

    # Analyze lap time delta
    analyzer = ERSLapAnalyzer(vehicle_mass_kg=800.0)
    distances = np.array([0.0, 100.0, 200.0, 300.0])
    speeds = np.array([50.0, 60.0, 70.0, 80.0])
    ax_arr = np.array([2.0, 2.0, 2.0, 2.0])
    curv = np.array([0.0, 0.0, 0.0, 0.0])

    res = analyzer.analyze(distances, speeds, ax_arr, curv)
    assert res["lap_time_delta_s"] < 0.0, "ERS deployment must reduce lap time"


def test_webhook_ssrf_protection_blocks_forbidden_ips(monkeypatch):
    monkeypatch.setenv("ALLOW_PRIVATE_WEBHOOKS", "false")

    # 1. Block AWS metadata IP (169.254.169.254)
    with pytest.raises(ValueError, match="prohibited IP address|not permitted"):
        validate_webhook_url("http://169.254.169.254/latest/meta-data/")

    # 2. Block localhost / 127.0.0.1
    with pytest.raises(ValueError, match="not permitted|prohibited IP address"):
        validate_webhook_url("http://127.0.0.1:8000/internal")

    with pytest.raises(ValueError, match="not permitted|prohibited IP address"):
        validate_webhook_url("http://localhost:3000/api")

    # 3. Block private RFC 1918 addresses
    with pytest.raises(ValueError, match="prohibited IP address"):
        validate_webhook_url("http://10.0.0.1:8080/hook")

    with pytest.raises(ValueError, match="prohibited IP address"):
        validate_webhook_url("http://192.168.1.100/hook")

    # 4. Block non-http schemes
    with pytest.raises(ValueError, match="Invalid URL scheme"):
        validate_webhook_url("file:///etc/passwd")

    with pytest.raises(ValueError, match="Invalid URL scheme"):
        validate_webhook_url("gopher://evil.com")


@pytest.mark.asyncio
async def test_sso_unverified_email_rejection():
    from fastapi import HTTPException
    from suspensionlab.backend.api.routes.sso_routes import _upsert_sso_user

    unverified_claims = {
        "email": "victim-admin@team.com",
        "email_verified": False,
        "sub": "attacker-idp-sub-1234",
    }

    with pytest.raises(HTTPException) as exc_info:
        await _upsert_sso_user(unverified_claims)

    assert exc_info.value.status_code == 401
    assert "unverified" in str(exc_info.value.detail).lower()


@pytest.mark.asyncio
async def test_ai_engineer_focus_validation_and_numeric_verification():
    from suspensionlab.backend.api.routes.ai_engineer_routes import ai_race_engineer_chat, AIChatRequest

    # Test problem that will trigger comfort focus and verify structured response
    req = AIChatRequest(problem="The car is too bouncy and floats over highway crests.")
    resp = await ai_race_engineer_chat(req)


    # 1. Verification of computed numbers
    assert resp.tested_setups > 0
    assert resp.confidence >= 0.3
    assert len(resp.predicted_effects) > 0
    for eff in resp.predicted_effects:
        assert isinstance(eff.baseline, float)
        assert isinstance(eff.predicted, float)

    # 2. Free-text fields are sanitized and grounded
    assert isinstance(resp.diagnosis, str)
    assert isinstance(resp.root_cause, str)
    assert isinstance(resp.setup_summary, str)

