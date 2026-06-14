"""
aegis-pm / api / staging.py

Admin bulk-upload workflow (spec §1–§8, §11–§12).

All endpoints live on the existing admin_router gate, so the route-level
require_admin check from api.auth applies without re-wiring. The module
is deliberately self-contained — its only imports from api.main are the
Session and existing SA tables.

Endpoints (all admin-only):
  POST /admin/upload-employees           multipart file → parse → stage
  GET  /admin/staging                    list pending staging rows (optionally ?batch_id=)
  GET  /admin/recommended-employees      rank staging rows against a required-skills list
  POST /admin/create-selected-employees  promote selected staging ids → users + employees
  GET  /admin/credentials-export         CSV download of a provisioning batch's credentials
  POST /admin/assign-task-ai             suggest + confirm best employee for a task
"""
from __future__ import annotations

import csv
import io
import json
import logging
import os
import secrets
import uuid
from datetime import datetime
from typing import Optional

import sqlalchemy as sa
from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
)
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import _allocate_user_id, _generate_password, hash_password, require_admin
from api.matching import MatchResult, score as score_async
from api.models import employee_staging_table, users_table

log = logging.getLogger("aegis.staging")

MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", str(5 * 1024 * 1024)))   # 5 MB
MAX_ROWS_PER_UPLOAD = int(os.getenv("MAX_ROWS_PER_UPLOAD", "500"))

# In-process cache of the last-generated credentials per batch, so the
# admin can download a CSV even after closing and re-opening the modal.
# Passwords are PLAINTEXT here — dropped after 10 minutes or on process
# restart. Never persisted.
_CREDS_CACHE: dict[str, list[dict]] = {}
_CREDS_CACHE_TS: dict[str, datetime] = {}
_CREDS_TTL_MIN = 10


def _prune_creds_cache() -> None:
    cutoff = datetime.utcnow()
    dead = [
        k for k, ts in _CREDS_CACHE_TS.items()
        if (cutoff - ts).total_seconds() > _CREDS_TTL_MIN * 60
    ]
    for k in dead:
        _CREDS_CACHE.pop(k, None)
        _CREDS_CACHE_TS.pop(k, None)


# ── Router ──────────────────────────────────────────────────────────────────

router = APIRouter(
    prefix="/admin",
    tags=["Admin · Staging"],
    dependencies=[Depends(require_admin)],
)


# ── Schemas ─────────────────────────────────────────────────────────────────

class UploadSummary(BaseModel):
    batch_id:           str
    rows_parsed:        int
    rows_staged:        int
    duplicates_skipped: int
    errors:             list[str] = []


class StagingRowOut(BaseModel):
    id:                  int
    name:                str
    email:               Optional[str]
    skills:              list[str]
    experience:          Optional[float]
    department:          Optional[str] = None
    is_manager:          bool = False
    upload_batch_id:     str
    status:              str
    created_at:          datetime


class RecommendationOut(BaseModel):
    staging_id:       int
    name:             str
    email:            Optional[str]
    skills:           list[str]
    experience:       Optional[float]
    department:       Optional[str] = None
    is_manager:       bool = False
    score:            float
    skill_score:      float = 0.0       # skill similarity (semantic or keyword)
    experience_score: float = 0.0
    priority_bonus:   float = 0.0
    confidence:       float = 0.0       # alias of skill_score
    matched_skills:   list[str]
    missing_skills:   list[str]
    reason:           str   = ""
    semantic:         bool  = False


class CreateSelectedRequest(BaseModel):
    staging_ids: list[int] = Field(..., min_length=1, max_length=200)


class ProvisionedCred(BaseModel):
    name:        str
    email:       Optional[str]
    user_id:     str
    password:    str          # plaintext, shown ONCE
    employee_id: int          # needed to assign tasks inline in the UI


class CreateSelectedResponse(BaseModel):
    batch_id:   str
    created:    list[ProvisionedCred]
    skipped:    list[dict]   # {staging_id, reason}


class AssignTaskAiRequest(BaseModel):
    task_id:     int
    confirm:     bool = False                 # False = dry-run suggestion
    # If omitted, we pull required_skills from tasks.required_skills.
    required:    Optional[list[str]] = None
    priority:    Optional[list[str]] = None   # weighted higher in the score
    # Candidate pool — default to all active employees linked to a user.
    candidates:  Optional[list[int]] = None   # employee_ids


