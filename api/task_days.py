"""
aegis-pm / api / task_days.py

Day-by-day task breakdown + daily check-ins.

Endpoints (mounted under /employee/* for user-scope consistency):
  POST /employee/tasks/{task_id}/generate-days?days=N   idempotent — recreates entries
  GET  /employee/tasks/{task_id}/days
  POST /employee/tasks/{task_id}/days/{day_number}/check-in  {note, completed}
  DELETE /employee/tasks/{task_id}/days                  admin: reset the plan

Authorisation:
  - Assignee (users.employee_id == tasks.assigned_to) OR admin can read/write.
  - Anyone else → 403. Same rule as /employee/update-progress.

Day generation strategy:
  1. total_days = ceil((end_date - start_date).days) if both present
                  else max(1, round(estimated_hours / 8))
  2. Clamp 1..30.
  3. LLM (Groq/OpenAI-compatible) writes a 1-sentence plan per day based
     on title + description. Zero-temp so re-gens are stable.
  4. Fallback (no API key / quota): generic "Day N — make progress on X"
     prompts that are still honest but less specific.
"""
from __future__ import annotations

import json
import logging
import math
import os
from datetime import datetime, timezone
from typing import Optional

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import get_current_user
from api.models import task_day_entries_table

log = logging.getLogger("aegis.task_days")

MIN_DAYS = 1
MAX_DAYS = int(os.getenv("TASK_DAY_MAX", "30"))


router = APIRouter(prefix="/employee", tags=["Employee · Daily plan"])


# ── Schemas ──────────────────────────────────────────────────────────────────

class DayEntryOut(BaseModel):
    id:                  int
    task_id:             int
    day_number:          int
    planned_description: Optional[str]
    actual_note:         Optional[str]
    completed_at:        Optional[datetime]
    created_at:          datetime


class DayListOut(BaseModel):
    task_id:       int
    total_days:    int
    completed:     int
    progress_pct:  int
    entries:       list[DayEntryOut]


class CheckInRequest(BaseModel):
    note:       Optional[str] = Field(None, max_length=2000)
    completed:  bool = True


class GenerateResponse(BaseModel):
    task_id:    int
    total_days: int
    method:     str   # 'llm' | 'keyword'
    model:      Optional[str]
    entries:    list[DayEntryOut]


# ── Helpers ──────────────────────────────────────────────────────────────────

async def _load_task(db: AsyncSession, task_id: int) -> dict:
    from api.main import tasks_table
    row = (
        await db.execute(sa.select(tasks_table).where(tasks_table.c.id == task_id))
    ).mappings().first()
    if not row:
        raise HTTPException(404, f"Task {task_id} not found")
    return dict(row)


def _authorise(task: dict, user: dict) -> None:
    if user["role"] == "admin":
        return
    emp_id = user.get("employee_id")
    if emp_id is None or task.get("assigned_to") != emp_id:
        raise HTTPException(403, "You can only plan/check-in your own tasks")


def _infer_total_days(task: dict) -> int:
    start = task.get("start_date")
    end   = task.get("end_date")
    if start and end:
        delta_days = max(1, (end - start).days + 1)
    else:
        hours = float(task.get("estimated_hours") or 0)
        delta_days = max(1, math.ceil(hours / 8)) if hours > 0 else 1
    return max(MIN_DAYS, min(MAX_DAYS, delta_days))


async def _recompute_progress(db: AsyncSession, task_id: int) -> tuple[int, int, int]:
    """
    Count completed vs total day-entries and persist progress_pct on the
    task. Returns (total, completed, pct). Called on every check-in.
    """
    from api.main import tasks_table
    rows = (
        await db.execute(
            sa.select(
                sa.func.count().label("total"),
                sa.func.sum(
                    sa.case((task_day_entries_table.c.completed_at.is_not(None), 1), else_=0)
                ).label("done"),
            ).where(task_day_entries_table.c.task_id == task_id)
        )
    ).mappings().first()
    total = int(rows["total"] or 0)
    done  = int(rows["done"] or 0)
    pct   = int(round((done / total) * 100)) if total else 0

    now = datetime.now(timezone.utc)
    update_vals: dict = {
        "progress_pct":     pct,
        "last_activity_at": now,
    }
    # Auto-flip status to 'done' when all days complete; auto-flip to
    # 'in_progress' when the first day gets checked off.
    if total > 0 and done == total:
        update_vals["status"]       = "done"
        update_vals["completed_at"] = now
    elif done > 0:
        update_vals["status"] = "in_progress"

    await db.execute(
        tasks_table.update().where(tasks_table.c.id == task_id).values(**update_vals)
    )
    await db.commit()
    return total, done, pct


