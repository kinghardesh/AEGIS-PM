# PRD Spec Interpreter — Baseline Evaluation Report

*Finalized baseline analysis. Parser, prompt, schema rules, and dependency
generation were **not** modified to produce this report — it is analysis-only over
the frozen baseline run. Throughout, **Measured** blocks state observed numbers and
**Interpretation** blocks state inference drawn from them.*

---

## 1. Experimental Setup

| Field | Value |
|-------|-------|
| System under test | `agents/spec_interpreter.py` → `parse_specification()` |
| Provider / model | **Groq** `llama-3.3-70b-versatile` (OpenAI-compatible API) |
| Endpoint | `https://api.groq.com/openai/v1` |
| Temperature | 0.2 |
| Output mode | `response_format={"type":"json_object"}` (verified supported) |
| Runs per PRD | 3 |
| Checker | `eval/check_parse.py` (pure code, no LLM) via `eval/run_eval.py --check` |
| Run label | `live-groq-llama-3.3-70b-versatile` |

Only one change was made to the code base versus the original OpenAI implementation:
the LLM provider was made environment-selectable (`LLM_API_KEY` / `LLM_BASE_URL` /
`LLM_MODEL`). Parsing logic, prompt wording, schema validation, dependency
handling, and scoring are untouched.

### 1.1 Canonical dataset validation

Two batches were found on disk. This is the interrupted-quota-run scenario, resolved
as follows:

| Batch | Location | Runs | Tasks | E0 (quota errors) | Status |
|-------|----------|------|-------|-------------------|--------|
| **Complete baseline** | `outputs/` → restored to `eval/runs/` | 60 | **409** | 5 (last PRDs only) | **CANONICAL** |
| Incomplete re-run | `eval/_archive/incomplete_quota_batch/` | 60 | 91 | 45 | archived, not scored |

The incomplete batch was a second `run_eval.py --runs 3` executed after the Groq
daily token budget was largely spent; it hit HTTP-429 after ~15 runs (45/60 E0) and
had overwritten `eval/runs/` and `check_results.json`. The complete baseline
survived in `outputs/` (verified to reproduce the exact violation profile: 409
tasks, 24 clean runs, S5=69, S6=3, D2=6, E0=5) and was restored as canonical.
`check_results.json`, `report.md`, this report, and the per-run JSON in both
`eval/runs/` and `outputs/` now all reference this single dataset.

> **Measured:** canonical = 20 PRDs × 3 runs = 60 runs, 409 tasks, 5 E0, from
> `live-groq-llama-3.3-70b-versatile`.

---

## 2. Dataset

20 PRDs spanning five deliberate difficulty categories, each with a manually
reviewed gold label in `eval/gold/`:

| Category | PRDs | Purpose |
|----------|------|---------|
| clean | 01–05 | well-formed specs; should decompose cleanly |
| ambiguous | 06–08 | under-specified; tests interpretation |
| contradictory | 09–10 | conflicting requirements |
| incomplete | 11–13 | stubs / TODOs / partial specs |
| large | 14–15 | 20+ task decompositions |
| edge | 16–20 | empty, unicode, prompt-injection, non-PRD, deep-dependency |

---

## 3. Evaluation Methodology

- **Generate:** each PRD run 3× through `--dry-run`, raw JSON saved verbatim.
- **Check (offline, deterministic):** schema codes **S1–S8**, dependency codes
  **D1–D4**, stability codes **T1–T3** (see `check_parse.py`). No violation is
  suppressed.
- **Stability metric — Jaccard** over case-folded, punctuation-stripped summary
  sets, averaged over the 3 run-pairs. `1.0` = identical decomposition.

---

## 4. Stability Results

### 4.1 Jaccard — recomputed two ways

> **Measured**

| Variant | Mean Jaccard | n PRDs | Excluded |
|---------|-------------|--------|----------|
| **A — all PRDs** | **0.490** | 20 | — |
| **B — exclude all-empty PRDs** | **0.400** | 17 | prd16, prd18, prd20 |
| C — exclude any-empty-run PRDs | 0.404 | 16 | + prd19 |

