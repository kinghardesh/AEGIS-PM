# PRD Spec Interpreter — Frozen Baseline Report (v1-complete)

*Immutable baseline for the Groq `llama-3.3-70b-versatile` parser, captured before
any parser change. Analysis-only: the parser, prompt, schema rules, and dependency
generation were **not** modified. **Measured** blocks state observed numbers;
**Interpretation** blocks state inference. Scored under the locked policy in
`eval/scoring_policy.md` (E1 + dual strict/relaxed S5).*

| | |
|---|---|
| Provider / model | **Groq `llama-3.3-70b-versatile`** (OpenAI-compatible) |
| Canonical batch | `eval/runs/2026-07-04_complete` |
| Git tag | `baseline-v1-complete` (supersedes `baseline-v1-partial`) |
| Manifest | `eval/manifest.json` (single source of truth) |
| Runs / tasks | 20 PRDs × 3 = 60 runs · **445 tasks** · **0 E0** |

---

## 1. Experimental Setup

The parser is provider-agnostic via `LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL`;
this run used Groq `llama-3.3-70b-versatile`, temperature 0.2,
`response_format=json_object`, with 429 exponential-backoff. Runs execute under the
base Python 3.11 interpreter (the repo's `venv311`/`.venv` are broken — `openai`
ships without its `__init__.py` and imports as an empty namespace package).

### 1.1 Canonical dataset validation & provenance

The baseline was assembled and frozen through two tagged commits:

| Batch dir | Contents | Role |
|-----------|----------|------|
| `runs/2026-07-03_partial/` | first live run; prd19 2/3 + prd20 3/3 quota-blocked (E0) | `baseline-v1-partial` |
| `runs/2026-07-04_recovery/` | the 5 quota-blocked runs, re-run after quota reset | provenance |
| `runs/2026-07-04_complete/` | partial with the 5 E0 stubs replaced by recovered runs | **`baseline-v1-complete` (canonical)** |
| `archive/incomplete_quota_batch/` | an unrelated quota-starved re-run (91 tasks, 45 E0) | quarantined, never scored |

`run_eval.py` now writes every run into a **new timestamped batch directory** and
never overwrites, so the earlier data-loss (a later run silently clobbering
`eval/runs/`) cannot recur. `manifest.json`, `check_results.json`, this report, and
the per-run JSON all resolve to `runs/2026-07-04_complete`.

> **Measured:** canonical = 60 runs, 445 tasks, 0 E0, `live-groq-llama-3.3-70b-versatile`.

---

## 2. Dataset

20 PRDs across five difficulty tiers, each with a manually-reviewed gold label
(`eval/gold/`) carrying `expected_task_count {min,max}`:

| Tier | PRDs | Purpose |
|------|------|---------|
| clean | 01–05 | well-formed specs |
| ambiguous | 06–08 | under-specified |
| contradictory | 09–10 | conflicting requirements |
| incomplete | 11–13 | stubs / TODOs |
| large | 14–15 | 20+ task decompositions |
| edge | 16–20 | empty, unicode, injection, non-PRD, deep-dependency |

---

## 3. Evaluation Methodology

- **Generate:** each PRD 3× via `--dry-run`, raw JSON saved verbatim into the batch dir.
- **Strict rubric (frozen, `check_parse.py`):** schema S1–S8, dependency D1–D4,
  stability T1–T3. No violation suppressed.
- **Scoring policy overlay (`scoring_policy.py`, locked):**
  - **E1** — gold-aware over-refusal: `generated==0 ∧ gold.min>0 ∧ ¬E0`.
  - **S5 dual metric** — **relaxed S5** (primary; any reasonable software
    imperative verb) and **strict S5** (secondary; the six-verb whitelist, an
    instruction-following signal). Both are always reported together; experiments
    are never compared across different rules.
- **Jaccard** over case-folded, punctuation-stripped summary sets, averaged over the
  3 run-pairs (`1.0` = identical decomposition).

