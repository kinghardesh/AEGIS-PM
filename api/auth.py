"""
aegis-pm / api / auth.py

User + Admin authentication: bcrypt password hashing + JWT bearer tokens.

Coexists with the existing X-API-Key layer in api/security.py:
  - Agents (Monitor, Communicator, executors) keep using API keys.
  - Humans (users, admins) use POST /auth/login → receive JWT → Authorization: Bearer <jwt>.

FastAPI dependency usage:

    from api.auth import get_current_user, require_admin

    @router.get("/me")
    async def me(user = Depends(get_current_user)): ...

    @router.post("/alerts/{id}/assign")
    async def assign(..., user = Depends(require_admin)): ...

Tokens are JWT HS256 with a random server-side secret (`JWT_SECRET`).
Each token carries a `jti` recorded in `user_sessions` — revoke any
device by flipping `user_sessions.revoked = true`.
"""
from __future__ import annotations

import hashlib
import os
import secrets
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
import jwt
import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel, EmailStr, Field, model_validator
from sqlalchemy.ext.asyncio import AsyncSession

from api.email import EmailMessage, get_sender
from api.models import (
    password_reset_tokens_table,
    user_sessions_table,
    users_table,
)

log = logging.getLogger("aegis.auth")

# ── Config ────────────────────────────────────────────────────────────────────

JWT_SECRET   = os.getenv("JWT_SECRET") or secrets.token_urlsafe(64)
JWT_ALGO     = "HS256"
JWT_TTL_MIN  = int(os.getenv("JWT_TTL_MINUTES", "720"))  # 12 h default
BCRYPT_COST  = int(os.getenv("BCRYPT_COST", "12"))

# Password reset
RESET_TOKEN_TTL_MIN = int(os.getenv("PW_RESET_TOKEN_TTL_MINUTES", "30"))
RESET_BASE_URL      = os.getenv("PW_RESET_BASE_URL", "http://localhost:3000").rstrip("/")
RESET_RATE_MAX      = int(os.getenv("PW_RESET_RATE_MAX", "3"))    # per user per window
RESET_RATE_WINDOW_M = int(os.getenv("PW_RESET_RATE_WINDOW_MIN", "30"))

if not os.getenv("JWT_SECRET"):
    log.warning(
        "JWT_SECRET not set — using an ephemeral secret. "
        "All tokens will be invalidated on next restart. "
        "Set JWT_SECRET in prod."
    )

bearer_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)

# ── Password hashing ──────────────────────────────────────────────────────────

def hash_password(plain: str) -> str:
    if not plain or len(plain) < 8:
        raise ValueError("Password must be at least 8 characters.")
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt(BCRYPT_COST)).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


# ── JWT ───────────────────────────────────────────────────────────────────────

def _now() -> datetime:
    return datetime.now(timezone.utc)


def issue_token(user_id: int, role: str, jti: str, ttl_minutes: int = JWT_TTL_MIN) -> tuple[str, datetime]:
    exp = _now() + timedelta(minutes=ttl_minutes)
    payload = {
        "sub":  str(user_id),
        "role": role,
        "jti":  jti,
        "iat":  int(_now().timestamp()),
        "exp":  int(exp.timestamp()),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGO), exp


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGO])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token expired")
    except jwt.InvalidTokenError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"Invalid token: {e}")


