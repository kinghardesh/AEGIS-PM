# Archived: non-canonical batch 2026-07-04_1344

A `run_eval.py` batch generated 2026-07-04 13:44 that is **not** part of the
frozen baseline. It was produced after the Groq daily-token budget was largely
spent, so most runs hit HTTP-429:

- 60 runs, ~259 tasks, **20 E0** (quota) errors.

The canonical frozen baseline is `baseline-v1-complete`
(`eval/runs/2026-07-04_complete`, 445 tasks, 0 E0). This batch is retained for
provenance only — **do not score it** and do not treat it as canonical.
