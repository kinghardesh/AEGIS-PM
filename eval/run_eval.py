#!/usr/bin/env python3
"""
Aegis PM — Spec Interpreter evaluation orchestrator (baseline-frozen edition).

Batch driver that automates generation + scoring over the whole 20-PRD set.

WHAT CHANGED FOR THE FROZEN BASELINE
────────────────────────────────────
  * Runs are NEVER written flat into eval/runs/ anymore. Every `generate`
    creates its own immutable, timestamped batch directory:
        eval/runs/2026-07-04_0915/prd01_clean_auth_run1.json
    so a later (e.g. quota-limited) re-run can never overwrite an earlier one.
  * Scoring is gold-aware. On top of the frozen strict rubric in check_parse.py
    it adds (see eval/scoring_policy.py + eval/scoring_policy.md):
        - E1          gold-aware over-refusal (empty output, gold expects tasks)
        - relaxed S5  PRIMARY summary-verb metric (strict S5 kept as secondary)
  * A single source of truth, eval/manifest.json, records the canonical batch,
    archives, provider/model, git commit/tag, settings and totals.

The single-PRD reference checker `check_parse.py` is unchanged and still the
canonical strict rubric; this script imports its functions so the two never drift.

Usage
─────
  # Generate a NEW timestamped batch (all 20 PRDs, 3 runs) then score it:
  python eval/run_eval.py --runs 3

  # Recover only the missing runs into a new batch (no overwrite of good runs):
  python eval/run_eval.py --generate --runs 3 --only prd19_edge_nonprd prd20_edge_deep_deps

  # Score an existing batch directory (offline, free):
  python eval/run_eval.py --check --batch 2026-07-03_partial

  # Score whatever manifest.json marks as the canonical baseline (offline):
  python eval/run_eval.py --check
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# Windows terminals default to cp1252 and choke on the box-drawing chars we
# print. Force UTF-8 on stdout/stderr so the report renders everywhere.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass

# Reuse the canonical (frozen) strict rubric — never reimplement it.
from check_parse import check_run, check_stability  # noqa: E402
from scoring_policy import gold_expected, score_run_gold_aware  # noqa: E402

EVAL_DIR = Path(__file__).resolve().parent
PRD_DIR = EVAL_DIR / "prds"
RUN_DIR = EVAL_DIR / "runs"
GOLD_DIR = EVAL_DIR / "gold"
MANIFEST = EVAL_DIR / "manifest.json"
REPO_ROOT = EVAL_DIR.parent

SCHEMA_CODES = {"S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8"}
DEP_CODES = {"D1", "D2", "D3", "D4"}


def discover_prds(only: list[str] | None) -> list[Path]:
    prds = sorted(PRD_DIR.glob("*.md"))
    if only:
        wanted = set(only)
        prds = [p for p in prds if p.stem in wanted]
    return prds


def prd_id(prd_path: Path) -> str:
    return prd_path.stem


def live_source_label() -> str:
    """Provider+model label derived from the LLM_* env config (never hardcoded)."""
    base_url = os.getenv("LLM_BASE_URL", "https://api.groq.com/openai/v1")
    model = os.getenv("LLM_MODEL", "llama-3.3-70b-versatile")
    host = base_url.split("//", 1)[-1].split("/", 1)[0].lower()
    if "groq" in host:
        provider = "groq"
    elif "openai" in host:
        provider = "openai"
    else:
        provider = host.split(".")[0] or "custom"
    return f"live-{provider}-{model}"


# ── Generation into a NEW timestamped batch dir ───────────────────────────────

def new_batch_dir(label: str | None) -> Path:
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M")
    name = f"{stamp}_{label}" if label else stamp
    d = RUN_DIR / name
    # Never overwrite: if the stamp collides, suffix with seconds.
    if d.exists():
        d = RUN_DIR / f"{name}_{datetime.now().strftime('%S')}"
    d.mkdir(parents=True, exist_ok=False)
    return d


def generate_runs(prds: list[Path], n_runs: int, mock: bool, batch_dir: Path) -> None:
    source = "mock" if mock else live_source_label()
    (batch_dir / "_manifest.json").write_text(
        json.dumps({"source": source, "runs_per_prd": n_runs,
                    "generated_at": datetime.now().isoformat(timespec="seconds"),
                    "prds": [prd_id(p) for p in prds]}, indent=2),
        encoding="utf-8")
    for prd in prds:
        pid = prd_id(prd)
        for k in range(1, n_runs + 1):
            out = batch_dir / f"{pid}_run{k}.json"
            print(f"  → {pid} run {k}/{n_runs}  ...", end="", flush=True)
            try:
                if mock:
                    from _mock_parser import mock_parse
                    out.write_text(mock_parse(prd, seed=k), encoding="utf-8")
                else:
                    child_env = os.environ.copy()
                    shim = str(EVAL_DIR / "_shims")
                    child_env["PYTHONPATH"] = (
                        shim + os.pathsep + child_env.get("PYTHONPATH", "")
                    ).rstrip(os.pathsep)
                    subprocess.run(
                        [sys.executable, "-m", "agents.spec_interpreter",
                         "--file", str(prd), "--dry-run", "--out", str(out)],
                        cwd=str(REPO_ROOT), env=child_env,
                        check=True, capture_output=True, text=True,
                    )
                print(" ok")
            except subprocess.CalledProcessError as exc:
                print(" FAILED")
                out.write_text(json.dumps(
                    {"error": f"parser exited {exc.returncode}: "
                              f"{(exc.stderr or '')[-400:]}", "tasks": []}),
                    encoding="utf-8")
            except Exception as exc:  # noqa: BLE001
                print(f" FAILED ({exc})")
                out.write_text(json.dumps({"error": str(exc), "tasks": []}),
                               encoding="utf-8")


# ── Scoring a batch directory (gold-aware) ────────────────────────────────────

def _batch_source(batch_dir: Path) -> str:
    m = batch_dir / "_manifest.json"
    if m.exists():
        try:
            return json.loads(m.read_text(encoding="utf-8")).get("source", "unknown")
        except json.JSONDecodeError:
            pass
    return "unknown"


def score_dir(batch_dir: Path, n_runs: int) -> dict:
    per_prd: dict[str, dict] = {}
    agg_freq: dict[str, int] = {}
    total_runs = total_tasks = clean_runs = 0
    strict_s5_total = relaxed_s5_total = e1_total = 0
    jaccards: list[float] = []
    count_stable_prds = dep_stable_prds = graded_prds = 0

    prds = sorted(PRD_DIR.glob("*.md"))
    for prd in prds:
        pid = prd_id(prd)
        run_files = sorted(batch_dir.glob(f"{pid}_run*.json"))
        if not run_files:
            continue
        expected = gold_expected(pid, GOLD_DIR)

        run_reports = []
        run_datas = []
        prd_e1 = prd_strict = prd_relaxed = 0
        for rf in run_files:
            try:
                data = json.loads(rf.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                data = {"error": f"unreadable: {exc}", "tasks": []}
            run_datas.append(data)
            rep = check_run(data, rf.name)
            gold_rep = score_run_gold_aware(data, rep, expected)
            rep["e1"] = gold_rep["e1"]
            rep["strict_s5"] = gold_rep["strict_s5"]
            rep["relaxed_s5"] = gold_rep["relaxed_s5"]
            run_reports.append(rep)

            total_runs += 1
            total_tasks += rep["n_tasks"]
            if not rep["violations"]:
                clean_runs += 1
            for v in rep["violations"]:
                agg_freq[v["code"]] = agg_freq.get(v["code"], 0) + 1
            if gold_rep["e1"]:
                agg_freq["E1"] = agg_freq.get("E1", 0) + 1
                e1_total += 1
                prd_e1 += 1
            strict_s5_total += gold_rep["strict_s5"]
            relaxed_s5_total += gold_rep["relaxed_s5"]
            prd_strict += gold_rep["strict_s5"]
            prd_relaxed += gold_rep["relaxed_s5"]

        stability = check_stability(run_datas) if len(run_datas) >= 2 else None
        if stability:
            graded_prds += 1
            jaccards.append(stability["mean_jaccard"])
            count_stable_prds += int(stability["count_stable"])
            dep_stable_prds += int(stability["dep_structure_stable"])

        schema_v = sum(1 for r in run_reports for v in r["violations"]
                       if v["code"] in SCHEMA_CODES)
        dep_v = sum(1 for r in run_reports for v in r["violations"]
                    if v["code"] in DEP_CODES)

        per_prd[pid] = {
            "category": _gold_field(pid, "category"),
            "gold_expected": expected,
            "n_runs": len(run_reports),
            "task_counts": [r["n_tasks"] for r in run_reports],
            "schema_violations": schema_v,
            "dep_violations": dep_v,
            "e1_violations": prd_e1,
            "strict_s5": prd_strict,
            "relaxed_s5": prd_relaxed,
            "runs": run_reports,
            "stability": stability,
        }

    aggregate = {
        "total_prds": len(per_prd),
        "total_runs": total_runs,
        "total_tasks": total_tasks,
        "clean_runs": clean_runs,
        "violation_frequency": dict(sorted(agg_freq.items())),
        "schema_violations": sum(v for k, v in agg_freq.items() if k in SCHEMA_CODES),
        "dep_violations": sum(v for k, v in agg_freq.items() if k in DEP_CODES),
        "parse_errors": agg_freq.get("E0", 0),
        "e1_over_refusals": e1_total,
        "strict_s5_total": strict_s5_total,
        "relaxed_s5_total": relaxed_s5_total,
        "mean_jaccard_overall": round(sum(jaccards) / len(jaccards), 3) if jaccards else None,
        "count_stable_prds": count_stable_prds,
        "dep_stable_prds": dep_stable_prds,
        "graded_prds": graded_prds,
    }
    return {"config": {"runs_per_prd": n_runs, "source": _batch_source(batch_dir),
                       "batch": batch_dir.name},
            "per_prd": per_prd, "aggregate": aggregate}


def _gold_field(pid: str, field: str):
    gp = GOLD_DIR / f"{pid}.gold.json"
    if gp.exists():
        try:
            return json.loads(gp.read_text(encoding="utf-8")).get(field)
        except json.JSONDecodeError:
            return None
    return None


def canonical_batch_dir() -> Path | None:
    """Resolve the canonical baseline batch dir from manifest.json."""
    if MANIFEST.exists():
        try:
            m = json.loads(MANIFEST.read_text(encoding="utf-8"))
            p = m.get("canonical_baseline_path")
            if p:
                cand = (REPO_ROOT / p)
                if cand.exists():
                    return cand
        except json.JSONDecodeError:
            pass
    return None


# ── Reporting ─────────────────────────────────────────────────────────────────

def print_summary(results: dict) -> None:
    agg = results["aggregate"]
    print("\n" + "═" * 68)
    print("  SPEC INTERPRETER — BATCH EVAL SUMMARY")
    print("═" * 68)
    print(f"  Run source:            {results['config'].get('source', 'unknown')}")
    print(f"  Batch:                 {results['config'].get('batch', '?')}")
    print(f"  PRDs evaluated:        {agg['total_prds']}")
    print(f"  Total runs checked:    {agg['total_runs']}")
    print(f"  Total tasks generated: {agg['total_tasks']}")
    print(f"  Fully-clean runs:      {agg['clean_runs']}/{agg['total_runs']}")
    print(f"  Schema violations:     {agg['schema_violations']}")
    print(f"  Dependency violations: {agg['dep_violations']}")
    print(f"  Parse errors (E0):     {agg['parse_errors']}")
    print(f"  Over-refusals (E1):    {agg['e1_over_refusals']}")
    print(f"  S5 strict / relaxed:   {agg['strict_s5_total']} / {agg['relaxed_s5_total']}")
    print(f"  Mean Jaccard (all PRDs): {agg['mean_jaccard_overall']}")
    print(f"  Count-stable PRDs:     {agg['count_stable_prds']}/{agg['graded_prds']}")
    print(f"  Dep-stable PRDs:       {agg['dep_stable_prds']}/{agg['graded_prds']}")
    if agg["violation_frequency"]:
        print("\n  Violation frequency (all runs):")
        for code, cnt in agg["violation_frequency"].items():
            print(f"    {code}: {cnt}")

    print("\n  Per-PRD stability:")
    print(f"    {'PRD':<28} {'cat':<14} {'counts':<14} {'Jaccard':<8} deps")
    for pid, d in results["per_prd"].items():
        st = d["stability"] or {}
        counts = ",".join(map(str, d["task_counts"]))
        jac = st.get("mean_jaccard", "-")
        deps = ("stable" if st.get("dep_structure_stable") else "DIFFERS") if st else "-"
        print(f"    {pid:<28} {str(d['category']):<14} {counts:<14} {str(jac):<8} {deps}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Aegis PM Spec Interpreter batch eval")
    ap.add_argument("--runs", type=int, default=3, help="runs per PRD (default 3)")
    ap.add_argument("--only", nargs="*", help="restrict to these PRD stems")
    ap.add_argument("--generate", action="store_true", help="only generate runs")
    ap.add_argument("--check", action="store_true", help="only check existing runs")
    ap.add_argument("--mock", action="store_true",
                    help="use the offline mock parser instead of the live LLM")
    ap.add_argument("--batch", help="batch dir name under eval/runs/ to score "
                                    "(default: manifest canonical)")
    ap.add_argument("--label", help="suffix label for a newly generated batch dir")
    args = ap.parse_args()

    do_generate = args.generate or not args.check
    do_check = args.check or not args.generate

    prds = discover_prds(args.only)
    if not prds:
        print(f"No PRDs found in {PRD_DIR} (matching {args.only})")
        sys.exit(1)

    batch_dir: Path | None = None
    if do_generate:
        batch_dir = new_batch_dir(args.label)
        mode = "MOCK" if args.mock else f"LIVE {live_source_label()}"
        print(f"Generating {args.runs} run(s) each for {len(prds)} PRD(s) — {mode}")
        print(f"Batch directory: {batch_dir}")
        generate_runs(prds, args.runs, args.mock, batch_dir)

    if do_check:
        if args.batch:
            score_target = RUN_DIR / args.batch
        elif batch_dir is not None:
            score_target = batch_dir
        else:
            score_target = canonical_batch_dir()
        if not score_target or not score_target.exists():
            print("No batch to score (use --batch NAME or set manifest canonical).")
            sys.exit(1)
        results = score_dir(score_target, args.runs)
        out = EVAL_DIR / "check_results.json"
        out.write_text(json.dumps(results, indent=2), encoding="utf-8")
        print_summary(results)
        print(f"\n  Aggregate results written to {out}")


if __name__ == "__main__":
    main()
