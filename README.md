# Aegis PM

An autonomous multi-agent project-management system — and a frozen evaluation study of the one component in it that uses an LLM.

Aegis PM watches a Jira board, flags work that has gone stale, notifies the right people in Slack, and turns a product requirements document into structured tasks. Nothing reaches Jira without human approval.

The system is real and running in staging. The more interesting half of this repo is the evaluation: 20 gold-labelled PRDs, 3 runs each, a scoring policy locked in writing *before* the first run, and a full account of where the LLM component is unreliable.

**Start here:** [`eval/baseline_report.md`](eval/baseline_report.md) · frozen at tag [`baseline-v1-complete`](../../releases/tag/baseline-v1-complete)

---

## Status

**Staging. Not production.** No paying users, no production deployment, no uptime claims.

| Component | State |
|---|---|
| Monitor agent (polls Jira for stale work, 5-min interval) | Live |
| Communicator agent (Slack notifications) | Live |
| Spec Interpreter agent (PRD → structured tasks, LLM-backed) | Live, and evaluated |
| Approval dashboard (human-in-the-loop) | Live |
| Three further agents described in early designs | **Not built** |

---

## What the evaluation found

The Spec Interpreter is the only LLM component in the system. It takes a PRD and emits JSON: a task list with summaries, descriptions, issue types, priorities, Fibonacci story points, acceptance criteria, and dependency indices.

Twenty PRDs across six difficulty tiers — clean, ambiguous, contradictory, incomplete, large, and edge cases — run three times each. 60 runs, 445 tasks generated, zero parse or quota errors.

**Headline numbers, frozen at `baseline-v1-complete`:**

| Metric | Result |
|---|---|
| Runs completed / attempted | 60 / 60 |
| Content-level stability (mean Jaccard, empty input excluded) | **0.433** |
| PRDs with stable task counts across 3 identical runs | 15 / 20 |
| PRDs with stable dependency graphs across 3 identical runs | **6 / 20** |
| Dependency violations (all self-references) | 6 / 445 tasks (1.3%) |
| Gold-aware over-refusals | 3 |

**Three findings worth your time:**

**1. Instability is structural, not cosmetic.** The same PRD, byte-identical, run three times, does not just get reworded — it gets reorganised. PRD05, one of the *clean* specs, scored 0.081 Jaccard, with tasks merging and splitting between runs. Its dependency graph came out as a branched tree, then a hub-and-spoke, then a linear chain. Same input, three different shapes.

**2. Estimate volatility is its own failure axis.** PRD05's sprint point totals across three runs were 15, 19, and 16 — roughly a 27% spread on identical input. On PRD20, run 1 differed on 3 of 6 estimates while the task summaries were byte-identical to run 2. Lexical stability, structural stability, estimate stability, and instruction adherence move independently. Measuring one tells you little about the others.

**3. Refusal is miscalibrated in both directions.** Empty input was correctly refused. A legitimate spec carrying a prompt-injection string was refused three times out of three — a false positive on real work. And a banana bread recipe, submitted as a PRD, produced nine confident, well-formed engineering tickets, three times out of three. The system is more willing to fabricate from plausible-looking nonsense than to process a legitimate document that looks suspicious.

Full method, threats to validity, and ten findings: [`eval/baseline_report.md`](eval/baseline_report.md).

---

## How the evaluation was run

The methodology is the point, so it is stated plainly:

- **Scoring policy written and locked before any runs**, in [`eval/scoring_policy.md`](eval/scoring_policy.md). Violation codes for schema (S1–S8), dependencies (D1–D4), and stability (T1–T3).
- **Two metrics reported together, never separately.** Strict schema compliance measures instruction-following against the prompt's own verb whitelist; relaxed compliance accepts any ordinary engineering imperative. Strict shows 84 violations, relaxed shows 22. Reporting only one would be misleading, so both appear everywhere.
- **Frozen baseline.** Tagged at a specific commit and never modified. Improvements will be measured as new tagged versions against this one, one variable at a time.
- **Failed batches are quarantined, not deleted.** Two bad runs live in `eval/archive/` with notes explaining why they were excluded. Neither was scored.
- **Raw outputs are kept verbatim.** Every run directory is timestamped and never overwritten; `eval/manifest.json` is the single source of truth.

Known limitation, stated up front: hallucination detection here was incidental. The banana-bread fabrication was caught because the domain was obviously wrong. A plausible-sounding but invented *software* task would not have been detected by this harness. A gold-aware content check is the next piece of work, not a solved problem.

---

## Architecture

```
PRD ──► Spec Interpreter ──► structured tasks ──┐
                                                 ├──► Approval dashboard ──► Jira
Jira ──► Monitor ──► stale-work alerts ──────────┘
                          │
                          └──► Communicator ──► Slack
```

- **Backend:** FastAPI, PostgreSQL, Alembic migrations
- **Agents:** Microsoft AutoGen
- **Auth:** two-tier API key, rate limiting; approval dashboard behind Basic Auth
- **Alerting:** explicit state machine, no fire-and-forget notifications
- **Tests:** pytest suite
- **Deploy:** Docker

Nothing writes to Jira without a human clicking approve. That is a design constraint, not a setting.

---

## Quickstart

```bash
git clone https://github.com/kinghardesh/AEGIS-PM.git
cd AEGIS-PM
cp .env.example .env        # fill in Jira, Slack, and LLM provider keys
docker compose up
```

To reproduce the evaluation without touching Jira:

```bash
python -m eval.run_baseline --dry-run
python eval/check_parse.py eval/runs/<timestamp>/
```

`--dry-run` parses only and writes nothing to Jira. All 60 baseline runs were produced this way.

---

## Known issues

Listed because a repo that hides these is worse than one that has them:

- Unnormalised log-level environment variable can crash the service on boot (`ValueError: Unknown level`)
- Incomplete refactor leaves a stale import (`poll_stale_tasks`)
- Dependency inference is untested. The one deep-dependency fixture states every edge in prose, so it demonstrates transcription, not inference. A proper fixture is planned.

---

## Credits

- Backend, agents, and the evaluation study — Rahul ([@kinghardesh](https://github.com/kinghardesh))
- Web frontend — Prithvi Singh Tomar ([@prithvi471](https://github.com/prithvi471))

Implementation was substantially AI-assisted. Study design, methodology, failure diagnosis, and validation of every reported number are the author's own; all results were verified against raw run artifacts.

## License

See [LICENSE](LICENSE).
