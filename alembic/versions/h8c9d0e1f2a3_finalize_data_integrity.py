"""finalize data integrity and engineering lineage snapshots

Revision ID: h8c9d0e1f2a3
Revises: g7b8c9d0e1f2
Create Date: 2026-08-31
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "h8c9d0e1f2a3"
down_revision = "g7b8c9d0e1f2"
branch_labels = None
depends_on = None


def _json_type():
    return sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    with op.batch_alter_table("simulation_runs", schema=None) as batch_op:
        batch_op.add_column(sa.Column("tire_snapshot", _json_type(), nullable=True))
        batch_op.add_column(sa.Column("aero_snapshot", _json_type(), nullable=True))
        batch_op.add_column(sa.Column("track_geometry_hash", sa.String(64), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("simulation_runs", schema=None) as batch_op:
        batch_op.drop_column("track_geometry_hash")
        batch_op.drop_column("aero_snapshot")
        batch_op.drop_column("tire_snapshot")