# ── Helpers ─────────────────────────────────────────────────────────────────

def _file_size_ok(upload: UploadFile, size: int) -> None:
    if size > MAX_UPLOAD_BYTES:
        raise HTTPException(
            413, f"File exceeds {MAX_UPLOAD_BYTES // (1024*1024)} MB limit ({size} bytes)"
        )


async def _existing_emails_and_names(db: AsyncSession) -> tuple[set[str], set[str]]:
    """For dedup: pull the set of emails and names already in employees."""
    from api.main import employees_table
    rows = (await db.execute(
        sa.select(employees_table.c.email, employees_table.c.name)
    )).all()
    emails = {e.lower() for (e, _) in rows if e}
    names  = {n.strip().lower() for (_, n) in rows if n}
    return emails, names


def _stage_row_to_out(row: dict) -> StagingRowOut:
    try:
        skills = json.loads(row.get("skills") or "[]")
    except Exception:
        skills = []
    return StagingRowOut(
        id=row["id"],
        name=row["name"],
        email=row["email"],
        skills=skills,
        experience=row.get("experience"),
        department=row.get("department"),
        is_manager=bool(row.get("is_manager")),
        upload_batch_id=row["upload_batch_id"],
        status=row["status"],
        created_at=row["created_at"],
    )


# ── 1. Upload ───────────────────────────────────────────────────────────────

@router.post("/upload-employees", response_model=UploadSummary)
async def upload_employees(
    request: Request,
    file:    UploadFile = File(...),
    admin:   dict = Depends(require_admin),
):
    """
    Accept an xlsx / csv / pdf file, parse it, and stage the rows.

    Validation order per row:
      1. `name` present                           (drop otherwise)
      2. dedup against `employees.email` / name   (→ status='duplicate')
      3. dedup against same-batch earlier rows    (→ skip)
    """
    from api.main import SessionLocal
    from api.parsers import parse_file

    contents = await file.read()
    _file_size_ok(file, len(contents))

    if not file.filename:
        raise HTTPException(400, "filename missing")

    try:
        parsed, parse_errors = parse_file(file.filename, contents)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except RuntimeError as e:
        # Missing optional parser dep (e.g. pdfplumber).
        raise HTTPException(500, str(e))

    if len(parsed) > MAX_ROWS_PER_UPLOAD:
        raise HTTPException(
            400,
            f"File contains {len(parsed)} rows; max {MAX_ROWS_PER_UPLOAD} per upload.",
        )
    if not parsed and not parse_errors:
        raise HTTPException(400, "No usable rows found. Ensure the file has a 'Name' column.")

    batch_id = uuid.uuid4().hex[:16]

    async with SessionLocal() as db:
        existing_emails, existing_names = await _existing_emails_and_names(db)
        seen_emails: set[str] = set()
        seen_names:  set[str] = set()
        rows_staged = 0
        duplicates  = 0
        errors: list[str] = list(parse_errors)  # surface validator errors to UI

        insert_rows = []
        for idx, r in enumerate(parsed):
            email_key = (r.get("email") or "").lower()
            name_key  = r["name"].strip().lower()
            is_dup = (
                (email_key and email_key in existing_emails) or
                (email_key and email_key in seen_emails) or
                # Name-only dup only if the existing record has no email match AND
                # the new row also has no email. Avoids false positives.
                (not email_key and name_key in existing_names)
            )
            status = "duplicate" if is_dup else "pending"
            if is_dup:
                duplicates += 1

            if email_key:
                seen_emails.add(email_key)
            seen_names.add(name_key)

            insert_rows.append({
                "name":       r["name"],
                "email":      r.get("email"),
                "skills":     r.get("skills") or "[]",
                "experience": r.get("experience"),
                "department": r.get("department"),
                "is_manager": bool(r.get("is_manager")),
                "raw_metadata":    r.get("extras"),
                "upload_batch_id": batch_id,
                "uploaded_by_user_id": admin["id"],
                "status":          status,
            })
            if status == "pending":
                rows_staged += 1

        if insert_rows:
            await db.execute(employee_staging_table.insert(), insert_rows)
            await db.commit()

    log.info(
        "upload: batch=%s filename=%s parsed=%d staged=%d duplicates=%d",
        batch_id, file.filename, len(parsed), rows_staged, duplicates,
    )
    return UploadSummary(
        batch_id=batch_id,
        rows_parsed=len(parsed),
        rows_staged=rows_staged,
        duplicates_skipped=duplicates,
        errors=errors,
    )


