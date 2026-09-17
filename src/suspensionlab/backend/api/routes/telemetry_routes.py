import json
import asyncio
import logging
import os
import time
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, UploadFile, File, Form, HTTPException, Depends, Query, status
from fastapi.responses import JSONResponse
from typing import Dict, Any, Optional
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from suspensionlab.backend.database.core import get_db_dependency

from suspensionlab.physics.magic_formula import TireCoeffs
from suspensionlab.physics.lap_sim import LapSimVehicle
from suspensionlab.backend.security.auth import verify_api_key, require_permission, UserContext
from suspensionlab.backend.security.permissions import Permission
from suspensionlab.backend.security.rate_limit import RateLimiter
from suspensionlab.backend.security.jwt_utils import decode_access_token
from suspensionlab.telemetry.protocol import (
    SLTPFrame,
    ChannelId,
    ChannelSample,
    QualityCode,
    GripStatusCode,
    MAGIC_HEADER,
)
from suspensionlab.telemetry.gateway import TelemetryIngestionGateway
from suspensionlab.telemetry.hub import (
    TelemetryHub,
    TelemetrySubscriber,
    TenantIsolationError,
    global_telemetry_hub,
)
from suspensionlab.telemetry.replay import (
    TelemetryReplayEngine,
    global_replay_engine,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/telemetry", tags=["Telemetry"])
gateway = TelemetryIngestionGateway()


@router.websocket("/live")
async def websocket_telemetry_endpoint(
    websocket: WebSocket,
    token: Optional[str] = Query(None, description="Bearer JWT for authentication"),
    session_id: str = Query("sess-live", description="Telemetry session identifier"),
    format: str = Query("binary", description="Format: binary (SLTP v1) or json"),
):
    """
    Live Telemetry Monitor WebSocket Endpoint.
    Streams high-frequency (>= 100 Hz) binary SLTP v1 telemetry frames
    with tenant isolation, sequence tracking, heartbeat, and backpressure.
    """
    # 1. Resolve Authentication Token
    jwt_token = token
    if not jwt_token:
        sec_protocol = websocket.headers.get("sec-websocket-protocol")
        if sec_protocol and "bearer" in sec_protocol.lower():
            for p in sec_protocol.split(","):
                p = p.strip()
                if not p.lower().startswith("bearer") and len(p) > 20:
                    jwt_token = p
                    break
        if not jwt_token:
            jwt_token = websocket.cookies.get("sl_token")

    user_data = None
    if jwt_token:
        user_data = decode_access_token(jwt_token)


    if not user_data:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid or missing authentication token.")
        return

    user_id = str(user_data.get("sub", "anon"))
    user_org_id = str(user_data.get("organization_id") or user_id)
    is_admin = bool(user_data.get("is_admin", False))
    binary_mode = (format.lower() == "binary")

    # 2. Authorize & Subscribe with Tenant Isolation (Step 4 & Step 7)
    try:
        subscriber = await global_telemetry_hub.subscribe(
            websocket=websocket,
            user_id=user_id,
            organization_id=user_org_id,
            session_id=session_id,
            is_admin=is_admin,
            binary_mode=binary_mode,
        )
    except TenantIsolationError as tie:
        logger.warning("Rejecting cross-tenant telemetry stream subscription: %s", tie)
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason=str(tie))
        return

    await websocket.accept()

    # 3. Concurrent Send & Receive Loops with Backpressure and Heartbeat
    async def sender_loop():
        try:
            while subscriber.is_alive:
                payload = await subscriber.queue.get()
                if binary_mode and isinstance(payload, (bytes, bytearray)):
                    await websocket.send_bytes(payload)
                elif isinstance(payload, dict):
                    await websocket.send_json(payload)
                elif isinstance(payload, str):
                    await websocket.send_text(payload)
                subscriber.frames_sent += 1
        except (WebSocketDisconnect, asyncio.CancelledError):
            pass
        except Exception as e:
            logger.debug("Telemetry sender exception: %s", e)

    async def receiver_loop():
        try:
            while subscriber.is_alive:
                msg = await websocket.receive()
                if msg.get("type") == "websocket.disconnect":
                    break

                if "text" in msg and msg["text"]:
                    try:
                        data = json.loads(msg["text"])
                    except Exception:
                        continue

                    if data.get("type") == "ping":
                        subscriber.last_heartbeat = time.time()
                        await websocket.send_json({"type": "pong", "ts": time.time()})
                    elif "speed_ms" in data or "channels" in data:
                        processed = gateway.validate_and_process(
                            data, org_id=user_org_id, session_id=session_id
                        )
                        await global_telemetry_hub.broadcast_frame(processed)

                elif "bytes" in msg and msg["bytes"]:
                    raw_bytes = msg["bytes"]
                    if raw_bytes.startswith(MAGIC_HEADER):
                        try:
                            frame = SLTPFrame.unpack(raw_bytes)
                            processed = gateway.validate_and_process(
                                frame, org_id=user_org_id, session_id=session_id
                            )
                            await global_telemetry_hub.broadcast_frame(processed)
                        except Exception as exc:
                            logger.debug("Failed unpacking binary frame from DAQ client: %s", exc)
        except (WebSocketDisconnect, asyncio.CancelledError):
            pass
        except Exception as e:
            logger.debug("Telemetry receiver exception: %s", e)

    sender_task = asyncio.create_task(sender_loop())
    receiver_task = asyncio.create_task(receiver_loop())

    try:
        done, pending = await asyncio.wait(
            [sender_task, receiver_task],
            return_when=asyncio.FIRST_COMPLETED,
        )
        for t in pending:
            t.cancel()
    finally:
        await global_telemetry_hub.unsubscribe(subscriber)


