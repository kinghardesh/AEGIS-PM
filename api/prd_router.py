"""
aegis-pm / api / prd_router.py

Admin PRD pipeline endpoints (spec §1, §2, §3, §14).

Thin wrappers over the existing staging + analysis layer — no business
logic duplicated. The workflow is:

  1. POST /admin/upload-prd              file → raw_text + extracted skills
  2. POST /admin/parse-prd/{id}          re-run extraction on an existing PRD
  3. POST /admin/analyze-candidates      rank staging rows against a PRD's skills
  4. GET  /admin/ranked-candidates       read cached analysis by PRD
  5. POST /admin/select-candidates       alias for /admin/create-selected-employees

All endpoints inherit the admin-only guard from the router-level dependency.
"""
from __future__ import annotations

import json
import logging
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
    UploadFile,
)
from pydantic import BaseModel, Field

from api.auth import require_admin
from api.models import prd_documents_table, prd_extracted_skills_table
from api.prd_parser import (
    extract_project_package,
    extract_skills,
    extract_text,
)
from api.staging import AnalyzeRequest, AnalyzeResponse

log = logging.getLogger("aegis.prd")

MAX_PRD_BYTES = 5 * 1024 * 1024     # 5 MB — same envelope as employee uploads

router = APIRouter(
    prefix="/admin",
    tags=["Admin · PRD"],
    dependencies=[Depends(require_admin)],
)


# ── Schemas ──────────────────────────────────────────────────────────────────

class ExtractedOut(BaseModel):
    skills:           list[str]
    priority_skills:  list[str]
    task_description: str
    method:           str
    model:            Optional[str]
    extracted_at:     datetime


class PRDOut(BaseModel):
    id:                 int
    project_id:         Optional[int]
    filename:           str
    content_type:       Optional[str]
    uploaded_by_user_id: Optional[int]
    created_at:         datetime
    latest_extraction:  Optional[ExtractedOut] = None


class PRDUploadResponse(BaseModel):
    prd:        PRDOut
    extraction: ExtractedOut


class AnalyzeCandidatesRequest(BaseModel):
    prd_id:          int
    batch_id:        Optional[str] = None
    min_experience:  float = Field(0.0, ge=0.0)


class SelectCandidatesRequest(BaseModel):
    staging_ids: list[int] = Field(..., min_length=1, max_length=200)
    prd_id:      Optional[int] = None   # for audit log only


# ── Helpers ──────────────────────────────────────────────────────────────────

async def _persist_extraction(db, prd_id: int, ext: dict) -> dict:
    result = await db.execute(
        prd_extracted_skills_table.insert()
        .values(
            prd_id=prd_id,
            skills=json.dumps(ext["skills"]),
            priority_skills=json.dumps(ext["priority_skills"]),
            task_description=ext["task_description"],
            method=ext["method"],
            model=ext["model"],
        )
        .returning(prd_extracted_skills_table)
    )
    await db.commit()
    return dict(result.mappings().first())


def _extraction_to_out(row: dict) -> ExtractedOut:
    return ExtractedOut(
        skills=json.loads(row["skills"] or "[]"),
        priority_skills=json.loads(row["priority_skills"] or "[]"),
        task_description=row["task_description"] or "",
        method=row["method"],
        model=row["model"],
        extracted_at=row["extracted_at"],
    )


async def _latest_extraction(db, prd_id: int) -> Optional[dict]:
    row = (
        await db.execute(
            sa.select(prd_extracted_skills_table)
            .where(prd_extracted_skills_table.c.prd_id == prd_id)
            .order_by(prd_extracted_skills_table.c.extracted_at.desc())
            .limit(1)
        )
    ).mappings().first()
    return dict(row) if row else None


def _prd_row_to_out(row: dict, latest: Optional[dict]) -> PRDOut:
    return PRDOut(
        id=row["id"],
        project_id=row["project_id"],
        filename=row["filename"],
        content_type=row["content_type"],
        uploaded_by_user_id=row["uploaded_by_user_id"],
        created_at=row["created_at"],
        latest_extraction=_extraction_to_out(latest) if latest else None,
    )


# ── 1. Upload + first-pass extraction ───────────────────────────────────────