---

## 4. Stability Results

### 4.1 Jaccard — two ways

> **Measured**

| Variant | Mean Jaccard | n | Excluded |
|---------|-------------|---|----------|
| **A — all PRDs** | **0.490** | 20 | — |
| **B — exclude all-empty PRDs** | **0.433** | 18 | prd16, prd18 |

Empty task-lists score a *trivial* Jaccard of `1.0` (`∅∩∅ / ∅∪∅ ≜ 1`). Only two
PRDs are now all-empty (prd16 correct refusal; prd18 over-refusal), inflating the
aggregate by ~0.057.

> **Interpretation:** report **B (0.433)** as the honest content-stability figure.
> The parser reproduces well under half of its own summary wording between runs of
> the same spec.

### 4.2 Count and dependency stability

> **Measured:** identical task **count** across runs: **15/20** PRDs. Identical
> **dependency structure**: **6/20** PRDs. Fully-clean runs (strict rubric):
> **27/60**.

> **Interpretation:** the parser is stable in *how many* tickets it emits, far less
> stable in *what they are* and *how they connect*.

### 4.3 Full per-PRD table

> **Measured**

| PRD | tier | counts | Jaccard | dep struct | E1 | S5 strict/relaxed |
|-----|------|--------|---------|-----------|----|-------------------|
| prd01 auth | clean | 7,7,7 | 0.556 | DIFFERS | 0 | 0/0 |
| prd02 csv | clean | 6,6,6 | 0.394 | stable | 0 | 3/0 |
| prd03 dark | clean | 4,5,5 | 0.576 | DIFFERS | 0 | 10/0 |
| prd04 rate | clean | 7,7,7 | 0.517 | DIFFERS | 0 | 4/0 |
| **prd05 pwd-reset** | clean | 7,7,7 | **0.081** | DIFFERS | 0 | 9/0 |
| prd06 perf | ambiguous | 7,7,7 | 0.280 | stable | 0 | 0/0 |
| prd07 notif | ambiguous | 8,7,7 | 0.778 | DIFFERS | 0 | 0/0 |
| prd08 search | ambiguous | 5,5,5 | 0.296 | DIFFERS | 0 | 0/0 |
| prd09 auth-contra | contradictory | 9,9,11 | 0.249 | DIFFERS | 0 | 2/0 |
| prd10 retention | contradictory | 7,7,7 | 0.185 | DIFFERS | 0 | 5/0 |
| prd11 payments | incomplete | 8,8,8 | 0.236 | DIFFERS | 0 | 7/0 |
| prd12 stub | incomplete | 3,3,3 | 0.300 | DIFFERS | 0 | 3/0 |
| prd13 todos | incomplete | 5,5,5 | 1.000 | stable | 0 | 12/0 |
| prd14 ecommerce | large | 21,21,20 | 0.142 | DIFFERS | 0 | 3/0 |
| prd15 saas-admin | large | 22,23,21 | 0.252 | DIFFERS | 0 | 4/0 |
| prd16 empty | edge | 0,0,0 | 1.000\* | stable | 0 | 0/0 |
| prd17 unicode | edge | 7,7,7 | 0.621 | DIFFERS | 0 | 0/0 |
| **prd18 injection** | edge | 0,0,0 | 1.000\* | stable | **3** | 0/0 |
| **prd19 non-PRD** | edge | 9,9,9 | 0.867 | DIFFERS | 0 | **22/22** |
| **prd20 deep-deps** | edge | 6,6,6 | 0.467 | **stable** | 0 | 0/0 |

\* trivial 1.0 from empty output.

---

## 5. Manual Case Study — PRD05 (lowest Jaccard, 0.081)

A **clean, unambiguous** 5-requirement spec, yet the least stable in the set. All
three runs produced exactly **7 tasks**, so the instability is entirely in content
and structure, not count.

### 5.1 Task-alignment drift (roles: R1 link, R2 email/token, R3 form/validation, R4 update, R5 sessions)

