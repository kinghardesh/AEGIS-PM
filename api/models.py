"""
aegis-pm / api / models.py

Shared SQLAlchemy Core tables for the new auth / notifications / activity
layer. Kept separate from `api.main` so that `auth`, `notifications`,
`websocket`, and `activity` modules can import them without a circular.

The existing `alerts`, `employees`, `tasks`, `projects`, `alert_audit_log`
tables still live in `api/main.py` — we reference them loosely by name where
needed to avoid a giant refactor.
"""
from __future__ import annotations

import sqlalchemy as sa

metadata = sa.MetaData()

users_table = sa.Table(
    "users",
    metadata,
    sa.Column("id",            sa.Integer,     primary_key=True),
    sa.Column("user_id",       sa.String(64),  nullable=False, unique=True),
    sa.Column("email",         sa.String(255), unique=True),
    sa.Column("full_name",     sa.String(255)),
    sa.Column("password_hash", sa.Text,        nullable=False),
    sa.Column("role",          sa.String(16),  nullable=False, server_default="user"),
    sa.Column("employee_id",   sa.Integer),
    sa.Column("is_active",     sa.Boolean,     nullable=False, server_default="true"),
    sa.Column("last_login_at", sa.DateTime(timezone=True)),
    sa.Column("created_at",    sa.DateTime(timezone=True), server_default=sa.func.now()),
    sa.Column("updated_at",    sa.DateTime(timezone=True), server_default=sa.func.now()),
)

user_sessions_table = sa.Table(
    "user_sessions",
    metadata,
    sa.Column("id",           sa.Integer,     primary_key=True),
    sa.Column("user_id",      sa.Integer,     nullable=False),
    sa.Column("jti",          sa.String(64),  nullable=False, unique=True),
    sa.Column("device",       sa.String(255)),
    sa.Column("user_agent",   sa.Text),
    sa.Column("ip_address",   sa.String(64)),
    sa.Column("revoked",      sa.Boolean,     nullable=False, server_default="false"),
    sa.Column("created_at",   sa.DateTime(timezone=True), server_default=sa.func.now()),
    sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    sa.Column("expires_at",   sa.DateTime(timezone=True), nullable=False),
)

notifications_table = sa.Table(
    "notifications",
    metadata,
    sa.Column("id",            sa.Integer,     primary_key=True),
    sa.Column("user_id",       sa.Integer,     nullable=False),
    sa.Column("kind",          sa.String(32),  nullable=False),
    sa.Column("title",         sa.String(255), nullable=False),
    sa.Column("body",          sa.Text),
    sa.Column("resource_type", sa.String(32)),
    sa.Column("resource_id",   sa.Integer),
    sa.Column("actor_user_id", sa.Integer),
    sa.Column("read_at",       sa.DateTime(timezone=True)),
    sa.Column("created_at",    sa.DateTime(timezone=True), server_default=sa.func.now()),
)

activity_log_table = sa.Table(
    "activity_log",
    metadata,
    sa.Column("id",          sa.Integer,     primary_key=True),
    sa.Column("user_id",     sa.Integer),
    sa.Column("session_id",  sa.Integer),
    sa.Column("action",      sa.String(64),  nullable=False),
    sa.Column("method",      sa.String(8)),
    sa.Column("path",        sa.String(255)),
    sa.Column("status_code", sa.Integer),
    sa.Column("ip_address",  sa.String(64)),
    sa.Column("user_agent",  sa.Text),
    sa.Column("meta",        sa.JSON),
    sa.Column("created_at",  sa.DateTime(timezone=True), server_default=sa.func.now()),
)

task_day_entries_table = sa.Table(
    "task_day_entries",
    metadata,
    sa.Column("id",                  sa.Integer,     primary_key=True),
    sa.Column("task_id",             sa.Integer,     nullable=False),
    sa.Column("day_number",          sa.Integer,     nullable=False),
    sa.Column("planned_description", sa.Text),
    sa.Column("actual_note",         sa.Text),
    sa.Column("completed_at",        sa.DateTime(timezone=True)),
    sa.Column("created_at",          sa.DateTime(timezone=True), server_default=sa.func.now()),
)


prd_documents_table = sa.Table(
    "prd_documents",
    metadata,
    sa.Column("id",                  sa.Integer,     primary_key=True),
    sa.Column("project_id",          sa.Integer),
    sa.Column("filename",            sa.String(255), nullable=False),
    sa.Column("content_type",        sa.String(64)),
    sa.Column("raw_text",            sa.Text,        nullable=False),
    sa.Column("uploaded_by_user_id", sa.Integer),
    sa.Column("created_at",          sa.DateTime(timezone=True), server_default=sa.func.now()),
)