@router.post("/upload-prd", response_model=PRDUploadResponse)
async def upload_prd(
    request:    Request,
    file:       UploadFile = File(...),
    project_id: Optional[int] = Query(None),
    admin:      dict = Depends(require_admin),
):
    """
    Upload a PRD file (.pdf/.txt/.md/.docx), extract raw text, and run the
    first skill extraction. Returns the stored row + the extraction.

    The extraction is persisted in `prd_extracted_skills` so the admin can
    audit what the parser produced — and re-parse later if the dictionary
    or model improves.
    """
    from api.main import SessionLocal

    contents = await file.read()
    if len(contents) > MAX_PRD_BYTES:
        raise HTTPException(
            413, f"File exceeds {MAX_PRD_BYTES // (1024*1024)} MB limit"
        )
    if not file.filename:
        raise HTTPException(400, "filename missing")

    # Extract text — any failure surfaces as a 400 (bad PRD), not a 500.
    try:
        raw_text = extract_text(file.filename, contents)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except RuntimeError as e:
        raise HTTPException(500, str(e))
    if not raw_text.strip():
        raise HTTPException(400, "PRD contains no extractable text")

    # Persist doc first so the extraction is FK-linked.
    async with SessionLocal() as db:
        prd_ins = await db.execute(
            prd_documents_table.insert()
            .values(
                project_id=project_id,
                filename=file.filename,
                content_type=file.content_type,
                raw_text=raw_text,
                uploaded_by_user_id=admin["id"],
            )
            .returning(prd_documents_table)
        )
        prd_row = dict(prd_ins.mappings().first())
        await db.commit()

        ext_dict = await extract_skills(raw_text)
        ext_row  = await _persist_extraction(db, prd_row["id"], ext_dict)

    log.info(
        "upload-prd: id=%d filename=%s method=%s skills=%d",
        prd_row["id"], file.filename, ext_dict["method"], len(ext_dict["skills"]),
    )
    return PRDUploadResponse(
        prd=_prd_row_to_out(prd_row, ext_row),
        extraction=_extraction_to_out(ext_row),
    )


# ── 2. Re-parse an existing PRD ─────────────────────────────────────────────

@router.post("/parse-prd/{prd_id}", response_model=ExtractedOut)
async def parse_prd(prd_id: int):
    """Re-run extraction on an already-uploaded PRD. Appends a new row."""
    from api.main import SessionLocal

    async with SessionLocal() as db:
        prd = (
            await db.execute(
                sa.select(prd_documents_table)
                .where(prd_documents_table.c.id == prd_id)
            )
        ).mappings().first()
        if not prd:
            raise HTTPException(404, f"PRD {prd_id} not found")
        ext_dict = await extract_skills(prd["raw_text"])
        ext_row  = await _persist_extraction(db, prd_id, ext_dict)

    return _extraction_to_out(ext_row)


# ── 3. List + get ────────────────────────────────────────────────────────────

@router.get("/prds", response_model=list[PRDOut])
async def list_prds(limit: int = Query(50, ge=1, le=200)):
    from api.main import SessionLocal
    async with SessionLocal() as db:
        rows = (
            await db.execute(
                sa.select(prd_documents_table)
                .order_by(prd_documents_table.c.created_at.desc())
                .limit(limit)
            )
        ).mappings().all()
        out: list[PRDOut] = []
        for r in rows:
            latest = await _latest_extraction(db, r["id"])
            out.append(_prd_row_to_out(dict(r), latest))
    return out


@router.get("/prds/{prd_id}", response_model=PRDOut)
async def get_prd(prd_id: int):
    from api.main import SessionLocal
    async with SessionLocal() as db:
        row = (
            await db.execute(
                sa.select(prd_documents_table)
                .where(prd_documents_table.c.id == prd_id)
            )
        ).mappings().first()
        if not row:
            raise HTTPException(404, f"PRD {prd_id} not found")
        latest = await _latest_extraction(db, prd_id)
    return _prd_row_to_out(dict(row), latest)


# ── 4. Analyze candidates against a PRD ──────────────────────────────────────

