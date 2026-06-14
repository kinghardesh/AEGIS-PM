"""
aegis-pm / api / parsers.py

Parse uploaded employee data files (xlsx / csv / pdf) into a uniform
list of StagingRow dicts. Each parser is pure: bytes in, rows out, no DB.

Header detection is lenient — we accept any case/whitespace variant of
  "name" | "email" | "skills" | "experience"
and map it to the canonical key. Unknown columns land in `extras` so
they can be stored on raw_metadata for admin inspection.

Row validation:
  - `name` is required (empty rows are silently dropped)
  - `email` is optional; if present it's lowercased
  - `skills` is normalised to a JSON array of trimmed lowercase strings
  - `experience` is coerced to float; malformed values → None
"""
from __future__ import annotations

import csv
import io
import json
import logging
import re
from typing import TypedDict

log = logging.getLogger("aegis.parsers")


class StagingRow(TypedDict, total=False):
    name:       str
    email:      str | None
    skills:     str          # JSON-encoded list[str]
    experience: float | None
    department: str | None
    is_manager: bool
    extras:     dict


# ── Header mapping ───────────────────────────────────────────────────────────

_CANONICAL = {
    "name":       "name",
    "full name":  "name",
    "employee":   "name",
    "email":      "email",
    "e-mail":     "email",
    "mail":       "email",
    "skills":     "skills",
    "skill":      "skills",
    "skill set":  "skills",
    "tech stack": "skills",
    "experience": "experience",
    "exp":        "experience",
    "years":      "experience",
    "yrs":        "experience",
    "department": "department",
    "dept":       "department",
    "team":       "department",
    "division":   "department",
    "manager":    "is_manager",
    "is manager": "is_manager",
    "is_manager": "is_manager",
    "role":       "role",
    "title":      "role",
    "designation":"role",
    "position":   "role",
    "seniority":  "role",
}


def _canonicalise(header: str) -> str | None:
    key = re.sub(r"\s+", " ", (header or "").strip().lower())
    return _CANONICAL.get(key)


# ── Skill / experience normalisation ─────────────────────────────────────────

def _normalise_skills(raw: object) -> str:
    """Return a JSON-encoded sorted unique list of lowercase skills."""
    if raw is None:
        return "[]"
    if isinstance(raw, list):
        items = raw
    else:
        # split on commas, semicolons, pipes, newlines
        items = re.split(r"[,;|\n/]+", str(raw))
    cleaned = sorted({s.strip().lower() for s in items if str(s).strip()})
    return json.dumps(cleaned)


_YEAR_RE = re.compile(r"(\d+(?:\.\d+)?)")


def _normalise_experience(raw: object) -> float | None:
    if raw is None or raw == "":
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        # e.g. "5 years" -> 5.0
        m = _YEAR_RE.search(str(raw))
        return float(m.group(1)) if m else None


# ── Department / manager inference ───────────────────────────────────────────

# Skill keyword → department label. First matching bucket wins. Used only as a
# fallback when the upload has no explicit "department" column.
_DEPARTMENT_BY_SKILL: list[tuple[str, tuple[str, ...]]] = [
    ("Legal",        ("legal", "contract", "compliance", "gdpr", "litigation",
                      "regulatory", "law", "intellectual property", "patent")),
    ("HR",           ("hr", "human resources", "recruiting", "recruitment",
                      "payroll", "onboarding", "talent")),
    ("Finance",      ("finance", "accounting", "bookkeeping", "tax", "budgeting",
                      "audit", "invoicing")),
    ("Marketing",    ("marketing", "seo", "sem", "content", "copywriting",
                      "social media", "brand", "campaign")),
    ("Design",       ("design", "figma", "ui", "ux", "ui/ux", "sketch",
                      "photoshop", "illustrator", "wireframe")),
    ("QA",           ("qa", "testing", "test automation", "selenium", "cypress",
                      "junit", "pytest", "quality assurance")),
    ("Data",         ("data science", "machine learning", "ml", "ai", "pandas",
                      "analytics", "data engineering", "spark")),
    ("Engineering",  ("react", "node", "node.js", "python", "java", "go", "rust",
                      "backend", "frontend", "api", "sql", "mongodb", "docker",
                      "kubernetes", "devops", "typescript", "javascript")),
]

# Words in a title/role that indicate a managerial position.
_MANAGER_TITLE_WORDS = (
    "manager", "lead", "director", "head", "chief", "vp",
    "principal", "supervisor", "cto", "ceo", "coo", "cfo",
)

# Years of experience at/above which we assume seniority → manager (fallback).
_MANAGER_EXPERIENCE_YEARS = 8.0

_TRUTHY = {"true", "yes", "y", "1", "manager", "lead"}