# ── 2. List staged ──────────────────────────────────────────────────────────

@router.get("/staging", response_model=list[StagingRowOut])
async def list_staging(
    batch_id: Optional[str] = Query(None),
    status:   Optional[str] = Query(None, pattern=r"^(pending|promoted|rejected|duplicate)$"),
    limit:    int = Query(500, ge=1, le=1000),
):
    from api.main import SessionLocal
    async with SessionLocal() as db:
        q = sa.select(employee_staging_table)
        if batch_id:
            q = q.where(employee_staging_table.c.upload_batch_id == batch_id)
        if status:
            q = q.where(employee_staging_table.c.status == status)
        q = q.order_by(employee_staging_table.c.created_at.desc()).limit(limit)
        rows = (await db.execute(q)).mappings().all()
    return [_stage_row_to_out(dict(r)) for r in rows]


# ── 3. AI recommendations ───────────────────────────────────────────────────

@router.get("/recommended-employees", response_model=list[RecommendationOut])
async def recommended_employees(
    skills:         str   = Query(..., description="Required skills, comma-separated"),
    priority:       Optional[str] = Query(None, description="Priority subset, comma-separated"),
    batch_id:       Optional[str] = Query(None, description="Rank only this upload batch"),
    min_experience: float = Query(0.0, ge=0.0, description="Drop candidates below this many years"),
    min_score:      float = Query(0.0, ge=0.0, le=1.0, description="Drop candidates scoring below this"),
    limit:          int   = Query(20, ge=1, le=100),
):
    """
    Rank pending staging rows against required skills.

    Scoring: semantic (OpenAI embeddings, if OPENAI_API_KEY) with keyword
    Jaccard fallback. See api/matching.score() for the formula.

    Optional `priority` is a comma-separated subset of `skills` that must
    be present (adds a 10% bonus). Use it to express "React is nice-to-
    have, but TypeScript is non-negotiable".
    """
    from api.main import SessionLocal

    required = [s.strip() for s in skills.split(",") if s.strip()]
    if not required:
        raise HTTPException(400, "skills parameter is empty")
    priority_list = (
        [s.strip() for s in priority.split(",") if s.strip()] if priority else None
    )

    async with SessionLocal() as db:
        q = sa.select(employee_staging_table).where(
            employee_staging_table.c.status == "pending"
        )
        if batch_id:
            q = q.where(employee_staging_table.c.upload_batch_id == batch_id)
        # Pre-filter by experience at the DB level — saves scoring rows we'd
        # drop anyway. NULL experience is treated as 0 so it falls out when
        # min_experience > 0.
        if min_experience > 0:
            q = q.where(
                sa.func.coalesce(employee_staging_table.c.experience, 0.0) >= min_experience
            )
        rows = (await db.execute(q)).mappings().all()

    scored: list[tuple[MatchResult, dict]] = []
    for row in rows:
        result = await score_async(
            required, row["skills"], row.get("experience"), priority_list
        )
        if result.score < min_score:
            continue
        scored.append((result, dict(row)))

    scored.sort(
        key=lambda pair: (
            -pair[0].score,
            -(pair[1].get("experience") or 0),
            pair[1]["name"].lower(),
        )
    )

    out: list[RecommendationOut] = []
    for result, row in scored[:limit]:
        try:
            row_skills = json.loads(row.get("skills") or "[]")
        except Exception:
            row_skills = []
        out.append(RecommendationOut(
            staging_id=row["id"],
            name=row["name"],
            email=row["email"],
            skills=row_skills,
            experience=row.get("experience"),
            department=row.get("department"),
            is_manager=bool(row.get("is_manager")),
            score=round(result.score, 4),
            skill_score=round(result.skill_score, 4),
            experience_score=round(result.experience_score, 4),
            priority_bonus=round(result.priority_bonus, 4),
            confidence=round(result.confidence, 4),
            matched_skills=result.matched_skills,
            missing_skills=result.missing_skills,
            reason=result.reason,
            semantic=result.semantic,
        ))
    return out


