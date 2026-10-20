"""phase7_5_cosimulation_contracts

Revision ID: y8z9a0b1c2d3
Revises: x7y8z9a0b1c2
Create Date: 2026-10-20 05:00:00.000000

Phase 7.5: Multi-Domain Co-Simulation Contracts, Time Synchronization & Worker Fencing:
- co_simulation_coupling_contracts table
- solver_execution_jobs: worker_id, lease_generation, coupling_contract_id, co_simulation_diagnostics
- indexes for worker lease fencing and contract lookup
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'y8z9a0b1c2d3'
down_revision: Union[str, None] = 'x7y8z9a0b1c2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"
    insp = sa.inspect(bind)

    # Dialect-aware types
    json_type = sa.JSON() if is_sqlite else postgresql.JSONB()
    uuid_type = sa.Uuid() if is_sqlite else postgresql.UUID(as_uuid=True)

    # 1. Create co_simulation_coupling_contracts table if not exists
    existing_tables = insp.get_table_names()
    if 'co_simulation_coupling_contracts' not in existing_tables:
        op.create_table(
            'co_simulation_coupling_contracts',
            sa.Column('id', uuid_type, primary_key=True),
            sa.Column('contract_id', sa.String(length=64), nullable=False),
            sa.Column('name', sa.String(length=255), nullable=False),
            sa.Column('version', sa.String(length=32), server_default='1.0.0', nullable=False),
            sa.Column('description', sa.Text(), nullable=True),
            sa.Column('status', sa.String(length=32), server_default='DRAFT', nullable=False),
            sa.Column('organization_id', uuid_type, nullable=True),
            sa.Column('team_id', uuid_type, nullable=True),
            sa.Column('created_by_user_id', uuid_type, nullable=False),
            sa.Column('participating_models', json_type, server_default='[]', nullable=False),
            sa.Column('connections', json_type, server_default='[]', nullable=False),
            sa.Column('time_sync_config', json_type, server_default='{}', nullable=False),
            sa.Column('operating_bounds', json_type, server_default='{}', nullable=False),
            sa.Column('validation_report', json_type, server_default='{}', nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
            sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], ondelete='RESTRICT'),
            sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='SET NULL'),
            sa.ForeignKeyConstraint(['team_id'], ['teams.id'], ondelete='SET NULL'),
        )
        op.create_index('ix_cosim_contracts_contract_id', 'co_simulation_coupling_contracts', ['contract_id'], unique=True)
        op.create_index('ix_cosim_contracts_status', 'co_simulation_coupling_contracts', ['status'])
        op.create_index('ix_cosim_contracts_tenant_status', 'co_simulation_coupling_contracts', ['team_id', 'status', 'created_at'])
        op.create_index('ix_cosim_contracts_user_status', 'co_simulation_coupling_contracts', ['created_by_user_id', 'status', 'created_at'])
        op.create_index('ix_cosim_contracts_org_status', 'co_simulation_coupling_contracts', ['organization_id', 'status'])

    # 2. Add columns to solver_execution_jobs if not already present
    existing_cols = [c['name'] for c in insp.get_columns('solver_execution_jobs')]
    if 'worker_id' not in existing_cols:
        op.add_column(
            'solver_execution_jobs',
            sa.Column('worker_id', sa.String(length=128), nullable=True),
        )
    if 'lease_generation' not in existing_cols:
        op.add_column(
            'solver_execution_jobs',
            sa.Column('lease_generation', sa.Integer(), server_default='1', nullable=False),
        )
    if 'coupling_contract_id' not in existing_cols:
        op.add_column(
            'solver_execution_jobs',
            sa.Column('coupling_contract_id', uuid_type, nullable=True),
        )
    if 'co_simulation_diagnostics' not in existing_cols:
        op.add_column(
            'solver_execution_jobs',
            sa.Column('co_simulation_diagnostics', json_type, server_default='{}', nullable=False),
        )

    # 3. Add FK and Indexes if not present
    existing_indexes = [ix['name'] for ix in insp.get_indexes('solver_execution_jobs')]
    if not is_sqlite:
        fks = [fk['name'] for fk in insp.get_foreign_keys('solver_execution_jobs')]
        if 'fk_solver_execution_jobs_contract' not in fks:
            op.create_foreign_key(
                'fk_solver_execution_jobs_contract',
                'solver_execution_jobs',
                'co_simulation_coupling_contracts',
                ['coupling_contract_id'],
                ['id'],
                ondelete='SET NULL',
            )

    if 'ix_solver_execution_jobs_worker' not in existing_indexes:
        op.create_index(
            'ix_solver_execution_jobs_worker',
            'solver_execution_jobs',
            ['worker_id', 'lease_generation'],
        )
    if 'ix_solver_execution_jobs_contract' not in existing_indexes:
        op.create_index(
            'ix_solver_execution_jobs_contract',
            'solver_execution_jobs',
            ['coupling_contract_id'],
        )


def downgrade() -> None:
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"
    insp = sa.inspect(bind)

    # 1. Revert solver_execution_jobs changes
    existing_indexes = [ix['name'] for ix in insp.get_indexes('solver_execution_jobs')]
    if 'ix_solver_execution_jobs_contract' in existing_indexes:
        op.drop_index('ix_solver_execution_jobs_contract', table_name='solver_execution_jobs')
    if 'ix_solver_execution_jobs_worker' in existing_indexes:
        op.drop_index('ix_solver_execution_jobs_worker', table_name='solver_execution_jobs')

    if not is_sqlite:
        fks = [fk['name'] for fk in insp.get_foreign_keys('solver_execution_jobs')]
        if 'fk_solver_execution_jobs_contract' in fks:
            op.drop_constraint('fk_solver_execution_jobs_contract', 'solver_execution_jobs', type_='foreignkey')

    existing_cols = [c['name'] for c in insp.get_columns('solver_execution_jobs')]
    if 'co_simulation_diagnostics' in existing_cols:
        op.drop_column('solver_execution_jobs', 'co_simulation_diagnostics')
    if 'coupling_contract_id' in existing_cols:
        op.drop_column('solver_execution_jobs', 'coupling_contract_id')
    if 'lease_generation' in existing_cols:
        op.drop_column('solver_execution_jobs', 'lease_generation')
    if 'worker_id' in existing_cols:
        op.drop_column('solver_execution_jobs', 'worker_id')

    # 2. Drop co_simulation_coupling_contracts table
    existing_tables = insp.get_table_names()
    if 'co_simulation_coupling_contracts' in existing_tables:
        op.drop_index('ix_cosim_contracts_org_status', table_name='co_simulation_coupling_contracts')
        op.drop_index('ix_cosim_contracts_user_status', table_name='co_simulation_coupling_contracts')
        op.drop_index('ix_cosim_contracts_tenant_status', table_name='co_simulation_coupling_contracts')
        op.drop_index('ix_cosim_contracts_status', table_name='co_simulation_coupling_contracts')
        op.drop_index('ix_cosim_contracts_contract_id', table_name='co_simulation_coupling_contracts')
        op.drop_table('co_simulation_coupling_contracts')
