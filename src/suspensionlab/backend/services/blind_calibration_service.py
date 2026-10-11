"""
backend/services/blind_calibration_service.py
=============================================
SuspensionLab PRO — Phase 5.4 Engineering Calibration & Longitudinal Track Record Service.

Provides authorized, tenant-isolated data access and aggregation pipelines:
- Retrieves authoritative immutable BlindSubmission and BlindComparisonResult records.
- Computes Basic Outcome Statistics, Brier Scores, and Reliability Curves.
- Enforces personal-workspace and team-level access boundaries.
- Traceability: links every aggregate to exact contributing comparison IDs and session IDs.
- Strictly NO universal engineer skill rating, NO leaderboard, and NO rationale text scoring.
"""
from __future__ import annotations

import copy
import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from suspensionlab.backend.database.models.blind_engineering import (
    BlindEngineeringSession,
    BlindSubmission,
    BlindComparisonResult,
    BlindSessionStatus,
)
from suspensionlab.backend.database.models.team import Team
from suspensionlab.backend.security.auth import UserContext
from suspensionlab.backend.services.blind_calibration_engine import (
    CALIBRATION_POLICY_V1,
    CALIBRATION_POLICY_NAME,
    CALIBRATION_POLICY_V1_SPEC,
    get_calibration_policy_spec,
    compute_calibration_policy_hash,
    evaluate_observation_eligibility,
    compute_outcome_statistics,
    compute_brier_score,
    compute_multiclass_brier_score,
    compute_calibration_curve,
    compute_aggregate_hash,
)

logger = logging.getLogger("blind_calibration_service")


class CalibrationAccessError(Exception):
    """Base exception for calibration access control errors."""
    pass


class UnauthorizedTeamAccessError(CalibrationAccessError):
    """Raised when user is unauthorized to view team calibration records."""
    pass


class TeamNotFoundError(CalibrationAccessError):
    """Raised when requested team does not exist in user tenant."""
    pass


