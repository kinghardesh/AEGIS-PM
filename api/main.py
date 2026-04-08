"""
aegis-pm / api / main.py

Aegis PM – FastAPI backend (production-grade).

Endpoints
─────────
  System
    GET  /health                         liveness probe
    GET  /stats                          alert counts by status

  Alerts – CRUD
    GET  /alerts                         list with filters + pagination
    POST /alerts                         create (called by Monitor Agent)
    GET  /alerts/{id}                    single alert

  Alerts – State transitions
    POST /alerts/{id}/approve            pending  → approved   (human HITL)
    POST /alerts/{id}/dismiss            pending  → dismissed  (human HITL)
    POST /alerts/{id}/notified           approved → notified   (Communicator Agent)
    POST /alerts/{id}/reopen             dismissed/notified → pending  (human re-triage)

  Alerts – Bulk actions
    POST /alerts/bulk/approve            approve a list of IDs at once
    POST /alerts/bulk/dismiss            dismiss a list of IDs at once

  Audit log
    GET  /alerts/{id}/history            full state-change history for one alert

Design decisions
────────────────
  - Async SQLAlchemy (asyncpg) throughout – no sync DB calls on the event loop
  - All state transitions validated server-side – can't double-approve, etc.
  - Audit trail written atomically with every state change
  - Pagination via `limit` + `offset` query params (cursor pagination can be
    added later without breaking the response shape)
  - Structured logging: every request logs method + path + status + duration
  - CORS permissive for development; tighten CORS_ORIGINS in production
"""
from __future__ import annotations

import os
import time
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from typing import List, Optional, Literal

from fastapi import FastAPI, HTTPException, Depends, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import (
    create_async_engine,
    AsyncSession,
    async_sessionmaker,
)
from dotenv import load_dotenv

load_dotenv()

from api.security import require_agent_key, require_admin_key, rate_limit, inject_request_id

# ── Logging ───────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("aegis.api")

# ── Constants ─────────────────────────────────────────────────────────────────

VALID_STATUSES = {"pending", "approved", "dismissed", "notified"}

# State machine: which transitions are legal
_TRANSITIONS: dict[str, set[str]] = {
    "pending":   {"approved", "dismissed"},
    "approved":  {"notified", "pending"},    # reopen from approved too
    "dismissed": {"pending"},                # reopen
    "notified":  {"pending"},                # reopen
}

# ── Database ──────────────────────────────────────────────────────────────────

def _dsn() -> str:
    # Render provides a single DATABASE_URL; fall back to individual vars for local dev.
    url = os.environ.get("DATABASE_URL") or os.environ.get("DATABASE_URI")
    if url:
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return url
    return (
        "postgresql+asyncpg://"
        f"{os.environ['POSTGRES_USER']}:{os.environ['POSTGRES_PASSWORD']}"
        f"@{os.environ.get('POSTGRES_HOST', 'postgres')}:"
        f"{os.environ.get('POSTGRES_PORT', '5432')}/"
        f"{os.environ['POSTGRES_DB']}"
    )


engine       = create_async_engine(_dsn(), echo=False, pool_pre_ping=True, pool_size=10)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
metadata     = sa.MetaData()

# ── Table definitions ─────────────────────────────────────────────────────────

alerts_table = sa.Table(
    "alerts",
    metadata,
    sa.Column("id",             sa.Integer,                  primary_key=True),
    sa.Column("task_key",       sa.String(64),               nullable=False),
    sa.Column("task_summary",   sa.Text),
    sa.Column("assignee",       sa.String(255),              nullable=False),
    sa.Column("assignee_email", sa.String(255)),
    sa.Column("jira_url",       sa.Text),
    sa.Column("last_updated",   sa.DateTime(timezone=True)),
    sa.Column("detected_at",    sa.DateTime(timezone=True),  server_default=sa.func.now()),
    sa.Column("status",         sa.String(32),               server_default="pending"),
    sa.Column("slack_sent",     sa.Boolean,                  server_default="false"),
    sa.Column("slack_ts",       sa.String(64)),
    sa.Column("notes",          sa.Text),
)

audit_log_table = sa.Table(
    "alert_audit_log",
    metadata,
    sa.Column("id",          sa.Integer,                  primary_key=True),
    sa.Column("alert_id",    sa.Integer,                  nullable=False),
    sa.Column("from_status", sa.String(32)),
    sa.Column("to_status",   sa.String(32),               nullable=False),
    sa.Column("actor",       sa.String(64),               server_default="system"),
    sa.Column("notes",       sa.Text),
    sa.Column("created_at",  sa.DateTime(timezone=True),  server_default=sa.func.now()),
)

# ── New tables: Projects, Employees, Tasks ────────────────────────────────────

projects_table = sa.Table(
    "projects",
    metadata,
    sa.Column("id",          sa.Integer,                  primary_key=True),
    sa.Column("name",        sa.String(255),              nullable=False),
    sa.Column("description", sa.Text),
    sa.Column("prd_text",    sa.Text),
    sa.Column("status",      sa.String(32),               server_default="active"),
    sa.Column("total_tasks", sa.Integer,                  server_default="0"),
    sa.Column("completed_tasks", sa.Integer,              server_default="0"),
    sa.Column("created_at",  sa.DateTime(timezone=True),  server_default=sa.func.now()),
    sa.Column("updated_at",  sa.DateTime(timezone=True),  server_default=sa.func.now()),
)

employees_table = sa.Table(
    "employees",
    metadata,
    sa.Column("id",          sa.Integer,                  primary_key=True),
    sa.Column("name",        sa.String(255),              nullable=False),
    sa.Column("email",       sa.String(255)),
    sa.Column("role",        sa.String(128)),
    sa.Column("skills",      sa.Text),              # JSON array stored as text
    sa.Column("availability",sa.String(32),               server_default="available"),
    sa.Column("current_load",sa.Integer,                  server_default="0"),
    sa.Column("created_at",  sa.DateTime(timezone=True),  server_default=sa.func.now()),
)

tasks_table = sa.Table(
    "tasks",
    metadata,
    sa.Column("id",              sa.Integer,                  primary_key=True),
    sa.Column("project_id",      sa.Integer,                  nullable=False),
    sa.Column("title",           sa.String(500),              nullable=False),
    sa.Column("description",     sa.Text),
    sa.Column("priority",        sa.String(32),               server_default="medium"),
    sa.Column("status",          sa.String(32),               server_default="todo"),
    sa.Column("estimated_hours", sa.Float,                    server_default="0"),
    sa.Column("assigned_to",     sa.Integer),                 # employee_id
    sa.Column("assigned_name",   sa.String(255)),
    sa.Column("ai_confidence",   sa.Float),
    sa.Column("required_skills", sa.Text),             # JSON array
    sa.Column("created_at",      sa.DateTime(timezone=True),  server_default=sa.func.now()),
    sa.Column("completed_at",    sa.DateTime(timezone=True)),
)



@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("Aegis PM API — starting up")
    async with engine.begin() as conn:
        await conn.run_sync(metadata.create_all)   # safety net; init.sql runs first in Docker
    yield
    log.info("Aegis PM API — shutting down")
    await engine.dispose()

# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Aegis PM API",
    description=(
        "HITL alert management backend for the Aegis autonomous project manager.\n\n"
        "Agents (Monitor, Communicator) and the HITL dashboard all talk through this API."
    ),
    version="0.2.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Mount health router ──────────────────────────────────────────────────────

# if _HEALTH_ROUTER_AVAILABLE and _health_router:
#     app.include_router(_health_router)

# ── Middleware: request logging + timing ──────────────────────────────────────

@app.middleware("http")
async def _log_requests(request: Request, call_next) -> Response:
    import uuid as _uuid
    rid   = request.headers.get("X-Request-ID") or str(_uuid.uuid4())
    start = time.perf_counter()
    response: Response = await call_next(request)
    ms = (time.perf_counter() - start) * 1000
    response.headers["X-Request-ID"] = rid
    log.info(
        "%s %s → %d  (%.1fms)  rid=%s",
        request.method,
        request.url.path,
        response.status_code,
        ms,
        rid[:8],
    )
    return response

# ── Global exception handler ──────────────────────────────────────────────────

@app.exception_handler(Exception)
async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
    log.exception("Unhandled exception on %s %s: %s", request.method, request.url.path, exc)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "type": type(exc).__name__},
    )

# ── DB dependency ─────────────────────────────────────────────────────────────

async def get_db():
    async with SessionLocal() as session:
        yield session

# ══════════════════════════════════════════════════════════════════════════════
#  Pydantic schemas
# ══════════════════════════════════════════════════════════════════════════════

class AlertOut(BaseModel):
    id:             int
    task_key:       str
    task_summary:   Optional[str]
    assignee:       str
    assignee_email: Optional[str]
    jira_url:       Optional[str]
    last_updated:   Optional[datetime]
    detected_at:    datetime
    status:         str
    slack_sent:     bool
    slack_ts:       Optional[str]
    notes:          Optional[str]

    class Config:
        from_attributes = True


