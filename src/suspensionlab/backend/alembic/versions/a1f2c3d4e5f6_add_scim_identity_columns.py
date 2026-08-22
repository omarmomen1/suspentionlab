"""add_scim_identity_columns

Revision ID: a1f2c3d4e5f6
Revises: d713c8804400
Create Date: 2026-08-22

Adds identity-federation columns to users for SCIM 2.0 provisioning and OIDC SSO:
  * external_id   — the IdP's immutable user identifier
  * auth_provider — 'local' | 'oidc'
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "a1f2c3d4e5f6"
down_revision = "d713c8804400"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("external_id", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("auth_provider", sa.String(length=32), nullable=False, server_default="local"),
    )
    op.create_index("ix_users_external_id", "users", ["external_id"])


def downgrade() -> None:
    op.drop_index("ix_users_external_id", table_name="users")
    op.drop_column("users", "auth_provider")
    op.drop_column("users", "external_id")
