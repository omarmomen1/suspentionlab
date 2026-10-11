"""add blind comparison results table

Revision ID: o5p6q7r8s9t0
Revises: n4o5p6q7r8s9
Create Date: 2026-10-08
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'o5p6q7r8s9t0'
down_revision = 'n4o5p6q7r8s9'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'blind_comparison_results',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('session_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('submission_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('organization_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('team_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('outcome_identity', postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), 'sqlite'), nullable=False),
        sa.Column('prediction_schema_version', sa.String(length=32), nullable=False, server_default='1'),
        sa.Column('comparison_policy_version', sa.String(length=32), nullable=False, server_default='1'),
        sa.Column('comparison_type', sa.String(length=64), nullable=False),
        sa.Column('verdict', sa.String(length=64), nullable=False),
        sa.Column('comparison_metrics', postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), 'sqlite'), nullable=False),
        sa.Column('tolerance_applied', postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), 'sqlite'), nullable=True),
        sa.Column('interpretation', sa.Text(), nullable=False),
        sa.Column('comparison_hash', sa.String(length=64), nullable=False),
        sa.Column('computed_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['session_id'], ['blind_engineering_sessions.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['submission_id'], ['blind_submissions.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('session_id', 'comparison_policy_version', name='uq_blind_session_comparison_policy'),
    )

    op.create_index('ix_blind_comparisons_session_policy', 'blind_comparison_results', ['session_id', 'comparison_policy_version'])
    op.create_index('ix_blind_comparisons_hash', 'blind_comparison_results', ['comparison_hash'])

    # Apply PostgreSQL RLS if running on PostgreSQL engine
    bind = op.get_bind()
    if bind and "postgres" in bind.dialect.name:
        from suspensionlab.backend.database.rls import generate_table_rls_sql
        for stmt in generate_table_rls_sql('blind_comparison_results'):
            op.execute(sa.text(stmt))


def downgrade() -> None:
    op.drop_index('ix_blind_comparisons_hash', table_name='blind_comparison_results')
    op.drop_index('ix_blind_comparisons_session_policy', table_name='blind_comparison_results')
    op.drop_table('blind_comparison_results')
