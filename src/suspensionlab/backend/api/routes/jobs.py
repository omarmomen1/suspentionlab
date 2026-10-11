from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import json
import logging
import redis.exceptions

from suspensionlab.backend.core.errors import JobNotFoundError, RedisUnavailableError
from suspensionlab.backend.security.auth import require_permission, UserContext
from suspensionlab.backend.security.permissions import Permission
from suspensionlab.backend.database.core import get_db_dependency
from suspensionlab.backend.database.models.job import JobRecord
from suspensionlab.backend.workers.task_queue import job_queue
from suspensionlab.backend.core.redis_client import get_async_redis_conn

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/jobs", tags=["jobs"])

@router.get("/{job_id}")
async def get_job_status(
    job_id: str,
    user: UserContext = Depends(require_permission(Permission.SIMULATION_READ)),
    db: AsyncSession = Depends(get_db_dependency)
):
    """
    Unified polling endpoint for any async job (optimization, future sweeps, etc.).
    Returns status, result, error, and timestamps.
    """
    import uuid
    try:
        job_uuid = uuid.UUID(job_id) if isinstance(job_id, str) else job_id
        user_uuid = uuid.UUID(str(user.user_id)) if isinstance(user.user_id, str) else user.user_id
    except ValueError:
        raise JobNotFoundError("Invalid job ID format")

    # 1. Try fast read-through from Redis to prevent DB load entirely
    try:
        async_redis = get_async_redis_conn()
        if async_redis:
            cached = await async_redis.get(f"job_status:{job_id}")
            if cached:
                parsed = json.loads(cached)
                cached_user_id = parsed.get("user_id")
                cached_team_id = parsed.get("team_id")
                # Authorize using user_id or team_id injected into cache if present
                is_owner = cached_user_id and str(cached_user_id) == str(user.user_id)
                is_teammate = cached_team_id and getattr(user, "team_id", None) and str(cached_team_id) == str(user.team_id)
                if cached_user_id and not (is_owner or is_teammate):
                    raise JobNotFoundError("Active job not found or unauthorized")
                # If still PENDING/RUNNING, return immediately without touching PostgreSQL
                if parsed.get("status") in ["PENDING", "RUNNING"]:
                    return parsed
            
            # If COMPLETED/FAILED, we fall through to DB to get authoritative timestamps
    except redis.exceptions.ConnectionError:
        pass # Fallback to DB if Redis is unreachable

    # 2. Fallback to Database
    from sqlalchemy import or_
    access_condition = (
        or_(JobRecord.team_id == uuid.UUID(str(user.team_id)), JobRecord.user_id == user_uuid)
        if getattr(user, "team_id", None)
        else (JobRecord.user_id == user_uuid)
    )
    result = await db.execute(
        select(JobRecord).where(
            JobRecord.id == job_uuid,
            access_condition,
            JobRecord.deleted_at.is_(None)
        )
    )
    job_record = result.scalars().first()
    
    if not job_record:
        logger.warning(f"DEBUG JOBS: job_uuid={job_uuid}, user_uuid={user_uuid}, access_condition={access_condition}")
        raise JobNotFoundError("Job not found in database")

    return {
        "job_id": str(job_record.id),
        "status": job_record.status,
        "result": job_record.result,
        "error": job_record.error,
        "parent_job_id": str(job_record.parent_job_id) if job_record.parent_job_id else None,
        "retry_count": job_record.retry_count or 0,
        "retry_reason": job_record.retry_reason,
        "started_at": job_record.started_at.isoformat() if job_record.started_at else None
    }

from fastapi.responses import StreamingResponse
import asyncio

