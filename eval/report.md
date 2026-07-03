# Spec Interpreter — Baseline Evaluation (Groq / Llama-3.3-70B)

**System under test:** `agents/spec_interpreter.py` → `parse_specification()`
**Provider / model:** `live-groq-llama-3.3-70b-versatile`
(OpenAI-compatible endpoint `https://api.groq.com/openai/v1`,
`temperature=0.2`, `response_format={"type":"json_object"}`).
**Task:** decompose a PRD into a structured JSON list of Jira tickets.
**Question:** does the parser produce *valid* (schema-conformant, dependency-sound)
and *deterministic* (stable across repeated runs of the same input) output?

This is the **baseline** run captured *before* any parser/prompt/schema/determinism
fixes. It exists purely so that future experiments can be compared against a
fixed reference point. No parser logic, prompt wording, schema rules, or scoring
were changed to produce it — the only code change was making the LLM provider
selectable by environment (`LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL`).

The report is produced by a fully automated, LLM-free checker
(`eval/check_parse.py` + `eval/run_eval.py`) over a 20-PRD dataset with
manually-reviewed gold standards.

---

## 1. Methodology

| Stage | Tool | What it does |
|-------|------|--------------|
| Generate | `spec_interpreter.py --dry-run --out` | Runs each PRD **N=3** times, writes the *raw* parser JSON to `runs/<prd>_run{k}.json` (mirrored to `outputs/<prdNN>_run{k}.json`) |
| Check (single PRD) | `check_parse.py a.json b.json c.json` | Schema (S1–S8) + dependency (D1–D4) + stability (T1–T3) for one PRD's runs |
| Check (batch) | `run_eval.py --check` | Same logic, per-PRD across all 20 PRDs, aggregated to `check_results.json` |

**Violation taxonomy** (no violation is suppressed):

- **Schema** — S1 invalid `issue_type`, S2 invalid `priority`, S3 non-Fibonacci
  `story_points`, S4 summary > 80 chars, S5 summary not starting with an approved
  verb, S6 non-lowercase labels, S7 missing/empty `acceptance_criteria`,
  S8 `total_tasks` ≠ `len(tasks)`.
- **Dependencies** — D1 `depends_on_index` out of range, D2 self-dependency,
  D3 dependency cycle, D4 forward reference (depends on a *later* task).
- **Stability** (across the N runs of one PRD) — T1 identical task count,
  T2 Jaccard similarity of normalized summaries, T3 identical dependency structure.

**Jaccard** is computed over the set of case-folded, punctuation-stripped
summaries: `|A ∩ B| / |A ∪ B|`, averaged over all run pairs. `1.0` = identical
decomposition; lower = the parser reorganizes/rewords the work between runs.

---

## 2. Configuration

| Field | Value |
|-------|-------|
| Provider | Groq (OpenAI-compatible) |
| Model | `llama-3.3-70b-versatile` |
| Base URL | `https://api.groq.com/openai/v1` |
| Temperature | 0.2 |
| JSON mode | `response_format={"type":"json_object"}` (verified supported) |
| Rate-limit handling | HTTP 429 → exponential backoff (2/4/8/16s, 5 attempts), then fail loudly |
| PRDs | 20 |
| Runs per PRD | 3 |
| Total API calls | 60 |
| Run label (`_manifest.json`) | `live-groq-llama-3.3-70b-versatile` |

---

## 3. Headline results

| Metric | Value |
|--------|-------|
| PRDs evaluated | 20 |
| Runs checked | 60 |
| Successful runs (produced parseable output) | 55 |
| Failed runs (E0) | 5 |
| Total tasks generated | 409 |
| Fully-clean runs (zero violations) | 24 / 60 |
| Schema violations (total) | 72 |
| Dependency violations (total) | 6 |
| Parse errors (E0) | 5 |
| Mean Jaccard (across 20 PRDs) | **0.49** |
| Lowest Jaccard | 0.081 (`prd05_clean_password_reset`) |
| Highest Jaccard | 1.0 (`prd13_incomplete_todos`; also trivially the empty-output edge PRDs 16/18/20) |
| Count-stable PRDs | 14 / 20 |
| Dependency-structure-stable PRDs | 6 / 20 |

**Violation frequency (all runs):**

| Code | Meaning | Count |
|------|---------|-------|
| S5 | summary does not start with an approved verb | 69 |
| S6 | labels not all lowercase | 3 |
| D2 | task depends on itself | 6 |
| E0 | parse returned an error / no tasks | 5 |

Most common **schema** violation: **S5** (69) — non-approved leading verb.
Most common **dependency** violation: **D2** (6) — self-dependency.

---

## 4. The 5 failed runs are quota, not parser

All five E0 failures share one root cause and it is **not** a parser defect:

```
Rate limit reached for model `llama-3.3-70b-versatile` ...
service tier `on_demand` on tokens per day (TPD): Limit 100000, Used ~99.4k
```

The Groq free-tier **daily token budget (100k TPD)** was exhausted at
`prd19_edge_nonprd` run 2. From that point on every call returned HTTP 429; the
new backoff logic retried 5× and then **terminated with a clear error** instead
of silently continuing (Phase 4 requirement). The affected runs are:

