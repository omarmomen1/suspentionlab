"""wave6: versioned profile revisions with diff

Revision ID: z88a0b1c2d3e
Revises: z87a0b1c2d3e
Create Date: 2026-11-26

Wave 6 §2: versioned setup revisions. Every saved revision stores the parent
revision ID, params snapshot, parameter diff, and author/timestamp so teams
can diff and roll back any two setup revisions.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "z88a0b1c2d3e"
down_revision = "z87a0b1c2d3e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "profile_revisions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("profile_id", sa.Uuid(), sa.ForeignKey("vehicle_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("parent_revision_id", sa.Uuid(), sa.ForeignKey("profile_revisions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("params", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("param_diff", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("author_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("author_name", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_profile_revisions_profile_id", "profile_revisions", ["profile_id"])
    op.create_index("ix_profile_revisions_id", "profile_revisions", ["id"])


def downgrade() -> None:
    op.drop_index("ix_profile_revisions_id", table_name="profile_revisions")
    op.drop_index("ix_profile_revisions_profile_id", table_name="profile_revisions")
    op.drop_table("profile_revisions")
