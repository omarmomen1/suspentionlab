"""phase 7.2 solver exchange lifecycle and artifact tables

Revision ID: s9t0u1v2w3x4
Revises: r8s9t0u1v2w3
Create Date: 2026-10-12
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 's9t0u1v2w3x4'
down_revision = 'r8s9t0u1v2w3'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Create solver_exchange_artifacts table
    op.create_table(
        'solver_exchange_artifacts',
        sa.Column('id', postgresql.UUID(as_uuid=True).with_variant(sa.Uuid(), 'sqlite'), primary_key=True),
        sa.Column('organization_id', postgresql.UUID(as_uuid=True).with_variant(sa.Uuid(), 'sqlite'), nullable=True),
        sa.Column('team_id', postgresql.UUID(as_uuid=True).with_variant(sa.Uuid(), 'sqlite'), nullable=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True).with_variant(sa.Uuid(), 'sqlite'), nullable=False),
        sa.Column('artifact_name', sa.String(length=255), nullable=False),
        sa.Column('file_format', sa.String(length=64), nullable=False),
        sa.Column('mime_type', sa.String(length=128), nullable=False),
        sa.Column('size_bytes', sa.Integer(), nullable=False),
        sa.Column('sha256_hash', sa.String(length=64), nullable=False),
        sa.Column('storage_path', sa.String(length=512), nullable=False),
        sa.Column('direction', sa.String(length=32), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['team_id'], ['teams.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='RESTRICT'),
    )
    op.create_index('ix_solver_exchange_artifacts_tenant', 'solver_exchange_artifacts', ['team_id', 'sha256_hash'])
    op.create_index('ix_solver_exchange_artifacts_user', 'solver_exchange_artifacts', ['user_id', 'sha256_hash'])
    op.create_index('ix_solver_exchange_artifacts_hash', 'solver_exchange_artifacts', ['sha256_hash'])

    # 2. Create solver_exchange_operations table
    op.create_table(
        'solver_exchange_operations',
        sa.Column('id', postgresql.UUID(as_uuid=True).with_variant(sa.Uuid(), 'sqlite'), primary_key=True),
        sa.Column('organization_id', postgresql.UUID(as_uuid=True).with_variant(sa.Uuid(), 'sqlite'), nullable=True),
        sa.Column('team_id', postgresql.UUID(as_uuid=True).with_variant(sa.Uuid(), 'sqlite'), nullable=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True).with_variant(sa.Uuid(), 'sqlite'), nullable=False),
        sa.Column('operation_type', sa.String(length=32), nullable=False),
        sa.Column('adapter_id', sa.String(length=128), nullable=False),
        sa.Column('adapter_version', sa.String(length=32), nullable=False),
        sa.Column('solver_name', sa.String(length=64), nullable=False),
        sa.Column('state', sa.String(length=32), nullable=False, server_default='PENDING'),
        sa.Column('input_artifact_id', postgresql.UUID(as_uuid=True).with_variant(sa.Uuid(), 'sqlite'), nullable=True),
        sa.Column('output_artifact_id', postgresql.UUID(as_uuid=True).with_variant(sa.Uuid(), 'sqlite'), nullable=True),
        sa.Column('canonical_manifest_version', sa.String(length=32), nullable=False, server_default='1.0.0'),
        sa.Column('manifest_hash', sa.String(length=64), nullable=True),
        sa.Column('coordinate_frame', postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), 'sqlite'), server_default='{}', nullable=False),
        sa.Column('units_summary', postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), 'sqlite'), server_default='{}', nullable=False),
        sa.Column('mapping_diagnostics', postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), 'sqlite'), server_default='{}', nullable=False),
        sa.Column('validation_diagnostics', postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), 'sqlite'), server_default='{}', nullable=False),
        sa.Column('failure_reason', sa.Text(), nullable=True),
        sa.Column('idempotency_key', sa.String(length=128), nullable=True),
        sa.Column('is_executed', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('is_physically_validated', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['team_id'], ['teams.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['input_artifact_id'], ['solver_exchange_artifacts.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['output_artifact_id'], ['solver_exchange_artifacts.id'], ondelete='SET NULL'),
    )
    op.create_index('ix_solver_exchange_ops_tenant', 'solver_exchange_operations', ['team_id', 'state', 'created_at'])
    op.create_index('ix_solver_exchange_ops_user', 'solver_exchange_operations', ['user_id', 'state', 'created_at'])
    op.create_index('ix_solver_exchange_ops_idemp', 'solver_exchange_operations', ['user_id', 'idempotency_key'])
    op.create_index('ix_solver_exchange_ops_hash', 'solver_exchange_operations', ['manifest_hash'])


def downgrade() -> None:
    op.drop_index('ix_solver_exchange_ops_hash', table_name='solver_exchange_operations')
    op.drop_index('ix_solver_exchange_ops_idemp', table_name='solver_exchange_operations')
    op.drop_index('ix_solver_exchange_ops_user', table_name='solver_exchange_operations')
    op.drop_index('ix_solver_exchange_ops_tenant', table_name='solver_exchange_operations')
    op.drop_table('solver_exchange_operations')

    op.drop_index('ix_solver_exchange_artifacts_hash', table_name='solver_exchange_artifacts')
    op.drop_index('ix_solver_exchange_artifacts_user', table_name='solver_exchange_artifacts')
    op.drop_index('ix_solver_exchange_artifacts_tenant', table_name='solver_exchange_artifacts')
    op.drop_table('solver_exchange_artifacts')
