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
    return postgresql.UUID(as_uuid=True)


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
    )
    op.create_index("ix_audit_logs_team_ts", "audit_logs", ["team_id", "timestamp"])
    op.create_index("ix_audit_logs_user_ts", "audit_logs", ["user_id", "timestamp"])

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
    op.create_index("ix_eng_audit_user_ts", "engineering_audit_logs", ["user_id", "created_at"])
    op.create_index("ix_eng_audit_team_ts", "engineering_audit_logs", ["team_id", "created_at"])
    op.create_index("ix_eng_audit_job", "engineering_audit_logs", ["job_id"])

    # ── shared_reports provenance (#24) ───────────────────────────────────
    op.add_column("shared_reports", sa.Column("simulation_id", _uuid(), nullable=True))
    op.add_column("shared_reports", sa.Column("params_hash", sa.String(64), nullable=True))
    op.add_column("shared_reports", sa.Column("result_hash", sa.String(64), nullable=True))
    op.add_column("shared_reports", sa.Column("input_hash", sa.String(64), nullable=True))
    op.add_column("shared_reports", sa.Column("software_version", sa.String(32), nullable=True))
    op.add_column("shared_reports", sa.Column("physics_version", sa.String(32), nullable=True))
    op.add_column("shared_reports", sa.Column(
        "provenance", sa.String(20), nullable=False, server_default="client-asserted"))
    op.add_column("shared_reports", sa.Column("signature", sa.String(128), nullable=True))


def downgrade() -> None:
    op.drop_column("shared_reports", "signature")
    op.drop_column("shared_reports", "provenance")
    op.drop_column("shared_reports", "physics_version")
    op.drop_column("shared_reports", "software_version")
    op.drop_column("shared_reports", "input_hash")
    op.drop_column("shared_reports", "result_hash")
    op.drop_column("shared_reports", "params_hash")
    op.drop_column("shared_reports", "simulation_id")
    op.drop_index("ix_eng_audit_job", table_name="engineering_audit_logs")
    op.drop_index("ix_eng_audit_team_ts", table_name="engineering_audit_logs")
    op.drop_index("ix_eng_audit_user_ts", table_name="engineering_audit_logs")
    op.drop_table("engineering_audit_logs")
    op.drop_index("ix_audit_logs_user_ts", table_name="audit_logs")
    op.drop_index("ix_audit_logs_team_ts", table_name="audit_logs")
    op.drop_table("audit_logs")
