"""
tests/test_ai_engineer_copilot.py
=================================
Automated verification for SuspensionLab PRO AI Race Engineer Copilot:
1. Target Question Experience:
   "Why is front tire saturation increasing in Turn 7?"
   - Inspects telemetry -> slip angles & roll distribution -> forward simulation ->
     formulates hypothesis -> states uncertainty -> proposes experiment -> enforces approval gate.
2. Workflow 1: "Why did lap time get worse?"
   - Compares laps -> identifies correlated factors -> inspects simulation -> proposes experiment.
3. Workflow 2: "Try reducing rear roll stiffness by 10%."
   - Creates reproducible experiment -> executes real simulation -> compares baseline -> reports result.
4. Workflow 3: "Why is model correlation poor?"
   - Residual analysis -> identifies problematic channels -> explains uncertainty -> recommends calibration.
5. Workflow 4: "What changed between Setup 17 and Setup 23?"
   - Setup comparison -> parameter differences -> CAE artifacts -> timeline decisions.
6. Envelope Standardization:
   - Verifies all tool outputs conform to authoritative 7-field envelope:
     source, object/run ID, timestamp, model/version, parameters, provenance, result status.
7. Approval Gate & Non-Negotiable Governance:
   - Blocks autonomous sign-off by AI.
   - Permits authorized human sign-off with HMAC-SHA256 signature.
"""

import pytest
import uuid

from suspensionlab.physics.ai_engineering_authority import (
    AIEngineeringToolRegistry,
    RBACPermissionDenied,
)
from suspensionlab.backend.api.routes.ai_engineer_routes import (
    AIChatRequest,
    AIChatResponse,
    ApprovalGateRequest,
    ai_race_engineer_chat,
    approve_ai_decision,
    DEFAULT_PARAMS,
)
from suspensionlab.backend.security.auth import UserContext


@pytest.fixture
def chief_engineer():
    return UserContext(
        user_id=str(uuid.uuid4()),
        plan="enterprise",
        email="chief.engineer@f1-paddock.com",
        name="Dr. Marcus Weber",
        onboarding_complete=True,
        team_id=str(uuid.uuid4()),
        team_role="chief_engineer",
    )


@pytest.fixture
def race_engineer():
    return UserContext(
        user_id=str(uuid.uuid4()),
        plan="enterprise",
        email="race.engineer@f1-paddock.com",
        name="Elena Rostova",
        onboarding_complete=True,
        team_id=str(uuid.uuid4()),
        team_role="engineer",
    )


# ── 1. Target Question: Turn 7 Tire Saturation ───────────────────────────────

@pytest.mark.asyncio
async def test_target_question_turn7_front_tire_saturation(chief_engineer):
    """
    Target Question Experience:
    'Why is front tire saturation increasing in Turn 7?'
    AI must:
    - Inspect available telemetry evidence
    - Call real tools
    - Formulate 5-part contract response
    - Classify as HYPOTHESIZED / CORRELATED (no fake root cause)
    - Require human approval gate
    """
    req = AIChatRequest(
        problem="Why is front tire saturation increasing in Turn 7?",
        params=DEFAULT_PARAMS.copy(),
    )
    resp = await ai_race_engineer_chat(req, user=chief_engineer)

    # 1. 5-Part Contract Enforced
    assert resp.answer is not None and len(resp.answer) > 20
    assert resp.engineering_interpretation is not None and len(resp.engineering_interpretation) > 20
    assert resp.uncertainty is not None and len(resp.uncertainty) > 20
    assert resp.next_action is not None and len(resp.next_action) > 20
    assert resp.structured_response is not None

    for section in [
        "### ANSWER",
        "### EVIDENCE",
        "### ENGINEERING INTERPRETATION",
        "### UNCERTAINTY",
        "### NEXT ACTION",
    ]:
        assert section in resp.structured_response

    # 2. Epistemic Classification
    assert resp.epistemic_classification == "HYPOTHESIZED"
    assert any(b.get("epistemic_status") == "MEASURED" for b in resp.epistemic_badges)

    # 3. Real Tool Execution
    tool_names = [t.get("tool_name") or t.get("object_id") or t.get("source") for t in resp.tool_calls]
    assert len(resp.tool_calls) >= 3

    # 4. Human Approval Gate
    assert resp.approval_gate is not None
    assert resp.approval_gate["required"] is True
    assert resp.approval_gate["status"] == "PENDING_APPROVAL"
    assert resp.approval_gate["decision_id"] == "EXP-T7-SAT-2026"


