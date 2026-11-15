"""Persistent job queue: rows in SQLite, executed one at a time by a worker thread."""

from __future__ import annotations

import logging
import threading
import traceback

from sqlalchemy import select, update

from ..db import session_scope
from ..i18n import tr
from ..models import GenerationJob, JobStatus, ScraperJob, utcnow

log = logging.getLogger("dayfold.jobs")

_wake = threading.Event()
_stop = threading.Event()
_thread: threading.Thread | None = None


def recover_interrupted() -> None:
    """Jobs left RUNNING by a crash or restart are marked FAILED on boot."""
    with session_scope() as s:
        for model in (GenerationJob, ScraperJob):
            s.execute(
                update(model)
                .where(model.status == JobStatus.RUNNING)
                .values(status=JobStatus.FAILED, error="interrompido por reinício do servidor",
                        finished_at=utcnow())
            )


def enqueue_generation(trigger: str = "manual") -> int:
    with session_scope() as s:
        running = s.scalar(
            select(GenerationJob.id).where(
                GenerationJob.status.in_([JobStatus.QUEUED, JobStatus.RUNNING])
            ).limit(1)
        )
        if running:
            return running
        job = GenerationJob(trigger=trigger,
                            log=[tr(f"Geração solicitada ({trigger}).", f"Generation requested ({trigger}).")])
        s.add(job)
        s.flush()
        job_id = job.id
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


def _loop() -> None:
    while not _stop.is_set():
        nxt = _next()
        if nxt is None:
            _wake.wait(timeout=5)
            _wake.clear()
            continue
        kind, job_id = nxt
        try:
            _run(kind, job_id)
        except Exception:  # noqa: BLE001
            log.error("job %s %s falhou:\n%s", kind, job_id, traceback.format_exc())
            model = ScraperJob if kind == "scraper" else GenerationJob
            with session_scope() as s:
                job = s.get(model, job_id)
                if job and job.status in (JobStatus.QUEUED, JobStatus.RUNNING):
                    job.status = JobStatus.FAILED
                    job.error = traceback.format_exc(limit=3)[-1500:]
                    job.finished_at = utcnow()


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
