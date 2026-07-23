"""lemon_squeezy_migration

Revision ID: 743884f94247
Revises: 7e44398ceef5
Create Date: 2026-06-11 03:30:19.058258

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import sqlite

# revision identifiers, used by Alembic.
revision: str = '743884f94247'
down_revision: Union[str, Sequence[str], None] = '7e44398ceef5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.create_table('lemon_events',
    sa.Column('event_id', sa.String(), nullable=False),
    sa.Column('payload', sa.JSON(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('event_id')
    )
    with op.batch_alter_table('lemon_events', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_lemon_events_event_id'), ['event_id'], unique=False)

    op.execute("DROP TABLE IF EXISTS user_api_keys")
    op.execute("DROP TABLE IF EXISTS _alembic_tmp_jobs")
    op.execute("DROP TABLE IF EXISTS stripe_events")

    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('lemon_customer_id', sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column('lemon_subscription_id', sa.String(length=255), nullable=True))
        batch_op.create_index('ix_users_lemon_cust', ['lemon_customer_id'], unique=False)
        batch_op.drop_index('ix_users_stripe_cust')
        batch_op.drop_column('stripe_customer_id')
        batch_op.drop_column('stripe_subscription_id')
        batch_op.drop_column('tier')


def downgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('stripe_subscription_id', sa.VARCHAR(length=255), nullable=True))
        batch_op.add_column(sa.Column('stripe_customer_id', sa.VARCHAR(length=255), nullable=True))
        batch_op.drop_index('ix_users_lemon_cust')
        batch_op.create_index(batch_op.f('ix_users_stripe_cust'), ['stripe_customer_id'], unique=False)
        batch_op.drop_column('lemon_subscription_id')
        batch_op.drop_column('lemon_customer_id')

    with op.batch_alter_table('lemon_events', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_lemon_events_event_id'))

    op.drop_table('lemon_events')
