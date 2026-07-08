#!/usr/bin/env python3
"""
Offline MOCK parser for the eval pipeline self-test.

This is NOT the real Spec Interpreter. It fabricates parser-shaped JSON so that
run_eval.py + check_parse.py can be exercised end-to-end with **no OpenAI API
call and no env vars**. It deliberately reproduces the kinds of nondeterminism
and schema/dependency defects a real LLM parser exhibits, driven by the PRD's
filename category, so the checker and stability metrics have something to catch.

Any check_results.json / report produced with `--mock` describes THIS mock, not
gpt-4o. It exists only to prove the harness is correct and reproducible.

Determinism: output is a pure function of (prd content, seed). No wall-clock, no
RNG module — we hash (content + seed) so results are byte-reproducible.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

FIB = [1, 2, 3, 5, 8, 13]
VERBS = ["Implement", "Add", "Create", "Write", "Migrate", "Fix"]


def _rng_stream(content: str, seed: int):
    """Deterministic pseudo-random byte stream from (content, seed)."""
    i = 0
    while True:
        h = hashlib.sha256(f"{seed}:{i}:{content}".encode("utf-8")).digest()
        for b in h:
            yield b
        i += 1


def _base_tasks(pid: str, n: int, rng) -> list[dict]:
    tasks = []
    for j in range(n):
        verb = VERBS[next(rng) % len(VERBS)]
        tasks.append({
            "summary": f"{verb} {pid} component {j + 1}",
            "description": f"Auto-generated mock task {j + 1} for {pid}. Provides context.",
            "issue_type": ["Story", "Task", "Bug"][next(rng) % 3],
            "priority": ["Highest", "High", "Medium", "Low"][next(rng) % 4],
            "story_points": FIB[next(rng) % len(FIB)],
            "acceptance_criteria": [f"Given input, when action {j + 1}, then result"],
            "labels": ["backend", "mock"],
            "depends_on_index": (j - 1) if j > 0 and next(rng) % 3 == 0 else None,
        })
    return tasks


def mock_parse(prd_path: Path, seed: int = 1) -> str:
    content = Path(prd_path).read_text(encoding="utf-8")
    pid = Path(prd_path).stem
    rng = _rng_stream(content, seed)
    words = len(content.split())

    # Empty / off-topic inputs → graceful low/zero output (as a good parser should).
    if "edge_empty" in pid or words < 3:
        return json.dumps({"project_title": pid, "total_tasks": 0, "tasks": []})
    if "edge_nonprd" in pid:
        # A weaker parser sometimes hallucinates a task or two from off-topic text.
        n = next(rng) % 2  # 0 or 1
        tasks = _base_tasks(pid, n, rng)
        return json.dumps({"project_title": pid, "total_tasks": len(tasks), "tasks": tasks})

    # Base size scales with PRD length; +/- jitter per seed → count instability.
    base = max(3, min(20, words // 45))
    jitter = (next(rng) % 3) - 1  # -1, 0, +1
    if "large" in pid:
        base += 8 + (next(rng) % 4)
    if "ambiguous" in pid or "incomplete" in pid:
        jitter += (next(rng) % 3) - 1  # noisier → lower Jaccard, less count-stable
    n = max(1, base + jitter)

    tasks = _base_tasks(pid, n, rng)

    # Inject category-specific DEFECTS so the checker has real violations to find.
    if "contradictory" in pid and tasks:
        # Model silently emits an over-long, non-verb summary trying to reconcile.
        tasks[0]["summary"] = (
            "Reconcile the conflicting authentication requirements described in "
            "both sections of the specification without asking for clarification"
        )  # >80 chars (S4) and starts with 'Reconcile' (S5, not approved)
    if "edge_injection" in pid and tasks:
        tasks[0]["labels"] = ["Backend", "Security"]  # uppercase → S6
    if "incomplete" in pid and tasks:
        tasks[-1]["story_points"] = 4  # non-Fibonacci → S3
    if "edge_deep_deps" in pid:
        # Occasionally a forward/self dependency slips in (D4/D2).
        if next(rng) % 2 == 0 and len(tasks) > 2:
            tasks[1]["depends_on_index"] = len(tasks) - 1  # forward ref → D4

    data = {"project_title": pid.replace("_", " ").title(),
            "total_tasks": len(tasks), "tasks": tasks}
    return json.dumps(data)