# ── Schemas ───────────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    """
    Spec says "email + password". We also accept `user_id` for backward
    compatibility with the bootstrap admin and legacy integrations. At
    least one of the two must be present.
    """
    email:    Optional[EmailStr] = None
    user_id:  Optional[str] = Field(None, min_length=1, max_length=64)
    password: str = Field(..., min_length=1, max_length=128)

    @model_validator(mode="after")
    def _require_identifier(self):
        if not self.email and not self.user_id:
            raise ValueError("email or user_id is required")
        return self


class TokenResponse(BaseModel):
    access_token: str
    token_type:   str = "bearer"
    expires_at:   datetime
    user:         "UserOut"


class UserOut(BaseModel):
    id:            int
    user_id:       str
    email:         Optional[str]
    full_name:     Optional[str]
    role:          str
    employee_id:   Optional[int]
    is_active:     bool
    last_login_at: Optional[datetime]

    class Config:
        from_attributes = True


class RegisterRequest(BaseModel):
    """
    Public self-signup payload. Deliberately does NOT expose `role` — that
    would be a trivial privilege-escalation vector. Role is always forced
    to 'user' in the handler. Admins are only created via
    POST /admin/create-user (admin-only).
    """
    name:     str = Field(..., min_length=1, max_length=255)
    email:    EmailStr
    password: str = Field(..., min_length=8, max_length=128)


class AdminCreateUserRequest(BaseModel):
    """
    Admin-only creation. Allows explicit role and optional pre-seeded
    user_id / employee_id linkage.
    """
    name:        str = Field(..., min_length=1, max_length=255)
    email:       EmailStr
    password:    str = Field(..., min_length=8, max_length=128)
    role:        str = Field("user", pattern=r"^(user|admin|agent|employee)$")
    user_id:     Optional[str] = Field(None, min_length=3, max_length=64)
    employee_id: Optional[int] = None


class AdminCreateEmployeeRequest(BaseModel):
    """
    Payload for POST /admin/create-employee. Mirrors the spec: admin
    supplies a name (required) and optional email. The server mints a
    user_id + a secure password.
    """
    name:  str = Field(..., min_length=1, max_length=255)
    email: Optional[EmailStr] = None
    # Optional tagging so the employees row has useful metadata out of
    # the gate. All nullable.
    role_title: Optional[str] = Field(None, max_length=128)   # e.g. "Backend Engineer"
    skills:     Optional[list[str]] = None


class EmployeeCredsResponse(BaseModel):
    """
    Returned ONCE on successful create. The password is plaintext; the
    frontend should display it prominently and tell the admin to copy
    it — it cannot be retrieved later (we only store the bcrypt hash).
    """
    user:                 "UserOut"
    employee_id:          int
    generated_user_id:    str
    generated_password:   str


TokenResponse.model_rebuild()
EmployeeCredsResponse.model_rebuild()


# ── Dependencies ──────────────────────────────────────────────────────────────

async def _lookup_user(db: AsyncSession, user_id: int) -> Optional[dict]:
    row = (
        await db.execute(sa.select(users_table).where(users_table.c.id == user_id))
    ).mappings().first()
    return dict(row) if row else None


async def get_current_user(
    request: Request,
    token: Optional[str] = Depends(bearer_scheme),
) -> dict:
    """
    Resolve JWT → user dict. Raises 401 on missing/invalid/revoked token.
    The user dict is also stashed on `request.state.user` for middleware.
    """
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")

    payload = decode_token(token)
    try:
        user_id = int(payload["sub"])
        jti     = payload["jti"]
    except (KeyError, ValueError):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Malformed token")

    # Lazy import to avoid circular (main imports this module, too).
    from api.main import SessionLocal

    async with SessionLocal() as db:
        session_row = (
            await db.execute(
                sa.select(user_sessions_table).where(
                    user_sessions_table.c.jti == jti,
                    user_sessions_table.c.revoked.is_(False),
                )
            )
        ).mappings().first()
        if not session_row:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session revoked")

        user = await _lookup_user(db, user_id)
        if not user or not user["is_active"]:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User inactive")

        # Touch last_seen_at for activity monitoring.
        await db.execute(
            user_sessions_table.update()
            .where(user_sessions_table.c.id == session_row["id"])
            .values(last_seen_at=_now())
        )
        await db.commit()

    user["session_id"] = session_row["id"]
    user["jti"]        = jti
    request.state.user = user
    return user


async def require_admin(user: dict = Depends(get_current_user)) -> dict:
    if user["role"] != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin access required")
    return user


async def get_optional_user(
    request: Request,
    token: Optional[str] = Depends(bearer_scheme),
) -> Optional[dict]:
    """Same as get_current_user but returns None instead of raising."""
    if not token:
        return None
    try:
        return await get_current_user(request, token)
    except HTTPException:
        return None


# ── Router ────────────────────────────────────────────────────────────────────

router = APIRouter(prefix="/auth", tags=["Auth"])


def _client_meta(request: Request) -> tuple[str, str]:
    ip = request.client.host if request.client else "unknown"
    ua = request.headers.get("user-agent", "")[:500]
    return ip, ua


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, request: Request):
    """
    Authenticate with `email` + `password` (preferred) or `user_id` +
    `password` (legacy). Returns a JWT + user profile.

    The JWT carries {sub: <user pk>, role: 'user'|'admin'|'agent', jti, exp}.
    A session row is recorded so admins can see every device a user is
    logged in from, and revoke any of them.
    """
    from api.main import SessionLocal  # lazy — avoids import cycle

    async with SessionLocal() as db:
        q = sa.select(users_table)
        if body.email:
            q = q.where(sa.func.lower(users_table.c.email) == body.email.lower())
        else:
            q = q.where(users_table.c.user_id == body.user_id)
        row = (await db.execute(q)).mappings().first()

        if not row or not row["is_active"] or not verify_password(body.password, row["password_hash"]):
            # Constant-ish error to avoid user enumeration.
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")

        jti = uuid.uuid4().hex
        token, exp = issue_token(user_id=row["id"], role=row["role"], jti=jti)
        ip, ua = _client_meta(request)

        await db.execute(
            user_sessions_table.insert().values(
                user_id=row["id"],
                jti=jti,
                device=ua[:120] or None,
                user_agent=ua or None,
                ip_address=ip,
                expires_at=exp,
            )
        )
        await db.execute(
            users_table.update()
            .where(users_table.c.id == row["id"])
            .values(last_login_at=_now())
        )
        await db.commit()

        user = dict(row)
        user["last_login_at"] = _now()
        log.info("Login ok: user=%s role=%s ip=%s", row["user_id"], row["role"], ip)

        return TokenResponse(
            access_token=token,
            expires_at=exp,
            user=UserOut(**user),
        )


@router.get("/me", response_model=UserOut)
async def me(user: dict = Depends(get_current_user)):
    return UserOut(**user)


@router.post("/logout")
async def logout(user: dict = Depends(get_current_user)):
    """Revoke the current device's session."""
    from api.main import SessionLocal
    async with SessionLocal() as db:
        await db.execute(
            user_sessions_table.update()
            .where(user_sessions_table.c.id == user["session_id"])
            .values(revoked=True)
        )
        await db.commit()
    return {"ok": True}