# ── 4. Promote selected → users + employees ─────────────────────────────────

@router.post(
    "/create-selected-employees",
    response_model=CreateSelectedResponse,
    status_code=201,
)
async def create_selected_employees(body: CreateSelectedRequest):
    """
    Atomic per-row promotion.

    For each staging_id:
      1. Load row; skip if not `pending`.
      2. Dedup against users/employees by email.
      3. Create an `employees` row (name, email, skills).
      4. Create a `users` row with role='employee' linked to that employee.
      5. Mark staging row status='promoted' with the new employee_id.

    Returns the list of provisioned credentials ONCE. The plaintext
    passwords are also cached for CSV export for 10 minutes.
    """
    from api.main import SessionLocal, employees_table

    batch_ref = uuid.uuid4().hex[:12]
    _prune_creds_cache()

    created: list[ProvisionedCred] = []
    skipped: list[dict] = []

    async with SessionLocal() as db:
        for sid in body.staging_ids:
            row = (await db.execute(
                sa.select(employee_staging_table).where(employee_staging_table.c.id == sid)
            )).mappings().first()
            if not row:
                skipped.append({"staging_id": sid, "reason": "not_found"})
                continue
            if row["status"] != "pending":
                skipped.append({"staging_id": sid, "reason": f"status={row['status']}"})
                continue

            email = (row["email"] or "").lower() or None

            # Dedup at promotion time, too — another admin might have added
            # the same person concurrently.
            if email:
                dup = (await db.execute(
                    sa.select(users_table.c.id).where(
                        sa.func.lower(users_table.c.email) == email
                    )
                )).first()
                if dup:
                    skipped.append({"staging_id": sid, "reason": "user_email_exists"})
                    await db.execute(
                        employee_staging_table.update()
                        .where(employee_staging_table.c.id == sid)
                        .values(status="duplicate")
                    )
                    continue

            # Allocate a unique user_id from the email or name.
            seed = email or row["name"]
            user_id = await _allocate_user_id(db, seed)

            # If no email on file, synthesize one so the NOT NULL constraint
            # holds. Admin can update it later.
            user_email = email or f"{user_id}@bootstrap.aegis-pm.app"

            # Secure one-time password.
            plain_pw = _generate_password(14)
            pw_hash  = hash_password(plain_pw)

            # 1) employees row
            emp_ins = await db.execute(
                employees_table.insert()
                .values(
                    name=row["name"],
                    email=row["email"],                   # keep original (may be null)
                    role=None,
                    skills=row.get("skills") or "[]",     # carry JSON-encoded list forward
                    availability="available",
                    department=row.get("department"),     # carry dept/manager forward
                    is_manager=bool(row.get("is_manager")),
                )
                .returning(employees_table)
            )
            emp = emp_ins.mappings().first()

            # 2) users row
            usr_ins = await db.execute(
                users_table.insert()
                .values(
                    user_id=user_id,
                    email=user_email,
                    full_name=row["name"],
                    password_hash=pw_hash,
                    role="employee",
                    employee_id=emp["id"],
                )
                .returning(users_table)
            )
            _ = usr_ins.mappings().first()

            # 3) mark staging promoted
            await db.execute(
                employee_staging_table.update()
                .where(employee_staging_table.c.id == sid)
                .values(status="promoted", promoted_to_employee_id=emp["id"])
            )

            created.append(ProvisionedCred(
                name=row["name"],
                email=row["email"],
                user_id=user_id,
                password=plain_pw,
                employee_id=emp["id"],
            ))

        await db.commit()

    # Cache plaintext creds for the CSV export window.
    _CREDS_CACHE[batch_ref]    = [c.model_dump() for c in created]
    _CREDS_CACHE_TS[batch_ref] = datetime.utcnow()

    log.info(
        "promoted: batch_ref=%s created=%d skipped=%d",
        batch_ref, len(created), len(skipped),
    )
    return CreateSelectedResponse(batch_id=batch_ref, created=created, skipped=skipped)


# ── 5. CSV export of the just-provisioned credentials ───────────────────────