@router.post("/ingest")
async def ingest_telemetry_packet(
    frame_data: Dict[str, Any],
    user: UserContext = Depends(verify_api_key),
):
    """
    Direct DAQ Ingestion Gateway Endpoint.
    Ingests raw sensor frame, validates physical limits, attaches Digital Twin state,
    and broadcasts to authorized subscribers.
    """
    org_id = user.organization_id or user.user_id
    session_id = str(frame_data.get("session_id", "sess-live"))
    processed = gateway.validate_and_process(frame_data, org_id=org_id, session_id=session_id)
    sent = await global_telemetry_hub.broadcast_frame(processed)
    return {
        "status": "ingested",
        "seq": processed.sequence_number,
        "subscribers_notified": sent,
        "twin": {
            "theoretical_max_lat_g": processed.twin.theoretical_max_lat_g,
            "actual_lat_g": processed.twin.actual_lat_g,
            "divergence_pct": processed.twin.divergence_pct,
            "grip_status": processed.twin.grip_status.name,
        } if processed.twin else None,
    }


class StartReplayRequest(BaseModel):
    dataset: Optional[str] = None
    dataset_path: Optional[str] = None
    session_id: Optional[str] = None
    rate_hz: Optional[float] = None


@router.post("/replay/start")
async def start_telemetry_replay(
    req: Optional[StartReplayRequest] = None,
    dataset: Optional[str] = None,
    session_id: str = "sess-live",
    rate_hz: float = 100.0,
    user: UserContext = Depends(verify_api_key),
):
    """
    Start streaming recorded MoTeC/AiM telemetry session at calibrated 100 Hz.
    """
    org_id = user.organization_id or user.user_id
    effective_ds = (req.dataset or req.dataset_path) if req else dataset
    effective_ds = effective_ds or dataset or "sample_data/motec_spa_session.csv"
    if req and req.session_id:
        session_id = req.session_id
    if req and req.rate_hz is not None:
        rate_hz = req.rate_hz

    clean_ds = effective_ds.replace("\\", "/")
    if ".." in clean_ds or clean_ds.startswith("/") or (len(clean_ds) > 1 and clean_ds[1] == ":"):
        raise HTTPException(status_code=400, detail="Invalid dataset path: Path traversal detected.")

    csv_file = effective_ds
    if not os.path.isabs(csv_file):
        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../../.."))
        candidate = os.path.join(repo_root, csv_file)
        if os.path.exists(candidate):
            csv_file = candidate

    st = await global_replay_engine.start_replay(
        csv_path=csv_file,
        session_id=session_id,
        org_id=org_id,
        rate_hz=rate_hz,
        loop_playback=True,
    )
    return {
        "status": "started",
        "session_id": session_id,
        "target_rate_hz": rate_hz,
        "dataset": os.path.basename(csv_file),
    }


@router.post("/replay/stop")
async def stop_telemetry_replay(
    session_id: str = "sess-live",
    user: UserContext = Depends(verify_api_key),
):
    """Stop active telemetry replay."""
    await global_replay_engine.stop_replay(session_id)
    return {"status": "stopped", "session_id": session_id}


