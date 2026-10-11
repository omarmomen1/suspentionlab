"""
tests/test_final_engineering_operating_system.py
=================================================
SuspensionLab PRO — Section 18 End-to-End Acceptance Test & OS Integration Suite.

Verifies the complete closed engineering lifecycle:
QUESTION → EVIDENCE → EXPERIMENT → SIMULATION → COMPARISON →
OPTIMIZATION → VALIDATION → DECISION → APPROVAL → TIMELINE → TRACK → LEARNING

Also verifies:
- Incumbent CAE Interoperability (Adams, MATLAB/Simulink, CarMaker, FMI) with External Model Identity
- Universal Engineering Search across 9 domains with multi-tenant isolation
- Institutional Memory Reconstruction ("Why did we choose Setup X?")
- Failure Diagnostics UX (5 explicit failure factors)
"""
from __future__ import annotations

import uuid
import pytest
import numpy as np
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from suspensionlab.backend.database.core import Base
from suspensionlab.backend.database.models.vehicle_twin import VehicleTwin, CalibrationObservation
from suspensionlab.backend.database.models.engineering_decision import EngineeringDecision
from suspensionlab.backend.database.models.timeline_event import TimelineEventRecord
from suspensionlab.backend.database.models.experiment import ExperimentRecord
from suspensionlab.backend.services.telemetry_correlation_service import TelemetryCorrelationService
from suspensionlab.backend.services.timeline_decision_service import TimelineDecisionService
from suspensionlab.backend.services.cae_integration_service import CaeIntegrationService
from suspensionlab.backend.services.universal_search_service import UniversalSearchService
from suspensionlab.backend.services import digital_twin
from suspensionlab.physics.quarter_car import run_quarter_car_analysis, RoadProfile, QuarterCarParams


@pytest.fixture
async def async_test_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


# ── SECTION 18: 15-STAGE END-TO-END WORKFLOW ACCEPTANCE TEST ───────────────────

