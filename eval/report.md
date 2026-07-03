# Spec Interpreter — Baseline (concise) — `baseline-v1-complete`

**System:** `agents/spec_interpreter.py` → `parse_specification()`
**Provider / model:** `live-groq-llama-3.3-70b-versatile` (OpenAI-compatible,
temp 0.2, `response_format=json_object`).
**Canonical batch:** `eval/runs/2026-07-04_complete` · **tag:** `baseline-v1-complete`.
**Full analysis:** [`baseline_report.md`](baseline_report.md) · **scoring rules:**
[`scoring_policy.md`](scoring_policy.md) · **provenance:** [`manifest.json`](manifest.json).

This is the frozen, immutable baseline captured **before** any parser change, so
future (post-fix) experiments can be compared against it under identical scoring.

## Headline (measured)

| Metric | Value |
|---|---|
| PRDs / runs / tasks | 20 / 60 / 445 |
| Parse errors (E0) | 0 |
| Fully-clean runs (strict) | 27/60 |
| Over-refusals (E1) | 3 (prd18) |
| Mean Jaccard — all / excl-empty | 0.490 / 0.433 |
| Count-stable / dep-stable PRDs | 15/20 / 6/20 |
| S5 — strict (secondary) / relaxed (primary) | 84 / 22 |
| Other schema (S6) | 3 |
| Dependency violations | 6 (all D2 self-deps) |
| Edge verdicts | ✅refusal prd16 · ❌over-refusal prd18 · ❌hallucination prd19 · ✅extraction prd20 |

## Interpretation (one line each)

- **Stability:** low — content Jaccard ~0.43; counts stable (15/20), dependency
  structure not (6/20). PRD05 (clean spec) is the worst at 0.081 (tree/star/chain
  drift, ±27% story-point spread).
- **Dependencies:** *valid* (6 D2s / 445 tasks, no cycles) and the deepest-dep
  fixture (PRD20) is a perfect, stable linear chain — but *structure* drifts when
  the decomposition is under-determined.
- **Schema:** S5 84→22 under the primary relaxed rule; the 22 residual are entirely
  the prd19 recipe hallucination (no unexplained remainder).
- **Calibration:** generation tracks *surface plausibility*, not real requirements —
  empty→silence, plausible-non-spec→hallucination, injected-spec→over-refusal.

## Recovery note

5 runs (prd19 run2/3, prd20 run1–3) were quota-blocked (Groq 100k TPD) in the
`2026-07-03_partial` batch and recovered the next day in `2026-07-04_recovery`;
the canonical `2026-07-04_complete` batch merges them (0 E0). The earlier
quota-starved re-run is quarantined in `eval/archive/incomplete_quota_batch/`.
