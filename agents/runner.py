"""
aegis-pm / agents / runner.py

Entry point for the agent container.
APScheduler runs Monitor + Communicator on their schedules.
AgentHealthTracker records every cycle outcome and fires Slack alerts on failure.

AEGIS_MODE=agents      (default) – independent Monitor + Communicator schedules
AEGIS_MODE=groupchat   – single GroupChat full-cycle job per poll interval
"""
from __future__ import annotations

import asyncio
import logging
import os
import signal
import sys

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from dotenv import load_dotenv

from agents.monitor_agent import MonitorAgent
from agents.communicator_agent import CommunicatorAgent
from agents.group_chat import run_full_cycle
from agents.executors import (
    CodeWriterExecutor,
    TestWriterExecutor,
    DocWriterExecutor,
    ResearcherExecutor,
    ReviewerExecutor,
    TriageExecutor,
)
from agents.executors.project_poller import ProjectPoller
from agents.health.monitor import health, AgentName

load_dotenv()

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("aegis.runner")

POLL_INTERVAL   = int(os.getenv("POLL_INTERVAL_SECONDS", "300"))
NOTIFY_INTERVAL = 30
EXEC_INTERVAL   = int(os.getenv("EXEC_INTERVAL_SECONDS", "600"))
PROJECT_POLLER_INTERVAL = int(os.getenv("PROJECT_POLLER_INTERVAL_SECONDS", "60"))
AEGIS_MODE      = os.getenv("AEGIS_MODE", "agents").lower()
EXECUTORS_ENABLED = os.getenv("AEGIS_EXECUTORS_ENABLED", "true").lower() == "true"
PROJECT_POLLER_ENABLED = os.getenv("AEGIS_PROJECT_POLLER_ENABLED", "true").lower() == "true"

# Reminder scheduler (spec §9). Runs daily at REMINDER_HOUR (UTC).
REMINDERS_ENABLED = os.getenv("AEGIS_REMINDERS_ENABLED", "true").lower() == "true"
REMINDER_HOUR     = int(os.getenv("REMINDER_HOUR_UTC", "9"))

# (ExecutorClass, AgentName health enum) – one entry per executor agent.
EXECUTOR_SPECS = [
    (CodeWriterExecutor, AgentName.CODE_WRITER),
    (TestWriterExecutor, AgentName.TEST_WRITER),
    (DocWriterExecutor,  AgentName.DOC_WRITER),
    (ResearcherExecutor, AgentName.RESEARCHER),
    (ReviewerExecutor,   AgentName.REVIEWER),
    (TriageExecutor,     AgentName.TRIAGE),
]


async def run_monitor():
    try:
        agent = MonitorAgent()
        loop  = asyncio.get_event_loop()

        def _run():
            with health.track(AgentName.MONITOR):
                return MonitorAgent().run_once()

        summary = await loop.run_in_executor(None, _run)
        health.record_success(
            AgentName.MONITOR,
            stale_found=summary.get("stale_found", 0),
            alerts_saved=summary.get("alerts_saved", 0),
        )
        log.info(
            "Monitor cycle – stale=%d  saved=%d  notified=%d  failed=%d",
            summary.get("stale_found", 0),
            summary.get("alerts_saved", 0),
            summary.get("notifications_sent", 0),
            summary.get("failures", 0),
        )
    except Exception as e:
        health.record_failure(AgentName.MONITOR, str(e))
        log.exception("Monitor agent crashed: %s", e)


async def run_communicator():
    try:
        loop = asyncio.get_event_loop()

        def _run():
            with health.track(AgentName.COMMUNICATOR):
                return CommunicatorAgent().run_once()

        summary = await loop.run_in_executor(None, _run)
        if summary.get("notified", 0) or summary.get("failed", 0):
            health.record_success(
                AgentName.COMMUNICATOR,
                notified=summary.get("notified", 0),
                failed=summary.get("failed", 0),
            )
            log.info(
                "Communicator cycle – approved=%d  notified=%d  failed=%d",
                summary.get("approved_found", 0),
                summary.get("notified", 0),
                summary.get("failed", 0),
            )
    except Exception as e:
        health.record_failure(AgentName.COMMUNICATOR, str(e))
        log.exception("Communicator agent crashed: %s", e)


def _make_executor_job(executor_cls, agent_enum: AgentName):
    """
    Factory: build an async coroutine function that runs one cycle of the
    given executor under health tracking. Used to register each of the six
    executor agents with APScheduler.
    """
    async def _job():
        try:
            loop = asyncio.get_event_loop()

            def _run():
                with health.track(agent_enum):
                    return executor_cls().run_once()

            summary = await loop.run_in_executor(None, _run)
            health.record_success(
                agent_enum,
                tasks_found=summary.get("tasks_found", 0),
                tasks_done=summary.get("tasks_done", 0),
                tasks_failed=summary.get("tasks_failed", 0),
            )
            if summary.get("tasks_found", 0):
                log.info(
                    "%s cycle – found=%d  done=%d  failed=%d",
                    agent_enum.value,
                    summary.get("tasks_found", 0),
                    summary.get("tasks_done", 0),
                    summary.get("tasks_failed", 0),
                )
        except Exception as e:
            health.record_failure(agent_enum, str(e))
            log.exception("%s executor crashed: %s", agent_enum.value, e)

    _job.__name__ = f"run_{agent_enum.value}"
    return _job


