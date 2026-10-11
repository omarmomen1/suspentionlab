"""add job retry lineage columns

Revision ID: l2m3n4o5p6q7
Revises: k1f2c3d4e5f6
Create Date: 2026-09-04
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'l2m3n4o5p6q7'
down_revision = 'k1f2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('jobs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('parent_job_id', postgresql.UUID(as_uuid=True), nullable=True))
        batch_op.add_column(sa.Column('retry_count', sa.Integer(), server_default='0', nullable=False))
        batch_op.add_column(sa.Column('retry_reason', sa.String(255), nullable=True))
        batch_op.create_index('ix_jobs_parent_job_id', ['parent_job_id'])


def downgrade() -> None:
    with op.batch_alter_table('jobs', schema=None) as batch_op:
        batch_op.drop_index('ix_jobs_parent_job_id')
        batch_op.drop_column('retry_reason')
        batch_op.drop_column('retry_count')
        batch_op.drop_column('parent_job_id')
