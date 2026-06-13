"""add_shared_reports_table

Revision ID: a1b2c3d4e5f6
Revises: 743884f94247
Create Date: 2026-06-13 12:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '743884f94247'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'shared_reports',
        sa.Column(
            'id',
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text('gen_random_uuid()'),
            nullable=False,
        ),
        sa.Column('token', sa.String(36), unique=True, nullable=False, index=True),
        sa.Column('simulation_type', sa.String(50), nullable=False, server_default='quarter_car'),
        sa.Column('params', sa.JSON(), nullable=False),
        sa.Column('result', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column('view_count', sa.String(), server_default='0', nullable=True),
        sa.Column('is_public', sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column('title', sa.String(200), server_default='', nullable=False),
        sa.Column('notes', sa.String(2000), server_default='', nullable=False),
    )
    op.create_index('ix_shared_reports_token', 'shared_reports', ['token'], unique=True)


def downgrade() -> None:
    op.drop_index('ix_shared_reports_token', table_name='shared_reports')
    op.drop_table('shared_reports')