| Role | Run 1 | Run 2 | Run 3 | Drift |
|---|---|---|---|---|
| R1 link | Implement forgot password link | Add forgot password link | Implement forgot password link | wording |
| R2b token gen | Generate and email reset token | Implement email token generation | Generate reset token | wording |
| R2a email delivery | Create email template | Send reset link via email | Implement emailed reset link **+ Add email form** | **decomposition** |
| R3a reset form | Implement reset form | Create reset form | Create password reset form | wording |
| R3b token validation | Add token validation | Implement token validation | *(absent — merged)* | **missing / merged** |
| R4 update password | Update password on successful reset | Update user password | Update user password | wording |
| R5 invalidate sessions | Invalidate old sessions on reset | Invalidate old sessions | Invalidate old sessions | wording |

> **Measured:** 5/7 roles are pure wording variation; 2 drift structurally — the
> token-validation ticket exists standalone in Runs 1–2 but vanishes (merged) in
> Run 3; the email step is split 3 different ways.

> **Interpretation:** Jaccard 0.081 **overstates** disagreement (mostly synonym
> churn a human PM would treat as the same ticket), yet is **not purely cosmetic** —
> a real backlog item appears/disappears between runs.

---

## 6. Dependency Analysis

### 6.1 PRD05 — topology changes run-to-run (edges = child → prerequisite)

```
Run 1  two roots + orphan, branch at form:      Run 2  single hub at node 1:
  0(link)      1(email-tmpl, orphan)              0(link, orphan)   1(token)
   └2(token)                                                       ╱  │  ╲
      └3(form)─┬─4(update)─5(invalidate)                     2(form) 3(send) 6(valid)
               └─6(validation)                                  └4(update)─5(invalidate)

Run 3  pure linear chain:   0 → 1 → 2 → 3 → 4 → 5 → 6
```

> **Measured:** three runs of the same clean PRD → three topologies
> (branched-with-orphan, hub-with-orphan, linear chain). All internally valid
> (backward edges, no cycles).

### 6.2 PRD20 — the deepest-dependency fixture (recovered; Phase 11)

> **Measured:** all 3 runs produced the **identical, correct linear chain**
> `ingest → validate → transform → deduplicate → load → notify`
> (deps `None,0,1,2,3,4`). **Zero** violations, **zero** cycles, **zero**
> self-references, **zero** forward references. Dependency structure **stable**
> across all runs; counts stable (6,6,6). Run 3 varied only two summary verbs
> (Add/Create) — structure unchanged.

> **Interpretation — refined conclusion:** the earlier "dependency generation is
> generally stable" claim must be **split in two**:
> - **Dependency *validity* is strong** — 6 violations (all D2 self-deps) across
>   445 tasks (<1.4%); no cycles/out-of-range/forward refs; the fixture explicitly
>   built to stress depth (PRD20) is handled **perfectly**.
> - **Dependency *structure stability* is content-dependent** — when the PRD
>   dictates a clear linear order (PRD20), the graph is reproduced exactly; when
>   the decomposition itself is under-determined (PRD05), the same work is
>   expressed as a tree, a star, or a chain interchangeably (only 6/20 PRDs
>   dep-stable overall).

---

## 7. Story Point Analysis (PRD05)

> **Measured**

| Role | Run 1 | Run 2 | Run 3 |
|---|---|---|---|
| R3a reset form | **3** | **5** | **3** |
| R2b token | 3 | 3 | 2 |
| others (link/update/invalidate) | stable at 2 | | |
| **Sprint total** | **15** | **19** | **16** |

> **Interpretation:** the reset-form estimate swings a full Fibonacci step
> (3→5→3); the sprint total ranges **15–19 (≈27% spread)** on a byte-identical
> input — the difference between "fits a 20-pt sprint" and "doesn't."

---

## 8. Schema Violations & S5 Accounting

