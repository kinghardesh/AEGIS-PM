"""
aegis-pm / api / activity.py

Activity monitoring:

  - log_activity(request, action, status, meta=...) writes to activity_log.
  - A middleware automatically logs every mutating, authenticated request
    so admins get a full audit trail without every handler having to call
    log_activity() manually.
  - GET /activity                  — admin-only feed
  - GET /activity/sessions         — admin-only list of active user sessions
  - POST /activity/sessions/{id}/revoke  — admin-only device revoke

The middleware is purposely conservative: it only logs successful
state-changing requests made by authenticated users. Read-only GETs do not
flood the log.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.middleware.base import BaseHTTPMiddleware

from api.auth import require_admin
from api.models import activity_log_table, user_sessions_table, users_table

log = logging.getLogger("aegis.activity")

_LOGGED_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
_SKIP_PATHS = {"/auth/login", "/auth/logout"}  # logged explicitly below


class ActivityOut(BaseModel):
    id:          int
    user_id:     Optional[int]
    user_handle: Optional[str]
    session_id:  Optional[int]
    action:      str
    method:      Optional[str]
    path:        Optional[str]
    status_code: Optional[int]
    ip_address:  Optional[str]
    user_agent:  Optional[str]
    created_at:  datetime


async def log_activity(
    db: AsyncSession,
    *,
    user_id: int | None,
    session_id: int | None,
    action: str,
    method: str | None = None,
    path: str | None = None,
    status_code: int | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    meta: dict | None = None,
) -> None:
    await db.execute(
        activity_log_table.insert().values(
            user_id=user_id,
            session_id=session_id,
            action=action,
            method=method,
            path=(path or "")[:255] or None,
            status_code=status_code,
            ip_address=ip_address,
            user_agent=(user_agent or "")[:500] or None,
            meta=meta,
        )
    )
    await db.commit()


class ActivityMiddleware(BaseHTTPMiddleware):
    """
    Automatic logger for mutating requests by authenticated users.

    Runs AFTER the route handler so we know the final status code and have
    a `request.state.user` populated by `get_current_user` (if used).
    """

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)

        try:
            user = getattr(request.state, "user", None)
            if user and request.method in _LOGGED_METHODS and request.url.path not in _SKIP_PATHS:
                from api.main import SessionLocal
                async with SessionLocal() as db:
                    await log_activity(
                        db,
                        user_id=user.get("id"),
                        session_id=user.get("session_id"),
                        action=f"{request.method} {request.url.path}",
                        method=request.method,
                        path=request.url.path,
                        status_code=response.status_code,
                        ip_address=request.client.host if request.client else None,
                        user_agent=request.headers.get("user-agent", "")[:500] or None,
                    )
        except Exception as e:
            log.warning("activity log failed: %s", e)

        return response


# ── Admin routes ─────────────────────────────────────────────────────────────

router = APIRouter(prefix="/activity", tags=["Activity"])


@router.get("", response_model=list[ActivityOut])
async def feed(
    _admin: dict = Depends(require_admin),
    user_id: Optional[int] = Query(None, description="Filter to one user"),
    action:  Optional[str] = Query(None, description="Partial action match"),
    since_hours: int = Query(24, ge=1, le=24 * 30),
    limit: int = Query(100, ge=1, le=500),
):
    """
    Admin-only feed of user actions across all devices.
    """
    from api.main import SessionLocal
    cutoff = datetime.now(timezone.utc) - timedelta(hours=since_hours)

    async with SessionLocal() as db:
        a = activity_log_table
        u = users_table
        q = (
            sa.select(
                a.c.id,
                a.c.user_id,
                u.c.user_id.label("user_handle"),
                a.c.session_id,
                a.c.action,
                a.c.method,
                a.c.path,
                a.c.status_code,
                a.c.ip_address,
                a.c.user_agent,
                a.c.created_at,
            )
            .select_from(a.outerjoin(u, u.c.id == a.c.user_id))
            .where(a.c.created_at >= cutoff)
        )
        if user_id:
            q = q.where(a.c.user_id == user_id)
        if action:
            q = q.where(a.c.action.ilike(f"%{action}%"))
        q = q.order_by(a.c.created_at.desc()).limit(limit)
        rows = (await db.execute(q)).mappings().all()

    return [ActivityOut(**dict(r)) for r in rows]


@router.get("/sessions")
async def active_sessions(_admin: dict = Depends(require_admin)):
    """List every non-revoked session across all users."""
    from api.main import SessionLocal
    async with SessionLocal() as db:
        s = user_sessions_table
        u = users_table
        rows = (
            await db.execute(
                sa.select(
                    s.c.id,
                    s.c.user_id,
                    u.c.user_id.label("user_handle"),
                    u.c.role,
                    s.c.device,
                    s.c.ip_address,
                    s.c.created_at,
                    s.c.last_seen_at,
                    s.c.expires_at,
                )
                .select_from(s.join(u, u.c.id == s.c.user_id))
                .where(s.c.revoked.is_(False))
                .order_by(s.c.last_seen_at.desc())
            )
        ).mappings().all()
    return [dict(r) for r in rows]


@router.post("/sessions/{session_id}/revoke")
async def revoke_session(session_id: int, _admin: dict = Depends(require_admin)):
    from api.main import SessionLocal
    async with SessionLocal() as db:
        result = await db.execute(
            user_sessions_table.update()
            .where(user_sessions_table.c.id == session_id)
            .values(revoked=True)
        )
        await db.commit()
        if result.rowcount == 0:
            raise HTTPException(404, "Session not found")
    return {"ok": True}
