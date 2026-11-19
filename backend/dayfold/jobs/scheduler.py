"""Daily schedule: an APScheduler cron trigger rebuilt whenever settings change."""

from __future__ import annotations

import logging
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select

from .. import clock
from ..db import session_scope
from ..models import Edition, EditionStatus
from ..settings import ScheduleSettings, get_section
from .queue import enqueue_generation

log = logging.getLogger("dayfold.scheduler")
_scheduler: BackgroundScheduler | None = None
JOB_ID = "daily-edition"
WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


def _fire() -> None:
    log.info("geração agendada disparada")
    enqueue_generation("schedule")


def _trigger(sched: ScheduleSettings) -> CronTrigger:
    hh, mm = map(int, sched.time.split(":"))
    return CronTrigger(day_of_week=",".join(WEEKDAYS[d] for d in sched.days),
                       hour=hh, minute=mm, timezone=sched.timezone)


def reschedule() -> None:
    if _scheduler is None:
        return
    with session_scope() as s:
        sched: ScheduleSettings = get_section(s, "schedule")  # type: ignore[assignment]
    if _scheduler.get_job(JOB_ID):
        _scheduler.remove_job(JOB_ID)
    if sched.enabled:
        _scheduler.add_job(_fire, _trigger(sched), id=JOB_ID, misfire_grace_time=3600, coalesce=True)


def next_run() -> datetime | None:
    if _scheduler is None:
        return None
    job = _scheduler.get_job(JOB_ID)
    return job.next_run_time if job else None


def catch_up() -> int | None:
    """Make today's paper when the scheduled run was missed: the machine was off or asleep then.

    Called once at startup. A day the schedule does not print has nothing to make up, nothing is
    due before the scheduled time, and a READY edition dated today already counts as printed, so
    an evening restart changes nothing.
    """
    with session_scope() as s:
        sched: ScheduleSettings = get_section(s, "schedule")  # type: ignore[assignment]
        if not sched.enabled:
            return None
        now = clock.now(sched.timezone)
        if now.weekday() not in sched.days:
            return None
        hour, minute = map(int, sched.time.split(":"))
        if (now.hour, now.minute) < (hour, minute):
            return None
        printed = s.scalar(select(Edition.id).where(Edition.status == EditionStatus.READY,
                                                    Edition.edition_date == now.date()).limit(1))
    if printed:
        return None
    job_id = enqueue_generation("catch-up")
    log.info("catch-up: edição de %s na fila (job %s)", now.date(), job_id)
    return job_id


def start_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        return
    _scheduler = BackgroundScheduler()
    _scheduler.start()
    reschedule()
    catch_up()


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