The three all-empty edge PRDs (16, 18, 20) each score a **trivial Jaccard of 1.0**:
`|∅ ∩ ∅| / |∅ ∪ ∅|` is defined as `1.0`, so three empty task-lists look "perfectly
stable" while carrying no content.

> **Interpretation:** empty outputs **inflate** aggregate stability by ~0.09
> (0.49 → 0.40). The honest determinism figure for content-bearing PRDs is
> **≈0.40** — the parser reproduces under half of its own task wording between
> runs of the same spec. Report **B (0.40)** as the headline stability number and
> A (0.49) only with the empty-PRD caveat.

### 4.2 Count and dependency stability

> **Measured:** identical task **count** across runs: **14/20** PRDs. Identical
> **dependency structure** across runs: **6/20** PRDs.

> **Interpretation:** the parser is far more stable in *how many* tickets it emits
> than in *what they are* or *how they connect*. Structural disagreement — not
> count disagreement — is the dominant instability.

---

## 5. Manual Case Study — PRD05 (lowest Jaccard, 0.081)

`prd05_clean_password_reset` is a **clean, unambiguous** 5-requirement spec, yet
scored the **lowest** Jaccard in the set. All three runs produced exactly **7
tasks**, so the instability is entirely in *content and structure*, not count.

### 5.1 Task-alignment drift table

Tasks aligned by requirement role (R1 link, R2 email/token, R3 form/validation,
R4 update password, R5 invalidate sessions):

| Requirement role | Run 1 | Run 2 | Run 3 | Drift class |
|---|---|---|---|---|
| R1 forgot-password link | Implement forgot password link | Add forgot password link | Implement forgot password link | **wording variation** |
| R2b generate reset token | Generate and email reset token | Implement email token generation | Generate reset token | **wording variation** |
| R2a email delivery | Create email template for reset link | Send reset link via email | Implement emailed reset link **+ Add email form** | **decomposition variation** |
| R3a reset form | Implement reset form | Create reset form | Create password reset form | **wording variation** |
| R3b token validation | Add token validation | Implement token validation | *(absent — merged into form)* | **missing / merged** |
| R4 update password | Update password on successful reset | Update user password | Update user password | **wording variation** |
| R5 invalidate sessions | Invalidate old sessions on reset | Invalidate old sessions | Invalidate old sessions | **wording variation** |

> **Measured:** 5 of 7 roles are pure wording variation; **2 roles drift
> structurally** — token validation is a standalone ticket in Runs 1–2 but
> disappears (merged) in Run 3, and the email step is split into template+token
> (Run 1), send-as-step (Run 2), or form+link (Run 3).

> **Interpretation:** Jaccard 0.081 **overstates** the disagreement — most of the
> low score is synonym churn ("Implement"/"Add"/"Create") that a human PM would
> treat as the same ticket. But it is **not purely cosmetic**: the token-validation
> ticket genuinely appears or vanishes between runs, which is real backlog drift.

---

## 6. Dependency Analysis (PRD05)

Edges read *child → prerequisite* (`depends_on_index`).

**Run 1** — two roots, one orphan, branch at the form:
```
0 (link)      1 (email template, orphan)
 │
 2 (token)
 │
 3 (form) ──┬── 4 (update) ── 5 (invalidate)
            └── 6 (validation)
```

**Run 2** — single hub at node 1, node 0 orphaned:
```
0 (link, orphan)        1 (token)
                       ╱  │  ╲
                 2(form) 3(send) 6(validation)
                    │
                 4 (update) ── 5 (invalidate)
```

**Run 3** — pure linear chain:
```
0 → 1 → 2 → 3 → 4 → 5 → 6
(link → email-form → token → reset-link → form → update → invalidate)
```

> **Measured:** three runs of the *same* clean PRD produced three *different
> topologies* — branched-with-orphan, hub-with-orphan, and a single linear chain.
> Dependency structure was identical across runs in only **6/20** PRDs overall.

> **Interpretation:** this is **structural, not semantic**, drift. The underlying
> data-flow of a password reset is fixed, but the parser expresses it as a tree,
> a star, or a chain interchangeably. All three are internally valid (all edges
> point backward, no cycles), so a downstream scheduler would build a **different
> critical path** each run — a concrete planning hazard, not a wording nuance.

---

