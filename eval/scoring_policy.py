#!/usr/bin/env python3
"""
Aegis PM — evaluation *scoring policy* layer (gold-aware, parser-independent).

This module sits ON TOP of the frozen strict rubric in `check_parse.py`
(S1–S8 / D1–D4 / T1–T3, provided verbatim by the user and never modified).
It adds two things the baseline study locked in, both evaluation-only — they
never touch parser behaviour:

  E1  — gold-aware over-refusal code.
        Fired when a run produced ZERO tasks while the gold standard for that
        PRD expects at least one task (gold.expected_task_count.min > 0),
        AND the run is not already an E0 parse/quota error.
        This catches the prompt-injection over-refusal (prd18) that the pure
        structural checker cannot see (an empty task list trips no S/D code).

  Relaxed S5 — the PRIMARY schema metric for summary verbs.
        `check_parse.py`'s strict S5 only whitelists
        {implement, add, fix, create, migrate, write}. Relaxed S5 accepts any
        reasonable *software* imperative action verb (curated list below).
        Strict S5 is retained as a SECONDARY "instruction-following" metric.

The two S5 numbers must always be reported side by side; experiments are never
compared using different scoring rules (see eval/scoring_policy.md).
"""
from __future__ import annotations

import json
from pathlib import Path

# ── Strict whitelist (mirrors check_parse.STRICT_VERBS — the secondary metric) ─
STRICT_VERBS = {"implement", "add", "fix", "create", "migrate", "write"}

# ── Relaxed whitelist — PRIMARY metric. Any reasonable software imperative. ────
# Deliberately EXCLUDES cooking verbs (preheat, mash, …) so that hallucinated
# recipe "tasks" from the non-PRD fixture (prd19) remain visible as violations.
RELAXED_VERBS = STRICT_VERBS | {
    # Phase-7 named examples
    "generate", "send", "update", "validate", "configure", "reset",
    "authenticate", "remove", "invalidate", "delete", "import", "export", "build",
    # common engineering imperatives observed in the corpus / standard Jira usage
    "define", "integrate", "test", "list", "apply", "persist", "restrict",
    "enforce", "record", "collect", "conduct", "calculate", "describe", "respect",
    "enable", "support", "provide", "store", "handle", "display", "allow",
    "ensure", "develop", "design", "refactor", "expose", "render", "log",
    "cache", "encrypt", "hash", "verify", "check", "return", "redirect", "link",
    "email", "document", "deploy", "schedule", "track", "notify", "prevent",
    "protect", "secure", "audit", "throttle", "paginate", "seed", "rollback",
    "revoke", "issue", "sign", "decode", "encode", "route", "mount", "bind",
    "wire", "connect", "initialize", "load", "save", "edit", "view", "show",
    "manage", "register", "sanitize", "escape", "filter", "sort", "upload",
    "download", "parse", "limit", "block", "migrate", "monitor", "set",
    "setup", "capture", "compute", "aggregate", "index", "queue", "publish",
    "subscribe", "authorize", "flag", "mask", "purge", "archive", "restore",
}


def first_word(summary: str) -> str:
    parts = (summary or "").split()
    return parts[0].lower() if parts else ""


def gold_expected(pid: str, gold_dir: Path) -> dict | None:
    """Return {'min':int,'max':int} for a PRD stem, or None if no gold file."""
    gp = gold_dir / f"{pid}.gold.json"
    if not gp.exists():
        return None
    try:
        return json.loads(gp.read_text(encoding="utf-8")).get("expected_task_count")
    except json.JSONDecodeError:
        return None


def score_run_gold_aware(data: dict, base_report: dict, expected: dict | None) -> dict:
    """
    Augment a `check_parse.check_run` report with the scoring-policy metrics.

    Adds:
      strict_s5   : count of strict-S5 violations (from base_report)
      relaxed_s5  : count of summaries whose first word is not a RELAXED verb
      e1          : True if over-refusal (empty vs gold-expects-tasks, non-E0)
    Returns a new dict; does not mutate base_report.
    """
    tasks = data.get("tasks", []) or []
    is_e0 = any(v["code"] == "E0" for v in base_report["violations"])

    strict_s5 = sum(1 for v in base_report["violations"] if v["code"] == "S5")

    relaxed_s5 = 0
    relaxed_offenders = []
    for i, t in enumerate(tasks):
        fw = first_word(t.get("summary", ""))
        if fw not in RELAXED_VERBS:
            relaxed_s5 += 1
            relaxed_offenders.append({"task": i, "verb": fw,
                                      "summary": t.get("summary", "")})

    gold_min = (expected or {}).get("min", 0) if expected else 0
    e1 = (len(tasks) == 0) and (not is_e0) and (gold_min > 0)

    return {
        "strict_s5": strict_s5,
        "relaxed_s5": relaxed_s5,
        "relaxed_offenders": relaxed_offenders,
        "e1": e1,
        "gold_expected": expected,
    }
