"""Add embeddings_cache and reminder_logs (persistent dedup)

Revision ID: 007_embeddings_reminder_logs
Revises: 006_employee_staging
Create Date: 2026-04-16 00:00:00.000000

Two new tables, both purely additive:

  embeddings_cache          keyed by sha256(model|text). Rows are small (one
                            vector of ~1536 floats as JSONB) and deduplicated
                            across every matcher call, so one request for
                            "React, Node.js" is computed once and reused.

  reminder_logs             records every sent reminder so the scheduler can
                            be restarted without re-sending. The UNIQUE
                            index on (user_id, task_id, type, date) is what
                            actually makes dedup atomic — inserts race-safe
                            via `ON CONFLICT DO NOTHING`.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "007_embeddings_reminder_logs"
down_revision = "006_employee_staging"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── embeddings_cache ────────────────────────────────────────────────────
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS embeddings_cache (
            text_hash   VARCHAR(64)  PRIMARY KEY,
            model       VARCHAR(64)  NOT NULL,
            embedding   JSONB        NOT NULL,
            created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
        )
    """))

    # ── reminder_logs ───────────────────────────────────────────────────────
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS reminder_logs (
            id             SERIAL PRIMARY KEY,
            user_id        INTEGER      NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            task_id        INTEGER      NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
            reminder_type  VARCHAR(32)  NOT NULL
                           CHECK (reminder_type IN ('deadline', 'pending')),
            reminder_date  DATE         NOT NULL,
            created_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW()
        )
    """))
    # The atomic dedup guarantee — multiple concurrent INSERTs can't both win.
    op.execute(sa.text(
        "CREATE UNIQUE INDEX IF NOT EXISTS reminder_logs_unique "
        "ON reminder_logs (user_id, task_id, reminder_type, reminder_date)"
    ))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS idx_reminder_logs_date "
        "ON reminder_logs (reminder_date DESC)"
    ))


def downgrade() -> None:
    op.execute(sa.text("DROP TABLE IF EXISTS reminder_logs"))
    op.execute(sa.text("DROP TABLE IF EXISTS embeddings_cache"))
