"""simulation run artifacts

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-08-23

Creates the immutable `simulation_runs` table (Issue 32): every completed
simulation becomes a RUN-xxxxxx artifact with full engineering context,
version pinning and integrity hashes.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "c3d4e5f6a7b8"
down_revision = "b2c3d4e5f6a7"
branch_labels = None
depends_on = None


def _json_type():
    return sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def _uuid():
    return sa.UUID()


def upgrade() -> None:
    op.create_table(
        "simulation_runs",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("seq", sa.Integer(), nullable=False, unique=True),
        sa.Column("label", sa.String(24), nullable=False),
        sa.Column("job_id", _uuid(), nullable=True),
        sa.Column("user_id", _uuid(), nullable=False),
        sa.Column("team_id", _uuid(), nullable=True),
        sa.Column("simulation_type", sa.String(50), nullable=False),
        sa.Column("title", sa.String(200), nullable=False, server_default=""),
        sa.Column("vehicle_ref", sa.String(255), nullable=True),
        sa.Column("setup_ref", sa.String(255), nullable=True),
        sa.Column("tire_ref", sa.String(255), nullable=True),
        sa.Column("track_ref", sa.String(255), nullable=True),
        sa.Column("telemetry_ref", sa.String(255), nullable=True),
        sa.Column("objective", sa.String(100), nullable=True),
        sa.Column("constraints", _json_type(), nullable=True),
        sa.Column("params", _json_type(), nullable=False),
        sa.Column("profile", _json_type(), nullable=True),
        sa.Column("result", _json_type(), nullable=False),
        sa.Column("warnings", _json_type(), nullable=True),
        sa.Column("model_validity", _json_type(), nullable=True),
        sa.Column("software_version", sa.String(32), nullable=False),
        sa.Column("physics_version", sa.String(32), nullable=False),
        sa.Column("kinematics_version", sa.String(32), nullable=False, server_default="unknown"),
        sa.Column("solver_version", sa.String(32), nullable=False),
        sa.Column("git_build_id", sa.String(64), nullable=True),
        sa.Column("params_hash", sa.String(64), nullable=False),
        sa.Column("result_hash", sa.String(64), nullable=False),
        sa.Column("input_hash", sa.String(64), nullable=True),
        sa.Column("compute_seconds", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    with op.batch_alter_table("simulation_runs", schema=None) as batch_op:
        batch_op.create_index("ix_simruns_user_ts", ["user_id", "created_at"])
        batch_op.create_index("ix_simruns_team_ts", ["team_id", "created_at"])
        batch_op.create_index("ix_simruns_job", ["job_id"])
        batch_op.create_index("ix_simruns_label", ["label"], unique=True)


def downgrade() -> None:
    with op.batch_alter_table("simulation_runs", schema=None) as batch_op:
        batch_op.drop_index("ix_simruns_label")
        batch_op.drop_index("ix_simruns_job")
        batch_op.drop_index("ix_simruns_team_ts")
        batch_op.drop_index("ix_simruns_user_ts")
    op.drop_table("simulation_runs")
