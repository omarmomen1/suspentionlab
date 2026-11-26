"""
backend/api/routes/correlation_routes.py
=========================================
Telemetry Correlation Cockpit & Diagnostic API Routes (Sections 1-5, 8).

Endpoints:
GET  /api/v1/telemetry/correlation-cockpit     → Real-time / Session forward model vs telemetry correlation
POST /api/v1/telemetry/investigate-divergence  → Root-cause investigation of correlation drop
GET  /api/v1/telemetry/channel-detail          → Raw, filtered, model, residual & FFT spectrum
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from suspensionlab.backend.security.auth import require_permission, UserContext
from suspensionlab.backend.security.permissions import Permission
from suspensionlab.backend.services.telemetry_correlation_service import TelemetryCorrelationService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/telemetry", tags=["telemetry-correlation"])


class InvestigateDivergenceRequest(BaseModel):
    current_session: str = Field(..., description="Active session ID, e.g. SESS-FP2-004")
    previous_session: Optional[str] = Field(None, description="Baseline comparison session ID, e.g. SESS-FP1-003")
    parameter_deltas: Optional[Dict[str, Any]] = Field(None, description="Known setup adjustments")


@router.get("/correlation-cockpit")
async def get_correlation_cockpit_endpoint(
    session_id: str = Query("SESS-LIVE-001", description="Telemetry session identifier"),
    model_params_json: Optional[str] = Query(None, description="Optional JSON string of setup parameters"),
    user: UserContext = Depends(require_permission(Permission.VEHICLE_READ)),
):
    """
    Primary interface for: 'How well does our virtual vehicle match the real vehicle?' (Section 1).
    Anti-Tautology: Forward-model output computed from independent ODE calculations.
    """
    params = None
    if model_params_json:
        try:
            params = json.loads(model_params_json)
        except Exception:
            raise HTTPException(status_code=400, detail="model_params_json must be valid JSON.")

    try:
        report = TelemetryCorrelationService.get_correlation_cockpit(
            session_id=session_id,
            model_params=params,
        )
        return report
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Correlation cockpit calculation failed: {exc}")


@router.post("/investigate-divergence")
async def investigate_divergence_endpoint(
    req: InvestigateDivergenceRequest,
    user: UserContext = Depends(require_permission(Permission.VEHICLE_READ)),
):
    """
    Root-Cause Correlation Drop Investigator (Section 4).
    Compares previous vs current sessions, setup, aero balance, tire compliance, and sensor dropouts.
    """
    try:
        report = TelemetryCorrelationService.investigate_correlation_drop(
            current_session_id=req.current_session,
            previous_session_id=req.previous_session,
            parameters_diff=req.parameter_deltas,
        )
        return report
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Divergence investigation failed: {exc}")


@router.get("/channel-detail")
async def get_channel_detail_endpoint(
    channel_key: str = Query("ride_accel", description="Channel key: ride_accel | pitch_angle | roll_angle | tire_load_fl | susp_travel | damper_velocity"),
    sample_rate_hz: float = Query(100.0, ge=10.0, le=1000.0),
    user: UserContext = Depends(require_permission(Permission.VEHICLE_READ)),
):
    """
    Single-channel detailed signal breakdown (Section 5):
    Raw, filtered, independently simulated model signal, residual, FFT frequency spectrum, and events.
    """
    try:
        detail = TelemetryCorrelationService.get_channel_detail(
            channel_key=channel_key,
            sample_rate_hz=sample_rate_hz,
        )
        return detail
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Channel detail extraction failed: {exc}")


# ── Step 2-5 Upgrades: Multi-Model, Events, Session Comparison, and Direct Investigation ──

from typing import List, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from suspensionlab.backend.database.core import get_db_dependency
from suspensionlab.backend.services.engineering_question_service import EngineeringQuestionService
from suspensionlab.physics.telemetry_events import detect_all_vehicle_dynamics_events
from suspensionlab.physics.telemetry_analysis import compare_telemetry_sessions


class CompareModelRequest(BaseModel):
    telemetry_data: Optional[Dict[str, Any]] = Field(None, description="Recorded telemetry channel dictionary")
    model_type: str = Field("quarter_car", description="quarter_car | half_car | full_car | handling | lap_sim | digital_twin")
    model_params: Optional[Dict[str, Any]] = Field(None, description="Optional setup parameter overrides")
    event_window: Optional[Tuple[float, float]] = Field(None, description="Optional [t_start, t_end] window")


class DetectEventsRequest(BaseModel):
    telemetry_data: Dict[str, Any] = Field(..., description="Telemetry channels dictionary or session data")


class CompareSessionsRequest(BaseModel):
    session_a: Dict[str, Any] = Field(..., description="Telemetry data for Lap/Session A")
    session_b: Dict[str, Any] = Field(..., description="Telemetry data for Lap/Session B")
    label_a: str = Field("Lap A", description="Label for Session A")
    label_b: str = Field("Lap B", description="Label for Session B")


class InvestigateEventRequest(BaseModel):
    session_id: str = Field(..., description="Telemetry session identifier")
    vehicle_id: Optional[str] = Field("CAR-2026-07", description="Vehicle identifier")
    setup_id: Optional[str] = Field("SETUP-NOMINAL", description="Active setup configuration")
    event_type: str = Field(..., description="Anomaly event category e.g. DAMPER_SPIKE, WHEEL_HOP")
    severity: str = Field("WARNING", description="CRITICAL | WARNING | INFO")
    start_time_s: float = Field(..., description="Event start timestamp [s]")
    end_time_s: float = Field(..., description="Event end timestamp [s]")
    channel_name: str = Field(..., description="Primary channel associated with anomaly")
    evidence: Optional[Dict[str, Any]] = Field(None, description="Physical metrics, peak values, FFT info")
    notes: Optional[str] = Field(None, description="Optional engineer remarks")


class InvestigateResidualRequest(BaseModel):
    session_id: str = Field(..., description="Telemetry session identifier")
    vehicle_id: Optional[str] = Field("CAR-2026-07", description="Vehicle identifier")
    setup_id: Optional[str] = Field("SETUP-NOMINAL", description="Active setup configuration")
    channel_key: str = Field(..., description="Discrepant channel name")
    model_type: str = Field("quarter_car", description="Model compared against")
    discrepancy_magnitude: float = Field(..., description="RMSE or peak error magnitude")
    discrepancy_unit: str = Field("-", description="Physical unit of error")
    systematic_bias: Optional[Dict[str, Any]] = Field(None, description="Bias offset and diagnosis")
    suggested_params: Optional[List[str]] = Field(None, description="Candidate parameters for identification")
    notes: Optional[str] = Field(None, description="Optional engineer remarks")


@router.post("/compare-model")
async def compare_model_endpoint(
    req: CompareModelRequest,
    user: UserContext = Depends(require_permission(Permission.VEHICLE_READ)),
):
    """
    Multi-Model Comparison Engine (Finding 88-89 & Cockpit Section 4).
    Simulates selected forward model and aligns against measured telemetry with
    strict anti-tautology and epistemic state classifications.
    """
    try:
        report = TelemetryCorrelationService.compare_measured_vs_model(
            telemetry_data=req.telemetry_data,
            model_type=req.model_type,
            model_params=req.model_params,
            event_window=req.event_window,
        )
        return report
    except Exception as exc:
        logger.error("Compare model failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"Model comparison calculation failed: {exc}")


@router.post("/events")
async def detect_events_endpoint(
    req: DetectEventsRequest,
    user: UserContext = Depends(require_permission(Permission.VEHICLE_READ)),
):
    """
    Deterministic Vehicle Dynamics Anomaly & Event Detection (11 categories).
    Detects braking onset, corner entry, apex, wheel-hop, damper saturation, and yaw deviations.
    """
    try:
        events = detect_all_vehicle_dynamics_events(req.telemetry_data)

        # Wave 5A: return the FULL sampled (ay, ax) point cloud for the G-G
        # friction-circle diagram, decimated to at most 2000 points, plus
        # honest statistics computed from the uploaded channels themselves.
        # No values are hardcoded or fabricated; if the channels are absent
        # the fields are empty/null.
        import numpy as np

        def _channel(*names):
            for name in names:
                for cand in (name, name.lower(), name.upper()):
                    arr = req.telemetry_data.get(cand)
                    if arr is not None and len(arr) > 0:
                        return np.asarray(arr, dtype=float)
            return None

        lat = _channel("lat_g", "g_lat", "ay", "latacc", "lateral_g")
        lon = _channel("long_g", "g_lon", "ax", "inlineacc", "longitudinal_g")
        gg_points = {"lat_g": [], "long_g": []}
        gg_stats = {"max_resultant_g": None, "peak_lat_g": None, "peak_long_g": None, "sample_count": 0}
        if lat is not None and lon is not None:
            n = min(len(lat), len(lon))
            lat, lon = lat[:n], lon[:n]
            finite = np.isfinite(lat) & np.isfinite(lon)
            lat, lon = lat[finite], lon[finite]
            MAX_PTS = 2000
            stride = max(1, len(lat) // MAX_PTS)
            gg_points = {
                "lat_g": [round(float(v), 4) for v in lat[::stride]],
                "long_g": [round(float(v), 4) for v in lon[::stride]],
            }
            resultant = np.sqrt(lat ** 2 + lon ** 2)
            gg_stats = {
                "max_resultant_g": round(float(np.max(resultant)), 3) if len(resultant) else None,
                "peak_lat_g": round(float(lat[np.argmax(np.abs(lat))]), 3) if len(lat) else None,
                "peak_long_g": round(float(lon[np.argmax(np.abs(lon))]), 3) if len(lon) else None,
                "sample_count": int(len(lat)),
            }

        return {
            "events_count": len(events),
            "events": [e.to_dict() for e in events],
            "gg_points": gg_points,
            "gg_stats": gg_stats,
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Event detection failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"Vehicle dynamics event detection failed: {exc}")


@router.post("/compare-sessions")
async def compare_sessions_endpoint(
    req: CompareSessionsRequest,
    user: UserContext = Depends(require_permission(Permission.VEHICLE_READ)),
):
    """
    Lap A vs Lap B / Setup 1 vs Setup 2 Session Comparison.
    Computes WHAT changed, WHERE it changed, WHEN it changed, and physics-derived explanations.
    """
    try:
        report = compare_telemetry_sessions(
            session_a=req.session_a,
            session_b=req.session_b,
            label_a=req.label_a,
            label_b=req.label_b,
        )
        return report.to_dict()
    except Exception as exc:
        logger.error("Session comparison failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"Session comparison failed: {exc}")


@router.post("/investigate-event")
async def investigate_event_endpoint(
    req: InvestigateEventRequest,
    user: UserContext = Depends(require_permission(Permission.SETUP_CREATE)),
    db: AsyncSession = Depends(get_db_dependency),
):
    """
    Directly create an EngineeringQuestion from a detected telemetry event.
    Enforces the scientific chain: MEASURED DATA -> EVENT -> EVIDENCE -> QUESTION -> EXPERIMENT.
    """
    try:
        from suspensionlab.backend.services.trial_service import TrialService
        await TrialService.assert_trial_access(db, user, action="decision")

        title = f"{req.event_type.replace('_', ' ').title()} on {req.channel_name} ({req.start_time_s:.2f}s - {req.end_time_s:.2f}s)"
        question_text = (
            f"Deterministic vehicle dynamics detector identified {req.event_type} on channel {req.channel_name} "
            f"during session {req.session_id} between t={req.start_time_s:.2f}s and t={req.end_time_s:.2f}s. "
            f"Evidence indicates potential suspension envelope saturation or compliance limit. "
            f"What mechanical or aerodynamic adjustments are required to mitigate this anomaly?"
        )
        if req.notes:
            question_text += f"\nEngineer notes: {req.notes}"

        context = {
            "source": "TELEMETRY_ANOMALY",
            "session_id": req.session_id,
            "channel_name": req.channel_name,
            "event_type": req.event_type,
            "time_window": [req.start_time_s, req.end_time_s],
            "evidence": req.evidence or {},
        }

        created = await EngineeringQuestionService.create_question(
            db=db,
            user_id=user.user_id,
            user_name=user.name or user.email,
            title=title,
            question_text=question_text,
            vehicle_id=req.vehicle_id or "Formula 1 2026 Spec (CAR 07)",
            setup_id=req.setup_id or "Spa-Francorchamps Aero Rev 28",
            severity=req.severity,
            source="TELEMETRY_ANOMALY",
            organization_id=getattr(user, "organization_id", None),
            team_id=getattr(user, "team_id", None),
            context=context,
            linked_telemetry_ids=[req.session_id],
            linked_evidence=[req.evidence] if req.evidence else [],
        )

        q_id = created.get("question_id") or created.get("id")
        return {
            "question_id": q_id,
            "id": created.get("id"),
            "redirect_url": f"/investigate?id={q_id}",
            "question": created,
        }
    except Exception as exc:
        logger.error("Investigate event failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"Failed to create engineering question from event: {exc}")


@router.post("/investigate-residual")
async def investigate_residual_endpoint(
    req: InvestigateResidualRequest,
    user: UserContext = Depends(require_permission(Permission.SETUP_CREATE)),
    db: AsyncSession = Depends(get_db_dependency),
):
    """
    Directly create an EngineeringQuestion from a model residual discrepancy.
    Pre-populates channel, error magnitude, bias diagnosis, and candidate parameters.
    """
    try:
        from suspensionlab.backend.services.trial_service import TrialService
        await TrialService.assert_trial_access(db, user, action="decision")

        title = f"Model Discrepancy: {req.channel_key} ({req.discrepancy_magnitude:.2f} {req.discrepancy_unit} error vs {req.model_type})"
        params_str = ", ".join(req.suggested_params) if req.suggested_params else "damping/spring parameters"
        question_text = (
            f"Forward {req.model_type} simulation exhibits a discrepancy of {req.discrepancy_magnitude:.2f} {req.discrepancy_unit} "
            f"on channel {req.channel_key} in session {req.session_id}. "
            f"Residual analysis suggests investigating parameter calibration for: {params_str}. "
            f"How should the vehicle setup or model parameters be adjusted to resolve this divergence?"
        )
        if req.notes:
            question_text += f"\nEngineer notes: {req.notes}"

        context = {
            "source": "SIMULATION_DISCREPANCY",
            "session_id": req.session_id,
            "channel_key": req.channel_key,
            "model_type": req.model_type,
            "discrepancy_magnitude": req.discrepancy_magnitude,
            "discrepancy_unit": req.discrepancy_unit,
            "systematic_bias": req.systematic_bias or {},
            "suggested_params": req.suggested_params or [],
        }

        created = await EngineeringQuestionService.create_question(
            db=db,
            user_id=user.user_id,
            user_name=user.name or user.email,
            title=title,
            question_text=question_text,
            vehicle_id=req.vehicle_id or "Formula 1 2026 Spec (CAR 07)",
            setup_id=req.setup_id or "Spa-Francorchamps Aero Rev 28",
            severity="WARNING",
            source="SIMULATION_DISCREPANCY",
            organization_id=getattr(user, "organization_id", None),
            team_id=getattr(user, "team_id", None),
            context=context,
            linked_telemetry_ids=[req.session_id],
            linked_evidence=[context],
        )

        q_id = created.get("question_id") or created.get("id")
        return {
            "question_id": q_id,
            "id": created.get("id"),
            "redirect_url": f"/investigate?id={q_id}",
            "question": created,
        }
    except Exception as exc:
        logger.error("Investigate residual failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"Failed to create engineering question from residual: {exc}")

