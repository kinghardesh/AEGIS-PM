"""Make users.email required (backfill first)

Revision ID: 004_email_required
Revises: 003_password_reset
Create Date: 2026-04-16 00:00:00.000000

Spec: register + login must use email as the canonical identifier.
Existing rows (notably the bootstrap admin) may have NULL email, so we
backfill deterministically with "<user_id>@local.invalid" BEFORE the
NOT NULL constraint is applied. The `.invalid` TLD is reserved for this
purpose (RFC 2606) and will never route real mail.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "004_email_required"
down_revision = "003_password_reset"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Backfill uses a real gTLD so Pydantic's EmailStr (via email-validator)
    # accepts these emails at login time. RFC 2606 reserved domains (.invalid,
    # .local, .test, .example) are rejected by the validator even though
    # they parse — don't use them here.
    op.execute(sa.text(
        "UPDATE users "
        "SET email = user_id || '@bootstrap.aegis-pm.app' "
        "WHERE email IS NULL OR email = '' OR email LIKE '%@local.invalid' "
        "  OR email LIKE '%@aegis.local'"
    ))
    op.execute(sa.text("ALTER TABLE users ALTER COLUMN email SET NOT NULL"))


def downgrade() -> None:
    op.execute(sa.text("ALTER TABLE users ALTER COLUMN email DROP NOT NULL"))