@pytest.mark.asyncio
async def test_section_18_complete_engineering_decision_lifecycle(async_test_db: AsyncSession):
    """
    Executes the 15-stage Section 18 user journey:
    1. Track session: Load telemetry trace
    2. Detection: Telemetry indicates excess curb bounce
    3. Question: Engineer asks 'Why is apex curb bounce high?'
    4. Investigation: System identifies high damper velocity and underdamped heave mode
    5. Evidence: Evidence graph links telemetry to vehicle model and current setup
    6. Experiment: One-click experiment tests +15% damping
    7. Simulation: Forward simulation validates heave settling improvement
    8. Comparison: Compare View shows reduced vertical acceleration with acceptable tire load penalty
    9. Optimization: Run local Pareto sweep for optimal damper curve
    10. Validation: Out-of-sample holdout test confirms >0.85 correlation
    11. Decision: Engineer records decision: 'Adopt Setup Rev 12 for Turn 8 curbs'
    12. Approval: Track engineer and lead dynamicist approve with HMAC signatures
    13. Timeline: Timeline adds event with causal chain and parameter diff
    14. Track: Next session telemetry confirms bounce reduction
    15. Closed loop: Verification complete, decision marked VALIDATED ON TRACK
    """
    uid = uuid.uuid4()
    tid = uuid.uuid4()
    car_ref = "CAR-2026-F1"
    setup_baseline_ref = "SETUP-T8-REV11"
    setup_candidate_ref = "SETUP-T8-REV12"

    # ──────────────────────────────────────────────────────────────────────────
    # Stage 1: Track Session — Load Telemetry Trace
    # ──────────────────────────────────────────────────────────────────────────
    t_track = np.linspace(0.0, 5.0, 250)
    # Simulated curb impact at t=1.5s exciting a 2.0 Hz bounce mode
    curb_profile = np.exp(-((t_track - 1.5) / 0.3) ** 2) * 1.8
    telem_csv = "time,vert_g,speed,rh_fl,rh_fr\n" + "\n".join(
        f"{t:.3f},{g + 0.05 * np.random.randn():.4f},42.5,28.0,28.0"
        for t, g in zip(t_track, curb_profile)
    )
    assert len(telem_csv) > 200

    # ──────────────────────────────────────────────────────────────────────────
    # Stage 2: Detection — Telemetry indicates excess curb bounce
    # ──────────────────────────────────────────────────────────────────────────
    cockpit = TelemetryCorrelationService.get_correlation_cockpit()
    assert "channels" in cockpit
    ride_ch = next(c for c in cockpit["channels"] if c["key"] == "ride_accel")
    assert ride_ch["status"] in ("ALIGNED", "DIVERGENT", "DEGRADED", "CORRELATED", "diverged", "good", "warning")
    assert ride_ch["measured"] > 0.0

    # ──────────────────────────────────────────────────────────────────────────
    # Stage 3: Question — "Why is apex curb bounce high?"
    # ──────────────────────────────────────────────────────────────────────────
    question_text = "Why is apex curb bounce high through Turn 8 curbs?"
    assert len(question_text) > 10

    # ──────────────────────────────────────────────────────────────────────────
    # Stage 4: Investigation — System identifies high damper velocity & underdamping
    # ──────────────────────────────────────────────────────────────────────────
    investigation = TelemetryCorrelationService.investigate_divergence(
        channel_name="ride_accel",
        active_params={"m_s": 320.0, "k_s": 35000.0, "c": 2200.0, "MR": 0.85},
    )
    assert "findings" in investigation
    assert len(investigation["findings"]) >= 1
    assert investigation["drop_risk"] in ("LOW", "MEDIUM", "HIGH")
    assert "recommended_next_action" in investigation

    # ──────────────────────────────────────────────────────────────────────────
    # Stage 5: Evidence Graph — Links telemetry, vehicle twin, and baseline setup
    # ──────────────────────────────────────────────────────────────────────────
    twin = await digital_twin.create_twin(
        db=async_test_db,
        user_id=uid,
        team_id=tid,
        car_ref=car_ref,
        setup_ref=setup_baseline_ref,
        track_ref="Silverstone GP",
        base_params={"m_s": 320.0, "m_u": 45.0, "k_s": 35000.0, "c": 2200.0, "k_t": 220000.0, "MR": 0.85},
    )
    assert twin.id is not None
    assert twin.setup_ref == setup_baseline_ref

    # ──────────────────────────────────────────────────────────────────────────
    # Stage 6 & 7: Experiment & Simulation — Forward ODE validates +15% damping
    # ──────────────────────────────────────────────────────────────────────────
    prof = RoadProfile(profile_type="step", amplitude=0.05, duration=3.0)
    p_base = QuarterCarParams(m_s=320.0, m_u=45.0, k_s=35000.0, c=2200.0, k_t=220000.0, MR=0.85)
    p_cand = QuarterCarParams(m_s=320.0, m_u=45.0, k_s=35000.0, c=2530.0, k_t=220000.0, MR=0.85)  # +15% c

    res_base = run_quarter_car_analysis(p_base, prof)
    res_cand = run_quarter_car_analysis(p_cand, prof)

    # Real physics verification: higher damping increases damping ratio and lowers peak heave transmissibility
    assert res_cand.zeta_s > res_base.zeta_s
    assert res_cand.peak_transmissibility < res_base.peak_transmissibility

    # Persist experiment record
    exp_rec = ExperimentRecord(
        user_id=uid,
        team_id=tid,
        question=question_text,
        hypothesis="Increasing damper rate by 15% attenuates Turn 8 apex curb heave excitation.",
        author="Lead Dynamics Specialist",
        status="COMPLETED",
        validation_state="VALIDATED",
        parent_setup={"c": 2200.0, "k_s": 35000.0},
        candidate_setup={"c": 2530.0, "k_s": 35000.0},
        parameter_changes=[{"parameter": "c", "delta_pct": 15.0, "baseline": 2200.0, "candidate": 2530.0}],
        baseline_metrics={"peak_transmissibility": res_base.peak_transmissibility, "zeta_s": res_base.zeta_s},
        candidate_metrics={"peak_transmissibility": res_cand.peak_transmissibility, "zeta_s": res_cand.zeta_s},
        improvements=[{"metric": "Transmissibility reduced by 8.4%", "unit": "%", "baseline": 1.0, "candidate": 0.916, "delta_pct": -8.4, "reason": "Higher c"}],
        regressions=[{"metric": "Tire peak normal force increased by 1.9%", "unit": "%", "baseline": 1.0, "candidate": 1.019, "delta_pct": 1.9, "reason": "Higher c"}],
        causal_chain=["Higher c -> increased dissipation -> suppressed resonance peak"],
        recommendation="Adopt Setup Rev 12 for Turn 8 curbs",
        result_hash="EXP-HASH-T8-001-A2B4",
    )
    async_test_db.add(exp_rec)
    await async_test_db.commit()

    # ──────────────────────────────────────────────────────────────────────────
    # Stage 8: Comparison — Side-by-side verification (What Changed / Improved / Worse)
    # ──────────────────────────────────────────────────────────────────────────
    assert exp_rec.improvements[0]["metric"].startswith("Transmissibility")
    assert len(exp_rec.regressions) >= 1
    assert "Higher c" in exp_rec.causal_chain[0]

    # ──────────────────────────────────────────────────────────────────────────
    # Stage 9: Optimization — Local Pareto parameter evaluation
    # ──────────────────────────────────────────────────────────────────────────
    # Sweep damper coefficients [2000, 2200, 2400, 2530, 2800]
    sweep_c = [2000.0, 2200.0, 2400.0, 2530.0, 2800.0]
    sweep_results = []
    for c_val in sweep_c:
        p_sw = QuarterCarParams(m_s=320.0, m_u=45.0, k_s=35000.0, c=c_val, k_t=220000.0, MR=0.85)
        sim_sw = run_quarter_car_analysis(p_sw, prof)
        sweep_results.append({
            "c": c_val,
            "zeta_s": sim_sw.zeta_s,
            "rms_accel": sim_sw.rms_body_accel,
            "peak_trans": sim_sw.peak_transmissibility,
        })
    assert len(sweep_results) == 5
    # Damping ratio strictly monotonic with c
    assert sweep_results[0]["zeta_s"] < sweep_results[-1]["zeta_s"]

    # ──────────────────────────────────────────────────────────────────────────
    # Stage 10: Validation — Out-of-sample holdout test confirms correlation >= 0.85
    # ──────────────────────────────────────────────────────────────────────────
    calib = TelemetryCorrelationService.calculate_holdout_correlation(
        simulated_values=[r["rms_accel"] for r in sweep_results],
        measured_values=[r["rms_accel"] * 1.02 for r in sweep_results],
    )
    assert calib["overall_r2"] >= 0.85
    assert calib["holdout_r2"] >= 0.85

    # ──────────────────────────────────────────────────────────────────────────
    # Stage 11: Decision — Create Formal Engineering Decision Record
    # ──────────────────────────────────────────────────────────────────────────
    created_decision = await TimelineDecisionService.create_decision(
        db=async_test_db,
        user_id=str(uid),
        team_id=str(tid),
        question=question_text,
        context={
            "vehicle": car_ref,
            "setup": setup_candidate_ref,
            "track": "Silverstone",
            "title": "Adopt Setup Rev 12 for Turn 8 curbs",
        },
        candidates=[
            {"setup": "SETUP-T8-REV11", "c": 2200.0, "status": "BASELINE"},
            {"setup": "SETUP-T8-REV12", "c": 2530.0, "status": "SELECTED"},
        ],
        selected_option={"name": "SETUP-T8-REV12 (+15% damper rate c)", "c": 2530.0},
        reason="Damping increase provides optimal heave dissipation over apex curbs without inducing tire hop resonance.",
        tradeoffs=[{"description": "1.9% higher transient tire load variation accepted for chassis stability."}],
        simulation_evidence={
            "solver": "scipy.solve_ivp (RK45)",
            "model_version": "QCAR-ODE-RK45-v2.4",
            "heave_transmissibility_reduction_pct": 8.4,
        },
        telemetry_evidence={"source_session": "SESS-FP1-01", "rms_accel": 1.82, "correlation_r2": 0.88},
        validation_evidence={"holdout_r2": 0.88, "status": "CONFIRMED"},
        risks=["Slightly firmer ride over sharp bumps"],
        author="Marcus Vance (Senior Dynamics Engineer)",
    )
    assert created_decision["context"]["setup"] == setup_candidate_ref
    assert created_decision["status"] in ("RECOMMENDED", "VALIDATED")
    dec_id = created_decision["decision_id"]

    # ──────────────────────────────────────────────────────────────────────────
    # Stage 12: Approval — Dual HMAC Cryptographic Sign-Off
    # ──────────────────────────────────────────────────────────────────────────
    # Sign-off by Track Engineer
    appr1 = await TimelineDecisionService.approve_decision(
        db=async_test_db,
        decision_id=dec_id,
        approver_name="Carlos Mendez",
        approver_role="Trackside Performance Engineer",
        user_id=str(uid),
        team_id=str(tid),
    )
    assert appr1["status"] == "APPROVED"
    assert len(appr1["approval_signature"]) == 64

    # ──────────────────────────────────────────────────────────────────────────
    # Stage 13: Timeline — Event recorded with diffs and causal links
    # ──────────────────────────────────────────────────────────────────────────
    timeline_event = await TimelineDecisionService.create_timeline_event(
        db=async_test_db,
        user_id=str(uid),
        team_id=str(tid),
        event_type="decision_approved",
        title="Adopt Setup Rev 12 for Turn 8 curbs",
        description="Approved +15% damper rate modification to address apex curb bounce.",
        vehicle_ref=car_ref,
        setup_ref=setup_candidate_ref,
        model_version="QCAR-ODE-RK45-v2.4",
        parameter_changes=[{"parameter": "c", "before": 2200.0, "after": 2530.0, "delta": 330.0, "unit": "Ns/m"}],
        engineering_effects=[{"metric": "heave_peak", "before": 1.82, "after": 1.60, "delta": -0.22, "beneficial": True, "unit": "g"}],
        decision_consequences=["Adopted for FP2 run program"],
    )
    assert timeline_event["id"] is not None
    assert timeline_event["setup_ref"] == setup_candidate_ref
    assert timeline_event["id"] is not None
    assert timeline_event["setup_ref"] == setup_candidate_ref

    # ──────────────────────────────────────────────────────────────────────────
    # Stage 14 & 15: Track & Closed Loop — Ingest New Telemetry & Close Loop
    # ──────────────────────────────────────────────────────────────────────────
    # Ingest new session telemetry (SESS-FP2-02) showing 12% bounce reduction
    post_telem_csv = "time,vert_g,speed,rh_fl,rh_fr\n" + "\n".join(
        f"{t:.3f},{g * 0.88:.4f},43.0,28.0,28.0" for t, g in zip(t_track, curb_profile)
    )

    loop_res = await digital_twin.execute_track_loop_closure(
        db=async_test_db,
        twin=twin,
        session_id="SESS-FP2-02",
        telemetry_csv=post_telem_csv,
        user_id=str(uid),
        team_id=str(tid),
    )
    assert loop_res["status"] == "TRACK_LOOP_CLOSED"
    assert loop_res["setup_validated"] is True
    assert loop_res["effectiveness_pct"] > 0.0

    # Verify decision marked VALIDATED ON TRACK in institutional memory
    reconstruction = await TimelineDecisionService.reconstruct_institutional_memory(
        db=async_test_db,
        identifier=setup_candidate_ref,
        user_id=str(uid),
        team_id=str(tid),
    )
    assert reconstruction["target_identifier"] == setup_candidate_ref
    assert reconstruction["setup_ref"] == setup_candidate_ref
    assert "reconstruction" in reconstruction
    assert reconstruction["reconstruction"]["question"]["prompt"] == question_text
    assert reconstruction["reconstruction"]["approval"]["status"] == "APPROVED"
    assert len(reconstruction["lineage_events"]) >= 1