def _normalise_department(raw: object, skills_str: object) -> str | None:
    """Explicit department wins; otherwise infer from skill keywords."""
    if raw not in (None, ""):
        return str(raw).strip() or None
    try:
        skills_list = json.loads(skills_str) if isinstance(skills_str, str) else (skills_str or [])
    except Exception:
        skills_list = []
    skill_set = {str(s).strip().lower() for s in skills_list}
    for label, keywords in _DEPARTMENT_BY_SKILL:
        if skill_set & set(keywords):
            return label
    return None


def _infer_manager(raw: object, role: object, experience: object) -> bool:
    """Explicit manager flag wins; else infer from title words or seniority."""
    if raw not in (None, ""):
        return str(raw).strip().lower() in _TRUTHY
    role_text = str(role or "").strip().lower()
    if any(w in role_text for w in _MANAGER_TITLE_WORDS):
        return True
    years = _normalise_experience(experience)
    return years is not None and years >= _MANAGER_EXPERIENCE_YEARS


def _row_from_mapping(data: dict) -> StagingRow | None:
    """Build a StagingRow from a {canonical_key: value} mapping."""
    name = str(data.get("name") or "").strip()
    if not name:
        return None
    email = str(data.get("email") or "").strip().lower() or None

    skills = _normalise_skills(data.get("skills"))
    consumed = {"name", "email", "skills", "experience", "department", "is_manager", "role"}
    extras = {k: v for k, v in data.items() if k not in consumed}
    return {
        "name":       name,
        "email":      email,
        "skills":     skills,
        "experience": _normalise_experience(data.get("experience")),
        "department": _normalise_department(data.get("department"), skills),
        "is_manager": _infer_manager(
            data.get("is_manager"), data.get("role"), data.get("experience")
        ),
        "extras":     extras,
    }


# ── CSV ──────────────────────────────────────────────────────────────────────

def parse_csv(content: bytes) -> list[StagingRow]:
    text = content.decode("utf-8-sig", errors="replace")
    reader = csv.reader(io.StringIO(text))
    rows: list[StagingRow] = []
    header_map: dict[int, str] = {}
    for idx, raw in enumerate(reader):
        if idx == 0:
            for col_idx, h in enumerate(raw):
                canonical = _canonicalise(h)
                if canonical:
                    header_map[col_idx] = canonical
            if "name" not in header_map.values():
                raise ValueError("CSV is missing a 'Name' column.")
            continue
        record: dict = {}
        for col_idx, val in enumerate(raw):
            key = header_map.get(col_idx) or f"extra_{col_idx}"
            record[key] = val
        row = _row_from_mapping(record)
        if row:
            rows.append(row)
    return rows


# ── XLSX ─────────────────────────────────────────────────────────────────────

def parse_xlsx(content: bytes) -> list[StagingRow]:
    try:
        from openpyxl import load_workbook  # lazy import; heavy
    except ImportError as e:  # pragma: no cover
        raise RuntimeError("openpyxl is not installed; cannot parse .xlsx") from e

    wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    ws = wb.active
    if ws is None:
        return []

    rows: list[StagingRow] = []
    header_map: dict[int, str] = {}
    for idx, raw in enumerate(ws.iter_rows(values_only=True)):
        if idx == 0:
            for col_idx, h in enumerate(raw):
                canonical = _canonicalise(str(h) if h is not None else "")
                if canonical:
                    header_map[col_idx] = canonical
            if "name" not in header_map.values():
                raise ValueError("Spreadsheet is missing a 'Name' column.")
            continue
        record: dict = {}
        for col_idx, val in enumerate(raw):
            key = header_map.get(col_idx) or f"extra_{col_idx}"
            record[key] = val
        row = _row_from_mapping(record)
        if row:
            rows.append(row)
    return rows


# ── Single free-form resume (one CV = one candidate) ─────────────────────────

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")

# Section headers that mark the END of a skills block (or that a line is not a name).
_SECTION_HEADER_RE = re.compile(
    r"^\s*(work\s+experience|professional\s+experience|experience|employment|"
    r"education|projects?|certifications?|summary|objective|profile|about|"
    r"contact|achievements?|interests?|languages?|references?|awards?)\b",
    re.I,
)
_SKILLS_HEADER_RE = re.compile(
    r"^\s*(technical\s+skills|core\s+skills|key\s+skills|skills|technologies|"
    r"tech\s+stack|core\s+competencies|competencies|expertise)\s*[:\-]?\s*(.*)$",
    re.I,
)
# Lines that are clearly not a person's name.
_NOT_A_NAME = re.compile(r"^(resume|cv|curriculum\s+vitae)\s*$", re.I)

