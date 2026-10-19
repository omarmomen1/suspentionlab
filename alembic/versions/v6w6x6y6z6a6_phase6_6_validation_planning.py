"""phase 6.6 engineering validation planning and evidence closure tables

Revision ID: v6w6x6y6z6a6
Revises: u1v2w3x4y5z6
Create Date: 2026-10-13

Phase 6.6: Engineering Validation Planning, Evidence Closure & Decision Reassessment:
- engineering_validation_plans
- validation_evidence_items
- validation_evidence_closures
- validation_decision_reassessments
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'v6w6x6y6z6a6'
down_revision: Union[str, None] = 'u1v2w3x4y5z6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. engineering_validation_plans
    op.create_table(
        'engineering_validation_plans',
        sa.Column('id', postgresql.UUID(as_uuid=True).with_variant(sa.Uuid(), 'sqlite'), primary_key=True),
        sa.Column('plan_id', sa.String(length=128), nullable=False),
        sa.Column('decision_id', sa.String(length=128), nullable=False),
        sa.Column('decision_type', sa.String(length=64), server_default='EngineeringDecision', nullable=False),
        sa.Column('parameter_name', sa.String(length=128), nullable=False),
        sa.Column('parameter_path', sa.String(length=256), nullable=True),
        sa.Column('evidence_gap_id', sa.String(length=128), nullable=True),
        sa.Column('validation_objective', sa.Text(), nullable=False),
        sa.Column('validation_method', sa.String(length=64), nullable=False),
        sa.Column('status', sa.String(length=32), server_default='DRAFT', nullable=False),
        sa.Column('plan_version', sa.Integer(), server_default='1', nullable=False),
        sa.Column('parent_plan_id', postgresql.UUID(as_uuid=True).with_variant(sa.Uuid(), 'sqlite'), nullable=True),
        sa.Column('exposure_assessment_id', postgresql.UUID(as_uuid=True).with_variant(sa.Uuid(), 'sqlite'), nullable=True),
        sa.Column('robustness_analysis_id', postgresql.UUID(as_uuid=True).with_variant(sa.Uuid(), 'sqlite'), nullable=True),
        sa.Column('analysis_snapshot_hash', sa.String(length=64), nullable=True),
        sa.Column('input_artifact_requirements', postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), 'sqlite'), server_default='[]', nullable=False),
        sa.Column('operating_conditions', postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), 'sqlite'), server_default='{}', nullable=False),
        sa.Column('applicability_envelope', postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), 'sqlite'), server_default='{}', nullable=False),
        sa.Column('unit', sa.String(length=32), nullable=False),
        sa.Column('measurement_definition', sa.Text(), nullable=False),
        sa.Column('acceptance_criteria', postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), 'sqlite'), server_default='[]', nullable=False),
        sa.Column('criteria_established_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('criteria_authorized_by_user_id', postgresql.UUID(as_uuid=True).with_variant(sa.Uuid(), 'sqlite'), nullable=True),
        sa.Column('expected_outputs', postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), 'sqlite'), server_default='[]', nullable=False),
        sa.Column('required_reviewer_role', sa.String(length=64), server_default='VALIDATION_LEAD', nullable=False),
        sa.Column('authorized_by_user_id', postgresql.UUID(as_uuid=True).with_variant(sa.Uuid(), 'sqlite'), nullable=True),
        sa.Column('authorized_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('plan_hash', sa.String(length=64), nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('organization_id', postgresql.UUID(as_uuid=True).with_variant(sa.Uuid(), 'sqlite'), nullable=True),
        sa.Column('team_id', postgresql.UUID(as_uuid=True).with_variant(sa.Uuid(), 'sqlite'), nullable=True),
        sa.Column('created_by_user_id', postgresql.UUID(as_uuid=True).with_variant(sa.Uuid(), 'sqlite'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['parent_plan_id'], ['engineering_validation_plans.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['exposure_assessment_id'], ['decision_exposure_assessments.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['robustness_analysis_id'], ['decision_robustness_analyses.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['criteria_authorized_by_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['authorized_by_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['team_id'], ['teams.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], ondelete='RESTRICT'),
    )
    op.create_index('ix_val_plans_decision_id', 'engineering_validation_plans', ['decision_id'])
    op.create_index('ix_val_plans_parameter_name', 'engineering_validation_plans', ['parameter_name'])
    op.create_index('ix_val_plans_status', 'engineering_validation_plans', ['status'])
    op.create_index('ix_val_plans_tenant', 'engineering_validation_plans', ['organization_id', 'team_id'])
    op.create_index('ix_val_plans_active', 'engineering_validation_plans', ['is_active'])

    # 2. validation_evidence_items
    op.create_table(
        'validation_evidence_items',
        sa.Column('id', postgresql.UUID(as_uuid=True).with_variant(sa.Uuid(), 'sqlite'), primary_key=True),
        sa.Column('plan_id', postgresql.UUID(as_uuid=True).with_variant(sa.Uuid(), 'sqlite'), nullable=False),
        sa.Column('evidence_source_type', sa.String(length=64), nullable=False),
        sa.Column('source_identifier', sa.String(length=256), nullable=False),
        sa.Column('source_timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.Column('parameter_name', sa.String(length=128), nullable=False),
        sa.Column('observed_value', sa.Float(), nullable=True),
        sa.Column('observed_interval', postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), 'sqlite'), nullable=True),
        sa.Column('observed_samples', postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), 'sqlite'), nullable=True),
        sa.Column('unit', sa.String(length=32), nullable=False),
        sa.Column('operating_scope', postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), 'sqlite'), server_default='{}', nullable=False),
        sa.Column('integrity_hash', sa.String(length=64), nullable=False),
        sa.Column('provenance', postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), 'sqlite'), server_default='{}', nullable=False),
        sa.Column('calibration_metadata', postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), 'sqlite'), server_default='{}', nullable=False),
        sa.Column('is_physically_validated', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('physical_limitations', sa.Text(), nullable=True),
        sa.Column('review_status', sa.String(length=32), server_default='PENDING_REVIEW', nullable=False),
        sa.Column('review_notes', sa.Text(), nullable=True),
        sa.Column('reviewed_by_user_id', postgresql.UUID(as_uuid=True).with_variant(sa.Uuid(), 'sqlite'), nullable=True),
        sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('organization_id', postgresql.UUID(as_uuid=True).with_variant(sa.Uuid(), 'sqlite'), nullable=True),
        sa.Column('team_id', postgresql.UUID(as_uuid=True).with_variant(sa.Uuid(), 'sqlite'), nullable=True),
        sa.Column('submitted_by_user_id', postgresql.UUID(as_uuid=True).with_variant(sa.Uuid(), 'sqlite'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['plan_id'], ['engineering_validation_plans.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['reviewed_by_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['team_id'], ['teams.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['submitted_by_user_id'], ['users.id'], ondelete='RESTRICT'),
    )
    op.create_index('ix_val_evidence_plan_id', 'validation_evidence_items', ['plan_id'])
    op.create_index('ix_val_evidence_param', 'validation_evidence_items', ['parameter_name'])
    op.create_index('ix_val_evidence_review_status', 'validation_evidence_items', ['review_status'])
    op.create_index('ix_val_evidence_tenant', 'validation_evidence_items', ['organization_id', 'team_id'])

    # 3. validation_evidence_closures
    op.create_table(
        'validation_evidence_closures',
        sa.Column('id', postgresql.UUID(as_uuid=True).with_variant(sa.Uuid(), 'sqlite'), primary_key=True),
        sa.Column('plan_id', postgresql.UUID(as_uuid=True).with_variant(sa.Uuid(), 'sqlite'), nullable=False),
        sa.Column('decision_id', sa.String(length=128), nullable=False),
        sa.Column('parameter_name', sa.String(length=128), nullable=False),
        sa.Column('evidence_gap_id', sa.String(length=128), nullable=True),
        sa.Column('closure_verdict', sa.String(length=64), nullable=False),
        sa.Column('criteria_met', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('criteria_evaluated', postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), 'sqlite'), server_default='[]', nullable=False),
        sa.Column('applicability_check', postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), 'sqlite'), server_default='{}', nullable=False),
        sa.Column('conflict_assessment', postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), 'sqlite'), server_default='{}', nullable=False),
        sa.Column('uncertainty_update', postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), 'sqlite'), server_default='{}', nullable=False),
        sa.Column('requires_robustness_reassessment', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('closure_summary', sa.Text(), nullable=False),
        sa.Column('closure_hash', sa.String(length=64), nullable=False),
        sa.Column('governance_separation_notice', sa.Text(), nullable=False),
        sa.Column('finite_sample_notice', sa.Text(), nullable=False),
        sa.Column('deployment_safety_inferred', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('deployment_authorization', sa.String(length=32), server_default='NOT_ESTABLISHED', nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('superseded_by', postgresql.UUID(as_uuid=True).with_variant(sa.Uuid(), 'sqlite'), nullable=True),
        sa.Column('organization_id', postgresql.UUID(as_uuid=True).with_variant(sa.Uuid(), 'sqlite'), nullable=True),
        sa.Column('team_id', postgresql.UUID(as_uuid=True).with_variant(sa.Uuid(), 'sqlite'), nullable=True),
        sa.Column('evaluated_by_user_id', postgresql.UUID(as_uuid=True).with_variant(sa.Uuid(), 'sqlite'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['plan_id'], ['engineering_validation_plans.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['superseded_by'], ['validation_evidence_closures.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['team_id'], ['teams.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['evaluated_by_user_id'], ['users.id'], ondelete='RESTRICT'),
    )
    op.create_index('ix_val_closure_plan_id', 'validation_evidence_closures', ['plan_id'])
    op.create_index('ix_val_closure_decision_id', 'validation_evidence_closures', ['decision_id'])
    op.create_index('ix_val_closure_verdict', 'validation_evidence_closures', ['closure_verdict'])
    op.create_index('ix_val_closure_active', 'validation_evidence_closures', ['is_active'])
    op.create_index('ix_val_closure_tenant', 'validation_evidence_closures', ['organization_id', 'team_id'])

    # 4. validation_decision_reassessments
    op.create_table(
        'validation_decision_reassessments',
        sa.Column('id', postgresql.UUID(as_uuid=True).with_variant(sa.Uuid(), 'sqlite'), primary_key=True),
        sa.Column('decision_id', sa.String(length=128), nullable=False),
        sa.Column('decision_type', sa.String(length=64), server_default='EngineeringDecision', nullable=False),
        sa.Column('plan_id', postgresql.UUID(as_uuid=True).with_variant(sa.Uuid(), 'sqlite'), nullable=False),
        sa.Column('closure_id', postgresql.UUID(as_uuid=True).with_variant(sa.Uuid(), 'sqlite'), nullable=False),
        sa.Column('original_exposure_assessment_id', postgresql.UUID(as_uuid=True).with_variant(sa.Uuid(), 'sqlite'), nullable=True),
        sa.Column('original_robustness_analysis_id', postgresql.UUID(as_uuid=True).with_variant(sa.Uuid(), 'sqlite'), nullable=True),
        sa.Column('new_robustness_analysis_id', postgresql.UUID(as_uuid=True).with_variant(sa.Uuid(), 'sqlite'), nullable=True),
        sa.Column('reassessment_delta', postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), 'sqlite'), server_default='{}', nullable=False),
        sa.Column('reversal_status', sa.String(length=64), nullable=False),
        sa.Column('envelope_coverage_statement', sa.Text(), nullable=False),
        sa.Column('governance_separation_notice', sa.Text(), nullable=False),
        sa.Column('deployment_safety_inferred', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('deployment_authorization', sa.String(length=32), server_default='NOT_ESTABLISHED', nullable=False),
        sa.Column('reassessment_hash', sa.String(length=64), nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('superseded_by', postgresql.UUID(as_uuid=True).with_variant(sa.Uuid(), 'sqlite'), nullable=True),
        sa.Column('organization_id', postgresql.UUID(as_uuid=True).with_variant(sa.Uuid(), 'sqlite'), nullable=True),
        sa.Column('team_id', postgresql.UUID(as_uuid=True).with_variant(sa.Uuid(), 'sqlite'), nullable=True),
        sa.Column('reassessed_by_user_id', postgresql.UUID(as_uuid=True).with_variant(sa.Uuid(), 'sqlite'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['plan_id'], ['engineering_validation_plans.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['closure_id'], ['validation_evidence_closures.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['original_exposure_assessment_id'], ['decision_exposure_assessments.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['original_robustness_analysis_id'], ['decision_robustness_analyses.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['new_robustness_analysis_id'], ['decision_robustness_analyses.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['superseded_by'], ['validation_decision_reassessments.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['team_id'], ['teams.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['reassessed_by_user_id'], ['users.id'], ondelete='RESTRICT'),
    )
    op.create_index('ix_val_reassess_decision_id', 'validation_decision_reassessments', ['decision_id'])
    op.create_index('ix_val_reassess_plan_id', 'validation_decision_reassessments', ['plan_id'])
    op.create_index('ix_val_reassess_closure_id', 'validation_decision_reassessments', ['closure_id'])
    op.create_index('ix_val_reassess_active', 'validation_decision_reassessments', ['is_active'])
    op.create_index('ix_val_reassess_tenant', 'validation_decision_reassessments', ['organization_id', 'team_id'])


def downgrade() -> None:
    # 4. validation_decision_reassessments
    op.drop_index('ix_val_reassess_tenant', table_name='validation_decision_reassessments')
    op.drop_index('ix_val_reassess_active', table_name='validation_decision_reassessments')
    op.drop_index('ix_val_reassess_closure_id', table_name='validation_decision_reassessments')
    op.drop_index('ix_val_reassess_plan_id', table_name='validation_decision_reassessments')
    op.drop_index('ix_val_reassess_decision_id', table_name='validation_decision_reassessments')
    op.drop_table('validation_decision_reassessments')

    # 3. validation_evidence_closures
    op.drop_index('ix_val_closure_tenant', table_name='validation_evidence_closures')
    op.drop_index('ix_val_closure_active', table_name='validation_evidence_closures')
    op.drop_index('ix_val_closure_verdict', table_name='validation_evidence_closures')
    op.drop_index('ix_val_closure_decision_id', table_name='validation_evidence_closures')
    op.drop_index('ix_val_closure_plan_id', table_name='validation_evidence_closures')
    op.drop_table('validation_evidence_closures')

    # 2. validation_evidence_items
    op.drop_index('ix_val_evidence_tenant', table_name='validation_evidence_items')
    op.drop_index('ix_val_evidence_review_status', table_name='validation_evidence_items')
    op.drop_index('ix_val_evidence_param', table_name='validation_evidence_items')
    op.drop_index('ix_val_evidence_plan_id', table_name='validation_evidence_items')
    op.drop_table('validation_evidence_items')

    # 1. engineering_validation_plans
    op.drop_index('ix_val_plans_active', table_name='engineering_validation_plans')
    op.drop_index('ix_val_plans_tenant', table_name='engineering_validation_plans')
    op.drop_index('ix_val_plans_status', table_name='engineering_validation_plans')
    op.drop_index('ix_val_plans_parameter_name', table_name='engineering_validation_plans')
    op.drop_index('ix_val_plans_decision_id', table_name='engineering_validation_plans')
    op.drop_table('engineering_validation_plans')
