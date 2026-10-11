"""audit tables + shared report provenance

Revision ID: b2c3d4e5f6a7
Revises: a1f2c3d4e5f6
Create Date: 2026-08-22

Creates:
  * audit_logs             — durable security/compliance events (team-scoped)
  * engineering_audit_logs — immutable per-simulation provenance records (#23)

Adds to shared_reports (#24):
  * provenance columns: simulation_id, input_hash, result_hash,
    params_hash, software_version, physics_version, provenance, signature
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "b2c3d4e5f6a7"
down_revision = "a1f2c3d4e5f6"
branch_labels = None
depends_on = None


def _json_type():
    return sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def _uuid():
    return sa.UUID()


def upgrade() -> None:
    # ── audit_logs ────────────────────────────────────────────────────────
    op.create_table(
        "audit_logs",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("event", sa.String(64), nullable=False),
        sa.Column("user_id", _uuid(), nullable=True),
        sa.Column("team_id", _uuid(), nullable=True),
        sa.Column("ip", sa.String(64), nullable=True),
        sa.Column("user_agent", sa.String(255), nullable=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metadata", _json_type(), nullable=True),
        sa.Column("previous_hash", sa.String(64), nullable=True),
        sa.Column("hash", sa.String(64), nullable=True),
    )
    with op.batch_alter_table("audit_logs", schema=None) as batch_op:
        batch_op.create_index("ix_audit_logs_team_ts", ["team_id", "timestamp"])
        batch_op.create_index("ix_audit_logs_user_ts", ["user_id", "timestamp"])
        batch_op.create_index("ix_audit_logs_user_id", ["user_id"])

    # ── engineering_audit_logs ────────────────────────────────────────────
    op.create_table(
        "engineering_audit_logs",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("job_id", _uuid(), nullable=True),
        sa.Column("user_id", _uuid(), nullable=True),
        sa.Column("team_id", _uuid(), nullable=True),
        sa.Column("simulation_type", sa.String(50), nullable=False),
        sa.Column("vehicle_ref", sa.String(255), nullable=True),
        sa.Column("setup_version", sa.String(100), nullable=True),
        sa.Column("dataset_ref", sa.String(255), nullable=True),
        sa.Column("software_version", sa.String(32), nullable=False, server_default="0.0.0"),
        sa.Column("physics_version", sa.String(32), nullable=False, server_default="unknown"),
        sa.Column("simulation_version", sa.String(32), nullable=False, server_default="unknown"),
        sa.Column("params_hash", sa.String(64), nullable=False),
        sa.Column("result_hash", sa.String(64), nullable=False),
        sa.Column("input_hash", sa.String(64), nullable=True),
        sa.Column("compute_seconds", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    with op.batch_alter_table("engineering_audit_logs", schema=None) as batch_op:
        batch_op.create_index("ix_eng_audit_user_ts", ["user_id", "created_at"])
        batch_op.create_index("ix_eng_audit_team_ts", ["team_id", "created_at"])
        batch_op.create_index("ix_eng_audit_job", ["job_id"])

    # ── shared_reports provenance (#24) ───────────────────────────────────
    with op.batch_alter_table("shared_reports", schema=None) as batch_op:
        batch_op.add_column(sa.Column("owner_id", _uuid(), nullable=True))
        batch_op.add_column(sa.Column("simulation_id", _uuid(), nullable=True))
        batch_op.add_column(sa.Column("params_hash", sa.String(64), nullable=True))
        batch_op.add_column(sa.Column("result_hash", sa.String(64), nullable=True))
        batch_op.add_column(sa.Column("input_hash", sa.String(64), nullable=True))
        batch_op.add_column(sa.Column("software_version", sa.String(32), nullable=True))
        batch_op.add_column(sa.Column("physics_version", sa.String(32), nullable=True))
        batch_op.add_column(sa.Column("provenance", sa.String(20), nullable=False, server_default="client-asserted"))
        batch_op.add_column(sa.Column("signature", sa.String(128), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("shared_reports", schema=None) as batch_op:
        batch_op.drop_column("signature")
        batch_op.drop_column("provenance")
        batch_op.drop_column("physics_version")
        batch_op.drop_column("software_version")
        batch_op.drop_column("input_hash")
        batch_op.drop_column("result_hash")
        batch_op.drop_column("params_hash")
        batch_op.drop_column("simulation_id")
        batch_op.drop_column("owner_id")
    op.drop_table("engineering_audit_logs")
    op.drop_table("audit_logs")
