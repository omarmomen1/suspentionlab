"""phase 6.7 evidence integrity, source verification, and decision dossiers

Revision ID: x7y8z9a0b1c2
Revises: w7x7y7z7a7b7
Create Date: 2026-10-20

Phase 6.7: Validation Evidence Integrity, Engineering Decision Dossiers & Closure Governance:
- trusted_source_registries
- source_verification_records
- engineering_decision_dossiers
- validation_evidence_items additions: integrity_stage, source_verification_status, source_verification_id
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'x7y8z9a0b1c2'
down_revision: Union[str, Sequence[str], None] = 'w7x7y7z7a7b7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UUID_TYPE = postgresql.UUID(as_uuid=True).with_variant(sa.Uuid(), 'sqlite')
JSON_TYPE = postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), 'sqlite')

GOVERNANCE_SEPARATION_NOTICE_V2 = (
    "GOVERNANCE & SAFETY SEPARATION: Engineering decision closure and evidence dossier approval "
    "establish verification and criteria satisfaction only. Deployment authorization, functional safety "
    "certification (ISO 26262), and operational release require separate statutory authorization and "
    "are NEVER established or inferred by evidence closure or parameter trust reassessments."
)


def upgrade() -> None:
    # 1. trusted_source_registries
    op.create_table(
        'trusted_source_registries',
        sa.Column('id', UUID_TYPE, primary_key=True),
        sa.Column('source_identifier', sa.String(length=256), nullable=False, unique=True),
        sa.Column('source_name', sa.String(length=128), nullable=False),
        sa.Column('source_type', sa.String(length=64), nullable=False),
        sa.Column('is_authorized', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('certificate_ref', sa.String(length=256), nullable=True),
        sa.Column('public_key_pem', sa.Text(), nullable=True),
        sa.Column('valid_from', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('valid_until', sa.DateTime(timezone=True), nullable=True),
        sa.Column('organization_id', UUID_TYPE, sa.ForeignKey('organizations.id', ondelete='SET NULL'), nullable=True),
        sa.Column('team_id', UUID_TYPE, sa.ForeignKey('teams.id', ondelete='SET NULL'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
    )
    op.create_index('ix_trusted_source_identifier', 'trusted_source_registries', ['source_identifier'])
    op.create_index('ix_trusted_source_tenant', 'trusted_source_registries', ['organization_id', 'team_id'])

    # 2. source_verification_records
    op.create_table(
        'source_verification_records',
        sa.Column('id', UUID_TYPE, primary_key=True),
        sa.Column('evidence_item_id', UUID_TYPE, sa.ForeignKey('validation_evidence_items.id', ondelete='CASCADE'), nullable=False),
        sa.Column('verification_method', sa.String(length=64), nullable=False),
        sa.Column('verification_status', sa.String(length=32), server_default='UNVERIFIED', nullable=False),
        sa.Column('verifier_identity', sa.String(length=256), nullable=False),
        sa.Column('verifier_role', sa.String(length=64), nullable=False),
        sa.Column('verifier_user_id', UUID_TYPE, sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('verification_timestamp', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('artifact_hash', sa.String(length=64), nullable=False),
        sa.Column('supporting_references', JSON_TYPE, server_default='{}', nullable=False),
        sa.Column('scope', JSON_TYPE, server_default='{}', nullable=False),
        sa.Column('verification_notes', sa.Text(), nullable=True),
        sa.Column('verification_hash', sa.String(length=64), nullable=False),
        sa.Column('is_revoked', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('revocation_reason', sa.Text(), nullable=True),
        sa.Column('revoked_by_user_id', UUID_TYPE, sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('organization_id', UUID_TYPE, sa.ForeignKey('organizations.id', ondelete='SET NULL'), nullable=True),
        sa.Column('team_id', UUID_TYPE, sa.ForeignKey('teams.id', ondelete='SET NULL'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
    )
    op.create_index('ix_src_verif_evidence_id', 'source_verification_records', ['evidence_item_id'])
    op.create_index('ix_src_verif_status', 'source_verification_records', ['verification_status'])
    op.create_index('ix_src_verif_tenant', 'source_verification_records', ['organization_id', 'team_id'])

    # 3. Add columns to validation_evidence_items
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == 'sqlite'

    if is_sqlite:
        with op.batch_alter_table('validation_evidence_items', schema=None) as batch_op:
            batch_op.add_column(sa.Column('integrity_stage', sa.String(length=64), server_default='SOURCE_CLAIMED', nullable=False))
            batch_op.add_column(sa.Column('source_verification_status', sa.String(length=32), server_default='UNVERIFIED', nullable=False))
            batch_op.add_column(sa.Column('source_verification_id', UUID_TYPE, nullable=True))
            batch_op.create_index('ix_val_evidence_verif_status', ['source_verification_status'])
            batch_op.create_index('ix_val_evidence_stage', ['integrity_stage'])
    else:
        op.add_column('validation_evidence_items', sa.Column('integrity_stage', sa.String(length=64), server_default='SOURCE_CLAIMED', nullable=False))
        op.add_column('validation_evidence_items', sa.Column('source_verification_status', sa.String(length=32), server_default='UNVERIFIED', nullable=False))
        op.add_column('validation_evidence_items', sa.Column('source_verification_id', UUID_TYPE, sa.ForeignKey('source_verification_records.id', ondelete='SET NULL', name='fk_val_evidence_source_verification'), nullable=True))
        op.create_index('ix_val_evidence_verif_status', 'validation_evidence_items', ['source_verification_status'])
        op.create_index('ix_val_evidence_stage', 'validation_evidence_items', ['integrity_stage'])

    # 4. engineering_decision_dossiers
    op.create_table(
        'engineering_decision_dossiers',
        sa.Column('id', UUID_TYPE, primary_key=True),
        sa.Column('dossier_number', sa.String(length=64), nullable=False, unique=True),
        sa.Column('decision_id', sa.String(length=128), nullable=False),
        sa.Column('decision_type', sa.String(length=64), server_default='EngineeringDecision', nullable=False),
        sa.Column('engineering_question', sa.Text(), nullable=False),
        sa.Column('dossier_version', sa.Integer(), server_default='1', nullable=False),
        sa.Column('parent_dossier_id', UUID_TYPE, sa.ForeignKey('engineering_decision_dossiers.id', ondelete='SET NULL'), nullable=True),
        sa.Column('plan_id', UUID_TYPE, sa.ForeignKey('engineering_validation_plans.id', ondelete='CASCADE'), nullable=False),
        sa.Column('plan_version', sa.Integer(), server_default='1', nullable=False),
        sa.Column('plan_hash', sa.String(length=64), nullable=False),
        sa.Column('sealed_acceptance_criteria', JSON_TYPE, server_default='[]', nullable=False),
        sa.Column('exposure_assessment_id', UUID_TYPE, sa.ForeignKey('decision_exposure_assessments.id', ondelete='SET NULL'), nullable=True),
        sa.Column('exposure_hash', sa.String(length=64), nullable=True),
        sa.Column('baseline_robustness_analysis_id', UUID_TYPE, sa.ForeignKey('decision_robustness_analyses.id', ondelete='SET NULL'), nullable=True),
        sa.Column('baseline_robustness_hash', sa.String(length=64), nullable=True),
        sa.Column('closure_id', UUID_TYPE, sa.ForeignKey('validation_evidence_closures.id', ondelete='CASCADE'), nullable=False),
        sa.Column('closure_hash', sa.String(length=64), nullable=False),
        sa.Column('reassessment_id', UUID_TYPE, sa.ForeignKey('validation_decision_reassessments.id', ondelete='CASCADE'), nullable=False),
        sa.Column('reassessment_hash', sa.String(length=64), nullable=False),
        sa.Column('reassessed_robustness_analysis_id', UUID_TYPE, sa.ForeignKey('decision_robustness_analyses.id', ondelete='SET NULL'), nullable=True),
        sa.Column('reassessed_robustness_hash', sa.String(length=64), nullable=True),
        sa.Column('evidence_item_ids', JSON_TYPE, server_default='[]', nullable=False),
        sa.Column('source_verification_ids', JSON_TYPE, server_default='[]', nullable=False),
        sa.Column('evidence_lineage_summary', JSON_TYPE, server_default='{}', nullable=False),
        sa.Column('contradictory_evidence_summary', JSON_TYPE, server_default='{}', nullable=False),
        sa.Column('unresolved_assumptions', JSON_TYPE, server_default='[]', nullable=False),
        sa.Column('before_after_comparison', JSON_TYPE, server_default='{}', nullable=False),
        sa.Column('governance_state', sa.String(length=64), server_default='DRAFT', nullable=False),
        sa.Column('admissibility_status', sa.String(length=32), server_default='PENDING', nullable=False),
        sa.Column('criteria_satisfaction_status', sa.String(length=32), server_default='PENDING', nullable=False),
        sa.Column('closure_status', sa.String(length=32), server_default='PENDING', nullable=False),
        sa.Column('conclusion_review_status', sa.String(length=32), server_default='PENDING', nullable=False),
        sa.Column('decision_approval_status', sa.String(length=32), server_default='PENDING', nullable=False),
        sa.Column('governance_separation_notice', sa.Text(), server_default=GOVERNANCE_SEPARATION_NOTICE_V2, nullable=False),
        sa.Column('deployment_authorization_status', sa.String(length=32), server_default='NOT_ESTABLISHED', nullable=False),
        sa.Column('deployment_safety_inferred', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('review_audit_trail', JSON_TYPE, server_default='[]', nullable=False),
        sa.Column('dossier_content_hash', sa.String(length=64), nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('superseded_by', UUID_TYPE, sa.ForeignKey('engineering_decision_dossiers.id', ondelete='SET NULL'), nullable=True),
        sa.Column('organization_id', UUID_TYPE, sa.ForeignKey('organizations.id', ondelete='SET NULL'), nullable=True),
        sa.Column('team_id', UUID_TYPE, sa.ForeignKey('teams.id', ondelete='SET NULL'), nullable=True),
        sa.Column('compiled_by_user_id', UUID_TYPE, sa.ForeignKey('users.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
    )
    op.create_index('ix_dossier_decision_lookup', 'engineering_decision_dossiers', ['decision_id'])
    op.create_index('ix_dossier_number', 'engineering_decision_dossiers', ['dossier_number'])
    op.create_index('ix_dossier_plan_id', 'engineering_decision_dossiers', ['plan_id'])
    op.create_index('ix_dossier_gov_state', 'engineering_decision_dossiers', ['governance_state'])
    op.create_index('ix_dossier_active', 'engineering_decision_dossiers', ['is_active'])
    op.create_index('ix_dossier_tenant', 'engineering_decision_dossiers', ['organization_id', 'team_id'])


def downgrade() -> None:
    # 4. drop engineering_decision_dossiers
    op.drop_index('ix_dossier_tenant', table_name='engineering_decision_dossiers')
    op.drop_index('ix_dossier_active', table_name='engineering_decision_dossiers')
    op.drop_index('ix_dossier_gov_state', table_name='engineering_decision_dossiers')
    op.drop_index('ix_dossier_plan_id', table_name='engineering_decision_dossiers')
    op.drop_index('ix_dossier_number', table_name='engineering_decision_dossiers')
    op.drop_index('ix_dossier_decision_lookup', table_name='engineering_decision_dossiers')
    op.drop_table('engineering_decision_dossiers')

    # 3. drop columns from validation_evidence_items
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == 'sqlite'

    if is_sqlite:
        with op.batch_alter_table('validation_evidence_items', schema=None) as batch_op:
            batch_op.drop_index('ix_val_evidence_stage')
            batch_op.drop_index('ix_val_evidence_verif_status')
            batch_op.drop_column('source_verification_id')
            batch_op.drop_column('source_verification_status')
            batch_op.drop_column('integrity_stage')
    else:
        op.drop_index('ix_val_evidence_stage', table_name='validation_evidence_items')
        op.drop_index('ix_val_evidence_verif_status', table_name='validation_evidence_items')
        op.drop_column('validation_evidence_items', 'source_verification_id')
        op.drop_column('validation_evidence_items', 'source_verification_status')
        op.drop_column('validation_evidence_items', 'integrity_stage')

    # 2. drop source_verification_records
    op.drop_index('ix_src_verif_tenant', table_name='source_verification_records')
    op.drop_index('ix_src_verif_status', table_name='source_verification_records')
    op.drop_index('ix_src_verif_evidence_id', table_name='source_verification_records')
    op.drop_table('source_verification_records')

    # 1. drop trusted_source_registries
    op.drop_index('ix_trusted_source_tenant', table_name='trusted_source_registries')
    op.drop_index('ix_trusted_source_identifier', table_name='trusted_source_registries')
    op.drop_table('trusted_source_registries')
