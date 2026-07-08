# Archived: incomplete quota-starved batch

This directory holds an INCOMPLETE evaluation batch that was generated as a
second `run_eval.py --runs 3` against Groq after the daily token budget was
largely consumed. It hit HTTP-429 (tokens-per-day) after ~15 successful runs:

- 60 run files, only ~91 tasks total, 45 of 60 runs are E0 (quota errors).

It is NOT the canonical baseline. The canonical complete baseline (409 tasks,
5 E0, all failures confined to the last PRDs) is restored in ../runs/ from the
verified mirror in /outputs/. Kept here only for provenance; do not score it.