# Known skills for keyword fallback. Built from the department buckets plus a
# broad set of common tech/role skills so we can recognise them in prose.
_KNOWN_SKILLS: frozenset[str] = frozenset(
    {kw for _, kws in _DEPARTMENT_BY_SKILL for kw in kws}
    | {
        "python", "java", "javascript", "typescript", "react", "angular", "vue",
        "node", "node.js", "go", "golang", "rust", "c++", "c#", ".net", "php",
        "ruby", "rails", "django", "flask", "fastapi", "spring", "express",
        "sql", "mysql", "postgresql", "postgres", "mongodb", "redis", "kafka",
        "docker", "kubernetes", "aws", "gcp", "azure", "terraform", "ansible",
        "jenkins", "git", "html", "css", "sass", "tailwind", "graphql", "rest",
        "selenium", "cypress", "pytest", "junit", "jest", "pandas", "numpy",
        "tensorflow", "pytorch", "nlp", "spark", "hadoop", "tableau",
        "power bi", "excel", "linux", "bash", "scala", "kotlin", "swift",
    }
)


def _extract_skills_section(lines: list[str]) -> list[str]:
    """Pull the items under a 'Skills' header until the next section/blank gap."""
    out: list[str] = []
    capturing = False
    for raw in lines:
        s = raw.strip()
        m = _SKILLS_HEADER_RE.match(s)
        if m:
            capturing = True
            if m.group(2).strip():          # inline: "Skills: react, node"
                out.append(m.group(2).strip())
            continue
        if capturing:
            if not s or _SECTION_HEADER_RE.match(s):
                break
            out.append(s)
    tokens: list[str] = []
    for chunk in out:
        for tok in re.split(r"[,;|/•·•\t]+", chunk):
            t = tok.strip().lower()
            if t and 1 < len(t) <= 40:
                tokens.append(t)
    return tokens


def _kw_present(kw: str, low_text: str) -> bool:
    """Whole-token match so 'ui' doesn't match 'building' or 'scala' 'scalable'.

    Boundaries are alphanumeric-aware (not \\b) so skills with punctuation —
    node.js, c++, c#, .net, power bi — still match correctly.
    """
    return re.search(
        r"(?<![A-Za-z0-9])" + re.escape(kw) + r"(?![A-Za-z0-9])", low_text
    ) is not None


def _resume_years(text: str) -> float | None:
    """Largest 'N years' / 'N+ yrs' mentioned — a rough seniority proxy."""
    yrs = [float(m) for m in re.findall(r"(\d{1,2})\+?\s*(?:years?|yrs?)\b", text, re.I)]
    return max(yrs) if yrs else None


def parse_single_resume(text: str) -> StagingRow | None:
    """
    Best-effort extraction of ONE candidate from a free-form resume/CV.

    Heuristics (resumes vary wildly, so this aims for 'useful', not perfect):
      - name:   first name-like line near the top (1–4 words, alphabetic)
      - email:  first email anywhere in the doc
      - skills: a 'Skills' section if present, plus known-skill keywords found
                anywhere in the text
      - experience / department / is_manager: inferred (see _infer_manager etc.)

    Returns None if nothing identifying (no name and no email) can be found.
    """
    lines = text.splitlines()
    nonempty = [l.strip() for l in lines if l.strip()]
    if not nonempty:
        return None

    email_m = _EMAIL_RE.search(text)
    email = email_m.group(0).lower() if email_m else None

    name: str | None = None
    for l in nonempty[:10]:
        if "@" in l or _EMAIL_RE.search(l) or _NOT_A_NAME.match(l):
            continue
        if _SECTION_HEADER_RE.match(l):
            continue
        letters = re.sub(r"[^A-Za-z .'\-]", "", l).strip()
        words = [w for w in letters.split() if w]
        if 1 <= len(words) <= 4 and len(letters) >= 3:
            name = letters[:120]
            break
    if not name:
        if email:
            name = email.split("@")[0].replace(".", " ").replace("_", " ").title()
        else:
            return None

    found = set(_extract_skills_section(lines))
    low = text.lower()
    for kw in _KNOWN_SKILLS:
        if _kw_present(kw, low):
            found.add(kw)
    skills = _normalise_skills(sorted(found)) if found else "[]"

    years = _resume_years(text)
    # Manager inference from the title area (first few lines), not whole doc.
    title_hint = " ".join(nonempty[:6])
    return {
        "name":       name,
        "email":      email,
        "skills":     skills,
        "experience": years,
        "department": _normalise_department(None, skills),
        "is_manager": _infer_manager(None, title_hint, years),
        "extras":     {},
    }


# ── PDF ──────────────────────────────────────────────────────────────────────