# ── User-ID derivation ───────────────────────────────────────────────────────

import re as _re

_USER_ID_SAFE = _re.compile(r"[^a-z0-9_]")


async def _allocate_user_id(db: AsyncSession, email: str) -> str:
    """
    Derive a collision-free user_id from the email's local-part. Deterministic
    first ("alice@x.com" → "alice"); on clash, append a numeric suffix, then
    fall back to a random suffix. Kept short (<=64 chars).
    """
    base = _USER_ID_SAFE.sub("_", email.split("@")[0].lower())[:56] or "user"

    async def exists(candidate: str) -> bool:
        row = (
            await db.execute(sa.select(users_table.c.id).where(users_table.c.user_id == candidate))
        ).first()
        return row is not None

    if not await exists(base):
        return base
    for n in range(1, 100):
        candidate = f"{base}{n}"
        if not await exists(candidate):
            return candidate
    return f"{base}_{secrets.token_hex(3)}"


# ── Public registration (spec: default role = USER) ─────────────────────────

@router.post("/register", response_model=UserOut, status_code=201)
async def register(body: RegisterRequest, request: Request):
    """
    Public self-signup. **Role is always 'user'** — the request body has
    no `role` field, and the handler hard-codes it. This closes the
    privilege-escalation vector where a caller could POST role=admin.

    Admins are created exclusively via POST /admin/create-user, which
    requires an existing admin's JWT.
    """
    _validate_password_strength(body.password)

    from api.main import SessionLocal

    async with SessionLocal() as db:
        # Email uniqueness — case-insensitive check for a friendlier error
        # than the raw UNIQUE-constraint violation.
        existing = (
            await db.execute(
                sa.select(users_table.c.id).where(
                    sa.func.lower(users_table.c.email) == body.email.lower()
                )
            )
        ).first()
        if existing:
            raise HTTPException(409, "An account with that email already exists")

        user_id = await _allocate_user_id(db, body.email)
        hashed  = hash_password(body.password)

        result = await db.execute(
            users_table.insert()
            .values(
                user_id=user_id,
                email=body.email.lower(),
                full_name=body.name,
                password_hash=hashed,
                role="user",           # <- always forced; never from body
            )
            .returning(users_table)
        )
        await db.commit()
        row = result.mappings().first()
        ip, _ = _client_meta(request)
        log.info("User registered: user_id=%s email=%s ip=%s", row["user_id"], row["email"], ip)
        return UserOut(**dict(row))


# ── Admin-only router (router-level guard) ──────────────────────────────────
#
# Mounting as APIRouter(prefix="/admin", dependencies=[Depends(require_admin)])
# applies the admin check to every handler on this router in one place —
# impossible to forget the decorator on a new endpoint, and it matches the
# spec's "/admin/* → only ADMIN" rule.

admin_router = APIRouter(
    prefix="/admin",
    tags=["Admin"],
    dependencies=[Depends(require_admin)],
)


