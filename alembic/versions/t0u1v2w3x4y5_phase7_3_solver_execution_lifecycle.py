"""phase7_3_solver_execution_lifecycle

Revision ID: t0u1v2w3x4y5
Revises: s9t0u1v2w3x4
Create Date: 2026-10-12 10:10:00.000000

Phase 7.3: Persistent solver execution jobs table:
- solver_execution_jobs
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 't0u1v2w3x4y5'
down_revision: Union[str, None] = 's9t0u1v2w3x4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'solver_execution_jobs',
        sa.Column('id', postgresql.UUID(as_uuid=True).with_variant(sa.Uuid(), 'sqlite'), primary_key=True),
        sa.Column('organization_id', postgresql.UUID(as_uuid=True).with_variant(sa.Uuid(), 'sqlite'), nullable=True),
        sa.Column('team_id', postgresql.UUID(as_uuid=True).with_variant(sa.Uuid(), 'sqlite'), nullable=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True).with_variant(sa.Uuid(), 'sqlite'), nullable=False),
        sa.Column('solver_name', sa.String(length=64), nullable=False),
        sa.Column('solver_version', sa.String(length=32), nullable=False),
        sa.Column('adapter_id', sa.String(length=128), nullable=False),
        sa.Column('state', sa.String(length=32), nullable=False, server_default='QUEUED'),
        sa.Column('input_artifact_id', postgresql.UUID(as_uuid=True).with_variant(sa.Uuid(), 'sqlite'), nullable=True),
        sa.Column('input_artifact_hash', sa.String(length=64), nullable=False),
        sa.Column('output_artifact_ids', postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), 'sqlite'), server_default='[]', nullable=False),
        sa.Column('execution_config', postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), 'sqlite'), server_default='{}', nullable=False),
        sa.Column('resource_limits', postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), 'sqlite'), server_default='{}', nullable=False),
        sa.Column('pid', sa.Integer(), nullable=True),
        sa.Column('exit_code', sa.Integer(), nullable=True),
        sa.Column('stdout_excerpt', sa.Text(), nullable=True),
        sa.Column('stderr_excerpt', sa.Text(), nullable=True),
        sa.Column('failure_reason', sa.Text(), nullable=True),
        sa.Column('error_category', sa.String(length=64), nullable=True),
        sa.Column('is_executed', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('is_physically_validated', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('execution_provenance', postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), 'sqlite'), server_default='{}', nullable=False),
        sa.Column('reconciliation_summary', postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), 'sqlite'), server_default='{}', nullable=False),
        sa.Column('idempotency_key', sa.String(length=128), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['team_id'], ['teams.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['input_artifact_id'], ['solver_exchange_artifacts.id'], ondelete='SET NULL'),
    )
    op.create_index('ix_solver_execution_jobs_tenant_state', 'solver_execution_jobs', ['team_id', 'state', 'created_at'])
    op.create_index('ix_solver_execution_jobs_user_state', 'solver_execution_jobs', ['user_id', 'state', 'created_at'])
    op.create_index('ix_solver_execution_jobs_idemp', 'solver_execution_jobs', ['user_id', 'idempotency_key'])
    op.create_index('ix_solver_execution_jobs_hash', 'solver_execution_jobs', ['input_artifact_hash'])


def downgrade() -> None:
    op.drop_index('ix_solver_execution_jobs_hash', table_name='solver_execution_jobs')
    op.drop_index('ix_solver_execution_jobs_idemp', table_name='solver_execution_jobs')
    op.drop_index('ix_solver_execution_jobs_user_state', table_name='solver_execution_jobs')
    op.drop_index('ix_solver_execution_jobs_tenant_state', table_name='solver_execution_jobs')
    op.drop_table('solver_execution_jobs')
