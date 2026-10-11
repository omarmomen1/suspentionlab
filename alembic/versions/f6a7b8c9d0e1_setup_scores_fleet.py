"""setup_scores fleet benchmark table (Tier A1).

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-08-26
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "f6a7b8c9d0e1"
down_revision = "e5f6a7b8c9d0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "setup_scores",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("vehicle_class", sa.String(32), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("comfort", sa.Float(), nullable=False),
        sa.Column("grip", sa.Float(), nullable=False),
        sa.Column("control", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("(CURRENT_TIMESTAMP)")),
    )
    with op.batch_alter_table("setup_scores", schema=None) as batch_op:
        batch_op.create_index("ix_setup_scores_class_score", ["vehicle_class", "score"])


def downgrade() -> None:
    op.drop_table("setup_scores")