@router.get("/{job_id}/stream")
async def stream_job_status(
    job_id: str,
    user: UserContext = Depends(require_permission(Permission.SIMULATION_READ)),
    db: AsyncSession = Depends(get_db_dependency)
):
    """
    Server-Sent Events (SSE) endpoint for real-time job status.
    """
    import uuid
    try:
        job_uuid = uuid.UUID(job_id) if isinstance(job_id, str) else job_id
        user_uuid = uuid.UUID(str(user.user_id)) if isinstance(user.user_id, str) else user.user_id
    except ValueError:
        raise JobNotFoundError("Invalid job ID format")

    async def event_generator():
        while True:
            try:
                async_redis = get_async_redis_conn()
                if async_redis:
                    cached = await async_redis.get(f"job_status:{job_id}")
                    if cached:
                        parsed = json.loads(cached)
                        cached_user_id = parsed.get("user_id")
                        cached_team_id = parsed.get("team_id")
                        is_owner = cached_user_id and str(cached_user_id) == str(user.user_id)
                        is_teammate = cached_team_id and getattr(user, "team_id", None) and str(cached_team_id) == str(user.team_id)
                        if cached_user_id and not (is_owner or is_teammate):
                            yield f"data: {json.dumps({'error': 'Job not found'})}\n\n"
                            break
                    
                    yield f"data: {json.dumps(parsed)}\n\n"
                    
                    if parsed.get("status") in ["COMPLETED", "FAILED", "CANCELED"]:
                        break
            except redis.exceptions.ConnectionError:
                pass
            
            from sqlalchemy import or_
            if getattr(user, "team_id", None):
                access_condition = or_(JobRecord.team_id == uuid.UUID(str(user.team_id)), JobRecord.user_id == user_uuid)
            else:
                access_condition = (JobRecord.user_id == user_uuid)
            result = await db.execute(select(JobRecord).where(JobRecord.id == job_uuid, access_condition, JobRecord.deleted_at.is_(None)))
            job_record = result.scalars().first()
            if not job_record:
                yield f"data: {json.dumps({'error': 'Job not found'})}\n\n"
                break
                
            data = {
                "job_id": str(job_record.id),
                "status": job_record.status,
                "result": job_record.result,
                "error": job_record.error,
                "started_at": job_record.started_at.isoformat() if job_record.started_at else None
            }
            yield f"data: {json.dumps(data)}\n\n"
            
            if job_record.status in ["COMPLETED", "FAILED", "CANCELED"]:
                break
                
            await asyncio.sleep(1.0)
            
    return StreamingResponse(event_generator(), media_type="text/event-stream")

from fastapi import Query
from typing import Optional
from sqlalchemy import func

@router.get("")
async def list_jobs(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    status: Optional[str] = Query(default=None, pattern="^(PENDING|RUNNING|COMPLETED|FAILED)$"),
    user: UserContext = Depends(require_permission(Permission.SIMULATION_READ)),
    db: AsyncSession = Depends(get_db_dependency)
):
    """
    List all historical jobs for the user.
    """
    import uuid
    from sqlalchemy import or_
    user_uuid = uuid.UUID(str(user.user_id))
    access_condition = (
        or_(JobRecord.team_id == uuid.UUID(str(user.team_id)), JobRecord.user_id == user_uuid)
        if getattr(user, "team_id", None)
        else (JobRecord.user_id == user_uuid)
    )
    query = select(JobRecord).where(access_condition, JobRecord.deleted_at.is_(None))
    if status:
        query = query.where(JobRecord.status == status)
    
    total_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = total_result.scalar()
    
    query = query.order_by(JobRecord.started_at.desc()).offset(offset).limit(limit)
    result = await db.execute(query)
    jobs = result.scalars().all()
    
    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "jobs": [
            {
                "job_id": j.id,
                "status": j.status,
                "started_at": j.started_at.isoformat() if j.started_at else None,
                "result": j.result,
                "error": j.error,
            }
            for j in jobs
        ]
    }

from fastapi import HTTPException

from pydantic import BaseModel, Field

class RetryJobRequest(BaseModel):
    reason: Optional[str] = Field(default="Manual user retry", description="Reason for initiating retry")