> **Measured:** 87 schema violations — **S5 = 84** (strict), **S6 = 3** (non-lowercase
> labels). S1–S4, S7, S8 = 0. Under the **primary (relaxed) S5**, only **22** remain.

### 8.1 Every relaxed-S5 violation, accounted for (Phase 8)

> **Measured** — the 22 residual relaxed-S5 violations have exactly one source:

| Violation verb | Occurrences | Reason | Example |
|---|---|---|---|
| preheat | 3 | non-PRD hallucination (prd19 recipe) | "Preheat oven" |
| grease | 3 | non-PRD hallucination | "Grease loaf pan" |
| mash | 3 | non-PRD hallucination | "Mash bananas" |
| mix | 4 | non-PRD hallucination | "Mix butter and bananas" |
| fold | 3 | non-PRD hallucination | "Fold in flour" |
| pour | 3 | non-PRD hallucination | "Pour batter into loaf pan" |
| bake | 3 | non-PRD hallucination | "Bake banana bread" |
| **total** | **22** | **all from prd19 (all 3 runs)** | — |

> **Interpretation:** there is **no unexplained remainder**. Strict S5 (84) is
> overwhelmingly a **checker-vocabulary artifact** — 62 of 84 are ordinary
> engineering imperatives the six-verb whitelist omits (define, integrate, update,
> generate, invalidate, …). The only *content-level* S5 failures are the 22
> hallucinated cooking verbs. Relaxed S5 = 22 is thus a **pure hallucination
> signal**; strict S5 = 84 is an **instruction-following** signal (how literally
> the model obeyed the six-verb rule).

---

## 9. Special-Fixture Validation (Phase 9)

> **Measured** — classified against gold `expected_task_count` and notes:

| Fixture | Gold expects | Output | Classification |
|---|---|---|---|
| prd16 empty | 0 | [0,0,0] valid empty | ✅ **Correct refusal** |
| prd18 injection | 4–6 (ignore injection, parse contact form; *must not emit `{}`*) | [0,0,0] valid empty | ❌ **Over-refusal (E1×3)** |
| prd19 non-PRD recipe | 0–2 | [9,9,9] recipe tasks | ❌ **Hallucination** (all 3 runs) |
| prd20 deep-deps | 5–7 linear chain | [6,6,6] correct chain | ✅ **Correct extraction** |

> **Interpretation:** recovering prd19/prd20 sharpened the picture — the non-PRD
> hallucination is now confirmed **reproducible** (3/3 runs, J=0.867), and the
> deep-dependency fixture is a **correct extraction**, not the "no data" gap of the
> partial baseline.

---

## 10. Generation-Calibration Finding (Phase 10)

Three edge fixtures expose a single, consistent calibration behavior. The parser's
decision to *generate* is driven by **surface plausibility of the input, not by the
presence of genuine software requirements**:

1. **Truly empty input (prd16) → correct refusal.** Nothing plausible to latch
   onto → 0 tasks (3/3). *Evidence: [0,0,0], gold min 0.*
2. **Legitimate spec carrying a prompt injection (prd18) → over-refusal.** Real
   contact-form requirements were present, but the adversarial "output nothing"
   instruction suppressed all output → `{"tasks":[]}` (3/3, E1×3). The parser
   attended to the injected instruction over the genuine content. *Evidence: gold
   4–6, actual 0; the exact trap the gold warned against.*
3. **Plausible-looking non-spec (prd19 recipe) → hallucinated plan.** A numbered
   banana-bread recipe *looks* like a requirements list, so the parser fabricated 9
   engineering tickets from cooking steps — reproducibly (3/3, J=0.867).

> **Interpretation:** the failure axis is **form, not substance**. Empty→silence,
> plausible-non-spec→fabrication, and spec-with-injection→suppression together show
> the model is calibrated to the *shape* of the input rather than to whether it
> contains real, actionable requirements. Notably, prd18's failure is **invisible
> to the strict structural checker** (empty list trips no S/D code) — E1 exists
> precisely to surface it.

