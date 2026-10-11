"""
backend/database/models/setup_engineering.py
=============================================
SuspensionLab PRO — Phase 3L Setup Engineering & Causal Experimentation Database Models.

Persists the formal setup engineering entities:
- EngineeringProblemRecord
- CausalHypothesisRecord
- ControlledExperimentDesignRecord
- SetupCandidateRecord
- TrackTestPredictionRecord
- PostTrackReconciliationRecord

All entities enforce strict epistemic status demarcation, cryptographic provenance,
and zero retroactive mutation of predictions or historical evidence.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy import Column, String, DateTime, JSON, Integer, Float, Text, Boolean, Index, Uuid
from sqlalchemy.dialects.postgresql import JSONB

JSON_TYPE = JSON().with_variant(JSONB, "postgresql")
from suspensionlab.backend.database.core import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class EngineeringProblemRecord(Base):
    """
    Formal Engineering Problem Definition (Phase 3L Section 1).
    Distinguishes OBSERVED FACT from HYPOTHESIS, MODEL INFERENCE, and ENGINEERING DECISION.
    """
    __tablename__ = "engineering_problems"
    __table_args__ = (
        Index("ix_engprob_id", "problem_id", unique=True),
        Index("ix_engprob_session", "telemetry_session_id"),
        Index("ix_engprob_user_ts", "user_id", "created_at"),
    )

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    problem_id = Column(String(64), nullable=False, unique=True)  # e.g. "PROB-P3L-01"
    telemetry_session_id = Column(String(64), nullable=False)     # e.g. "TS-STANFORD-01"
    investigation_id = Column(String(64), nullable=False)         # e.g. "INV-P3K1-01"
    engineering_question_id = Column(String(64), nullable=False)  # e.g. "Q-P3K1-01"

    observable = Column(Text, nullable=False)                     # e.g. "Front axle lateral performance deteriorated during Turn 8 exit"
    baseline_metric = Column(JSON_TYPE, nullable=False)           # {"lat_accel_g": 1.15, "roll_angle_deg": 3.2, ...}
    target_metric = Column(JSON_TYPE, nullable=False)             # {"lat_accel_g": 1.25, "roll_angle_deg": 2.4, ...}
    operating_condition = Column(JSON_TYPE, nullable=False)       # {"speed_kph": 115.0, "corner_phase": "exit", ...}
    track_context = Column(JSON_TYPE, nullable=False)             # {"track": "Thunderhill West", "corner": "Turn 8", ...}
    session_context = Column(JSON_TYPE, nullable=False)           # {"surface": "dry asphalt", "ambient_temp_c": 22.0}

    model_version = Column(String(64), nullable=False)            # e.g. "DYNAMIC_TRANSIENT_14DOF-v2.6"
    epistemic_classification = Column(JSON_TYPE, nullable=False) # {observed_fact: [...], hypothesis: [...], inference: [...], decision: [...]}

    artifact_hash = Column(String(64), nullable=False)
    user_id = Column(Uuid(as_uuid=True), nullable=False)
    team_id = Column(Uuid(as_uuid=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class CausalHypothesisRecord(Base):
    """
    Formal Causal Hypothesis (Phase 3L Section 3).
    Captures physical causal mechanisms, supporting/contradicting evidence,
    and statistical confidence with defined mathematical meaning.
    """
    __tablename__ = "causal_hypotheses"
    __table_args__ = (
        Index("ix_causalhyp_id", "hypothesis_id", unique=True),
        Index("ix_causalhyp_problem", "problem_id"),
        Index("ix_causalhyp_user_ts", "user_id", "created_at"),
    )

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    hypothesis_id = Column(String(64), nullable=False, unique=True)  # e.g. "HYP-P3L-01"
    problem_id = Column(String(64), nullable=False)                  # e.g. "PROB-P3L-01"

    hypothesis = Column(Text, nullable=False)                        # Verbatim causal statement
    mechanism = Column(Text, nullable=False)                         # Physical mechanism (load transfer distribution, damping)
    supporting_evidence = Column(JSON_TYPE, nullable=False)          # List of citations/facts
    contradicting_evidence = Column(JSON_TYPE, nullable=False)        # List of risks/tradeoffs
    affected_observables = Column(JSON_TYPE, nullable=False)         # ["lat_accel_g", "roll_angle_deg", ...]
    candidate_parameters = Column(JSON_TYPE, nullable=False)         # ["spring_rate_front", "damper_bump_front"]
    expected_direction_of_effect = Column(JSON_TYPE, nullable=False) # {"lat_accel_g": "+", "roll_angle_deg": "-"}

    # Rigorous statistical confidence (covariance, std errors, CI; NOT arbitrary scalar)
    confidence_uncertainty = Column(JSON_TYPE, nullable=False)
    model_version = Column(String(64), nullable=False)
    epistemic_status = Column(String(32), nullable=False, default="HYPOTHESIS")

    artifact_hash = Column(String(64), nullable=False)
    user_id = Column(Uuid(as_uuid=True), nullable=False)
    team_id = Column(Uuid(as_uuid=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class ControlledExperimentDesignRecord(Base):
    """
    Controlled Experiment Design (Phase 3L Section 4).
    Enforces isolated treatment intervention and prevents accidental simultaneous parameter changes.
    """
    __tablename__ = "controlled_experiment_designs"
    __table_args__ = (
        Index("ix_ctrlexp_id", "experiment_id", unique=True),
        Index("ix_ctrlexp_problem", "problem_id"),
        Index("ix_ctrlexp_user_ts", "user_id", "created_at"),
    )

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    experiment_id = Column(String(64), nullable=False, unique=True)  # e.g. "EXP-P3L-01"
    problem_id = Column(String(64), nullable=False)                  # e.g. "PROB-P3L-01"
    hypothesis_id = Column(String(64), nullable=False)               # e.g. "HYP-P3L-01"

    control_variables = Column(JSON_TYPE, nullable=False)            # {mass_kg, aero_map, tire_model, ride_height}
    treatment_variables = Column(JSON_TYPE, nullable=False)          # {spring_rate_front, damper_bump_front}
    held_constant_variables = Column(JSON_TYPE, nullable=False)      # All other vehicle parameters
    measured_outputs = Column(JSON_TYPE, nullable=False)             # ["front_load_transfer", "front_lat_accel", ...]
    expected_effect = Column(JSON_TYPE, nullable=False)              # Quantitative expected shift
    constraints = Column(JSON_TYPE, nullable=False)                  # Multi-objective constraints
    validity_domain = Column(JSON_TYPE, nullable=False)              # Operating envelope
    isolation_verified = Column(Boolean, nullable=False, default=True)

    artifact_hash = Column(String(64), nullable=False)
    user_id = Column(Uuid(as_uuid=True), nullable=False)
    team_id = Column(Uuid(as_uuid=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class SetupCandidateRecord(Base):
    """
    Authentic Setup Candidate Object (Phase 3L Section 5).
    Contains parent setup lineage, parameter deltas, provenance, and validity domain.
    """
    __tablename__ = "candidate_setups"
    __table_args__ = (
        Index("ix_candsetup_id", "setup_id", unique=True),
        Index("ix_candsetup_parent", "parent_setup_id"),
        Index("ix_candsetup_user_ts", "user_id", "created_at"),
    )

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    setup_id = Column(String(64), nullable=False, unique=True)       # e.g. "SETUP-P3L-CAND-01"
    parent_setup_id = Column(String(64), nullable=False)             # e.g. "SETUP-GTI-BASE"

    changed_parameters = Column(JSON_TYPE, nullable=False)           # {param: {baseline, candidate, delta_pct}}
    unchanged_parameters = Column(JSON_TYPE, nullable=False)         # {param: value}
    parameter_provenance = Column(JSON_TYPE, nullable=False)         # {param: provenance_label}
    model_version = Column(String(64), nullable=False)
    validity_domain = Column(JSON_TYPE, nullable=False)
    creation_reason = Column(Text, nullable=False)
    simulation_run_id = Column(String(64), nullable=True)

    artifact_hash = Column(String(64), nullable=False)
    user_id = Column(Uuid(as_uuid=True), nullable=False)
    team_id = Column(Uuid(as_uuid=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class TrackTestPredictionRecord(Base):
    """
    Formal Track-Test Prediction (Phase 3L Section 11).
    Explicit prediction of candidate metrics, expected delta, and uncertainty intervals.
    Cryptographically immutable after creation.
    """
    __tablename__ = "track_test_predictions"
    __table_args__ = (
        Index("ix_trackpred_id", "prediction_id", unique=True),
        Index("ix_trackpred_decision", "decision_id"),
        Index("ix_trackpred_setup", "candidate_setup_id"),
    )

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    prediction_id = Column(String(64), nullable=False, unique=True)  # e.g. "PRED-P3L-01"
    decision_id = Column(String(64), nullable=False)                 # e.g. "DEC-P3L-01"
    candidate_setup_id = Column(String(64), nullable=False)          # e.g. "SETUP-P3L-CAND-01"

    baseline_metric = Column(JSON_TYPE, nullable=False)              # e.g. {"lat_accel_g": 1.15}
    expected_candidate_metric = Column(JSON_TYPE, nullable=False)    # e.g. {"lat_accel_g": 1.23}
    expected_delta = Column(JSON_TYPE, nullable=False)               # e.g. {"lat_accel_g": 0.08}
    uncertainty_interval = Column(JSON_TYPE, nullable=False)         # e.g. {"lat_accel_g": [0.05, 0.11]} (± 0.03 g)

    operating_conditions = Column(JSON_TYPE, nullable=False)
    failure_conditions = Column(JSON_TYPE, nullable=False)           # List of falsification/invalidation rules
    prediction_hash = Column(String(64), nullable=False)             # Canonical hash preventing retroactive edit
    is_immutable = Column(Boolean, nullable=False, default=True)
    epistemic_status = Column(String(32), nullable=False, default="PREDICTION")

    user_id = Column(Uuid(as_uuid=True), nullable=False)
    team_id = Column(Uuid(as_uuid=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class PostTrackReconciliationRecord(Base):
    """
    Post-Track Reconciliation Record (Phase 3L Section 12).
    Compares original prediction against subsequent actual track telemetry.
    Never retroactively alters the prediction.
    """
    __tablename__ = "post_track_reconciliations"
    __table_args__ = (
        Index("ix_reconcil_id", "reconciliation_id", unique=True),
        Index("ix_reconcil_pred", "prediction_id"),
        Index("ix_reconcil_session", "actual_session_id"),
    )

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    reconciliation_id = Column(String(64), nullable=False, unique=True)  # e.g. "RECON-P3L-01"
    prediction_id = Column(String(64), nullable=False)                   # e.g. "PRED-P3L-01"
    actual_session_id = Column(String(64), nullable=False)               # e.g. "TS-STANFORD-02"

    prediction_error = Column(JSON_TYPE, nullable=False)                 # Predicted vs actual error
    directional_agreement = Column(Boolean, nullable=False)              # True if direction matches prediction
    magnitude_error = Column(JSON_TYPE, nullable=False)                  # |delta_actual - delta_predicted|
    new_residuals = Column(JSON_TYPE, nullable=False)                    # Residuals against post-track telemetry
    new_evidence = Column(JSON_TYPE, nullable=False)                     # New insights learned

    reconciliation_status = Column(String(32), nullable=False, default="RECONCILED_CONFIRMED")
    original_prediction_hash_verified = Column(Boolean, nullable=False, default=True)
    artifact_hash = Column(String(64), nullable=False)

    user_id = Column(Uuid(as_uuid=True), nullable=False)
    team_id = Column(Uuid(as_uuid=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
