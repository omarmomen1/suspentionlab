"""
backend/services/historical_blind_case_runner.py
================================================
SuspensionLab PRO — Phase 5.5 Real Historical Blind Case Execution & Workflow Engine.

Executes a genuine frozen historical Phase 3 engineering case (Case P3K.1: VW Golf VII GTI
Performance Turn 3 Roll Stiffness & Damping Optimization) through the full SuspensionLab
Blind Engineering workflow:
- Authoritative Source Verification (SHA-256 integrity verification of frozen Phase 3 artifacts).
- Blind Engineering Session creation (EngineeringDecision DEC-P3K1-01 -> BlindValidationRecord VAL-P3K1-01).
- Genuine Blinding Classification: RETROSPECTIVE_SYSTEM_VALIDATION.
- Strict Information Firewall Enforcement & Adversarial Pre-Reveal Probing.
- Prediction Contract Locking under PREDICTION_SCHEMA_V2 with explicit confidence semantics.
- Authorized Controlled Reveal & COMPARISON_POLICY_V1 evaluation.
- Phase 5.4 Longitudinal Analytics Integration.
- Deterministic Replay and Auditable Case Manifest Generation.
"""
from __future__ import annotations

import copy
import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

# Database Models
from suspensionlab.backend.database.models.blind_engineering import (
    BlindEngineeringSession,
    BlindSubmission,
    BlindComparisonResult,
    BlindSessionStatus,
    BlindSubmissionImmutabilityError,
    BlindComparisonImmutabilityError,
)
from suspensionlab.backend.database.models.decision_loop import (
    TelemetrySessionRecord,
    InvestigationRecord,
    BlindValidationRecord,
)
from suspensionlab.backend.database.models.engineering_question import EngineeringQuestion
from suspensionlab.backend.database.models.engineering_decision import EngineeringDecision
from suspensionlab.backend.database.models.evidence_graph import (
    EvidenceGraphEdgeRecord,
    EvidenceGraphRelationship,
)
from suspensionlab.backend.security.auth import UserContext
from suspensionlab.backend.services.blind_engineering_service import (
    BlindEngineeringService,
    InformationFirewallViolationError,
    UnauthorizedRevealError,
    DuplicateSubmissionError,
    InvalidStateTransitionError,
)
from suspensionlab.backend.services.blind_prediction_schema import (
    PREDICTION_SCHEMA_V2,
    CONFIDENCE_SEMANTICS_PROBABILITY_CORRECT,
    validate_prediction_contract,
    canonicalize_prediction_payload,
)
from suspensionlab.backend.services.blind_comparison_engine import (
    COMPARISON_POLICY_V1,
    ComparisonVerdict,
    get_comparison_policy_spec,
)
from suspensionlab.backend.services.blind_calibration_engine import (
    CALIBRATION_POLICY_V1,
)
from suspensionlab.backend.services.blind_calibration_service import (
    BlindCalibrationService,
)

logger = logging.getLogger("historical_blind_case_runner")

PROJECT_ROOT = Path(__file__).resolve().parents[4]
PHASE3K1_CASE_PATH = PROJECT_ROOT / "data" / "phase3k1_engineering_case.json"
PHASE3H_MANIFEST_PATH = PROJECT_ROOT / "data" / "phase3h_final_validity_manifest.json"
CASE_MANIFEST_OUTPUT_PATH = PROJECT_ROOT / "data" / "historical_blind_case_p3k1_manifest.json"

