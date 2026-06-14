"""
aegis-pm / agents / executors / code_writer.py

CodeWriterExecutor – picks up Jira tasks labelled `aegis:code` and writes
the code implementation, posting it back as a Jira comment.

Workflow
────────
  1. Search Jira for `aegis:code` tasks in status "To Do"
  2. For each:
       - transition → In Progress
       - LLM generates a complete, runnable implementation
         (file tree + code blocks) based on the task summary + description
       - post as a Jira comment
       - transition → In Review (or label `aegis:done`)
"""
from __future__ import annotations

from agents.executors.base import BaseExecutor


class CodeWriterExecutor(BaseExecutor):
    AGENT_LABEL        = "aegis:code"
    AGENT_NAME         = "code_writer"
    DELIVERABLE_HEADER = "## Implementation"

    SYSTEM_PROMPT = """You are the Code Writer agent for Aegis PM – an autonomous
software engineering team member.

Your job: given a Jira task that describes a feature or change, produce a
complete, runnable implementation.

Output format (markdown):

1. One-sentence summary of the approach.
2. `### File tree` section: a bullet list of the files you are creating or
   modifying, with a short purpose for each.
3. `### Code` section: one fenced code block per file. Each block must start
   with a comment giving the file path, e.g.:

       ```python
       # path: app/services/billing.py
       ...
       ```

   Use the correct language tag in the fence (`python`, `typescript`, `sql`…).
4. `### Notes` section (optional): migrations, env vars, or follow-up steps
   the reviewer should know about.

Rules:
- Prefer editing existing patterns over introducing new abstractions.
- Include imports, type hints, and docstrings where appropriate.
- Do NOT include scaffolding/explanation that is already obvious from the code.
- If the task is ambiguous, pick the most reasonable interpretation and state
  your assumption at the top.
- Your final message MUST end with the word TERMINATE on its own line."""
