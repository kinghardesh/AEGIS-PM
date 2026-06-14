"""
aegis-pm / agents / executors

Executor agents – unlike Monitor/Communicator/SpecInterpreter which only
manage the flow of work, these agents actually *perform* the Jira tasks
that are assigned to them.

Each executor:
  1. Polls Jira for tasks with its label (aegis:code, aegis:test, ...)
     in status "To Do".
  2. Transitions the task to "In Progress".
  3. Runs an AutoGen agent with a specialised system prompt that produces
     the deliverable (code, tests, docs, research, review, triage).
  4. Posts the deliverable as a Jira comment.
  5. Transitions the task to "In Review" (falls back to adding an
     "aegis:done" label if the transition is not available).
"""
from agents.executors.base import BaseExecutor, JiraExecClient
from agents.executors.code_writer import CodeWriterExecutor
from agents.executors.test_writer import TestWriterExecutor
from agents.executors.doc_writer import DocWriterExecutor
from agents.executors.researcher import ResearcherExecutor
from agents.executors.reviewer import ReviewerExecutor
from agents.executors.triage import TriageExecutor

EXECUTORS = {
    "code_writer":  CodeWriterExecutor,
    "test_writer":  TestWriterExecutor,
    "doc_writer":   DocWriterExecutor,
    "researcher":   ResearcherExecutor,
    "reviewer":     ReviewerExecutor,
    "triage":       TriageExecutor,
}

__all__ = [
    "BaseExecutor",
    "JiraExecClient",
    "CodeWriterExecutor",
    "TestWriterExecutor",
    "DocWriterExecutor",
    "ResearcherExecutor",
    "ReviewerExecutor",
    "TriageExecutor",
    "EXECUTORS",
]
