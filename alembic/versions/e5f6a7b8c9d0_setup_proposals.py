"""setup proposals

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-08-23

Creates the immutable `setup_proposals` table (Issue 50): traceable setup
recommendations generated from twin calibration + candidate search.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "e5f6a7b8c9d0"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None


def _json_type():
    return sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def _uuid():
    return sa.UUID()


def upgrade() -> None:
    op.create_table(
        "setup_proposals",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("twin_id", _uuid(),
                  sa.ForeignKey("vehicle_twins.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", _uuid(), nullable=False),
        sa.Column("team_id", _uuid(), nullable=True),
        sa.Column("problem", sa.Text(), nullable=False),
        sa.Column("focus", sa.String(32), nullable=False),
        sa.Column("baseline_params", _json_type(), nullable=False),
        sa.Column("tested_setups", sa.Integer(), nullable=False),
        sa.Column("feasible_found", sa.Integer(), nullable=False),
        sa.Column("recommended_params", _json_type(), nullable=False),
        sa.Column("param_changes", _json_type(), nullable=False),
        sa.Column("predicted_effects", _json_type(), nullable=False),
        sa.Column("constraint_violations", _json_type(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(16), nullable=False, server_default="PROPOSED"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    with op.batch_alter_table("setup_proposals", schema=None) as batch_op:
        batch_op.create_index("ix_proposals_twin_ts", ["twin_id", "created_at"])
        batch_op.create_index("ix_proposals_user_ts", ["user_id", "created_at"])


def downgrade() -> None:
    op.drop_table("setup_proposals")