@router.get("/credentials-export")
async def credentials_export(batch_id: str = Query(...)):
    """
    Return the plaintext credentials from a recent /create-selected-employees
    call as text/csv. Only available for 10 minutes after creation and only
    in-process — if the API restarts, the batch is gone.
    """
    _prune_creds_cache()
    rows = _CREDS_CACHE.get(batch_id)
    if rows is None:
        raise HTTPException(404, "Credentials batch not found or expired")

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["name", "email", "user_id", "password"])
    for r in rows:
        writer.writerow([r["name"], r.get("email") or "", r["user_id"], r["password"]])
    csv_body = buf.getvalue()

    return Response(
        content=csv_body,
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="aegis-credentials-{batch_id}.csv"',
            "Cache-Control": "no-store",
        },
    )


# ── 6. AI task → employee suggestion ────────────────────────────────────────

@router.post("/assign-task-ai")
async def assign_task_ai(body: AssignTaskAiRequest):
    """
    Suggest (and optionally commit) the best employee for a task.

    Source of required skills (in order):
      1. body.required  — admin override
      2. tasks.required_skills  — canonical per-task field
      3. None ⇒ ranks candidates purely on experience

    Candidate pool: body.candidates (employee_ids) or all employees.
    Dry-run by default; pass `confirm: true` to atomically write the
    assignment to tasks.assigned_to.
    """
    from api.main import SessionLocal, employees_table, tasks_table

    async with SessionLocal() as db:
        task = (await db.execute(
            sa.select(tasks_table).where(tasks_table.c.id == body.task_id)
        )).mappings().first()
        if not task:
            raise HTTPException(404, f"Task {body.task_id} not found")

        if body.required:
            required = body.required
        else:
            try:
                required = json.loads(task.get("required_skills") or "[]")
            except Exception:
                required = []

        q = sa.select(employees_table)
        if body.candidates:
            q = q.where(employees_table.c.id.in_(body.candidates))
        employees = (await db.execute(q)).mappings().all()

        scored = []
        for e in employees:
            result = await score_async(required, e.get("skills"), None, body.priority)
            scored.append((result, dict(e)))
        scored.sort(key=lambda p: -p[0].score)

        top = scored[:5]
        recommendations = [
            {
                "employee_id":   emp["id"],
                "name":          emp["name"],
                "skills":        json.loads(emp.get("skills") or "[]"),
                "score":         round(res.score, 4),
                "confidence":    round(res.confidence, 4),
                "matched":       res.matched_skills,
                "missing":       res.missing_skills,
                "reason":        res.reason,
                "semantic":      res.semantic,
            }
            for res, emp in top
        ]

        assigned = None
        if body.confirm and top:
            res, emp = top[0]
            await db.execute(
                tasks_table.update()
                .where(tasks_table.c.id == body.task_id)
                .values(
                    assigned_to=emp["id"],
                    assigned_name=emp["name"],
                    ai_confidence=res.score,
                )
            )
            await db.commit()
            assigned = {"employee_id": emp["id"], "name": emp["name"], "score": res.score}

            # Push the assignment to the employee's dashboard in real time.
            try:
                from api.notifications import notify
                target_user = (
                    await db.execute(
                        sa.select(users_table.c.id)
                        .where(users_table.c.employee_id == emp["id"])
                    )
                ).first()
                if target_user:
                    await notify(
                        db,
                        user_id=target_user[0],
                        kind="task_assigned",
                        title=f"New task: {task['title']}",
                        body=f"AI assigned you this task (match {int(res.score * 100)}%)",
                        resource_type="task",
                        resource_id=body.task_id,
                    )
            except Exception as e:
                log.warning("assign-task-ai notify failed task=%d: %s", body.task_id, e)

            log.info(
                "assign-task-ai: task=%d → employee=%s (score=%.3f)",
                body.task_id, emp["name"], res.score,
            )

        return {
            "task_id":        body.task_id,
            "required":       required,
            "recommendations": recommendations,
            "assigned":       assigned,
        }


# ── 7. Persisted analysis (POST /admin/analyze-employees) ──────────────────

class AnalyzeRequest(BaseModel):
    required:       list[str] = Field(..., min_length=1)
    priority:       Optional[list[str]] = None
    min_experience: float = Field(0.0, ge=0.0)
    batch_id:       Optional[str] = None


