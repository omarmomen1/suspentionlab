"""
backend/api/routes/blind_calibration_routes.py
==============================================
SuspensionLab PRO — Phase 5.4 Engineering Calibration API Routes.

Exposes authenticated, tenant-isolated calibration and longitudinal track record endpoints:
- GET /api/v1/blind-calibration/me: User calibration summary & brier score
- GET /api/v1/blind-calibration/me/summary: User calibration summary
- GET /api/v1/blind-calibration/me/history: Paginated longitudinal evaluation records
- GET /api/v1/blind-calibration/me/curve: 5-bin calibration reliability curve
- GET /api/v1/blind-calibration/team/{team_id}: Team-scoped aggregate calibration summary

Strictly NO global leaderboard, NO engineer rankings, and NO rationale scoring endpoints.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from suspensionlab.backend.database.core import get_db_dependency
from suspensionlab.backend.security.auth import verify_api_key, UserContext
from suspensionlab.backend.services.blind_calibration_service import (
    BlindCalibrationService,
    UnauthorizedTeamAccessError,
    TeamNotFoundError,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/blind-calibration", tags=["blind-calibration"])


# ── SCHEMAS ───────────────────────────────────────────────────────────────────

class OutcomeStatisticsDTO(BaseModel):
    total_completed_evaluations: int
    comparable_evaluations: int
    uncomparable_evaluations: int
    metrics_only_evaluations: int
    binary_evaluated_count: int
    correct_outcomes: int
    incorrect_outcomes: int
    observed_accuracy: Optional[float] = None
    observed_accuracy_ci: Optional[List[float]] = None
    comparison_coverage: Optional[float] = None
    excluded_counts: Dict[str, int]
    cohort_breakdown: Dict[str, Any]


class BrierScoreDTO(BaseModel):
    brier_score: Optional[float] = None
    eligible_sample_size: int
    status: str
    excluded_count: int
    excluded_reasons: Dict[str, int] = Field(default_factory=dict)
    interpretation: str


class CalibrationBinDTO(BaseModel):
    bin_index: int
    range: List[float]
    label: str
    sample_count: int
    positive_count: int
    mean_forecast_probability: Optional[float] = None
    observed_frequency: Optional[float] = None
    uncertainty_interval: Optional[List[float]] = None
    is_empty: bool


class CalibrationCurveResponse(BaseModel):
    status: str
    status_message: str
    total_eligible_samples: int
    excluded_observations_count: int
    bins: List[CalibrationBinDTO]
    policy_version: str
    binning_method: str
    uncertainty_method: str
    aggregate_hash: Optional[str] = None
    cohort_definition: Optional[Dict[str, Any]] = None


class CalibrationSummaryResponse(BaseModel):
    calibration_policy_version: str
    calibration_policy_hash: str
    aggregate_hash: str
    cohort_definition: Dict[str, Any]
    outcome_statistics: OutcomeStatisticsDTO
    brier_score: BrierScoreDTO
    calibration_curve_summary: Dict[str, Any]
    source_comparisons_count: int
    source_comparison_ids: List[str]


class EvaluationHistoryItemDTO(BaseModel):
    comparison_id: str
    comparison_hash: str
    comparison_policy_version: str
    comparison_type: str
    verdict: str
    interpretation: str
    comparison_metrics: Dict[str, Any]
    computed_at: Optional[str] = None
    session_id: str
    session_name: str
    session_status: str
    root_entity_type: str
    root_entity_id: str
    revealed_at: Optional[str] = None
    submission_id: str
    submission_hash: str
    submitted_at: Optional[str] = None
    prediction_payload: Dict[str, Any]
    outcome_identity: Dict[str, Any]
    eligibility: Dict[str, Any]


class CalibrationHistoryResponse(BaseModel):
    calibration_policy_version: str
    total_count: int
    limit: int
    offset: int
    evaluations: List[EvaluationHistoryItemDTO]


# ── HELPERS ───────────────────────────────────────────────────────────────────

def _parse_iso_datetime(dt_str: Optional[str]) -> Optional[datetime]:
    if not dt_str:
        return None
    try:
        return datetime.fromisoformat(dt_str)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid ISO datetime format '{dt_str}': {e}",
        )


# ── ENDPOINTS ─────────────────────────────────────────────────────────────────

@router.get("/me", response_model=CalibrationSummaryResponse)
@router.get("/me/summary", response_model=CalibrationSummaryResponse)
async def get_my_summary(
    prediction_type: Optional[str] = Query(None, description="Optional prediction type filter"),
    window_start: Optional[str] = Query(None, description="ISO window start datetime"),
    window_end: Optional[str] = Query(None, description="ISO window end datetime"),
    user_context: UserContext = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    """
    Retrieves the caller's longitudinal outcome statistics, Brier score, and curve summary.
    """
    w_start = _parse_iso_datetime(window_start)
    w_end = _parse_iso_datetime(window_end)
    try:
        return await BlindCalibrationService.get_my_calibration_summary(
            db=db,
            user_context=user_context,
            prediction_type_filter=prediction_type,
            window_start=w_start,
            window_end=w_end,
        )
    except Exception as e:
        logger.error("Failed to fetch user calibration summary: %s", e)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/me/curve", response_model=CalibrationCurveResponse)
async def get_my_curve(
    prediction_type: Optional[str] = Query(None, description="Optional prediction type filter"),
    user_context: UserContext = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    """
    Retrieves full 5-bin calibration curve details with Wilson score confidence intervals.
    """
    try:
        return await BlindCalibrationService.get_my_calibration_curve(
            db=db,
            user_context=user_context,
            prediction_type_filter=prediction_type,
        )
    except Exception as e:
        logger.error("Failed to fetch user calibration curve: %s", e)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/me/history", response_model=CalibrationHistoryResponse)
async def get_my_history(
    limit: int = Query(50, ge=1, le=200, description="Page limit"),
    offset: int = Query(0, ge=0, description="Page offset"),
    prediction_type: Optional[str] = Query(None, description="Optional prediction type filter"),
    user_context: UserContext = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    """
    Retrieves paginated longitudinal evaluations with full provenance backlinks.
    """
    try:
        return await BlindCalibrationService.get_my_calibration_history(
            db=db,
            user_context=user_context,
            limit=limit,
            offset=offset,
            prediction_type_filter=prediction_type,
        )
    except Exception as e:
        logger.error("Failed to fetch user calibration history: %s", e)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/team/{team_id}", response_model=CalibrationSummaryResponse)
async def get_team_summary(
    team_id: str,
    prediction_type: Optional[str] = Query(None, description="Optional prediction type filter"),
    window_start: Optional[str] = Query(None, description="ISO window start datetime"),
    window_end: Optional[str] = Query(None, description="ISO window end datetime"),
    user_context: UserContext = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    """
    Retrieves team-scoped calibration summary. Requires team membership or administrative role.
    """
    w_start = _parse_iso_datetime(window_start)
    w_end = _parse_iso_datetime(window_end)
    try:
        return await BlindCalibrationService.get_team_calibration_summary(
            db=db,
            team_id=team_id,
            user_context=user_context,
            prediction_type_filter=prediction_type,
            window_start=w_start,
            window_end=w_end,
        )
    except UnauthorizedTeamAccessError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except TeamNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error("Failed to fetch team calibration summary: %s", e)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
