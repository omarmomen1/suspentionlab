"""phase 6.5 decision robustness analysis tables

Revision ID: t0u1v2w3x4y5
Revises: s9t0u1v2w3x4
Create Date: 2026-10-12
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 't0u1v2w3x4y5'
down_revision = 's9t0u1v2w3x4'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'decision_robustness_analyses',
        sa.Column('id', postgresql.UUID(as_uuid=True).with_variant(sa.Uuid(), 'sqlite'), primary_key=True),
        sa.Column('decision_id', sa.String(length=64), nullable=False),
        sa.Column('decision_type', sa.String(length=64), server_default='EngineeringDecision', nullable=False),
        sa.Column('policy_version', sa.String(length=32), server_default='ROBUSTNESS_POLICY_V1', nullable=False),
        sa.Column('analysis_hash', sa.String(length=64), nullable=False),
        sa.Column('input_snapshot_hash', sa.String(length=64), nullable=False),
        sa.Column('robustness_classification', sa.String(length=64), nullable=False),
        sa.Column('robustness_summary', sa.Text(), nullable=False),
        sa.Column('evaluated_envelope', postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), 'sqlite'), server_default='{}', nullable=False),
        sa.Column('parameter_uncertainties', postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), 'sqlite'), server_default='[]', nullable=False),
        sa.Column('reversal_scenarios', postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), 'sqlite'), server_default='[]', nullable=False),
        sa.Column('boundary_crossings', postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), 'sqlite'), server_default='[]', nullable=False),
        sa.Column('dominant_uncertainties', postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), 'sqlite'), server_default='[]', nullable=False),
        sa.Column('voi_prioritizations', postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), 'sqlite'), server_default='[]', nullable=False),
        sa.Column('solver_failures', postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), 'sqlite'), server_default='[]', nullable=False),
        sa.Column('governance_separation_notice', sa.Text(), nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('superseded_by', postgresql.UUID(as_uuid=True).with_variant(sa.Uuid(), 'sqlite'), nullable=True),
        sa.Column('organization_id', postgresql.UUID(as_uuid=True).with_variant(sa.Uuid(), 'sqlite'), nullable=True),
        sa.Column('team_id', postgresql.UUID(as_uuid=True).with_variant(sa.Uuid(), 'sqlite'), nullable=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True).with_variant(sa.Uuid(), 'sqlite'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['team_id'], ['teams.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='RESTRICT'),
    )
    op.create_index('ix_dec_robustness_lookup', 'decision_robustness_analyses', ['team_id', 'decision_id', 'created_at'])
    op.create_index('ix_dec_robustness_user', 'decision_robustness_analyses', ['user_id', 'decision_id'])
    op.create_index('ix_dec_robustness_hash', 'decision_robustness_analyses', ['analysis_hash'])
    op.create_index('ix_dec_robustness_active', 'decision_robustness_analyses', ['decision_id', 'is_active'])


def downgrade() -> None:
    op.drop_index('ix_dec_robustness_active', table_name='decision_robustness_analyses')
    op.drop_index('ix_dec_robustness_hash', table_name='decision_robustness_analyses')
    op.drop_index('ix_dec_robustness_user', table_name='decision_robustness_analyses')
    op.drop_index('ix_dec_robustness_lookup', table_name='decision_robustness_analyses')
    op.drop_table('decision_robustness_analyses')