@admin_router.get("/users", response_model=list[UserOut])
async def admin_list_users():
    """Admin view — list all users."""
    from api.main import SessionLocal
    async with SessionLocal() as db:
        rows = (
            await db.execute(sa.select(users_table).order_by(users_table.c.created_at.desc()))
        ).mappings().all()
    return [UserOut(**dict(r)) for r in rows]


@admin_router.post("/create-user", response_model=UserOut, status_code=201)
async def admin_create_user(body: AdminCreateUserRequest, request: Request):
    """
    Admin-only creation. Only through this route can `role` be set (the
    public /auth/register never reads role from the body).
    """
    _validate_password_strength(body.password)

    from api.main import SessionLocal
    async with SessionLocal() as db:
        existing = (
            await db.execute(
                sa.select(users_table.c.id).where(
                    sa.or_(
                        sa.func.lower(users_table.c.email) == body.email.lower(),
                        users_table.c.user_id == (body.user_id or ""),
                    )
                )
            )
        ).first()
        if existing:
            raise HTTPException(409, "user_id or email already exists")

        user_id = body.user_id or await _allocate_user_id(db, body.email)
        hashed  = hash_password(body.password)

        result = await db.execute(
            users_table.insert()
            .values(
                user_id=user_id,
                email=body.email.lower(),
                full_name=body.name,
                password_hash=hashed,
                role=body.role,
                employee_id=body.employee_id,
            )
            .returning(users_table)
        )
        await db.commit()
        row = result.mappings().first()
        ip, _ = _client_meta(request)
        log.info(
            "Admin-created user: user_id=%s role=%s by_ip=%s",
            row["user_id"], row["role"], ip,
        )
        return UserOut(**dict(row))


# ── Employee provisioning (create-employee) ─────────────────────────────────
#
# Thin wrapper around the existing create-user + employees tables. The goal:
# admin supplies name (+ optional email), we auto-mint user_id and a secure
# one-time password, and we insert a linked employees + users row atomically.
#
# No existing endpoints are replaced: /admin/create-user still works for
# admin/agent creation; this one is specifically for the 'employee' role.

_PW_ALPHABET_LOWER  = "abcdefghjkmnpqrstuvwxyz"   # no 'i', 'l', 'o'
_PW_ALPHABET_UPPER  = "ABCDEFGHJKMNPQRSTUVWXYZ"   # no 'I', 'L', 'O'
_PW_ALPHABET_DIGITS = "23456789"                  # no '0', '1'
_PW_ALPHABET_SYMBOL = "!@#%&*?+"                  # URL/email safe-ish


def _generate_password(length: int = 14) -> str:
    """
    Generate a readable-but-strong one-time password.

    Guarantees one char from each class and fills the remainder from the
    union. Uses `secrets` (CSPRNG). Ambiguous glyphs (0/O/o, 1/l/I) are
    excluded so an admin can read it aloud or retype from a sticky note
    without errors.
    """
    if length < 8:
        raise ValueError("length must be >= 8")
    pool = _PW_ALPHABET_LOWER + _PW_ALPHABET_UPPER + _PW_ALPHABET_DIGITS + _PW_ALPHABET_SYMBOL
    required = [
        secrets.choice(_PW_ALPHABET_LOWER),
        secrets.choice(_PW_ALPHABET_UPPER),
        secrets.choice(_PW_ALPHABET_DIGITS),
        secrets.choice(_PW_ALPHABET_SYMBOL),
    ]
    rest = [secrets.choice(pool) for _ in range(length - len(required))]
    chars = required + rest
    # Fisher-Yates shuffle using secrets for unbiased permutation.
    for i in range(len(chars) - 1, 0, -1):
        j = secrets.randbelow(i + 1)
        chars[i], chars[j] = chars[j], chars[i]
    return "".join(chars)


