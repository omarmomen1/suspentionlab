"""
sdk/suspensionlab/streaming.py
==============================
SuspensionLab PRO — Real-Time WebSocket Streaming Client.
Provides live telemetry streaming, collaborative session event dispatch,
and resilient auto-reconnect logic.
"""

from __future__ import annotations

import json
import time
import asyncio
import logging
from typing import AsyncIterator, Callable, Dict, Any, Optional
import websockets
from websockets.exceptions import ConnectionClosed

logger = logging.getLogger("suspensionlab.streaming")


class SuspensionLabStreamingClient:
    """
    Asynchronous WebSocket streaming client for live vehicle telemetry.
    """

    def __init__(
        self,
        ws_url: str,
        auth_token: Optional[str] = None,
        max_reconnect_attempts: int = 5,
        reconnect_backoff: float = 1.0,
    ):
        self.ws_url = ws_url
        self.auth_token = auth_token
        self.max_reconnect_attempts = max_reconnect_attempts
        self.reconnect_backoff = reconnect_backoff
        self._ws: Optional[websockets.WebSocketClientProtocol] = None
        self._connected = False
        self._closed = False

    async def connect(self):
        """Establish WebSocket connection with retry and authentication."""
        headers = {}
        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"

        attempt = 0
        while attempt < self.max_reconnect_attempts and not self._closed:
            try:
                self._ws = await websockets.connect(self.ws_url, extra_headers=headers)
                self._connected = True
                logger.info("Connected to SuspensionLab streaming endpoint: %s", self.ws_url)
                return
            except Exception as e:
                attempt += 1
                wait_time = self.reconnect_backoff * (2 ** (attempt - 1))
                logger.warning(
                    "Streaming connection attempt %d failed: %s. Retrying in %.2f s...",
                    attempt, e, wait_time
                )
                await asyncio.sleep(wait_time)

        raise ConnectionError(
            f"Failed to connect to streaming endpoint {self.ws_url} after {self.max_reconnect_attempts} attempts."
        )

    async def send(self, data: Dict[str, Any]):
        """Send a JSON payload to the active streaming channel."""
        if not self._ws or not self._connected:
            raise ConnectionError("WebSocket is not connected.")
        msg = json.dumps(data)
        await self._ws.send(msg)

    async def listen(self) -> AsyncIterator[Dict[str, Any]]:
        """Yield parsed JSON messages from the stream, handling reconnects."""
        while not self._closed:
            if not self._connected or not self._ws:
                await self.connect()

            try:
                async for message in self._ws:
                    try:
                        data = json.loads(message)
                        yield data
                    except json.JSONDecodeError:
                        yield {"raw": message}
            except ConnectionClosed:
                self._connected = False
                logger.warning("Streaming connection closed by server.")
                if not self._closed:
                    await asyncio.sleep(self.reconnect_backoff)
            except Exception as e:
                self._connected = False
                logger.error("Streaming error: %s", e)
                if not self._closed:
                    await asyncio.sleep(self.reconnect_backoff)

    async def close(self):
        """Cleanly terminate the streaming connection."""
        self._closed = True
        self._connected = False
        if self._ws:
            await self._ws.close()
            self._ws = None

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
