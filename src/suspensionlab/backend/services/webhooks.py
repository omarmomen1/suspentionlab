"""
backend/services/webhooks.py
============================
Outbound webhook delivery (Tier C2).

Delivery contract
-----------------
POST {url}
Headers:
    Content-Type: application/json
    X-SL-Event: <event name, e.g. job.completed>
    X-SL-Timestamp: <unix seconds>
    X-SL-Signature: v1=<hex hmac_sha256(secret, f"{timestamp}.{body}")>
Retries: 3 attempts with exponential backoff (1s, 2s, 4s). A delivery that
exhausts retries is logged and dropped — webhook delivery is best-effort and
must never break the simulation pipeline.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import time

from sqlalchemy import select

logger = logging.getLogger(__name__)

import ipaddress
import os
import socket
from urllib.parse import urlparse

RETRY_DELAYS_S = (1.0, 2.0, 4.0)
TIMEOUT_S = 10.0


def validate_webhook_url(url: str) -> str | None:
    """
    Validates webhook URL to prevent Server-Side Request Forgery (SSRF).
    Blocks private RFC 1918 addresses, loopbacks, link-local (AWS metadata 169.254.169.254),
    and non-http(s) schemes unless ALLOW_PRIVATE_WEBHOOKS=true is explicitly set in testing.
    Returns the first verified safe IP string.
    """
    if os.getenv("ALLOW_PRIVATE_WEBHOOKS", "false").lower() == "true":
        return None

    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"Invalid URL scheme '{parsed.scheme}'. Only http and https are permitted.")

    hostname = parsed.hostname
    if not hostname:
        raise ValueError("Invalid URL: missing hostname.")

    if hostname.lower() in ("localhost", "127.0.0.1", "::1", "metadata.google.internal"):
        raise ValueError(f"Webhook target '{hostname}' is not permitted.")

    try:
        addr_info = socket.getaddrinfo(hostname, None)
        safe_ip = None
        for _, _, _, _, sockaddr in addr_info:
            ip_str = sockaddr[0]
            ip = ipaddress.ip_address(ip_str)
            if (
                ip.is_private
                or ip.is_loopback
                or ip.is_link_local
                or ip.is_reserved
                or ip.is_multicast
                or ip.is_unspecified
                or ip_str == "169.254.169.254"
            ):
                raise ValueError(f"Webhook URL resolves to prohibited IP address: {ip_str}")
            if safe_ip is None:
                safe_ip = ip_str
        return safe_ip
    except socket.gaierror as exc:
        raise ValueError(f"Could not resolve webhook hostname '{hostname}': {exc}")


def sign_payload(secret: str, timestamp: str, body: str) -> str:
    """v1-signature over '{timestamp}.{body}' — mirrors Stripe's scheme."""
    mac = hmac.new(secret.encode("utf-8"), f"{timestamp}.{body}".encode("utf-8"), hashlib.sha256)
    return f"v1={mac.hexdigest()}"


async def _deliver_once(url: str, headers: dict, body: str) -> bool:
    try:
        validate_webhook_url(url)
    except ValueError as val_err:
        logger.warning("Blocked outbound webhook to %s due to SSRF policy: %s", url, val_err)
        return False

    try:
        import httpx
        # Explicitly disallow redirects (follow_redirects=False) to prevent redirect-based SSRF bypass
        async with httpx.AsyncClient(timeout=TIMEOUT_S, follow_redirects=False) as client:
            resp = await client.post(url, content=body, headers=headers)
        return 200 <= resp.status_code < 300
    except Exception as exc:
        logger.warning("Webhook delivery to %s failed: %s", url, exc)
        return False




async def dispatch_event(db, user_id: str, event: str, payload: dict) -> int:
    """
    Send `event` with `payload` to every active endpoint of `user_id`
    subscribed to it. Returns the number of successful deliveries.
    Safe to call fire-and-forget; never raises.
    """
    delivered = 0
    try:
        from suspensionlab.backend.database.models.webhook import WebhookEndpoint
        result = await db.execute(
            select(WebhookEndpoint).where(
                WebhookEndpoint.user_id == user_id,
                WebhookEndpoint.is_active == True,  # noqa: E712
            )
        )
        endpoints = [ep for ep in result.scalars().all() if event in (ep.events or "").split(",")]
        if not endpoints:
            return 0

        body = json.dumps({"event": event, "data": payload}, default=str, separators=(",", ":"))
        timestamp = str(int(time.time()))
        signature = None  # computed per-endpoint (each has its own secret)

        for ep in endpoints:
            sig = sign_payload(ep.secret, timestamp, body)
            headers = {
                "Content-Type": "application/json",
                "X-SL-Event": event,
                "X-SL-Timestamp": timestamp,
                "X-SL-Signature": sig,
            }
            ok = False
            for delay in (0.0,) + RETRY_DELAYS_S:
                if delay:
                    await asyncio.sleep(delay)
                if await _deliver_once(ep.url, headers, body):
                    ok = True
                    break
            if ok:
                delivered += 1
            else:
                logger.error(
                    "Webhook endpoint %s exhausted retries for %s — dropping delivery.",
                    ep.id, event,
                )
        return delivered
    except Exception:
        logger.exception("Webhook dispatch failed for user %s event %s", user_id, event)
        return delivered


def fire_and_forget(user_id: str, event: str, payload: dict) -> None:
    """
    Schedule dispatch on the current event loop without blocking the caller.
    Opens its own DB session — safe to call from worker code paths.
    """
    async def _run() -> None:
        try:
            from suspensionlab.backend.database.core import SessionLocal
            async with SessionLocal() as db:
                await dispatch_event(db, user_id, event, payload)
        except Exception:
            logger.exception("fire_and_forget webhook dispatch failed")

    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_run())
    except RuntimeError:
        logger.warning("fire_and_forget: no running event loop; webhook skipped.")
