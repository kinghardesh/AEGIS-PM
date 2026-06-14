"""
aegis-pm / api / prd_parser.py

Extract text from a PRD file and then extract skills from that text.

Text extraction (real, deterministic)
─────────────────────────────────────
  .pdf   → pdfplumber page-by-page, joined
  .txt   → utf-8 decode (bom-tolerant)
  .docx  → python-docx paragraphs (optional dep; clear error if missing)

Skill extraction
────────────────
  Primary   — chat completion (OpenAI-compatible; works with Groq if
              GROQ_API_KEY is set). Returns JSON with {skills,
              priority_skills, task_description}. Deterministic
              temperature=0, response_format=json_object.

  Fallback  — keyword scan. No mock data: skills are found only if the
              text contains the token. Uses a curated dictionary of
              common tech terms (frontend/backend/data/devops/langs) plus
              regex for "Required:" / "Must have:" / "Priority:" headers
              which are then split on commas.

The two methods produce identical JSON shape, so callers don't branch.
`extract_skills()` tries LLM first and falls through on any failure
without raising — the API stays up even if no key is configured.
"""
from __future__ import annotations

import io
import json
import logging
import os
import re
from typing import TypedDict

log = logging.getLogger("aegis.prd")


class ExtractedSkills(TypedDict):
    skills:           list[str]
    priority_skills:  list[str]
    task_description: str
    method:           str   # 'llm' | 'keyword'
    model:            str | None


# ── Text extraction ──────────────────────────────────────────────────────────

def extract_text(filename: str, content: bytes) -> str:
    """Route to the right text extractor; raise ValueError on unsupported."""
    lower = filename.lower()
    if lower.endswith((".txt", ".md")):
        return content.decode("utf-8-sig", errors="replace")
    if lower.endswith(".pdf"):
        return _pdf_text(content)
    if lower.endswith(".docx"):
        return _docx_text(content)
    raise ValueError(
        f"Unsupported PRD format: {filename!r}. Use .pdf, .txt, .md, or .docx."
    )


def _pdf_text(content: bytes) -> str:
    try:
        import pdfplumber  # type: ignore
    except ImportError as e:  # pragma: no cover
        raise RuntimeError("pdfplumber is not installed") from e
    parts: list[str] = []
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        for page in pdf.pages:
            t = page.extract_text() or ""
            if t:
                parts.append(t)
    return "\n".join(parts)


def _docx_text(content: bytes) -> str:
    try:
        from docx import Document  # type: ignore   — python-docx
    except ImportError as e:
        raise RuntimeError(
            "python-docx is not installed; cannot parse .docx"
        ) from e
    doc = Document(io.BytesIO(content))
    return "\n".join(p.text for p in doc.paragraphs if p.text.strip())


# ── Skill dictionary (conservative; lowercase canonical form) ──────────────

_SKILL_DICT: set[str] = {
    # Languages
    "python", "javascript", "typescript", "java", "kotlin", "swift", "c",
    "c++", "c#", "go", "golang", "rust", "ruby", "php", "scala", "r",
    "dart", "elixir", "haskell", "perl", "shell", "bash",
    # Frontend
    "react", "react native", "next.js", "vue", "vue.js", "angular",
    "svelte", "solid.js", "redux", "mobx", "zustand", "tailwindcss",
    "tailwind", "bootstrap", "sass", "scss", "webpack", "vite", "esbuild",
    "remix", "astro",
    # Backend
    "node.js", "express", "nestjs", "fastify", "koa", "django", "flask",
    "fastapi", "spring", "spring boot", "rails", "laravel", "asp.net",
    ".net", "gin", "fiber", "echo",
    # Data & DB
    "sql", "postgres", "postgresql", "mysql", "mariadb", "sqlite",
    "mongodb", "dynamodb", "cassandra", "redis", "memcached", "elasticsearch",
    "snowflake", "bigquery", "redshift", "clickhouse",
    # Message / streaming
    "kafka", "rabbitmq", "nats", "pulsar", "kinesis", "sqs", "sns",
    # Cloud / devops
    "aws", "gcp", "azure", "kubernetes", "docker", "terraform", "ansible",
    "helm", "argo", "prometheus", "grafana", "datadog", "sentry",
    "cloudflare", "vercel", "netlify", "heroku", "s3", "lambda", "ec2",
    "rds", "cloudrun", "gke", "eks", "aks",
    # Data science / ML
    "pandas", "numpy", "scikit-learn", "pytorch", "tensorflow", "keras",
    "jax", "spark", "hadoop", "airflow", "dbt", "kubeflow", "mlflow",
    "huggingface", "langchain", "openai", "llm", "rag",
    # Testing / QA
    "jest", "vitest", "pytest", "rspec", "cypress", "playwright", "selenium",
    "junit", "mockito", "karma", "storybook",
    # Other
    "graphql", "rest", "grpc", "websocket", "websockets", "oauth", "jwt",
    "microservices", "ci/cd", "git", "github actions", "jenkins", "gitlab",
    "linux", "unix", "macos", "windows",
}