class AnalysisRowOut(BaseModel):
    staging_id:       int
    name:             str
    email:            Optional[str]
    experience:       Optional[float]
    score:            float
    skill_score:      float
    experience_score: float
    priority_bonus:   float
    confidence:       float
    matched_skills:   list[str]
    missing_skills:   list[str]
    reason:           str
    semantic:         bool
    analyzed_at:      datetime


class AnalyzeResponse(BaseModel):
    requirement_hash: str
    analyzed:         int
    top:              list[AnalysisRowOut]


def _requirement_hash(required: list[str], priority: list[str] | None, min_exp: float) -> str:
    """Deterministic hash so re-running the same spec reuses cache rows."""
    import hashlib
    req = sorted({s.strip().lower() for s in required if s.strip()})
    pri = sorted({s.strip().lower() for s in (priority or []) if s.strip()})
    key = json.dumps({"req": req, "pri": pri, "min_exp": round(min_exp, 2)}, sort_keys=True)
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


@router.post("/analyze-employees", response_model=AnalyzeResponse)
async def analyze_employees(body: AnalyzeRequest, admin: dict = Depends(require_admin)):
    """
    Score every pending staging row against the given requirements and
    persist the results into `employee_analysis`.

    Keyed by `requirement_hash` so two admins submitting the same spec
    share rows. Does not remove prior analyses — call again to create a
    fresh snapshot. Use `GET /admin/employee-scores?requirement_hash=...`
    to read them back, or the returned `top` list inline.
    """
    from api.main import SessionLocal
    from api.models import employee_analysis_table

    req_hash = _requirement_hash(body.required, body.priority, body.min_experience)

    async with SessionLocal() as db:
        q = sa.select(employee_staging_table).where(
            employee_staging_table.c.status == "pending"
        )
        if body.batch_id:
            q = q.where(employee_staging_table.c.upload_batch_id == body.batch_id)
        if body.min_experience > 0:
            q = q.where(
                sa.func.coalesce(employee_staging_table.c.experience, 0.0)
                >= body.min_experience
            )
        rows = (await db.execute(q)).mappings().all()

        inserted: list[tuple[MatchResult, dict]] = []
        rows_to_insert: list[dict] = []
        for row in rows:
            r = await score_async(
                body.required, row["skills"], row.get("experience"), body.priority
            )
            inserted.append((r, dict(row)))
            rows_to_insert.append({
                "staging_id":         row["id"],
                "requirement_hash":   req_hash,
                "required_skills":    json.dumps(body.required),
                "priority_skills":    json.dumps(body.priority or []),
                "min_experience":     body.min_experience or None,
                "score":              round(r.score, 4),
                "skill_score":        round(r.skill_score, 4),
                "experience_score":   round(r.experience_score, 4),
                "priority_bonus":     round(r.priority_bonus, 4),
                "confidence":         round(r.confidence, 4),
                "matched_skills":     json.dumps(r.matched_skills),
                "missing_skills":     json.dumps(r.missing_skills),
                "reason":             r.reason,
                "semantic":           r.semantic,
                "analyzed_by_user_id": admin["id"],
            })

        if rows_to_insert:
            await db.execute(employee_analysis_table.insert(), rows_to_insert)
            await db.commit()

    inserted.sort(
        key=lambda pair: (
            -pair[0].score,
            -(pair[1].get("experience") or 0),
            pair[1]["name"].lower(),
        )
    )
    now = datetime.utcnow()
    top = [
        AnalysisRowOut(
            staging_id=row["id"],
            name=row["name"],
            email=row["email"],
            experience=row.get("experience"),
            score=round(r.score, 4),
            skill_score=round(r.skill_score, 4),
            experience_score=round(r.experience_score, 4),
            priority_bonus=round(r.priority_bonus, 4),
            confidence=round(r.confidence, 4),
            matched_skills=r.matched_skills,
            missing_skills=r.missing_skills,
            reason=r.reason,
            semantic=r.semantic,
            analyzed_at=now,
        )
        for r, row in inserted[:50]
    ]
    log.info("analyze-employees: hash=%s analyzed=%d", req_hash, len(rows_to_insert))
    return AnalyzeResponse(
        requirement_hash=req_hash,
        analyzed=len(rows_to_insert),
        top=top,
    )