# ── LLM day plan ─────────────────────────────────────────────────────────────

_DAY_SYSTEM = (
    "You are an engineering tech lead. Given a task, break it into a concrete "
    "per-day plan. Each day should be one actionable sentence. Avoid vague "
    "words like 'work on' or 'continue'. Return strict JSON — no prose."
)


async def _llm_day_plan(title: str, description: str, total_days: int) -> tuple[list[str], str | None]:
    """Returns (plan[N], model_name) or ([], None) on failure."""
    from api.prd_parser import _chat_client

    client, model = _chat_client()
    if not client:
        return [], None

    user_msg = (
        f"Task: {title}\n"
        f"Description: {description or '(no description)'}\n"
        f"Days available: {total_days}\n\n"
        "Return JSON exactly like:\n"
        "{\n"
        f"  \"days\": [\"day 1 plan\", \"day 2 plan\", ... {total_days} items]\n"
        "}\n"
        "Each entry should be a single imperative sentence (≤ 120 chars)."
    )
    try:
        resp = await client.chat.completions.create(
            model=model,
            temperature=0,
            messages=[
                {"role": "system", "content": _DAY_SYSTEM},
                {"role": "user",   "content": user_msg},
            ],
            response_format={"type": "json_object"},
        )
        raw = resp.choices[0].message.content or "{}"
        data = json.loads(raw)
    except Exception as e:
        log.warning("day plan llm call failed: %s: %s", type(e).__name__, e)
        return [], None

    days = data.get("days")
    if not isinstance(days, list):
        return [], None
    cleaned: list[str] = []
    for d in days[:total_days]:
        if not isinstance(d, str):
            continue
        s = " ".join(d.split()).strip()
        if s:
            cleaned.append(s[:200])
    return cleaned, model


def _keyword_day_plan(title: str, total_days: int) -> list[str]:
    """Generic fallback — honest and labeled but not fake-specific."""
    if total_days == 1:
        return [f"Complete {title}"]
    plans = [f"Kick off {title}: scope and outline approach"]
    for d in range(2, total_days):
        plans.append(f"Day {d}: advance implementation / unblock remaining items")
    plans.append(f"Final day: polish, verify, and wrap up {title}")
    return plans[:total_days]


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/tasks/{task_id}/generate-days", response_model=GenerateResponse)
async def generate_days(
    task_id: int,
    days:    Optional[int] = Query(None, ge=1, le=MAX_DAYS, description="Override inferred day count"),
    user:    dict = Depends(get_current_user),
):
    from api.main import SessionLocal

    async with SessionLocal() as db:
        task = await _load_task(db, task_id)
        _authorise(task, user)

        total_days = days or _infer_total_days(task)

        # Produce the plan. LLM first, fall back to keyword generator.
        plan, model = await _llm_day_plan(
            task.get("title") or "", task.get("description") or "", total_days
        )
        method = "llm" if plan else "keyword"
        if not plan:
            plan = _keyword_day_plan(task.get("title") or f"task {task_id}", total_days)

        # Pad if the model returned fewer rows than requested.
        while len(plan) < total_days:
            plan.append(f"Day {len(plan) + 1}: continue the work")
        plan = plan[:total_days]

        # Idempotent: clear existing rows, then insert the fresh plan.
        await db.execute(
            task_day_entries_table.delete().where(task_day_entries_table.c.task_id == task_id)
        )
        await db.execute(
            task_day_entries_table.insert(),
            [
                {
                    "task_id":             task_id,
                    "day_number":          idx + 1,
                    "planned_description": plan[idx],
                }
                for idx in range(total_days)
            ],
        )
        await db.commit()

        entries_rows = (
            await db.execute(
                sa.select(task_day_entries_table)
                .where(task_day_entries_table.c.task_id == task_id)
                .order_by(task_day_entries_table.c.day_number)
            )
        ).mappings().all()

        # Reset progress since we just rewrote the plan.
        await _recompute_progress(db, task_id)

    log.info(
        "generate-days: task=%d total=%d method=%s actor=%s",
        task_id, total_days, method, user["user_id"],
    )
    return GenerateResponse(
        task_id=task_id,
        total_days=total_days,
        method=method,
        model=model,
        entries=[DayEntryOut(**dict(r)) for r in entries_rows],
    )