class BlindCalibrationService:
    """
    Authoritative service for longitudinal Blind Engineering calibration analytics.
    """

    @classmethod
    async def _fetch_user_authorized_evaluations(
        cls,
        db: AsyncSession,
        user_context: UserContext,
        prediction_type_filter: Optional[str] = None,
        window_start: Optional[datetime] = None,
        window_end: Optional[datetime] = None,
    ) -> List[Dict[str, Any]]:
        """
        Gathers immutable comparison records for submissions made by the calling user.
        Enforces tenant filtering and strictly queries revealed or completed sessions.
        """
        user_uuid = uuid.UUID(str(user_context.user_id))

        # Query revealed/completed sessions where user submitted the prediction
        query = (
            select(BlindComparisonResult, BlindSubmission, BlindEngineeringSession)
            .join(BlindSubmission, BlindComparisonResult.submission_id == BlindSubmission.id)
            .join(BlindEngineeringSession, BlindComparisonResult.session_id == BlindEngineeringSession.id)
            .where(
                BlindSubmission.submitted_by_user_id == user_uuid,
                BlindEngineeringSession.status.in_([
                    BlindSessionStatus.REVEALED.value,
                    BlindSessionStatus.COMPLETED.value,
                ]),
            )
        )

        # Organization / Tenant boundary enforcement
        if user_context.organization_id is not None:
            org_uuid = uuid.UUID(str(user_context.organization_id))
            query = query.where(
                or_(
                    BlindEngineeringSession.organization_id == org_uuid,
                    BlindEngineeringSession.organization_id.is_(None),
                )
            )

        # Date window filtering if specified
        if window_start is not None:
            query = query.where(BlindComparisonResult.computed_at >= window_start)
        if window_end is not None:
            query = query.where(BlindComparisonResult.computed_at <= window_end)

        # Stable ordering for deterministic aggregation
        query = query.order_by(
            BlindComparisonResult.computed_at.asc(),
            BlindComparisonResult.id.asc(),
        )

        result = await db.execute(query)
        rows = result.all()

        evaluations: List[Dict[str, Any]] = []
        for comp, sub, sess in rows:
            # Enforce personal vs team workspace boundary
            if sess.team_id is not None:
                if user_context.team_id is None or str(sess.team_id) != str(user_context.team_id):
                    # Skip if from a different team
                    continue
            else:
                if str(sess.created_by_user_id) != str(user_context.user_id):
                    # Skip personal sessions created by another user
                    continue

            pred_payload = sub.submission_payload or {}
            p_type = str(pred_payload.get("prediction_type", comp.comparison_type)).strip().upper()

            if prediction_type_filter:
                clean_filter = prediction_type_filter.strip().upper()
                if p_type != clean_filter:
                    continue

            # Check eligibility and format record
            elig = evaluate_observation_eligibility(pred_payload, comp.verdict)

            evaluations.append({
                "comparison_id": str(comp.id),
                "comparison_hash": comp.comparison_hash,
                "comparison_policy_version": comp.comparison_policy_version,
                "comparison_type": comp.comparison_type,
                "verdict": comp.verdict,
                "interpretation": comp.interpretation,
                "comparison_metrics": comp.comparison_metrics,
                "computed_at": comp.computed_at.isoformat() if comp.computed_at else None,
                "session_id": str(sess.id),
                "session_name": sess.name,
                "session_status": sess.status,
                "root_entity_type": sess.root_entity_type,
                "root_entity_id": sess.root_entity_id,
                "revealed_at": sess.revealed_at.isoformat() if sess.revealed_at else None,
                "submission_id": str(sub.id),
                "submission_hash": sub.submission_hash,
                "submitted_at": sub.submitted_at.isoformat() if sub.submitted_at else None,
                "prediction_payload": pred_payload,
                "outcome_identity": comp.outcome_identity,
                "eligibility": elig.to_dict(),
            })

        return evaluations

    @classmethod
    async def _fetch_team_authorized_evaluations(
        cls,
        db: AsyncSession,
        team_id: Union[str, uuid.UUID],
        user_context: UserContext,
        prediction_type_filter: Optional[str] = None,
        window_start: Optional[datetime] = None,
        window_end: Optional[datetime] = None,
    ) -> List[Dict[str, Any]]:
        """
        Gathers immutable comparison records for a specific team.
        Validates caller has explicit team membership / permissions.
        """
        team_uuid = uuid.UUID(str(team_id))

        # Authorization check: User must belong to this team or be admin
        user_team_str = str(user_context.team_id) if user_context.team_id else None
        is_member = (user_team_str == str(team_uuid))
        is_admin = bool(
            user_context.is_admin
            or (user_context.org_role and user_context.org_role.upper() in ("ORG_ADMIN", "ADMIN"))
            or (user_context.team_role and user_context.team_role.upper() in ("OWNER", "ADMIN", "LEAD", "TEAM_LEAD"))
        )

        if not (is_member or is_admin):
            raise UnauthorizedTeamAccessError(f"User is not authorized to view team '{team_id}' calibration.")

        # Verify team exists in organization
        team_res = await db.execute(select(Team).where(Team.id == team_uuid))
        team = team_res.scalar_one_or_none()
        if not team:
            raise TeamNotFoundError(f"Team '{team_id}' not found.")

        if user_context.organization_id is not None:
            org_uuid = uuid.UUID(str(user_context.organization_id))
            if team.organization_id is not None and team.organization_id != org_uuid:
                raise TeamNotFoundError(f"Team '{team_id}' not found.")

        # Query team comparisons
        query = (
            select(BlindComparisonResult, BlindSubmission, BlindEngineeringSession)
            .join(BlindSubmission, BlindComparisonResult.submission_id == BlindSubmission.id)
            .join(BlindEngineeringSession, BlindComparisonResult.session_id == BlindEngineeringSession.id)
            .where(
                BlindEngineeringSession.team_id == team_uuid,
                BlindEngineeringSession.status.in_([
                    BlindSessionStatus.REVEALED.value,
                    BlindSessionStatus.COMPLETED.value,
                ]),
            )
        )

        if window_start is not None:
            query = query.where(BlindComparisonResult.computed_at >= window_start)
        if window_end is not None:
            query = query.where(BlindComparisonResult.computed_at <= window_end)

        query = query.order_by(
            BlindComparisonResult.computed_at.asc(),
            BlindComparisonResult.id.asc(),
        )

        result = await db.execute(query)
        rows = result.all()

        evaluations: List[Dict[str, Any]] = []
        for comp, sub, sess in rows:
            pred_payload = sub.submission_payload or {}
            p_type = str(pred_payload.get("prediction_type", comp.comparison_type)).strip().upper()

            if prediction_type_filter:
                clean_filter = prediction_type_filter.strip().upper()
                if p_type != clean_filter:
                    continue

            elig = evaluate_observation_eligibility(pred_payload, comp.verdict)

            evaluations.append({
                "comparison_id": str(comp.id),
                "comparison_hash": comp.comparison_hash,
                "comparison_policy_version": comp.comparison_policy_version,
                "comparison_type": comp.comparison_type,
                "verdict": comp.verdict,
                "interpretation": comp.interpretation,
                "comparison_metrics": comp.comparison_metrics,
                "computed_at": comp.computed_at.isoformat() if comp.computed_at else None,
                "session_id": str(sess.id),
                "session_name": sess.name,
                "session_status": sess.status,
                "root_entity_type": sess.root_entity_type,
                "root_entity_id": sess.root_entity_id,
                "revealed_at": sess.revealed_at.isoformat() if sess.revealed_at else None,
                "submission_id": str(sub.id),
                "submission_hash": sub.submission_hash,
                "submitted_at": sub.submitted_at.isoformat() if sub.submitted_at else None,
                "prediction_payload": pred_payload,
                "outcome_identity": comp.outcome_identity,
                "eligibility": elig.to_dict(),
            })

        return evaluations

    @classmethod
    async def get_my_calibration_summary(
        cls,
        db: AsyncSession,
        user_context: UserContext,
        prediction_type_filter: Optional[str] = None,
        window_start: Optional[datetime] = None,
        window_end: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """
        Computes aggregate calibration summary for the authenticated user.
        """
        evaluations = await cls._fetch_user_authorized_evaluations(
            db=db,
            user_context=user_context,
            prediction_type_filter=prediction_type_filter,
            window_start=window_start,
            window_end=window_end,
        )

        stats = compute_outcome_statistics(evaluations)
        brier = compute_brier_score(evaluations)
        curve = compute_calibration_curve(evaluations)

        cohort_def = {
            "scope": "USER",
            "user_id": str(user_context.user_id),
            "prediction_type_filter": prediction_type_filter,
            "window_start": window_start.isoformat() if window_start else None,
            "window_end": window_end.isoformat() if window_end else None,
        }

        source_comp_ids = [e["comparison_id"] for e in evaluations]
        source_comp_hashes = [e["comparison_hash"] for e in evaluations]

        agg_hash = compute_aggregate_hash(
            cohort_definition=cohort_def,
            policy_version=CALIBRATION_POLICY_V1,
            source_comparison_ids=source_comp_ids,
            source_comparison_hashes=source_comp_hashes,
        )

        return {
            "calibration_policy_version": CALIBRATION_POLICY_V1,
            "calibration_policy_hash": compute_calibration_policy_hash(CALIBRATION_POLICY_V1),
            "aggregate_hash": agg_hash,
            "cohort_definition": cohort_def,
            "outcome_statistics": stats,
            "brier_score": brier,
            "calibration_curve_summary": {
                "status": curve["status"],
                "status_message": curve["status_message"],
                "total_eligible_samples": curve["total_eligible_samples"],
            },
            "source_comparisons_count": len(evaluations),
            "source_comparison_ids": source_comp_ids,
        }

    @classmethod
    async def get_my_calibration_curve(
        cls,
        db: AsyncSession,
        user_context: UserContext,
        prediction_type_filter: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Retrieves full 5-bin calibration curve details for the authenticated user.
        """
        evaluations = await cls._fetch_user_authorized_evaluations(
            db=db,
            user_context=user_context,
            prediction_type_filter=prediction_type_filter,
        )

        curve = compute_calibration_curve(evaluations)

        cohort_def = {
            "scope": "USER",
            "user_id": str(user_context.user_id),
            "prediction_type_filter": prediction_type_filter,
        }

        source_comp_ids = [e["comparison_id"] for e in evaluations]
        source_comp_hashes = [e["comparison_hash"] for e in evaluations]

        agg_hash = compute_aggregate_hash(
            cohort_definition=cohort_def,
            policy_version=CALIBRATION_POLICY_V1,
            source_comparison_ids=source_comp_ids,
            source_comparison_hashes=source_comp_hashes,
        )

        curve["aggregate_hash"] = agg_hash
        curve["cohort_definition"] = cohort_def
        return curve

    @classmethod
    async def get_my_calibration_history(
        cls,
        db: AsyncSession,
        user_context: UserContext,
        limit: int = 50,
        offset: int = 0,
        prediction_type_filter: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Retrieves paginated longitudinal history of completed evaluations for the user.
        Includes full provenance links back to source sessions, submissions, and comparisons.
        """
        all_evals = await cls._fetch_user_authorized_evaluations(
            db=db,
            user_context=user_context,
            prediction_type_filter=prediction_type_filter,
        )

        total_count = len(all_evals)
        paginated = all_evals[offset : offset + limit]

        return {
            "calibration_policy_version": CALIBRATION_POLICY_V1,
            "total_count": total_count,
            "limit": limit,
            "offset": offset,
            "evaluations": paginated,
        }

    @classmethod
    async def get_team_calibration_summary(
        cls,
        db: AsyncSession,
        team_id: Union[str, uuid.UUID],
        user_context: UserContext,
        prediction_type_filter: Optional[str] = None,
        window_start: Optional[datetime] = None,
        window_end: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """
        Computes aggregate calibration summary for a team.
        Requires authenticated caller to have team membership or authorized admin role.
        """
        evaluations = await cls._fetch_team_authorized_evaluations(
            db=db,
            team_id=team_id,
            user_context=user_context,
            prediction_type_filter=prediction_type_filter,
            window_start=window_start,
            window_end=window_end,
        )

        stats = compute_outcome_statistics(evaluations)
        brier = compute_brier_score(evaluations)
        curve = compute_calibration_curve(evaluations)

        cohort_def = {
            "scope": "TEAM",
            "team_id": str(team_id),
            "prediction_type_filter": prediction_type_filter,
            "window_start": window_start.isoformat() if window_start else None,
            "window_end": window_end.isoformat() if window_end else None,
        }

        source_comp_ids = [e["comparison_id"] for e in evaluations]
        source_comp_hashes = [e["comparison_hash"] for e in evaluations]

        agg_hash = compute_aggregate_hash(
            cohort_definition=cohort_def,
            policy_version=CALIBRATION_POLICY_V1,
            source_comparison_ids=source_comp_ids,
            source_comparison_hashes=source_comp_hashes,
        )

        return {
            "calibration_policy_version": CALIBRATION_POLICY_V1,
            "calibration_policy_hash": compute_calibration_policy_hash(CALIBRATION_POLICY_V1),
            "aggregate_hash": agg_hash,
            "cohort_definition": cohort_def,
            "outcome_statistics": stats,
            "brier_score": brier,
            "calibration_curve_summary": {
                "status": curve["status"],
                "status_message": curve["status_message"],
                "total_eligible_samples": curve["total_eligible_samples"],
            },
            "source_comparisons_count": len(evaluations),
            "source_comparison_ids": source_comp_ids,
        }
