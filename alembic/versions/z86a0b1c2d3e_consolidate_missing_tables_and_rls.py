"""consolidate_missing_tables_and_rls

Revision ID: z86a0b1c2d3e
Revises: z85a0b1c2d3e
Create Date: 2026-11-12 02:35:00.000000

Consolidates all SQLAlchemy ORM tables missing from prior Alembic migrations
using CREATE TABLE IF NOT EXISTS (19 tables including trials and audit_outbox),
adds missing ORM columns on audit_logs and shared_reports, and applies
PostgreSQL ENABLE ROW LEVEL SECURITY + FORCE ROW LEVEL SECURITY + tenant
isolation policies across all tenant tables.
"""
from __future__ import annotations

from typing import Dict, List, Sequence, Tuple, Union

from alembic import context, op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex, CreateTable

# revision identifiers, used by Alembic.
revision: str = 'z86a0b1c2d3e'
down_revision: Union[str, None] = 'z85a0b1c2d3e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

PG_UUID = postgresql.UUID(as_uuid=True)
SA_UUID = sa.Uuid(as_uuid=True)
JSON_TYPE = sa.JSON().with_variant(postgresql.JSONB(), 'postgresql')


def _build_missing_tables(metadata: sa.MetaData) -> List[sa.Table]:
    """Define all 19 ORM tables missing from migrations <= z85a0b1c2d3e."""
    # Register stub references for existing parent tables so ForeignKey targets resolve cleanly
    for parent_name in ('organizations', 'teams', 'users'):
        sa.Table(parent_name, metadata, sa.Column('id', PG_UUID, primary_key=True))

    tables: List[sa.Table] = []

    # 1. audit_outbox (models/audit.py)
    tables.append(
        sa.Table(
            'audit_outbox',
            metadata,
            sa.Column('id', PG_UUID, primary_key=True),
            sa.Column('idempotency_key', sa.String(length=128), nullable=True, unique=True, index=True),
            sa.Column('event_type', sa.String(length=64), nullable=False),
            sa.Column('user_id', PG_UUID, nullable=True, index=True),
            sa.Column('organization_id', PG_UUID, sa.ForeignKey('organizations.id', ondelete='SET NULL'), nullable=True, index=True),
            sa.Column('team_id', PG_UUID, nullable=True, index=True),
            sa.Column('ip', sa.String(length=64), nullable=True),
            sa.Column('user_agent', sa.String(length=255), nullable=True),
            sa.Column('artifact_id', sa.String(length=255), nullable=True, index=True),
            sa.Column('metadata', JSON_TYPE, nullable=True),
            sa.Column('status', sa.String(length=64), nullable=False),
            sa.Column('retry_count', sa.Integer(), nullable=False),
            sa.Column('max_retries', sa.Integer(), nullable=False),
            sa.Column('last_error', sa.Text(), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('processed_at', sa.DateTime(timezone=True), nullable=True),
            sa.Index('ix_audit_outbox_status', 'status'),
            sa.Index('ix_audit_outbox_created', 'created_at'),
        )
    )

    # 2. organization_invitations (models/invitation.py)
    tables.append(
        sa.Table(
            'organization_invitations',
            metadata,
            sa.Column('id', PG_UUID, primary_key=True),
            sa.Column('organization_id', PG_UUID, sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
            sa.Column('team_id', PG_UUID, sa.ForeignKey('teams.id', ondelete='SET NULL'), nullable=True),
            sa.Column('invited_by_user_id', PG_UUID, sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
            sa.Column('invitee_email', sa.String(length=255), nullable=False),
            sa.Column('role', sa.String(length=32), nullable=False),
            sa.Column('team_role', sa.String(length=20), nullable=True),
            sa.Column('token_hash', sa.String(length=64), unique=True, nullable=False),
            sa.Column('token_prefix', sa.String(length=16), nullable=False),
            sa.Column('status', sa.String(length=20), nullable=False),
            sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('accepted_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('accepted_by_user_id', PG_UUID, sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Index('ix_org_invites_token_hash', 'token_hash', unique=True),
            sa.Index('ix_org_invites_org_status', 'organization_id', 'status'),
            sa.Index('ix_org_invites_email_status', 'invitee_email', 'status'),
        )
    )

    # 3. trials (models/trial.py)
    tables.append(
        sa.Table(
            'trials',
            metadata,
            sa.Column('id', sa.UUID(as_uuid=True), primary_key=True),
            sa.Column('organization_id', sa.UUID(as_uuid=True), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False, unique=True),
            sa.Column('user_id', sa.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('status', sa.String(length=32), nullable=False),
            sa.Column('simulation_run_limit', sa.Integer(), nullable=False),
            sa.Column('simulation_run_count', sa.Integer(), nullable=False),
            sa.Column('telemetry_storage_limit_bytes', sa.BigInteger(), nullable=False),
            sa.Column('telemetry_storage_used_bytes', sa.BigInteger(), nullable=False),
            sa.Column('vehicle_project_limit', sa.Integer(), nullable=False),
            sa.Column('vehicle_project_count', sa.Integer(), nullable=False),
            sa.Column('evaluation_title', sa.String(length=255), nullable=False),
            sa.Column('contact_email', sa.String(length=255), nullable=True),
            sa.Column('metadata_json', JSON_TYPE, nullable=True),
            sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Index('ix_trials_org_id', 'organization_id', unique=True),
            sa.Index('ix_trials_user_id', 'user_id'),
            sa.Index('ix_trials_status', 'status'),
            sa.Index('ix_trials_expires_at', 'expires_at'),
        )
    )

    # 4. engineering_questions (models/engineering_question.py)
    tables.append(
        sa.Table(
            'engineering_questions',
            metadata,
            sa.Column('id', SA_UUID, primary_key=True),
            sa.Column('question_id', sa.String(length=64), nullable=False, unique=True),
            sa.Column('organization_id', SA_UUID, nullable=True),
            sa.Column('team_id', SA_UUID, nullable=True),
            sa.Column('created_by_user_id', SA_UUID, nullable=False),
            sa.Column('created_by', sa.String(length=128), nullable=False),
            sa.Column('vehicle_id', sa.String(length=128), nullable=False),
            sa.Column('setup_id', sa.String(length=128), nullable=False),
            sa.Column('title', sa.String(length=256), nullable=False),
            sa.Column('question_text', sa.Text(), nullable=False),
            sa.Column('context', JSON_TYPE, nullable=False),
            sa.Column('severity', sa.String(length=32), nullable=False),
            sa.Column('source', sa.String(length=64), nullable=False),
            sa.Column('status', sa.String(length=32), nullable=False),
            sa.Column('linked_telemetry_ids', JSON_TYPE, nullable=False),
            sa.Column('linked_evidence', JSON_TYPE, nullable=False),
            sa.Column('linked_experiments', JSON_TYPE, nullable=False),
            sa.Column('linked_decisions', JSON_TYPE, nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
            sa.Index('ix_questions_question_id', 'question_id', unique=True),
            sa.Index('ix_questions_user_ts', 'created_by_user_id', 'created_at'),
            sa.Index('ix_questions_org_ts', 'organization_id', 'created_at'),
            sa.Index('ix_questions_team_ts', 'team_id', 'created_at'),
            sa.Index('ix_questions_status', 'status'),
            sa.Index('ix_questions_severity', 'severity'),
        )
    )

    # 5. engineering_decisions (models/engineering_decision.py)
    tables.append(
        sa.Table(
            'engineering_decisions',
            metadata,
            sa.Column('id', SA_UUID, primary_key=True),
            sa.Column('decision_id', sa.String(length=64), nullable=False),
            sa.Column('question', sa.Text(), nullable=False),
            sa.Column('context', JSON_TYPE, nullable=False),
            sa.Column('candidates', JSON_TYPE, nullable=False),
            sa.Column('selected_option', JSON_TYPE, nullable=False),
            sa.Column('reason', sa.Text(), nullable=False),
            sa.Column('tradeoffs', JSON_TYPE, nullable=False),
            sa.Column('risks', JSON_TYPE, nullable=False),
            sa.Column('simulation_evidence', JSON_TYPE, nullable=False),
            sa.Column('telemetry_evidence', JSON_TYPE, nullable=False),
            sa.Column('validation_evidence', JSON_TYPE, nullable=False),
            sa.Column('evidence_summary', sa.Text(), nullable=True),
            sa.Column('status', sa.String(length=32), nullable=False),
            sa.Column('author', sa.String(length=120), nullable=False),
            sa.Column('approver', sa.String(length=120), nullable=True),
            sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('approval_signature', sa.String(length=128), nullable=True),
            sa.Column('artifact_hashes', JSON_TYPE, nullable=False),
            sa.Column('user_id', SA_UUID, nullable=False),
            sa.Column('team_id', SA_UUID, nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
            sa.Index('ix_decisions_decision_id', 'decision_id', unique=True),
            sa.Index('ix_decisions_user_ts', 'user_id', 'created_at'),
            sa.Index('ix_decisions_team_ts', 'team_id', 'created_at'),
            sa.Index('ix_decisions_status', 'status'),
        )
    )

    # 6. engineering_experiments (models/experiment.py)
    tables.append(
        sa.Table(
            'engineering_experiments',
            metadata,
            sa.Column('id', SA_UUID, primary_key=True),
            sa.Column('user_id', SA_UUID, nullable=False),
            sa.Column('team_id', SA_UUID, nullable=True),
            sa.Column('question', sa.Text(), nullable=False),
            sa.Column('hypothesis', sa.Text(), nullable=False),
            sa.Column('author', sa.String(length=100), nullable=False),
            sa.Column('vehicle_version', sa.String(length=50), nullable=False),
            sa.Column('setup_version', sa.String(length=50), nullable=False),
            sa.Column('model_version', sa.String(length=50), nullable=False),
            sa.Column('solver', sa.String(length=100), nullable=False),
            sa.Column('backend', sa.String(length=100), nullable=False),
            sa.Column('simulation_id', sa.String(length=50), nullable=True),
            sa.Column('parent_setup', JSON_TYPE, nullable=False),
            sa.Column('candidate_setup', JSON_TYPE, nullable=False),
            sa.Column('parameter_changes', JSON_TYPE, nullable=False),
            sa.Column('baseline_metrics', JSON_TYPE, nullable=False),
            sa.Column('candidate_metrics', JSON_TYPE, nullable=False),
            sa.Column('improvements', JSON_TYPE, nullable=False),
            sa.Column('regressions', JSON_TYPE, nullable=False),
            sa.Column('causal_chain', JSON_TYPE, nullable=False),
            sa.Column('constraints_passed', sa.Boolean(), nullable=False),
            sa.Column('constraint_details', JSON_TYPE, nullable=True),
            sa.Column('validation_state', sa.String(length=32), nullable=False),
            sa.Column('confidence', sa.Float(), nullable=False),
            sa.Column('recommendation', sa.Text(), nullable=False),
            sa.Column('status', sa.String(length=32), nullable=False),
            sa.Column('result_hash', sa.String(length=64), nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
            sa.Index('ix_experiments_user_ts', 'user_id', 'created_at'),
            sa.Index('ix_experiments_team_ts', 'team_id', 'created_at'),
            sa.Index('ix_experiments_status', 'status'),
        )
    )

    # 7. timeline_events (models/timeline_event.py)
    tables.append(
        sa.Table(
            'timeline_events',
            metadata,
            sa.Column('id', SA_UUID, primary_key=True),
            sa.Column('event_type', sa.String(length=64), nullable=False),
            sa.Column('title', sa.String(length=255), nullable=False),
            sa.Column('description', sa.Text(), nullable=False),
            sa.Column('author', sa.String(length=120), nullable=False),
            sa.Column('vehicle_ref', sa.String(length=120), nullable=False),
            sa.Column('setup_ref', sa.String(length=120), nullable=False),
            sa.Column('model_version', sa.String(length=64), nullable=False),
            sa.Column('before_state', JSON_TYPE, nullable=True),
            sa.Column('after_state', JSON_TYPE, nullable=True),
            sa.Column('parameter_changes', JSON_TYPE, nullable=True),
            sa.Column('engineering_effects', JSON_TYPE, nullable=True),
            sa.Column('validation_effects', JSON_TYPE, nullable=True),
            sa.Column('decision_consequences', JSON_TYPE, nullable=True),
            sa.Column('evidence', JSON_TYPE, nullable=True),
            sa.Column('result', JSON_TYPE, nullable=True),
            sa.Column('approval_status', sa.String(length=32), nullable=False),
            sa.Column('approved_by', sa.String(length=120), nullable=True),
            sa.Column('artifact_hashes', JSON_TYPE, nullable=False),
            sa.Column('linked_entity_type', sa.String(length=64), nullable=True),
            sa.Column('linked_entity_id', sa.String(length=128), nullable=True),
            sa.Column('user_id', SA_UUID, nullable=False),
            sa.Column('team_id', SA_UUID, nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
            sa.Index('ix_timeline_event_type', 'event_type'),
            sa.Index('ix_timeline_user_ts', 'user_id', 'created_at'),
            sa.Index('ix_timeline_team_ts', 'team_id', 'created_at'),
            sa.Index('ix_timeline_vehicle_setup', 'vehicle_ref', 'setup_ref'),
        )
    )

    # 8. telemetry_sessions (models/decision_loop.py)
    tables.append(
        sa.Table(
            'telemetry_sessions',
            metadata,
            sa.Column('id', SA_UUID, primary_key=True),
            sa.Column('session_number', sa.Integer(), nullable=False, unique=True),
            sa.Column('session_code', sa.String(length=32), nullable=False, unique=True),
            sa.Column('track_name', sa.String(length=128), nullable=False),
            sa.Column('vehicle_id', sa.String(length=128), nullable=False),
            sa.Column('setup_id', sa.String(length=128), nullable=False),
            sa.Column('channels', JSON_TYPE, nullable=False),
            sa.Column('summary_metrics', JSON_TYPE, nullable=False),
            sa.Column('sample_count', sa.Integer(), nullable=False),
            sa.Column('duration_s', sa.Float(), nullable=False),
            sa.Column('artifact_hash', sa.String(length=64), nullable=False),
            sa.Column('user_id', SA_UUID, nullable=False),
            sa.Column('team_id', SA_UUID, nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
            sa.Index('ix_telemsess_number', 'session_number', unique=True),
            sa.Index('ix_telemsess_code', 'session_code', unique=True),
            sa.Index('ix_telemsess_user_ts', 'user_id', 'created_at'),
            sa.Index('ix_telemsess_track', 'track_name'),
        )
    )

    # 9. telemetry_investigations (models/decision_loop.py)
    tables.append(
        sa.Table(
            'telemetry_investigations',
            metadata,
            sa.Column('id', SA_UUID, primary_key=True),
            sa.Column('investigation_number', sa.Integer(), nullable=False, unique=True),
            sa.Column('investigation_code', sa.String(length=32), nullable=False, unique=True),
            sa.Column('session_code', sa.String(length=32), nullable=False),
            sa.Column('detection_type', sa.String(length=64), nullable=False),
            sa.Column('symptom', sa.Text(), nullable=False),
            sa.Column('affected_regime', sa.String(length=128), nullable=False),
            sa.Column('severity', sa.String(length=32), nullable=False),
            sa.Column('status', sa.String(length=32), nullable=False),
            sa.Column('evidence_snapshot', JSON_TYPE, nullable=False),
            sa.Column('artifact_hash', sa.String(length=64), nullable=False),
            sa.Column('user_id', SA_UUID, nullable=False),
            sa.Column('team_id', SA_UUID, nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
            sa.Index('ix_investigations_number', 'investigation_number', unique=True),
            sa.Index('ix_investigations_code', 'investigation_code', unique=True),
            sa.Index('ix_investigations_session', 'session_code'),
        )
    )

    # 10. setup_comparisons (models/decision_loop.py)
    tables.append(
        sa.Table(
            'setup_comparisons',
            metadata,
            sa.Column('id', SA_UUID, primary_key=True),
            sa.Column('comparison_number', sa.Integer(), nullable=False, unique=True),
            sa.Column('comparison_code', sa.String(length=32), nullable=False, unique=True),
            sa.Column('baseline_setup_id', sa.String(length=64), nullable=False),
            sa.Column('candidate_setup_id', sa.String(length=64), nullable=False),
            sa.Column('simulation_run_id', sa.String(length=64), nullable=True),
            sa.Column('baseline_metrics', JSON_TYPE, nullable=False),
            sa.Column('candidate_metrics', JSON_TYPE, nullable=False),
            sa.Column('measured_metrics', JSON_TYPE, nullable=False),
            sa.Column('deltas', JSON_TYPE, nullable=False),
            sa.Column('uncertainty', JSON_TYPE, nullable=False),
            sa.Column('validity', JSON_TYPE, nullable=False),
            sa.Column('artifact_hash', sa.String(length=64), nullable=False),
            sa.Column('user_id', SA_UUID, nullable=False),
            sa.Column('team_id', SA_UUID, nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
            sa.Index('ix_comparisons_number', 'comparison_number', unique=True),
            sa.Index('ix_comparisons_code', 'comparison_code', unique=True),
        )
    )

    # 11. engineering_optimizations (models/decision_loop.py)
    tables.append(
        sa.Table(
            'engineering_optimizations',
            metadata,
            sa.Column('id', SA_UUID, primary_key=True),
            sa.Column('optimization_number', sa.Integer(), nullable=False, unique=True),
            sa.Column('optimization_code', sa.String(length=32), nullable=False, unique=True),
            sa.Column('experiment_id', sa.String(length=64), nullable=False),
            sa.Column('objective', sa.String(length=128), nullable=False),
            sa.Column('constraints', JSON_TYPE, nullable=False),
            sa.Column('design_variables', JSON_TYPE, nullable=False),
            sa.Column('candidates_evaluated', sa.Integer(), nullable=False),
            sa.Column('solver_calls', sa.Integer(), nullable=False),
            sa.Column('optimal_setup_id', sa.String(length=64), nullable=False),
            sa.Column('optimal_parameters', JSON_TYPE, nullable=False),
            sa.Column('pareto_frontier', JSON_TYPE, nullable=False),
            sa.Column('status', sa.String(length=32), nullable=False),
            sa.Column('artifact_hash', sa.String(length=64), nullable=False),
            sa.Column('user_id', SA_UUID, nullable=False),
            sa.Column('team_id', SA_UUID, nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
            sa.Index('ix_optimizations_number', 'optimization_number', unique=True),
            sa.Index('ix_optimizations_code', 'optimization_code', unique=True),
        )
    )

    # 12. blind_validations (models/decision_loop.py)
    tables.append(
        sa.Table(
            'blind_validations',
            metadata,
            sa.Column('id', SA_UUID, primary_key=True),
            sa.Column('validation_number', sa.Integer(), nullable=False, unique=True),
            sa.Column('validation_code', sa.String(length=32), nullable=False, unique=True),
            sa.Column('setup_id', sa.String(length=64), nullable=False),
            sa.Column('decision_id', sa.String(length=64), nullable=True),
            sa.Column('fit_dataset_ref', sa.String(length=128), nullable=False),
            sa.Column('holdout_dataset_ref', sa.String(length=128), nullable=False),
            sa.Column('is_zero_leakage', sa.Boolean(), nullable=False),
            sa.Column('fit_r2', sa.Float(), nullable=False),
            sa.Column('holdout_r2', sa.Float(), nullable=False),
            sa.Column('holdout_rmse', sa.Float(), nullable=False),
            sa.Column('gate_verdict', sa.String(length=32), nullable=False),
            sa.Column('artifact_hash', sa.String(length=64), nullable=False),
            sa.Column('user_id', SA_UUID, nullable=False),
            sa.Column('team_id', SA_UUID, nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
            sa.Index('ix_validations_number', 'validation_number', unique=True),
            sa.Index('ix_validations_code', 'validation_code', unique=True),
        )
    )

    # 13. engineering_approvals (models/decision_loop.py)
    tables.append(
        sa.Table(
            'engineering_approvals',
            metadata,
            sa.Column('id', SA_UUID, primary_key=True),
            sa.Column('approval_number', sa.Integer(), nullable=False, unique=True),
            sa.Column('approval_code', sa.String(length=32), nullable=False, unique=True),
            sa.Column('decision_id', sa.String(length=64), nullable=False),
            sa.Column('approver_name', sa.String(length=128), nullable=False),
            sa.Column('approver_role', sa.String(length=128), nullable=False),
            sa.Column('approval_signature', sa.String(length=128), nullable=False),
            sa.Column('status', sa.String(length=32), nullable=False),
            sa.Column('notes', sa.Text(), nullable=True),
            sa.Column('artifact_hash', sa.String(length=64), nullable=False),
            sa.Column('user_id', SA_UUID, nullable=False),
            sa.Column('team_id', SA_UUID, nullable=True),
            sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
            sa.Index('ix_approvals_number', 'approval_number', unique=True),
            sa.Index('ix_approvals_code', 'approval_code', unique=True),
        )
    )

    # 14. engineering_problems (models/setup_engineering.py)
    tables.append(
        sa.Table(
            'engineering_problems',
            metadata,
            sa.Column('id', SA_UUID, primary_key=True),
            sa.Column('problem_id', sa.String(length=64), nullable=False, unique=True),
            sa.Column('telemetry_session_id', sa.String(length=64), nullable=False),
            sa.Column('investigation_id', sa.String(length=64), nullable=False),
            sa.Column('engineering_question_id', sa.String(length=64), nullable=False),
            sa.Column('observable', sa.Text(), nullable=False),
            sa.Column('baseline_metric', JSON_TYPE, nullable=False),
            sa.Column('target_metric', JSON_TYPE, nullable=False),
            sa.Column('operating_condition', JSON_TYPE, nullable=False),
            sa.Column('track_context', JSON_TYPE, nullable=False),
            sa.Column('session_context', JSON_TYPE, nullable=False),
            sa.Column('model_version', sa.String(length=64), nullable=False),
            sa.Column('epistemic_classification', JSON_TYPE, nullable=False),
            sa.Column('artifact_hash', sa.String(length=64), nullable=False),
            sa.Column('user_id', SA_UUID, nullable=False),
            sa.Column('team_id', SA_UUID, nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
            sa.Index('ix_engprob_id', 'problem_id', unique=True),
            sa.Index('ix_engprob_session', 'telemetry_session_id'),
            sa.Index('ix_engprob_user_ts', 'user_id', 'created_at'),
        )
    )

    # 15. causal_hypotheses (models/setup_engineering.py)
    tables.append(
        sa.Table(
            'causal_hypotheses',
            metadata,
            sa.Column('id', SA_UUID, primary_key=True),
            sa.Column('hypothesis_id', sa.String(length=64), nullable=False, unique=True),
            sa.Column('problem_id', sa.String(length=64), nullable=False),
            sa.Column('hypothesis', sa.Text(), nullable=False),
            sa.Column('mechanism', sa.Text(), nullable=False),
            sa.Column('supporting_evidence', JSON_TYPE, nullable=False),
            sa.Column('contradicting_evidence', JSON_TYPE, nullable=False),
            sa.Column('affected_observables', JSON_TYPE, nullable=False),
            sa.Column('candidate_parameters', JSON_TYPE, nullable=False),
            sa.Column('expected_direction_of_effect', JSON_TYPE, nullable=False),
            sa.Column('confidence_uncertainty', JSON_TYPE, nullable=False),
            sa.Column('model_version', sa.String(length=64), nullable=False),
            sa.Column('epistemic_status', sa.String(length=32), nullable=False),
            sa.Column('artifact_hash', sa.String(length=64), nullable=False),
            sa.Column('user_id', SA_UUID, nullable=False),
            sa.Column('team_id', SA_UUID, nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
            sa.Index('ix_causalhyp_id', 'hypothesis_id', unique=True),
            sa.Index('ix_causalhyp_problem', 'problem_id'),
            sa.Index('ix_causalhyp_user_ts', 'user_id', 'created_at'),
        )
    )

    # 16. controlled_experiment_designs (models/setup_engineering.py)
    tables.append(
        sa.Table(
            'controlled_experiment_designs',
            metadata,
            sa.Column('id', SA_UUID, primary_key=True),
            sa.Column('experiment_id', sa.String(length=64), nullable=False, unique=True),
            sa.Column('problem_id', sa.String(length=64), nullable=False),
            sa.Column('hypothesis_id', sa.String(length=64), nullable=False),
            sa.Column('control_variables', JSON_TYPE, nullable=False),
            sa.Column('treatment_variables', JSON_TYPE, nullable=False),
            sa.Column('held_constant_variables', JSON_TYPE, nullable=False),
            sa.Column('measured_outputs', JSON_TYPE, nullable=False),
            sa.Column('expected_effect', JSON_TYPE, nullable=False),
            sa.Column('constraints', JSON_TYPE, nullable=False),
            sa.Column('validity_domain', JSON_TYPE, nullable=False),
            sa.Column('isolation_verified', sa.Boolean(), nullable=False),
            sa.Column('artifact_hash', sa.String(length=64), nullable=False),
            sa.Column('user_id', SA_UUID, nullable=False),
            sa.Column('team_id', SA_UUID, nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
            sa.Index('ix_ctrlexp_id', 'experiment_id', unique=True),
            sa.Index('ix_ctrlexp_problem', 'problem_id'),
            sa.Index('ix_ctrlexp_user_ts', 'user_id', 'created_at'),
        )
    )

    # 17. candidate_setups (models/setup_engineering.py)
    tables.append(
        sa.Table(
            'candidate_setups',
            metadata,
            sa.Column('id', SA_UUID, primary_key=True),
            sa.Column('setup_id', sa.String(length=64), nullable=False, unique=True),
            sa.Column('parent_setup_id', sa.String(length=64), nullable=False),
            sa.Column('changed_parameters', JSON_TYPE, nullable=False),
            sa.Column('unchanged_parameters', JSON_TYPE, nullable=False),
            sa.Column('parameter_provenance', JSON_TYPE, nullable=False),
            sa.Column('model_version', sa.String(length=64), nullable=False),
            sa.Column('validity_domain', JSON_TYPE, nullable=False),
            sa.Column('creation_reason', sa.Text(), nullable=False),
            sa.Column('simulation_run_id', sa.String(length=64), nullable=True),
            sa.Column('artifact_hash', sa.String(length=64), nullable=False),
            sa.Column('user_id', SA_UUID, nullable=False),
            sa.Column('team_id', SA_UUID, nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
            sa.Index('ix_candsetup_id', 'setup_id', unique=True),
            sa.Index('ix_candsetup_parent', 'parent_setup_id'),
            sa.Index('ix_candsetup_user_ts', 'user_id', 'created_at'),
        )
    )

    # 18. track_test_predictions (models/setup_engineering.py)
    tables.append(
        sa.Table(
            'track_test_predictions',
            metadata,
            sa.Column('id', SA_UUID, primary_key=True),
            sa.Column('prediction_id', sa.String(length=64), nullable=False, unique=True),
            sa.Column('decision_id', sa.String(length=64), nullable=False),
            sa.Column('candidate_setup_id', sa.String(length=64), nullable=False),
            sa.Column('baseline_metric', JSON_TYPE, nullable=False),
            sa.Column('expected_candidate_metric', JSON_TYPE, nullable=False),
            sa.Column('expected_delta', JSON_TYPE, nullable=False),
            sa.Column('uncertainty_interval', JSON_TYPE, nullable=False),
            sa.Column('operating_conditions', JSON_TYPE, nullable=False),
            sa.Column('failure_conditions', JSON_TYPE, nullable=False),
            sa.Column('prediction_hash', sa.String(length=64), nullable=False),
            sa.Column('is_immutable', sa.Boolean(), nullable=False),
            sa.Column('epistemic_status', sa.String(length=32), nullable=False),
            sa.Column('user_id', SA_UUID, nullable=False),
            sa.Column('team_id', SA_UUID, nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
            sa.Index('ix_trackpred_id', 'prediction_id', unique=True),
            sa.Index('ix_trackpred_decision', 'decision_id'),
            sa.Index('ix_trackpred_setup', 'candidate_setup_id'),
        )
    )

    # 19. post_track_reconciliations (models/setup_engineering.py)
    tables.append(
        sa.Table(
            'post_track_reconciliations',
            metadata,
            sa.Column('id', SA_UUID, primary_key=True),
            sa.Column('reconciliation_id', sa.String(length=64), nullable=False, unique=True),
            sa.Column('prediction_id', sa.String(length=64), nullable=False),
            sa.Column('actual_session_id', sa.String(length=64), nullable=False),
            sa.Column('prediction_error', JSON_TYPE, nullable=False),
            sa.Column('directional_agreement', sa.Boolean(), nullable=False),
            sa.Column('magnitude_error', JSON_TYPE, nullable=False),
            sa.Column('new_residuals', JSON_TYPE, nullable=False),
            sa.Column('new_evidence', JSON_TYPE, nullable=False),
            sa.Column('reconciliation_status', sa.String(length=32), nullable=False),
            sa.Column('original_prediction_hash_verified', sa.Boolean(), nullable=False),
            sa.Column('artifact_hash', sa.String(length=64), nullable=False),
            sa.Column('user_id', SA_UUID, nullable=False),
            sa.Column('team_id', SA_UUID, nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
            sa.Index('ix_reconcil_id', 'reconciliation_id', unique=True),
            sa.Index('ix_reconcil_pred', 'prediction_id'),
            sa.Index('ix_reconcil_session', 'actual_session_id'),
        )
    )

    return tables


_STRICT_ORG_EXPR = "(organization_id = NULLIF(current_setting('app.current_organization_id', true), '')::uuid)"
_TEAM_USER_EXPR = (
    "((team_id IS NOT NULL AND team_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid) "
    "OR (user_id IS NOT NULL AND user_id = NULLIF(current_setting('app.current_user_id', true), '')::uuid) "
    "OR current_setting('app.is_super_admin', true) = 'true')"
)
_ORG_TEAM_USER_EXPR = (
    "((team_id IS NOT NULL AND team_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid) "
    "OR (organization_id IS NOT NULL AND organization_id = NULLIF(current_setting('app.current_organization_id', true), '')::uuid) "
    "OR (user_id IS NOT NULL AND user_id = NULLIF(current_setting('app.current_user_id', true), '')::uuid) "
    "OR current_setting('app.is_super_admin', true) = 'true')"
)
_ORG_TEAM_CREATED_BY_EXPR = (
    "((team_id IS NOT NULL AND team_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid) "
    "OR (organization_id IS NOT NULL AND organization_id = NULLIF(current_setting('app.current_organization_id', true), '')::uuid) "
    "OR (created_by_user_id IS NOT NULL AND created_by_user_id = NULLIF(current_setting('app.current_user_id', true), '')::uuid) "
    "OR current_setting('app.is_super_admin', true) = 'true')"
)
_USER_ONLY_EXPR = (
    "((user_id IS NOT NULL AND user_id = NULLIF(current_setting('app.current_user_id', true), '')::uuid) "
    "OR current_setting('app.is_super_admin', true) = 'true')"
)


def _get_tenant_rls_specs() -> List[Tuple[str, str]]:
    """Return (table_name, policy_using_expr) for every tenant table in the schema."""
    specs: List[Tuple[str, str]] = [
        (
            'organizations',
            "(id = NULLIF(current_setting('app.current_organization_id', true), '')::uuid "
            "OR current_setting('app.is_super_admin', true) = 'true')",
        ),
        (
            'teams',
            "(id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid "
            "OR organization_id = NULLIF(current_setting('app.current_organization_id', true), '')::uuid "
            "OR owner_id = NULLIF(current_setting('app.current_user_id', true), '')::uuid "
            "OR current_setting('app.is_super_admin', true) = 'true')",
        ),
        (
            'users',
            "(id = NULLIF(current_setting('app.current_user_id', true), '')::uuid "
            "OR team_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid "
            "OR organization_id = NULLIF(current_setting('app.current_organization_id', true), '')::uuid "
            "OR current_setting('app.is_super_admin', true) = 'true')",
        ),
        ('audit_logs', _ORG_TEAM_USER_EXPR),
        ('audit_outbox', _ORG_TEAM_USER_EXPR),
        ('engineering_audit_logs', _ORG_TEAM_USER_EXPR),
        ('evidence_graph_edges', _ORG_TEAM_CREATED_BY_EXPR),
        ('engineering_questions', _ORG_TEAM_CREATED_BY_EXPR),
        ('blind_engineering_sessions', _ORG_TEAM_CREATED_BY_EXPR),
        (
            'blind_submissions',
            "((team_id IS NOT NULL AND team_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid) "
            "OR (organization_id IS NOT NULL AND organization_id = NULLIF(current_setting('app.current_organization_id', true), '')::uuid) "
            "OR (submitted_by_user_id IS NOT NULL AND submitted_by_user_id = NULLIF(current_setting('app.current_user_id', true), '')::uuid) "
            "OR current_setting('app.is_super_admin', true) = 'true')",
        ),
        (
            'blind_comparison_results',
            "((team_id IS NOT NULL AND team_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid) "
            "OR (organization_id IS NOT NULL AND organization_id = NULLIF(current_setting('app.current_organization_id', true), '')::uuid) "
            "OR current_setting('app.is_super_admin', true) = 'true')",
        ),
        (
            'engineering_decision_releases',
            "((team_id IS NOT NULL AND team_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid) "
            "OR (organization_id IS NOT NULL AND organization_id = NULLIF(current_setting('app.current_organization_id', true), '')::uuid) "
            "OR (author_id IS NOT NULL AND author_id = NULLIF(current_setting('app.current_user_id', true), '')::uuid) "
            "OR current_setting('app.is_super_admin', true) = 'true')",
        ),
        (
            'evidence_change_impacts',
            "((team_id IS NOT NULL AND team_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid) "
            "OR (organization_id IS NOT NULL AND organization_id = NULLIF(current_setting('app.current_organization_id', true), '')::uuid) "
            "OR (assessed_by_user_id IS NOT NULL AND assessed_by_user_id = NULLIF(current_setting('app.current_user_id', true), '')::uuid) "
            "OR current_setting('app.is_super_admin', true) = 'true')",
        ),
        (
            'trials',
            "((organization_id = NULLIF(current_setting('app.current_organization_id', true), '')::uuid) "
            "OR (user_id = NULLIF(current_setting('app.current_user_id', true), '')::uuid) "
            "OR current_setting('app.is_super_admin', true) = 'true')",
        ),
        (
            'organization_invitations',
            "((organization_id = NULLIF(current_setting('app.current_organization_id', true), '')::uuid) "
            "OR (team_id IS NOT NULL AND team_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid) "
            "OR (invited_by_user_id = NULLIF(current_setting('app.current_user_id', true), '')::uuid) "
            "OR current_setting('app.is_super_admin', true) = 'true')",
        ),
        (
            'scim_groups',
            "((team_id IS NOT NULL AND team_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid) "
            "OR (organization_id = NULLIF(current_setting('app.current_organization_id', true), '')::uuid) "
            "OR current_setting('app.is_super_admin', true) = 'true')",
        ),
        (
            'scim_group_members',
            "((user_id = NULLIF(current_setting('app.current_user_id', true), '')::uuid) "
            "OR EXISTS (SELECT 1 FROM public.scim_groups sg WHERE sg.id = scim_group_members.group_id) "
            "OR current_setting('app.is_super_admin', true) = 'true')",
        ),
        (
            'sessions',
            "((team_id IS NOT NULL AND team_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid) "
            "OR (owner_id IS NOT NULL AND owner_id = NULLIF(current_setting('app.current_user_id', true), '')::uuid) "
            "OR current_setting('app.is_super_admin', true) = 'true')",
        ),
        (
            'session_comments',
            "((author_id IS NOT NULL AND author_id = NULLIF(current_setting('app.current_user_id', true), '')::uuid) "
            "OR current_setting('app.is_super_admin', true) = 'true')",
        ),
        ('user_api_keys', _USER_ONLY_EXPR),
        ('user_sessions', _USER_ONLY_EXPR),
        ('webhook_endpoints', _USER_ONLY_EXPR),
        (
            'calibration_observations',
            "(EXISTS (SELECT 1 FROM public.vehicle_twins vt WHERE vt.id = calibration_observations.twin_id) "
            "OR current_setting('app.is_super_admin', true) = 'true')",
        ),
        ('shared_reports', 'true'),
        ('setup_scores', 'true'),
    ]

    # Strict organization-scoped tables (Phases 6, 7, 8.1, 8.3, 8.4, 8.5)
    for tbl in (
        'co_simulation_coupling_contracts',
        'decision_exposure_assessments',
        'decision_parameter_dependencies',
        'decision_robustness_analyses',
        'engineering_decision_dossiers',
        'engineering_validation_plans',
        'parameter_trust_assembly_impacts',
        'parameter_trust_assessments',
        'parameter_trust_evidence',
        'parameter_trust_fleet_reports',
        'parameter_trust_profiles',
        'solver_exchange_artifacts',
        'solver_exchange_operations',
        'solver_execution_jobs',
        'source_verification_records',
        'trusted_source_registries',
        'validation_decision_reassessments',
        'validation_evidence_closures',
        'validation_evidence_items',
        'engineering_memory_records',
        'engineering_memory_source_links',
        'engineering_memory_index_entries',
        'engineering_case_comparisons',
        'engineering_outcomes',
        'engineering_lessons',
        'engineering_patterns',
        'contradiction_records',
        'organizational_learnings',
    ):
        specs.append((tbl, _STRICT_ORG_EXPR))

    # Team + user scoped tables (core + newly consolidated workflow models)
    for tbl in (
        'jobs',
        'vehicle_profiles',
        'simulation_runs',
        'setup_proposals',
        'vehicle_twins',
        'engineering_decisions',
        'engineering_experiments',
        'timeline_events',
        'telemetry_sessions',
        'telemetry_investigations',
        'setup_comparisons',
        'engineering_optimizations',
        'blind_validations',
        'engineering_approvals',
        'engineering_problems',
        'causal_hypotheses',
        'controlled_experiment_designs',
        'candidate_setups',
        'track_test_predictions',
        'post_track_reconciliations',
    ):
        specs.append((tbl, _TEAM_USER_EXPR))

    return specs


def _ensure_missing_columns(is_sqlite: bool) -> None:
    """Idempotently add ORM columns missing from audit_logs and shared_reports."""
    if not is_sqlite:
        op.execute(sa.text('ALTER TABLE public.audit_logs ADD COLUMN IF NOT EXISTS sequence_number INTEGER NOT NULL DEFAULT 1;'))
        op.execute(sa.text('ALTER TABLE public.audit_logs ADD COLUMN IF NOT EXISTS artifact_id VARCHAR(255);'))
        op.execute(sa.text('ALTER TABLE public.shared_reports ADD COLUMN IF NOT EXISTS team_id UUID;'))
        op.execute(sa.text('ALTER TABLE public.shared_reports ADD COLUMN IF NOT EXISTS organization_id UUID;'))
    elif not context.is_offline_mode():
        insp = sa.inspect(op.get_bind())
        existing_tables = set(insp.get_table_names())
        if 'audit_logs' in existing_tables:
            cols = {c['name'] for c in insp.get_columns('audit_logs')}
            if 'sequence_number' not in cols:
                op.add_column('audit_logs', sa.Column('sequence_number', sa.Integer(), server_default='1', nullable=False))
            if 'artifact_id' not in cols:
                op.add_column('audit_logs', sa.Column('artifact_id', sa.String(length=255), nullable=True))
        if 'shared_reports' in existing_tables:
            cols = {c['name'] for c in insp.get_columns('shared_reports')}
            if 'team_id' not in cols:
                op.add_column('shared_reports', sa.Column('team_id', sa.Uuid(), nullable=True))
            if 'organization_id' not in cols:
                op.add_column('shared_reports', sa.Column('organization_id', sa.Uuid(), nullable=True))

    for idx_sql in (
        'CREATE INDEX IF NOT EXISTS ix_audit_logs_sequence_number ON audit_logs (sequence_number);',
        'CREATE INDEX IF NOT EXISTS ix_audit_logs_artifact_id ON audit_logs (artifact_id);',
        'CREATE INDEX IF NOT EXISTS ix_shared_reports_owner_id ON shared_reports (owner_id);',
        'CREATE INDEX IF NOT EXISTS ix_shared_reports_team_id ON shared_reports (team_id);',
        'CREATE INDEX IF NOT EXISTS ix_shared_reports_organization_id ON shared_reports (organization_id);',
        'CREATE INDEX IF NOT EXISTS ix_shared_reports_owner_ts ON shared_reports (owner_id, created_at);',
        'CREATE INDEX IF NOT EXISTS ix_shared_reports_team_ts ON shared_reports (team_id, created_at);',
    ):
        op.execute(sa.text(idx_sql))


def _apply_postgresql_rls() -> None:
    """Enable and force PostgreSQL Row-Level Security and policies on all tenant tables."""
    for table_name, policy_expr in _get_tenant_rls_specs():
        op.execute(sa.text(f'ALTER TABLE IF EXISTS public.{table_name} ENABLE ROW LEVEL SECURITY;'))
        op.execute(sa.text(f'ALTER TABLE IF EXISTS public.{table_name} FORCE ROW LEVEL SECURITY;'))
        op.execute(sa.text(f'DROP POLICY IF EXISTS {table_name}_tenant_isolation_policy ON public.{table_name};'))
        op.execute(
            sa.text(
                f'CREATE POLICY {table_name}_tenant_isolation_policy ON public.{table_name} '
                f'FOR ALL USING ({policy_expr}) WITH CHECK ({policy_expr});'
            )
        )

    # Ensure existing unprivileged application roles receive DML grants on newly consolidated tables
    op.execute(
        sa.text(
            """
            DO $$
            BEGIN
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_user') THEN
                    GRANT USAGE ON SCHEMA public TO app_user;
                    GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO app_user;
                END IF;
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'suspensionlab_unprivileged_app') THEN
                    GRANT USAGE ON SCHEMA public TO suspensionlab_unprivileged_app;
                    GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO suspensionlab_unprivileged_app;
                END IF;
            END
            $$;
            """
        )
    )


def upgrade() -> None:
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == 'sqlite'

    metadata = sa.MetaData()
    tables = _build_missing_tables(metadata)

    # 1. Create all missing ORM tables with CREATE TABLE IF NOT EXISTS + indexes
    for tbl in tables:
        op.execute(CreateTable(tbl, if_not_exists=True))
        for idx in sorted(tbl.indexes, key=lambda i: i.name or ''):
            op.execute(CreateIndex(idx, if_not_exists=True))

    # 2. Reconcile missing columns/indexes on already-migrated tables
    _ensure_missing_columns(is_sqlite)

    # 3. Enforce ENABLE ROW LEVEL SECURITY and FORCE ROW LEVEL SECURITY on all tenant tables
    if not is_sqlite:
        _apply_postgresql_rls()


def downgrade() -> None:
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == 'sqlite'

    if not is_sqlite:
        for table_name, _ in _get_tenant_rls_specs():
            if table_name in (
                'audit_outbox',
                'organization_invitations',
                'trials',
                'engineering_questions',
                'engineering_decisions',
                'engineering_experiments',
                'timeline_events',
                'telemetry_sessions',
                'telemetry_investigations',
                'setup_comparisons',
                'engineering_optimizations',
                'blind_validations',
                'engineering_approvals',
                'engineering_problems',
                'causal_hypotheses',
                'controlled_experiment_designs',
                'candidate_setups',
                'track_test_predictions',
                'post_track_reconciliations',
                'engineering_decision_releases',
                'evidence_change_impacts',
                'co_simulation_coupling_contracts',
                'decision_exposure_assessments',
                'decision_parameter_dependencies',
                'decision_robustness_analyses',
                'engineering_decision_dossiers',
                'engineering_validation_plans',
                'parameter_trust_assembly_impacts',
                'parameter_trust_assessments',
                'parameter_trust_evidence',
                'parameter_trust_fleet_reports',
                'parameter_trust_profiles',
                'solver_exchange_artifacts',
                'solver_exchange_operations',
                'solver_execution_jobs',
                'source_verification_records',
                'trusted_source_registries',
                'validation_decision_reassessments',
                'validation_evidence_closures',
                'validation_evidence_items',
                'calibration_observations',
                'scim_group_members',
            ):
                op.execute(sa.text(f'DROP POLICY IF EXISTS {table_name}_tenant_isolation_policy ON public.{table_name};'))
                op.execute(sa.text(f'ALTER TABLE IF EXISTS public.{table_name} NO FORCE ROW LEVEL SECURITY;'))
                op.execute(sa.text(f'ALTER TABLE IF EXISTS public.{table_name} DISABLE ROW LEVEL SECURITY;'))

    # Drop consolidated tables in reverse dependency order
    metadata = sa.MetaData()
    for tbl in reversed(_build_missing_tables(metadata)):
        op.execute(sa.text(f'DROP TABLE IF EXISTS {tbl.name};'))