@router.get("/tasks/{task_id}/days", response_model=DayListOut)
async def list_days(task_id: int, user: dict = Depends(get_current_user)):
    from api.main import SessionLocal
    async with SessionLocal() as db:
        task = await _load_task(db, task_id)
        _authorise(task, user)
        rows = (
            await db.execute(
                sa.select(task_day_entries_table)
                .where(task_day_entries_table.c.task_id == task_id)
                .order_by(task_day_entries_table.c.day_number)
            )
        ).mappings().all()

    completed = sum(1 for r in rows if r["completed_at"] is not None)
    total = len(rows)
    pct = int(round((completed / total) * 100)) if total else 0
    return DayListOut(
        task_id=task_id,
        total_days=total,
        completed=completed,
        progress_pct=pct,
        entries=[DayEntryOut(**dict(r)) for r in rows],
    )


@router.post("/tasks/{task_id}/days/{day_number}/check-in")
async def check_in(
    task_id:     int,
    day_number:  int,
    body:        CheckInRequest,
    user:        dict = Depends(get_current_user),
):
    from api.main import SessionLocal
    from api.notifications import notify_admins

    async with SessionLocal() as db:
        task = await _load_task(db, task_id)
        _authorise(task, user)

        entry_row = (
            await db.execute(
                sa.select(task_day_entries_table)
                .where(
                    task_day_entries_table.c.task_id == task_id,
                    task_day_entries_table.c.day_number == day_number,
                )
            )
        ).mappings().first()
        if not entry_row:
            raise HTTPException(404, f"Day {day_number} of task {task_id} not found")

        update_vals = {"actual_note": body.note}
        if body.completed:
            update_vals["completed_at"] = datetime.now(timezone.utc)
        else:
            update_vals["completed_at"] = None

        await db.execute(
            task_day_entries_table.update()
            .where(task_day_entries_table.c.id == entry_row["id"])
            .values(**update_vals)
        )
        await db.commit()

        total, done, pct = await _recompute_progress(db, task_id)

        # Tell admins — their monitoring table + WS bell update live.
        try:
            await notify_admins(
                db,
                kind="task_update",
                title=f"{user['user_id']} checked in day {day_number}",
                body=(
                    f"{task['title']} · {done}/{total} days · {pct}%"
                    + (f" — {body.note}" if body.note else "")
                ),
                resource_type="task",
                resource_id=task_id,
                actor_user_id=user["id"],
            )
        except Exception as e:
            log.warning("check-in notify_admins failed task=%d: %s", task_id, e)

    return {
        "task_id":      task_id,
        "day_number":   day_number,
        "completed":    bool(update_vals.get("completed_at")),
        "total_days":   total,
        "completed_days": done,
        "progress_pct": pct,
    }


@router.delete("/tasks/{task_id}/days")
async def reset_days(task_id: int, user: dict = Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(403, "Admin only")
    from api.main import SessionLocal
    async with SessionLocal() as db:
        await _load_task(db, task_id)   # 404 if task missing
        result = await db.execute(
            task_day_entries_table.delete().where(task_day_entries_table.c.task_id == task_id)
        )
        await db.commit()
        await _recompute_progress(db, task_id)
    return {"task_id": task_id, "removed": result.rowcount}
