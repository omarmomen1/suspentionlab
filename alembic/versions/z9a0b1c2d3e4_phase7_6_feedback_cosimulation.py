"""phase7_6_feedback_cosimulation

Revision ID: z9a0b1c2d3e4
Revises: y8z9a0b1c2d3
Create Date: 2026-10-25 07:00:00.000000

Phase 7.6: Genuine Feedback Co-Simulation, Physical Interface Expansion & Numerical Verification:
- co_simulation_coupling_contracts:
    - feedback_topology (VARCHAR 64, e.g. FEEDFORWARD, FEEDBACK_COUPLED)
    - staggered_execution_order (JSON/JSONB, list of participating model IDs in Gauss-Seidel order)
    - energy_residual_tolerance (FLOAT, default 0.05 / 5%)
- solver_execution_jobs:
    - feedback_metrics (JSON/JSONB, contains actuator_work_joules, energy_residual_relative, etc.)
    - cosim_synchronization_mode (VARCHAR 64, e.g. GAUSS_SEIDEL, JACOBI)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'z9a0b1c2d3e4'
down_revision: Union[str, None] = 'y8z9a0b1c2d3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"
    insp = sa.inspect(bind)

    json_type = sa.JSON() if is_sqlite else postgresql.JSONB()

    # 1. Add feedback columns to co_simulation_coupling_contracts
    existing_tables = insp.get_table_names()
    if 'co_simulation_coupling_contracts' in existing_tables:
        existing_cols = [c['name'] for c in insp.get_columns('co_simulation_coupling_contracts')]
        if 'feedback_topology' not in existing_cols:
            op.add_column(
                'co_simulation_coupling_contracts',
                sa.Column('feedback_topology', sa.String(length=64), server_default='FEEDFORWARD', nullable=False)
            )
        if 'staggered_execution_order' not in existing_cols:
            op.add_column(
                'co_simulation_coupling_contracts',
                sa.Column('staggered_execution_order', json_type, server_default='[]', nullable=False)
            )
        if 'energy_residual_tolerance' not in existing_cols:
            op.add_column(
                'co_simulation_coupling_contracts',
                sa.Column('energy_residual_tolerance', sa.Float(), server_default='0.05', nullable=False)
            )

        existing_indices = [idx['name'] for idx in insp.get_indexes('co_simulation_coupling_contracts')]
        if 'ix_cosim_contracts_topology' not in existing_indices:
            op.create_index(
                'ix_cosim_contracts_topology',
                'co_simulation_coupling_contracts',
                ['feedback_topology']
            )

    # 2. Add feedback metrics and synchronization mode to solver_execution_jobs
    if 'solver_execution_jobs' in existing_tables:
        existing_job_cols = [c['name'] for c in insp.get_columns('solver_execution_jobs')]
        if 'feedback_metrics' not in existing_job_cols:
            op.add_column(
                'solver_execution_jobs',
                sa.Column('feedback_metrics', json_type, server_default='{}', nullable=False)
            )
        if 'cosim_synchronization_mode' not in existing_job_cols:
            op.add_column(
                'solver_execution_jobs',
                sa.Column('cosim_synchronization_mode', sa.String(length=64), server_default='GAUSS_SEIDEL', nullable=False)
            )

        existing_job_indices = [idx['name'] for idx in insp.get_indexes('solver_execution_jobs')]
        if 'ix_solver_execution_cosim_sync' not in existing_job_indices:
            op.create_index(
                'ix_solver_execution_cosim_sync',
                'solver_execution_jobs',
                ['cosim_synchronization_mode']
            )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    existing_tables = insp.get_table_names()

    # 1. Revert solver_execution_jobs additions
    if 'solver_execution_jobs' in existing_tables:
        existing_job_indices = [idx['name'] for idx in insp.get_indexes('solver_execution_jobs')]
        if 'ix_solver_execution_cosim_sync' in existing_job_indices:
            op.drop_index('ix_solver_execution_cosim_sync', table_name='solver_execution_jobs')

        existing_job_cols = [c['name'] for c in insp.get_columns('solver_execution_jobs')]
        if 'cosim_synchronization_mode' in existing_job_cols:
            op.drop_column('solver_execution_jobs', 'cosim_synchronization_mode')
        if 'feedback_metrics' in existing_job_cols:
            op.drop_column('solver_execution_jobs', 'feedback_metrics')

    # 2. Revert co_simulation_coupling_contracts additions
    if 'co_simulation_coupling_contracts' in existing_tables:
        existing_indices = [idx['name'] for idx in insp.get_indexes('co_simulation_coupling_contracts')]
        if 'ix_cosim_contracts_topology' in existing_indices:
            op.drop_index('ix_cosim_contracts_topology', table_name='co_simulation_coupling_contracts')

        existing_cols = [c['name'] for c in insp.get_columns('co_simulation_coupling_contracts')]
        if 'energy_residual_tolerance' in existing_cols:
            op.drop_column('co_simulation_coupling_contracts', 'energy_residual_tolerance')
        if 'staggered_execution_order' in existing_cols:
            op.drop_column('co_simulation_coupling_contracts', 'staggered_execution_order')
        if 'feedback_topology' in existing_cols:
            op.drop_column('co_simulation_coupling_contracts', 'feedback_topology')
