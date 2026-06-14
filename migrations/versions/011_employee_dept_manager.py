"""Add department and is_manager to employees and employee_staging

Revision ID: 011_employee_dept_manager
Revises: 010_task_day_entries
Create Date: 2026-06-14

Foundation for department-based org structure:
  - employees.department        (VARCHAR(128), nullable)
  - employees.is_manager        (BOOLEAN, default false)
  - employee_staging.department (VARCHAR(128), nullable)
  - employee_staging.is_manager (BOOLEAN, default false)

Idempotent (IF NOT EXISTS / IF EXISTS) so it is safe to re-run.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "011_employee_dept_manager"
down_revision = "010_task_day_entries"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("""
        ALTER TABLE employees
            ADD COLUMN IF NOT EXISTS department VARCHAR(128),
            ADD COLUMN IF NOT EXISTS is_manager BOOLEAN NOT NULL DEFAULT FALSE
    """))
    op.execute(sa.text("""
        ALTER TABLE employee_staging
            ADD COLUMN IF NOT EXISTS department VARCHAR(128),
            ADD COLUMN IF NOT EXISTS is_manager BOOLEAN NOT NULL DEFAULT FALSE
    """))


def downgrade() -> None:
    op.execute(sa.text("""
        ALTER TABLE employee_staging
            DROP COLUMN IF EXISTS is_manager,
            DROP COLUMN IF EXISTS department
    """))
    op.execute(sa.text("""
        ALTER TABLE employees
            DROP COLUMN IF EXISTS is_manager,
            DROP COLUMN IF EXISTS department
    """))