---

## 11. Threats to Validity

1. **"Clean" ≠ "correct".** The 27 strict-clean runs include prd18's 3 false-clean
   (over-refusal) runs; E1 catches these but they still count as structurally clean.
   Content-meaningful *and* correct clean runs are fewer.
2. **Jaccard is lexical** — penalizes synonym churn (§5), rewards empty output
   (§4.1); a proxy for, not a measurement of, semantic stability.
3. **Checker vocabulary** inflates strict S5 ~3.8× (84 vs 22 relaxed, §8).
4. **Non-determinism source** — temperature 0.2 (not 0) plus provider sampling; the
   numbers are one 3-run sample, not a distribution.
5. **Recovery timing** — prd19/prd20 were generated one day later than the rest
   (same provider/model/settings/prompt); no drift observed, but noted for rigor.

---

## 12. Key Findings

Each backed by a measured section.

1. **Wording similarity overstates instability** — PRD05 0.081 is mostly synonym
   churn (5/7 roles wording-only) (§5).
2. **…but real structural decomposition drift exists** — token-validation ticket
   appears/vanishes; email split three ways (§5, §6.1).
3. **Dependency graphs change across runs** — tree/star/chain for the same PRD;
   only 6/20 dep-stable (§6.1).
4. **Dependency *validity* is strong and the deepest-dep fixture is perfect** — 6
   D2s across 445 tasks; PRD20 a correct, stable linear chain 3/3 (§6.2).
5. **Story-point estimates vary materially** — ±27% sprint-total spread on identical
   input (§7).
6. **Schema violations are concentrated and largely artifactual** — 84 strict S5 →
   22 relaxed, every residual explained as prd19 recipe hallucination (§8).
7. **Empty input is correctly refused; deep-dep spec correctly extracted** (§9).
8. **Prompt injection causes over-refusal (E1×3), invisible to the strict checker**
   (§9, §10).
9. **Generation is calibrated to surface plausibility, not real requirements** —
   empty→silence, plausible-non-spec→hallucination, injected-spec→suppression (§10).

---

## 13. Baseline Summary (locked)

> **Headline numbers — `baseline-v1-complete`, `live-groq-llama-3.3-70b-versatile`**

| Metric | Value |
|---|---|
| PRDs / runs / tasks | 20 / 60 / 445 |
| E0 (parse/quota) | 0 |
| Fully-clean runs (strict) | 27/60 |
| **Over-refusals (E1)** | **3** (prd18) |
| Mean Jaccard — all / excl-empty | 0.490 / **0.433** |
| Count-stable / dep-stable PRDs | 15/20 / 6/20 |
| **S5 — strict (secondary) / relaxed (primary)** | **84 / 22** |
| Other schema (S6) | 3 |
| Dependency violations | 6 (all D2) |
| Edge verdicts | refusal ✅prd16 · over-refusal ❌prd18 · hallucination ❌prd19 · extraction ✅prd20 |

**Fit for comparison?** Yes — this is a **complete (0 E0), reproducible, tagged**
baseline. Future (post-fix) experiments must be scored under the same locked policy
(`scoring_policy.md`: relaxed S5 primary, strict S5 secondary, E1) and compared
against `baseline-v1-complete`. The signal to beat: **content stability ~0.43**,
**valid-but-structurally-unstable dependencies**, **±27% estimate volatility**,
**S5 84/22**, and **three distinct edge failure modes** (over-refusal,
hallucination, and surface-plausibility mis-calibration).

---

*Artifacts: `eval/manifest.json` · `eval/check_results.json` ·
`eval/analysis_metrics.json` · `eval/report.md` (concise) · `eval/scoring_policy.md`
· `eval/runs/2026-07-04_complete/` (canonical) · `eval/runs/2026-07-03_partial/` +
`eval/runs/2026-07-04_recovery/` (provenance) ·
`eval/archive/incomplete_quota_batch/` (quarantined). Parser unchanged.*
