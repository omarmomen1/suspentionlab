"""add report approvals and engineering metadata

Revision ID: k1f2c3d4e5f6
Revises: j0e1f2a3b4c5
Create Date: 2026-09-03
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'k1f2c3d4e5f6'
down_revision = 'j0e1f2a3b4c5'
branch_labels = None
depends_on = None


def _json_type():
    return sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    with op.batch_alter_table('shared_reports', schema=None) as batch_op:
        batch_op.add_column(sa.Column('status', sa.String(16), server_default='PROPOSED', nullable=False))
        batch_op.add_column(sa.Column('doc_id', sa.String(32), nullable=True))
        batch_op.add_column(sa.Column('vehicle_ref', sa.String(255), nullable=True))
        batch_op.add_column(sa.Column('setup_ref', sa.String(255), nullable=True))
        batch_op.add_column(sa.Column('tire_ref', sa.String(255), nullable=True))
        batch_op.add_column(sa.Column('track_ref', sa.String(255), nullable=True))
        batch_op.add_column(sa.Column('telemetry_ref', sa.String(255), nullable=True))
        batch_op.add_column(sa.Column('solver_version', sa.String(64), nullable=True))
        batch_op.add_column(sa.Column('software_build', sa.String(64), nullable=True))
        batch_op.add_column(sa.Column('validation_status', sa.String(32), server_default='PASS', nullable=True))
        batch_op.add_column(sa.Column('correlation_pct', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('artifact_hash', sa.String(64), nullable=True))
        batch_op.add_column(sa.Column('approved_by_user_id', postgresql.UUID(as_uuid=True), nullable=True))
        batch_op.add_column(sa.Column('approved_by_email', sa.String(255), nullable=True))
        batch_op.add_column(sa.Column('approved_by_role', sa.String(50), nullable=True))
        batch_op.add_column(sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column('approval_comment', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('approval_signature', sa.String(128), nullable=True))
        batch_op.add_column(sa.Column('metrics', _json_type(), nullable=True))
        batch_op.add_column(sa.Column('telemetry_analysis', _json_type(), nullable=True))
        batch_op.add_column(sa.Column('optimization_data', _json_type(), nullable=True))
        batch_op.add_column(sa.Column('validation_data', _json_type(), nullable=True))
        batch_op.add_column(sa.Column('plot_data', _json_type(), nullable=True))
        batch_op.create_index('ix_shared_reports_status', ['status'])


def downgrade() -> None:
    with op.batch_alter_table('shared_reports', schema=None) as batch_op:
        batch_op.drop_index('ix_shared_reports_status')
        batch_op.drop_column('plot_data')
        batch_op.drop_column('validation_data')
        batch_op.drop_column('optimization_data')
        batch_op.drop_column('telemetry_analysis')
        batch_op.drop_column('metrics')
        batch_op.drop_column('approval_signature')
        batch_op.drop_column('approval_comment')
        batch_op.drop_column('approved_at')
        batch_op.drop_column('approved_by_role')
        batch_op.drop_column('approved_by_email')
        batch_op.drop_column('approved_by_user_id')
        batch_op.drop_column('artifact_hash')
        batch_op.drop_column('correlation_pct')
        batch_op.drop_column('validation_status')
        batch_op.drop_column('software_build')
        batch_op.drop_column('solver_version')
        batch_op.drop_column('telemetry_ref')
        batch_op.drop_column('track_ref')
        batch_op.drop_column('tire_ref')
        batch_op.drop_column('setup_ref')
        batch_op.drop_column('vehicle_ref')
        batch_op.drop_column('doc_id')
        batch_op.drop_column('status')