# Longer multi-word skills first so they win over substrings.
_MULTI_WORD = sorted(
    {s for s in _SKILL_DICT if " " in s or "." in s or "#" in s or "+" in s or "/" in s},
    key=len, reverse=True,
)


_REQUIRED_HDR = re.compile(
    r"(required(?:\s+skills)?|must[\s\-]have|skills?\s*(?:needed|required)?|"
    r"tech(?:\s*stack)?|stack)\s*[:\-]",
    re.IGNORECASE,
)
_PRIORITY_HDR = re.compile(
    r"(priority|critical|mandatory|must[\s\-]have|key)\s*(?:skills?)?\s*[:\-]",
    re.IGNORECASE,
)
_LIST_SPLIT = re.compile(r"[,;|/\n]+")


def _normalise_token(tok: str) -> str | None:
    """Strip, lowercase, remove wrapping punct; reject junk shorter than 2 chars."""
    s = re.sub(r"[^a-zA-Z0-9+#.\-\s/]", "", tok).strip().lower()
    s = re.sub(r"\s+", " ", s)
    if len(s) < 2 or s.isdigit():
        return None
    return s


def _scan_dictionary(text: str) -> set[str]:
    """Return the set of known skills appearing anywhere in the text."""
    found: set[str] = set()
    lower = text.lower()
    # Multi-word first (so "node.js" beats a stray "node") — straight substring check
    for s in _MULTI_WORD:
        if s in lower:
            found.add(s)
    # Then word-boundary check for single-word skills
    for tok in re.findall(r"[A-Za-z][A-Za-z0-9+#]{1,29}", lower):
        if tok in _SKILL_DICT:
            found.add(tok)
    return found


def _scan_header_sections(pattern: re.Pattern, text: str, window: int = 500) -> set[str]:
    """Find `pattern:` labels and grab the comma-split items in the window after."""
    out: set[str] = set()
    for m in pattern.finditer(text):
        tail = text[m.end(): m.end() + window]
        # Stop at a newline-separated header that looks like another section.
        stop = re.search(r"\n\s*[A-Z][A-Za-z0-9 ]{2,40}\s*[:\n]", tail)
        if stop:
            tail = tail[: stop.start()]
        for tok in _LIST_SPLIT.split(tail):
            norm = _normalise_token(tok)
            if norm and (norm in _SKILL_DICT or " " in norm):
                out.add(norm)
    return out


# ── Fallback: keyword extraction ─────────────────────────────────────────────

def extract_skills_keyword(text: str) -> ExtractedSkills:
    dict_hits     = _scan_dictionary(text)
    required_hits = _scan_header_sections(_REQUIRED_HDR, text)
    priority_hits = _scan_header_sections(_PRIORITY_HDR, text)

    skills   = sorted(dict_hits | required_hits)
    priority = sorted(priority_hits & (dict_hits | required_hits))

    # Short task description = first ~240 chars of the PRD, collapsed.
    task_desc = re.sub(r"\s+", " ", text).strip()[:240]
    return ExtractedSkills(
        skills=skills,
        priority_skills=priority,
        task_description=task_desc,
        method="keyword",
        model=None,
    )


# ── LLM extraction (OpenAI-compatible, works with Groq) ─────────────────────

def _chat_client():
    """
    Return (AsyncOpenAI, model_name) or (None, None) if no key is configured.

    Prefers GROQ_API_KEY (the user already has a key with quota), falls
    back to OPENAI_API_KEY. Groq is OpenAI-API-compatible at this endpoint.
    """
    try:
        from openai import AsyncOpenAI
    except ImportError:
        return None, None

    groq_key = os.getenv("GROQ_API_KEY", "").strip()
    if groq_key:
        model = os.getenv("OPENAI_MODEL", "llama-3.3-70b-versatile")
        return AsyncOpenAI(api_key=groq_key, base_url="https://api.groq.com/openai/v1"), model

    openai_key = os.getenv("OPENAI_API_KEY", "").strip()
    if openai_key:
        model = os.getenv("PRD_PARSE_MODEL", "gpt-4o-mini")
        return AsyncOpenAI(api_key=openai_key), model

    return None, None


