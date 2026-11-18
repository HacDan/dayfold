"""Persistent job queue: rows in SQLite, executed one at a time by a worker thread."""

from __future__ import annotations

import logging
import threading
import traceback

from sqlalchemy import select, update

from .. import clock
from ..db import session_scope
from ..i18n import tr
from ..models import Edition, EditionStatus, GenerationJob, JobStatus, ScraperJob, utcnow

log = logging.getLogger("dayfold.jobs")

RETRY_DELAY_S = 30  # long enough for a feed or the AI to come back, short enough to notice

_wake = threading.Event()
_stop = threading.Event()
_thread: threading.Thread | None = None


def recover_interrupted() -> None:
    """Jobs left RUNNING by a crash or restart are marked FAILED on boot.

    The interrupted generation also leaves the edition it was building, which would sit next to
    the paper printed after the restart.
    """
    from ..pipeline.generate import discard_failed_attempt

    with session_scope() as s:
        interrupted = list(s.scalars(select(GenerationJob.id)
                                     .where(GenerationJob.status == JobStatus.RUNNING)))
        for model in (GenerationJob, ScraperJob):
            s.execute(
                update(model)
                .where(model.status == JobStatus.RUNNING)
                .values(status=JobStatus.FAILED,
                        error=tr("interrompido por reinício do servidor", "interrupted by a server restart"),
                        finished_at=utcnow())
            )
    for job_id in interrupted:
        discard_failed_attempt(job_id)


def enqueue_generation(trigger: str = "manual") -> int:
    """Queue the day's paper, clearing first what an earlier run left behind: a rerun would
    otherwise print next to the failed edition still sitting on the dashboard."""
    from ..pipeline.generate import discard_failed_attempt

    with session_scope() as s:
        running = s.scalar(
            select(GenerationJob.id).where(
                GenerationJob.status.in_([JobStatus.QUEUED, JobStatus.RUNNING])
            ).limit(1)
        )
        if running:
            return running
        stale = list(s.scalars(
            select(GenerationJob.id)
            .join(Edition, Edition.id == GenerationJob.edition_id)
            .where(Edition.status.in_([EditionStatus.BUILDING, EditionStatus.FAILED]))
        ))
        job = GenerationJob(trigger=trigger,
                            log=[tr(f"Geração solicitada ({trigger}).", f"Generation requested ({trigger}).")])
        s.add(job)
        s.flush()
        job_id = job.id
    for old_job in stale:
        discard_failed_attempt(old_job)
    _wake.set()
    return job_id


def enqueue_scraper(provider_id: int, *, kind: str = "generate", use_ai: bool = True,
                    extra_prompt: str | None = None, version_id: int | None = None) -> int:
    with session_scope() as s:
        job = ScraperJob(provider_id=provider_id, kind=kind, use_ai=use_ai,
                         extra_prompt=extra_prompt, version_id=version_id, log=[])
        s.add(job)
        s.flush()
        job_id = job.id
    _wake.set()
    return job_id


def _next() -> tuple[str, int] | None:
    with session_scope() as s:
        g = s.scalar(select(GenerationJob.id).where(GenerationJob.status == JobStatus.QUEUED)
                     .order_by(GenerationJob.id).limit(1))
        sc = s.scalar(select(ScraperJob.id).where(ScraperJob.status == JobStatus.QUEUED)
                      .order_by(ScraperJob.id).limit(1))
    if sc:  # scraper jobs are short and the UI waits on them
        return ("scraper", sc)
    if g:
        return ("generation", g)
    return None


def _run(kind: str, job_id: int) -> None:
    if kind == "scraper":
        from ..sources.builder import run_scraper_job

        run_scraper_job(job_id)
    else:
        from ..pipeline.generate import run_generation_job

        run_generation_job(job_id)


def _fail(kind: str, job_id: int, error: str) -> None:
    model = ScraperJob if kind == "scraper" else GenerationJob
    with session_scope() as s:
        job = s.get(model, job_id)
        if job and job.status in (JobStatus.QUEUED, JobStatus.RUNNING):
            job.status = JobStatus.FAILED
            job.error = error
            job.finished_at = utcnow()


def _retrying(job_id: int, error: str) -> None:
    """Back to running, with why the first attempt failed left in the log the dashboard shows: a
    retry that works would otherwise leave no record of it."""
    with session_scope() as s:
        job = s.get(GenerationJob, job_id)
        if job:
            job.status = JobStatus.RUNNING
            job.error = None
            stamp = clock.now(clock.zone()).strftime("%H:%M:%S")
            reason = error.strip().splitlines()[-1][:300]
            job.log = [*job.log, f"[{stamp}] {tr(f'Tentando de novo: {reason}', f'Trying again: {reason}')}"]


def _printed(job_id: int) -> bool:
    """A failure after the paper was typeset must not start another one for the same day."""
    with session_scope() as s:
        job = s.get(GenerationJob, job_id)
        edition = s.get(Edition, job.edition_id) if job and job.edition_id else None
        return bool(edition and edition.status not in (EditionStatus.BUILDING, EditionStatus.FAILED))


def _attempt(kind: str, job_id: int) -> None:
    """Run one job. A generation gets a second chance: transient failures are common and the
    day's paper is the point."""
    tries = 2 if kind == "generation" else 1
    for attempt in range(1, tries + 1):
        try:
            _run(kind, job_id)
            return
        except Exception:  # noqa: BLE001
            error = traceback.format_exc()
            log.error("job %s %s falhou (tentativa %s/%s):\n%s", kind, job_id, attempt, tries, error)
            if attempt == tries or _printed(job_id):
                _fail(kind, job_id, error[-1500:])
                return
            _retrying(job_id, error)
            if _stop.wait(RETRY_DELAY_S):  # stopping: do not start the second attempt
                _fail(kind, job_id, error[-1500:])
                return


def _loop() -> None:
    while not _stop.is_set():
        nxt = _next()
        if nxt is None:
            _wake.wait(timeout=5)
            _wake.clear()
            continue
        kind, job_id = nxt
        _attempt(kind, job_id)


def start_worker() -> None:
    global _thread
    if _thread and _thread.is_alive():
        return
    _stop.clear()
    _thread = threading.Thread(target=_loop, name="dayfold-worker", daemon=True)
    _thread.start()


def stop_worker() -> None:
    _stop.set()
    _wake.set()
