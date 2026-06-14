"""
aegis-pm / api / balancer_router.py

Admin endpoints that call `api.balancer.balance_assign()` against the
live employee pool.

  POST /admin/tasks/{task_id}/balance-assign
    body: { confirm?: bool, priority_override?: "high|medium|low" }
    returns:
      {
        "task_id":         int,
        "priority":        str,
        "ai_share":        float,     # current AI fraction of active load
        "human_share":     float,
        "recommendations": [
          {
            "member_id": ..., "member_name": ..., "member_type": "AI|HUMAN",
            "score": ..., "skill_match": ..., "workload_score": ...,
            "balance_score": ..., "priority_score": ..., "reason": ...,
            "current_load": int
          }, ...
        ],
        "assigned": { employee_id, name, type, score } | null
      }

  GET  /admin/tasks/unassigned     — unassigned tasks with their top pick.

Classification:
  Employees whose email ends with `@aegis.ai` are AI; everyone else is
  HUMAN. This mirrors the convention used by
  /team/add-ai-agents.
"""
from __future__ import annotations

import json
import logging
from typing import Optional

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from api.auth import require_admin
from api.balancer import BalanceMember, balance_assign
from api.models import users_table

log = logging.getLogger("aegis.balancer")

router = APIRouter(
    prefix="/admin",
    tags=["Admin · Balancer"],
    dependencies=[Depends(require_admin)],
)


class BalanceAssignRequest(BaseModel):
    confirm:            bool = False
    priority_override:  Optional[str] = Field(None, pattern=r"^(high|medium|low)$")


# ── Helpers ──────────────────────────────────────────────────────────────────

def _classify(email: Optional[str]) -> str:
    return "AI" if (email or "").lower().endswith("@aegis.ai") else "HUMAN"


async def _load_members(db) -> list[BalanceMember]:
    """
    Build the BalanceMember list from live DB state:
      - every `available` employee
      - their current_load = count of their tasks in ('todo','in_progress')
      - skills parsed from employees.skills JSON
    One round-trip for employees + one for loads — O(2) queries, not N.
    """
    from api.main import employees_table, tasks_table, EXECUTORS_ENABLED

    emp_query = sa.select(employees_table).where(
        employees_table.c.availability == "available"
    )
    # With executors disabled, drop the AI agent records (@aegis.ai) from the
    # candidate pool so the balancer only ever assigns work to humans.
    if not EXECUTORS_ENABLED:
        emp_query = emp_query.where(
            sa.not_(employees_table.c.email.ilike("%@aegis.ai"))
        )
    emp_rows = (await db.execute(emp_query)).mappings().all()

    # Batch the load query — no N+1.
    load_rows = (
        await db.execute(
            sa.select(
                tasks_table.c.assigned_to,
                sa.func.count().label("n"),
            )
            .where(
                tasks_table.c.assigned_to.is_not(None),
                tasks_table.c.status.in_(("todo", "in_progress")),
            )
            .group_by(tasks_table.c.assigned_to)
        )
    ).all()
    load_by_id = {row.assigned_to: row.n for row in load_rows}

    members: list[BalanceMember] = []
    for r in emp_rows:
        try:
            skills = json.loads(r["skills"] or "[]")
        except Exception:
            skills = []
        members.append(BalanceMember(
            id=r["id"],
            name=r["name"],
            type=_classify(r["email"]),
            skills=frozenset(s.strip().lower() for s in skills if str(s).strip()),
            current_load=int(load_by_id.get(r["id"], 0)),
        ))
    return members


# ── 1) Single-task balance-assign ────────────────────────────────────────────