# ── 2. Workflow 1: Lap Time Worsening ────────────────────────────────────────

@pytest.mark.asyncio
async def test_workflow_1_lap_time_degradation(race_engineer):
    """
    Workflow 1:
    'Why did lap time get worse on lap 14?'
    AI must compare telemetry laps, identify correlated factors, and propose an experiment.
    """
    req = AIChatRequest(
        problem="Why did lap time get worse on Lap 14?",
        params=DEFAULT_PARAMS.copy(),
    )
    resp = await ai_race_engineer_chat(req, user=race_engineer)

    assert resp.workflow == "lap_time_degradation"
    assert resp.epistemic_classification in ["CORRELATED", "SIMULATED"]
    assert "### ANSWER" in resp.structured_response
    assert "### EVIDENCE" in resp.structured_response
    assert "### NEXT ACTION" in resp.structured_response

    # Telemetry and correlation evidence
    assert len(resp.tool_calls) >= 3
    assert resp.approval_gate is not None
    assert resp.approval_gate["status"] == "PENDING_APPROVAL"


# ── 3. Workflow 2: Reduce Rear Roll Stiffness by 10% ─────────────────────────

@pytest.mark.asyncio
async def test_workflow_2_reduce_rear_roll_stiffness(race_engineer):
    """
    Workflow 2:
    'Try reducing rear roll stiffness by 10%.'
    AI must create reproducible experiment, execute simulation, and report actual result.
    """
    req = AIChatRequest(
        problem="Try reducing rear roll stiffness by 10%.",
        params=DEFAULT_PARAMS.copy(),
    )
    resp = await ai_race_engineer_chat(req, user=race_engineer)

    assert resp.workflow == "reduce_rear_roll_stiffness"
    assert resp.epistemic_classification == "SIMULATED"
    assert len(resp.best_feasible) > 0
    # Parameter change delta should be -10.0%
    rear_arb_change = next(c for c in resp.best_feasible if c.parameter == "k_arb_r")
    assert rear_arb_change.change_pct == -10.0
    assert resp.simulated is True
    assert resp.approval_gate is not None
    assert resp.approval_gate["required"] is True


# ── 4. Workflow 3: Model Correlation Drop ────────────────────────────────────

@pytest.mark.asyncio
async def test_workflow_3_model_correlation_poor(chief_engineer):
    """
    Workflow 3:
    'Why is model correlation poor?'
    AI must inspect residuals, identify problematic channels, explain uncertainty, and propose calibration.
    """
    req = AIChatRequest(
        problem="Why is model correlation poor with track data?",
        params=DEFAULT_PARAMS.copy(),
    )
    resp = await ai_race_engineer_chat(req, user=chief_engineer)

    assert resp.workflow == "model_correlation_investigation"
    assert resp.epistemic_classification == "ESTIMATED"
    assert "R²" in resp.structured_response or "correlation" in resp.structured_response.lower()
    assert resp.approval_gate is not None
    assert resp.approval_gate["decision_id"] == "CALIB-NONLIN-DAMPER"


# ── 5. Workflow 4: Setup 17 vs Setup 23 Comparison ───────────────────────────

@pytest.mark.asyncio
async def test_workflow_4_setup_diff(chief_engineer):
    """
    Workflow 4:
    'What changed between Setup 17 and Setup 23?'
    AI must retrieve setup metadata, compare parameters, retrieve CAE simulation artifacts, and summarize consequences.
    """
    req = AIChatRequest(
        problem="What changed between Setup 17 and Setup 23?",
        params=DEFAULT_PARAMS.copy(),
    )
    resp = await ai_race_engineer_chat(req, user=chief_engineer)

    assert resp.workflow == "setup_comparison_diff"
    assert resp.epistemic_classification == "SIMULATED"
    assert len(resp.best_feasible) >= 3
    # Check that front spring and damping changes are present
    param_names = [c.parameter for c in resp.best_feasible]
    assert "k_sf" in param_names
    assert "c" in param_names
    assert resp.approval_gate is not None
    assert resp.approval_gate["decision_type"] == "SETUP_PROMOTION"


# ── 6. Tool Metadata Envelope Standardization ────────────────────────────────