@router.post("/analyze-candidates", response_model=AnalyzeResponse)
async def analyze_candidates(
    body:  AnalyzeCandidatesRequest,
    admin: dict = Depends(require_admin),
):
    """
    Pull the latest extracted skills for `prd_id` and hand them to the
    existing `analyze_employees` function so scoring + persistence live
    in exactly one place.
    """
    from api.main import SessionLocal
    from api.staging import analyze_employees

    async with SessionLocal() as db:
        prd = (
            await db.execute(
                sa.select(prd_documents_table)
                .where(prd_documents_table.c.id == body.prd_id)
            )
        ).mappings().first()
        if not prd:
            raise HTTPException(404, f"PRD {body.prd_id} not found")
        latest = await _latest_extraction(db, body.prd_id)
        if not latest:
            raise HTTPException(400, "PRD has not been parsed yet")

    skills   = json.loads(latest["skills"] or "[]")
    priority = json.loads(latest["priority_skills"] or "[]")
    if not skills:
        raise HTTPException(400, "PRD extraction produced no skills")

    return await analyze_employees(
        AnalyzeRequest(
            required=skills,
            priority=priority,
            min_experience=body.min_experience,
            batch_id=body.batch_id,
        ),
        admin=admin,
    )


# ── 5. Ranked candidates shortcut — reads employee_scores by PRD ────────────

@router.get("/ranked-candidates")
async def ranked_candidates(
    prd_id:    int   = Query(...),
    min_score: float = Query(0.0, ge=0.0, le=1.0),
    limit:     int   = Query(50, ge=1, le=200),
):
    """
    Convenience wrapper: reads the latest persisted analysis for `prd_id`'s
    requirement hash. Handy for the admin UI so it doesn't have to pass
    the hash around.
    """
    from api.main import SessionLocal
    from api.staging import _requirement_hash, employee_scores

    async with SessionLocal() as db:
        latest = await _latest_extraction(db, prd_id)
    if not latest:
        raise HTTPException(400, "PRD has not been parsed yet")

    skills   = json.loads(latest["skills"] or "[]")
    priority = json.loads(latest["priority_skills"] or "[]")
    req_hash = _requirement_hash(skills, priority, 0.0)
    return await employee_scores(
        requirement_hash=req_hash,
        batch_id=None,
        min_score=min_score,
        limit=limit,
    )


# ── 6a. Combined pipeline: upload PRD → create project → seed tasks ─────────

class CreatedTaskOut(BaseModel):
    id:              int
    title:           str
    priority:        str
    estimated_hours: float
    required_skills: list[str]


class UploadAndCreateResponse(BaseModel):
    project_id:   int
    prd_id:       int
    project_name: str
    skills:       list[str]
    priority:     list[str]
    tasks:        list[CreatedTaskOut]
    method:       str
    model:        Optional[str]


