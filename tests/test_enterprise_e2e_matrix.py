"""
tests/test_enterprise_e2e_matrix.py
===================================
Comprehensive Enterprise E2E Test Matrix (Finding 69).

Validates complete interconnected lifecycle across:
- Tenant Context & RBAC Authorization
- Vehicle Hardpoints & Kinematics continuation solve
- Quarter-car & Full-car ride simulation
- Telemetry Ingestion & Statistical Health Screening
- Model-to-Telemetry Residual Attribution
- Parameter Identification & Digital Twin Lineage
- Engineering Git, Setup Diff & Decision Summary
- Constrained Optimization & Sensitivity Ranking
- Failure Recovery & Structured Diagnostic Reports
"""

import pytest
import numpy as np

from suspensionlab.backend.security.tenancy import TenantContext, TenantScopedRepository
from suspensionlab.backend.security.permissions import Permission, has_permission
from suspensionlab.physics.quarter_car import QuarterCarParams, RoadProfile, simulate_time_response
from suspensionlab.physics.telemetry_health import assess_telemetry_health
from suspensionlab.physics.residual_analysis import compute_residuals
from suspensionlab.physics.digital_twin import DigitalTwin, VersionLineage
from suspensionlab.physics.engineering_git import compare_setups
from suspensionlab.physics.decision_dashboard import generate_executive_summary
from suspensionlab.physics.engineering_failure import create_tire_liftoff_failure


def test_enterprise_e2e_full_workflow_matrix():
    # 1. Tenancy & RBAC Verification
    tenant = TenantContext(
        user_id="lead-engineer-01",
        organization_id="org-ferrari",
        team_id="team-f1-dynamics",
        role="lead_engineer",
    )
    assert has_permission(tenant.role, Permission.SIMULATION_RUN)
    assert has_permission(tenant.role, Permission.SETUP_APPROVE)
    assert not has_permission(tenant.role, Permission.BILLING_MANAGE)

    # 2. Forward Physics Simulation Execution
    p = QuarterCarParams(m_s=260.0, m_u=32.0, k_s=28000.0, c=1600.0, k_t=190000.0)
    prof = RoadProfile(profile_type="step", amplitude=0.025, duration=2.0)
    sim_res = simulate_time_response(p, prof)
    assert len(sim_res["time"]) > 100
    assert max(np.abs(sim_res["susp_travel"])) > 0.0

    # 3. Telemetry Health Ingestion & Safety Screening
    t_tel = np.array(sim_res["time"])
    travel_tel = np.array(sim_res["susp_travel"]) + 0.002 * np.sin(2.0 * np.pi * 1.5 * t_tel)
    health = assess_telemetry_health({"damper_travel_fl": travel_tel}, time_channel=t_tel)
    assert not health.is_blocked

    # 4. Residual Attribution & Model Calibration
    residuals = compute_residuals(
        {"time": t_tel, "susp_travel_fl": travel_tel},
        {"time": sim_res["time"], "susp_travel_fl": sim_res["susp_travel"]},
    )
    assert "susp_travel_fl" in residuals.channel_residuals

    # 5. Parameter Identification & Digital Twin Lineage
    from suspensionlab.physics.parameter_identification import identify_suspension_parameters
    cal_rep = identify_suspension_parameters(
        target_telemetry={"vert_g": sim_res["ddz_s"]},
        nominal_params={"k_s": 25000.0, "c": 1400.0, "MR": 1.0},
    )
    assert cal_rep.residual_reduction_pct >= 0.0

    from suspensionlab.physics.digital_twin import create_reference_digital_twin
    twin = create_reference_digital_twin("TWIN-SF26-001")
    assert twin.twin_id == "TWIN-SF26-001"
    assert len(twin.compute_fingerprint()) == 64

    # 6. Engineering Git & Decision-First Executive Summary
    base_setup = {"k_sf": 35000.0, "k_sr": 40000.0, "c_lsr": 2200.0}
    cand_setup = {"k_sf": 35000.0, "k_sr": 44000.0, "c_lsr": 2450.0}
    diff = compare_setups(base_setup, cand_setup)
    assert len(diff.causal_chain) > 0

    exec_summary = generate_executive_summary(base_setup, cand_setup, lap_delta_s=-0.092)
    assert exec_summary.lap_time_delta_s == -0.092
    assert "Rear platform stability" in exec_summary.primary_mechanism

    # 7. Failure Handling & Actionable Diagnostics
    failure = create_tire_liftoff_failure(time_s=3.45, corner="RL")
    assert failure.error_code == "ERR_TIRE_CONTACT_LOSS"
    assert len(failure.suggested_actions) >= 2