async def run_project_poller():
    """Run one cycle of the ProjectPoller under health tracking."""
    try:
        loop = asyncio.get_event_loop()

        def _run():
            with health.track(AgentName.PROJECT_POLLER):
                return ProjectPoller().run_once()

        summary = await loop.run_in_executor(None, _run)
        health.record_success(
            AgentName.PROJECT_POLLER,
            tasks_claimed=summary.get("tasks_claimed", 0),
            tasks_done=summary.get("tasks_done", 0),
            tasks_failed=summary.get("tasks_failed", 0),
        )
        if summary.get("tasks_claimed", 0):
            log.info(
                "ProjectPoller – claimed=%d  done=%d  failed=%d",
                summary.get("tasks_claimed", 0),
                summary.get("tasks_done", 0),
                summary.get("tasks_failed", 0),
            )
    except Exception as e:
        health.record_failure(AgentName.PROJECT_POLLER, str(e))
        log.exception("ProjectPoller crashed: %s", e)


async def run_group_chat_cycle():
    try:
        loop = asyncio.get_event_loop()

        def _run():
            with health.track(AgentName.GROUP_CHAT):
                return run_full_cycle()

        report = await loop.run_in_executor(None, _run)
        health.record_success(
            AgentName.GROUP_CHAT,
            status=report.get("status"),
            summary=report.get("summary"),
        )
        log.info(
            "GroupChat cycle – status=%s  summary=%s",
            report.get("status", "?"),
            report.get("summary", ""),
        )
    except Exception as e:
        health.record_failure(AgentName.GROUP_CHAT, str(e))
        log.exception("GroupChat cycle crashed: %s", e)


def main():
    log.info("═══════════════════════════════════════════")
    log.info("  Aegis PM – Agent Runner starting up      ")
    log.info("  Mode             : %s", AEGIS_MODE.upper())
    log.info("  Poll interval    : %ds", POLL_INTERVAL)
    if AEGIS_MODE == "agents":
        log.info("  Notify interval  : %ds", NOTIFY_INTERVAL)
    log.info("  Executors        : %s", "ENABLED" if EXECUTORS_ENABLED else "disabled")
    if EXECUTORS_ENABLED:
        log.info("  Executor interval: %ds", EXEC_INTERVAL)
        log.info("  Executor agents  : %s",
                 ", ".join(e.value for _, e in EXECUTOR_SPECS))
    log.info("  Project poller   : %s  (%ds)",
             "ENABLED" if PROJECT_POLLER_ENABLED else "disabled",
             PROJECT_POLLER_INTERVAL)
    log.info("═══════════════════════════════════════════")

    scheduler = AsyncIOScheduler()

    if AEGIS_MODE == "groupchat":
        scheduler.add_job(
            run_group_chat_cycle,
            trigger=IntervalTrigger(seconds=POLL_INTERVAL),
            id="groupchat_cycle",
            name="GroupChat Full Cycle",
            next_run_time=__import__("datetime").datetime.now(),
            misfire_grace_time=120,
        )
    else:
        scheduler.add_job(
            run_monitor,
            trigger=IntervalTrigger(seconds=POLL_INTERVAL),
            id="monitor",
            name="Monitor Agent",
            next_run_time=__import__("datetime").datetime.now(),
            misfire_grace_time=60,
        )
        scheduler.add_job(
            run_communicator,
            trigger=IntervalTrigger(seconds=NOTIFY_INTERVAL),
            id="communicator",
            name="Communicator Agent",
            misfire_grace_time=30,
        )

    # ── ProjectPoller – runs queued tasks from the Aegis PM DB ───────────────
    if PROJECT_POLLER_ENABLED:
        import datetime as _dt2
        scheduler.add_job(
            run_project_poller,
            trigger=IntervalTrigger(seconds=PROJECT_POLLER_INTERVAL),
            id="project_poller",
            name="ProjectPoller",
            next_run_time=_dt2.datetime.now() + _dt2.timedelta(seconds=10),
            misfire_grace_time=30,
            max_instances=1,   # prevent overlapping cycles
        )

    # ── Reminder agent – daily pending + deadline warnings ───────────────────
    if REMINDERS_ENABLED:
        from agents.reminder_agent import run_reminder_cycle
        scheduler.add_job(
            run_reminder_cycle,
            trigger=CronTrigger(hour=REMINDER_HOUR, minute=0),
            id="reminder_agent",
            name="Reminder Agent (daily)",
            misfire_grace_time=60 * 60,   # forgive if the container was down
            max_instances=1,
        )

    # ── Executor agents – actually perform Jira work ─────────────────────────
    if EXECUTORS_ENABLED:
        # Stagger executor first-runs by a few seconds each so they don't all
        # hit Jira at the same instant on startup.
        import datetime as _dt
        base = _dt.datetime.now() + _dt.timedelta(seconds=15)
        for idx, (cls, agent_enum) in enumerate(EXECUTOR_SPECS):
            scheduler.add_job(
                _make_executor_job(cls, agent_enum),
                trigger=IntervalTrigger(seconds=EXEC_INTERVAL),
                id=agent_enum.value,
                name=f"{cls.__name__}",
                next_run_time=base + _dt.timedelta(seconds=idx * 5),
                misfire_grace_time=60,
                max_instances=1,   # never overlap cycles of the same executor
            )

    scheduler.start()
    loop = asyncio.get_event_loop()

    def _shutdown(sig, frame):
        log.info("Shutdown signal (%s) – stopping…", sig)
        scheduler.shutdown(wait=False)
        loop.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT,  _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    try:
        loop.run_forever()
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        scheduler.shutdown(wait=False)
        log.info("Aegis PM agent runner stopped.")


if __name__ == "__main__":
    main()
