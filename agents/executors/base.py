"""
aegis-pm / agents / executors / base.py

Shared infrastructure for all six executor agents.

Provides
────────
  JiraExecClient      Synchronous Jira REST v3 client scoped to executor work:
                        - search tasks by label + status
                        - transition issue status (by name)
                        - add a comment (Atlassian Document Format)
                        - add a label
                        - read attachments / description text
  BaseExecutor        Abstract base class for all executor agents.
                      Implements the common work loop:
                        1. fetch tasks by label in "To Do"
                        2. transition → "In Progress"
                        3. subclass.produce_deliverable(task) → markdown body
                        4. add comment on the Jira issue
                        5. transition → "In Review" (or label 'aegis:done')
                      Subclasses only override:
                        - AGENT_LABEL         e.g. "aegis:code"
                        - AGENT_NAME          e.g. "code_writer"
                        - SYSTEM_PROMPT       LLM system message
                        - DELIVERABLE_HEADER  header line for the Jira comment
"""
from __future__ import annotations

import json
import logging
import os
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx
from autogen import AssistantAgent, UserProxyAgent
from dotenv import load_dotenv
from tenacity import (
    RetryError,
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

load_dotenv()

log = logging.getLogger("aegis.executor")


# ── Config ────────────────────────────────────────────────────────────────────

JIRA_BASE_URL  = os.environ.get("JIRA_BASE_URL", "").rstrip("/")
JIRA_EMAIL     = os.environ.get("JIRA_EMAIL", "")
JIRA_API_TOKEN = os.environ.get("JIRA_API_TOKEN", "")
JIRA_PROJECT   = os.environ.get("JIRA_PROJECT_KEY", "")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")

EXEC_MAX_TASKS_PER_CYCLE = int(os.getenv("EXEC_MAX_TASKS_PER_CYCLE", "5"))
EXEC_TODO_STATUS         = os.getenv("EXEC_TODO_STATUS",    "To Do")
EXEC_INPROGRESS_STATUS   = os.getenv("EXEC_INPROGRESS_STATUS", "In Progress")
EXEC_DONE_STATUS         = os.getenv("EXEC_DONE_STATUS",   "In Review")
EXEC_DONE_LABEL          = os.getenv("EXEC_DONE_LABEL",    "aegis:done")

# Single shared AutoGen LLM config – mirrors what monitor/communicator use.
# Falls back gracefully between Groq/OpenAI depending on which key is present.
_OPENAI_MODEL = os.getenv("OPENAI_MODEL", "llama-3.3-70b-versatile")
_GROQ_KEY     = os.getenv("GROQ_API_KEY", "")

if _GROQ_KEY:
    EXEC_LLM_CONFIG: Dict[str, Any] = {
        "config_list": [{
            "model":    _OPENAI_MODEL,
            "api_key":  _GROQ_KEY,
            "base_url": "https://api.groq.com/openai/v1",
            "price":    [0.00059, 0.00079],
        }],
        "temperature": 0.2,
        "timeout":     180,
        "cache_seed":  None,
    }
else:
    EXEC_LLM_CONFIG = {
        "config_list": [{
            "model":   _OPENAI_MODEL if _OPENAI_MODEL.startswith("gpt") else "gpt-4o-mini",
            "api_key": OPENAI_API_KEY,
        }],
        "temperature": 0.2,
        "timeout":     180,
        "cache_seed":  None,
    }


# ══════════════════════════════════════════════════════════════════════════════
#  Jira client (sync, since executors run on APScheduler thread pool)
# ══════════════════════════════════════════════════════════════════════════════

_JIRA_RETRYABLE = (httpx.TimeoutException, httpx.ConnectError, httpx.RemoteProtocolError)


class JiraExecClient:
    """Minimal synchronous Jira REST v3 client for executor workflow."""

    def __init__(self) -> None:
        self._auth = (JIRA_EMAIL, JIRA_API_TOKEN)
        self._base = JIRA_BASE_URL

    # ── Search ────────────────────────────────────────────────────────────────

    @retry(
        retry=retry_if_exception_type(_JIRA_RETRYABLE),
        stop=stop_after_attempt(3),
        wait=wait_exponential(min=2, max=8),
        before_sleep=before_sleep_log(log, logging.WARNING),
        reraise=True,
    )
    def search_by_label(
        self,
        label: str,
        status: str = EXEC_TODO_STATUS,
        project_key: str = JIRA_PROJECT,
        max_results: int = EXEC_MAX_TASKS_PER_CYCLE,
    ) -> List[Dict[str, Any]]:
        """
        Return all Jira issues with the given label in the given status.
        Returns [] on any non-retryable failure (logged).
        """
        jql = (
            f'project = "{project_key}" '
            f'AND labels = "{label}" '
            f'AND status = "{status}" '
            f'ORDER BY priority DESC, created ASC'
        )
        url = f"{self._base}/rest/api/3/search/jql"
        body = {
            "jql":        jql,
            "maxResults": max_results,
            "fields":     ["summary", "description", "labels", "status",
                           "priority", "assignee", "created", "attachment"],
        }
        try:
            with httpx.Client(auth=self._auth, timeout=30.0) as client:
                resp = client.post(url, json=body)
                resp.raise_for_status()
                return resp.json().get("issues", [])
        except httpx.HTTPStatusError as exc:
            log.error(
                "Jira search %s [%s] → HTTP %s: %s",
                label, status, exc.response.status_code, exc.response.text[:200],
            )
            return []
        except RetryError:
            log.error("Jira search %s [%s] retries exhausted", label, status)
            return []

    # ── Transitions ───────────────────────────────────────────────────────────

    def transition(self, key: str, target_status: str) -> bool:
        """Move an issue to target_status by name. Returns True on success."""
        try:
            with httpx.Client(auth=self._auth, timeout=15.0) as client:
                r = client.get(f"{self._base}/rest/api/3/issue/{key}/transitions")
                r.raise_for_status()
                transitions = r.json().get("transitions", [])

                # Case-insensitive match on target_status
                target_id = next(
                    (t["id"] for t in transitions
                     if t.get("to", {}).get("name", "").lower() == target_status.lower()),
                    None,
                )
                if target_id is None:
                    log.warning(
                        "Transition '%s' not available for %s; options: %s",
                        target_status, key,
                        [t.get("to", {}).get("name") for t in transitions],
                    )
                    return False

                r2 = client.post(
                    f"{self._base}/rest/api/3/issue/{key}/transitions",
                    json={"transition": {"id": target_id}},
                )
                if r2.status_code in (200, 204):
                    log.info("Transitioned %s → %s", key, target_status)
                    return True
                log.warning("Transition %s → %s failed: HTTP %s",
                            key, target_status, r2.status_code)
                return False
        except Exception as exc:
            log.error("Transition %s → %s error: %s", key, target_status, exc)
            return False

    # ── Comment ───────────────────────────────────────────────────────────────

    def add_comment(self, key: str, body_markdown: str) -> bool:
        """
        Append a comment to a Jira issue.
        Body is provided as markdown; we wrap it in an ADF code block so the
        full formatting (including code fences) is preserved verbatim.
        """
        # ADF: use a single codeBlock node to preserve markdown/code formatting.
        adf_body = {
            "body": {
                "type":    "doc",
                "version": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "content": [
                            {"type": "text", "text": "[Aegis PM executor output]",
                             "marks": [{"type": "em"}]}
                        ],
                    },
                    {
                        "type":  "codeBlock",
                        "attrs": {"language": "markdown"},
                        "content": [{"type": "text", "text": body_markdown}],
                    },
                ],
            }
        }
        try:
            with httpx.Client(auth=self._auth, timeout=20.0) as client:
                resp = client.post(
                    f"{self._base}/rest/api/3/issue/{key}/comment",
                    json=adf_body,
                )
                resp.raise_for_status()
                log.info("Comment added to %s (%d chars)", key, len(body_markdown))
                return True
        except httpx.HTTPStatusError as exc:
            log.error(
                "add_comment %s → HTTP %s: %s",
                key, exc.response.status_code, exc.response.text[:200],
            )
            return False
        except Exception as exc:
            log.error("add_comment %s error: %s", key, exc)
            return False

    # ── Label ─────────────────────────────────────────────────────────────────

    def add_label(self, key: str, label: str) -> bool:
        """Add a label to an issue via PUT /issue/{key} with update.labels.add."""
        try:
            with httpx.Client(auth=self._auth, timeout=15.0) as client:
                resp = client.put(
                    f"{self._base}/rest/api/3/issue/{key}",
                    json={"update": {"labels": [{"add": label}]}},
                )
                resp.raise_for_status()
                log.info("Label '%s' added to %s", label, key)
                return True
        except Exception as exc:
            log.error("add_label %s → %s error: %s", key, label, exc)
            return False

    # ── Parse helpers ─────────────────────────────────────────────────────────

    @staticmethod
    def extract_description_text(issue: Dict[str, Any]) -> str:
        """
        Walk Jira's ADF description and flatten it to plain text.
        Returns '' if no description.
        """
        desc = (issue.get("fields") or {}).get("description")
        if not desc:
            return ""
        if isinstance(desc, str):   # older API sometimes returns raw str
            return desc
        return _flatten_adf(desc)

    @staticmethod
    def issue_url(key: str) -> str:
        return f"{JIRA_BASE_URL}/browse/{key}"


