"""setup proposal approval provenance columns
 
Revision ID: i9d0e1f2a3b4
Revises: h8c9d0e1f2a3
Create Date: 2026-09-01
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'i9d0e1f2a3b4'
down_revision = 'h8c9d0e1f2a3'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('setup_proposals', schema=None) as batch_op:
        batch_op.add_column(sa.Column('proposal_hash', sa.String(64), nullable=True))
        batch_op.add_column(sa.Column('approved_by_user_id', postgresql.UUID(as_uuid=True), nullable=True))
        batch_op.add_column(sa.Column('approved_by_role', sa.String(50), nullable=True))
        batch_op.add_column(sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column('approval_signature', sa.String(128), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('setup_proposals', schema=None) as batch_op:
        batch_op.drop_column('approval_signature')
        batch_op.drop_column('approved_at')
        batch_op.drop_column('approved_by_role')
        batch_op.drop_column('approved_by_user_id')
        batch_op.drop_column('proposal_hash')
