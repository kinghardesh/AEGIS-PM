"""Password reset tokens

Revision ID: 003_password_reset
Revises: 002_auth_notifications_activity
Create Date: 2026-04-16 00:00:00.000000

Adds one table:

    password_reset_tokens
      id            PK
      user_id       → users.id  (ON DELETE CASCADE)
      token_hash    sha256 hex  (NEVER store the raw token)
      expires_at    TIMESTAMPTZ
      consumed_at   TIMESTAMPTZ NULL
      ip_requested  VARCHAR(64)
      created_at    TIMESTAMPTZ DEFAULT NOW()

Indexes:
  - UNIQUE(token_hash)                       fast lookup at reset time
  - INDEX (user_id, created_at DESC)         rate-limit + recent history
  - PARTIAL INDEX on unconsumed active       cheap "active token" checks
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "003_password_reset"
down_revision = "002_auth_notifications_activity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS password_reset_tokens (
            id            SERIAL PRIMARY KEY,
            user_id       INTEGER      NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            token_hash    VARCHAR(128) NOT NULL UNIQUE,
            expires_at    TIMESTAMPTZ  NOT NULL,
            consumed_at   TIMESTAMPTZ,
            ip_requested  VARCHAR(64),
            created_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW()
        )
    """))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS idx_prt_user_time "
        "ON password_reset_tokens (user_id, created_at DESC)"
    ))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS idx_prt_active "
        "ON password_reset_tokens (user_id, expires_at) "
        "WHERE consumed_at IS NULL"
    ))


def downgrade() -> None:
    op.execute(sa.text("DROP TABLE IF EXISTS password_reset_tokens"))
