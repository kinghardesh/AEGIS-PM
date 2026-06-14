"""
aegis-pm / agents / reminder_agent.py

Reminder scheduler with atomic, persistent deduplication.

Dedup model
───────────
  Every attempt to send a reminder first tries to insert a row into
  `reminder_logs` with ON CONFLICT DO NOTHING. The table has a UNIQUE
  index on (user_id, task_id, reminder_type, reminder_date), so:

    - two workers racing on the same reminder → exactly one winner
    - container restart mid-run → previously-sent reminders stay recorded
    - the scheduler can safely run more often than once per day

Only the winner actually calls notify(). Everyone else short-circuits.

Reminder kinds:
  'deadline'  — task.end_date within REMINDER_DEADLINE_HOURS (default 24 h)
                and status != 'done'.
  'pending'   — task still 'todo' more than REMINDER_PENDING_DAYS (default 3)
                after start_date.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert

log = logging.getLogger("aegis.reminders")

REMINDER_DEADLINE_HOURS = int(os.getenv("REMINDER_DEADLINE_HOURS", "24"))
REMINDER_PENDING_DAYS   = int(os.getenv("REMINDER_PENDING_DAYS", "3"))


# ── Candidate queries ────────────────────────────────────────────────────────

async def _find_due_tasks(db) -> list[dict]:
    from api.main import tasks_table
    cutoff = datetime.now(timezone.utc) + timedelta(hours=REMINDER_DEADLINE_HOURS)
    rows = (
        await db.execute(
            sa.select(tasks_table).where(
                tasks_table.c.status != "done",
                tasks_table.c.end_date.is_not(None),
                tasks_table.c.end_date <= cutoff,
                tasks_table.c.end_date >= datetime.now(timezone.utc),
                tasks_table.c.assigned_to.is_not(None),
            )
        )
    ).mappings().all()
    return [dict(r) for r in rows]


async def _find_stalled_tasks(db) -> list[dict]:
    from api.main import tasks_table
    since = datetime.now(timezone.utc) - timedelta(days=REMINDER_PENDING_DAYS)
    rows = (
        await db.execute(
            sa.select(tasks_table).where(
                tasks_table.c.status == "todo",
                tasks_table.c.start_date.is_not(None),
                tasks_table.c.start_date <= since,
                tasks_table.c.assigned_to.is_not(None),
            )
        )
    ).mappings().all()
    return [dict(r) for r in rows]


async def _resolve_user_for_employee(db, employee_id: int) -> int | None:
    from api.models import users_table
    row = (
        await db.execute(
            sa.select(users_table.c.id).where(users_table.c.employee_id == employee_id)
        )
    ).first()
    return row[0] if row else None


# ── Atomic send ──────────────────────────────────────────────────────────────

async def _try_record_and_send(
    user_id: int,
    task: dict,
    kind: str,
    title: str,
    body: str,
) -> bool:
    """
    Atomically claim the (user, task, kind, today) slot and, on success,
    emit the in-app notification. Returns True iff we sent.
    """
    from api.main import SessionLocal
    from api.models import reminder_logs_table
    from api.notifications import notify

    today = datetime.now(timezone.utc).date()

    async with SessionLocal() as db:
        stmt = (
            pg_insert(reminder_logs_table)
            .values(
                user_id=user_id,
                task_id=task["id"],
                reminder_type=kind,
                reminder_date=today,
            )
            .on_conflict_do_nothing(
                index_elements=["user_id", "task_id", "reminder_type", "reminder_date"],
            )
        )
        result = await db.execute(stmt)
        await db.commit()
        # rowcount == 0 → another run already recorded this reminder today.
        if result.rowcount == 0:
            return False

        # Fire the notification in the same session so the sequence is
        # visible on the same connection — notify() handles its own commit.
        await notify(
            db,
            user_id=user_id,
            kind="task_update",
            title=title,
            body=body,
            resource_type="task",
            resource_id=task["id"],
        )
    return True


# ── Cycle ────────────────────────────────────────────────────────────────────

async def run_once() -> dict:
    """
    One reminder pass. Safe to call more than once per day — dedup is on
    the DB unique index, not in-memory.
    """
    from api.main import SessionLocal

    sent_deadline = 0
    sent_pending  = 0

    async with SessionLocal() as db:
        due     = await _find_due_tasks(db)
        stalled = await _find_stalled_tasks(db)

        due_users = []
        for t in due:
            u = await _resolve_user_for_employee(db, t["assigned_to"])
            if u is not None:
                due_users.append((u, t))
        stalled_users = []
        for t in stalled:
            u = await _resolve_user_for_employee(db, t["assigned_to"])
            if u is not None:
                stalled_users.append((u, t))

    for user_id, task in due_users:
        hours_left = max(
            0,
            int((task["end_date"] - datetime.now(timezone.utc)).total_seconds() / 3600),
        )
        ok = await _try_record_and_send(
            user_id=user_id,
            task=task,
            kind="deadline",
            title=f"Due soon: {task['title']}",
            body=f"Ends in ~{hours_left}h. Update your progress so the team stays aligned.",
        )
        if ok:
            sent_deadline += 1

    for user_id, task in stalled_users:
        ok = await _try_record_and_send(
            user_id=user_id,
            task=task,
            kind="pending",
            title=f"Still pending: {task['title']}",
            body="This task is still 'todo' past its start date — kick it off or ask for help.",
        )
        if ok:
            sent_pending += 1

    summary = {"deadline": sent_deadline, "pending": sent_pending}
    if sent_deadline or sent_pending:
        log.info("Reminders sent – deadline=%d pending=%d", sent_deadline, sent_pending)
    return summary


async def run_reminder_cycle() -> None:
    try:
        await run_once()
    except Exception as e:
        log.exception("Reminder cycle crashed: %s", e)