class AlertCreate(BaseModel):
    task_key:       str             = Field(..., min_length=1, max_length=64)
    task_summary:   Optional[str]  = None
    assignee:       str             = Field(..., min_length=1, max_length=255)
    assignee_email: Optional[str]  = None
    jira_url:       Optional[str]  = None
    last_updated:   Optional[datetime] = None

    @field_validator("task_key")
    @classmethod
    def task_key_upper(cls, v: str) -> str:
        return v.strip().upper()


class ActionRequest(BaseModel):
    notes: Optional[str] = Field(None, max_length=1000)
    actor: str           = Field("human", max_length=64)  # who performed the action


class BulkActionRequest(BaseModel):
    ids:   List[int]     = Field(..., min_length=1, max_length=100)
    notes: Optional[str] = Field(None, max_length=1000)
    actor: str           = Field("human", max_length=64)


class AlertStats(BaseModel):
    pending:   int
    approved:  int
    notified:  int
    dismissed: int
    total:     int


class AuditEntry(BaseModel):
    id:          int
    alert_id:    int
    from_status: Optional[str]
    to_status:   str
    actor:       str
    notes:       Optional[str]
    created_at:  datetime

    class Config:
        from_attributes = True


class PaginatedAlerts(BaseModel):
    items:  List[AlertOut]
    total:  int
    limit:  int
    offset: int


# ══════════════════════════════════════════════════════════════════════════════
#  Internal helpers
# ══════════════════════════════════════════════════════════════════════════════

async def _fetch_or_404(alert_id: int, db: AsyncSession):
    result = await db.execute(
        sa.select(alerts_table).where(alerts_table.c.id == alert_id)
    )
    row = result.mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")
    return row


async def _transition(
    alert_id:    int,
    to_status:   str,
    db:          AsyncSession,
    actor:       str = "system",
    notes:       Optional[str] = None,
    extra_values: Optional[dict] = None,
) -> dict:
    """
    Atomically transition an alert's status and write an audit log entry.

    Raises 404 if alert doesn't exist.
    Raises 400 if the transition is illegal per the state machine.
    Returns the updated alert row as a dict.
    """
    row = await _fetch_or_404(alert_id, db)
    current = row["status"]

    allowed = _TRANSITIONS.get(current, set())
    if to_status not in allowed:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Cannot transition alert {alert_id} from '{current}' to '{to_status}'. "
                f"Allowed targets from '{current}': {sorted(allowed) or 'none'}"
            ),
        )

    # Update alert
    update_vals = {"status": to_status, "notes": notes}
    if extra_values:
        update_vals.update(extra_values)

    await db.execute(
        alerts_table.update()
        .where(alerts_table.c.id == alert_id)
        .values(**update_vals)
    )

    # Audit log entry
    await db.execute(
        audit_log_table.insert().values(
            alert_id=alert_id,
            from_status=current,
            to_status=to_status,
            actor=actor,
            notes=notes,
        )
    )

    await db.commit()
    log.info(
        "Alert %d: %s → %s  (actor=%s)",
        alert_id, current, to_status, actor,
    )
    return dict(await _fetch_or_404(alert_id, db))


# ══════════════════════════════════════════════════════════════════════════════
#  Routes – System
# ══════════════════════════════════════════════════════════════════════════════