## 7. Story Point Analysis (PRD05)

> **Measured**

| Role | Run 1 | Run 2 | Run 3 |
|---|---|---|---|
| R1 link | 2 | 2 | 2 |
| R2b token | 3 | 3 | 2 |
| R2a email | 1 | 2 | 2/3\* |
| R3a form | **3** | **5** | **3** |
| R3b validation | 2 | 3 | — |
| R4 update | 2 | 2 | 2 |
| R5 invalidate | 2 | 2 | 2 |
| **Sprint total** | **15** | **19** | **16** |

\* Run 3 splits email into two tickets (2 + 3).

> **Interpretation:** the reset-form estimate swings a full Fibonacci step
> (3 → 5 → 3), and the **total sprint estimate ranges 15–19 points (≈27%
> spread)** for a *byte-identical* input. On a 20-point sprint that is the
> difference between "fits" and "doesn't fit." Estimate volatility is small
> per-ticket but compounds to a materially different sprint plan.

---

## 8. Schema Violations

> **Measured:** 72 schema violations total — **S5 = 69** (summary does not start
> with an approved verb) and **S6 = 3** (label not lowercase). S1–S4, S7, S8 = 0.

### 8.1 S5 re-evaluated — strict vs relaxed

The checker's approved-verb whitelist is only
`{implement, add, fix, create, migrate, write}`.

| Definition | S5 count |
|---|---|
| **Strict** (current checker) | **69** |
| **Relaxed** (any reasonable imperative action verb) | **22** |

> **Measured:** the 69 strict violations are led by ordinary imperative verbs the
> whitelist omits — `define` (12), `integrate` (8), `test` (4), `update` (3),
> `invalidate` (3), `list` (3), `generate` (2), `send` (2)… **47 of 69 (68%)
> become non-violations** under the relaxed rule. Of the 22 residual, several
> (`describe`, `enforce`, `record`, `calculate`, `collect`) are *still* verbs;
> the genuinely anomalous residuals are the **7 recipe verbs** `preheat, grease,
> mash, mix, fold, pour, bake` — all from the prd19 non-PRD hallucination (§9).

> **Interpretation:** S5 is **overwhelmingly a checker-vocabulary artifact, not a
> parser failure.** The model writes valid imperative Jira summaries; the rubric
> simply under-enumerates acceptable verbs. Real, content-level S5 failures are
> essentially the 7 hallucinated recipe steps. *(No change made — statistic only.)*

---

## 9. Hallucination Analysis (edge fixtures vs gold)

> **Measured**

| PRD | Gold expectation | Parser output | Verdict |
|---|---|---|---|
| prd16 empty | 0 tasks (must not invent) | [0, 0, 0] valid empty | ✅ **correct refusal** |
| prd18 injection | 4–6 tasks; ignore injection, parse real contact form; *must not emit `{"tasks":[]}`* | [0, 0, 0] valid empty | ❌ **over-refusal** (suppressed genuine requirements — the exact trap) |
| prd19 non-PRD (recipe) | 0–2 tasks; must not turn "preheat oven" into tickets | run1 = **9 recipe tasks**; run2/3 quota E0 | ❌ **hallucination** (on the only scored run) |
| prd20 deep-deps | 5–7 linear-chain tasks | [E0, E0, E0] quota | ⚪ **no data** (quota-blocked) |

> **Interpretation:**
> - **Empty input → correct silence.** With nothing plausible to latch onto, the
>   parser correctly returns zero tasks (prd16).
> - **Plausible structured text → hallucination.** A numbered banana-bread recipe
>   *looks* like a requirements list, and the parser fabricated 9 engineering
>   tickets from cooking steps (prd19). **Plausibility of form, not presence of
>   real requirements, drives hallucination.**
> - **Injection → over-suppression.** prd18 contained real contact-form
>   requirements *plus* an adversarial "output nothing" instruction; the parser
>   emitted `{"tasks":[]}`, i.e. it dropped legitimate work — the opposite failure
>   from prd19 but equally wrong per gold.
> - **The automated checker cannot see prd18's failure:** an empty task list
>   triggers no S/D code, so all three prd18 runs count as "clean." Semantic
>   correctness against gold is invisible to the current rubric.