@router.get("/employee-scores", response_model=list[AnalysisRowOut])
async def employee_scores(
    requirement_hash: Optional[str] = Query(None, description="Read a specific analysis"),
    batch_id:         Optional[str] = Query(None, description="Filter by upload batch"),
    min_score:        float         = Query(0.0, ge=0.0, le=1.0),
    limit:            int           = Query(100, ge=1, le=500),
):
    """
    Read the most-recent persisted analysis for each staging row.

    Without `requirement_hash`, returns the latest score per (staging_id)
    regardless of which spec produced it — handy for "show me the current
    state of this batch".

    With `requirement_hash`, returns every candidate scored against that
    exact spec, ordered by score desc.
    """
    from api.main import SessionLocal
    from api.models import employee_analysis_table

    a = employee_analysis_table.c
    s = employee_staging_table.c

    if requirement_hash:
        # Deterministic query: all rows for this spec, latest-per-staging.
        subq = (
            sa.select(
                a.staging_id,
                sa.func.max(a.analyzed_at).label("ts"),
            )
            .where(a.requirement_hash == requirement_hash)
            .group_by(a.staging_id)
            .subquery()
        )
    else:
        subq = (
            sa.select(
                a.staging_id,
                sa.func.max(a.analyzed_at).label("ts"),
            )
            .group_by(a.staging_id)
            .subquery()
        )

    q = (
        sa.select(a, s.name, s.email, s.experience)
        .select_from(
            employee_analysis_table
            .join(subq, sa.and_(
                a.staging_id == subq.c.staging_id,
                a.analyzed_at == subq.c.ts,
            ))
            .join(employee_staging_table, s.id == a.staging_id)
        )
        .where(a.score >= min_score)
    )
    if batch_id:
        q = q.where(s.upload_batch_id == batch_id)
    q = q.order_by(a.score.desc()).limit(limit)

    async with SessionLocal() as db:
        rows = (await db.execute(q)).mappings().all()

    out: list[AnalysisRowOut] = []
    for r in rows:
        out.append(AnalysisRowOut(
            staging_id=r["staging_id"],
            name=r["name"],
            email=r["email"],
            experience=r["experience"],
            score=r["score"],
            skill_score=r["skill_score"],
            experience_score=r["experience_score"],
            priority_bonus=r["priority_bonus"],
            confidence=r["confidence"],
            matched_skills=json.loads(r["matched_skills"] or "[]"),
            missing_skills=json.loads(r["missing_skills"] or "[]"),
            reason=r["reason"] or "",
            semantic=bool(r["semantic"]),
            analyzed_at=r["analyzed_at"],
        ))
    return out


# ── 8. Warm the embeddings cache for existing employees ────────────────────

@router.post("/embeddings/warm")
async def warm_embeddings():
    """
    Batch-compute embeddings for every employee's skill string so the first
    admin search is fast. Idempotent — uses the same ON CONFLICT path as
    regular get_embedding_batch calls, so re-running is cheap.

    Returns:  { available, employees, warmed }
      available  — whether OPENAI_API_KEY is configured
      employees  — total employees with non-empty skills
      warmed     — embeddings successfully produced (already-cached count)
    """
    from api.embeddings import get_embedding_batch, is_available
    from api.main import SessionLocal, employees_table
    from api.matching import _split_skills, _to_sorted_csv

    available = is_available()
    if not available:
        return {"available": False, "employees": 0, "warmed": 0}

    async with SessionLocal() as db:
        rows = (
            await db.execute(
                sa.select(employees_table.c.id, employees_table.c.skills)
            )
        ).all()

    texts = []
    for _, raw_skills in rows:
        tokens = _split_skills(raw_skills)
        if tokens:
            texts.append(_to_sorted_csv(tokens))

    if not texts:
        return {"available": True, "employees": 0, "warmed": 0}

    vectors = await get_embedding_batch(texts)
    warmed = sum(1 for v in vectors if v is not None)
    log.info("embeddings warmed: employees=%d warmed=%d", len(texts), warmed)
    return {"available": True, "employees": len(texts), "warmed": warmed}