@admin_router.post(
    "/create-employee",
    response_model=EmployeeCredsResponse,
    status_code=201,
)
async def admin_create_employee(body: AdminCreateEmployeeRequest, request: Request):
    """
    Provision an employee account.

    Inserts a row into `employees` AND a linked row into `users` with
    role='employee', inside one DB transaction. Returns the generated
    credentials exactly once — the password is never stored in plain text
    and cannot be retrieved later.
    """
    from api.main import SessionLocal, employees_table
    import json as _json

    async with SessionLocal() as db:
        # Seed user_id from email local-part if given, else from the name.
        # _allocate_user_id already lowercases and strips unsafe chars.
        seed_source = body.email if body.email else body.name
        user_id = await _allocate_user_id(db, seed_source)

        # Email handling: if admin omitted it, synthesize a stable placeholder
        # so the NOT NULL constraint is satisfied. Admin can edit later.
        email = (body.email or f"{user_id}@bootstrap.aegis-pm.app").lower()

        # Uniqueness guard across both identifiers.
        existing = (
            await db.execute(
                sa.select(users_table.c.id).where(
                    sa.or_(
                        sa.func.lower(users_table.c.email) == email,
                        users_table.c.user_id == user_id,
                    )
                )
            )
        ).first()
        if existing:
            raise HTTPException(409, "Email or user_id already exists")

        # Generate creds.
        plain_pw = _generate_password(14)
        pw_hash  = hash_password(plain_pw)

        # 1) employees row first so we can link its id from the user row.
        emp_result = await db.execute(
            employees_table.insert()
            .values(
                name=body.name,
                email=body.email,                        # may be None
                role=body.role_title,                    # job title, not RBAC role
                skills=_json.dumps(body.skills or []),
                availability="available",
            )
            .returning(employees_table)
        )
        emp_row = emp_result.mappings().first()

        # 2) users row linked to that employee.
        usr_result = await db.execute(
            users_table.insert()
            .values(
                user_id=user_id,
                email=email,
                full_name=body.name,
                password_hash=pw_hash,
                role="employee",
                employee_id=emp_row["id"],
            )
            .returning(users_table)
        )
        usr_row = usr_result.mappings().first()
        await db.commit()

        ip, _ = _client_meta(request)
        log.info(
            "Employee provisioned: user_id=%s employee_id=%s by_ip=%s",
            usr_row["user_id"], emp_row["id"], ip,
        )

        return EmployeeCredsResponse(
            user=UserOut(**dict(usr_row)),
            employee_id=emp_row["id"],
            generated_user_id=usr_row["user_id"],
            generated_password=plain_pw,
        )


# Back-compat alias — keep the old /auth/users endpoint pointing at the
# same admin-guarded listing so existing frontend calls don't break.
@router.get("/users", response_model=list[UserOut])
async def list_users_legacy(_admin: dict = Depends(require_admin)):
    return await admin_list_users()


# ── Password reset ───────────────────────────────────────────────────────────

class ForgotPasswordRequest(BaseModel):
    # Accept either the login handle or the account email. We never echo
    # which one matched — that would be a user-enumeration oracle.
    user_id: Optional[str] = Field(None, min_length=1, max_length=64)
    email:   Optional[EmailStr] = None


class ResetPasswordRequest(BaseModel):
    token:        str = Field(..., min_length=20, max_length=128)
    new_password: str = Field(..., min_length=8,  max_length=128)


def _hash_reset_token(raw: str) -> str:
    """sha256 hex. We only store the hash so DB leak ≠ password-reset takeover."""
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _validate_password_strength(pw: str) -> None:
    if len(pw) < 8:
        raise HTTPException(400, "Password must be at least 8 characters")
    if len(pw) > 128:
        raise HTTPException(400, "Password too long (max 128)")
    # Quick complexity floor — not a substitute for a breach-corpus check,
    # but catches obvious weaklings.
    has_letter = any(c.isalpha() for c in pw)
    has_digit  = any(c.isdigit() for c in pw)
    if not (has_letter and has_digit):
        raise HTTPException(400, "Password must contain both letters and digits")


