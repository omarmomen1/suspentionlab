"""phase7_4_execution_hardening

Revision ID: v2w3x4y5z6p74
Revises: u1v2w3x4y5z6
Create Date: 2026-10-13 18:00:00.000000

Phase 7.4: Execution hardening, lease tracking, and benchmark reference metadata:
- lease_expires_at
- heartbeat_at
- execution_mode
- benchmark_reference_type
- index ix_solver_execution_jobs_lease
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'v2w3x4y5z6p74'
down_revision: Union[str, None] = 'u1v2w3x4y5z6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'solver_execution_jobs',
        sa.Column('lease_expires_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        'solver_execution_jobs',
        sa.Column('heartbeat_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        'solver_execution_jobs',
        sa.Column('execution_mode', sa.String(length=32), nullable=False, server_default='TRUSTED_ALLOWLIST'),
    )
    op.add_column(
        'solver_execution_jobs',
        sa.Column('benchmark_reference_type', sa.String(length=64), nullable=True),
    )
    op.create_index(
        'ix_solver_execution_jobs_lease',
        'solver_execution_jobs',
        ['state', 'lease_expires_at'],
    )


def downgrade() -> None:
    op.drop_index('ix_solver_execution_jobs_lease', table_name='solver_execution_jobs')
    op.drop_column('solver_execution_jobs', 'benchmark_reference_type')
    op.drop_column('solver_execution_jobs', 'execution_mode')
    op.drop_column('solver_execution_jobs', 'heartbeat_at')
    op.drop_column('solver_execution_jobs', 'lease_expires_at')