@router.post("/tasks/{task_id}/balance-assign")
async def balance_assign_task(
    task_id: int,
    body:    BalanceAssignRequest = BalanceAssignRequest(),
    admin:   dict = Depends(require_admin),
):
    from api.main import SessionLocal, tasks_table, projects_table

    async with SessionLocal() as db:
        task_row = (
            await db.execute(sa.select(tasks_table).where(tasks_table.c.id == task_id))
        ).mappings().first()
        if not task_row:
            raise HTTPException(404, f"Task {task_id} not found")

        try:
            req_skills = json.loads(task_row.get("required_skills") or "[]")
        except Exception:
            req_skills = []

        priority = (
            body.priority_override
            or (task_row.get("priority") or "medium").lower()
        )

        members = await _load_members(db)
        if not members:
            raise HTTPException(400, "No available employees to assign")

        ranked = balance_assign(req_skills, priority, members, top_n=5)
        if not ranked:
            raise HTTPException(400, "Balancer produced no candidates")

        # Current type-split (helpful for the UI badge).
        ai_load    = sum(m.current_load for m in members if m.type == "AI")
        human_load = sum(m.current_load for m in members if m.type == "HUMAN")
        total      = max(1, ai_load + human_load)
        ai_share    = round(ai_load / total, 3)
        human_share = round(human_load / total, 3)

        assigned_info = None
        if body.confirm:
            pick = ranked[0]
            await db.execute(
                tasks_table.update()
                .where(tasks_table.c.id == task_id)
                .values(
                    assigned_to=pick.member_id,
                    assigned_name=pick.member_name,
                    ai_confidence=pick.score,
                )
            )
            await db.commit()

            # WS notify the linked user (if any) so their dashboard refreshes live.
            try:
                from api.notifications import notify
                target_user = (
                    await db.execute(
                        sa.select(users_table.c.id)
                        .where(users_table.c.employee_id == pick.member_id)
                    )
                ).first()
                if target_user:
                    proj_row = (
                        await db.execute(
                            sa.select(projects_table.c.name)
                            .where(projects_table.c.id == task_row["project_id"])
                        )
                    ).first()
                    pname = proj_row[0] if proj_row else ""
                    await notify(
                        db,
                        user_id=target_user[0],
                        kind="task_assigned",
                        title=f"New task: {task_row['title']}",
                        body=(
                            f"Balancer assigned you this task "
                            f"(score {int(pick.score * 100)}%)"
                            + (f" · {pname}" if pname else "")
                        ),
                        resource_type="task",
                        resource_id=task_id,
                        actor_user_id=admin["id"],
                    )
            except Exception as e:
                log.warning("balance-assign notify failed task=%d: %s", task_id, e)

            assigned_info = {
                "employee_id": pick.member_id,
                "name":        pick.member_name,
                "type":        pick.member_type,
                "score":       pick.score,
            }
            log.info(
                "balance-assign: task=%d → %s [%s] score=%.3f",
                task_id, pick.member_name, pick.member_type, pick.score,
            )

        return {
            "task_id":  task_id,
            "priority": priority,
            "ai_share":    ai_share,
            "human_share": human_share,
            "recommendations": [
                {
                    "member_id":      r.member_id,
                    "member_name":    r.member_name,
                    "member_type":    r.member_type,
                    "score":          r.score,
                    "skill_match":    r.skill_match,
                    "workload_score": r.workload_score,
                    "balance_score":  r.balance_score,
                    "priority_score": r.priority_score,
                    "reason":         r.reason,
                    "current_load":   next(
                        (m.current_load for m in members if m.id == r.member_id), 0
                    ),
                }
                for r in ranked
            ],
            "assigned": assigned_info,
        }


# ── 1b) Bulk: balance-assign every unassigned task in a project ─────────────