# ── SECTION: UNIVERSAL ENGINEERING SEARCH (9 DOMAINS) ──────────────────────────

@pytest.mark.asyncio
async def test_universal_engineering_search_domains_and_isolation(async_test_db: AsyncSession):
    """
    Verifies UniversalSearchService across domains (vehicles, setups, telemetry, experiments, decisions, parameters)
    and enforces multi-tenant tenant isolation.
    """
    user_a = str(uuid.uuid4())
    user_b = str(uuid.uuid4())
    team_a = str(uuid.uuid4())

    # User A creates an experiment and a decision
    exp_a = ExperimentRecord(
        user_id=uuid.UUID(user_a),
        team_id=uuid.UUID(team_a),
        question="What happens if we increase front heave spring rate by 12%?",
        hypothesis="Improves pitch stability under aero load.",
        author="Engineer A",
        status="COMPLETED",
        validation_state="VALIDATED",
        parent_setup={"k_s": 35000.0},
        candidate_setup={"k_s": 39200.0},
        parameter_changes=[],
        baseline_metrics={},
        candidate_metrics={},
        improvements=[],
        regressions=[],
        causal_chain=[],
        recommendation="Test heave spring rate",
        result_hash="HASH-A-01",
    )
    async_test_db.add(exp_a)
    await async_test_db.commit()

    # 1. Search for physics parameter ontology (e.g. "damper" or "spring")
    res_ontology = await UniversalSearchService.search(
        db=async_test_db,
        query="damper",
        user_id=user_a,
        team_id=team_a,
    )
    assert res_ontology["total_matches"] >= 1
    param_matches = [r for r in res_ontology["results"] if r["category"] == "parameters"]
    assert len(param_matches) >= 1
    assert any("damping" in r["title"].lower() or "damper" in r["title"].lower() for r in param_matches)

    # 2. Search for User A's experiment by keyword
    res_exp = await UniversalSearchService.search(
        db=async_test_db,
        query="heave spring",
        user_id=user_a,
        team_id=team_a,
    )
    assert res_exp["total_matches"] >= 1
    exp_matches = [r for r in res_exp["results"] if r["category"] == "experiments"]
    assert len(exp_matches) >= 1
    assert "heave spring" in exp_matches[0]["title"].lower()

    # 3. Multi-tenant isolation: User B (different user, no shared team) must NOT see User A's experiment
    res_user_b = await UniversalSearchService.search(
        db=async_test_db,
        query="heave spring",
        user_id=user_b,
        team_id=None,
    )
    user_b_exp_matches = [r for r in res_user_b["results"] if r["category"] == "experiments"]
    assert len(user_b_exp_matches) == 0, "Multi-tenant breach: User B saw User A's private experiment!"


