"""
backend/database/models/vehicle_twin.py
========================================
Digital Setup Twin (Issue 40) + Learning store (Issue 41).

VehicleTwin — the calibrated digital counterpart of a real car:
    CAR-2026-07 + SETUP-SPA-R4 + track + telemetry → identified parameters.

CalibrationObservation — every calibration event is recorded as a
(param deltas → measured response) pair with operating conditions.
Aggregated over sessions this becomes vehicle-specific engineering
intelligence: "when rear damping changed +7%, this car's comfort metric
responded −4.2% (n=5)". That history is the moat — it cannot be copied,
only earned through use.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, JSON, Integer, Float, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB

JSON_TYPE = JSON().with_variant(JSONB, "postgresql")
from suspensionlab.backend.database.core import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class VehicleTwin(Base):
    __tablename__ = "vehicle_twins"
    __table_args__ = (
        Index("ix_twins_user", "user_id"),
        Index("ix_twins_team", "team_id"),
        Index("ix_twins_car_setup", "car_ref", "setup_ref"),
    )

    id         = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    car_ref    = Column(String(120), nullable=False)     # e.g. CAR-2026-07
    setup_ref  = Column(String(120), nullable=False)     # e.g. SETUP-SPA-R4
    track_ref  = Column(String(120), nullable=True)
    user_id    = Column(PG_UUID(as_uuid=True), nullable=False)
    team_id    = Column(PG_UUID(as_uuid=True), nullable=True)

    # Parameter snapshots
    base_params       = Column(JSON_TYPE, nullable=False)  # as-designed (handbook) params
    calibrated_params = Column(JSON_TYPE, nullable=True)   # after identification

    # Calibration state
    calibration_count      = Column(Integer, nullable=False, default=0)
    last_calibration_at    = Column(DateTime(timezone=True), nullable=True)
    last_identification    = Column(JSON_TYPE, nullable=True)  # full ID report (freqs, zeta, confidence)

    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)


class CalibrationObservation(Base):
    __tablename__ = "calibration_observations"
    __table_args__ = (
        Index("ix_calobs_twin_ts", "twin_id", "created_at"),
    )

    id            = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    twin_id       = Column(PG_UUID(as_uuid=True), ForeignKey("vehicle_twins.id", ondelete="CASCADE"), nullable=False)

    # What changed (identified parameter deltas vs previous state)
    param_deltas  = Column(JSON_TYPE, nullable=False)   # {param: {before, after, delta_pct}}
    # What the car exhibited (measured responses from telemetry)
    responses     = Column(JSON_TYPE, nullable=False)   # {metric: value} e.g. f_n_s_hz, zeta_s
    # Operating conditions for conditioning learnings
    conditions    = Column(JSON_TYPE, nullable=True)    # {speed_band, track, session_len_s, sample_rate}
    n_samples     = Column(Integer, nullable=False, default=0)
    confidence    = Column(Float, nullable=False, default=0.0)  # 0-1 identification confidence

    created_at    = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