@router.post("/{job_id}/cancel")
async def cancel_job(
    job_id: str,
    user: UserContext = Depends(require_permission(Permission.SIMULATION_CANCEL)),
    db: AsyncSession = Depends(get_db_dependency)
):
    """
    Multi-stage cancellation:
    - If already finished (COMPLETED, FAILED, CANCELLED, TIMEOUT), returns terminal status.
    - If PENDING or QUEUED, immediately transitions to CANCELLED.
    - If RUNNING, sets CANCEL_REQUESTED and emits cancellation signal to active worker.
    """
    import uuid
    from sqlalchemy import or_, update
    try:
        job_uuid = uuid.UUID(str(job_id))
        user_uuid = uuid.UUID(str(user.user_id))
    except ValueError:
        raise JobNotFoundError("Invalid job ID format")
    
    if getattr(user, "team_id", None):
        team_role = (getattr(user, "team_role", None) or "Viewer").upper()
        if team_role in ("OWNER", "ADMIN"):
            access_cond = or_(JobRecord.user_id == user_uuid, JobRecord.team_id == uuid.UUID(str(user.team_id)))
        else:
            access_cond = (JobRecord.user_id == user_uuid)
    else:
        access_cond = (JobRecord.user_id == user_uuid)

    result = await db.execute(select(JobRecord).where(JobRecord.id == job_uuid, access_cond, JobRecord.deleted_at.is_(None)))
    job = result.scalars().first()
    if not job:
        raise JobNotFoundError("Job not found")

    FINISHED_STATUSES = {
        "COMPLETED", "COMPLETED_VALID", "COMPLETED_WITH_WARNINGS",
        "FAILED", "FAILED_NUMERICAL", "FAILED_INPUT", "FAILED_PHYSICS",
        "CANCELED", "CANCELLED", "TIMEOUT"
    }
    if job.status in FINISHED_STATUSES:
        return {"status": job.status, "message": f"Job already terminated with status {job.status}."}

    from rq.job import Job
    import asyncio
    try:
        redis_conn = job_queue.connection
        def cancel_rq_job():
            rq_job = Job.fetch(job_id, connection=redis_conn)
            rq_job.cancel()
        await asyncio.to_thread(cancel_rq_job)
    except Exception:
        pass

    target_status = "CANCEL_REQUESTED" if job.status == "RUNNING" else "CANCELLED"

    await db.execute(update(JobRecord).where(JobRecord.id == job_uuid).values(status=target_status))
    await db.commit()

    try:
        async_redis = get_async_redis_conn()
        if async_redis:
            await async_redis.setex(f"job_cancel:{job_id}", 86400, "1")
            cached = await async_redis.get(f"job_status:{job_id}")
            if cached:
                parsed = json.loads(cached)
                parsed["status"] = target_status
                await async_redis.setex(f"job_status:{job_id}", 86400, json.dumps(parsed))
    except Exception:
        pass

    return {
        "status": target_status,
        "message": "Cancellation requested; worker notified." if target_status == "CANCEL_REQUESTED" else "Job cancelled immediately."
    }


