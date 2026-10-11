"""
tests/test_telemetry_tenant_isolation.py
========================================
Security regression tests for multi-tenant isolation in telemetry streaming.
Verifies that clients from Organization B cannot subscribe to Organization A's telemetry.
"""

import pytest
import asyncio
from unittest.mock import MagicMock

from suspensionlab.telemetry.hub import (
    TelemetryHub,
    TenantIsolationError,
    TelemetrySubscriber,
)
from suspensionlab.telemetry.protocol import (
    SLTPFrame,
    ChannelSample,
    ChannelId,
    QualityCode,
)


@pytest.mark.asyncio
async def test_tenant_isolation_allows_same_org():
    """Verify subscriber belonging to the session organization is authorized."""
    hub = TelemetryHub()
    session_id = "session-redbull-01"
    org_id = "org-redbull"

    mock_ws = MagicMock()
    sub = await hub.subscribe(
        websocket=mock_ws,
        user_id="user-max",
        organization_id=org_id,
        session_id=session_id,
        is_admin=False,
    )
    assert sub.organization_id == org_id
    assert hub.get_subscriber_count(session_id) == 1
    await hub.unsubscribe(sub)


@pytest.mark.asyncio
async def test_tenant_isolation_blocks_cross_org_subscription():
    """Verify subscriber from competing organization is rejected with TenantIsolationError."""
    hub = TelemetryHub()
    session_id = "session-ferrari-private"
    org_ferrari = "org-ferrari"
    org_mclaren = "org-mclaren"

    mock_ws_ferrari = MagicMock()
    # Ferrari starts and owns session
    sub_ferrari = await hub.subscribe(
        websocket=mock_ws_ferrari,
        user_id="charles",
        organization_id=org_ferrari,
        session_id=session_id,
        is_admin=False,
    )

    # McLaren engineer attempts unauthorized cross-tenant subscription
    mock_ws_mclaren = MagicMock()
    with pytest.raises(TenantIsolationError, match="Access Denied"):
        await hub.subscribe(
            websocket=mock_ws_mclaren,
            user_id="lando",
            organization_id=org_mclaren,
            session_id=session_id,
            is_admin=False,
        )

    # Verify McLaren subscriber was NOT added
    assert hub.get_subscriber_count(session_id) == 1
    await hub.unsubscribe(sub_ferrari)


@pytest.mark.asyncio
async def test_admin_cross_org_bypass():
    """Verify super-admin can inspect telemetry sessions across tenants for safety/compliance."""
    hub = TelemetryHub()
    session_id = "session-audit-01"
    org_team = "org-williams"

    # Team starts session
    hub.register_session_owner(session_id, org_team)

    mock_ws_admin = MagicMock()
    admin_sub = await hub.subscribe(
        websocket=mock_ws_admin,
        user_id="fia-auditor",
        organization_id="org-fia",
        session_id=session_id,
        is_admin=True,
    )
    assert admin_sub.is_admin is True
    assert hub.get_subscriber_count(session_id) == 1
    await hub.unsubscribe(admin_sub)


@pytest.mark.asyncio
async def test_isolated_broadcast_delivery():
    """Verify telemetry broadcast to Org 1 does not leak into Org 2's session."""
    hub = TelemetryHub()
    sess_1 = "sess-team1"
    sess_2 = "sess-team2"

    sub_1 = await hub.subscribe(MagicMock(), "u1", "org1", sess_1)
    sub_2 = await hub.subscribe(MagicMock(), "u2", "org2", sess_2)

    # Broadcast frame to sess_1 only
    frame_1 = SLTPFrame(
        sequence_number=1,
        timestamp=0.01,
        org_id="org1",
        session_id=sess_1,
        samples=[ChannelSample(ChannelId.SPEED_MS, 50.0, QualityCode.GOOD)],
    )
    await hub.broadcast_frame(frame_1)

    assert sub_1.queue.qsize() == 1
    assert sub_2.queue.qsize() == 0  # Zero leakage into org 2!

    await hub.unsubscribe(sub_1)
    await hub.unsubscribe(sub_2)