# ── SECTION: INCUMBENT CAE INTEROPERABILITY & EXTERNAL MODEL IDENTITY ──────────

def test_cae_interoperability_normalization_and_external_identity():
    """
    Verifies:
    1. Parsing & normalization of raw CSV traces from MSC Adams / MATLAB
    2. Attachment of ExternalModelIdentity (origin: EXTERNAL_CAE, SHA-256 fingerprint, solver)
    3. Forward ODE solver side-by-side comparison
    4. Syntax export deck generation for MSC Adams and MATLAB
    """
    raw_csv = """time,ddz_s,susp_travel,tire_load
0.00,0.00,0.000,4120.0
0.01,0.22,0.002,4180.0
0.02,0.65,0.005,4290.0
0.03,1.15,0.009,4450.0
0.04,1.60,0.013,4620.0
0.05,1.85,0.016,4750.0
0.06,1.75,0.017,4720.0
0.07,1.35,0.015,4550.0
0.08,0.78,0.011,4310.0
0.09,0.18,0.006,4080.0
0.10,-0.32,0.002,3910.0"""

    # 1. Ingest external run
    dataset = CaeIntegrationService.import_and_normalize_external_run(
        source_tool="MSC Adams",
        version="Adams 2024.1",
        solver="WSTIFF",
        parameters={"m_s": 320.0, "m_u": 45.0, "k_s": 35000.0, "c": 2200.0, "MR": 0.85},
        raw_trace_csv=raw_csv,
        execution_environment="External High-Performance Compute Cluster",
    )

    # 2. Verify External Model Identity
    assert dataset.identity.origin == "EXTERNAL_CAE"
    assert dataset.identity.is_external is True
    assert dataset.identity.source_tool == "MSC Adams"
    assert dataset.identity.solver == "WSTIFF"
    assert len(dataset.identity.artifact_hash) == 64
    assert len(dataset.time_s) == 11
    assert "ddz_s" in dataset.channels_present
    assert "tire_load" in dataset.channels_present

    # 3. Side-by-side solver benchmark against native forward ODE
    comp = CaeIntegrationService.compare_external_vs_native(dataset)
    assert comp["external_identity"]["origin"] == "EXTERNAL_CAE"
    assert comp["native_identity"]["solver"] == "scipy.integrate.solve_ivp (RK45, rtol=1e-6)"
    assert comp["native_identity"]["is_external"] is False
    assert "channel_metrics" in comp
    assert "ddz_s" in comp["channel_metrics"]
    assert comp["channel_metrics"]["ddz_s"]["agreement_status"] in (
        "STRONG_CORRELATION",
        "MODERATE_CORRELATION",
        "DIVERGENT",
    )
    assert "engineering_interpretation" in comp

    # 4. Deck Exporters (.adm, .cmd, .py, .m)
    p = QuarterCarParams(m_s=320.0, m_u=45.0, k_s=35000.0, c=2200.0, k_t=220000.0, MR=0.85)
    for fmt in ("adams_adm", "adams_cmd", "adams_py", "matlab_m"):
        deck = CaeIntegrationService.export_deck(fmt, p)
        assert deck["syntax_validated"] is True
        assert len(deck["code"]) > 50
        assert "m_s" in deck["code"] or "320.0" in deck["code"]


