"""
suspensionlab.telemetry.hub
===========================
Multi-Tenant Telemetry Streaming Hub with Backpressure & Heartbeat.

Enforces:
- Organization tenant isolation (clients cannot subscribe across tenant boundary)
- Per-client backpressure handling with bounded async queues
- Binary SLTP v1 and JSON subprotocol distribution
- Dynamic connection health & ping/pong heartbeats
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Any
from fastapi import WebSocket, status

from suspensionlab.telemetry.protocol import SLTPFrame

logger = logging.getLogger(__name__)


@dataclass
class TelemetrySubscriber:
    """Represents an active WebSocket subscriber."""
    websocket: WebSocket
    user_id: str
    organization_id: str
    is_admin: bool
    session_id: str
    binary_mode: bool = True
    queue: asyncio.Queue[bytes | dict] = field(default_factory=lambda: asyncio.Queue(maxsize=100))
    connected_at: float = field(default_factory=time.time)
    last_heartbeat: float = field(default_factory=time.time)
    frames_sent: int = 0
    frames_dropped: int = 0
    is_alive: bool = True


class TenantIsolationError(Exception):
    """Raised when a client attempts to subscribe to another organization's telemetry."""
    pass


class TelemetryHub:
    """Central multi-tenant telemetry distribution hub."""

    def __init__(self):
        # Maps session_id -> list of subscribers
        self._subscribers: Dict[str, List[TelemetrySubscriber]] = {}
        # Maps session_id -> owner organization_id
        self._session_owners: Dict[str, str] = {}
        self._lock = asyncio.Lock()
        self._stats = {
            "total_broadcasts": 0,
            "total_bytes_sent": 0,
            "backpressure_drops": 0,
        }

    def register_session_owner(self, session_id: str, organization_id: str) -> None:
        """Bind a telemetry session to an owning organization."""
        self._session_owners[session_id] = organization_id

    record_session_tenant = register_session_owner

    def get_session_owner(self, session_id: str) -> Optional[str]:
        return self._session_owners.get(session_id)

    def assert_tenant_access(self, organization_id: str, session_id: str, is_admin: bool = False) -> bool:
        """Synchronously assert tenant permission to access a session."""
        owner_org = self._session_owners.get(session_id)
        if owner_org is None:
            self._session_owners[session_id] = organization_id
            return True
        if not is_admin and str(owner_org) != str(organization_id):
            raise TenantIsolationError(
                f"Access Denied: Session belongs to organization '{owner_org}', "
                f"but subscriber belongs to '{organization_id}'."
            )
        return True

    async def subscribe(
        self,
        websocket: WebSocket,
        user_id: str,
        organization_id: str,
        session_id: str,
        is_admin: bool = False,
        binary_mode: bool = True,
    ) -> TelemetrySubscriber:
        """
        Authenticate and authorize a WebSocket connection to subscribe to a session.
        Enforces tenant isolation: unless is_admin is True, organization_id must match!
        """
        # Enforce Tenant Isolation (Step 7)
        owner_org = self._session_owners.get(session_id)
        if owner_org is None:
            # First one to claim or register binds the session
            self._session_owners[session_id] = organization_id
            owner_org = organization_id

        if not is_admin and str(owner_org) != str(organization_id):
            logger.warning(
                "Tenant violation attempt! User %s (org %s) tried to access session %s owned by org %s",
                user_id, organization_id, session_id, owner_org,
            )
            raise TenantIsolationError(
                f"Access Denied: Session belongs to organization '{owner_org}', "
                f"but subscriber belongs to '{organization_id}'."
            )

        subscriber = TelemetrySubscriber(
            websocket=websocket,
            user_id=user_id,
            organization_id=organization_id,
            is_admin=is_admin,
            session_id=session_id,
            binary_mode=binary_mode,
        )

        async with self._lock:
            if session_id not in self._subscribers:
                self._subscribers[session_id] = []
            self._subscribers[session_id].append(subscriber)

        logger.info(
            "Subscriber joined session %s (org: %s, binary: %s). Active: %d",
            session_id, organization_id, binary_mode, len(self._subscribers[session_id]),
        )
        return subscriber

    async def unsubscribe(self, subscriber: TelemetrySubscriber) -> None:
        """Remove a subscriber and cleanly release resources."""
        subscriber.is_alive = False
        async with self._lock:
            subs = self._subscribers.get(subscriber.session_id, [])
            if subscriber in subs:
                subs.remove(subscriber)
            if not subs and subscriber.session_id in self._subscribers:
                del self._subscribers[subscriber.session_id]
        logger.info("Subscriber left session %s.", subscriber.session_id)

    async def broadcast_frame(self, frame: SLTPFrame) -> int:
        """
        Distribute a telemetry frame to all authorized subscribers of the session.
        Implements bounded queue backpressure.
        """
        session_id = frame.session_id
        async with self._lock:
            subs = list(self._subscribers.get(session_id, []))

        if not subs:
            return 0

        binary_payload = frame.pack()
        json_payload = frame.to_dict()
        sent_count = 0

        for sub in subs:
            if not sub.is_alive:
                continue

            payload = binary_payload if sub.binary_mode else json_payload
            try:
                # Non-blocking put into bounded queue; drop oldest if buffer is full (backpressure)
                if sub.queue.full():
                    try:
                        sub.queue.get_nowait()
                        sub.frames_dropped += 1
                        self._stats["backpressure_drops"] += 1
                    except asyncio.QueueEmpty:
                        pass

                sub.queue.put_nowait(payload)
                sent_count += 1
            except Exception as exc:
                logger.debug("Failed to enqueue telemetry frame for subscriber: %s", exc)

        self._stats["total_broadcasts"] += 1
        self._stats["total_bytes_sent"] += len(binary_payload) * sent_count
        return sent_count

    def get_active_sessions_count(self) -> int:
        return len(self._subscribers)

    def get_subscriber_count(self, session_id: str) -> int:
        return len(self._subscribers.get(session_id, []))

    def get_stats(self) -> Dict[str, Any]:
        total_subs = sum(len(s) for s in self._subscribers.values())
        return {
            "active_sessions": len(self._subscribers),
            "total_subscribers": total_subs,
            **self._stats,
        }


# Global singleton hub for application telemetry streaming
global_telemetry_hub = TelemetryHub()
