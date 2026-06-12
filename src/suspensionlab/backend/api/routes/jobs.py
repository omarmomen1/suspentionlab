from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import json
import redis.exceptions

from suspensionlab.backend.core.errors import JobNotFoundError, RedisUnavailableError
from suspensionlab.backend.security.auth import verify_api_key
from suspensionlab.backend.database.core import get_db_dependency
from suspensionlab.backend.database.models.job import JobRecord
from suspensionlab.backend.workers.queue import job_queue

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
    # 1. Try fast read-through from Redis to prevent DB load entirely
    try:
        redis_conn = job_queue.connection
        cached = redis_conn.get(f"job_status:{job_id}")
        if cached:
            parsed = json.loads(cached)
            # Authorize using user_id injected into cache
            if parsed.get("user_id") != user["user_id"]:
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
            JobRecord.id == job_id,
            JobRecord.user_id == user["user_id"]
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
    query = select(JobRecord).where(JobRecord.user_id == user["user_id"])
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

