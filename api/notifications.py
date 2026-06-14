"""
aegis-pm / api / notifications.py

In-app notifications: persist to Postgres and fan out over Redis pub/sub
so every connected WebSocket for that user/admin sees it immediately.

Public API:
  await notify(db, user_id, kind, title, body=..., resource_type=..., resource_id=..., actor_user_id=...)
  await notify_admins(db, kind, title, body=..., ...)

REST endpoints (mounted from api.main):
  GET    /notifications            list mine (paginated, ?unread=true optional)
  POST   /notifications/{id}/read  mark one read
  POST   /notifications/read-all   mark all mine read
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Literal, Optional

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import get_current_user
from api.models import notifications_table, users_table
from api.pubsub import publish_to_admins, publish_to_user

log = logging.getLogger("aegis.notifications")

NotificationKind = Literal[
    "task_assigned",
    "task_update",
    "task_completed",
    "alert_new",
    "system",
]


class NotificationOut(BaseModel):
    id:            int
    user_id:       int
    kind:          str
    title:         str
    body:          Optional[str]
    resource_type: Optional[str]
    resource_id:   Optional[int]
    actor_user_id: Optional[int]
    read_at:       Optional[datetime]
    created_at:    datetime

    class Config:
        from_attributes = True


# ── Core emit ────────────────────────────────────────────────────────────────

async def notify(
    db: AsyncSession,
    user_id: int,
    kind: NotificationKind,
    title: str,
    body: str | None = None,
    resource_type: str | None = None,
    resource_id: int | None = None,
    actor_user_id: int | None = None,
) -> dict:
    """Persist a notification row and publish to the user's channel."""
    result = await db.execute(
        notifications_table.insert()
        .values(
            user_id=user_id,
            kind=kind,
            title=title,
            body=body,
            resource_type=resource_type,
            resource_id=resource_id,
            actor_user_id=actor_user_id,
        )
        .returning(notifications_table)
    )
    await db.commit()
    row = dict(result.mappings().first())

    await publish_to_user(
        user_id,
        {"type": "notification", "payload": _serialize(row)},
    )
    return row


async def notify_admins(
    db: AsyncSession,
    kind: NotificationKind,
    title: str,
    body: str | None = None,
    resource_type: str | None = None,
    resource_id: int | None = None,
    actor_user_id: int | None = None,
) -> None:
    """
    Fan notification to every admin.

    Performance model
    ─────────────────
      Before:  N admins ⇒ N round-trips to Postgres (INSERT each) + N pub/sub
               publishes. At 10k admins this was O(10k) statements and
               O(10k) Redis PUBLISHes per event.
      Now:     one INSERT … SELECT drives the fan-out entirely inside the
               database (zero round-trips per admin) and one Redis PUBLISH
               on `admin:all` — the WS layer already subscribes every admin
               connection to that channel, so one publish reaches all
               connected admins. The per-user PUBLISH loop is gone.

    Scale-out path (10k → 1M):
      - Keep the INSERT … SELECT (Postgres fan-out scales linearly, ~100k
        rows/s on a modest box). If that becomes hot, partition
        `notifications` by user_id and/or move admin-inbox writes onto a
        background queue (RQ / Celery / NATS / Kafka).
      - Replace Redis pub/sub with Kafka (partition by user_id) only when
        you need durability + replay for offline admins. Redis fire-and-
        forget is correct for live-connected dashboards.
    """
    # Single round-trip, single statement — server-side fan-out.
    cols = notifications_table.c
    insert_select = sa.insert(notifications_table).from_select(
        [
            cols.user_id, cols.kind, cols.title, cols.body,
            cols.resource_type, cols.resource_id, cols.actor_user_id,
        ],
        sa.select(
            users_table.c.id,
            sa.literal(kind).label("kind"),
            sa.literal(title).label("title"),
            sa.literal(body).label("body"),
            sa.literal(resource_type).label("resource_type"),
            sa.literal(resource_id).label("resource_id"),
            sa.literal(actor_user_id).label("actor_user_id"),
        ).where(
            users_table.c.role == "admin",
            users_table.c.is_active.is_(True),
        ),
    )
    await db.execute(insert_select)
    await db.commit()

    # Single publish on the shared channel. Every admin's live WebSocket is
    # already subscribed to admin:all — O(1) work per event, independent of
    # how many admins exist.
    await publish_to_admins({
        "type": "admin_notification",
        "payload": {
            "kind":          kind,
            "title":         title,
            "body":          body,
            "resource_type": resource_type,
            "resource_id":   resource_id,
            "actor_user_id": actor_user_id,
        },
    })


def _serialize(row: dict) -> dict:
    out = dict(row)
    for k, v in list(out.items()):
        if isinstance(v, datetime):
            out[k] = v.isoformat()
    return out


# ── REST endpoints ───────────────────────────────────────────────────────────

router = APIRouter(prefix="/notifications", tags=["Notifications"])


@router.get("", response_model=list[NotificationOut])
async def list_mine(
    user:   dict = Depends(get_current_user),
    unread: bool = Query(False, description="Only unread if true"),
    limit:  int  = Query(50, ge=1, le=200),
):
    from api.main import SessionLocal
    async with SessionLocal() as db:
        q = sa.select(notifications_table).where(
            notifications_table.c.user_id == user["id"]
        )
        if unread:
            q = q.where(notifications_table.c.read_at.is_(None))
        q = q.order_by(notifications_table.c.created_at.desc()).limit(limit)
        rows = (await db.execute(q)).mappings().all()
    return [NotificationOut(**dict(r)) for r in rows]


@router.post("/{notif_id}/read")
async def mark_read(notif_id: int, user: dict = Depends(get_current_user)):
    from api.main import SessionLocal
    async with SessionLocal() as db:
        result = await db.execute(
            notifications_table.update()
            .where(
                notifications_table.c.id == notif_id,
                notifications_table.c.user_id == user["id"],
                notifications_table.c.read_at.is_(None),
            )
            .values(read_at=datetime.now(timezone.utc))
        )
        await db.commit()
        if result.rowcount == 0:
            raise HTTPException(404, "Notification not found or already read")
    return {"ok": True}


@router.post("/read-all")
async def mark_all_read(user: dict = Depends(get_current_user)):
    from api.main import SessionLocal
    async with SessionLocal() as db:
        result = await db.execute(
            notifications_table.update()
            .where(
                notifications_table.c.user_id == user["id"],
                notifications_table.c.read_at.is_(None),
            )
            .values(read_at=datetime.now(timezone.utc))
        )
        await db.commit()
    return {"ok": True, "marked": result.rowcount}


@router.get("/unread-count")
async def unread_count(user: dict = Depends(get_current_user)):
    from api.main import SessionLocal
    async with SessionLocal() as db:
        n = (
            await db.execute(
                sa.select(sa.func.count())
                .select_from(notifications_table)
                .where(
                    notifications_table.c.user_id == user["id"],
                    notifications_table.c.read_at.is_(None),
                )
            )
        ).scalar_one()
    return {"count": n}
