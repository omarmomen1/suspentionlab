"""digital twin and calibration learnings

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-08-23

Creates:
  * vehicle_twins             — Digital Setup Twin per car/setup (#40)
  * calibration_observations  — learning store: param deltas → measured
                                responses, conditioned on operating state (#41)
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "d4e5f6a7b8c9"
down_revision = "c3d4e5f6a7b8"
branch_labels = None
depends_on = None


def _json_type():
    return sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def _uuid():
    return postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "vehicle_twins",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("car_ref", sa.String(120), nullable=False),
        sa.Column("setup_ref", sa.String(120), nullable=False),
        sa.Column("track_ref", sa.String(120), nullable=True),
        sa.Column("user_id", _uuid(), nullable=False),
        sa.Column("team_id", _uuid(), nullable=True),
        sa.Column("base_params", _json_type(), nullable=False),
        sa.Column("calibrated_params", _json_type(), nullable=True),
        sa.Column("calibration_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_calibration_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_identification", _json_type(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_twins_user", "vehicle_twins", ["user_id"])
    op.create_index("ix_twins_team", "vehicle_twins", ["team_id"])
    op.create_index("ix_twins_car_setup", "vehicle_twins", ["car_ref", "setup_ref"])

    op.create_table(
        "calibration_observations",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("twin_id", _uuid(),
                  sa.ForeignKey("vehicle_twins.id", ondelete="CASCADE"), nullable=False),
        sa.Column("param_deltas", _json_type(), nullable=False),
        sa.Column("responses", _json_type(), nullable=False),
        sa.Column("conditions", _json_type(), nullable=True),
        sa.Column("n_samples", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_calobs_twin_ts", "calibration_observations", ["twin_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_calobs_twin_ts", table_name="calibration_observations")
    op.drop_table("calibration_observations")
    op.drop_index("ix_twins_car_setup", table_name="vehicle_twins")
    op.drop_index("ix_twins_team", table_name="vehicle_twins")
    op.drop_index("ix_twins_user", table_name="vehicle_twins")
    op.drop_table("vehicle_twins")
