from sqlalchemy.sql import func
from sqlalchemy import Column, CheckConstraint, String, DateTime, ForeignKey, Integer, JSON, Uuid
from datetime import datetime
import uuid
from suspensionlab.backend.database.core import Base
from suspensionlab.backend.database.models.user import User
from suspensionlab.backend.database.models.team import Team
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

JSON_TYPE = JSON().with_variant(JSONB, "postgresql")

class VehicleProfile(Base):
    __tablename__ = "vehicle_profiles"
    
    id = Column(Uuid, primary_key=True, default=uuid.uuid4, index=True)
    name = Column(String, nullable=False, index=True)
    
    user_id = Column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True) # Creator
    team_id = Column(Uuid, ForeignKey("teams.id", ondelete="SET NULL"), nullable=True, index=True) # Workspace
    
    vehicle_type = Column(String, CheckConstraint("vehicle_type IN ('QUARTER_CAR', 'HALF_CAR', 'FULL_CAR')", name="chk_vehicle_type"), default="QUARTER_CAR")
    params = Column(JSON_TYPE, nullable=False)
    
    # Lineage tracking (Git for setups)
    version = Column(Integer, default=1, nullable=False)
    parent_id = Column(Uuid, ForeignKey("vehicle_profiles.id", ondelete="SET NULL"), nullable=True, index=True)
    
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    user = relationship("User", back_populates="profiles")
    team = relationship("Team", back_populates="profiles")


class ProfileRevision(Base):
    """Versioned setup revision (Wave 6 §2).

    Every saved revision stores the parent revision ID, the full params
    snapshot, the parameter diff against its parent, and author/timestamp,
    so teams can diff and roll back any two setup revisions.
    """
    __tablename__ = "profile_revisions"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4, index=True)
    profile_id = Column(Uuid, ForeignKey("vehicle_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    revision_number = Column(Integer, nullable=False)
    parent_revision_id = Column(Uuid, ForeignKey("profile_revisions.id", ondelete="SET NULL"), nullable=True)
    params = Column(JSON_TYPE, nullable=False)
    param_diff = Column(JSON_TYPE, nullable=False, default=dict)
    author_user_id = Column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    author_name = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    profile = relationship("VehicleProfile", foreign_keys=[profile_id])
    parent_revision = relationship("ProfileRevision", remote_side=[id], foreign_keys=[parent_revision_id])


def compute_params_diff(old: dict, new: dict) -> dict:
    """Flat recursive parameter diff: {path: {old, new}} for changed keys,
    plus explicit added/removed path lists."""
    diff: dict = {}
    added: list = []
    removed: list = []

    def _walk(o, n, path):
        if isinstance(o, dict) and isinstance(n, dict):
            for k in o.keys() - n.keys():
                removed.append(f"{path}{k}")
            for k in n.keys() - o.keys():
                added.append(f"{path}{k}")
            for k in o.keys() & n.keys():
                _walk(o[k], n[k], f"{path}{k}.")
        elif o != n:
            diff[path[:-1]] = {"old": o, "new": n}

    _walk(old or {}, new or {}, "")
    result = {"changed": diff, "added": added, "removed": removed}
    return result