_SYSTEM_PROMPT = (
    "You are a senior technical recruiter and project scoper. "
    "From the PRD text, extract ONLY technologies, frameworks, languages, "
    "databases, cloud services, and other concrete technical skills that "
    "engineers need. Return strict JSON — no prose."
)

_USER_TEMPLATE = (
    "Here is the PRD:\n\n"
    "<<<\n{prd}\n>>>\n\n"
    "Return a JSON object exactly like:\n"
    "{{\n"
    "  \"skills\": [\"lowercase canonical skills, e.g. react, node.js, postgres\"],\n"
    "  \"priority_skills\": [\"subset of skills the PRD marks as must-have\"],\n"
    "  \"task_description\": \"one or two sentences describing what needs to be built\"\n"
    "}}\n"
    "Use the canonical form (e.g. 'node.js' not 'Node', 'postgres' not 'PostgreSQL DB'). "
    "If the PRD doesn't mark any priority skills, return []."
)


async def extract_skills_llm(text: str) -> ExtractedSkills | None:
    client, model = _chat_client()
    if not client:
        return None
    try:
        resp = await client.chat.completions.create(
            model=model,
            temperature=0,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user",   "content": _USER_TEMPLATE.format(prd=text[:12000])},
            ],
            response_format={"type": "json_object"},
        )
        raw = resp.choices[0].message.content or "{}"
        data = json.loads(raw)
    except Exception as e:
        log.warning("prd llm extraction failed: %s: %s", type(e).__name__, e)
        return None

    # Normalise + dedupe — model output is trusted but not blindly.
    def _clean(lst) -> list[str]:
        if not isinstance(lst, list):
            return []
        out = set()
        for item in lst:
            if not isinstance(item, str):
                continue
            norm = _normalise_token(item)
            if norm:
                out.add(norm)
        return sorted(out)

    skills = _clean(data.get("skills", []))
    priority = _clean(data.get("priority_skills", []))
    # Priority must be a subset of skills; drop orphans.
    priority = [p for p in priority if p in set(skills)]
    desc = str(data.get("task_description") or "")[:800]
    return ExtractedSkills(
        skills=skills,
        priority_skills=priority,
        task_description=desc,
        method="llm",
        model=model,
    )


# ── Public API: try LLM first, fall back to keyword ─────────────────────────

async def extract_skills(text: str) -> ExtractedSkills:
    if text and text.strip():
        llm = await extract_skills_llm(text)
        if llm is not None and llm["skills"]:
            return llm
    return extract_skills_keyword(text or "")


# ═══════════════════════════════════════════════════════════════════════════════
#  Project + Task extraction  (one LLM call → everything needed to create a
#  project, persist the PRD, and seed the tasks table).
# ═══════════════════════════════════════════════════════════════════════════════

class ExtractedTask(TypedDict):
    title:            str
    description:      str
    priority:         str          # 'high' | 'medium' | 'low'
    estimated_hours:  float
    required_skills:  list[str]


class ExtractedProject(TypedDict):
    project_title:       str
    project_description: str
    skills:              list[str]
    priority_skills:     list[str]
    task_description:    str
    tasks:               list[ExtractedTask]
    method:              str
    model:               str | None


_PKG_SYSTEM = (
    "You are a senior technical PM + recruiter. Read the PRD and extract a "
    "structured plan: a short project title, a 1-sentence description, the "
    "concrete technical skills engineers will need, any priority/must-have "
    "subset, and a concrete task breakdown. Return strict JSON — no prose. "
    "Task titles must be short (≤ 60 chars). Task priorities must be one of "
    "'high', 'medium', 'low'. Estimated hours must be a positive number."
)

_PKG_TEMPLATE = (
    "PRD text:\n\n<<<\n{prd}\n>>>\n\n"
    "Return a JSON object exactly like:\n"
    "{{\n"
    "  \"project_title\": \"short clear project name\",\n"
    "  \"project_description\": \"one sentence summary\",\n"
    "  \"skills\": [\"lowercase canonical skills, e.g. react, node.js, postgres\"],\n"
    "  \"priority_skills\": [\"subset the PRD marks as must-have\"],\n"
    "  \"task_description\": \"2-sentence overview of the work\",\n"
    "  \"tasks\": [\n"
    "    {{\n"
    "      \"title\": \"short imperative title\",\n"
    "      \"description\": \"1-3 sentence scope\",\n"
    "      \"priority\": \"high|medium|low\",\n"
    "      \"estimated_hours\": 8,\n"
    "      \"required_skills\": [\"subset of the skills list\"]\n"
    "    }}\n"
    "  ]\n"
    "}}\n"
    "If the PRD does not enumerate tasks, propose 3–6 sensible ones based on "
    "the work described. Use canonical skill names (e.g. 'node.js' not 'Node')."
)


