"""
aegis-pm / agents / executors / project_poller.py

ProjectPoller – unlike the per-label Jira pollers, this one polls the Aegis PM
`tasks` table directly and runs the right executor for each task.

Workflow per cycle
──────────────────
  1. SELECT tasks WHERE agent_type IS NOT NULL
                    AND executor_status = 'queued'
                    AND status IN ('todo', 'in_progress')
     ORDER BY priority DESC, created_at ASC
     LIMIT EXEC_MAX_TASKS_PER_CYCLE
  2. For each task:
       - lock: UPDATE … SET executor_status='running', status='in_progress'
       - look up the executor class from EXECUTORS[agent_type]
       - call executor.produce_deliverable(task.title, task.description)
       - on success: store executor_output, mark 'done', status='done',
                     completed_at=NOW()
       - on failure: mark 'failed', store executor_error, status='todo'
  3. Return a summary dict for the health tracker

This runs on APScheduler on the agents container and is health-tracked under
AgentName.PROJECT_POLLER.
"""
from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

from agents.executors import EXECUTORS

load_dotenv()
log = logging.getLogger("aegis.exec.poller")


# ── DB config (same pattern as the other agent modules) ──────────────────────

DB_PARAMS: Dict[str, str] = {
    "host":     os.getenv("POSTGRES_HOST", "localhost"),
    "port":     os.getenv("POSTGRES_PORT", "5432"),
    "dbname":   os.getenv("POSTGRES_DB",   "aegispm"),
    "user":     os.getenv("POSTGRES_USER", "aegis"),
    "password": os.getenv("POSTGRES_PASSWORD", ""),
}

EXEC_MAX_TASKS_PER_CYCLE = int(os.getenv("EXEC_MAX_TASKS_PER_CYCLE", "3"))


class ProjectPoller:
    """
    Polls the Aegis PM tasks table and runs executors against queued tasks.
    One instance, invoked by APScheduler on its own cadence.
    """

    def run_once(self) -> Dict[str, Any]:
        log.info("━━━ ProjectPoller cycle start ━━━")

        tasks = self._claim_tasks(limit=EXEC_MAX_TASKS_PER_CYCLE)
        if not tasks:
            log.debug("No queued tasks")
            return {"tasks_claimed": 0, "tasks_done": 0, "tasks_failed": 0, "results": []}

        log.info("Claimed %d task(s) for execution", len(tasks))
        done:   List[Dict[str, Any]] = []
        failed: List[Dict[str, Any]] = []

        for task in tasks:
            task_id    = task["id"]
            agent_type = task["agent_type"]
            title      = task.get("title") or ""
            desc       = task.get("description") or ""

            executor_cls = EXECUTORS.get(agent_type)
            if executor_cls is None:
                log.warning("Task %d has unknown agent_type=%r; marking failed",
                            task_id, agent_type)
                self._mark_failed(task_id, f"Unknown agent_type '{agent_type}'")
                failed.append({"task_id": task_id, "error": "unknown agent"})
                continue

            log.info("→ Task %d │ %s │ '%s'", task_id, agent_type, title[:70])
            t0 = time.perf_counter()
            try:
                executor = executor_cls()
                deliverable = executor.produce_deliverable(
                    task_key=f"TASK-{task_id}",
                    summary=title,
                    description=desc,
                )
                duration_ms = (time.perf_counter() - t0) * 1000
                self._mark_done(task_id, deliverable)
                log.info("✓ Task %d done by %s in %.0fms", task_id, agent_type, duration_ms)
                done.append({
                    "task_id":     task_id,
                    "agent_type":  agent_type,
                    "duration_ms": duration_ms,
                })
            except Exception as exc:
                log.exception("✗ Task %d failed: %s", task_id, exc)
                self._mark_failed(task_id, str(exc))
                failed.append({
                    "task_id":    task_id,
                    "agent_type": agent_type,
                    "error":      str(exc)[:200],
                })

        summary = {
            "tasks_claimed": len(tasks),
            "tasks_done":    len(done),
            "tasks_failed":  len(failed),
            "results":       done + failed,
        }
        log.info(
            "━━━ ProjectPoller cycle end │ claimed=%d │ done=%d │ failed=%d ━━━",
            summary["tasks_claimed"], summary["tasks_done"], summary["tasks_failed"],
        )
        return summary

    # ── DB helpers ────────────────────────────────────────────────────────────

    def _claim_tasks(self, limit: int) -> List[Dict[str, Any]]:
        """
        Atomically claim up to `limit` queued tasks. Uses SELECT … FOR UPDATE
        SKIP LOCKED so multiple pollers (if ever) never double-claim.
        """
        sql_select = """
            SELECT id, title, description, agent_type, priority, created_at
            FROM   tasks
            WHERE  agent_type IS NOT NULL
              AND  executor_status = 'queued'
              AND  status IN ('todo', 'in_progress')
            ORDER  BY
              CASE priority WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END,
              created_at
            LIMIT  %(limit)s
            FOR UPDATE SKIP LOCKED
        """
        sql_update = """
            UPDATE tasks
            SET    executor_status = 'running',
                   status = 'in_progress'
            WHERE  id = ANY(%(ids)s)
        """
        conn = None
        try:
            conn = psycopg2.connect(**DB_PARAMS)
            conn.autocommit = False
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql_select, {"limit": limit})
                rows = cur.fetchall()
                if not rows:
                    conn.commit()
                    return []
                ids = [r["id"] for r in rows]
                cur.execute(sql_update, {"ids": ids})
            conn.commit()
            return [dict(r) for r in rows]
        except Exception as exc:
            if conn:
                conn.rollback()
            log.error("claim_tasks failed: %s", exc, exc_info=True)
            return []
        finally:
            if conn:
                conn.close()

    def _mark_done(self, task_id: int, deliverable: str) -> None:
        sql = """
            UPDATE tasks
            SET    executor_status = 'done',
                   executor_output = %(out)s,
                   executor_error  = NULL,
                   executor_run_at = NOW(),
                   status          = 'done',
                   completed_at    = NOW()
            WHERE  id = %(id)s
        """
        self._run_sql(sql, {"id": task_id, "out": deliverable})

    def _mark_failed(self, task_id: int, error: str) -> None:
        sql = """
            UPDATE tasks
            SET    executor_status = 'failed',
                   executor_error  = %(err)s,
                   executor_run_at = NOW(),
                   status          = 'todo'
            WHERE  id = %(id)s
        """
        self._run_sql(sql, {"id": task_id, "err": error[:2000]})

    def _run_sql(self, sql: str, params: Dict[str, Any]) -> None:
        conn = None
        try:
            conn = psycopg2.connect(**DB_PARAMS)
            with conn.cursor() as cur:
                cur.execute(sql, params)
            conn.commit()
        except Exception as exc:
            if conn:
                conn.rollback()
            log.error("SQL update failed: %s", exc, exc_info=True)
        finally:
            if conn:
                conn.close()