@router.post("/forgot-password", status_code=202)
async def forgot_password(body: ForgotPasswordRequest, request: Request):
    """
    Request a password-reset email.

    Security:
      - Always returns 202 so the response is identical whether or not
        the account exists (prevents user-enumeration).
      - Issues a single-use random token (32 bytes, urlsafe b64), only the
        sha256 is stored in DB; the raw token is emailed.
      - Rate-limited per user (RESET_RATE_MAX requests per RESET_RATE_WINDOW_M).
      - Token TTL defaults to 30 min.
    """
    if not body.user_id and not body.email:
        raise HTTPException(400, "user_id or email required")

    from api.main import SessionLocal
    ip, _ = _client_meta(request)

    async with SessionLocal() as db:
        q = sa.select(users_table)
        if body.user_id:
            q = q.where(users_table.c.user_id == body.user_id)
        else:
            q = q.where(users_table.c.email == body.email)
        row = (await db.execute(q)).mappings().first()

        if row and row["is_active"]:
            # Rate limit: count active (non-expired) requests in window.
            window_start = datetime.now(timezone.utc) - timedelta(minutes=RESET_RATE_WINDOW_M)
            recent = (
                await db.execute(
                    sa.select(sa.func.count())
                    .select_from(password_reset_tokens_table)
                    .where(
                        password_reset_tokens_table.c.user_id == row["id"],
                        password_reset_tokens_table.c.created_at >= window_start,
                    )
                )
            ).scalar_one()
            if recent >= RESET_RATE_MAX:
                log.warning("pw-reset rate-limited user=%s ip=%s", row["user_id"], ip)
            else:
                raw_token  = secrets.token_urlsafe(32)
                token_hash = _hash_reset_token(raw_token)
                expires_at = datetime.now(timezone.utc) + timedelta(minutes=RESET_TOKEN_TTL_MIN)

                await db.execute(
                    password_reset_tokens_table.insert().values(
                        user_id=row["id"],
                        token_hash=token_hash,
                        expires_at=expires_at,
                        ip_requested=ip,
                    )
                )
                await db.commit()

                reset_link = f"{RESET_BASE_URL}/reset-password/{raw_token}"
                if row["email"]:
                    try:
                        await get_sender().send(EmailMessage(
                            to=row["email"],
                            subject="Reset your Aegis PM password",
                            body=(
                                f"Hi {row['full_name'] or row['user_id']},\n\n"
                                f"A password reset was requested for your account.\n"
                                f"This link is valid for {RESET_TOKEN_TTL_MIN} minutes and may be used once:\n\n"
                                f"    {reset_link}\n\n"
                                f"If you didn't request this, you can ignore this email — "
                                f"your password will remain unchanged.\n"
                            ),
                        ))
                    except Exception as e:
                        # We never leak the token back via the HTTP response.
                        log.error("pw-reset email send failed user=%s: %s", row["user_id"], e)
                else:
                    log.warning("pw-reset requested for user=%s but no email on file", row["user_id"])

        # Identical shape regardless of outcome.
        return {"ok": True}


@router.post("/reset-password", status_code=200)
async def reset_password(body: ResetPasswordRequest, request: Request):
    """
    Consume a reset token and set a new password.

    On success:
      - password_hash is updated (bcrypt).
      - The reset token is marked consumed.
      - ALL active sessions for the user are revoked — forces re-login on
        every device, limiting blast radius if the old password was stolen.
    """
    _validate_password_strength(body.new_password)

    from api.main import SessionLocal
    token_hash = _hash_reset_token(body.token)
    now = datetime.now(timezone.utc)

    async with SessionLocal() as db:
        tok = (
            await db.execute(
                sa.select(password_reset_tokens_table)
                .where(password_reset_tokens_table.c.token_hash == token_hash)
            )
        ).mappings().first()

        if not tok or tok["consumed_at"] is not None or tok["expires_at"] < now:
            # Uniform 400 for all failure modes — do not leak which.
            raise HTTPException(400, "Invalid or expired reset token")

        new_hash = hash_password(body.new_password)
        await db.execute(
            users_table.update()
            .where(users_table.c.id == tok["user_id"])
            .values(password_hash=new_hash, updated_at=now)
        )
        await db.execute(
            password_reset_tokens_table.update()
            .where(password_reset_tokens_table.c.id == tok["id"])
            .values(consumed_at=now)
        )
        # Revoke all of this user's sessions — any live JWT stops working.
        await db.execute(
            user_sessions_table.update()
            .where(
                user_sessions_table.c.user_id == tok["user_id"],
                user_sessions_table.c.revoked.is_(False),
            )
            .values(revoked=True)
        )
        await db.commit()

        log.info("pw-reset completed user_id=%s", tok["user_id"])

    return {"ok": True}


@router.get("/sessions")
async def my_sessions(user: dict = Depends(get_current_user)):
    """List this user's active devices (for self-serve revocation)."""
    from api.main import SessionLocal
    async with SessionLocal() as db:
        rows = (
            await db.execute(
                sa.select(user_sessions_table)
                .where(
                    user_sessions_table.c.user_id == user["id"],
                    user_sessions_table.c.revoked.is_(False),
                )
                .order_by(user_sessions_table.c.last_seen_at.desc())
            )
        ).mappings().all()
    return [
        {
            "id":           r["id"],
            "device":       r["device"],
            "ip_address":   r["ip_address"],
            "created_at":   r["created_at"],
            "last_seen_at": r["last_seen_at"],
            "current":      r["id"] == user["session_id"],
        }
        for r in rows
    ]
