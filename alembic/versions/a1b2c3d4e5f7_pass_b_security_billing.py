"""pass b: entitlement source, stripe event ordering, revocation + usage fallback tables

Revision ID: a1b2c3d4e5f7
Revises: z88a0b1c2d3e
Create Date: 2026-11-28

Pass B (enterprise cleanup):
- users.plan_source tracks entitlement provenance (stripe | gumroad | license_key)
  so subscription.deleted never downgrades a non-Stripe entitlement.
- users.billing_last_event_created stores the last applied Stripe event.created
  for stale-event ordering protection.
- revoked_tokens is the durable JTI revocation fallback when Redis is down.
- usage_counters is the durable monthly simulation metering fallback when
  Redis is down (usage meter must reflect actual runs, not stick at 0/500).
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "a1b2c3d4e5f7"
down_revision = "z88a0b1c2d3e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("plan_source", sa.String(length=32), nullable=True))
    op.add_column("users", sa.Column("billing_last_event_created", sa.BigInteger(), nullable=True))

    op.create_table(
        "revoked_tokens",
        sa.Column("jti", sa.String(length=255), primary_key=True),
        sa.Column("reason", sa.String(length=64), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "usage_counters",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("month", sa.String(length=7), primary_key=True),
        sa.Column("count", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_table("usage_counters")
    op.drop_table("revoked_tokens")
    op.drop_column("users", "billing_last_event_created")
    op.drop_column("users", "plan_source")