def test_tool_metadata_envelope_standardization(chief_engineer):
    """
    Every deterministic tool in AIEngineeringToolRegistry must wrap results in
    the authoritative 7-field envelope:
    - source
    - object/run ID
    - timestamp
    - model/version
    - parameters
    - provenance (SHA-256 hash)
    - result status
    """
    tools_to_test = [
        ("run_simulation", {"params": {"k_s": 28000.0, "c": 2100.0}}),
        ("run_kinematics", {}),
        ("analyze_telemetry", {"session_id": "SESS-001"}),
        ("get_residuals", {"run_id": "RUN-001"}),
        ("get_constraints", {}),
        ("get_model_validity", {"params": DEFAULT_PARAMS.copy()}),
        ("compare_setups", {}),
        ("query_telemetry", {"session_id": "SESS-001", "lap": 12}),
        ("analyze_telemetry_correlation", {"session_id": "SESS-001"}),
        ("get_vehicle_state", {"vehicle_id": "CAR-01"}),
        ("inspect_parameters", {}),
        ("lookup_provenance", {"item_id": "SETUP-01"}),
        ("lookup_cae_artifacts", {"run_id": "RUN-01"}),
        ("lookup_timeline_decisions", {"vehicle_ref": "CAR-01"}),
    ]

    for tool_name, args in tools_to_test:
        envelope = AIEngineeringToolRegistry.execute_tool(tool_name, args, user_context=chief_engineer)
        # All 7 mandatory envelope fields must be present
        assert "source" in envelope, f"Missing source in {tool_name}"
        assert "object_id" in envelope or "run_id" in envelope, f"Missing ID in {tool_name}"
        assert "timestamp" in envelope, f"Missing timestamp in {tool_name}"
        assert "model_version" in envelope, f"Missing model_version in {tool_name}"
        assert "parameters" in envelope, f"Missing parameters in {tool_name}"
        assert "provenance" in envelope, f"Missing provenance in {tool_name}"
        assert "result_status" in envelope or "status" in envelope, f"Missing status in {tool_name}"
        # Provenance must have SHA-256 fingerprint
        assert "hash" in envelope["provenance"], f"Missing provenance hash in {tool_name}"


# ── 7. Approval Gate & Governance Enforcement ────────────────────────────────

@pytest.mark.asyncio
async def test_approval_gate_blocks_autonomous_ai(race_engineer):
    """The AI Engineer is strictly prohibited from autonomously signing off decisions."""
    gate_req = ApprovalGateRequest(
        decision_id="EXP-T7-SAT-2026",
        approver_name="",  # Empty approver indicates autonomous attempt
        autonomous_request=True,
    )
    with pytest.raises(Exception) as exc_info:
        await approve_ai_decision(gate_req, user=race_engineer)
    # Must reject with 403 Forbidden
    assert "403" in str(exc_info.value) or "Autonomous AI sign-off forbidden" in str(exc_info.value)


@pytest.mark.asyncio
async def test_approval_gate_accepts_authorized_human(chief_engineer, monkeypatch):
    """Authorized human engineers can sign off decisions with HMAC-SHA256 audit trail."""
    gate_req = ApprovalGateRequest(
        decision_id="EXP-T7-SAT-2026",
        approver_name="Dr. Marcus Weber",
        approver_role="chief_engineer",
        autonomous_request=False,
        decision_type="SETUP_MODIFICATION",
        rationale="Telemetry confirms front slip saturation; 10% front ARB softening approved for FP2.",
    )
    # Wave 6: the route now writes a hash-chained audit record. Direct-call test, so
    # pass a stand-in db and capture the record instead of hitting a database.
    import suspensionlab.backend.security.audit as audit_mod
    audit_calls = []

    async def fake_record_audit_event(db, event_type, **kw):
        audit_calls.append({"event_type": event_type, **kw})

    monkeypatch.setattr(audit_mod, "record_audit_event", fake_record_audit_event)
    res = await approve_ai_decision(gate_req, user=chief_engineer, db=object())

    assert len(audit_calls) == 1 and audit_calls[0]["event_type"] == "ai.decision.approved"
    assert res["result_status"] == "SUCCESS"
    assert res["approval_status"] == "APPROVED"
    assert res["approver_name"] == "Dr. Marcus Weber"
    assert "signature_hmac_sha256" in res
    assert len(res["signature_hmac_sha256"]) == 64
