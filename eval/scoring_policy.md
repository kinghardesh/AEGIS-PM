# Evaluation Scoring Policy (locked for the baseline study)

This document freezes the scoring rules used for the Spec-Interpreter baseline so
that the baseline and every future (post-fix) experiment are compared under
**identical** rules. Changing any rule here invalidates cross-experiment
comparison. Implemented in `eval/scoring_policy.py`; the strict structural rubric
lives (unchanged) in `eval/check_parse.py`.

> **Golden rule:** never compare two experiments scored under different rules.
> Always report the primary and secondary metrics side by side.

---

## 1. Layers

| Layer | File | Status |
|-------|------|--------|
| Strict structural rubric (S1–S8, D1–D4, T1–T3) | `check_parse.py` | frozen, provided verbatim; never modified |
| Gold-aware overlay (E1, relaxed S5) | `scoring_policy.py` | this policy |

Both are **evaluation-only**. Neither changes parser behaviour.

---

## 2. E1 — gold-aware over-refusal

**Definition.** A run records **E1** when it produced **zero tasks** while the gold
standard for that PRD expects **at least one** task, and the run is **not** already
an `E0` parse/quota error.

```
E1  ⇔  len(generated_tasks) == 0
       AND gold.expected_task_count.min > 0
       AND run is not E0
```

**Why it exists.** The pure structural checker cannot see this failure: an empty
task list trips no S/D code, so an over-refusal counts as "clean." E1 makes the
prompt-injection over-refusal (prd18: gold expects 4–6 contact-form tasks, parser
returned `{"tasks":[]}`) visible and countable.

**What it deliberately does *not* flag.** PRDs whose gold `min == 0`
(empty input prd16, non-PRD prd19, stub prds 12/13) — for these, returning zero
tasks is a *correct refusal*, not a failure.

---

## 3. S5 — dual metric (primary + secondary)

The summary-verb rule is reported **two ways, always together**.

### 3.1 Primary — Relaxed S5

Accepts any reasonable **software** imperative action verb. This is the headline
schema-verb metric for the study. The whitelist (`RELAXED_VERBS` in
`scoring_policy.py`) includes the Phase-7 examples (create, build, generate,
update, send, configure, validate, reset, authenticate, remove, invalidate,
delete, import, export) plus common engineering imperatives observed in the
corpus (define, integrate, test, enforce, record, collect, describe, respect,
persist, restrict, …).

It **deliberately excludes cooking verbs** (preheat, grease, mash, mix, fold,
pour, bake) so that hallucinated recipe "tasks" from the non-PRD fixture (prd19)
remain visible as violations rather than being laundered into passes.

### 3.2 Secondary — Strict S5

The original `check_parse.py` whitelist **exactly**:
`{implement, add, fix, create, migrate, write}`. This is retained as an
**instruction-following** metric — it measures how often the model obeyed the
prompt's literal six-verb rule, not whether the summary is a valid Jira title.

### 3.3 Reporting rule

Every table that cites S5 cites **both** numbers (e.g. `S5 strict/relaxed =
84/22`). An experiment is never scored with one definition and compared against
another scored with the other.

---

## 4. Provenance requirement

Every scored batch resolves through `eval/manifest.json`, which pins the provider,
model, git commit, git tag, batch directory, and settings for the numbers in
`check_results.json`. See `eval/manifest.json`.