@app.get(
    "/health",
    summary="Liveness probe",
    tags=["System"],
)
async def health(db: AsyncSession = Depends(get_db)):
    """
    Returns 200 + DB connectivity status.
    Used by Docker Compose healthcheck and load balancers.
    """
    try:
        await db.execute(sa.text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False

    return {
        "status": "ok" if db_ok else "degraded",
        "service": "aegis-pm-api",
        "version": "0.2.0",
        "database": "connected" if db_ok else "unreachable",
    }


@app.get(
    "/stats",
    response_model=AlertStats,
    summary="Alert counts by status",
    tags=["System"],
)
async def get_stats(db: AsyncSession = Depends(get_db)):
    """
    Returns a summary count of alerts per status.
    Used by the HITL dashboard stat cards.
    """
    result = await db.execute(
        sa.select(
            alerts_table.c.status,
            sa.func.count().label("count"),
        ).group_by(alerts_table.c.status)
    )
    counts = {row.status: row.count for row in result}
    total = sum(counts.values())
    return AlertStats(
        pending=counts.get("pending", 0),
        approved=counts.get("approved", 0),
        notified=counts.get("notified", 0),
        dismissed=counts.get("dismissed", 0),
        total=total,
    )


# ══════════════════════════════════════════════════════════════════════════════
#  Routes – Alerts CRUD
# ══════════════════════════════════════════════════════════════════════════════

@app.get(
    "/alerts",
    response_model=PaginatedAlerts,
    summary="List alerts with filters and pagination",
    tags=["Alerts"],
)
async def list_alerts(
    _auth: str = Depends(require_agent_key),
    _rl: None = Depends(rate_limit),
    # ── Filters ──────────────────────────────────────────────────────────────
    status:   Optional[str]  = Query(None, description="Filter by status: pending | approved | notified | dismissed"),
    assignee: Optional[str]  = Query(None, description="Filter by assignee name (partial match, case-insensitive)"),
    task_key: Optional[str]  = Query(None, description="Filter by Jira task key (partial match)"),
    slack_sent: Optional[bool] = Query(None, description="Filter by whether Slack was sent"),
    detected_after:  Optional[datetime] = Query(None, description="Detected at or after this datetime (ISO 8601)"),
    detected_before: Optional[datetime] = Query(None, description="Detected at or before this datetime (ISO 8601)"),
    # ── Sorting ───────────────────────────────────────────────────────────────
    order_by: Literal["detected_at", "last_updated", "status", "assignee"] = Query(
        "detected_at", description="Field to sort by"
    ),
    order_dir: Literal["asc", "desc"] = Query("desc", description="Sort direction"),
    # ── Pagination ────────────────────────────────────────────────────────────
    limit:  int = Query(50,  ge=1, le=500, description="Max items to return"),
    offset: int = Query(0,   ge=0,         description="Items to skip"),
    db: AsyncSession = Depends(get_db),
):
    """
    Returns a paginated list of alerts with optional filters.

    **Filters** can be combined freely. All filters are AND-ed together.

    **Pagination**: use `limit` + `offset`. The response includes `total`
    (unfiltered count with these filters applied) so the frontend can
    calculate page count.

    **Sorting**: default is newest first (`detected_at desc`).
    """
    if status and status not in VALID_STATUSES:
        raise HTTPException(
            400,
            detail=f"Invalid status '{status}'. Valid: {sorted(VALID_STATUSES)}",
        )

    col = alerts_table.c

    # ── Build WHERE clauses ────────────────────────────────────────────────────
    conditions = []
    if status:
        conditions.append(col.status == status)
    if assignee:
        conditions.append(col.assignee.ilike(f"%{assignee}%"))
    if task_key:
        conditions.append(col.task_key.ilike(f"%{task_key}%"))
    if slack_sent is not None:
        conditions.append(col.slack_sent == slack_sent)
    if detected_after:
        conditions.append(col.detected_at >= detected_after)
    if detected_before:
        conditions.append(col.detected_at <= detected_before)

    where_clause = sa.and_(*conditions) if conditions else sa.true()

    # ── Count total matching rows ──────────────────────────────────────────────
    count_result = await db.execute(
        sa.select(sa.func.count()).select_from(alerts_table).where(where_clause)
    )
    total = count_result.scalar_one()

    # ── Sort column ───────────────────────────────────────────────────────────
    sort_col  = getattr(col, order_by)
    sort_expr = sort_col.desc() if order_dir == "desc" else sort_col.asc()

    # ── Fetch page ────────────────────────────────────────────────────────────
    rows_result = await db.execute(
        sa.select(alerts_table)
        .where(where_clause)
        .order_by(sort_expr)
        .limit(limit)
        .offset(offset)
    )
    rows = rows_result.mappings().all()

    return PaginatedAlerts(
        items=[dict(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@app.post(
    "/alerts",
    response_model=AlertOut,
    status_code=201,
    summary="Create a new stale-task alert",
    tags=["Alerts"],
)
async def create_alert(
    payload: AlertCreate,
    db: AsyncSession = Depends(get_db),
    _auth: str = Depends(require_agent_key),
    _rl: None = Depends(rate_limit),
):
    """
    Called by the **Monitor Agent** when it finds a stale Jira task.

    **Idempotent**: if a `pending` alert already exists for the same
    `task_key`, the existing alert is returned without creating a duplicate.
    The HTTP status is still 201 to keep agent logic simple.
    """
    # Deduplicate: only one pending alert per task at a time
    existing_result = await db.execute(
        sa.select(alerts_table).where(
            alerts_table.c.task_key == payload.task_key,
            alerts_table.c.status == "pending",
        )
    )
    existing_row = existing_result.mappings().first()
    if existing_row:
        log.info("Duplicate suppressed – pending alert already exists for %s", payload.task_key)
        return dict(existing_row)

    ins_result = await db.execute(
        alerts_table.insert()
        .values(**payload.model_dump())
        .returning(alerts_table)
    )
    await db.commit()
    row = ins_result.mappings().first()

    # Write initial audit entry
    await db.execute(
        audit_log_table.insert().values(
            alert_id=row["id"],
            from_status=None,
            to_status="pending",
            actor="monitor_agent",
            notes=f"Detected stale task {payload.task_key}",
        )
    )
    await db.commit()

    log.info("Alert created: id=%d  task=%s  assignee=%s", row["id"], row["task_key"], row["assignee"])
    return dict(row)


@app.get(
    "/alerts/{alert_id}",
    response_model=AlertOut,
    summary="Get a single alert",
    tags=["Alerts"],
)
async def get_alert(
    alert_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Returns a single alert by ID. Raises 404 if not found."""
    row = await _fetch_or_404(alert_id, db)
    return dict(row)


# ══════════════════════════════════════════════════════════════════════════════
#  Routes – State transitions
# ══════════════════════════════════════════════════════════════════════════════

@app.post(
    "/alerts/{alert_id}/approve",
    response_model=AlertOut,
    summary="Approve a pending alert",
    tags=["Alerts – Actions"],
)
async def approve_alert(
    alert_id: int,
    body: ActionRequest = ActionRequest(),
    db: AsyncSession = Depends(get_db),
    _auth: str = Depends(require_admin_key),
    _rl: None = Depends(rate_limit),
):
    """
    **Human HITL action.** Approves a `pending` alert.

    After approval the **Communicator Agent** will pick it up on its next
    30-second cycle and send a Slack message to the task assignee.

    State machine: `pending → approved`

    Returns 400 if the alert is not currently `pending`.
    """
    result = await _transition(
        alert_id=alert_id,
        to_status="approved",
        db=db,
        actor=body.actor,
        notes=body.notes,
    )
    # Side effect: move the linked internal task to "in_progress" so it shows
    # up on the team's active list. The alert task_key looks like "TASK-103";
    # the trailing number is the internal task id for alerts created via
    # /alerts/generate-from-tasks.
    try:
        alert_row = (
            await db.execute(sa.select(alerts_table).where(alerts_table.c.id == alert_id))
        ).mappings().first()
        if alert_row and alert_row["task_key"]:
            import re
            m = re.search(r"(\d+)$", alert_row["task_key"])
            if m:
                task_id = int(m.group(1))
                task_row = (
                    await db.execute(sa.select(tasks_table).where(tasks_table.c.id == task_id))
                ).mappings().first()
                if task_row and task_row["status"] != "in_progress":
                    await db.execute(
                        tasks_table.update()
                        .where(tasks_table.c.id == task_id)
                        .values(status="in_progress")
                    )
                    await db.commit()
                    log.info("Alert %d approval moved task %d to in_progress", alert_id, task_id)
    except Exception as e:
        log.warning("Could not auto-progress task for alert %d: %s", alert_id, e)
    return result


@app.post(
    "/alerts/{alert_id}/dismiss",
    response_model=AlertOut,
    summary="Dismiss a pending alert",
    tags=["Alerts – Actions"],
)
async def dismiss_alert(
    alert_id: int,
    body: ActionRequest = ActionRequest(),
    db: AsyncSession = Depends(get_db),
    _auth: str = Depends(require_admin_key),
    _rl: None = Depends(rate_limit),
):
    """
    **Human HITL action.** Dismisses a `pending` alert.

    No Slack message will be sent. Use this when the alert is a false positive
    or the task already has an offline update.

    State machine: `pending → dismissed`

    Returns 400 if the alert is not currently `pending`.
    """
    return await _transition(
        alert_id=alert_id,
        to_status="dismissed",
        db=db,
        actor=body.actor,
        notes=body.notes,
    )


@app.post(
    "/alerts/{alert_id}/notified",
    response_model=AlertOut,
    summary="Mark alert as notified (Communicator Agent)",
    tags=["Alerts – Actions"],
)
async def mark_notified(
    alert_id: int,
    slack_ts: Optional[str] = Query(None, description="Slack message timestamp for threading"),
    db: AsyncSession = Depends(get_db),
):
    """
    Called by the **Communicator Agent** after a Slack message is sent.

    Sets `slack_sent=True` and records the Slack message timestamp
    (`slack_ts`) for future thread replies.

    State machine: `approved → notified`

    Returns 400 if the alert is not currently `approved`.
    """
    return await _transition(
        alert_id=alert_id,
        to_status="notified",
        db=db,
        actor="communicator_agent",
        notes="Slack notification sent",
        extra_values={"slack_sent": True, "slack_ts": slack_ts},
    )


@app.post(
    "/alerts/{alert_id}/reopen",
    response_model=AlertOut,
    summary="Reopen a dismissed or notified alert",
    tags=["Alerts – Actions"],
)
async def reopen_alert(
    alert_id: int,
    body: ActionRequest = ActionRequest(),
    db: AsyncSession = Depends(get_db),
    _auth: str = Depends(require_admin_key),
    _rl: None = Depends(rate_limit),
):
    """
    **Human HITL action.** Reopens an alert back to `pending`.

    Use when a dismissed alert needs another look, or a notified task
    is still blocked and requires another nudge.

    State machine: `dismissed | notified | approved → pending`

    Returns 400 if already `pending`.
    """
    return await _transition(
        alert_id=alert_id,
        to_status="pending",
        db=db,
        actor=body.actor,
        notes=body.notes or "Reopened",
    )


# ══════════════════════════════════════════════════════════════════════════════
#  Routes – Bulk actions
# ══════════════════════════════════════════════════════════════════════════════

@app.post(
    "/alerts/bulk/approve",
    summary="Bulk approve a list of pending alerts",
    tags=["Alerts – Bulk"],
)
async def bulk_approve(
    body: BulkActionRequest,
    db: AsyncSession = Depends(get_db),
    _auth: str = Depends(require_admin_key),
    _rl: None = Depends(rate_limit),
):
    """
    Approve multiple `pending` alerts in a single request.
    Useful in the HITL dashboard when reviewing a batch.

    Returns a summary of successes and failures.
    Failures (e.g. wrong state) are reported but do not abort the batch.
    """
    return await _bulk_transition(body, to_status="approved", db=db)


@app.post(
    "/alerts/bulk/dismiss",
    summary="Bulk dismiss a list of pending alerts",
    tags=["Alerts – Bulk"],
)
async def bulk_dismiss(
    body: BulkActionRequest,
    db: AsyncSession = Depends(get_db),
    _auth: str = Depends(require_admin_key),
    _rl: None = Depends(rate_limit),
):
    """
    Dismiss multiple `pending` alerts in a single request.
    """
    return await _bulk_transition(body, to_status="dismissed", db=db)


async def _bulk_transition(
    body: BulkActionRequest,
    to_status: str,
    db: AsyncSession,
) -> dict:
    succeeded, failed = [], []
    for alert_id in body.ids:
        try:
            await _transition(
                alert_id=alert_id,
                to_status=to_status,
                db=db,
                actor=body.actor,
                notes=body.notes,
            )
            succeeded.append(alert_id)
        except HTTPException as exc:
            failed.append({"id": alert_id, "reason": exc.detail})
        except Exception as exc:
            failed.append({"id": alert_id, "reason": str(exc)})

    log.info(
        "Bulk %s: %d succeeded, %d failed",
        to_status, len(succeeded), len(failed),
    )
    return {
        "to_status":  to_status,
        "succeeded":  succeeded,
        "failed":     failed,
        "total":      len(body.ids),
    }


# ══════════════════════════════════════════════════════════════════════════════
#  Routes – Audit log
# ══════════════════════════════════════════════════════════════════════════════

@app.get(
    "/alerts/{alert_id}/history",
    response_model=List[AuditEntry],
    summary="Get full state-change history for an alert",
    tags=["Audit"],
)
async def get_alert_history(
    alert_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Returns every status transition ever made on an alert, oldest first.

    Useful for debugging, compliance, and the HITL dashboard detail view.
    """
    # Confirm the alert exists first
    await _fetch_or_404(alert_id, db)

    result = await db.execute(
        sa.select(audit_log_table)
        .where(audit_log_table.c.alert_id == alert_id)
        .order_by(audit_log_table.c.created_at.asc())
    )
    rows = result.mappings().all()
    return [dict(r) for r in rows]


# ══════════════════════════════════════════════════════════════════════════════
#  Routes – Generate alerts from real DB tasks
# ══════════════════════════════════════════════════════════════════════════════

@app.post(
    "/alerts/generate-from-tasks",
    summary="Generate alerts from real assigned/in-progress tasks in the DB",
    tags=["Alerts – CRUD"],
)
async def generate_alerts_from_tasks(db: AsyncSession = Depends(get_db)):
    """
    Scans all tasks that are assigned to an employee (status != 'done').
    For each task, creates a pending alert if one does not already exist
    (matched by task_key = 'TASK-{id}').
    Returns the count of newly created alerts.
    """
    # Fetch all non-done tasks that have an assignee
    task_rows = await db.execute(
        sa.select(tasks_table).where(
            tasks_table.c.assigned_to.isnot(None),
            tasks_table.c.status != "done",
        )
    )
    tasks = [dict(r) for r in task_rows.mappings().all()]

    if not tasks:
        return {"created": 0, "skipped": 0, "message": "No assigned non-done tasks found"}

    # Build lookup of existing alert task_keys so we don't duplicate
    existing_rows = await db.execute(sa.select(alerts_table.c.task_key))
    existing_keys = {r[0] for r in existing_rows.fetchall()}

    created = 0
    skipped = 0

    for task in tasks:
        task_key = f"TASK-{task['id']}"
        if task_key in existing_keys:
            skipped += 1
            continue

        # Get employee email if available
        emp_email = None
        if task["assigned_to"]:
            emp_row = await db.execute(
                sa.select(employees_table).where(employees_table.c.id == task["assigned_to"])
            )
            emp = emp_row.mappings().first()
            if emp:
                emp_email = emp.get("email")

        await db.execute(
            alerts_table.insert().values(
                task_key=task_key,
                task_summary=task["title"],
                assignee=task["assigned_name"] or "Unassigned",
                assignee_email=emp_email,
                jira_url=None,
                last_updated=task.get("created_at"),
                status="pending",
                slack_sent=False,
            )
        )
        created += 1

    await db.commit()
    log.info("Generated %d alerts from real tasks (%d skipped as duplicates)", created, skipped)
    return {
        "created": created,
        "skipped": skipped,
        "message": f"Created {created} alert(s) from your real tasks ({skipped} already existed)",
    }


# ══════════════════════════════════════════════════════════════════════════════
#  Routes – Analytics
# ══════════════════════════════════════════════════════════════════════════════

@app.get(
    "/analytics",
    summary="Full analytics data for the dashboard",
    tags=["Analytics"],
)
async def get_analytics(db: AsyncSession = Depends(get_db)):
    """
    Returns comprehensive analytics data:
    - Status distribution
    - Alerts by assignee
    - Daily alert trend (last 7 days)
    - Recent audit log activity
    - Resolution metrics
    """
    from datetime import timedelta

    now = datetime.utcnow()
    col = alerts_table.c

    # 1. Status distribution
    status_result = await db.execute(
        sa.select(col.status, sa.func.count().label("count"))
        .group_by(col.status)
    )
    status_dist = {row.status: row.count for row in status_result}

    # 2. Alerts by assignee
    assignee_result = await db.execute(
        sa.select(col.assignee, col.status, sa.func.count().label("count"))
        .group_by(col.assignee, col.status)
    )
    assignee_map = {}
    for row in assignee_result:
        if row.assignee not in assignee_map:
            assignee_map[row.assignee] = {"total": 0, "pending": 0, "approved": 0, "dismissed": 0, "notified": 0}
        assignee_map[row.assignee][row.status] = row.count
        assignee_map[row.assignee]["total"] += row.count

    assignee_breakdown = [
        {"assignee": k, **v} for k, v in sorted(assignee_map.items(), key=lambda x: -x[1]["total"])
    ]

    # 3. Daily trend (last 7 days)
    daily_trend = []
    for i in range(6, -1, -1):
        day_start = (now - timedelta(days=i)).replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)
        day_result = await db.execute(
            sa.select(sa.func.count()).select_from(alerts_table)
            .where(col.detected_at >= day_start, col.detected_at < day_end)
        )
        count = day_result.scalar_one()
        daily_trend.append({
            "date": day_start.strftime("%Y-%m-%d"),
            "label": day_start.strftime("%a"),
            "count": count,
        })

    # 4. Recent audit activity (last 20 entries)
    audit_result = await db.execute(
        sa.select(audit_log_table)
        .order_by(audit_log_table.c.created_at.desc())
        .limit(20)
    )
    recent_activity = [dict(r) for r in audit_result.mappings().all()]

    # 5. Resolution metrics
    resolved_result = await db.execute(
        sa.select(sa.func.count()).select_from(alerts_table)
        .where(col.status.in_(["approved", "notified", "dismissed"]))
    )
    total_resolved = resolved_result.scalar_one()

    total_result = await db.execute(
        sa.select(sa.func.count()).select_from(alerts_table)
    )
    total_all = total_result.scalar_one()

    # Slack sent count
    slack_result = await db.execute(
        sa.select(sa.func.count()).select_from(alerts_table)
        .where(col.slack_sent == True)
    )
    slack_sent = slack_result.scalar_one()

    # 6. Projects summary
    proj_result = await db.execute(sa.select(projects_table))
    projects = [dict(r) for r in proj_result.mappings().all()]
    total_projects = len(projects)
    active_projects = sum(1 for p in projects if p["status"] == "active")

    # 7. Tasks summary
    task_result = await db.execute(sa.select(tasks_table))
    all_tasks = [dict(r) for r in task_result.mappings().all()]
    task_status_dist = {"todo": 0, "in_progress": 0, "done": 0}
    task_priority_dist = {"high": 0, "medium": 0, "low": 0}
    for t in all_tasks:
        s = t.get("status", "todo")
        if s in task_status_dist:
            task_status_dist[s] += 1
        p = t.get("priority", "medium")
        if p in task_priority_dist:
            task_priority_dist[p] += 1
    total_tasks = len(all_tasks)
    assigned_tasks = sum(1 for t in all_tasks if t.get("assigned_to"))

    # 8. Employee workload
    emp_result = await db.execute(sa.select(employees_table))
    employees = [dict(r) for r in emp_result.mappings().all()]
    total_employees = len(employees)
    available_employees = sum(1 for e in employees if e.get("availability") == "available")
    employee_workload = []
    for emp in employees:
        emp_tasks = [t for t in all_tasks if t.get("assigned_to") == emp["id"]]
        employee_workload.append({
            "name": emp["name"],
            "role": emp.get("role") or "—",
            "total_tasks": len(emp_tasks),
            "done": sum(1 for t in emp_tasks if t.get("status") == "done"),
            "in_progress": sum(1 for t in emp_tasks if t.get("status") == "in_progress"),
            "todo": sum(1 for t in emp_tasks if t.get("status") == "todo"),
            "availability": emp.get("availability", "available"),
        })
    employee_workload.sort(key=lambda x: -x["total_tasks"])

    return {
        "status_distribution": status_dist,
        "assignee_breakdown": assignee_breakdown,
        "daily_trend": daily_trend,
        "recent_activity": recent_activity,
        "metrics": {
            "total_alerts": total_all,
            "total_resolved": total_resolved,
            "resolution_rate": round(total_resolved / max(total_all, 1) * 100, 1),
            "slack_notifications_sent": slack_sent,
            "pending": status_dist.get("pending", 0),
            # Project/Task/Employee metrics
            "total_projects": total_projects,
            "active_projects": active_projects,
            "total_tasks": total_tasks,
            "tasks_done": task_status_dist["done"],
            "tasks_in_progress": task_status_dist["in_progress"],
            "tasks_todo": task_status_dist["todo"],
            "assigned_tasks": assigned_tasks,
            "task_completion_rate": round(task_status_dist["done"] / max(total_tasks, 1) * 100, 1),
            "total_employees": total_employees,
            "available_employees": available_employees,
        },
        "task_status_dist": task_status_dist,
        "task_priority_dist": task_priority_dist,
        "employee_workload": employee_workload,
        "projects_summary": [
            {
                "name": p["name"],
                "status": p["status"],
                "total_tasks": p.get("total_tasks", 0),
                "completed_tasks": p.get("completed_tasks", 0),
                "completion_pct": round(p.get("completed_tasks", 0) / max(p.get("total_tasks", 1), 1) * 100),
            }
            for p in projects
        ],
    }


# ══════════════════════════════════════════════════════════════════════════════
#  Routes – Employees
# ══════════════════════════════════════════════════════════════════════════════

class EmployeeCreate(BaseModel):
    name:         str  = Field(..., min_length=1, max_length=255)
    email:        Optional[str] = None
    role:         Optional[str] = None
    skills:       List[str]     = Field(default_factory=list)
    availability: str           = "available"

class EmployeeOut(BaseModel):
    id:           int
    name:         str
    email:        Optional[str]
    role:         Optional[str]
    skills:       str      # JSON string
    availability: str
    current_load: int
    created_at:   datetime
    class Config:
        from_attributes = True


@app.post("/employees", status_code=201, summary="Add employee", tags=["Employees"])
async def create_employee(payload: EmployeeCreate, db: AsyncSession = Depends(get_db)):
    import json
    result = await db.execute(
        employees_table.insert()
        .values(name=payload.name, email=payload.email, role=payload.role,
                skills=json.dumps(payload.skills), availability=payload.availability)
        .returning(employees_table)
    )
    await db.commit()
    row = result.mappings().first()
    log.info("Employee created: %s (%s)", row["name"], row["role"])
    return dict(row)


@app.get("/employees", summary="List employees", tags=["Employees"])
async def list_employees(db: AsyncSession = Depends(get_db)):
    import json
    result = await db.execute(sa.select(employees_table).order_by(employees_table.c.name))
    rows = result.mappings().all()
    emp_list = []
    for r in rows:
        d = dict(r)
        try:
            d["skills_list"] = json.loads(d["skills"]) if d["skills"] else []
        except:
            d["skills_list"] = []
        emp_list.append(d)
    return emp_list


@app.put("/employees/{emp_id}", summary="Update employee", tags=["Employees"])
async def update_employee(emp_id: int, payload: EmployeeCreate, db: AsyncSession = Depends(get_db)):
    import json
    result = await db.execute(sa.select(employees_table).where(employees_table.c.id == emp_id))
    if not result.mappings().first():
        raise HTTPException(404, f"Employee {emp_id} not found")
    await db.execute(
        employees_table.update().where(employees_table.c.id == emp_id)
        .values(name=payload.name, email=payload.email, role=payload.role,
                skills=json.dumps(payload.skills), availability=payload.availability)
    )
    await db.commit()
    result2 = await db.execute(sa.select(employees_table).where(employees_table.c.id == emp_id))
    return dict(result2.mappings().first())


@app.delete("/employees/{emp_id}", summary="Delete employee", tags=["Employees"])
async def delete_employee(emp_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(sa.select(employees_table).where(employees_table.c.id == emp_id))
    if not result.mappings().first():
        raise HTTPException(404, f"Employee {emp_id} not found")
    await db.execute(employees_table.delete().where(employees_table.c.id == emp_id))
    await db.commit()
    return {"deleted": emp_id}


# ══════════════════════════════════════════════════════════════════════════════
#  Routes – Projects
# ══════════════════════════════════════════════════════════════════════════════

class ProjectCreate(BaseModel):
    name:        str           = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    prd_text:    Optional[str] = None


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    prd_text: Optional[str] = None
    status: Optional[str] = None


@app.put("/projects/{project_id}", summary="Update a project", tags=["Projects"])
async def update_project(project_id: int, payload: ProjectUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(sa.select(projects_table).where(projects_table.c.id == project_id))
    if not result.mappings().first():
        raise HTTPException(404, f"Project {project_id} not found")
    values = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not values:
        raise HTTPException(400, "No fields to update")
    values["updated_at"] = datetime.utcnow()
    await db.execute(projects_table.update().where(projects_table.c.id == project_id).values(**values))
    await db.commit()
    updated = (await db.execute(sa.select(projects_table).where(projects_table.c.id == project_id))).mappings().first()
    log.info("Project %d updated: %s", project_id, list(values.keys()))
    return dict(updated)


@app.delete("/projects/{project_id}", summary="Delete a project and all its tasks", tags=["Projects"])
async def delete_project(project_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(sa.select(projects_table).where(projects_table.c.id == project_id))
    project = result.mappings().first()
    if not project:
        raise HTTPException(404, f"Project {project_id} not found")
    # Delete child tasks first to satisfy any FK constraints
    await db.execute(tasks_table.delete().where(tasks_table.c.project_id == project_id))
    await db.execute(projects_table.delete().where(projects_table.c.id == project_id))
    await db.commit()
    log.info("Project %d (%s) deleted along with its tasks", project_id, project["name"])
    return {"deleted": True, "project_id": project_id}


@app.post("/projects", status_code=201, summary="Create project", tags=["Projects"])
async def create_project(payload: ProjectCreate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        projects_table.insert()
        .values(name=payload.name, description=payload.description, prd_text=payload.prd_text)
        .returning(projects_table)
    )
    await db.commit()
    row = result.mappings().first()
    log.info("Project created: %s", row["name"])
    return dict(row)


@app.get("/projects", summary="List projects", tags=["Projects"])
async def list_projects(db: AsyncSession = Depends(get_db)):
    result = await db.execute(sa.select(projects_table).order_by(projects_table.c.created_at.desc()))
    projects = []
    for r in result.mappings().all():
        d = dict(r)
        # get task counts
        task_result = await db.execute(
            sa.select(tasks_table.c.status, sa.func.count().label("c"))
            .where(tasks_table.c.project_id == d["id"])
            .group_by(tasks_table.c.status)
        )
        status_counts = {row.status: row.c for row in task_result}
        d["task_stats"] = status_counts
        d["total_tasks"] = sum(status_counts.values())
        d["completed_tasks"] = status_counts.get("done", 0)
        in_progress = status_counts.get("in_progress", 0)
        # Progress: done = 100%, in_progress = 50% credit, todo/paused = 0%.
        d["progress"] = round(
            (d["completed_tasks"] + in_progress * 0.5) / max(d["total_tasks"], 1) * 100,
            1,
        )
        projects.append(d)
    return projects


@app.get("/projects/{project_id}", summary="Get project detail", tags=["Projects"])
async def get_project(project_id: int, db: AsyncSession = Depends(get_db)):
    import json
    result = await db.execute(sa.select(projects_table).where(projects_table.c.id == project_id))
    row = result.mappings().first()
    if not row:
        raise HTTPException(404, f"Project {project_id} not found")
    d = dict(row)
    # Get tasks
    task_result = await db.execute(
        sa.select(tasks_table).where(tasks_table.c.project_id == project_id)
        .order_by(tasks_table.c.priority.desc(), tasks_table.c.created_at)
    )
    tasks = []
    for t in task_result.mappings().all():
        td = dict(t)
        try:
            td["required_skills_list"] = json.loads(td["required_skills"]) if td["required_skills"] else []
        except:
            td["required_skills_list"] = []
        tasks.append(td)
    d["tasks"] = tasks

    status_counts = {}
    for t in tasks:
        s = t["status"]
        status_counts[s] = status_counts.get(s, 0) + 1
    d["task_stats"] = status_counts
    d["total_tasks"] = len(tasks)
    d["completed_tasks"] = status_counts.get("done", 0)
    d["progress"] = round(d["completed_tasks"] / max(d["total_tasks"], 1) * 100, 1)
    return d


# ══════════════════════════════════════════════════════════════════════════════
#  Routes – AI PRD Parsing
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/projects/{project_id}/parse", summary="AI parse PRD into tasks", tags=["AI"])
async def parse_prd(project_id: int, db: AsyncSession = Depends(get_db)):
    """
    Uses OpenAI to parse the project's PRD text into structured tasks.
    Each task gets a title, description, priority, estimated hours, and required skills.
    """
    import json
    import httpx

    # Get the project
    result = await db.execute(sa.select(projects_table).where(projects_table.c.id == project_id))
    project = result.mappings().first()
    if not project:
        raise HTTPException(404, f"Project {project_id} not found")
    if not project["prd_text"]:
        raise HTTPException(400, "No PRD text uploaded for this project")

    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key or api_key.startswith("sk-..."):
        # Fallback: generate mock tasks from PRD keywords
        log.warning("No valid OpenAI key — using rule-based task extraction")
        tasks = _fallback_parse_prd(project["prd_text"])
    else:
        prompt = f"""You are a senior tech lead AI. Analyze this Product Requirements Document (PRD) and break it down into actionable development tasks. For each task, write it as if you are briefing a developer who has never seen this project — explain WHAT to build and HOW to approach it.

For each task, provide:
- title: Clear, concise task title
- description: 2-3 sentence summary of what this task is about and why it matters
- implementation_steps: Array of 3-6 concrete step-by-step instructions a developer should follow to solve this task (e.g. "Create a new endpoint POST /foo", "Add a migration for the bar table", "Write unit tests covering X")
- acceptance_criteria: Array of 2-4 testable conditions that must be true for this task to be considered done
- tech_hints: Short string suggesting libraries, patterns, or files the developer should look at
- priority: "high", "medium", or "low"
- estimated_hours: Estimated hours to complete (number)
- required_skills: Array of skill tags needed (e.g. ["python", "react", "devops", "ml", "backend", "frontend", "testing", "database", "api", "ui/ux"])

Return a JSON array of tasks. Respond with ONLY valid JSON, no markdown.

PRD:
{project["prd_text"][:4000]}"""

        try:
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                    json={
                        "model": "gpt-4o-mini",
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.3,
                        "max_tokens": 3000,
                    }
                )
                if resp.status_code != 200:
                    log.error("OpenAI error: %s", resp.text)
                    tasks = _fallback_parse_prd(project["prd_text"])
                else:
                    content = resp.json()["choices"][0]["message"]["content"]
                    # Clean markdown if present
                    if content.strip().startswith("```"):
                        content = content.strip().split("\n", 1)[1].rsplit("```", 1)[0]
                    tasks = json.loads(content)
        except Exception as e:
            log.error("OpenAI parsing failed: %s", e)
            tasks = _fallback_parse_prd(project["prd_text"])

    # Insert tasks into DB
    created_tasks = []
    for t in tasks:
        # Build a rich, developer-facing description: summary + steps + acceptance criteria + hints
        parts = []
        if t.get("description"):
            parts.append(t["description"].strip())
        steps = t.get("implementation_steps") or []
        if steps:
            parts.append("**How to solve this:**\n" + "\n".join(f"{i+1}. {s}" for i, s in enumerate(steps)))
        criteria = t.get("acceptance_criteria") or []
        if criteria:
            parts.append("**Acceptance criteria:**\n" + "\n".join(f"- {c}" for c in criteria))
        if t.get("tech_hints"):
            parts.append(f"**Tech hints:** {t['tech_hints']}")
        rich_description = "\n\n".join(parts) if parts else t.get("description", "")

        ins = await db.execute(
            tasks_table.insert().values(
                project_id=project_id,
                title=t.get("title", "Untitled Task"),
                description=rich_description,
                priority=t.get("priority", "medium"),
                estimated_hours=t.get("estimated_hours", 4),
                required_skills=json.dumps(t.get("required_skills", [])),
            ).returning(tasks_table)
        )
        created_tasks.append(dict(ins.mappings().first()))

    # Update project task count
    await db.execute(
        projects_table.update().where(projects_table.c.id == project_id)
        .values(total_tasks=len(created_tasks))
    )
    await db.commit()

    log.info("Parsed PRD for project %d: %d tasks created", project_id, len(created_tasks))
    return {"project_id": project_id, "tasks_created": len(created_tasks), "tasks": created_tasks}


def _fallback_parse_prd(prd_text: str) -> list:
    """Simple rule-based fallback when OpenAI is not available."""
    import re
    lines = prd_text.strip().split("\n")
    tasks = []
    skill_keywords = {
        "api": ["api", "endpoint", "rest", "graphql"],
        "frontend": ["ui", "interface", "dashboard", "page", "component", "react", "css"],
        "backend": ["server", "logic", "middleware", "service", "handler"],
        "database": ["database", "schema", "migration", "table", "query", "sql"],
        "testing": ["test", "coverage", "qa", "validation"],
        "devops": ["deploy", "ci/cd", "docker", "kubernetes", "pipeline"],
        "ml": ["model", "ai", "machine learning", "prediction", "training"],
        "python": ["python", "flask", "django", "fastapi"],
        "react": ["react", "next.js", "component", "jsx"],
    }

    for line in lines:
        line = line.strip()
        if not line or len(line) < 10:
            continue
        # Extract headings or bullet points as task candidates
        if line.startswith(("#", "-", "*", "•")) or re.match(r'^\d+\.', line):
            title = re.sub(r'^[#\-*•\d.]+\s*', '', line).strip()
            if len(title) < 5:
                continue
            # Detect skills from text
            skills = []
            lower = title.lower()
            for skill, keywords in skill_keywords.items():
                if any(kw in lower for kw in keywords):
                    skills.append(skill)
            if not skills:
                skills = ["backend"]  # default

            tasks.append({
                "title": title[:200],
                "description": f"Task derived from PRD: {title}",
                "priority": "high" if any(w in lower for w in ["critical", "must", "important", "core"]) else "medium",
                "estimated_hours": 8,
                "required_skills": skills,
            })

    if not tasks:
        # Create at least a few generic tasks
        tasks = [
            {"title": "Review and finalize requirements", "description": "Review the PRD and clarify requirements", "priority": "high", "estimated_hours": 4, "required_skills": ["backend"]},
            {"title": "Design system architecture", "description": "Create architecture diagram and tech stack decisions", "priority": "high", "estimated_hours": 8, "required_skills": ["backend", "devops"]},
            {"title": "Set up development environment", "description": "Configure repos, CI/CD, and dev tools", "priority": "medium", "estimated_hours": 4, "required_skills": ["devops"]},
        ]
    return tasks[:20]  # Cap at 20 tasks


# ══════════════════════════════════════════════════════════════════════════════
#  Routes – AI Task Assignment
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/projects/{project_id}/unassign-all", summary="Clear assignees on all tasks in a project", tags=["AI"])  # touch
async def unassign_all(project_id: int, db: AsyncSession = Depends(get_db)):
    res = await db.execute(
        tasks_table.update()
        .where(tasks_table.c.project_id == project_id)
        .values(assigned_to=None, assigned_name=None, ai_confidence=None)
    )
    await db.commit()
    log.info("Unassigned all tasks in project %d (%d rows)", project_id, res.rowcount or 0)
    return {"project_id": project_id, "unassigned": res.rowcount or 0}


@app.post("/projects/{project_id}/assign-all", summary="AI assign all unassigned tasks", tags=["AI"])
async def ai_assign_all(project_id: int, db: AsyncSession = Depends(get_db)):
    """
    For each unassigned task in the project, use AI to match the best employee
    based on skill overlap, current workload, and availability.
    """
    import json

    # Get unassigned tasks
    task_result = await db.execute(
        sa.select(tasks_table).where(
            tasks_table.c.project_id == project_id,
            tasks_table.c.assigned_to.is_(None),
        )
    )
    unassigned = [dict(r) for r in task_result.mappings().all()]
    if not unassigned:
        return {"message": "No unassigned tasks", "assignments": []}

    # Get available employees
    emp_result = await db.execute(
        sa.select(employees_table).where(employees_table.c.availability == "available")
    )
    employees = []
    for r in emp_result.mappings().all():
        d = dict(r)
        try:
            d["skills_list"] = json.loads(d["skills"]) if d["skills"] else []
        except:
            d["skills_list"] = []
        employees.append(d)

    if not employees:
        raise HTTPException(400, "No available employees. Add employees first.")

    # Recompute true current_load from real DB task counts so stale values
    # in the employees table don't bias the assigner toward one person.
    load_rows = await db.execute(
        sa.select(tasks_table.c.assigned_to, sa.func.count().label("c"))
        .where(tasks_table.c.assigned_to.is_not(None))
        .where(tasks_table.c.status.in_(("todo", "in_progress")))
        .group_by(tasks_table.c.assigned_to)
    )
    real_loads = {row.assigned_to: row.c for row in load_rows}
    for emp in employees:
        emp["current_load"] = real_loads.get(emp["id"], 0)

    assignments = []
    for task in unassigned:
        try:
            task_skills = json.loads(task["required_skills"]) if task["required_skills"] else []
        except Exception:
            task_skills = []

        # Score each employee. Skill 0.5 / load 0.5 — load matters as much as
        # skill so we never dump everything on one person when skills tie.
        scored = []
        for emp in employees:
            emp_skills = emp["skills_list"]
            if task_skills:
                overlap = len(set(s.lower() for s in task_skills) & set(s.lower() for s in emp_skills))
                skill_score = overlap / len(task_skills)
            else:
                skill_score = 0.5
            load_score = max(0.0, 1.0 - (emp["current_load"] * 0.2))
            score = (skill_score * 0.5) + (load_score * 0.5)
            scored.append((score, emp["current_load"], emp))

        # Sort by score desc, then by lowest current load (round-robin tie break),
        # then by employee id for deterministic ordering.
        scored.sort(key=lambda x: (-x[0], x[1], x[2]["id"]))
        best_score, _, best_emp = scored[0]

        if best_emp:
            confidence = round(best_score * 100, 1)
            await db.execute(
                tasks_table.update().where(tasks_table.c.id == task["id"])
                .values(assigned_to=best_emp["id"], assigned_name=best_emp["name"], ai_confidence=confidence)
            )
            # Increment load
            await db.execute(
                employees_table.update().where(employees_table.c.id == best_emp["id"])
                .values(current_load=employees_table.c.current_load + 1)
            )
            best_emp["current_load"] += 1  # update in-memory too

            assignments.append({
                "task_id": task["id"],
                "task_title": task["title"],
                "assigned_to": best_emp["name"],
                "employee_id": best_emp["id"],
                "employee_email": best_emp.get("email"),
                "confidence": confidence,
                "matched_skills": list(set(s.lower() for s in (json.loads(task["required_skills"]) if task["required_skills"] else [])) & set(s.lower() for s in best_emp["skills_list"])),
            })

    await db.commit()

    # Send notification emails (best-effort) — runs after commit so DB is consistent
    proj_row = (await db.execute(sa.select(projects_table).where(projects_table.c.id == project_id))).mappings().first()
    project_name = proj_row["name"] if proj_row else ""
    emails_sent = 0
    for a in assignments:
        if not a.get("employee_email"):
            continue
        task_row = (await db.execute(sa.select(tasks_table).where(tasks_table.c.id == a["task_id"]))).mappings().first()
        if task_row and await send_assignment_email(a["employee_email"], a["assigned_to"], dict(task_row), project_name):
            emails_sent += 1

    log.info("AI assigned %d tasks in project %d (%d emails sent)", len(assignments), project_id, emails_sent)
    return {"project_id": project_id, "assignments": assignments, "total_assigned": len(assignments), "emails_sent": emails_sent}


# ══════════════════════════════════════════════════════════════════════════════
#  Routes – Tasks
# ══════════════════════════════════════════════════════════════════════════════

class TaskStatusUpdate(BaseModel):
    status: str = Field(..., pattern="^(todo|in_progress|done)$")

@app.get("/projects/{project_id}/tasks", summary="Get project tasks", tags=["Tasks"])
async def list_project_tasks(project_id: int, db: AsyncSession = Depends(get_db)):
    import json
    result = await db.execute(
        sa.select(tasks_table).where(tasks_table.c.project_id == project_id)
        .order_by(
            sa.case(
                (tasks_table.c.priority == "high", 1),
                (tasks_table.c.priority == "medium", 2),
                (tasks_table.c.priority == "low", 3),
                else_=4
            ),
            tasks_table.c.created_at
        )
    )
    tasks = []
    for r in result.mappings().all():
        d = dict(r)
        try:
            d["required_skills_list"] = json.loads(d["required_skills"]) if d["required_skills"] else []
        except:
            d["required_skills_list"] = []
        tasks.append(d)
    return tasks


@app.put("/tasks/{task_id}/status", summary="Update task status", tags=["Tasks"])
async def update_task_status(task_id: int, body: TaskStatusUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(sa.select(tasks_table).where(tasks_table.c.id == task_id))
    task = result.mappings().first()
    if not task:
        raise HTTPException(404, f"Task {task_id} not found")

    update_vals = {"status": body.status}
    if body.status == "done":
        update_vals["completed_at"] = datetime.utcnow()

    await db.execute(tasks_table.update().where(tasks_table.c.id == task_id).values(**update_vals))

    # Update project completed count
    if body.status == "done" or task["status"] == "done":
        proj_id = task["project_id"]
        done_result = await db.execute(
            sa.select(sa.func.count()).select_from(tasks_table)
            .where(tasks_table.c.project_id == proj_id, tasks_table.c.status == "done")
        )
        done_count = done_result.scalar_one()
        await db.execute(
            projects_table.update().where(projects_table.c.id == proj_id)
            .values(completed_tasks=done_count)
        )

    await db.commit()
    updated = await db.execute(sa.select(tasks_table).where(tasks_table.c.id == task_id))
    return dict(updated.mappings().first())


class TaskAssignBody(BaseModel):
    employee_id: int
    employee_name: str


async def send_assignment_email(to_email: str, to_name: str, task: dict, project_name: str = "") -> bool:
    """Send a 'you've been assigned a task' email via Resend. Returns True on success."""
    import httpx
    api_key = os.environ.get("RESEND_API_KEY", "").strip()
    from_email = os.environ.get("RESEND_FROM_EMAIL", "onboarding@resend.dev").strip()
    if not api_key or not to_email:
        return False
    desc_html = (task.get("description") or "").replace("\n", "<br>").replace("**", "")
    subject = f"[Aegis PM] You've been assigned: {task['title']}"
    html = f"""
    <div style="font-family:-apple-system,Segoe UI,Helvetica,Arial,sans-serif;max-width:640px;margin:0 auto;color:#0f172a;">
      <h2 style="color:#2563eb;">Hi {to_name}, you have a new task</h2>
      <p>You've been assigned the following task{f' in <strong>{project_name}</strong>' if project_name else ''}:</p>
      <div style="border:1px solid #e2e8f0;border-radius:10px;padding:18px;background:#f8fafc;">
        <h3 style="margin:0 0 6px 0;">{task['title']}</h3>
        <div style="color:#64748b;font-size:13px;margin-bottom:14px;">
          Priority: <strong>{task.get('priority','medium')}</strong> ·
          Estimated: <strong>{task.get('estimated_hours','?')}h</strong>
        </div>
        <div style="font-size:14px;line-height:1.6;">{desc_html or '(No instructions yet — open the dashboard to generate them.)'}</div>
      </div>
      <p style="margin-top:18px;font-size:13px;color:#64748b;">— Aegis PM</p>
    </div>
    """
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={"from": from_email, "to": [to_email], "subject": subject, "html": html},
            )
        if r.status_code >= 300:
            log.error("Resend error %s: %s", r.status_code, r.text[:300])
            return False
        log.info("Sent assignment email to %s for task %s", to_email, task.get("id"))
        return True
    except Exception as e:
        log.error("Resend exception: %s", e)
        return False


@app.post("/tasks/{task_id}/assign", summary="Manually assign a task to an employee", tags=["Tasks"])
async def assign_task(task_id: int, body: TaskAssignBody, db: AsyncSession = Depends(get_db)):
    result = await db.execute(sa.select(tasks_table).where(tasks_table.c.id == task_id))
    task = result.mappings().first()
    if not task:
        raise HTTPException(404, f"Task {task_id} not found")

    # Verify the employee exists
    emp_result = await db.execute(sa.select(employees_table).where(employees_table.c.id == body.employee_id))
    employee = emp_result.mappings().first()
    if not employee:
        raise HTTPException(404, f"Employee {body.employee_id} not found")

    await db.execute(
        tasks_table.update().where(tasks_table.c.id == task_id)
        .values(assigned_to=body.employee_id, assigned_name=body.employee_name)
    )
    await db.commit()

    updated_row = (await db.execute(sa.select(tasks_table).where(tasks_table.c.id == task_id))).mappings().first()
    updated = dict(updated_row)

    # Send email notification to the assignee (best-effort, non-blocking on failure)
    proj_row = (await db.execute(sa.select(projects_table).where(projects_table.c.id == updated["project_id"]))).mappings().first()
    project_name = proj_row["name"] if proj_row else ""
    email_sent = False
    if employee.get("email"):
        email_sent = await send_assignment_email(employee["email"], employee["name"], updated, project_name)

    log.info("Task %d manually assigned to employee %d (%s) email_sent=%s",
             task_id, body.employee_id, body.employee_name, email_sent)
    updated["email_sent"] = email_sent
    return updated


@app.post("/tasks/{task_id}/pause", summary="Pause a task", tags=["Tasks"])
async def pause_task(task_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(sa.select(tasks_table).where(tasks_table.c.id == task_id))
    task = result.mappings().first()
    if not task:
        raise HTTPException(404, f"Task {task_id} not found")
    if task["status"] == "paused":
        raise HTTPException(400, "Task is already paused")
    await db.execute(tasks_table.update().where(tasks_table.c.id == task_id).values(status="paused"))
    await db.commit()
    updated = await db.execute(sa.select(tasks_table).where(tasks_table.c.id == task_id))
    log.info("Task %d paused (was: %s)", task_id, task["status"])
    return dict(updated.mappings().first())


@app.post("/tasks/{task_id}/resume", summary="Resume a paused task", tags=["Tasks"])
async def resume_task(task_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(sa.select(tasks_table).where(tasks_table.c.id == task_id))
    task = result.mappings().first()
    if not task:
        raise HTTPException(404, f"Task {task_id} not found")
    if task["status"] != "paused":
        raise HTTPException(400, f"Task is not paused (current status: {task['status']})")
    await db.execute(tasks_table.update().where(tasks_table.c.id == task_id).values(status="in_progress"))
    await db.commit()
    updated = await db.execute(sa.select(tasks_table).where(tasks_table.c.id == task_id))
    log.info("Task %d resumed", task_id)
    return dict(updated.mappings().first())


@app.post("/tasks/{task_id}/generate-instructions", summary="AI-generate developer instructions for a task", tags=["AI"])
async def generate_task_instructions(task_id: int, db: AsyncSession = Depends(get_db)):
    """
    Use Groq (LLaMA) to generate developer-facing implementation instructions
    for a single existing task, using its title + the parent project's PRD as context.
    Saves the result into the task's `description` field and returns it.
    """
    import json, httpx
    result = await db.execute(sa.select(tasks_table).where(tasks_table.c.id == task_id))
    task = result.mappings().first()
    if not task:
        raise HTTPException(404, f"Task {task_id} not found")

    proj_result = await db.execute(sa.select(projects_table).where(projects_table.c.id == task["project_id"]))
    project = proj_result.mappings().first()
    prd_snippet = (project["prd_text"] or "")[:3500] if project else ""

    groq_key = os.environ.get("GROQ_API_KEY", "").strip()
    data = None
    llm_error = None

    prompt = f"""You are a senior tech lead briefing a developer who is new to this project.
Given the project context and the specific task below, write clear developer instructions.

Project PRD context:
{prd_snippet}

Task title: {task["title"]}
Required skills: {task["required_skills"] or "[]"}
Estimated hours: {task["estimated_hours"]}

Return ONLY valid JSON (no markdown fences) with this shape:
{{
  "summary": "2-3 sentence explanation of WHAT this task is and WHY it matters in the project",
  "implementation_steps": ["step 1", "step 2", "step 3", "step 4"],
  "acceptance_criteria": ["testable condition 1", "testable condition 2"],
  "tech_hints": "short string of libraries/files/patterns the developer should look at"
}}"""

    if groq_key:
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {groq_key}", "Content-Type": "application/json"},
                    json={
                        "model": "llama-3.3-70b-versatile",
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.3,
                        "max_tokens": 1200,
                        "response_format": {"type": "json_object"},
                    },
                )
            if resp.status_code == 200:
                content = resp.json()["choices"][0]["message"]["content"]
                data = json.loads(content)
            else:
                llm_error = f"Groq {resp.status_code}"
                log.warning("Groq unavailable, using template fallback: %s", resp.text[:200])
        except Exception as e:
            llm_error = str(e)
            log.warning("Groq call failed, using template fallback: %s", e)

    if data is None:
        # Template fallback — produces sensible dev instructions without an LLM
        try:
            skills = json.loads(task["required_skills"]) if task["required_skills"] else []
        except Exception:
            skills = []
        title = task["title"]
        project_name = project["name"] if project else "the project"
        title_lc = title.lower()

        # Pick step templates by detected category
        categories = []
        if any(k in title_lc for k in ["api", "endpoint", "route"]): categories.append("api")
        if any(k in title_lc for k in ["ui", "dashboard", "page", "frontend", "screen"]): categories.append("frontend")
        if any(k in title_lc for k in ["database", "schema", "migration", "model"]): categories.append("database")
        if any(k in title_lc for k in ["test", "qa", "coverage"]): categories.append("testing")
        if any(k in title_lc for k in ["deploy", "ci", "docker", "pipeline"]): categories.append("devops")
        if any(k in title_lc for k in ["security", "auth", "encrypt", "token"]): categories.append("security")
        if any(k in title_lc for k in ["monitor", "metric", "log", "observ"]): categories.append("monitoring")
        if not categories: categories = ["generic"]

        step_templates = {
            "api":        ["Define the request/response schema (Pydantic models or DTOs)",
                           f"Implement the endpoint logic for '{title}' in the appropriate router/service",
                           "Wire up authentication and input validation",
                           "Add unit + integration tests covering happy path and edge cases",
                           "Update the OpenAPI/Swagger docs"],
            "frontend":   [f"Sketch the layout for '{title}' (wireframe or Figma)",
                           "Build the component(s) and hook them up to the API",
                           "Handle loading, empty, and error states",
                           "Make it responsive and accessible (keyboard + ARIA)",
                           "Write a smoke test or visual snapshot"],
            "database":   [f"Design the schema changes needed for '{title}'",
                           "Write a migration script (Alembic / Prisma / SQL)",
                           "Update the ORM models and any affected queries",
                           "Backfill or seed data if required",
                           "Test the migration on a dev DB before merging"],
            "testing":    [f"Identify the critical paths for '{title}'",
                           "Write unit tests for pure logic and integration tests for I/O",
                           "Add fixtures or factories for reusable test data",
                           "Wire the suite into CI and ensure it runs on every PR"],
            "devops":     [f"Define what '{title}' must produce (artifact, container, deployment)",
                           "Write the pipeline / Dockerfile / IaC config",
                           "Set up secrets and environment variables securely",
                           "Add health checks and rollback strategy",
                           "Document how to run/redeploy locally"],
            "security":   [f"Threat-model '{title}' — list assets, attackers, and risks",
                           "Choose proven libraries (don't roll your own crypto/auth)",
                           "Implement with secure defaults and least privilege",
                           "Add tests for auth bypass / injection attempts",
                           "Get a peer review focused on the security boundary"],
            "monitoring": [f"Decide which metrics/events represent '{title}' health",
                           "Instrument the code (logs, metrics, traces)",
                           "Build a dashboard and an alert with sensible thresholds",
                           "Document the runbook for when the alert fires"],
            "generic":    [f"Read the relevant section of the {project_name} PRD and clarify any open questions",
                           f"Break '{title}' into 2–4 sub-steps and sketch the data flow",
                           "Implement the smallest working version end-to-end",
                           "Add tests and update documentation",
                           "Open a PR and request review"],
        }
        steps = []
        for c in categories:
            for s in step_templates[c]:
                if s not in steps:
                    steps.append(s)
        steps = steps[:6]

        criteria = [
            f"'{title}' works end-to-end in a local dev environment",
            "All new code is covered by tests and CI is green",
            "Code is reviewed and merged with no open blockers",
        ]
        if "security" in categories:
            criteria.append("No secrets are committed and threat model is documented")

        hint_bits = []
        if skills: hint_bits.append("Skills: " + ", ".join(skills))
        if "api" in categories: hint_bits.append("look at existing routers and the auth dependency")
        if "frontend" in categories: hint_bits.append("reuse existing components and design tokens")
        if "database" in categories: hint_bits.append("check the migrations folder for prior examples")

        data = {
            "summary": f"This task — '{title}' — is part of {project_name}. Deliver it so the rest of the team can build on top of it without rework.",
            "implementation_steps": steps,
            "acceptance_criteria": criteria,
            "tech_hints": "; ".join(hint_bits) if hint_bits else "Follow existing project conventions.",
        }

    parts = []
    if data.get("summary"): parts.append(data["summary"].strip())
    steps = data.get("implementation_steps") or []
    if steps:
        parts.append("**How to solve this:**\n" + "\n".join(f"{i+1}. {s}" for i, s in enumerate(steps)))
    criteria = data.get("acceptance_criteria") or []
    if criteria:
        parts.append("**Acceptance criteria:**\n" + "\n".join(f"- {c}" for c in criteria))
    if data.get("tech_hints"):
        parts.append(f"**Tech hints:** {data['tech_hints']}")
    rich = "\n\n".join(parts)

    await db.execute(tasks_table.update().where(tasks_table.c.id == task_id).values(description=rich))
    await db.commit()
    log.info("Generated instructions for task %d (%d chars)", task_id, len(rich))
    return {"task_id": task_id, "description": rich}


@app.delete("/tasks/{task_id}", summary="Delete a task", tags=["Tasks"])
async def delete_task(task_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(sa.select(tasks_table).where(tasks_table.c.id == task_id))
    task = result.mappings().first()
    if not task:
        raise HTTPException(404, f"Task {task_id} not found")
    proj_id = task["project_id"]
    await db.execute(tasks_table.delete().where(tasks_table.c.id == task_id))
    # Recalculate project completed_tasks count
    done_result = await db.execute(
        sa.select(sa.func.count()).select_from(tasks_table)
        .where(tasks_table.c.project_id == proj_id, tasks_table.c.status == "done")
    )
    done_count = done_result.scalar_one()
    total_result = await db.execute(
        sa.select(sa.func.count()).select_from(tasks_table)
        .where(tasks_table.c.project_id == proj_id)
    )
    total_count = total_result.scalar_one()
    await db.execute(
        projects_table.update().where(projects_table.c.id == proj_id)
        .values(completed_tasks=done_count, total_tasks=total_count)
    )
    await db.commit()
    log.info("Task %d deleted from project %d", task_id, proj_id)
    return {"deleted": True, "task_id": task_id}


# ══════════════════════════════════════════════════════════════════════════════
#  Routes – Project Analytics
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/projects/{project_id}/analytics", summary="Project analytics", tags=["Analytics"])
async def project_analytics(project_id: int, db: AsyncSession = Depends(get_db)):
    import json
    # Get project
    proj_result = await db.execute(sa.select(projects_table).where(projects_table.c.id == project_id))
    project = proj_result.mappings().first()
    if not project:
        raise HTTPException(404, f"Project {project_id} not found")

    # Task stats
    task_result = await db.execute(
        sa.select(tasks_table).where(tasks_table.c.project_id == project_id)
    )
    tasks = [dict(r) for r in task_result.mappings().all()]
    total = len(tasks)
    done = sum(1 for t in tasks if t["status"] == "done")
    in_progress = sum(1 for t in tasks if t["status"] == "in_progress")
    todo = sum(1 for t in tasks if t["status"] == "todo")

    # Priority breakdown
    high = sum(1 for t in tasks if t["priority"] == "high")
    medium = sum(1 for t in tasks if t["priority"] == "medium")
    low = sum(1 for t in tasks if t["priority"] == "low")

    # Workload by assignee
    workload = {}
    for t in tasks:
        name = t["assigned_name"] or "Unassigned"
        if name not in workload:
            workload[name] = {"total": 0, "done": 0, "in_progress": 0, "todo": 0, "hours": 0}
        workload[name]["total"] += 1
        workload[name][t["status"]] = workload[name].get(t["status"], 0) + 1
        workload[name]["hours"] += t["estimated_hours"] or 0

    # Total estimated hours
    total_hours = sum(t["estimated_hours"] or 0 for t in tasks)
    completed_hours = sum(t["estimated_hours"] or 0 for t in tasks if t["status"] == "done")

    return {
        "project": {"id": project["id"], "name": project["name"], "status": project["status"]},
        "progress": round(done / max(total, 1) * 100, 1),
        "task_summary": {
            "total": total, "done": done, "in_progress": in_progress, "todo": todo,
        },
        "priority_breakdown": {"high": high, "medium": medium, "low": low},
        "workload": [{"assignee": k, **v} for k, v in sorted(workload.items(), key=lambda x: -x[1]["total"])],
        "hours": {"total_estimated": round(total_hours, 1), "completed": round(completed_hours, 1)},
    }
