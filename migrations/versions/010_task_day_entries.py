"""Add task_day_entries: day-by-day plan + daily check-ins per task

Revision ID: 010_task_day_entries
Revises: 009_prd_documents
Create Date: 2026-04-17 00:00:00.000000

When a task is assigned, we break it into N daily entries (N derived
from start_date/end_date or estimated_hours). Each entry holds the
planned scope for that day and an `actual_note` the assignee writes
when they check off the day. Progress percent on the parent task is
kept in lockstep with (completed_days / total_days).

Purely additive — tasks table unchanged.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "010_task_day_entries"
down_revision = "009_prd_documents"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS task_day_entries (
            id                   SERIAL PRIMARY KEY,
            task_id              INTEGER      NOT NULL
                                 REFERENCES tasks(id) ON DELETE CASCADE,
            day_number           INTEGER      NOT NULL CHECK (day_number >= 1),
            planned_description  TEXT,
            actual_note          TEXT,
            completed_at         TIMESTAMPTZ,
            created_at           TIMESTAMPTZ  NOT NULL DEFAULT NOW()
        )
    """))
    op.execute(sa.text(
        "CREATE UNIQUE INDEX IF NOT EXISTS task_day_entries_unique "
        "ON task_day_entries (task_id, day_number)"
    ))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS idx_task_day_entries_task "
        "ON task_day_entries (task_id, day_number)"
    ))


def downgrade() -> None:
    op.execute(sa.text("DROP TABLE IF EXISTS task_day_entries"))
