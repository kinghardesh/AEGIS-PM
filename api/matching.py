"""
aegis-pm / api / matching.py

Skill-match scoring.

Two callable entry points:

  score_keyword(...)  → sync, zero deps, Jaccard-based. Fallback path.
  score(...)          → async, prefers semantic embeddings when OpenAI
                        is available, else reuses score_keyword.

Final-score formula (spec §4):

    final = 0.6 * skill_similarity
          + 0.3 * experience_score
          + 0.1 * priority_skill_bonus

Where:
    skill_similarity    cosine(embedding(req), embedding(cand))   [0..1]
                        OR |req∩cand| / |req| if embeddings are off
    experience_score    clamp(experience / 10, 0..1)
    priority_skill_bonus |priority∩cand| / |priority|              [0..1]
                        (0 when no priority skills are given)

The returned `matched_skills` / `missing_skills` are ALWAYS keyword-based
so explanations remain exact and auditable — embeddings tell us "fit",
keyword overlap tells us "which words line up".
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class MatchResult:
    score:           float               # final weighted score 0..1
    matched_skills:  list[str]
    missing_skills:  list[str]
    experience:      float | None
    # Populated by the new score() flow; defaulted so existing callers
    # (and tests) that construct MatchResult without them keep working.
    skill_score:     float = 0.0         # pure skill similarity 0..1 (semantic or Jaccard)
    experience_score: float = 0.0        # clamp(experience / 10, 0..1)
    priority_bonus:  float = 0.0
    confidence:      float = 0.0         # alias of skill_score (kept for back-compat)
    reason:          str   = ""
    semantic:        bool  = False       # True when embeddings drove the score


# ── Normalisation ────────────────────────────────────────────────────────────

_WS = re.compile(r"\s+")


def _normalise(token: str) -> str:
    return _WS.sub(" ", token.strip().lower())


def _split_skills(raw: str | list[str] | None) -> set[str]:
    if raw is None:
        return set()
    if isinstance(raw, list):
        items = raw
    else:
        s = raw.strip()
        if s.startswith("["):
            try:
                items = json.loads(s)
            except Exception:
                items = re.split(r"[,;|/\n]+", s)
        else:
            items = re.split(r"[,;|/\n]+", s)
    return {_normalise(x) for x in items if str(x).strip()}


def _to_sorted_csv(tokens: set[str]) -> str:
    """Canonical serialisation for cache keys + embedding input."""
    return ", ".join(sorted(tokens))


def _experience_score(experience: float | None) -> float:
    if experience is None or experience <= 0:
        return 0.0
    return min(1.0, float(experience) / 10.0)


def _priority_bonus(priority: set[str], candidate: set[str]) -> float:
    if not priority:
        return 0.0
    return len(priority & candidate) / len(priority)


def _build_reason(
    matched: set[str],
    required: set[str],
    experience: float | None,
    priority_bonus: float,
    skill_sim: float,
) -> str:
    parts: list[str] = []
    if required:
        parts.append(f"covers {len(matched)}/{len(required)} required skills")
    if skill_sim >= 0.7 and not matched:
        parts.append("strong semantic fit")
    if experience and experience >= 3:
        parts.append(f"{experience:g} yrs experience")
    if priority_bonus >= 0.5:
        parts.append("covers priority skills")
    if not parts:
        parts.append("low overall fit")
    return "; ".join(parts)


# ── Sync keyword scorer (fallback + used everywhere pre-embeddings) ─────────

def score_keyword(
    required_skills: str | list[str],
    candidate_skills: str | list[str] | None,
    experience: float | None = None,
    priority_skills: str | list[str] | None = None,
) -> MatchResult:
    required = _split_skills(required_skills)
    candidate = _split_skills(candidate_skills)
    priority = _split_skills(priority_skills)

    if not required:
        exp_s = _experience_score(experience)
        return MatchResult(
            score=exp_s, matched_skills=[], missing_skills=[],
            experience=experience, skill_score=0.0, experience_score=exp_s,
            priority_bonus=0.0, confidence=0.0,
            reason="no requirements", semantic=False,
        )

    matched = required & candidate
    missing = required - candidate
    skill_sim = len(matched) / len(required)
    exp_s     = _experience_score(experience)
    pri_bonus = _priority_bonus(priority, candidate)

    final = 0.6 * skill_sim + 0.3 * exp_s + 0.1 * pri_bonus
    return MatchResult(
        score=round(min(1.0, final), 4),
        matched_skills=sorted(matched),
        missing_skills=sorted(missing),
        experience=experience,
        skill_score=round(skill_sim, 4),
        experience_score=round(exp_s, 4),
        priority_bonus=round(pri_bonus, 4),
        confidence=round(skill_sim, 4),
        reason=_build_reason(matched, required, experience, pri_bonus, skill_sim),
        semantic=False,
    )


# ── Async unified scorer — semantic when possible, keyword otherwise ────────

async def score(
    required_skills: str | list[str],
    candidate_skills: str | list[str] | None,
    experience: float | None = None,
    priority_skills: str | list[str] | None = None,
) -> MatchResult:
    """
    Prefers cosine similarity of OpenAI embeddings over keyword overlap.
    Safe to call even without OPENAI_API_KEY — falls back to `score_keyword`.
    """
    from api.embeddings import cosine, get_embedding_batch, is_available

    required = _split_skills(required_skills)
    candidate = _split_skills(candidate_skills)
    priority = _split_skills(priority_skills)

    # Compute keyword-based explanation regardless (exact, auditable).
    matched = required & candidate
    missing = required - candidate

    skill_sim = len(matched) / len(required) if required else 0.0
    semantic = False

    if required and candidate and is_available():
        req_text  = _to_sorted_csv(required)
        cand_text = _to_sorted_csv(candidate)
        vecs = await get_embedding_batch([req_text, cand_text])
        if vecs[0] and vecs[1]:
            skill_sim = max(0.0, min(1.0, cosine(vecs[0], vecs[1])))
            semantic = True
            # Widen the "matched" set: anything with ≥0.75 cosine to the
            # required set counts as a soft match. Purely additive — exact
            # matches remain in matched_skills; we don't subtract.
            # (Kept a single call; no per-token fan-out to preserve latency.)
        # else: fall through to keyword skill_sim

    exp_s     = _experience_score(experience)
    pri_bonus = _priority_bonus(priority, candidate)

    final = 0.6 * skill_sim + 0.3 * exp_s + 0.1 * pri_bonus
    return MatchResult(
        score=round(min(1.0, final), 4),
        matched_skills=sorted(matched),
        missing_skills=sorted(missing),
        experience=experience,
        skill_score=round(skill_sim, 4),
        experience_score=round(exp_s, 4),
        priority_bonus=round(pri_bonus, 4),
        confidence=round(skill_sim, 4),
        reason=_build_reason(matched, required, experience, pri_bonus, skill_sim),
        semantic=semantic,
    )


# ── Back-compat export: embedding-only signature (now an alias) ─────────────

async def score_embedding(*args, **kwargs) -> MatchResult:  # pragma: no cover
    return await score(*args, **kwargs)
