"""
aegis-pm / api / websocket.py

Production WebSocket endpoint for realtime notifications.

Authentication model (hardened)
───────────────────────────────
  1. Client opens:        ws://host/ws            (NO token in URL)
  2. Server accepts:      ws.accept()             (transport-only)
  3. Client sends:        {"type":"auth","token":"<jwt>"}  within AUTH_TIMEOUT
  4. Server validates:    JWT signature + expiry + session-row not revoked
  5. Server replies:      {"type":"ready",...}    on success, else close 4401
  6. Server subscribes:   user:<id> + admin:all (if admin) and pumps events

Rationale for dropping `?token=`:
  - WS URLs are sometimes logged by proxies / access logs / browser history.
  - Sensitive data in query strings is the #1 accidental token leak.
  - First-message auth is the same pattern used by Phoenix/Actioncable/
    socket.io, and matches OWASP WebSocket guidance.

Log hygiene:
  - The JWT is NEVER logged. We log `user_id` and `role` only after auth.
  - A connection that times out or fails auth logs IP + reason only.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Optional

import sqlalchemy as sa
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from api.auth import decode_token
from api.models import user_sessions_table, users_table
from api.pubsub import admin_channel, broker, user_channel

log = logging.getLogger("aegis.ws")

router = APIRouter()

# ── Config ────────────────────────────────────────────────────────────────────

# Custom close codes (WebSocket RFC 6455 allows 4000–4999 for app use).
WS_CLOSE_UNAUTHENTICATED = 4401
WS_CLOSE_AUTH_TIMEOUT    = 4408
WS_CLOSE_MALFORMED       = 4400
WS_CLOSE_POLICY          = 4403

AUTH_TIMEOUT_SECONDS = float(os.getenv("WS_AUTH_TIMEOUT", "5"))
MAX_AUTH_MESSAGE_BYTES = 4 * 1024   # 4 KB cap so a giant payload can't DOS

# ── Helpers ──────────────────────────────────────────────────────────────────

def _peer(ws: WebSocket) -> str:
    """Client address for logging — never include tokens."""
    try:
        return f"{ws.client.host}:{ws.client.port}"
    except Exception:
        return "unknown"


async def _resolve_user(token: str) -> Optional[dict]:
    """Return user dict iff JWT is valid AND session row is active, else None."""
    try:
        payload = decode_token(token)
    except Exception:
        return None

    try:
        user_id = int(payload["sub"])
        jti     = payload["jti"]
    except (KeyError, ValueError):
        return None

    from api.main import SessionLocal
    async with SessionLocal() as db:
        session_row = (
            await db.execute(
                sa.select(user_sessions_table).where(
                    user_sessions_table.c.jti == jti,
                    user_sessions_table.c.revoked.is_(False),
                )
            )
        ).mappings().first()
        if not session_row:
            return None

        user_row = (
            await db.execute(sa.select(users_table).where(users_table.c.id == user_id))
        ).mappings().first()
        if not user_row or not user_row["is_active"]:
            return None
        return dict(user_row)


async def _authenticate(ws: WebSocket) -> Optional[dict]:
    """
    Wait for the first inbound message; require {"type":"auth","token":...}.
    Returns the user dict on success, or None (caller must close).
    """
    try:
        raw = await asyncio.wait_for(ws.receive_text(), timeout=AUTH_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        log.info("WS auth timeout from %s", _peer(ws))
        await ws.close(code=WS_CLOSE_AUTH_TIMEOUT, reason="auth timeout")
        return None
    except WebSocketDisconnect:
        return None

    if len(raw) > MAX_AUTH_MESSAGE_BYTES:
        await ws.close(code=WS_CLOSE_MALFORMED, reason="oversized auth")
        return None

    try:
        msg = json.loads(raw)
    except json.JSONDecodeError:
        await ws.close(code=WS_CLOSE_MALFORMED, reason="bad json")
        return None

    if not isinstance(msg, dict) or msg.get("type") != "auth":
        await ws.close(code=WS_CLOSE_MALFORMED, reason="expected auth frame")
        return None

    token = msg.get("token")
    if not isinstance(token, str) or not token:
        await ws.close(code=WS_CLOSE_UNAUTHENTICATED, reason="missing token")
        return None

    user = await _resolve_user(token)
    # Deliberately do not log the token OR its tail — just the outcome.
    if not user:
        log.info("WS auth rejected from %s", _peer(ws))
        await ws.close(code=WS_CLOSE_UNAUTHENTICATED, reason="unauthenticated")
        return None

    return user


# ── Endpoint ─────────────────────────────────────────────────────────────────

@router.websocket("/ws")
async def ws_notifications(ws: WebSocket):
    await ws.accept()

    user = await _authenticate(ws)
    if not user:
        return  # close already issued

    await ws.send_json({
        "type": "ready",
        "payload": {"user_id": user["user_id"], "role": user["role"]},
    })
    log.info("WS connected user=%s role=%s from=%s", user["user_id"], user["role"], _peer(ws))

    channels = [user_channel(user["id"])]
    if user["role"] == "admin":
        channels.append(admin_channel())

    tasks: list[asyncio.Task] = []

    async def pump(channel: str):
        try:
            async for event in broker.subscribe(channel):
                await ws.send_json(event)
        except Exception as e:
            log.debug("WS pump closed (%s): %s", channel, e)

    try:
        for ch in channels:
            tasks.append(asyncio.create_task(pump(ch)))

        # Inbound loop (client ping + disconnect detection).
        while True:
            msg = await ws.receive_text()
            if msg == "ping":
                await ws.send_text("pong")
            # Silently ignore everything else — no commands over WS.

    except WebSocketDisconnect:
        log.info("WS disconnect user=%s", user["user_id"])
    except Exception as e:
        log.warning("WS error user=%s: %s", user["user_id"], type(e).__name__)
    finally:
        for t in tasks:
            t.cancel()
        for t in tasks:
            try:
                await t
            except asyncio.CancelledError:
                pass
