"""Daily schedule: an APScheduler cron trigger rebuilt whenever settings change."""

from __future__ import annotations

import logging
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from ..db import session_scope
from ..settings import ScheduleSettings, get_section
from .queue import enqueue_generation

log = logging.getLogger("dayfold.scheduler")
_scheduler: BackgroundScheduler | None = None
JOB_ID = "daily-edition"


def _fire() -> None:
    log.info("geração agendada disparada")
    enqueue_generation("schedule")


def reschedule() -> None:
    if _scheduler is None:
        return
    with session_scope() as s:
        sched: ScheduleSettings = get_section(s, "schedule")  # type: ignore[assignment]
    if _scheduler.get_job(JOB_ID):
        _scheduler.remove_job(JOB_ID)
    if sched.enabled:
        hh, mm = map(int, sched.time.split(":"))
        _scheduler.add_job(_fire, CronTrigger(hour=hh, minute=mm, timezone=sched.timezone),
                           id=JOB_ID, misfire_grace_time=3600, coalesce=True)


def next_run() -> datetime | None:
    if _scheduler is None:
        return None
    job = _scheduler.get_job(JOB_ID)
    return job.next_run_time if job else None


def start_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        return
    _scheduler = BackgroundScheduler()
    _scheduler.start()
    reschedule()


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
