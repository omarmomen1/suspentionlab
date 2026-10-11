"""webhook_endpoints table + teams.data_region (Tier C1/C2).

Revision ID: g7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-08-26
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "g7b8c9d0e1f2"
down_revision = "f6a7b8c9d0e1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "webhook_endpoints",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("user_id", sa.UUID(),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("url", sa.String(2048), nullable=False),
        sa.Column("secret", sa.Text(), nullable=False),
        sa.Column("events", sa.String(255), nullable=False, server_default="job.completed,job.failed"),
        sa.Column("description", sa.String(255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("(CURRENT_TIMESTAMP)")),
    )
    with op.batch_alter_table("webhook_endpoints", schema=None) as batch_op:
        batch_op.create_index("ix_webhooks_user_active", ["user_id", "is_active"])

    with op.batch_alter_table("teams", schema=None) as batch_op:
        batch_op.add_column(sa.Column("data_region", sa.String(32),
                                      nullable=False, server_default="eu-central"))


def downgrade() -> None:
    with op.batch_alter_table("teams", schema=None) as batch_op:
        batch_op.drop_column("data_region")
    op.drop_table("webhook_endpoints")
