"""setup_scores fleet benchmark table (Tier A1).

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-08-26
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

# revision identifiers, used by Alembic.
revision = "f6a7b8c9d0e1"
down_revision = "e5f6a7b8c9d0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "setup_scores",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column("vehicle_class", sa.String(32), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("comfort", sa.Float(), nullable=False),
        sa.Column("grip", sa.Float(), nullable=False),
        sa.Column("control", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("(CURRENT_TIMESTAMP)")),
    )
    op.create_index("ix_setup_scores_class_score", "setup_scores", ["vehicle_class", "score"])


def downgrade() -> None:
    op.drop_index("ix_setup_scores_class_score", table_name="setup_scores")
    op.drop_table("setup_scores")
