"""add parameter trust tables

Revision ID: o5p6q7r8s9t0
Revises: n4o5p6q7r8s9
Create Date: 2026-10-08
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'p6q7r8s9t0u1'
down_revision = 'o5p6q7r8s9t0'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Create parameter_trust_profiles table
    op.create_table(
        'parameter_trust_profiles',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('organization_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('team_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('created_by_user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('entity_type', sa.String(length=64), nullable=False),
        sa.Column('entity_id', sa.String(length=128), nullable=False),
        sa.Column('parameter_name', sa.String(length=128), nullable=False),
        sa.Column('parameter_path', sa.String(length=256), nullable=False),
        sa.Column('unit', sa.String(length=32), nullable=False, server_default=''),
        sa.Column('value_reference', postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), 'sqlite'), nullable=False),
        sa.Column('provenance_class', sa.String(length=64), nullable=False),
        sa.Column('provenance_details', postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), 'sqlite'), server_default='{}', nullable=False),
        sa.Column('scope', postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), 'sqlite'), server_default='{}', nullable=False),
        sa.Column('current_trust_state', sa.String(length=32), nullable=False, server_default='UNASSESSED'),
        sa.Column('validation_coverage', sa.String(length=32), nullable=False, server_default='NO_VALIDATION'),
        sa.Column('policy_version', sa.String(length=32), nullable=False, server_default='TRUST_POLICY_V1'),
        sa.Column('assessment_hash', sa.String(length=64), nullable=False),
        sa.Column('explanation', postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), 'sqlite'), server_default='{}', nullable=False),
        sa.Column('conflicts', postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), 'sqlite'), server_default='[]', nullable=False),
        sa.Column('recency_metadata', postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), 'sqlite'), server_default='{}', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['team_id'], ['teams.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], ondelete='RESTRICT'),
        sa.UniqueConstraint('team_id', 'entity_type', 'entity_id', 'parameter_name', 'policy_version', name='uq_param_trust_team_scope'),
    )

    op.create_index('ix_param_trust_team_lookup', 'parameter_trust_profiles', ['team_id', 'entity_type', 'entity_id', 'parameter_name'])
    op.create_index('ix_param_trust_user_lookup', 'parameter_trust_profiles', ['created_by_user_id', 'entity_type', 'entity_id', 'parameter_name'])
    op.create_index('ix_param_trust_org', 'parameter_trust_profiles', ['organization_id'])
    op.create_index('ix_param_trust_hash', 'parameter_trust_profiles', ['assessment_hash'])
    op.create_index('ix_param_trust_state', 'parameter_trust_profiles', ['current_trust_state'])

    # 2. Create parameter_trust_evidence table
    op.create_table(
        'parameter_trust_evidence',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('profile_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('organization_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('team_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('evidence_type', sa.String(length=64), nullable=False),
        sa.Column('evidence_id', sa.String(length=128), nullable=False),
        sa.Column('artifact_hash', sa.String(length=64), nullable=False),
        sa.Column('relationship', sa.String(length=64), nullable=False),
        sa.Column('evidence_timestamp', sa.DateTime(timezone=True), nullable=True),
        sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), 'sqlite'), server_default='{}', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['profile_id'], ['parameter_trust_profiles.id'], ondelete='CASCADE'),
    )

    op.create_index('ix_param_ev_profile', 'parameter_trust_evidence', ['profile_id'])
    op.create_index('ix_param_ev_target', 'parameter_trust_evidence', ['evidence_type', 'evidence_id'])
    op.create_index('ix_param_ev_team', 'parameter_trust_evidence', ['team_id'])
    op.create_index('ix_param_ev_hash', 'parameter_trust_evidence', ['artifact_hash'])

    # 3. Create parameter_trust_assessments table
    op.create_table(
        'parameter_trust_assessments',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('profile_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('organization_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('team_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('trust_state', sa.String(length=32), nullable=False),
        sa.Column('validation_coverage', sa.String(length=32), nullable=False),
        sa.Column('policy_version', sa.String(length=32), nullable=False),
        sa.Column('assessment_hash', sa.String(length=64), nullable=False),
        sa.Column('value_identity', sa.String(length=128), nullable=False),
        sa.Column('supporting_evidence_hashes', postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), 'sqlite'), server_default='[]', nullable=False),
        sa.Column('explanation', postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), 'sqlite'), server_default='{}', nullable=False),
        sa.Column('conflicts', postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), 'sqlite'), server_default='[]', nullable=False),
        sa.Column('recency_metadata', postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), 'sqlite'), server_default='{}', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['profile_id'], ['parameter_trust_profiles.id'], ondelete='CASCADE'),
    )

    op.create_index('ix_param_assess_profile_ts', 'parameter_trust_assessments', ['profile_id', 'created_at'])
    op.create_index('ix_param_assess_team', 'parameter_trust_assessments', ['team_id'])
    op.create_index('ix_param_assess_hash', 'parameter_trust_assessments', ['assessment_hash'])
    op.create_index('ix_param_assess_user', 'parameter_trust_assessments', ['user_id'])


def downgrade() -> None:
    op.drop_table('parameter_trust_assessments')
    op.drop_table('parameter_trust_evidence')
    op.drop_table('parameter_trust_profiles')
