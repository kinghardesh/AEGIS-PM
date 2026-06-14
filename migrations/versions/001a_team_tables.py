"""Team tables: employees, projects, tasks (with executor columns)

Revision ID: 001a_team_tables
Revises: 001_baseline
Create Date: 2026-04-16 00:00:00.000000

These tables existed in the running DB because the old `metadata.create_all`
safety-net in api/main.py lifespan silently created them at boot. When we
removed `create_all` and switched to Alembic-only schema management, they
needed a proper migration. This migration backfills that and must run
before 002_auth_notifications_activity (which declares an FK into employees).

All DDL is IF NOT EXISTS so deploys that ran against the old boot-time
creator keep working without surprises.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "001a_team_tables"
down_revision = "001_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── employees ────────────────────────────────────────────────────────────
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS employees (
            id            SERIAL PRIMARY KEY,
            name          VARCHAR(255) NOT NULL,
            email         VARCHAR(255),
            role          VARCHAR(128),
            skills        TEXT,                             -- JSON array as text
            availability  VARCHAR(32) NOT NULL DEFAULT 'available',
            current_load  INTEGER NOT NULL DEFAULT 0,
            created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS idx_employees_name ON employees (name)"
    ))

    # ── projects ─────────────────────────────────────────────────────────────
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS projects (
            id              SERIAL PRIMARY KEY,
            name            VARCHAR(255) NOT NULL,
            description     TEXT,
            prd_text        TEXT,
            status          VARCHAR(32) NOT NULL DEFAULT 'active',
            total_tasks     INTEGER NOT NULL DEFAULT 0,
            completed_tasks INTEGER NOT NULL DEFAULT 0,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS idx_projects_status ON projects (status)"
    ))

    # ── tasks (with executor-agent columns) ──────────────────────────────────
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS tasks (
            id               SERIAL PRIMARY KEY,
            project_id       INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            title            VARCHAR(500) NOT NULL,
            description      TEXT,
            priority         VARCHAR(32) NOT NULL DEFAULT 'medium',
            status           VARCHAR(32) NOT NULL DEFAULT 'todo',
            estimated_hours  REAL NOT NULL DEFAULT 0,
            assigned_to      INTEGER REFERENCES employees(id) ON DELETE SET NULL,
            assigned_name    VARCHAR(255),
            ai_confidence    REAL,
            required_skills  TEXT,                          -- JSON array as text
            created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            completed_at     TIMESTAMPTZ,
            agent_type       VARCHAR(32),
            executor_status  VARCHAR(32),
            executor_output  TEXT,
            executor_error   TEXT,
            executor_run_at  TIMESTAMPTZ
        )
    """))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS idx_tasks_project ON tasks (project_id)"
    ))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS idx_tasks_assigned_to ON tasks (assigned_to) "
        "WHERE assigned_to IS NOT NULL"
    ))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks (status)"
    ))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS idx_tasks_executor_queue "
        "ON tasks (executor_status, priority DESC, created_at) "
        "WHERE executor_status IN ('queued', 'running')"
    ))


def downgrade() -> None:
    op.execute(sa.text("DROP TABLE IF EXISTS tasks"))
    op.execute(sa.text("DROP TABLE IF EXISTS projects"))
    op.execute(sa.text("DROP TABLE IF EXISTS employees"))
