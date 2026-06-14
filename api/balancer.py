"""
aegis-pm / api / balancer.py

Task-assignment load balancer for the mixed AI + human team.

`balance_assign()` is a pure function — bytes in, ranked results out,
no DB. Callers (the admin endpoint, a unit test, a cron job) all
use the same scoring so behaviour stays consistent.

Scoring formula (tunable via W_*):

    final = 0.45 * skill_match      (Jaccard of required ∩ candidate skills)
          + 0.25 * workload_score   (1 − current_load / max_load)
          + 0.20 * balance_score    (rewards the under-utilised type)
          + 0.10 * priority_score   (high→humans, low→AI, medium→neutral)

Rules-of-thumb the formula encodes (spec §2):

  1. Skill match first — weight 0.45 is the largest single factor.
  2. Workload check — ties broken by lowest current load.
  3. Balance control — the current AI% vs HUMAN% of active tasks across
     the whole team pulls the score of the over-represented side down.
  4. Priority override — a +10% shove toward humans on high-priority
     tasks, toward AI on low-priority. Never exclusive — the other
     factors can still carry a strong match.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Literal

MemberType = Literal["AI", "HUMAN"]


# ── Tunable weights ──────────────────────────────────────────────────────────
W_SKILL    = 0.45
W_LOAD     = 0.25
W_BALANCE  = 0.20
W_PRIORITY = 0.10


# ── Data model ───────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class BalanceMember:
    id:            int
    name:          str
    type:          MemberType
    skills:        frozenset[str]
    current_load: int              # count of open tasks (todo + in_progress)


@dataclass(frozen=True)
class BalanceResult:
    member_id:       int
    member_name:     str
    member_type:     MemberType
    score:           float
    skill_match:     float
    workload_score:  float
    balance_score:   float
    priority_score:  float
    reason:          str


# ── Helpers ──────────────────────────────────────────────────────────────────

def _norm(skills: Iterable[str]) -> set[str]:
    return {s.strip().lower() for s in skills if str(s).strip()}


def _priority_score(member_type: MemberType, priority: str) -> float:
    """
    high  → human=1.0, ai=0.3 (escalations land on a person)
    low   → ai=1.0,    human=0.5 (happy path runs headless)
    other → 0.7 for both (neutral)
    """
    p = (priority or "medium").lower()
    if p == "high":
        return 1.0 if member_type == "HUMAN" else 0.3
    if p == "low":
        return 1.0 if member_type == "AI" else 0.5
    return 0.7


# ── Public API ───────────────────────────────────────────────────────────────

def balance_assign(
    required_skills: Iterable[str],
    priority:        str,
    members:         list[BalanceMember],
    top_n:           int = 5,
) -> list[BalanceResult]:
    """
    Rank `members` for a task with the given `required_skills` and
    `priority`. Returns the top `top_n` candidates sorted by descending
    score; ties broken alphabetically by name for determinism.

    Safe to call with an empty member list (returns []) or empty skills
    (falls back to workload + balance + priority scoring only).
    """
    if not members:
        return []

    req = _norm(required_skills)

    # Normalisation bases — prevent divide-by-zero for a fresh team.
    max_load = max((m.current_load for m in members), default=0) or 1

    # Current AI vs HUMAN share of the ACTIVE workload. The side with
    # more load gets a smaller balance_score, pushing new tasks the
    # other way.
    ai_load    = sum(m.current_load for m in members if m.type == "AI")
    human_load = sum(m.current_load for m in members if m.type == "HUMAN")
    total_load = max(1, ai_load + human_load)
    ai_share    = ai_load / total_load
    human_share = human_load / total_load

    results: list[BalanceResult] = []
    for m in members:
        # 1) Skill match (Jaccard vs required). If no requirements, stay
        #    neutral at 0.5 so skill doesn't dominate accidentally.
        if req:
            matched = req & m.skills
            skill_match = len(matched) / len(req)
        else:
            matched = set()
            skill_match = 0.5

        # 2) Workload score — lower load = higher score.
        workload_score = 1.0 - (m.current_load / max_load)

        # 3) Balance — reward picking the currently under-loaded type.
        balance_score = (
            (1.0 - ai_share)    if m.type == "AI"
            else (1.0 - human_share)
        )

        # 4) Priority alignment.
        pri_score = _priority_score(m.type, priority)

        final = (
            W_SKILL    * skill_match
          + W_LOAD     * workload_score
          + W_BALANCE  * balance_score
          + W_PRIORITY * pri_score
        )

        # Build a short human-readable reason.
        parts: list[str] = []
        if req and matched:
            parts.append(f"matches {len(matched)}/{len(req)} skills")
        elif req and not matched:
            parts.append(f"0/{len(req)} skill match")
        if workload_score >= 0.8:
            parts.append("low current load")
        elif workload_score <= 0.25:
            parts.append("heavily loaded")
        if balance_score >= 0.65:
            parts.append(f"{m.type.lower()}s under-utilised")
        if priority == "high" and m.type == "HUMAN":
            parts.append("high-priority → prefer human")
        elif priority == "low" and m.type == "AI":
            parts.append("low-priority → AI OK")
        reason = "; ".join(parts) or "weighted overall fit"

        results.append(BalanceResult(
            member_id=m.id,
            member_name=m.name,
            member_type=m.type,
            score=round(min(1.0, final), 4),
            skill_match=round(skill_match, 4),
            workload_score=round(workload_score, 4),
            balance_score=round(balance_score, 4),
            priority_score=round(pri_score, 4),
            reason=reason,
        ))

    results.sort(key=lambda r: (-r.score, r.member_name.lower()))
    return results[:top_n]


# ── Example: runnable as `python -m api.balancer` ───────────────────────────

if __name__ == "__main__":
    members = [
        BalanceMember(1, "Code Writer AI",  "AI",
                      frozenset({"python", "backend"}),         current_load=5),
        BalanceMember(2, "Test Writer AI",  "AI",
                      frozenset({"testing", "pytest"}),          current_load=1),
        BalanceMember(3, "Hardesh",          "HUMAN",
                      frozenset({"backend", "api", "python"}),  current_load=3),
        BalanceMember(4, "Priya",            "HUMAN",
                      frozenset({"react", "frontend"}),         current_load=0),
    ]

    for label, pri, skills in [
        ("backend API task · HIGH",   "high",   ["backend", "api"]),
        ("frontend card · medium",    "medium", ["react"]),
        ("unit tests · low",          "low",    ["testing"]),
    ]:
        print(f"\n─ {label} ─")
        for r in balance_assign(skills, pri, members):
            print(
                f"  {r.member_name:<18} [{r.member_type:<5}] "
                f"score={r.score:.3f}  (skill={r.skill_match:.2f} "
                f"load={r.workload_score:.2f} bal={r.balance_score:.2f} "
                f"pri={r.priority_score:.2f})  — {r.reason}"
            )