@router.get("/replay/status")
async def get_replay_status(session_id: str = "sess-live"):
    """Get status of active telemetry replay."""
    st = global_replay_engine.get_status(session_id)
    return {
        "is_running": st.is_running,
        "session_id": st.session_id,
        "current_index": st.current_index,
        "total_samples": st.total_samples,
        "target_rate_hz": st.target_rate_hz,
        "measured_rate_hz": st.measured_rate_hz,
        "elapsed_seconds": st.elapsed_seconds,
        "error": st.error,
    }


@router.get("/stats")
async def get_telemetry_stats(session_id: str = "sess-live"):
    """Get streaming hub and ingestion gateway statistics."""
    return {
        "hub": global_telemetry_hub.get_stats(),
        "gateway": gateway.get_stats(session_id),
    }



@router.post(
    "/analyse",
    dependencies=[
        Depends(require_permission(Permission.TELEMETRY_READ)),
        Depends(RateLimiter("rate_limit_simulate")),
    ],
)
async def analyse_telemetry(
    file: UploadFile = File(..., description="Telemetry CSV file (AiM, MoTeC, generic)"),
    model_params: Optional[str] = Form(None, description="JSON string of quarter-car model parameters"),
):
    """
    Analyse an uploaded telemetry CSV session.

    Pipeline:
        Step 1 — Identify channels (40+ alias map)
        Step 2 — Validate data quality (dropouts, dead sensors, rate mismatch)
        Step 3 — Segment lap (straights, braking zones, corners)
        Step 4 — Compare simulation vs. telemetry (if model_params provided)

    Returns structured JSON with channel map, QA metrics, lap segments,
    and simulation comparison table.
    """
    # Validate file type
    if file.content_type not in ("text/csv", "text/plain", "application/octet-stream") and \
       not (file.filename or "").lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files are accepted.")

    # File size limit: 50 MB
    MAX_SIZE = 50 * 1024 * 1024
    content_bytes = await file.read(MAX_SIZE + 1)
    if len(content_bytes) > MAX_SIZE:
        raise HTTPException(status_code=413, detail="File too large. Maximum 50 MB.")

    try:
        csv_content = content_bytes.decode("utf-8", errors="replace")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Cannot decode file: {exc}")

    # Parse optional model params
    params_dict: dict | None = None
    if model_params:
        try:
            params_dict = json.loads(model_params)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="model_params must be valid JSON.")

    # Run analysis pipeline
    try:
        from suspensionlab.physics.telemetry_analysis import analyse_session
        result = analyse_session(csv_content, params_dict)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Analysis failed: {exc}")

    # Enforce Scientific Integrity Gate: Blocked or corrupt data must NOT return HTTP 200
    if result.is_blocked or (result.health and not result.health.can_proceed):
        raise HTTPException(
            status_code=422,
            detail={
                "error": "Telemetry data rejected by health and scientific integrity checks",
                "pipeline_status": result.pipeline_status,
                "blocking_reasons": result.health.blocking_reasons if result.health else ["Data quality validation failed"],
                "warnings": result.health.warnings if result.health else [],
                "missing_data_summary": result.health.missing_data_summary.to_dict() if (result.health and hasattr(result.health, "missing_data_summary")) else {},
                "stage_audit": [s.to_dict() for s in result.health.stage_audit] if (result.health and hasattr(result.health, "stage_audit")) else [],
            }
        )

    # Serialise result to JSON-safe dict
    qa = result.qa
    qa_dict = None
    if qa:
        qa_dict = {
            "n_samples":         qa.n_samples,
            "duration_s":        qa.duration_s,
            "sample_rate_hz":    qa.sample_rate_hz,
            "channels_found":    qa.channels_found,
            "channels_missing":  qa.channels_missing,
            "dead_channels":     qa.dead_channels,
            "dropout_intervals": qa.dropout_intervals,
            "rate_mismatch_pct": qa.rate_mismatch_pct,
            "total_warnings":    qa.total_warnings,
        }

    segments_list = [
        {
            "label":       s.label,
            "t_start":     s.t_start,
            "t_end":       s.t_end,
            "duration_s":  round(s.t_end - s.t_start, 3),
            "peak_lat_g":  s.peak_lat_g,
            "peak_long_g": s.peak_long_g,
            "peak_speed":  s.peak_speed,
        }
        for s in result.segments
    ]

    comparison_list = [
        {
            "channel":     row.channel,
            "description": row.description,
            "unit":        row.unit,
            "sim_value":   row.sim_value,
            "telem_value": row.telem_value,
            "error_abs":   row.error_abs,
            "error_pct":   row.error_pct,
            "status":      row.status,
        }
        for row in result.comparison
    ]

    # Truncate channel data arrays for response (max 2000 points)
    channels_preview: dict = {}
    for key, arr in result.channels.items():
        if isinstance(arr, list) and len(arr) > 0:
            step = max(1, len(arr) // 2000)
            channels_preview[key] = arr[::step]

    return JSONResponse(content={
        "summary": {
            "n_samples":      result.n_samples,
            "duration_s":     result.duration_s,
            "sample_rate_hz": result.sample_rate_hz,
            "mean_speed_ms":  result.mean_speed_ms,
            "peak_lat_g":     result.peak_lat_g,
            "peak_long_g":    result.peak_long_g,
            "peak_vert_g":    result.peak_vert_g,
        },
        "pipeline_status": result.pipeline_status,
        "channel_map":  result.channel_info,
        "qa":           qa_dict,
        "health":       result.health.to_dict() if result.health else None,
        "missing_data_summary": result.health.missing_data_summary.to_dict() if (result.health and hasattr(result.health, "missing_data_summary")) else {},
        "stage_audit":  [s.to_dict() for s in result.health.stage_audit] if (result.health and hasattr(result.health, "stage_audit")) else [],
        "segments":     segments_list,
        "comparison":   comparison_list,
        "model_note":   result.model_note,
        "channels_preview": channels_preview,
    })


@router.post(
    "/dataset",
    dependencies=[
        Depends(require_permission(Permission.TELEMETRY_UPLOAD)),
        Depends(RateLimiter("rate_limit_simulate")),
    ],
)
async def create_telemetry_dataset_endpoint(
    file: UploadFile = File(..., description="Telemetry CSV (MoTeC, AiM, Cosworth, Bosch, CAN, CSV)"),
    source: str = Form("CSV", description="MoTeC | AiM | Cosworth/Pi | Bosch | CAN | CSV"),
    vehicle: str = Form("CAR-01", description="Vehicle ID"),
    setup: str = Form("BASE", description="Setup identifier"),
    track: str = Form("Silverstone", description="Track name"),
    session: str = Form("FP1", description="Session name"),
    driver: str = Form("Driver 1", description="Driver name"),
    user: UserContext = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    """
    Step 1 & Step 3: Ingest telemetry file into canonical TelemetryDataset container.
    Preserves all raw samples and creates uniform canonical grid.
    """
    content_bytes = await file.read(50 * 1024 * 1024)

    # ── Trial Governance: Enforce 7-day expiration & storage quota ──
    from suspensionlab.backend.services.trial_service import TrialService
    trial = await TrialService.assert_trial_access(
        db, user, action="telemetry_upload", delta=len(content_bytes)
    )

    csv_content = content_bytes.decode("utf-8", errors="replace")

    from suspensionlab.physics.telemetry_dataset import TelemetryDataset, TelemetrySource
    from suspensionlab.physics.telemetry_health import assess_telemetry_health, TelemetryPipelineStatus

    src_enum = TelemetrySource.CSV
    for s in TelemetrySource:
        if s.value.lower() in source.lower():
            src_enum = s
            break

    ds = TelemetryDataset.from_csv_string(
        csv_content=csv_content,
        source=src_enum,
        vehicle=vehicle,
        setup=setup,
        track=track,
        session=session,
        driver=driver,
    )

    telem_dict = {k: ds.get_channel(k) for k in ds.channels}
    health = assess_telemetry_health(telem_dict, time_channel=ds.timestamps)
    if not health.can_proceed or health.pipeline_status == TelemetryPipelineStatus.REJECTED:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "Telemetry dataset ingestion rejected due to integrity/corruption violations",
                "pipeline_status": health.pipeline_status.value,
                "blocking_reasons": health.blocking_reasons,
                "missing_data_summary": health.missing_data_summary.to_dict(),
            }
        )

    if trial:
        await TrialService.record_trial_usage(db, user, action="telemetry_upload", delta=len(content_bytes))

    res_dict = ds.to_dict()
    res_dict["health"] = health.to_dict()
    res_dict["pipeline_status"] = health.pipeline_status.value
    return res_dict