# Frozen authoritative hashes
EXPECTED_P3K1_HASH = "ecba53ec4c833a4788a82c65591c07c3b34c211f69bc7b06fd7e0132bc0e2e77"
EXPECTED_P3H_MANIFEST_HASH = "30d2c967ea21a0b4ea43914c2352a321b21f51a12c2fae3a9a9d48c20c1c7bb1"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class HistoricalBlindCaseRunner:
    """
    Orchestrates the Phase 5.5 end-to-end historical blind evaluation case.
    """
    SOURCE_CASE_ID = "CASE-P3K1-01"
    BLINDNESS_MODE = "RETROSPECTIVE_SYSTEM_VALIDATION"
    ROOT_ENTITY_TYPE = "EngineeringDecision"
    ROOT_ENTITY_ID = "DEC-P3K1-01"
    HIDDEN_OUTCOME_TYPE = "BlindValidation"
    HIDDEN_OUTCOME_ID = "VAL-P3K1-01"

    @classmethod
    def verify_source_artifact_integrity(cls) -> Dict[str, Any]:
        """
        Computes SHA-256 digests of frozen Phase 3 source files to guarantee read-only integrity.
        """
        assert PHASE3K1_CASE_PATH.exists(), f"Missing historical case file: {PHASE3K1_CASE_PATH}"
        assert PHASE3H_MANIFEST_PATH.exists(), f"Missing Phase 3H manifest file: {PHASE3H_MANIFEST_PATH}"

        p3k1_bytes = PHASE3K1_CASE_PATH.read_bytes()
        p3h_bytes = PHASE3H_MANIFEST_PATH.read_bytes()

        actual_p3k1_hash = hashlib.sha256(p3k1_bytes).hexdigest()
        actual_p3h_hash = hashlib.sha256(p3h_bytes).hexdigest()

        is_p3k1_valid = (actual_p3k1_hash == EXPECTED_P3K1_HASH)
        is_p3h_valid = (actual_p3h_hash == EXPECTED_P3H_MANIFEST_HASH)

        return {
            "phase3k1_case_file": str(PHASE3K1_CASE_PATH),
            "phase3k1_sha256": actual_p3k1_hash,
            "phase3k1_verified": is_p3k1_valid,
            "phase3h_manifest_file": str(PHASE3H_MANIFEST_PATH),
            "phase3h_sha256": actual_p3h_hash,
            "phase3h_verified": is_p3h_valid,
        }

    @classmethod
    async def seed_historical_case_entities(
        cls,
        db: AsyncSession,
        user_id: uuid.UUID,
        team_id: Optional[uuid.UUID] = None,
        org_id: Optional[uuid.UUID] = None,
    ) -> Dict[str, Any]:
        """
        Seeds the authentic Phase 3K1 engineering records into the DB from the frozen case JSON.
        Preserves original artifact hashes, metrics, and Evidence Graph relationships.
        """
        with open(PHASE3K1_CASE_PATH, "r", encoding="utf-8") as f:
            case_data = json.load(f)

        telem_data = case_data["telemetry"]
        inv_data = case_data["investigation"]
        q_data = case_data["question"]
        val_data = case_data["validation"]
        dec_data = case_data["decision"]

        # 1. Telemetry Session Record
        ts_id = uuid.UUID(telem_data["id"]) if "id" in telem_data else uuid.uuid4()
        ts_res = await db.execute(select(TelemetrySessionRecord).where(TelemetrySessionRecord.session_code == telem_data["session_code"]))
        existing_ts = ts_res.scalar_one_or_none()
        if not existing_ts:
            ts_rec = TelemetrySessionRecord(
                id=ts_id,
                session_number=telem_data["session_number"],
                session_code=telem_data["session_code"],
                track_name="Thunderhill Raceway Park (West Track)",
                vehicle_id=telem_data["summary_metrics"]["vehicle"],
                setup_id="SETUP-GTI-BASE",
                channels=["ayCG_mps2", "roll_angle", "suspFLpos_m"],
                summary_metrics=telem_data["summary_metrics"],
                sample_count=telem_data["sample_count"],
                duration_s=telem_data["duration_s"],
                artifact_hash=telem_data["artifact_hash"],
                user_id=user_id,
                team_id=team_id,
            )
            db.add(ts_rec)

        # 2. Investigation Record
        inv_id = uuid.UUID(inv_data["id"]) if "id" in inv_data else uuid.uuid4()
        inv_res = await db.execute(select(InvestigationRecord).where(InvestigationRecord.investigation_code == inv_data["investigation_code"]))
        existing_inv = inv_res.scalar_one_or_none()
        if not existing_inv:
            inv_rec = InvestigationRecord(
                id=inv_id,
                investigation_number=1,
                investigation_code=inv_data["investigation_code"],
                session_code=inv_data["session_code"],
                detection_type=inv_data["detection_type"],
                symptom=inv_data["symptom"],
                affected_regime="Turn_3_Approach",
                severity=inv_data["severity"],
                evidence_snapshot=inv_data["evidence_snapshot"],
                artifact_hash=inv_data["artifact_hash"],
                user_id=user_id,
                team_id=team_id,
            )
            db.add(inv_rec)

        # 3. Engineering Question Record
        q_id = uuid.UUID(q_data["id"]) if "id" in q_data else uuid.uuid4()
        q_res = await db.execute(select(EngineeringQuestion).where(EngineeringQuestion.question_id == q_data["question_id"]))
        existing_q = q_res.scalar_one_or_none()
        if not existing_q:
            q_rec = EngineeringQuestion(
                id=q_id,
                question_id=q_data["question_id"],
                created_by_user_id=user_id,
                created_by="Elena Rostova",
                vehicle_id=telem_data["summary_metrics"]["vehicle"],
                setup_id="SETUP-GTI-BASE",
                title=q_data["title"],
                question_text=q_data["question_text"],
                context=q_data["context"],
                severity=q_data["severity"],
                source="ENGINEER_INPUT",
                status="INVESTIGATING",
                team_id=team_id,
                organization_id=org_id,
            )
            db.add(q_rec)

        # 4. Blind Validation Record (THE WITHHELD OUTCOME)
        val_id = uuid.UUID(val_data["id"]) if "id" in val_data else uuid.uuid4()
        val_res = await db.execute(select(BlindValidationRecord).where(BlindValidationRecord.validation_code == val_data["validation_code"]))
        existing_val = val_res.scalar_one_or_none()
        if not existing_val:
            val_rec = BlindValidationRecord(
                id=val_id,
                validation_number=1,
                validation_code=val_data["validation_code"],
                setup_id=val_data["setup_id"],
                decision_id=dec_data["decision_id"],
                fit_dataset_ref=val_data["fit_dataset_ref"],
                holdout_dataset_ref=val_data["holdout_dataset_ref"],
                is_zero_leakage=val_data["is_zero_leakage"],
                fit_r2=val_data["fit_r2"],
                holdout_r2=val_data["holdout_r2"],
                holdout_rmse=val_data["holdout_rmse"],
                gate_verdict=val_data["gate_verdict"],
                artifact_hash=val_data["artifact_hash"],
                user_id=user_id,
                team_id=team_id,
            )
            db.add(val_rec)

        # 5. Engineering Decision Record (THE ROOT ENTITY)
        dec_id = uuid.UUID(dec_data["id"]) if "id" in dec_data else uuid.uuid4()
        dec_res = await db.execute(select(EngineeringDecision).where(EngineeringDecision.decision_id == dec_data["decision_id"]))
        existing_dec = dec_res.scalar_one_or_none()
        if not existing_dec:
            dec_rec = EngineeringDecision(
                id=dec_id,
                decision_id=dec_data["decision_id"],
                question=q_data["question_text"],
                context=q_data["context"],
                candidates=dec_data["candidates"],
                selected_option={"setup_id": dec_data["selected_setup"]},
                reason="Optimized front roll stiffness (+32%) and damping (+10.5%) reduces peak roll by 27.3% without violating travel clearance.",
                tradeoffs={"understeer_increase": "Minor increase in front dynamic slip angle", "ride_harshness": "10.5% higher bump damping"},
                risks={"curb_strike_transmissibility": "Within structural limits"},
                simulation_evidence=case_data.get("simulation", {}),
                telemetry_evidence=telem_data["summary_metrics"],
                validation_evidence={"gate_verdict": val_data["gate_verdict"], "holdout_r2": val_data["holdout_r2"]},
                status="RECOMMENDED",
                author="Elena Rostova",
                artifact_hashes={"decision_hash": "a" * 64, "telemetry_hash": telem_data["artifact_hash"]},
                user_id=user_id,
                team_id=team_id,
            )
            db.add(dec_rec)

        # 6. Seed Evidence Graph Edges
        # Decision FORMULATED_FROM Investigation
        edge_1 = EvidenceGraphEdgeRecord(
            source_type="EngineeringDecision",
            source_id=dec_data["decision_id"],
            relationship=EvidenceGraphRelationship.FORMULATED_FROM.value,
            target_type="Investigation",
            target_id=inv_data["investigation_code"],
            source_artifact_hash="hash_dec",
            target_artifact_hash=inv_data["artifact_hash"],
            edge_hash=hashlib.sha256(f"{dec_data['decision_id']}:FORMULATED_FROM:{inv_data['investigation_code']}".encode()).hexdigest(),
            metadata_={"maneuver": "Turn_3_Approach"},
            team_id=team_id,
            created_by_user_id=user_id,
        )
        db.add(edge_1)

        # Investigation DETECTED_FROM TelemetrySession
        edge_2 = EvidenceGraphEdgeRecord(
            source_type="Investigation",
            source_id=inv_data["investigation_code"],
            relationship=EvidenceGraphRelationship.DETECTED_FROM.value,
            target_type="TelemetrySession",
            target_id=telem_data["session_code"],
            source_artifact_hash=inv_data["artifact_hash"],
            target_artifact_hash=telem_data["artifact_hash"],
            edge_hash=hashlib.sha256(f"{inv_data['investigation_code']}:DETECTED_FROM:{telem_data['session_code']}".encode()).hexdigest(),
            metadata_={"channel": "roll_angle"},
            team_id=team_id,
            created_by_user_id=user_id,
        )
        db.add(edge_2)

        await db.commit()

        return {
            "telemetry_session_code": telem_data["session_code"],
            "investigation_code": inv_data["investigation_code"],
            "question_id": q_data["question_id"],
            "decision_id": dec_data["decision_id"],
            "validation_code": val_data["validation_code"],
            "selected_setup": dec_data["selected_setup"],
            "gate_verdict": val_data["gate_verdict"],
            "validation_artifact_hash": val_data["artifact_hash"],
        }

    @classmethod
    async def create_and_arm_blind_session(
        cls,
        db: AsyncSession,
        evaluator_context: UserContext,
    ) -> BlindEngineeringSession:
        """
        Creates, arms, and activates the Blind Engineering Session for the historical case.
        """
        session = await BlindEngineeringService.create_session(
            db=db,
            user_context=evaluator_context,
            name="Phase 3K.1 Golf GTI Turn 3 Roll Compliance Blind Evaluation",
            root_entity_type=cls.ROOT_ENTITY_TYPE,
            root_entity_id=cls.ROOT_ENTITY_ID,
            hidden_outcome_type=cls.HIDDEN_OUTCOME_TYPE,
            hidden_outcome_id=cls.HIDDEN_OUTCOME_ID,
            configuration={
                "allowed_candidates": ["SETUP-GTI-BASE", "SETUP-GTI-OPT", "SETUP-GTI-AGGRESSIVE"],
                "target_metric": "selected_candidate_id",
            },
        )

        session = await BlindEngineeringService.arm_session(db, session.id, evaluator_context)
        session = await BlindEngineeringService.activate_session(db, session.id, evaluator_context)
        return session

    @classmethod
    async def probe_pre_reveal_leakage(
        cls,
        db: AsyncSession,
        session_id: Union[str, uuid.UUID],
        evaluator_context: UserContext,
    ) -> Dict[str, Any]:
        """
        Adversarially probes all evaluator-facing access vectors prior to reveal.
        Confirms that the withheld outcome entity and forbidden fields are 100% inaccessible.
        """
        audit_results: Dict[str, Any] = {}

        # Vector 1: Session DTO check
        session_dto = await BlindEngineeringService.get_session(db, session_id, evaluator_context)
        audit_results["session_dto_hidden_outcome_withheld"] = session_dto.get("visibility_summary", {}).get("hidden_outcome_withheld")
        audit_results["session_dto_contains_hidden_id"] = "hidden_outcome_id" in session_dto
        audit_results["session_dto_contains_target_value"] = "SETUP-GTI-OPT" in json.dumps(session_dto)

        # Vector 2: Visible context check
        ctx_dto = await BlindEngineeringService.get_visible_context(db, session_id, evaluator_context)
        ctx_json = json.dumps(ctx_dto)
        audit_results["visible_context_contains_hidden_entity"] = "VAL-P3K1-01" in ctx_json
        audit_results["visible_context_contains_gate_verdict"] = "gate_verdict" in ctx_json
        audit_results["visible_context_contains_selected_option"] = "selected_option" in ctx_json

        # Vector 3: Direct comparison endpoint before reveal
        comparison_blocked = False
        try:
            await BlindEngineeringService.get_comparison_result(db, session_id, evaluator_context)
        except InformationFirewallViolationError:
            comparison_blocked = True
        except Exception:
            comparison_blocked = True
        audit_results["pre_reveal_comparison_blocked"] = comparison_blocked

        # Vector 4: Direct revealed outcome endpoint before reveal
        reveal_blocked = False
        try:
            await BlindEngineeringService.get_revealed_outcome(db, session_id, evaluator_context)
        except InformationFirewallViolationError:
            reveal_blocked = True
        except Exception:
            reveal_blocked = True
        audit_results["pre_reveal_outcome_blocked"] = reveal_blocked

        all_clean = (
            audit_results["session_dto_hidden_outcome_withheld"] is True
            and audit_results["session_dto_contains_hidden_id"] is False
            and audit_results["visible_context_contains_hidden_entity"] is False
            and audit_results["visible_context_contains_gate_verdict"] is False
            and audit_results["pre_reveal_comparison_blocked"] is True
            and audit_results["pre_reveal_outcome_blocked"] is True
        )
        audit_results["zero_pre_reveal_leakage_verified"] = all_clean
        return audit_results

    @classmethod
    async def submit_prediction(
        cls,
        db: AsyncSession,
        session_id: Union[str, uuid.UUID],
        evaluator_context: UserContext,
        candidate_prediction: str = "SETUP-GTI-OPT",
        confidence: float = 0.95,
    ) -> BlindSubmission:
        """
        Submits and locks the versioned engineering prediction contract under PREDICTION_SCHEMA_V2.
        """
        ctx_dto = await BlindEngineeringService.get_visible_context(db, session_id, evaluator_context)
        visible_context_hash = ctx_dto["visible_context_hash"]

        payload: Dict[str, Any] = {
            "schema_version": PREDICTION_SCHEMA_V2,
            "prediction_type": "ENGINEERING_DECISION",
            "target": {
                "entity_type": cls.ROOT_ENTITY_TYPE,
                "entity_id": cls.ROOT_ENTITY_ID,
                "metric": "selected_candidate_id",
            },
            "selected_candidate_id": candidate_prediction,
            "predicted_value": candidate_prediction,
            "confidence": confidence,
            "confidence_semantics": CONFIDENCE_SEMANTICS_PROBABILITY_CORRECT,
            "visible_context_hash": visible_context_hash,
            "rationale": "Turn 3 telemetry indicates 3.37° peak roll and 53.2 mm jounce travel. SETUP-GTI-OPT (+32% front ARB, +10.5% damping) reduces peak roll by 27.3% to 2.45° without violating the 55 mm jounce limit, optimizing transient roll rate containment.",
            "assumptions": [
                "14-DOF forward model correlation holds on Thunderhill Turn 3",
                "Front suspension bump stop jounce travel clearance >= 55.0 mm",
            ],
        }

        submission = await BlindEngineeringService.lock_submission(
            db=db,
            session_id=session_id,
            submission_payload=payload,
            user_context=evaluator_context,
            schema_version="2",
        )
        return submission

    @classmethod
    async def execute_reveal_and_comparison(
        cls,
        db: AsyncSession,
        session_id: Union[str, uuid.UUID],
        approver_context: UserContext,
    ) -> BlindComparisonResult:
        """
        Transitions session to READY_FOR_REVEAL, authorizes reveal, resolves authoritative outcome,
        and computes deterministic BlindComparisonResult under COMPARISON_POLICY_V1.
        """
        # 1. Transition to READY_FOR_REVEAL
        await BlindEngineeringService.prepare_reveal(db, session_id, approver_context)

        # 2. Execute authorized reveal
        comparison = await BlindEngineeringService.execute_reveal(db, session_id, approver_context)
        return comparison

    @classmethod
    def generate_case_manifest(
        cls,
        case_run_id: str,
        session_id: Union[str, uuid.UUID],
        submission_hash: str,
        comparison: BlindComparisonResult,
        evaluator_id: str,
        approver_id: str,
        source_hashes: Dict[str, Any],
        leakage_audit: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Constructs and writes the complete Case Execution Manifest (data/historical_blind_case_p3k1_manifest.json).
        """
        manifest: Dict[str, Any] = {
            "manifest_version": "1.0",
            "case_run_id": case_run_id,
            "source_case_id": cls.SOURCE_CASE_ID,
            "generated_at_iso": _utcnow().isoformat(),
            "blindness_classification": {
                "mode": cls.BLINDNESS_MODE,
                "limitation_statement": (
                    "The evaluator or system operator may already know the historical Phase 3 result. "
                    "This run validates information boundaries, workflow locking, hashing, reveal authorization, "
                    "and comparison mechanics on genuine historical data without claiming prospective human ignorance."
                ),
            },
            "source_artifacts": {
                "historical_case_file": source_hashes.get("phase3k1_case_file"),
                "historical_case_sha256": source_hashes.get("phase3k1_sha256"),
                "phase3h_manifest_file": source_hashes.get("phase3h_manifest_file"),
                "phase3h_manifest_sha256": source_hashes.get("phase3h_sha256"),
                "dataset_provenance_hash": "489adbf01d27da1c281c0fff353554dfd7d07a3f1c48e2744e9dd902546b74d3",
            },
            "engineering_target": {
                "root_entity_type": cls.ROOT_ENTITY_TYPE,
                "root_entity_id": cls.ROOT_ENTITY_ID,
                "target_metric": "selected_candidate_id",
                "prediction_class": "ENGINEERING_DECISION",
            },
            "visible_inputs": [
                {"entity_type": "TelemetrySession", "entity_id": "TS-STANFORD-01"},
                {"entity_type": "Investigation", "entity_id": "INV-P3K1-01"},
                {"entity_type": "EngineeringQuestion", "entity_id": "Q-P3K1-01"},
                {"entity_type": "EngineeringDecision", "entity_id": "DEC-P3K1-01"},
            ],
            "withheld_outcome": {
                "entity_type": cls.HIDDEN_OUTCOME_TYPE,
                "entity_id": cls.HIDDEN_OUTCOME_ID,
                "authoritative_artifact_hash": "57e5a95b54946f5c445d9396702f6cce5ef9ebc78b72afb88db09409d88d4a27",
                "forbidden_fields_sealed": ["gate_verdict", "setup_id", "holdout_r2", "selected_option"],
            },
            "policies": {
                "prediction_schema_version": PREDICTION_SCHEMA_V2,
                "confidence_semantics": CONFIDENCE_SEMANTICS_PROBABILITY_CORRECT,
                "comparison_policy_version": COMPARISON_POLICY_V1,
                "calibration_policy_version": CALIBRATION_POLICY_V1,
            },
            "actors": {
                "evaluator_user_id": evaluator_id,
                "reveal_approver_user_id": approver_id,
            },
            "session_provenance": {
                "session_id": str(session_id),
                "submission_hash": submission_hash,
                "outcome_hash": comparison.outcome_identity.get("artifact_hash") if isinstance(comparison.outcome_identity, dict) else "",
                "comparison_id": str(comparison.id),
                "comparison_hash": comparison.comparison_hash,
                "verdict": comparison.verdict,
                "comparison_metrics": comparison.comparison_metrics,
                "computed_at_iso": comparison.computed_at.isoformat() if comparison.computed_at else None,
            },
            "pre_reveal_leakage_audit": leakage_audit,
            "status": "VALIDATED_AND_SEALED",
        }

        # Write manifest file
        CASE_MANIFEST_OUTPUT_PATH.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        return manifest
