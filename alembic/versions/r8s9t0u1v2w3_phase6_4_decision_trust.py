"""phase 6.4 decision parameter dependencies and decision exposure assessments tables

Revision ID: r8s9t0u1v2w3
Revises: q7r8s9t0u1v2
Create Date: 2026-10-12
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'r8s9t0u1v2w3'
down_revision = 'q7r8s9t0u1v2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Create decision_parameter_dependencies table
    op.create_table(
        'decision_parameter_dependencies',
        sa.Column('id', postgresql.UUID(as_uuid=True).with_variant(sa.Uuid(), 'sqlite'), primary_key=True),
        sa.Column('decision_id', sa.String(length=64), nullable=False),
        sa.Column('decision_type', sa.String(length=64), nullable=False, server_default='EngineeringDecision'),
        sa.Column('parameter_name', sa.String(length=128), nullable=False),
        sa.Column('entity_type', sa.String(length=64), nullable=False),
        sa.Column('entity_id', sa.String(length=128), nullable=False),
        sa.Column('dependency_nature', sa.String(length=64), nullable=False),
        sa.Column('kpi_metrics', postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), 'sqlite'), server_default='[]', nullable=False),
        sa.Column('sensitivity_status', sa.String(length=32), nullable=False),
        sa.Column('elasticity', sa.Float(), nullable=True),
        sa.Column('numerical_derivative', sa.Float(), nullable=True),
        sa.Column('derivative_unit', sa.String(length=64), nullable=True),
        sa.Column('source_artifact_hashes', postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), 'sqlite'), server_default='[]', nullable=False),
        sa.Column('source_evidence_ids', postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), 'sqlite'), server_default='[]', nullable=False),
        sa.Column('operating_conditions', postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), 'sqlite'), server_default='{}', nullable=False),
        sa.Column('model_version', sa.String(length=64), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('organization_id', postgresql.UUID(as_uuid=True).with_variant(sa.Uuid(), 'sqlite'), nullable=True),
        sa.Column('team_id', postgresql.UUID(as_uuid=True).with_variant(sa.Uuid(), 'sqlite'), nullable=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True).with_variant(sa.Uuid(), 'sqlite'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['team_id'], ['teams.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='RESTRICT'),
    )
    op.create_index('ix_dec_param_dep_lookup', 'decision_parameter_dependencies', ['team_id', 'decision_id', 'parameter_name'])
    op.create_index('ix_dec_param_dep_user', 'decision_parameter_dependencies', ['user_id', 'decision_id'])
    op.create_index('ix_dec_param_dep_nature', 'decision_parameter_dependencies', ['dependency_nature'])

    # 2. Create decision_exposure_assessments table
    op.create_table(
        'decision_exposure_assessments',
        sa.Column('id', postgresql.UUID(as_uuid=True).with_variant(sa.Uuid(), 'sqlite'), primary_key=True),
        sa.Column('decision_id', sa.String(length=64), nullable=False),
        sa.Column('decision_type', sa.String(length=64), nullable=False, server_default='EngineeringDecision'),
        sa.Column('policy_version', sa.String(length=32), nullable=False, server_default='DECISION_TRUST_POLICY_V1'),
        sa.Column('assessment_hash', sa.String(length=64), nullable=False),
        sa.Column('input_snapshot_hash', sa.String(length=64), nullable=False),
        sa.Column('exposure_classification', sa.String(length=64), nullable=False),
        sa.Column('exposure_summary', sa.Text(), nullable=False),
        sa.Column('parameter_dependencies', postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), 'sqlite'), server_default='[]', nullable=False),
        sa.Column('evidence_gaps', postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), 'sqlite'), server_default='[]', nullable=False),
        sa.Column('actionable_recommendations', postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), 'sqlite'), server_default='[]', nullable=False),
        sa.Column('governance_separation_notice', sa.Text(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('superseded_by', postgresql.UUID(as_uuid=True).with_variant(sa.Uuid(), 'sqlite'), nullable=True),
        sa.Column('organization_id', postgresql.UUID(as_uuid=True).with_variant(sa.Uuid(), 'sqlite'), nullable=True),
        sa.Column('team_id', postgresql.UUID(as_uuid=True).with_variant(sa.Uuid(), 'sqlite'), nullable=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True).with_variant(sa.Uuid(), 'sqlite'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['team_id'], ['teams.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='RESTRICT'),
    )
    op.create_index('ix_dec_exposure_lookup', 'decision_exposure_assessments', ['team_id', 'decision_id', 'created_at'])
    op.create_index('ix_dec_exposure_user', 'decision_exposure_assessments', ['user_id', 'decision_id'])
    op.create_index('ix_dec_exposure_hash', 'decision_exposure_assessments', ['assessment_hash'])
    op.create_index('ix_dec_exposure_active', 'decision_exposure_assessments', ['decision_id', 'is_active'])


def downgrade() -> None:
    op.drop_table('decision_exposure_assessments')
    op.drop_table('decision_parameter_dependencies')