@router.post(
    "/calibrate",
    dependencies=[
        Depends(require_permission(Permission.CALIBRATION_RUN)),
        Depends(RateLimiter("rate_limit_simulate")),
    ],
)
async def calibrate_forward_model_endpoint(
    file: UploadFile = File(..., description="Telemetry CSV file"),
    nominal_params: str = Form(..., description="JSON string of nominal parameters (m_s, k_s, c, k_t, MR)"),
    evidence_sessions: int = Form(1, description="Number of evidence sessions"),
):
    """
    Step 8, Step 9, Step 10: Multi-parameter forward ODE calibration with train/holdout validation.
    """
    content_bytes = await file.read(50 * 1024 * 1024)
    csv_content = content_bytes.decode("utf-8", errors="replace")

    try:
        nom_dict = json.loads(nominal_params)
    except Exception:
        raise HTTPException(status_code=400, detail="nominal_params must be valid JSON")

    from suspensionlab.physics.telemetry_dataset import TelemetryDataset
    from suspensionlab.physics.parameter_identification import identify_suspension_parameters
    from suspensionlab.physics.telemetry_health import assess_telemetry_health, TelemetryPipelineStatus

    ds = TelemetryDataset.from_csv_string(csv_content)
    telem_dict = {k: ds.get_channel(k) for k in ds.channels}
    health = assess_telemetry_health(telem_dict, time_channel=ds.timestamps)

    if not health.can_proceed or health.pipeline_status == TelemetryPipelineStatus.REJECTED:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "Cannot calibrate model: telemetry data failed integrity checks",
                "pipeline_status": health.pipeline_status.value,
                "blocking_reasons": health.blocking_reasons,
                "missing_data_summary": health.missing_data_summary.to_dict(),
            }
        )

    if not health.calibration_eligible:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "Telemetry data ineligible for forward model calibration (missing data exceeds 5.0% threshold or unphysical noise)",
                "pipeline_status": health.pipeline_status.value,
                "missing_data_summary": health.missing_data_summary.to_dict(),
            }
        )

    try:
        report = identify_suspension_parameters(
            target_telemetry=ds,
            nominal_params=nom_dict,
            evidence_sessions=evidence_sessions,
        )
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Parameter calibration failed: {exc}")

    return report.to_dict()


