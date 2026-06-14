"""Add users, notifications, activity_log; extend alerts with assignment + completion

Revision ID: 002_auth_notifications_activity
Revises: 001_baseline
Create Date: 2026-04-16 00:00:00.000000

Adds:
  - users                (human + admin + agent rows; unified identity table)
  - user_sessions        (multi-device session tracking for activity monitoring)
  - notifications        (in-app notifications, fanned out over WebSockets)
  - activity_log         (every authenticated request — admin visibility)
  - alerts.assignee_user_id    FK → users.id (who owns the alert)
  - alerts.completed_by_user_id FK → users.id (who completed it)
  - alerts.completed_at         TIMESTAMPTZ
  - alerts.status CHECK expanded to include 'completed'
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "002_auth_notifications_activity"
down_revision = "001a_team_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── users ────────────────────────────────────────────────────────────────
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS users (
            id               SERIAL PRIMARY KEY,
            user_id          VARCHAR(64)  NOT NULL UNIQUE,   -- login handle
            email            VARCHAR(255) UNIQUE,
            full_name        VARCHAR(255),
            password_hash    TEXT         NOT NULL,          -- bcrypt
            role             VARCHAR(16)  NOT NULL DEFAULT 'user'
                             CHECK (role IN ('user', 'admin', 'agent')),
            employee_id      INTEGER REFERENCES employees(id) ON DELETE SET NULL,
            is_active        BOOLEAN      NOT NULL DEFAULT TRUE,
            last_login_at    TIMESTAMPTZ,
            created_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
            updated_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW()
        )
    """))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS idx_users_role ON users (role)"))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS idx_users_email ON users (email)"))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS idx_users_employee ON users (employee_id)"))

    # ── user_sessions (multi-device) ─────────────────────────────────────────
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS user_sessions (
            id            SERIAL PRIMARY KEY,
            user_id       INTEGER      NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            jti           VARCHAR(64)  NOT NULL UNIQUE,      -- JWT id
            device        VARCHAR(255),
            user_agent    TEXT,
            ip_address    VARCHAR(64),
            revoked       BOOLEAN      NOT NULL DEFAULT FALSE,
            created_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
            last_seen_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
            expires_at    TIMESTAMPTZ  NOT NULL
        )
    """))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS idx_sessions_user ON user_sessions (user_id, revoked)"))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS idx_sessions_last_seen ON user_sessions (last_seen_at DESC)"))

    # ── notifications ────────────────────────────────────────────────────────
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS notifications (
            id            SERIAL PRIMARY KEY,
            user_id       INTEGER      NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            kind          VARCHAR(32)  NOT NULL,             -- task_assigned | task_update | task_completed | system
            title         VARCHAR(255) NOT NULL,
            body          TEXT,
            resource_type VARCHAR(32),                        -- 'alert' | 'task' | 'project'
            resource_id   INTEGER,
            actor_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            read_at       TIMESTAMPTZ,
            created_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW()
        )
    """))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS idx_notifications_user_unread "
        "ON notifications (user_id, read_at) WHERE read_at IS NULL"
    ))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS idx_notifications_user_time "
        "ON notifications (user_id, created_at DESC)"
    ))

    # ── activity_log ─────────────────────────────────────────────────────────
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS activity_log (
            id          SERIAL PRIMARY KEY,
            user_id     INTEGER REFERENCES users(id) ON DELETE SET NULL,
            session_id  INTEGER REFERENCES user_sessions(id) ON DELETE SET NULL,
            action      VARCHAR(64)  NOT NULL,   -- e.g. 'login', 'alert.approve', 'task.complete'
            method      VARCHAR(8),
            path        VARCHAR(255),
            status_code INTEGER,
            ip_address  VARCHAR(64),
            user_agent  TEXT,
            meta        JSONB,
            created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
        )
    """))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS idx_activity_user_time "
        "ON activity_log (user_id, created_at DESC)"
    ))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS idx_activity_time ON activity_log (created_at DESC)"
    ))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS idx_activity_action ON activity_log (action)"
    ))

    # ── extend alerts with assignment + completion tracking ──────────────────
    op.execute(sa.text(
        "ALTER TABLE alerts ADD COLUMN IF NOT EXISTS assignee_user_id "
        "INTEGER REFERENCES users(id) ON DELETE SET NULL"
    ))
    op.execute(sa.text(
        "ALTER TABLE alerts ADD COLUMN IF NOT EXISTS completed_by_user_id "
        "INTEGER REFERENCES users(id) ON DELETE SET NULL"
    ))
    op.execute(sa.text(
        "ALTER TABLE alerts ADD COLUMN IF NOT EXISTS completed_at TIMESTAMPTZ"
    ))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS idx_alerts_assignee_user "
        "ON alerts (assignee_user_id) WHERE assignee_user_id IS NOT NULL"
    ))

    # Expand the status CHECK to allow 'completed'. We drop & recreate the
    # constraint — Postgres doesn't have ALTER CHECK in place. The constraint
    # name is auto-generated on init.sql — we only drop if present.
    op.execute(sa.text("""
        DO $$
        DECLARE
            cname TEXT;
        BEGIN
            SELECT conname INTO cname
              FROM pg_constraint
             WHERE conrelid = 'alerts'::regclass
               AND contype  = 'c'
               AND pg_get_constraintdef(oid) ILIKE '%status%';
            IF cname IS NOT NULL THEN
                EXECUTE format('ALTER TABLE alerts DROP CONSTRAINT %I', cname);
            END IF;
        END $$;
    """))
    op.execute(sa.text(
        "ALTER TABLE alerts ADD CONSTRAINT alerts_status_check "
        "CHECK (status IN ('pending','approved','dismissed','notified','completed'))"
    ))


def downgrade() -> None:
    op.execute(sa.text("ALTER TABLE alerts DROP CONSTRAINT IF EXISTS alerts_status_check"))
    op.execute(sa.text("ALTER TABLE alerts DROP COLUMN IF EXISTS completed_at"))
    op.execute(sa.text("ALTER TABLE alerts DROP COLUMN IF EXISTS completed_by_user_id"))
    op.execute(sa.text("ALTER TABLE alerts DROP COLUMN IF EXISTS assignee_user_id"))
    op.execute(sa.text("DROP TABLE IF EXISTS activity_log"))
    op.execute(sa.text("DROP TABLE IF EXISTS notifications"))
    op.execute(sa.text("DROP TABLE IF EXISTS user_sessions"))
    op.execute(sa.text("DROP TABLE IF EXISTS users"))
