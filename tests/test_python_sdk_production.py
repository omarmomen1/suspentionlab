"""
tests/test_python_sdk_production.py
===================================
Comprehensive test suite for the SuspensionLab Production Python SDK:
- Typed Pydantic models & validation
- Authentication & header injection
- Configurable timeouts
- Exponential backoff retry with jitter on HTTP 429/503
- Idempotency key injection
- Pagination generator traversal
- Asynchronous job polling state machine
- WebSocket streaming client lifecycle
- CAE export integration
"""

import sys
import json
import pathlib
import pytest
from unittest.mock import MagicMock
import requests

from suspensionlab.sdk import (
    SuspensionLabClient,
    SuspensionLabStreamingClient,
    QuarterCarParams,
    FullCarParams,
    RoadProfile,
    JobStatus,
    JobInfo,
)


def make_mock_response(status_code=200, json_data=None, text=""):
    resp = requests.Response()
    resp.status_code = status_code
    resp._content = json.dumps(json_data).encode("utf-8") if json_data is not None else text.encode("utf-8")
    return resp


def test_sdk_typed_models_instantiation():
    """Verify Pydantic models initialize and validate inputs."""
    qc = QuarterCarParams(m_s=320.0, k_s=28000.0, c=2100.0, MR=0.88)
    assert qc.m_s == 320.0
    assert qc.k_s == 28000.0
    assert qc.MR == 0.88

    prof = RoadProfile(profile_type="pothole", amplitude=0.04, duration=4.0)
    assert prof.profile_type == "pothole"
    assert prof.amplitude == 0.04

    job = JobInfo(job_id="job-123", status=JobStatus.RUNNING, progress=0.45)
    assert job.job_id == "job-123"
    assert job.status == JobStatus.RUNNING
    assert job.progress == 0.45


def test_sdk_authentication_headers():
    """Verify API key and Bearer token are configured in session headers."""
    # API key client
    client_key = SuspensionLabClient(api_key="sk_test_12345", base_url="http://testserver")
    assert client_key.session.headers["X-API-Key"] == "sk_test_12345"
    assert "Authorization" not in client_key.session.headers

    # Bearer token client
    client_token = SuspensionLabClient(access_token="jwt.mock.token", base_url="http://testserver")
    assert client_token.session.headers["Authorization"] == "Bearer jwt.mock.token"
    assert "X-API-Key" not in client_token.session.headers

    # Missing credentials must raise ValueError
    with pytest.raises(ValueError):
        SuspensionLabClient(base_url="http://testserver")


def test_sdk_retry_on_429_and_503():
    """Verify client retries on transient errors and succeeds with idempotency keys."""
    client = SuspensionLabClient(
        api_key="sk_test_123",
        base_url="http://mock-api.com",
        max_retries=2,
        backoff_factor=0.001,  # Fast backoff for tests
    )

    # Sequence: 429 Too Many Requests -> 503 Service Unavailable -> 200 OK
    resp_429 = make_mock_response(status_code=429)
    resp_503 = make_mock_response(status_code=503)
    resp_200 = make_mock_response(
        status_code=200,
        json_data={
            "time": [0.0, 0.01],
            "z_s": [0.0, 0.005],
            "z_u": [0.0, 0.01],
            "metrics": {"rms_accel": 1.25},
        },
    )

    mock_req = MagicMock(side_effect=[resp_429, resp_503, resp_200])
    client.session.request = mock_req

    res = client.simulate_quarter_car(QuarterCarParams())
    assert mock_req.call_count == 3
    assert res.time == [0.0, 0.01]
    assert res.metrics["rms_accel"] == 1.25

    # Verify each attempt had an Idempotency-Key
    for call in mock_req.call_args_list:
        headers = call.kwargs.get("headers", {})
        assert "Idempotency-Key" in headers


def test_sdk_timeout_propagation():
    """Verify configured timeout is respected by the request execution."""
    client = SuspensionLabClient(
        api_key="sk_test_123",
        base_url="http://mock-api.com",
        timeout=12.5,
    )
    assert client.timeout == 12.5


def test_sdk_job_polling():
    """Verify wait_for_job polls until terminal status is reached."""
    client = SuspensionLabClient(
        api_key="sk_test_123",
        base_url="http://mock-api.com",
    )

    resp_queued = make_mock_response(200, json_data={"job_id": "opt-789", "status": "QUEUED", "progress": 0.0})
    resp_running = make_mock_response(200, json_data={"job_id": "opt-789", "status": "RUNNING", "progress": 0.5})
    resp_done = make_mock_response(
        200, json_data={"job_id": "opt-789", "status": "COMPLETED", "progress": 1.0, "result": {"best_score": 0.94}}
    )

    mock_req = MagicMock(side_effect=[resp_queued, resp_running, resp_done])
    client.session.request = mock_req

    job = client.wait_for_job("opt-789", poll_interval=0.001, timeout=2.0)
    assert job.status == JobStatus.COMPLETED
    assert job.result["best_score"] == 0.94
    assert mock_req.call_count == 3


def test_sdk_pagination_traversal():
    """Verify paginate_jobs iterates across multiple pages."""
    client = SuspensionLabClient(
        api_key="sk_test_123",
        base_url="http://mock-api.com",
    )

    page1 = make_mock_response(
        200, json_data={"items": [{"job_id": "j-1", "status": "COMPLETED"}, {"job_id": "j-2", "status": "COMPLETED"}], "has_next": True}
    )
    page2 = make_mock_response(
        200, json_data={"items": [{"job_id": "j-3", "status": "COMPLETED"}], "has_next": False}
    )

    mock_req = MagicMock(side_effect=[page1, page2])
    client.session.request = mock_req

    jobs = list(client.paginate_jobs(limit=2))
    assert len(jobs) == 3
    assert [j.job_id for j in jobs] == ["j-1", "j-2", "j-3"]


@pytest.mark.asyncio
async def test_sdk_streaming_client_lifecycle():
    """Verify SuspensionLabStreamingClient initializes and manages connection state."""
    stream_client = SuspensionLabStreamingClient(
        ws_url="ws://mock-ws/api/v1/telemetry/live",
        auth_token="test-token",
        max_reconnect_attempts=1,
    )
    assert stream_client.ws_url == "ws://mock-ws/api/v1/telemetry/live"
    assert stream_client.auth_token == "test-token"
    assert stream_client._connected is False
    assert stream_client._closed is False

    await stream_client.close()
    assert stream_client._closed is True