_VALID_PRIORITY = {"high", "medium", "low"}


def _sanitise_task(raw: object, known_skills: set[str]) -> ExtractedTask | None:
    if not isinstance(raw, dict):
        return None
    title = str(raw.get("title") or "").strip()[:120]
    if not title:
        return None
    description = str(raw.get("description") or "").strip()[:1000]
    priority = str(raw.get("priority") or "medium").strip().lower()
    if priority not in _VALID_PRIORITY:
        priority = "medium"
    try:
        hours = float(raw.get("estimated_hours") or 4)
    except (TypeError, ValueError):
        hours = 4.0
    hours = max(0.5, min(200.0, hours))

    rs_raw = raw.get("required_skills") or []
    if not isinstance(rs_raw, list):
        rs_raw = []
    rs_clean: list[str] = []
    for s in rs_raw:
        norm = _normalise_token(str(s))
        if norm and (not known_skills or norm in known_skills):
            rs_clean.append(norm)

    return {
        "title":           title,
        "description":     description,
        "priority":        priority,
        "estimated_hours": hours,
        "required_skills": sorted(set(rs_clean)),
    }


async def extract_project_package_llm(text: str) -> ExtractedProject | None:
    client, model = _chat_client()
    if not client:
        return None
    try:
        resp = await client.chat.completions.create(
            model=model,
            temperature=0,
            messages=[
                {"role": "system", "content": _PKG_SYSTEM},
                {"role": "user",   "content": _PKG_TEMPLATE.format(prd=text[:12000])},
            ],
            response_format={"type": "json_object"},
        )
        raw = resp.choices[0].message.content or "{}"
        data = json.loads(raw)
    except Exception as e:
        log.warning("prd package llm extraction failed: %s: %s", type(e).__name__, e)
        return None

    # Normalise skills + priority.
    def _clean_skills(lst) -> list[str]:
        if not isinstance(lst, list):
            return []
        out = set()
        for item in lst:
            if isinstance(item, str):
                norm = _normalise_token(item)
                if norm:
                    out.add(norm)
        return sorted(out)

    skills   = _clean_skills(data.get("skills", []))
    priority = _clean_skills(data.get("priority_skills", []))
    priority = [p for p in priority if p in set(skills)]
    known    = set(skills)

    raw_tasks = data.get("tasks") or []
    tasks: list[ExtractedTask] = []
    if isinstance(raw_tasks, list):
        for raw in raw_tasks[:30]:  # guardrail
            t = _sanitise_task(raw, known)
            if t:
                tasks.append(t)

    title_fallback = (
        str(data.get("project_title") or "").strip()[:200] or "Untitled project"
    )
    desc = str(data.get("project_description") or "").strip()[:500]
    task_desc = str(data.get("task_description") or "").strip()[:800]

    return ExtractedProject(
        project_title=title_fallback,
        project_description=desc,
        skills=skills,
        priority_skills=priority,
        task_description=task_desc,
        tasks=tasks,
        method="llm",
        model=model,
    )


def _fallback_project_package(text: str) -> ExtractedProject:
    """
    Keyword-only fallback: no task generation (we refuse to hallucinate task
    breakdowns). Returns one catch-all task carrying the extracted skills so
    the admin has at least a concrete starting point.
    """
    base = extract_skills_keyword(text or "")
    first_line = ""
    for line in (text or "").splitlines():
        s = line.strip()
        if s and len(s) < 200:
            first_line = s
            break
    title = first_line[:100] or "Project from PRD"
    task: ExtractedTask = {
        "title":           "Implement project scope",
        "description":     base["task_description"] or "Seeded from keyword-only PRD parse.",
        "priority":        "medium",
        "estimated_hours": 8.0,
        "required_skills": list(base["skills"]),
    }
    return ExtractedProject(
        project_title=title,
        project_description=base["task_description"] or "",
        skills=base["skills"],
        priority_skills=base["priority_skills"],
        task_description=base["task_description"],
        tasks=[task] if base["skills"] else [],
        method="keyword",
        model=None,
    )


async def extract_project_package(text: str) -> ExtractedProject:
    """LLM-first, keyword-fallback. Never raises; always returns a payload."""
    if text and text.strip():
        llm = await extract_project_package_llm(text)
        if llm is not None and llm["skills"]:
            return llm
    return _fallback_project_package(text or "")