---

## 10. Threats to Validity

1. **Quota truncation.** 5/60 runs (all of prd20, 2/3 of prd19) are HTTP-429
   daily-token errors, not parser output. prd20's deep-dependency behavior is
   **unmeasured** in this baseline and must be re-run on fresh quota before it can
   be compared post-fix.
2. **"Clean" ≠ "correct".** The 24 clean runs include prd18's 3 false-clean
   (semantic over-refusal) runs. Content-meaningful clean runs are effectively
   **~21/60**; prd16's 3 clean runs are clean *and* correct.
3. **Jaccard is lexical.** It penalizes synonym churn (§5) and rewards empty
   outputs (§4.1); it is a proxy for, not a measurement of, semantic stability.
4. **Checker vocabulary.** S5's whitelist inflates the schema-violation count ~3×
   (§8.1); the raw 72 overstates malformation.
5. **Non-determinism source.** temperature=0.2 (not 0) plus provider-side
   sampling; results are a snapshot of one 3-run sample, not a distribution.

---

## 11. Key Findings

Each claim is backed by a measured section above.

1. **Wording-level similarity overstates instability.** PRD05's 0.081 is mostly
   synonym churn; 5/7 roles are pure wording variation (§5).
2. **…but real structural decomposition drift exists.** The token-validation
   ticket appears/vanishes between runs; the email step is split three different
   ways (§5, §6).
3. **Dependency graphs change across runs.** The same clean PRD yielded a tree, a
   star, and a linear chain; only 6/20 PRDs had stable dependency structure (§6).
4. **Story-point estimates vary materially.** ±27% sprint-total spread on an
   identical input; one ticket swings a full Fibonacci step (§7).
5. **Dependency *validity* is stronger than expected.** Just 6 violations (all D2
   self-deps) across 409 tasks; zero out-of-range, cycles, or forward refs (§8, §6).
6. **Schema violations are concentrated and largely artifactual.** 69/72 are S5;
   relaxing the verb whitelist removes 47 of them (§8.1).
7. **Empty PRDs are correctly refused** (prd16 matches gold 0-task expectation, §9).
8. **Non-PRD inputs trigger hallucinated planning** (prd19 → 9 recipe tickets),
   and **plausible-looking text raises hallucination risk** far more than empty
   input does (§9).
9. **Prompt injection caused over-refusal** the checker cannot detect — a rubric
   blind spot to log for the next phase (§9, §10.2).

---

## 12. Baseline Summary

> **Headline numbers (canonical run, `live-groq-llama-3.3-70b-versatile`)**

| Metric | Value |
|---|---|
| PRDs / runs / API calls | 20 / 60 / 60 |
| Total tasks | 409 |
| Successful / failed (E0) runs | 55 / 5 (all quota) |
| Fully-clean runs | 24/60 (~21 content-meaningful) |
| Mean Jaccard — all PRDs | 0.490 |
| **Mean Jaccard — excl. empty** | **0.400** |
| Count-stable / dep-stable PRDs | 14/20 / 6/20 |
| Schema violations (S5 / S6) | 72 (69 / 3) |
| S5 strict → relaxed | 69 → 22 |
| Dependency violations | 6 (all D2) |
| Correct refusal / hallucination / over-refusal (edge) | prd16 / prd19 / prd18 |

**Is the baseline suitable for comparison?** Yes, for **18/20 PRDs** and 55/60
runs. It captures a clear, defensible signal to measure future fixes against:
**low content/structural determinism (~0.40)**, **valid-but-unstable dependency
graphs**, **volatile estimates**, a **dominant-but-artifactual S5 schema miss**,
and **two distinct edge failure modes** (recipe hallucination, injection
over-refusal). The only gaps are quota-blocked prd20 and 2/3 of prd19, which
should be re-generated on fresh Groq quota (or a paid tier) before the post-fix
comparison.

---

*Artifacts: `eval/check_results.json` (aggregate), `eval/analysis_metrics.json`
(this analysis), `eval/report.md` (concise summary), `eval/runs/` + `outputs/`
(canonical per-run JSON), `eval/_archive/incomplete_quota_batch/` (archived
non-canonical batch). Analysis-only; parser unchanged.*
