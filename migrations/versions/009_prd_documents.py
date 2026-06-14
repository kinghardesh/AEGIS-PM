"""Add prd_documents and prd_extracted_skills

Revision ID: 009_prd_documents
Revises: 008_employee_analysis
Create Date: 2026-04-16 00:00:00.000000

PRD upload + parsing pipeline (spec §2–§3):

  prd_documents         raw_text of the uploaded file (indexed retrieval)
  prd_extracted_skills  per-parse output (skills, priority_skills,
                        task_description, model). 1:N so re-parsing
                        preserves history.

Additive only — no existing table touched.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "009_prd_documents"
down_revision = "008_employee_analysis"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS prd_documents (
            id                    SERIAL PRIMARY KEY,
            project_id            INTEGER REFERENCES projects(id) ON DELETE SET NULL,
            filename              VARCHAR(255) NOT NULL,
            content_type          VARCHAR(64),
            raw_text              TEXT         NOT NULL,
            uploaded_by_user_id   INTEGER      REFERENCES users(id) ON DELETE SET NULL,
            created_at            TIMESTAMPTZ  NOT NULL DEFAULT NOW()
        )
    """))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS idx_prd_docs_project "
        "ON prd_documents (project_id, created_at DESC)"
    ))

    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS prd_extracted_skills (
            id                SERIAL PRIMARY KEY,
            prd_id            INTEGER      NOT NULL REFERENCES prd_documents(id) ON DELETE CASCADE,
            skills            TEXT         NOT NULL,   -- JSON array
            priority_skills   TEXT,                    -- JSON array
            task_description  TEXT,
            method            VARCHAR(32)  NOT NULL,   -- 'llm' | 'keyword'
            model             VARCHAR(64),             -- e.g. 'llama-3.3-70b-versatile'
            extracted_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
        )
    """))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS idx_prd_extracted_prd "
        "ON prd_extracted_skills (prd_id, extracted_at DESC)"
    ))


def downgrade() -> None:
    op.execute(sa.text("DROP TABLE IF EXISTS prd_extracted_skills"))
    op.execute(sa.text("DROP TABLE IF EXISTS prd_documents"))