prd_extracted_skills_table = sa.Table(
    "prd_extracted_skills",
    metadata,
    sa.Column("id",               sa.Integer,     primary_key=True),
    sa.Column("prd_id",           sa.Integer,     nullable=False),
    sa.Column("skills",           sa.Text,        nullable=False),   # JSON array
    sa.Column("priority_skills",  sa.Text),
    sa.Column("task_description", sa.Text),
    sa.Column("method",           sa.String(32),  nullable=False),
    sa.Column("model",            sa.String(64)),
    sa.Column("extracted_at",     sa.DateTime(timezone=True), server_default=sa.func.now()),
)


embeddings_cache_table = sa.Table(
    "embeddings_cache",
    metadata,
    sa.Column("text_hash",  sa.String(64),  primary_key=True),
    sa.Column("model",      sa.String(64),  nullable=False),
    sa.Column("embedding",  sa.JSON,        nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
)


reminder_logs_table = sa.Table(
    "reminder_logs",
    metadata,
    sa.Column("id",             sa.Integer,     primary_key=True),
    sa.Column("user_id",        sa.Integer,     nullable=False),
    sa.Column("task_id",        sa.Integer,     nullable=False),
    sa.Column("reminder_type",  sa.String(32),  nullable=False),
    sa.Column("reminder_date",  sa.Date,        nullable=False),
    sa.Column("created_at",     sa.DateTime(timezone=True), server_default=sa.func.now()),
)


employee_analysis_table = sa.Table(
    "employee_analysis",
    metadata,
    sa.Column("id",                  sa.Integer,     primary_key=True),
    sa.Column("staging_id",          sa.Integer,     nullable=False),
    sa.Column("requirement_hash",    sa.String(64),  nullable=False),
    sa.Column("required_skills",     sa.Text,        nullable=False),
    sa.Column("priority_skills",     sa.Text),
    sa.Column("min_experience",      sa.Float),
    sa.Column("score",               sa.Float,       nullable=False),
    sa.Column("skill_score",         sa.Float,       nullable=False),
    sa.Column("experience_score",    sa.Float,       nullable=False),
    sa.Column("priority_bonus",      sa.Float,       nullable=False),
    sa.Column("confidence",          sa.Float,       nullable=False),
    sa.Column("matched_skills",      sa.Text),
    sa.Column("missing_skills",      sa.Text),
    sa.Column("reason",              sa.Text),
    sa.Column("semantic",            sa.Boolean,     nullable=False, server_default="false"),
    sa.Column("analyzed_at",         sa.DateTime(timezone=True), server_default=sa.func.now()),
    sa.Column("analyzed_by_user_id", sa.Integer),
)


employee_staging_table = sa.Table(
    "employee_staging",
    metadata,
    sa.Column("id",                       sa.Integer,     primary_key=True),
    sa.Column("name",                     sa.String(255), nullable=False),
    sa.Column("email",                    sa.String(255)),
    sa.Column("skills",                   sa.Text),        # JSON array as text
    sa.Column("experience",               sa.Float),
    sa.Column("department",               sa.String(128)),  # org unit (parsed/inferred)
    sa.Column("is_manager",               sa.Boolean,     server_default="false"),
    sa.Column("raw_metadata",             sa.JSON),
    sa.Column("upload_batch_id",          sa.String(64),  nullable=False),
    sa.Column("uploaded_by_user_id",      sa.Integer),
    sa.Column("status",                   sa.String(16),  nullable=False, server_default="pending"),
    sa.Column("promoted_to_employee_id",  sa.Integer),
    sa.Column("created_at",               sa.DateTime(timezone=True), server_default=sa.func.now()),
)


password_reset_tokens_table = sa.Table(
    "password_reset_tokens",
    metadata,
    sa.Column("id",           sa.Integer,     primary_key=True),
    sa.Column("user_id",      sa.Integer,     nullable=False),
    # sha256(hex) of the raw token — raw token is ONLY sent in the email.
    sa.Column("token_hash",   sa.String(128), nullable=False, unique=True),
    sa.Column("expires_at",   sa.DateTime(timezone=True), nullable=False),
    sa.Column("consumed_at",  sa.DateTime(timezone=True)),
    sa.Column("ip_requested", sa.String(64)),
    sa.Column("created_at",   sa.DateTime(timezone=True), server_default=sa.func.now()),
)
