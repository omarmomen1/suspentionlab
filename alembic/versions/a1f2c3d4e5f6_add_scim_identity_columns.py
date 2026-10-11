"""add_scim_identity_columns

Revision ID: a1f2c3d4e5f6
Revises: 31ab9076ca94
Create Date: 2026-08-22

Adds identity-federation columns to users for SCIM 2.0 provisioning and OIDC SSO:
  * external_id   — the IdP's immutable user identifier
  * auth_provider — 'local' | 'oidc'
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "a1f2c3d4e5f6"
down_revision = "31ab9076ca94"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("external_id", sa.String(length=255), nullable=True)
        )
        batch_op.add_column(
            sa.Column("auth_provider", sa.String(length=32), nullable=False, server_default="local")
        )
        batch_op.create_index("ix_users_external_id", ["external_id"])


def downgrade() -> None:
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_index("ix_users_external_id")
        batch_op.drop_column("auth_provider")
        batch_op.drop_column("external_id")