@router.post(
    "/post-track-delta",
    dependencies=[
        Depends(verify_api_key),
        Depends(RateLimiter("rate_limit_simulate")),
    ],
)
async def post_track_delta_analysis_endpoint(
    file: UploadFile = File(..., description="Measured telemetry CSV from on-track session"),
    proposal_json: str = Form(..., description="JSON string of SetupProposal artifact"),
):
    """
    Step 12: Closed-loop post-track delta comparison between predicted setup gains and measured response.
    """
    content_bytes = await file.read(50 * 1024 * 1024)
    csv_content = content_bytes.decode("utf-8", errors="replace")

    try:
        prop_data = json.loads(proposal_json)
    except Exception:
        raise HTTPException(status_code=400, detail="proposal_json must be valid JSON")

    from suspensionlab.physics.telemetry_dataset import TelemetryDataset
    from suspensionlab.physics.post_track_loop import evaluate_post_track_proposal

    ds = TelemetryDataset.from_csv_string(csv_content)
    report = evaluate_post_track_proposal(proposal_data=prop_data, telemetry_dataset=ds)
    return report.to_dict()


from pydantic import BaseModel, Field
from typing import List

class DecimateRequest(BaseModel):
    timestamps: List[float] = Field(..., description="Array of time coordinates [s]")
    values: List[float] = Field(..., description="Array of channel values")
    channel_name: str = Field("damper_velocity_fl", description="Channel name for event detection")
    target_points: int = Field(2000, ge=10, le=50000, description="Target decimated point budget")
    detect_events: bool = Field(True, description="Whether to detect engineering spikes/events")


@router.post("/decimate")
async def decimate_telemetry_endpoint(req: DecimateRequest):
    """
    Downsample high-frequency telemetry channel using peak-preserving min-max bucketing.
    Preserves all physical spikes and extrema without smoothing out transients.
    """
    from suspensionlab.physics.telemetry_decimation import decimate_telemetry_trace
    decimated = decimate_telemetry_trace(
        timestamps=req.timestamps,
        values=req.values,
        channel_name=req.channel_name,
        target_points=req.target_points,
        detect_events=req.detect_events,
    )
    return decimated.to_dict()