@router.post("/projects/{project_id}/balance-assign-all")
async def balance_assign_project(
    project_id:       int,
    include_assigned: bool = Query(True, description="Also re-evaluate already-assigned open tasks"),
    admin:            dict = Depends(require_admin),
):
    """
    Run the balancer over every open task in the project.

    Default behaviour (`include_assigned=True`) — re-evaluates tasks
    that already have an owner, in case a better skill match exists on
    the team now (e.g. a human employee with the right skills was
    onboarded after the initial "AI assign" pass). Existing in-progress
    tasks are still included: if the balancer keeps the same owner,
    nothing user-visible changes. When the owner changes, we emit a
    fresh notification to the new assignee.

    Set `include_assigned=false` to restore the old "only brand-new
    tasks" behaviour.

    Mutates member load in-memory between iterations so a batch of 10
    tasks doesn't all pile on the currently least-loaded person.
    """
    from api.main import SessionLocal, tasks_table, projects_table
    from api.notifications import notify
    from dataclasses import replace

    async with SessionLocal() as db:
        where = [
            tasks_table.c.project_id == project_id,
            tasks_table.c.status.in_(("todo", "in_progress")),
        ]
        if not include_assigned:
            where.append(tasks_table.c.assigned_to.is_(None))

        tasks_rows = (
            await db.execute(
                sa.select(tasks_table)
                .where(*where)
                .order_by(
                    sa.case(
                        (tasks_table.c.priority == "high", 1),
                        (tasks_table.c.priority == "medium", 2),
                        (tasks_table.c.priority == "low", 3),
                        else_=4,
                    ),
                    tasks_table.c.created_at,
                )
            )
        ).mappings().all()

        if not tasks_rows:
            return {
                "assigned":   0,
                "new":        0,
                "reassigned": 0,
                "unchanged":  0,
                "results":    [],
            }

        members = await _load_members(db)
        if not members:
            raise HTTPException(400, "No available employees to assign")

        # Index members by id so we can increment load between iterations.
        by_id: dict[int, BalanceMember] = {m.id: m for m in members}

        # Project name for notification body.
        proj_row = (
            await db.execute(
                sa.select(projects_table.c.name).where(projects_table.c.id == project_id)
            )
        ).first()
        project_name = proj_row[0] if proj_row else ""

        results: list[dict] = []
        new_count        = 0    # task was unassigned → now has an owner
        reassigned_count = 0    # owner changed
        unchanged_count  = 0    # balancer picked the existing owner

        for row in tasks_rows:
            try:
                req_skills = json.loads(row.get("required_skills") or "[]")
            except Exception:
                req_skills = []
            priority = (row.get("priority") or "medium").lower()

            ranked = balance_assign(
                req_skills, priority, list(by_id.values()), top_n=1
            )
            if not ranked:
                continue
            pick = ranked[0]

            prev_assignee = row.get("assigned_to")
            outcome: str
            if prev_assignee is None:
                outcome = "new"
                new_count += 1
            elif prev_assignee == pick.member_id:
                outcome = "unchanged"
                unchanged_count += 1
            else:
                outcome = "reassigned"
                reassigned_count += 1

            # Skip writing if nothing would change — avoids spurious WS
            # events bouncing identical notifications at the assignee.
            if outcome != "unchanged":
                await db.execute(
                    tasks_table.update()
                    .where(tasks_table.c.id == row["id"])
                    .values(
                        assigned_to=pick.member_id,
                        assigned_name=pick.member_name,
                        ai_confidence=pick.score,
                    )
                )

            # Load bookkeeping: on reassignment, decrement the previous
            # owner and increment the new one so the next iteration's
            # balancer sees the accurate split.
            if outcome == "reassigned" and prev_assignee in by_id:
                old = by_id[prev_assignee]
                by_id[prev_assignee] = replace(
                    old, current_load=max(0, old.current_load - 1)
                )
            if outcome in ("new", "reassigned"):
                cur = by_id[pick.member_id]
                by_id[pick.member_id] = replace(
                    cur, current_load=cur.current_load + 1
                )

            results.append({
                "task_id":     row["id"],
                "task_title":  row["title"],
                "member_id":   pick.member_id,
                "member_name": pick.member_name,
                "member_type": pick.member_type,
                "score":       pick.score,
                "outcome":     outcome,
            })

        total_assigned = new_count + reassigned_count

        await db.commit()

        # Notify only the tasks whose owner actually changed — re-firing
        # the same notification at someone who already owns a task is
        # noise.
        changed = [r for r in results if r["outcome"] in ("new", "reassigned")]
        emp_ids = {r["member_id"] for r in changed}
        if emp_ids:
            user_rows = (
                await db.execute(
                    sa.select(users_table.c.id, users_table.c.employee_id)
                    .where(users_table.c.employee_id.in_(emp_ids))
                )
            ).all()
            emp_to_user = {eid: uid for (uid, eid) in user_rows}
            for r in changed:
                target = emp_to_user.get(r["member_id"])
                if not target:
                    continue
                try:
                    await notify(
                        db,
                        user_id=target,
                        kind="task_assigned",
                        title=f"New task: {r['task_title']}",
                        body=(
                            f"Auto-assigned (match {int(r['score'] * 100)}%)"
                            + (f" · {project_name}" if project_name else "")
                        ),
                        resource_type="task",
                        resource_id=r["task_id"],
                        actor_user_id=admin["id"],
                    )
                except Exception as e:
                    log.warning(
                        "balance-assign-all notify failed task=%d: %s",
                        r["task_id"], e,
                    )

    log.info(
        "balance-assign-all: project=%d new=%d reassigned=%d unchanged=%d",
        project_id, new_count, reassigned_count, unchanged_count,
    )
    return {
        "assigned":   total_assigned,
        "new":        new_count,
        "reassigned": reassigned_count,
        "unchanged":  unchanged_count,
        "results":    results,
    }


# ── 2) List unassigned tasks + pre-computed top recommendation ───────────────

@router.get("/tasks/unassigned")
async def unassigned_tasks(
    limit: int = Query(20, ge=1, le=100),
):
    """
    Returns up to `limit` unassigned tasks, each decorated with the top
    balancer pick so the admin UI can render a one-click "Assign"
    button per row without a follow-up call.
    """
    from api.main import SessionLocal, tasks_table

    async with SessionLocal() as db:
        rows = (
            await db.execute(
                sa.select(tasks_table)
                .where(
                    tasks_table.c.assigned_to.is_(None),
                    tasks_table.c.status.in_(("todo", "in_progress")),
                )
                .order_by(
                    sa.case(
                        (tasks_table.c.priority == "high", 1),
                        (tasks_table.c.priority == "medium", 2),
                        (tasks_table.c.priority == "low", 3),
                        else_=4,
                    ),
                    tasks_table.c.created_at.desc(),
                )
                .limit(limit)
            )
        ).mappings().all()

        # Load members ONCE and reuse for every task — huge win for
        # projects with many unassigned tasks.
        members = await _load_members(db)

    out = []
    for row in rows:
        try:
            req_skills = json.loads(row.get("required_skills") or "[]")
        except Exception:
            req_skills = []
        priority = (row.get("priority") or "medium").lower()
        ranked = balance_assign(req_skills, priority, members, top_n=1)
        pick = ranked[0] if ranked else None

        out.append({
            "task_id":        row["id"],
            "title":          row["title"],
            "priority":       priority,
            "required_skills": req_skills,
            "project_id":     row["project_id"],
            "recommended": (
                {
                    "member_id":   pick.member_id,
                    "member_name": pick.member_name,
                    "member_type": pick.member_type,
                    "score":       pick.score,
                    "reason":      pick.reason,
                }
                if pick else None
            ),
        })
    return out