@router.post("/upload-prd-and-create-project", response_model=UploadAndCreateResponse)
async def upload_prd_and_create_project(
    request:       Request,
    file:          UploadFile = File(...),
    project_name:  Optional[str] = Query(None, description="Override auto-extracted name"),
    admin:         dict = Depends(require_admin),
):
    """
    Single transaction — the canonical path. Wraps what used to be three
    separate operations (upload-prd, POST /projects, /projects/{id}/parse)
    into one atomic pipeline. The legacy /projects/{id}/parse endpoint is
    retained only as an internal re-parse helper.

    Steps:
      1. Extract text from the uploaded file (PDF/TXT/MD/DOCX)
      2. One LLM call → {project_title, description, skills, priority, tasks}
         (or keyword fallback with a single placeholder task)
      3. INSERT project → prd_documents (linked) → prd_extracted_skills →
         tasks (one row per extracted task, linked to the project)
      4. All inside one DB session so a failure rolls back the whole thing

    Returns the project_id, the task_ids (so the UI can deep-link), and the
    skill lists so the staging/ranking UI can immediately pre-fill its
    inputs from the same extraction.
    """
    from api.main import SessionLocal, projects_table, tasks_table

    contents = await file.read()
    if len(contents) > MAX_PRD_BYTES:
        raise HTTPException(413, f"File exceeds {MAX_PRD_BYTES // (1024*1024)} MB limit")
    if not file.filename:
        raise HTTPException(400, "filename missing")

    try:
        raw_text = extract_text(file.filename, contents)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except RuntimeError as e:
        raise HTTPException(500, str(e))
    if not raw_text.strip():
        raise HTTPException(400, "PRD contains no extractable text")

    package = await extract_project_package(raw_text)
    if not package["skills"] and not package["tasks"]:
        raise HTTPException(
            400, "Parser could not extract any skills or tasks from this PRD"
        )

    resolved_name = (project_name or package["project_title"]).strip()[:200] or "Project from PRD"

    import json as _json

    async with SessionLocal() as db:
        # 1) project
        proj_ins = await db.execute(
            projects_table.insert()
            .values(
                name=resolved_name,
                description=package["project_description"] or None,
                prd_text=raw_text,
                status="active",
            )
            .returning(projects_table)
        )
        proj = proj_ins.mappings().first()
        project_id = proj["id"]

        # 2) prd_documents (FK → project)
        prd_ins = await db.execute(
            prd_documents_table.insert()
            .values(
                project_id=project_id,
                filename=file.filename,
                content_type=file.content_type,
                raw_text=raw_text,
                uploaded_by_user_id=admin["id"],
            )
            .returning(prd_documents_table)
        )
        prd = prd_ins.mappings().first()

        # 3) prd_extracted_skills (audit trail of what the parser produced)
        await db.execute(
            prd_extracted_skills_table.insert().values(
                prd_id=prd["id"],
                skills=_json.dumps(package["skills"]),
                priority_skills=_json.dumps(package["priority_skills"]),
                task_description=package["task_description"],
                method=package["method"],
                model=package["model"],
            )
        )

        # 4) tasks — one per extracted task
        created_tasks: list[dict] = []
        for t in package["tasks"]:
            task_ins = await db.execute(
                tasks_table.insert()
                .values(
                    project_id=project_id,
                    title=t["title"],
                    description=t["description"],
                    priority=t["priority"],
                    status="todo",
                    estimated_hours=t["estimated_hours"],
                    required_skills=_json.dumps(t["required_skills"]),
                    progress_pct=0,
                )
                .returning(tasks_table)
            )
            created_tasks.append(dict(task_ins.mappings().first()))

        # Stamp the total_tasks counter so admin widgets read correctly.
        await db.execute(
            projects_table.update()
            .where(projects_table.c.id == project_id)
            .values(total_tasks=len(created_tasks))
        )
        await db.commit()

    log.info(
        "upload-prd-and-create-project: project_id=%d prd_id=%d tasks=%d method=%s",
        project_id, prd["id"], len(created_tasks), package["method"],
    )
    return UploadAndCreateResponse(
        project_id=project_id,
        prd_id=prd["id"],
        project_name=resolved_name,
        skills=package["skills"],
        priority=package["priority_skills"],
        tasks=[
            CreatedTaskOut(
                id=t["id"],
                title=t["title"],
                priority=t["priority"],
                estimated_hours=t["estimated_hours"] or 0,
                required_skills=_json.loads(t.get("required_skills") or "[]"),
            )
            for t in created_tasks
        ],
        method=package["method"],
        model=package["model"],
    )


# ── 6b. Analyze-and-rank alias (spec §11) ───────────────────────────────────

@router.post("/analyze-and-rank", response_model=AnalyzeResponse)
async def analyze_and_rank(
    body:  AnalyzeCandidatesRequest,
    admin: dict = Depends(require_admin),
):
    """Spec §11 alias — delegates to /admin/analyze-candidates."""
    return await analyze_candidates(body, admin=admin)


# ── 7. Select-candidates alias (spec §14) ────────────────────────────────────

@router.post("/select-candidates")
async def select_candidates(body: SelectCandidatesRequest):
    """
    Spec §14 alias. Delegates to the existing, battle-tested
    /admin/create-selected-employees which returns one-time credentials.
    """
    from api.staging import CreateSelectedRequest, create_selected_employees
    result = await create_selected_employees(
        CreateSelectedRequest(staging_ids=body.staging_ids)
    )
    if body.prd_id is not None:
        log.info("select-candidates: prd=%s created=%d", body.prd_id, len(result.created))
    return result
