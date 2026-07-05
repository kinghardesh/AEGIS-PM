#!/usr/bin/env python3
"""
Aegis PM — Spec Interpreter output checker (automated half of the eval rubric).

Validates the JSON produced by:
    python -m agents.spec_interpreter --file prd.md --dry-run  (captured as JSON)
or the raw string returned by parse_specification().

Checks (all pure code, no LLM, no API keys):

  SCHEMA
    S1  issue_type in {Story, Task, Bug, Subtask}
    S2  priority in {Highest, High, Medium, Low, Lowest}
    S3  story_points in {1, 2, 3, 5, 8, 13}
    S4  summary <= 80 chars (the prompt's own rule; code only enforces 255)
    S5  summary starts with an approved verb
    S6  labels are lowercase strings
    S7  acceptance_criteria is a non-empty list
    S8  total_tasks matches len(tasks)

  DEPENDENCIES
    D1  depends_on_index is null or an int within range [0, n_tasks)
    D2  no task depends on itself
    D3  no dependency cycles (A -> B -> A, etc.)
    D4  dependencies point backwards (a task only depends on an earlier index)
        — soft check: the system prompt says "create tasks in order so
        dependencies are created first", which only works if deps precede.

  STABILITY (when given multiple runs of the SAME PRD)
    T1  task count identical across runs
    T2  Jaccard similarity of normalized summaries across runs
    T3  dependency structure identical across runs

Usage:
    # Single run
    python check_parse.py run1.json

    # Multiple runs of the same PRD -> also computes stability
    python check_parse.py run1.json run2.json run3.json

    # Whole directory (each file = one run of one PRD; stability skipped)
    python check_parse.py results/*.json

Output: human-readable report to stdout + machine-readable summary to
        check_results.json (per-file violation counts, pass rates).
"""
from __future__ import annotations

import json
import re
import sys
from itertools import combinations
from pathlib import Path

# Windows consoles default to cp1252 and cannot encode the box-drawing / ✓✗
# characters used in the report; force UTF-8 so the checker runs everywhere.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass

# ── Rubric constants (mirror the prompt in spec_interpreter.py) ──────────────

VALID_ISSUE_TYPES = {"Story", "Task", "Bug", "Subtask"}
VALID_PRIORITIES = {"Highest", "High", "Medium", "Low", "Lowest"}
VALID_STORY_POINTS = {1, 2, 3, 5, 8, 13}
SUMMARY_MAX_CHARS = 80
APPROVED_VERBS = {
    "implement", "add", "fix", "create", "migrate", "write",
    # common reasonable extras the model tends to use — counted separately
}
STRICT_VERBS = {"implement", "add", "fix", "create", "migrate", "write"}


# ── Single-run checks ─────────────────────────────────────────────────────────

def check_run(data: dict, source: str) -> dict:
    """Validate one parse output. Returns a violations report dict."""
    violations: list[dict] = []

    def flag(code: str, task_idx, detail: str):
        violations.append({"code": code, "task": task_idx, "detail": detail})

    if "error" in data and not data.get("tasks"):
        flag("E0", None, f"parse returned error: {data['error']!r}")
        return {"source": source, "n_tasks": 0, "violations": violations}

    tasks = data.get("tasks", [])
    n = len(tasks)

    # S8 — count consistency
    declared = data.get("total_tasks")
    if declared is not None and declared != n:
        flag("S8", None, f"total_tasks={declared} but len(tasks)={n}")

    for i, t in enumerate(tasks):
        summary = t.get("summary", "") or ""

        it = t.get("issue_type")
        if it not in VALID_ISSUE_TYPES:
            flag("S1", i, f"issue_type={it!r}")

        pr = t.get("priority")
        if pr not in VALID_PRIORITIES:
            flag("S2", i, f"priority={pr!r}")

        sp = t.get("story_points")
        if sp not in VALID_STORY_POINTS:
            flag("S3", i, f"story_points={sp!r} (not Fibonacci)")

        if len(summary) > SUMMARY_MAX_CHARS:
            flag("S4", i, f"summary is {len(summary)} chars (>{SUMMARY_MAX_CHARS})")

        first_word = summary.split()[0].lower() if summary.split() else ""
        if first_word not in STRICT_VERBS:
            flag("S5", i, f"summary starts with {first_word!r}, not an approved verb")

        labels = t.get("labels", [])
        if not isinstance(labels, list) or any(
            not isinstance(l, str) or l != l.lower() for l in labels
        ):
            flag("S6", i, f"labels not all lowercase strings: {labels!r}")

        ac = t.get("acceptance_criteria", [])
        if not isinstance(ac, list) or len(ac) == 0:
            flag("S7", i, "acceptance_criteria missing or empty")

        # D1 / D2 — range and self-reference
        dep = t.get("depends_on_index", None)
        if dep is not None:
            if not isinstance(dep, int) or dep < 0 or dep >= n:
                flag("D1", i, f"depends_on_index={dep!r} out of range [0,{n})")
            elif dep == i:
                flag("D2", i, "task depends on itself")
            elif dep > i:
                flag("D4", i, f"depends on LATER task {dep} (creation order breaks)")

    # D3 — cycle detection over the dependency graph
    graph = {}
    for i, t in enumerate(tasks):
        dep = t.get("depends_on_index", None)
        if isinstance(dep, int) and 0 <= dep < n and dep != i:
            graph[i] = dep

    def has_cycle() -> list[int] | None:
        for start in graph:
            seen = [start]
            cur = start
            while cur in graph:
                cur = graph[cur]
                if cur in seen:
                    return seen + [cur]
                seen.append(cur)
        return None

    cyc = has_cycle()
    if cyc:
        flag("D3", cyc[0], f"dependency cycle: {' -> '.join(map(str, cyc))}")

    return {"source": source, "n_tasks": n, "violations": violations}


