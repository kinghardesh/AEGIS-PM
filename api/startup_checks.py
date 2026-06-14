"""
aegis-pm / api / startup_checks.py

Production boot guards — fail fast if configuration is missing or weak, or
if the DB is not at the expected Alembic revision.

Called once from api.main.lifespan during startup. In development (when
AEGIS_ENFORCE_AUTH != "true") missing config is demoted to a warning so
contributors can still run the app; in production every problem is fatal.

This module is intentionally *not* a decorator or a DI dependency —
everything here should run exactly once, at boot, before the first
request is served.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Callable

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncEngine

log = logging.getLogger("aegis.startup")

# The Alembic head we expect the DB to be at. Bump this in lockstep with
# the latest revision under migrations/versions/ — deploys that forget to
# run `alembic upgrade head` will then refuse to boot instead of serving
# 500s from a missing column.
EXPECTED_ALEMBIC_HEAD = "010_task_day_entries"


def _prod() -> bool:
    return os.getenv("AEGIS_ENFORCE_AUTH", "false").lower() == "true"


def _fatal(msg: str) -> None:
    """Raise in prod, log loudly in dev."""
    if _prod():
        raise RuntimeError(f"[startup] {msg}")
    log.warning("[startup] %s", msg)


# ── Individual checks ────────────────────────────────────────────────────────

def check_jwt_secret() -> None:
    secret = os.getenv("JWT_SECRET", "").strip()
    if not secret:
        _fatal("JWT_SECRET is not set. Generate with: python -c \"import secrets;print(secrets.token_urlsafe(64))\"")
        return
    if len(secret) < 32:
        _fatal(f"JWT_SECRET is too short ({len(secret)} chars). Minimum 32.")


def check_bcrypt_cost() -> None:
    try:
        cost = int(os.getenv("BCRYPT_COST", "12"))
    except ValueError:
        _fatal("BCRYPT_COST must be an integer")
        return
    if cost < 12:
        _fatal(f"BCRYPT_COST={cost} is too low for production; use >= 12.")


def check_redis_url() -> None:
    if os.getenv("REDIS_URL", "").strip():
        return
    # WS + notifications still function single-worker without Redis, but
    # any horizontal scale-out silently breaks. Warn hard in prod.
    _fatal("REDIS_URL not set — required for multi-worker WebSocket fan-out.")


def check_dependencies() -> None:
    """
    Guardrail: make sure we're running with the expected official deps
    and that no frontend code smuggled in the `unstable_instant` injection
    we spotted in node_modules/next/dist/docs.
    """
    # Python side — just confirm the required libs are importable. If a
    # contributor adds a new auth feature and forgets to `pip install`,
    # this turns "ImportError during first login" into a boot failure.
    required = ("bcrypt", "jwt", "redis")
    missing = []
    for name in required:
        try:
            __import__(name)
        except ImportError:
            missing.append(name)
    if missing:
        _fatal(f"Missing required packages: {', '.join(missing)}. Run `pip install -r requirements.txt`.")

    # Frontend side — if the Next.js bundle is co-located (monorepo dev
    # setup), scan for the injection pattern we flagged. This is a single
    # grep, no regex engines loaded.
    web_root = Path(__file__).resolve().parent.parent / "aegis-pm-web" / "src"
    if web_root.is_dir():
        for path in web_root.rglob("*.ts*"):
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            if "unstable_instant" in text:
                _fatal(f"Suspicious symbol 'unstable_instant' found in {path}. "
                       "This API does not exist in official Next.js — remove it.")


async def check_alembic_head(engine: AsyncEngine) -> None:
    """
    Refuse to boot if the DB's alembic_version != EXPECTED_ALEMBIC_HEAD.
    This replaces the previous `metadata.create_all` safety net with a
    migrations-are-mandatory policy.
    """
    async with engine.connect() as conn:
        try:
            rows = (await conn.execute(sa.text(
                "SELECT version_num FROM alembic_version"
            ))).scalars().all()
        except Exception as e:
            _fatal(f"Cannot read alembic_version ({e}). "
                   f"Did you run `alembic upgrade head`?")
            return

    if not rows:
        _fatal("alembic_version is empty — run `alembic upgrade head` before starting the API.")
        return
    if EXPECTED_ALEMBIC_HEAD not in rows:
        _fatal(
            f"DB is at alembic revision {rows} but the code expects "
            f"{EXPECTED_ALEMBIC_HEAD}. Run `alembic upgrade head`."
        )


# ── Entry point ──────────────────────────────────────────────────────────────

async def run_all(engine: AsyncEngine) -> None:
    log.info("[startup] running production guards (prod=%s)", _prod())
    check_jwt_secret()
    check_bcrypt_cost()
    check_redis_url()
    check_dependencies()
    await check_alembic_head(engine)
    log.info("[startup] all guards passed")
