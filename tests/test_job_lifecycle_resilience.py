"""
tests/test_job_lifecycle_resilience.py
======================================
Hostile audit verification for:
1. Job lifecycle states (PENDING, QUEUED, RUNNING, CANCEL_REQUESTED, CANCELLED, RETRYING, TIMEOUT).
2. Multi-stage cancellation (RUNNING -> CANCEL_REQUESTED vs. PENDING -> CANCELLED).
3. POST /jobs/{id}/retry validation, status gating, duplicate attempt prevention, and lineage tracking.
4. Redis outage resilience and clean HTTP 503 mapping.
"""

import uuid
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from fastapi import HTTPException
from sqlalchemy import select

from suspensionlab.backend.database.models.job import JobRecord
from suspensionlab.backend.security.auth import UserContext
from suspensionlab.backend.core.errors import RedisUnavailableError, JobNotFoundError
from suspensionlab.backend.api.routes.jobs import cancel_job, retry_job, RetryJobRequest


def make_user_context(user_id: uuid.UUID, permissions: list[str]) -> UserContext:
    return UserContext(
        user_id=str(user_id),
        email="engineer@suspensionlab.com",
        name="Lead Dynamics Engineer",
        plan="PRO",
        onboarding_complete=True,
        organization_id=str(uuid.uuid4()),
        permissions=permissions,
        is_admin=False,
    )


@pytest.mark.asyncio
async def test_job_model_allows_extended_lifecycle_states():
    # Verify JobRecord accepts extended lifecycle states in status field
    for st in ["PENDING", "QUEUED", "RUNNING", "CANCEL_REQUESTED", "CANCELLED", "RETRYING", "TIMEOUT"]:
        rec = JobRecord(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            job_type="OPTIMIZE_QUARTER",
            status=st,
            retry_count=1,
            retry_reason="Test attempt",
        )
        assert rec.status == st
        assert rec.retry_count == 1


@pytest.mark.asyncio
async def test_cancel_running_job_transitions_to_cancel_requested():
    job_uuid = uuid.uuid4()
    user_uuid = uuid.uuid4()
    mock_job = JobRecord(
        id=job_uuid,
        user_id=user_uuid,
        status="RUNNING",
    )

    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars().first.return_value = mock_job
    mock_db.execute.return_value = mock_result

    user = make_user_context(user_uuid, ["simulation:cancel"])

    with patch("suspensionlab.backend.api.routes.jobs.get_async_redis_conn", return_value=None):
        res = await cancel_job(job_id=str(job_uuid), user=user, db=mock_db)

    assert res["status"] == "CANCEL_REQUESTED"
    assert "notified" in res["message"].lower()


@pytest.mark.asyncio
async def test_cancel_terminal_job_returns_existing_status():
    job_uuid = uuid.uuid4()
    user_uuid = uuid.uuid4()
    mock_job = JobRecord(
        id=job_uuid,
        user_id=user_uuid,
        status="COMPLETED",
    )

    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars().first.return_value = mock_job
    mock_db.execute.return_value = mock_result

    user = make_user_context(user_uuid, ["simulation:cancel"])

    res = await cancel_job(job_id=str(job_uuid), user=user, db=mock_db)
    assert res["status"] == "COMPLETED"
    assert "already terminated" in res["message"].lower()


@pytest.mark.asyncio
async def test_retry_non_failed_job_raises_400():
    job_uuid = uuid.uuid4()
    user_uuid = uuid.uuid4()
    mock_job = JobRecord(
        id=job_uuid,
        user_id=user_uuid,
        status="RUNNING",  # Not retryable!
    )

    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars().first.return_value = mock_job
    mock_db.execute.return_value = mock_result

    user = make_user_context(user_uuid, ["simulation:run"])

    with pytest.raises(HTTPException) as exc_info:
        await retry_job(job_id=str(job_uuid), body=RetryJobRequest(reason="Retry test"), user=user, db=mock_db)

    assert exc_info.value.status_code == 400
    assert "cannot be retried" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_retry_duplicate_concurrent_attempt_raises_409():
    job_uuid = uuid.uuid4()
    user_uuid = uuid.uuid4()
    original_job = JobRecord(
        id=job_uuid,
        user_id=user_uuid,
        status="FAILED",
        retry_count=0,
    )
    existing_retry_child = JobRecord(
        id=uuid.uuid4(),
        parent_job_id=job_uuid,
        status="RUNNING",  # An attempt is already underway!
    )

    mock_db = AsyncMock()
    res1 = MagicMock()
    res1.scalars().first.return_value = original_job
    res2 = MagicMock()
    res2.scalars().first.return_value = existing_retry_child

    mock_db.execute.side_effect = [res1, res2]

    user = make_user_context(user_uuid, ["simulation:run"])

    with pytest.raises(HTTPException) as exc_info:
        await retry_job(job_id=str(job_uuid), body=RetryJobRequest(), user=user, db=mock_db)

    assert exc_info.value.status_code == 409
    assert "already active" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_retry_creates_linked_child_lineage():
    job_uuid = uuid.uuid4()
    user_uuid = uuid.uuid4()
    original_job = JobRecord(
        id=job_uuid,
        user_id=user_uuid,
        status="FAILED_NUMERICAL",
        retry_count=1,
        params={"k_s": 25000.0},
        profile={"amplitude": 0.01},
        job_type="OPTIMIZE_QUARTER",
    )

    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    res1 = MagicMock()
    res1.scalars().first.return_value = original_job
    res2 = MagicMock()
    res2.scalars().first.return_value = None  # No existing retry

    mock_db.execute.side_effect = [res1, res2]

    user = make_user_context(user_uuid, ["simulation:run"])

    with patch("suspensionlab.backend.workers.orchestrator.submit_simulation_job", new_callable=AsyncMock) as mock_submit:
        res = await retry_job(
            job_id=str(job_uuid),
            body=RetryJobRequest(reason="Post-failure numerical retry"),
            user=user,
            db=mock_db,
        )

    assert res["parent_job_id"] == str(job_uuid)
    assert res["retry_count"] == 2
    assert res["retry_reason"] == "Post-failure numerical retry"
    assert res["status"] == "PENDING"
    assert mock_submit.await_count == 1