# ── Stability checks across runs of the same PRD ─────────────────────────────

def normalize_summary(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", s.lower()).strip()


def check_stability(runs: list[dict]) -> dict:
    counts = [len(r.get("tasks", [])) for r in runs]
    report = {
        "n_runs": len(runs),
        "task_counts": counts,
        "count_stable": len(set(counts)) == 1,       # T1
        "pairwise_jaccard": [],
        "dep_structure_stable": True,                 # T3
    }

    def summary_set(r):
        return {normalize_summary(t.get("summary", "")) for t in r.get("tasks", [])}

    def dep_edges(r):
        return {
            (i, t.get("depends_on_index"))
            for i, t in enumerate(r.get("tasks", []))
            if t.get("depends_on_index") is not None
        }

    for (a_idx, a), (b_idx, b) in combinations(enumerate(runs), 2):
        sa, sb = summary_set(a), summary_set(b)
        union = sa | sb
        jac = (len(sa & sb) / len(union)) if union else 1.0
        report["pairwise_jaccard"].append(
            {"runs": [a_idx, b_idx], "jaccard": round(jac, 3)}
        )
        if dep_edges(a) != dep_edges(b):
            report["dep_structure_stable"] = False

    jacs = [p["jaccard"] for p in report["pairwise_jaccard"]]
    report["mean_jaccard"] = round(sum(jacs) / len(jacs), 3) if jacs else 1.0
    return report


# ── Main ──────────────────────────────────────────────────────────────────────

def load(path: str) -> dict:
    raw = Path(path).read_text(encoding="utf-8")
    return json.loads(raw)


def main(paths: list[str]) -> None:
    if not paths:
        print(__doc__)
        sys.exit(1)

    reports = []
    runs = []
    for p in paths:
        try:
            data = load(p)
        except (OSError, json.JSONDecodeError) as exc:
            print(f"✗ {p}: cannot load ({exc})")
            continue
        runs.append(data)
        reports.append(check_run(data, p))

    total_tasks = sum(r["n_tasks"] for r in reports)
    total_viol = sum(len(r["violations"]) for r in reports)

    print("═" * 64)
    print("  SPEC INTERPRETER — AUTOMATED CHECK REPORT")
    print("═" * 64)
    for r in reports:
        status = "PASS" if not r["violations"] else f'{len(r["violations"])} violation(s)'
        print(f"\n  {r['source']}  —  {r['n_tasks']} tasks  —  {status}")
        for v in r["violations"]:
            loc = f"task[{v['task']}]" if v["task"] is not None else "run"
            print(f"    [{v['code']}] {loc}: {v['detail']}")

    # Violation frequency table — this becomes a table in your report
    freq: dict[str, int] = {}
    for r in reports:
        for v in r["violations"]:
            freq[v["code"]] = freq.get(v["code"], 0) + 1
    if freq:
        print("\n  Violation frequency:")
        for code in sorted(freq):
            print(f"    {code}: {freq[code]}")

    clean_runs = sum(1 for r in reports if not r["violations"])
    print(f"\n  Runs fully clean: {clean_runs}/{len(reports)}")
    print(f"  Total tasks checked: {total_tasks}, total violations: {total_viol}")

    summary: dict = {"runs": reports, "violation_frequency": freq,
                     "clean_runs": clean_runs, "total_runs": len(reports)}

    if len(runs) >= 2:
        stab = check_stability(runs)
        summary["stability"] = stab
        print("\n  STABILITY (treating all inputs as runs of the SAME PRD):")
        print(f"    task counts across runs: {stab['task_counts']}"
              f"  {'✓ stable' if stab['count_stable'] else '✗ UNSTABLE'}")
        print(f"    mean summary Jaccard:    {stab['mean_jaccard']}"
              f"  (1.0 = identical wording)")
        print(f"    dependency structure:    "
              f"{'✓ identical' if stab['dep_structure_stable'] else '✗ DIFFERS between runs'}")

    out = Path("check_results.json")
    out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"\n  Machine-readable summary written to {out.resolve()}")


if __name__ == "__main__":
    main(sys.argv[1:])
