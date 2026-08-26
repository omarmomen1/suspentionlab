"""webhook_endpoints table + teams.data_region (Tier C1/C2).

Revision ID: g7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-08-26
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

# revision identifiers, used by Alembic.
revision = "g7b8c9d0e1f2"
down_revision = "f6a7b8c9d0e1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "webhook_endpoints",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("url", sa.String(2048), nullable=False),
        sa.Column("secret", sa.Text(), nullable=False),
        sa.Column("events", sa.String(255), nullable=False, server_default="job.completed,job.failed"),
        sa.Column("description", sa.String(255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("(CURRENT_TIMESTAMP)")),
    )
    op.create_index("ix_webhooks_user_active", "webhook_endpoints", ["user_id", "is_active"])

    op.add_column("teams", sa.Column("data_region", sa.String(32),
                                     nullable=False, server_default="eu-central"))


def downgrade() -> None:
    op.drop_column("teams", "data_region")
    op.drop_index("ix_webhooks_user_active", table_name="webhook_endpoints")
    op.drop_table("webhook_endpoints")
