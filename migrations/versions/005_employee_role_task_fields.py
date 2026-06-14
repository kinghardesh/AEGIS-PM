"""Add 'employee' role + task scheduling/progress fields

Revision ID: 005_employee_role_task_fields
Revises: 004_email_required
Create Date: 2026-04-16 00:00:00.000000

Additive-only:
  - users.role CHECK is dropped and replaced to include 'employee'
    (existing rows are unaffected — 'user'/'admin'/'agent' still valid).
  - tasks gets four new nullable columns:
        start_date, end_date       planning window
        last_activity_at           touched on any progress update
        progress_pct               0..100

No existing columns are dropped or renamed. Every existing task row
simply has NULL for the new fields.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "005_employee_role_task_fields"
down_revision = "004_email_required"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Expand users.role CHECK to allow 'employee' ──────────────────────────
    # Migration 002 created the CHECK inline, which Postgres auto-names
    # `users_role_check`. Drop it by lookup (resilient to name differences
    # across dev DBs) and add a named replacement.
    op.execute(sa.text("""
        DO $$
        DECLARE
            cname TEXT;
        BEGIN
            SELECT conname INTO cname
              FROM pg_constraint
             WHERE conrelid = 'users'::regclass
               AND contype  = 'c'
               AND pg_get_constraintdef(oid) ILIKE '%role%IN%';
            IF cname IS NOT NULL THEN
                EXECUTE format('ALTER TABLE users DROP CONSTRAINT %I', cname);
            END IF;
        END $$;
    """))
    op.execute(sa.text(
        "ALTER TABLE users ADD CONSTRAINT users_role_check "
        "CHECK (role IN ('user','admin','agent','employee'))"
    ))

    # ── tasks: scheduling + progress fields ──────────────────────────────────
    op.execute(sa.text(
        "ALTER TABLE tasks ADD COLUMN IF NOT EXISTS start_date TIMESTAMPTZ"
    ))
    op.execute(sa.text(
        "ALTER TABLE tasks ADD COLUMN IF NOT EXISTS end_date TIMESTAMPTZ"
    ))
    op.execute(sa.text(
        "ALTER TABLE tasks ADD COLUMN IF NOT EXISTS last_activity_at TIMESTAMPTZ"
    ))
    op.execute(sa.text(
        "ALTER TABLE tasks ADD COLUMN IF NOT EXISTS progress_pct INTEGER "
        "NOT NULL DEFAULT 0 CHECK (progress_pct >= 0 AND progress_pct <= 100)"
    ))

    # Monitoring query ("tasks nearing deadline, ordered by last activity")
    # benefits from this index; cheap because it's partial.
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS idx_tasks_deadline "
        "ON tasks (end_date, status) "
        "WHERE status <> 'done' AND end_date IS NOT NULL"
    ))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS idx_tasks_last_activity "
        "ON tasks (assigned_to, last_activity_at DESC) "
        "WHERE assigned_to IS NOT NULL"
    ))


def downgrade() -> None:
    op.execute(sa.text("DROP INDEX IF EXISTS idx_tasks_last_activity"))
    op.execute(sa.text("DROP INDEX IF EXISTS idx_tasks_deadline"))
    op.execute(sa.text("ALTER TABLE tasks DROP COLUMN IF EXISTS progress_pct"))
    op.execute(sa.text("ALTER TABLE tasks DROP COLUMN IF EXISTS last_activity_at"))
    op.execute(sa.text("ALTER TABLE tasks DROP COLUMN IF EXISTS end_date"))
    op.execute(sa.text("ALTER TABLE tasks DROP COLUMN IF EXISTS start_date"))

    op.execute(sa.text("ALTER TABLE users DROP CONSTRAINT IF EXISTS users_role_check"))
    op.execute(sa.text(
        "ALTER TABLE users ADD CONSTRAINT users_role_check "
        "CHECK (role IN ('user','admin','agent'))"
    ))