def parse_pdf(content: bytes) -> list[StagingRow]:
    """
    Extract tabular employee data from a PDF. Strategy:
      1. Try pdfplumber's table extractor first — works for well-structured
         tables produced by Excel/Word export.
      2. Fall back to line-based "Key: Value" parsing for free-form PDFs
         (one employee per blank-line-delimited block).

    Unstructured PDFs often need human cleanup; this parser aims to catch
    the common cases and return `[]` rather than wrong data when unsure.
    """
    try:
        import pdfplumber  # lazy import; heavy
    except ImportError as e:  # pragma: no cover
        raise RuntimeError("pdfplumber is not installed; cannot parse .pdf") from e

    rows: list[StagingRow] = []

    with pdfplumber.open(io.BytesIO(content)) as pdf:
        # --- Strategy 1: tables ---
        for page in pdf.pages:
            for table in page.extract_tables() or []:
                if not table or len(table) < 2:
                    continue
                header_map: dict[int, str] = {}
                for col_idx, h in enumerate(table[0] or []):
                    canonical = _canonicalise(str(h) if h else "")
                    if canonical:
                        header_map[col_idx] = canonical
                if "name" not in header_map.values():
                    continue
                for raw in table[1:]:
                    record: dict = {}
                    for col_idx, val in enumerate(raw or []):
                        key = header_map.get(col_idx) or f"extra_{col_idx}"
                        record[key] = val
                    row = _row_from_mapping(record)
                    if row:
                        rows.append(row)

        if rows:
            return rows

        # --- Strategy 2: freeform "Key: Value" blocks ---
        text = "\n".join((page.extract_text() or "") for page in pdf.pages)

    current: dict = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            if current:
                row = _row_from_mapping(current)
                if row:
                    rows.append(row)
                current = {}
            continue
        m = re.match(r"([A-Za-z ]{2,32})\s*[:\-]\s*(.+)", line)
        if not m:
            continue
        canonical = _canonicalise(m.group(1))
        if canonical:
            current[canonical] = m.group(2).strip()
    if current:
        row = _row_from_mapping(current)
        if row:
            rows.append(row)

    # --- Strategy 3: single free-form resume (one CV = one candidate) ---
    if not rows:
        single = parse_single_resume(text)
        if single:
            rows.append(single)

    return rows


# ── Row validation ──────────────────────────────────────────────────────────

def validate_row(row: StagingRow, line_no: int) -> str | None:
    """
    Return an error string if the row should be rejected, else None.

    Rejects:
      - missing / empty name (caller already filters these in _row_from_mapping,
        but we double-check at the boundary).
      - malformed email (contains '@' but no '.', or spaces)
      - completely empty skills AND missing email AND missing experience.
        Nothing identifying → no staging value.

    Warnings (soft — row still staged but admin sees the note) are
    returned as errors too so the UI can surface them.
    """
    if not row.get("name") or not str(row["name"]).strip():
        return f"row {line_no}: name is required"

    email = row.get("email")
    if email:
        # Lenient: we don't want to be stricter than Pydantic's EmailStr
        # here — admin can fix typos after staging. Just reject obvious
        # garbage.
        if " " in email or "@" not in email or "." not in email.split("@")[-1]:
            return f"row {line_no}: email '{email}' is malformed"

    try:
        skills_list = json.loads(row.get("skills") or "[]")
    except Exception:
        skills_list = []

    if (
        not skills_list
        and not email
        and (row.get("experience") in (None, 0, 0.0))
    ):
        return f"row {line_no}: no skills/email/experience — nothing to stage"
    return None


# ── Dispatcher ───────────────────────────────────────────────────────────────

def parse_file(filename: str, content: bytes) -> tuple[list[StagingRow], list[str]]:
    """
    Route to the right parser based on the filename extension.

    Returns (rows, errors). Errors are human-readable strings the admin UI
    surfaces under the upload summary so they know what was dropped.
    """
    lower = filename.lower()
    try:
        if lower.endswith(".csv"):
            rows = parse_csv(content)
        elif lower.endswith(".xlsx"):
            rows = parse_xlsx(content)
        elif lower.endswith(".pdf"):
            rows = parse_pdf(content)
        else:
            raise ValueError(
                f"Unsupported file type: {filename!r}. Use .csv, .xlsx, or .pdf."
            )
    except ValueError:
        raise
    except Exception as e:
        # Any other parser crash — surface as a single top-level error
        # rather than a 500.
        raise ValueError(f"Could not parse {filename}: {type(e).__name__}: {e}")

    errors: list[str] = []
    kept:   list[StagingRow] = []
    for idx, row in enumerate(rows, start=2):  # start=2 accounts for header row
        err = validate_row(row, idx)
        if err:
            errors.append(err)
            continue
        kept.append(row)
    return kept, errors
