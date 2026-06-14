"""Add employee_staging table for bulk upload flow

Revision ID: 006_employee_staging
Revises: 005_employee_role_task_fields
Create Date: 2026-04-16 00:00:00.000000

Holds candidate employees parsed from an uploaded file (xlsx/csv/pdf) until
an admin promotes selected rows into the real employees + users tables.

Purely additive: no existing table is touched.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "006_employee_staging"
down_revision = "005_employee_role_task_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS employee_staging (
            id              SERIAL PRIMARY KEY,
            name            VARCHAR(255) NOT NULL,
            email           VARCHAR(255),
            skills          TEXT,                       -- JSON array as text
            experience      REAL,                       -- years, nullable
            raw_metadata    JSONB,                      -- anything extra from the file
            upload_batch_id VARCHAR(64)  NOT NULL,
            uploaded_by_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            status          VARCHAR(16)  NOT NULL DEFAULT 'pending'
                            CHECK (status IN ('pending','promoted','rejected','duplicate')),
            promoted_to_employee_id INTEGER REFERENCES employees(id) ON DELETE SET NULL,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS idx_staging_batch  ON employee_staging (upload_batch_id)"
    ))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS idx_staging_status ON employee_staging (status)"
    ))


def downgrade() -> None:
    op.execute(sa.text("DROP TABLE IF EXISTS employee_staging"))
