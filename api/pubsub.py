"""
aegis-pm / api / pubsub.py

Redis pub/sub broker for the realtime notification fan-out.

Why pub/sub instead of direct WebSocket broadcast:
  With >1 FastAPI worker (uvicorn --workers 4, or horizontal pods), each
  worker owns a subset of WebSocket connections. When worker A emits a
  notification, workers B/C/D must also see it so their connected clients
  get delivery. Redis pub/sub is the industry-standard broker for this —
  channels are cheap, delivery is at-most-once (fine for notifications),
  and no message storage is needed because the notification row is already
  persisted in Postgres.

Channel scheme:
  user:<user_id>   one channel per user; every WS connection for that user
                   subscribes on connect and unsubscribes on disconnect.
  admin:all        admins subscribe here for system-wide events.

Fallback:
  If Redis is unreachable (e.g. local dev without `redis` running) we fall
  back to an in-process asyncio broadcaster. Single-worker dev still works;
  multi-worker prod needs Redis.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from collections import defaultdict
from typing import AsyncIterator, Callable, Optional

log = logging.getLogger("aegis.pubsub")

try:
    import redis.asyncio as aioredis  # type: ignore
except ImportError:
    aioredis = None  # type: ignore


# ── In-process fallback ──────────────────────────────────────────────────────

class _InProcessBroker:
    def __init__(self) -> None:
        self._subs: dict[str, set[asyncio.Queue]] = defaultdict(set)

    async def publish(self, channel: str, message: dict) -> None:
        for q in list(self._subs.get(channel, [])):
            try:
                q.put_nowait(message)
            except asyncio.QueueFull:
                pass

    async def subscribe(self, channel: str) -> AsyncIterator[dict]:
        q: asyncio.Queue = asyncio.Queue(maxsize=256)
        self._subs[channel].add(q)
        try:
            while True:
                yield await q.get()
        finally:
            self._subs[channel].discard(q)


# ── Redis-backed broker ──────────────────────────────────────────────────────

class _RedisBroker:
    def __init__(self, url: str) -> None:
        self._url   = url
        self._conn: Optional["aioredis.Redis"] = None  # type: ignore

    async def _client(self) -> "aioredis.Redis":  # type: ignore
        if self._conn is None:
            self._conn = aioredis.from_url(self._url, decode_responses=True)
        return self._conn

    async def publish(self, channel: str, message: dict) -> None:
        r = await self._client()
        await r.publish(channel, json.dumps(message, default=str))

    async def subscribe(self, channel: str) -> AsyncIterator[dict]:
        r = await self._client()
        pubsub = r.pubsub()
        await pubsub.subscribe(channel)
        try:
            async for raw in pubsub.listen():
                if raw.get("type") != "message":
                    continue
                data = raw.get("data")
                if not data:
                    continue
                try:
                    yield json.loads(data)
                except Exception as e:
                    log.warning("pubsub: bad payload on %s: %s", channel, e)
        finally:
            try:
                await pubsub.unsubscribe(channel)
                await pubsub.close()
            except Exception:
                pass


# ── Broker instance ──────────────────────────────────────────────────────────

def _build_broker():
    url = os.getenv("REDIS_URL", "").strip()
    if url and aioredis is not None:
        log.info("pubsub: using Redis at %s", url)
        return _RedisBroker(url)
    if aioredis is None:
        log.warning("pubsub: redis package missing — using in-process broker (single-worker only)")
    else:
        log.warning("pubsub: REDIS_URL not set — using in-process broker (single-worker only)")
    return _InProcessBroker()


broker = _build_broker()


# ── Public helpers ───────────────────────────────────────────────────────────

def user_channel(user_id: int) -> str:
    return f"user:{user_id}"


def admin_channel() -> str:
    return "admin:all"


async def publish_to_user(user_id: int, event: dict) -> None:
    await broker.publish(user_channel(user_id), event)


async def publish_to_admins(event: dict) -> None:
    await broker.publish(admin_channel(), event)