- `prd19_edge_nonprd` run 2, run 3
- `prd20_edge_deep_deps` run 1, run 2, run 3

Consequence: `prd20_edge_deep_deps` has **no usable output in this baseline**
(all 3 runs were quota-blocked), so its `1.0` Jaccard is an artefact of three
identical error stubs, not agreement. `prd19` has one good run (run 1) and two
quota stubs. Every other PRD (01–18) completed all 3 runs cleanly against the
model. The baseline is therefore complete and valid for 18.33 of 20 PRDs.

---

## 5. Per-PRD stability

| PRD | Category | Task counts | Jaccard | Dep struct |
|-----|----------|-------------|---------|-----------|
| prd01_clean_auth | clean | 7,7,7 | 0.556 | DIFFERS |
| prd02_clean_csv_export | clean | 6,6,6 | 0.394 | stable |
| prd03_clean_dark_mode | clean | 4,5,5 | 0.576 | DIFFERS |
| prd04_clean_rate_limit | clean | 7,7,7 | 0.517 | DIFFERS |
| prd05_clean_password_reset | clean | 7,7,7 | **0.081** | DIFFERS |
| prd06_ambiguous_performance | ambiguous | 7,7,7 | 0.280 | stable |
| prd07_ambiguous_notifications | ambiguous | 8,7,7 | 0.778 | DIFFERS |
| prd08_ambiguous_search | ambiguous | 5,5,5 | 0.296 | DIFFERS |
| prd09_contradictory_auth | contradictory | 9,9,11 | 0.249 | DIFFERS |
| prd10_contradictory_retention | contradictory | 7,7,7 | 0.185 | DIFFERS |
| prd11_incomplete_payments | incomplete | 8,8,8 | 0.236 | DIFFERS |
| prd12_incomplete_stub | incomplete | 3,3,3 | 0.300 | DIFFERS |
| prd13_incomplete_todos | incomplete | 5,5,5 | **1.000** | stable |
| prd14_large_ecommerce | large | 21,21,20 | 0.142 | DIFFERS |
| prd15_large_saas_admin | large | 22,23,21 | 0.252 | DIFFERS |
| prd16_edge_empty | edge | 0,0,0 | 1.000* | stable |
| prd17_edge_unicode | edge | 7,7,7 | 0.621 | DIFFERS |
| prd18_edge_injection | edge | 0,0,0 | 1.000* | stable |
| prd19_edge_nonprd | edge | 9,0,0 | 0.333 | DIFFERS |
| prd20_edge_deep_deps | edge | 0,0,0 | 1.000† | stable |

`*` legitimately-empty output (empty PRD / prompt-injection input → no tasks).
`†` all three runs were quota-blocked (E0); the 1.0 is three identical error stubs, not agreement.

---

## 6. Interpretation

- **Was the parser stable?** No. Mean Jaccard **0.49** means that on average the
  same PRD is decomposed less than half-identically between runs. Task *counts*
  are fairly stable (14/20 PRDs) but *wording and dependency structure* are not
  (only 6/20 have identical dependency edges across runs). `prd05` at 0.081 is
  effectively a different decomposition every run. `temperature=0.2` is not
  low enough to give deterministic output here.
- **Were schema violations common?** Yes, but concentrated. 72 violations, of
  which **69 are the single rule S5** (summary must start with one of
  implement/add/fix/create/migrate/write). The model routinely opens summaries
  with other verbs ("Set up", "Enable", "Support", "Configure", "Build", …).
  This is one prompt-vs-checker mismatch, not broad malformation — the rest of
  the schema (issue types, priorities, Fibonacci points, acceptance criteria)
  is almost entirely conformant. S6 (3) is a handful of capitalized labels.
- **Were dependency violations common?** No. Only **6 (all D2, self-dependency)**
  across 409 tasks — under 1.5%. No out-of-range indices, no cycles, no forward
  references. Dependency *validity* is good; dependency *stability* is the weak
  point (structure differs run-to-run).
- **Is the baseline suitable for comparison?** Yes, with one caveat. 55/60 runs
  and 18/20 PRDs are cleanly captured and directly comparable. Only
  `prd20_edge_deep_deps` (and 2/3 of `prd19`) are missing due to the Groq daily
  token cap — an infrastructure limit, not a parser property. Any future
  experiment should re-run those two PRDs (fresh daily quota, or a paid tier) to
  complete the comparison surface, but the aggregate signal — low determinism,
  a single dominant schema rule miss (S5), and sound-but-unstable dependencies —
  is a solid reference for measuring the next round of fixes.

**Do not** read the 5 failures as regressions to fix in the parser: fixing them
means supplying more token budget, not changing code.

---

*Generated by `eval/run_eval.py --runs 3` against Groq `llama-3.3-70b-versatile`.
Raw per-run outputs: `eval/runs/` (canonical) and `outputs/` (normalized names).
Machine-readable aggregate: `eval/check_results.json`.*