@router.post("/{job_id}/retry")
async def retry_job(
    job_id: str,
    body: Optional[RetryJobRequest] = None,
    user: UserContext = Depends(require_permission(Permission.SIMULATION_RUN)),
    db: AsyncSession = Depends(get_db_dependency),
):
    """
    Retry a failed or timed-out job.
    - Requires SIMULATION_RUN permission.
    - Authorizes caller as job owner or team admin.
    - Verifies retryable failure status.
    - Prevents duplicate concurrent retries.
    - Records parent/child attempt lineage and increments retry_count.
    - Dispatches job with Redis resilience (HTTP 503 if compute plane unavailable).
    """
    import uuid
    from sqlalchemy import or_, update
    try:
        job_uuid = uuid.UUID(str(job_id))
        user_uuid = uuid.UUID(str(user.user_id))
    except ValueError:
        raise JobNotFoundError("Invalid job ID format")

    if getattr(user, "team_id", None):
        team_role = (getattr(user, "team_role", None) or "Viewer").upper()
        if team_role in ("OWNER", "ADMIN"):
            access_cond = or_(JobRecord.user_id == user_uuid, JobRecord.team_id == uuid.UUID(str(user.team_id)))
        else:
            access_cond = (JobRecord.user_id == user_uuid)
    else:
        access_cond = (JobRecord.user_id == user_uuid)

    result = await db.execute(select(JobRecord).where(JobRecord.id == job_uuid, access_cond, JobRecord.deleted_at.is_(None)))
    original_job = result.scalars().first()
    if not original_job:
        raise JobNotFoundError("Job not found or unauthorized")

    RETRYABLE_STATUSES = {
        "FAILED", "FAILED_NUMERICAL", "FAILED_INPUT", "FAILED_PHYSICS", "TIMEOUT"
    }
    if original_job.status not in RETRYABLE_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"Job {job_id} is in status '{original_job.status}' and cannot be retried. "
                   f"Only failed or timed-out jobs can be retried."
        )

    # Check for active existing retry attempt
    existing_retry = await db.execute(
        select(JobRecord).where(
            JobRecord.parent_job_id == original_job.id,
            JobRecord.status.in_(["PENDING", "QUEUED", "RUNNING", "CANCEL_REQUESTED"]),
            JobRecord.deleted_at.is_(None),
        )
    )
    if existing_retry.scalars().first():
        raise HTTPException(
            status_code=409,
            detail=f"A retry attempt is already active or queued for job {job_id}."
        )

    current_retries = original_job.retry_count or 0
    if current_retries >= 5:
        raise HTTPException(
            status_code=400,
            detail=f"Maximum retry limit (5) reached for job {job_id}."
        )

    child_job_id = uuid.uuid4()
    retry_reason = body.reason if body and body.reason else "Manual user retry"

    child_job = JobRecord(
        id=child_job_id,
        user_id=original_job.user_id,
        team_id=original_job.team_id,
        session_id=original_job.session_id,
        job_type=original_job.job_type,
        status="PENDING",
        params=original_job.params,
        profile=original_job.profile,
        parent_job_id=original_job.id,
        retry_count=current_retries + 1,
        retry_reason=retry_reason,
    )
    db.add(child_job)
    await db.commit()

    # Resilient Enqueue
    payload = {
        "params": original_job.params or {},
        "profile": original_job.profile or {},
        "job_type": original_job.job_type,
    }

    try:
        from suspensionlab.backend.workers.orchestrator import submit_simulation_job
        from suspensionlab.backend.workers.unified_worker import run_job
        from rq import Retry
        import asyncio

        # Prime Redis cache for new job
        try:
            redis_conn = job_queue.connection
            res_data = {
                "job_id": str(child_job_id),
                "parent_job_id": str(original_job.id),
                "status": "PENDING",
                "user_id": str(user.user_id),
                "retry_count": child_job.retry_count,
            }
            await asyncio.to_thread(redis_conn.setex, f"job_status:{child_job_id}", 86400, json.dumps(res_data))
        except Exception:
            pass

        trace_carrier = {"correlation": {"job_id": str(child_job_id), "parent_job_id": str(original_job.id)}}
        await submit_simulation_job(
            run_job,
            job_id=str(child_job_id),
            payload=payload,
            trace_carrier=trace_carrier,
            plan=getattr(user, "plan", "STANDARD"),
            result_ttl=86400,
            failure_ttl=86400,
            retry=Retry(max=2, interval=[10, 30]),
        )
    except Exception as exc:
        logger.warning(f"Redis queue submit failed during retry: {exc}. Executing via bounded fallback pool.")
        try:
            from suspensionlab.backend.core.compute_governance import bounded_run
            from suspensionlab.backend.workers.unified_worker import run_job
            import asyncio
            loop = asyncio.get_running_loop()
            loop.create_task(bounded_run(run_job, str(child_job_id), payload, {}))
        except Exception as e:
            await db.execute(
                update(JobRecord)
                .where(JobRecord.id == child_job_id)
                .values(status="FAILED", error="Compute plane unavailable for retry.")
            )
            await db.commit()
            raise RedisUnavailableError("Compute plane unavailable for retry submission.")

    return {
        "job_id": str(child_job.id),
        "parent_job_id": str(original_job.id),
        "status": child_job.status,
        "retry_count": child_job.retry_count,
        "retry_reason": child_job.retry_reason,
        "message": f"Retry attempt #{child_job.retry_count} queued successfully."
    }

