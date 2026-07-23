from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import json
import redis.exceptions

from suspensionlab.backend.core.errors import JobNotFoundError, RedisUnavailableError
from suspensionlab.backend.security.auth import verify_api_key
from suspensionlab.backend.database.core import get_db_dependency
from suspensionlab.backend.database.models.job import JobRecord
from suspensionlab.backend.workers.task_queue import job_queue
from suspensionlab.backend.core.redis_client import get_async_redis_conn

router = APIRouter(prefix="/jobs", tags=["jobs"])

@router.get("/{job_id}")
async def get_job_status(
    job_id: str,
    user: dict = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency)
):
    """
    Unified polling endpoint for any async job (optimization, future sweeps, etc.).
    Returns status, result, error, and timestamps.
    """
    import uuid
    try:
        job_uuid = uuid.UUID(job_id) if isinstance(job_id, str) else job_id
        user_uuid = uuid.UUID(user.user_id) if isinstance(user.user_id, str) else user.user_id
    except ValueError:
        raise JobNotFoundError("Invalid job ID format")

    # 1. Try fast read-through from Redis to prevent DB load entirely
    try:
        async_redis = get_async_redis_conn()
        if async_redis:
            cached = await async_redis.get(f"job_status:{job_id}")
            if cached:
                parsed = json.loads(cached)
                # Authorize using user_id injected into cache
                if parsed.get("user_id") != user.user_id:
                    raise JobNotFoundError("Active job not found or unauthorized")
                # If still PENDING/RUNNING, return immediately without touching PostgreSQL
                if parsed.get("status") in ["PENDING", "RUNNING"]:
                    return parsed
            
            # If COMPLETED/FAILED, we fall through to DB to get authoritative timestamps
    except redis.exceptions.ConnectionError:
        pass # Fallback to DB if Redis is unreachable

    # 2. Fallback to Database
    result = await db.execute(
        select(JobRecord).where(
            JobRecord.id == job_uuid,
            JobRecord.user_id == user_uuid,
            JobRecord.deleted_at.is_(None)
        )
    )
    job_record = result.scalars().first()
    
    if not job_record:
        raise JobNotFoundError("Job not found in database")

    return {
        "job_id": job_record.id,
        "status": job_record.status,
        "result": job_record.result,
        "error": job_record.error,
        "started_at": job_record.started_at.isoformat() if job_record.started_at else None
    }

from fastapi.responses import StreamingResponse
import asyncio

@router.get("/{job_id}/stream")
async def stream_job_status(
    job_id: str,
    user: dict = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency)
):
    """
    Server-Sent Events (SSE) endpoint for real-time job status.
    """
    import uuid
    try:
        job_uuid = uuid.UUID(job_id) if isinstance(job_id, str) else job_id
        user_uuid = uuid.UUID(user.user_id) if isinstance(user.user_id, str) else user.user_id
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
                        if parsed.get("user_id") != user.user_id:
                            yield f"data: {json.dumps({'error': 'Unauthorized'})}\\n\\n"
                            break
                    
                    yield f"data: {json.dumps(parsed)}\\n\\n"
                    
                    if parsed.get("status") in ["COMPLETED", "FAILED", "CANCELED"]:
                        break
            except redis.exceptions.ConnectionError:
                pass
            
            result = await db.execute(select(JobRecord).where(JobRecord.id == job_uuid, JobRecord.user_id == user_uuid, JobRecord.deleted_at.is_(None),
            JobRecord.deleted_at.is_(None)))
            job_record = result.scalars().first()
            if not job_record:
                yield f"data: {json.dumps({'error': 'Job not found'})}\\n\\n"
                break
                
            data = {
                "job_id": str(job_record.id),
                "status": job_record.status,
                "result": job_record.result,
                "error": job_record.error,
                "started_at": job_record.started_at.isoformat() if job_record.started_at else None
            }
            yield f"data: {json.dumps(data)}\\n\\n"
            
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
    user: dict = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency)
):
    """
    List all historical jobs for the user.
    """
    query = select(JobRecord).where(JobRecord.user_id == user.user_id, JobRecord.deleted_at.is_(None))
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

@router.post("/{job_id}/cancel")
async def cancel_job(
    job_id: str,
    user: dict = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency)
):
    """
    Cancel a pending or running job.
    """
    result = await db.execute(select(JobRecord).where(JobRecord.id == job_id, JobRecord.user_id == user.user_id))
    job = result.scalars().first()
    if not job:
        raise JobNotFoundError("Job not found")
        
    if job.status in ["COMPLETED", "FAILED", "CANCELED"]:
        return {"status": job.status, "message": "Job already finished."}
        
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
        
    from sqlalchemy import update
    await db.execute(update(JobRecord).where(JobRecord.id == job_id).values(status="CANCELED"))
    await db.commit()
    
    try:
        async_redis = get_async_redis_conn()
        if async_redis:
            await async_redis.setex(f"job_cancel:{job_id}", 86400, "1")
            cached = await async_redis.get(f"job_status:{job_id}")
            if cached:
                parsed = json.loads(cached)
                parsed["status"] = "CANCELED"
                await async_redis.setex(f"job_status:{job_id}", 86400, json.dumps(parsed))
    except Exception:
        pass
        
    return {"status": "CANCELED", "message": "Cancellation requested."}

