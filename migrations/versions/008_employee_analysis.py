"""Add employee_analysis cache table

Revision ID: 008_employee_analysis
Revises: 007_embeddings_reminder_logs
Create Date: 2026-04-16 00:00:00.000000

Persists each scored candidate so admins can:
  - audit past decisions ("why did we shortlist Priya for project X?")
  - re-display a ranking without recomputing (handy for slow PDFs / offline OpenAI)

One row per (staging_id, requirement_hash, analyzed_at). `requirement_hash`
is a sha256 of the normalised (required, priority, min_experience) tuple
so repeat runs of the same spec hit the same cache key.

Additive only — nothing existing touched.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "008_employee_analysis"
down_revision = "007_embeddings_reminder_logs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS employee_analysis (
            id                  SERIAL PRIMARY KEY,
            staging_id          INTEGER      NOT NULL
                                REFERENCES employee_staging(id) ON DELETE CASCADE,
            requirement_hash    VARCHAR(64)  NOT NULL,
            required_skills     TEXT         NOT NULL,   -- JSON array
            priority_skills     TEXT,                    -- JSON array (nullable)
            min_experience      REAL,                    -- years, nullable
            score               REAL         NOT NULL,
            skill_score         REAL         NOT NULL,   -- raw similarity [0..1]
            experience_score    REAL         NOT NULL,
            priority_bonus      REAL         NOT NULL,
            confidence          REAL         NOT NULL,
            matched_skills      TEXT,                    -- JSON array
            missing_skills      TEXT,                    -- JSON array
            reason              TEXT,
            semantic            BOOLEAN      NOT NULL DEFAULT FALSE,
            analyzed_at         TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
            analyzed_by_user_id INTEGER      REFERENCES users(id) ON DELETE SET NULL
        )
    """))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS idx_analysis_req "
        "ON employee_analysis (requirement_hash, analyzed_at DESC)"
    ))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS idx_analysis_staging "
        "ON employee_analysis (staging_id, analyzed_at DESC)"
    ))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS idx_analysis_score "
        "ON employee_analysis (requirement_hash, score DESC)"
    ))


def downgrade() -> None:
    op.execute(sa.text("DROP TABLE IF EXISTS employee_analysis"))