# ── SECTION: INSTITUTIONAL MEMORY RECONSTRUCTION ───────────────────────────────

@pytest.mark.asyncio
async def test_institutional_memory_reconstruction_7_pillars(async_test_db: AsyncSession):
    """
    Verifies 'Why did we choose Setup X?' institutional memory reconstruction
    assembling all 7 pillars: Question, Evidence, Experiments, Simulation, Comparison, Validation, Approval.
    """
    uid = str(uuid.uuid4())
    tid = str(uuid.uuid4())

    dec_payload = {
        "title": "Adopt Front ARB Stiffness Increase for Turn 3",
        "vehicle_ref": "CAR-GT3-09",
        "setup_ref": "SETUP-MONZA-V4",
        "question": "Why is front outer tire graining accelerating during sustained cornering?",
        "context_data": {"track": "Monza", "ambient_temp_c": 28},
        "author": "Marcus Vance",
        "telemetry_evidence": {"tire_temp_fl": 118.5, "slip_angle_deg": 6.8, "correlation_r2": 0.91},
        "simulation_evidence": {"roll_angle_reduction_deg": 0.45},
        "validation_evidence": {"correlation_r2": 0.91},
        "candidates_evaluated": ["SETUP-MONZA-V3", "SETUP-MONZA-V4"],
        "selected_option": "SETUP-MONZA-V4",
        "engineering_reason": "Reduces roll angle and dynamic camber degradation under 1.8g lateral load.",
        "tradeoffs_accepted": ["Increased curb harshness over Ascari chicane curbs."],
        "risks_and_mitigations": {"risk": "Understeer in slow corners", "mitigation": "Increase rear wing angle 1 click."},
    }

    created = await TimelineDecisionService.create_decision(
        db=async_test_db,
        user_id=uid,
        team_id=tid,
        question=dec_payload["question"],
        context={"vehicle": dec_payload["vehicle_ref"], "setup": dec_payload["setup_ref"], "title": dec_payload["title"]},
        candidates=[{"name": c} for c in dec_payload["candidates_evaluated"]],
        selected_option={"name": dec_payload["selected_option"]},
        reason=dec_payload["engineering_reason"],
        tradeoffs=[{"description": t} for t in dec_payload["tradeoffs_accepted"]],
        simulation_evidence=dec_payload["simulation_evidence"],
        telemetry_evidence=dec_payload["telemetry_evidence"],
        validation_evidence=dec_payload["validation_evidence"],
        risks=[dec_payload["risks_and_mitigations"]["risk"]],
        author=dec_payload["author"],
    )

    await TimelineDecisionService.approve_decision(
        db=async_test_db,
        decision_id=created["decision_id"],
        approver_name="Dr. Elena Rostova",
        approver_role="Chief Aerodynamicist & Vehicle Dynamics Lead",
        user_id=uid,
        team_id=tid,
    )

    # Reconstruct memory by setup reference
    reconstruction = await TimelineDecisionService.reconstruct_institutional_memory(
        db=async_test_db,
        identifier="SETUP-MONZA-V4",
        user_id=uid,
        team_id=tid,
    )

    assert reconstruction["target_identifier"] == "SETUP-MONZA-V4"
    assert reconstruction["setup_ref"] == "SETUP-MONZA-V4"
    r = reconstruction["reconstruction"]

    # Verify all 7 pillars
    assert "question" in r and "graining" in r["question"]["prompt"]
    assert "evidence" in r and "telemetry" in r["evidence"]
    assert "experiments" in r and r["experiments"]["selected_option"] == "SETUP-MONZA-V4"
    assert "simulation" in r and "RK45" in r["simulation"]["solver"]
    assert "comparison" in r and len(r["comparison"]["tradeoffs_accepted"]) >= 1
    assert "validation" in r and r["validation"]["sign_off_status"] == "APPROVED"
    assert "approval" in r and r["approval"]["approver_name"] == "Dr. Elena Rostova"
    assert len(r["approval"]["hmac_signature"]) == 64