def _flatten_adf(node: Any) -> str:
    """Recursively extract plain-text content from an ADF document."""
    if not isinstance(node, dict):
        return ""
    if node.get("type") == "text":
        return node.get("text", "")
    parts: List[str] = []
    for child in node.get("content", []) or []:
        parts.append(_flatten_adf(child))
    # Insert newlines around block-level nodes for readability
    if node.get("type") in {"paragraph", "heading", "codeBlock",
                            "bulletList", "orderedList", "listItem"}:
        return "\n".join(p for p in parts if p) + "\n"
    return "".join(parts)


# ══════════════════════════════════════════════════════════════════════════════
#  BaseExecutor
# ══════════════════════════════════════════════════════════════════════════════

class BaseExecutor(ABC):
    """
    Common work loop for all six executor agents.

    Subclasses override:
      AGENT_LABEL         – Jira label used to scope work (e.g. "aegis:code")
      AGENT_NAME          – short name used for logging ("code_writer")
      SYSTEM_PROMPT       – system message for the LLM
      DELIVERABLE_HEADER  – first line of the Jira comment (e.g. "## Generated code")
    """

    AGENT_LABEL:        str = ""
    AGENT_NAME:         str = ""
    SYSTEM_PROMPT:      str = ""
    DELIVERABLE_HEADER: str = ""

    def __init__(self) -> None:
        if not self.AGENT_LABEL or not self.AGENT_NAME:
            raise ValueError(
                f"{type(self).__name__} must set AGENT_LABEL and AGENT_NAME"
            )
        self.jira = JiraExecClient()
        self.log  = logging.getLogger(f"aegis.exec.{self.AGENT_NAME}")

    # ── Public entry point (called by runner.py via APScheduler) ──────────────

    def run_once(self) -> Dict[str, Any]:
        """
        Run a single executor cycle: fetch → process → comment → transition.
        Returns a summary dict suitable for health tracker metadata.
        """
        self.log.info("━━━ %s cycle start (label=%s) ━━━",
                      self.AGENT_NAME, self.AGENT_LABEL)

        issues = self.jira.search_by_label(self.AGENT_LABEL)
        if not issues:
            self.log.debug("No %s tasks found", self.AGENT_LABEL)
            return {"tasks_found": 0, "tasks_done": 0, "tasks_failed": 0, "results": []}

        self.log.info("Found %d task(s) to execute", len(issues))

        done:   List[Dict[str, Any]] = []
        failed: List[Dict[str, Any]] = []

        for issue in issues:
            key = issue.get("key", "?")
            try:
                result = self._process_issue(issue)
                if result["success"]:
                    done.append(result)
                else:
                    failed.append(result)
            except Exception as exc:
                self.log.exception("Unhandled error processing %s: %s", key, exc)
                failed.append({
                    "task_key": key,
                    "success":  False,
                    "error":    str(exc),
                })

        summary = {
            "tasks_found":  len(issues),
            "tasks_done":   len(done),
            "tasks_failed": len(failed),
            "results":      done + failed,
        }
        self.log.info(
            "━━━ %s cycle end │ found=%d │ done=%d │ failed=%d ━━━",
            self.AGENT_NAME,
            summary["tasks_found"], summary["tasks_done"], summary["tasks_failed"],
        )
        return summary

    # ── Per-issue pipeline ────────────────────────────────────────────────────

    def _process_issue(self, issue: Dict[str, Any]) -> Dict[str, Any]:
        key     = issue["key"]
        fields  = issue.get("fields") or {}
        summary = fields.get("summary", "")
        desc    = self.jira.extract_description_text(issue)

        self.log.info("Processing %s: %s", key, summary[:80])

        # 1) Transition → In Progress (best-effort)
        self.jira.transition(key, EXEC_INPROGRESS_STATUS)

        # 2) Produce the deliverable
        try:
            deliverable = self.produce_deliverable(
                task_key=key, summary=summary, description=desc,
            )
        except Exception as exc:
            self.log.exception("produce_deliverable crashed for %s", key)
            self.jira.add_comment(
                key,
                f"# Aegis PM executor error\n\n"
                f"Agent `{self.AGENT_NAME}` failed while processing this task.\n\n"
                f"```\n{exc}\n```",
            )
            return {"task_key": key, "success": False, "error": str(exc)}

        # 3) Compose and post comment
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        body = (
            f"{self.DELIVERABLE_HEADER}\n\n"
            f"_Produced by `{self.AGENT_NAME}` at {ts}_\n\n"
            f"{deliverable}\n"
        )
        commented = self.jira.add_comment(key, body)

        # 4) Transition → In Review (fallback: add done label)
        transitioned = self.jira.transition(key, EXEC_DONE_STATUS)
        if not transitioned:
            self.jira.add_label(key, EXEC_DONE_LABEL)

        return {
            "task_key":    key,
            "summary":     summary,
            "success":     commented,
            "transitioned": transitioned,
            "url":         self.jira.issue_url(key),
        }

    # ── AutoGen-powered deliverable production (shared helper) ────────────────

    def produce_deliverable(
        self,
        task_key:    str,
        summary:     str,
        description: str,
    ) -> str:
        """
        Default implementation: run an AutoGen conversation with the subclass
        SYSTEM_PROMPT and return the assistant's last message (stripped of
        any TERMINATE sentinel).

        Subclasses can override for more complex flows (e.g. tool use,
        web fetch, etc).
        """
        assistant = AssistantAgent(
            name=f"{self.AGENT_NAME}_assistant",
            llm_config=EXEC_LLM_CONFIG,
            system_message=self.SYSTEM_PROMPT,
        )
        user_proxy = UserProxyAgent(
            name=f"{self.AGENT_NAME}_proxy",
            human_input_mode="NEVER",
            max_consecutive_auto_reply=1,   # single-turn: prompt → answer
            code_execution_config=False,
            is_termination_msg=lambda msg: (
                isinstance(msg.get("content"), str)
                and "TERMINATE" in msg["content"]
            ),
        )

        user_prompt = self.build_user_prompt(task_key, summary, description)

        try:
            user_proxy.initiate_chat(assistant, message=user_prompt, silent=True)
        except Exception as exc:
            self.log.error("AutoGen chat for %s crashed: %s", task_key, exc)
            return f"_Agent error: {exc}_"

        messages = user_proxy.chat_messages.get(assistant, [])
        for msg in reversed(messages):
            content = (msg.get("content") or "").strip()
            if content:
                # Strip any trailing TERMINATE sentinel
                return content.replace("TERMINATE", "").strip()

        return "_(The assistant produced no response.)_"

    # ── Subclass hook ─────────────────────────────────────────────────────────

    def build_user_prompt(
        self,
        task_key:    str,
        summary:     str,
        description: str,
    ) -> str:
        """
        Default prompt template. Override for specialised framing.
        """
        return (
            f"Jira task: {task_key}\n"
            f"Summary:   {summary}\n\n"
            f"Description:\n{description or '(no description provided)'}\n\n"
            f"Produce the deliverable as described in your instructions. "
            f"End your reply with TERMINATE on its own line."
        )
