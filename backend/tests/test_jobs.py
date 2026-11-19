"""The daily run: a missed schedule is made up on startup, and one failure gets a second try that
leaves no half-made paper behind — not after a crash, not after a failure, not on a rerun."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select

TZ = "America/New_York"


def _scheduled(monkeypatch, when: datetime, *, time: str = "09:00",
               days: list[int] | None = None) -> None:
    """Fix the operator's clock and the schedule the test acts on."""
    from dayfold.db import session_scope
    from dayfold.jobs import scheduler
    from dayfold.settings import set_section

    body = {"enabled": True, "time": time, "timezone": TZ}
    if days is not None:
        body["days"] = days
    with session_scope() as s:
        set_section(s, "schedule", body)
    monkeypatch.setattr(scheduler.clock, "now", lambda tz=None: when)


def _paper(edition_date: date) -> None:
    from dayfold.db import session_scope
    from dayfold.models import Edition, EditionStatus

    with session_scope() as s:
        s.add(Edition(number=1, edition_date=edition_date, title="Dayfold", status=EditionStatus.READY))


def test_catch_up_queues_todays_paper_after_a_missed_run(data_dir, monkeypatch):
    from dayfold.db import session_scope
    from dayfold.jobs import scheduler
    from dayfold.models import GenerationJob, JobStatus

    _scheduled(monkeypatch, datetime(2026, 11, 17, 12, 0, tzinfo=ZoneInfo(TZ)))

    job_id = scheduler.catch_up()

    assert job_id
    with session_scope() as s:
        job = s.get(GenerationJob, job_id)
        assert job.trigger == "catch-up"
        assert job.status == JobStatus.QUEUED


def test_catch_up_waits_for_the_scheduled_time(data_dir, monkeypatch):
    from dayfold.jobs import scheduler

    _scheduled(monkeypatch, datetime(2026, 11, 17, 7, 30, tzinfo=ZoneInfo(TZ)), time="09:00")

    assert scheduler.catch_up() is None


def test_catch_up_leaves_a_printed_paper_alone(data_dir, monkeypatch):
    from dayfold.jobs import scheduler

    _scheduled(monkeypatch, datetime(2026, 11, 17, 12, 0, tzinfo=ZoneInfo(TZ)))
    _paper(date(2026, 11, 17))

    assert scheduler.catch_up() is None


def test_catch_up_does_not_count_yesterdays_paper(data_dir, monkeypatch):
    from dayfold.jobs import scheduler

    _scheduled(monkeypatch, datetime(2026, 11, 17, 12, 0, tzinfo=ZoneInfo(TZ)))
    _paper(date(2026, 11, 16))

    assert scheduler.catch_up()


def test_catch_up_skips_a_day_the_schedule_does_not_print(data_dir, monkeypatch):
    from dayfold.jobs import scheduler

    # 2026-11-18 is a Wednesday; the paper prints on Tuesdays only.
    _scheduled(monkeypatch, datetime(2026, 11, 18, 12, 0, tzinfo=ZoneInfo(TZ)), days=[1])

    assert scheduler.catch_up() is None


def test_catch_up_prints_on_a_scheduled_weekday(data_dir, monkeypatch):
    from dayfold.jobs import scheduler

    _scheduled(monkeypatch, datetime(2026, 11, 18, 12, 0, tzinfo=ZoneInfo(TZ)), days=[2, 4])

    assert scheduler.catch_up()


def test_the_cron_trigger_names_the_chosen_weekdays():
    from dayfold.jobs import scheduler
    from dayfold.settings import ScheduleSettings

    trigger = scheduler._trigger(ScheduleSettings(days=[4, 0, 2], time="07:30"))
    field = next(f for f in trigger.fields if f.name == "day_of_week")
    assert [str(e) for e in field.expressions] == ["mon", "wed", "fri"]


def test_catch_up_respects_a_disabled_schedule(data_dir, monkeypatch):
    from dayfold.db import session_scope
    from dayfold.jobs import scheduler
    from dayfold.settings import set_section

    _scheduled(monkeypatch, datetime(2026, 11, 17, 12, 0, tzinfo=ZoneInfo(TZ)))
    with session_scope() as s:
        set_section(s, "schedule", {"enabled": False})

    assert scheduler.catch_up() is None


def _generation_job() -> int:
    from dayfold.db import session_scope
    from dayfold.models import GenerationJob

    with session_scope() as s:
        job = GenerationJob(trigger="schedule", log=[])
        s.add(job)
        s.flush()
        return job.id


def _always_raising(calls: list[str]):
    def run(kind: str, job_id: int) -> None:
        calls.append(kind)
        raise RuntimeError("nenhuma matéria disponível")

    return run


def test_a_failed_generation_is_tried_once_more(data_dir, monkeypatch):
    from dayfold.db import session_scope
    from dayfold.jobs import queue
    from dayfold.models import GenerationJob, JobStatus

    job_id = _generation_job()
    calls: list[str] = []

    def flaky(kind: str, job_id: int) -> None:
        calls.append(kind)
        if len(calls) == 1:
            raise RuntimeError("feed timeout")

    monkeypatch.setattr(queue, "_run", flaky)
    monkeypatch.setattr(queue, "RETRY_DELAY_S", 0)
    queue._stop.clear()  # a TestClient elsewhere in the suite may have stopped the worker

    queue._attempt("generation", job_id)

    assert calls == ["generation", "generation"]
    with session_scope() as s:
        job = s.get(GenerationJob, job_id)
        assert job.status == JobStatus.RUNNING  # the second attempt is the one that has to finish
        assert job.error is None


def test_a_retry_records_why_the_first_attempt_failed(data_dir, monkeypatch):
    """A retry that works must still say, in the log the dashboard shows, why the first
    attempt failed: the error field is cleared for the new attempt."""
    from dayfold.db import session_scope
    from dayfold.jobs import queue
    from dayfold.models import GenerationJob, JobStatus

    job_id = _generation_job()
    calls: list[str] = []

    def flaky(kind: str, job_id: int) -> None:
        calls.append(kind)
        if len(calls) == 1:
            raise RuntimeError("feed timeout")

    monkeypatch.setattr(queue, "_run", flaky)
    monkeypatch.setattr(queue, "RETRY_DELAY_S", 0)
    queue._stop.clear()

    queue._attempt("generation", job_id)

    with session_scope() as s:
        job = s.get(GenerationJob, job_id)
        assert job.status == JobStatus.RUNNING
        assert any("RuntimeError: feed timeout" in line for line in job.log)


def test_a_generation_that_fails_twice_is_marked_failed(data_dir, monkeypatch):
    from dayfold.db import session_scope
    from dayfold.jobs import queue
    from dayfold.models import GenerationJob, JobStatus

    job_id = _generation_job()
    calls: list[str] = []
    monkeypatch.setattr(queue, "_run", _always_raising(calls))
    monkeypatch.setattr(queue, "RETRY_DELAY_S", 0)
    queue._stop.clear()

    queue._attempt("generation", job_id)

    assert calls == ["generation", "generation"]
    with session_scope() as s:
        job = s.get(GenerationJob, job_id)
        assert job.status == JobStatus.FAILED
        assert "RuntimeError" in job.error


def _edition(job_id: int, status, day: date = date(2026, 11, 17)) -> int:
    """The edition a job has attached, with its directory on disk."""
    from dayfold.db import session_scope
    from dayfold.models import Edition, GameInstance, GenerationJob
    from dayfold.pipeline.generate import edition_dir

    out_dir = edition_dir(day, 1)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "cover.png").write_bytes(b"png")
    with session_scope() as s:
        ed = Edition(number=1, edition_date=day, title="Dayfold", status=status, job_id=job_id,
                     cover_path=str(out_dir / "cover.png"))
        s.add(ed)
        s.flush()
        s.add(GameInstance(edition_id=ed.id, kind="sudoku", position=0, title="Sudoku",
                           puzzle={}, solution={}))
        s.get(GenerationJob, job_id).edition_id = ed.id
        return ed.id


def test_a_retry_discards_the_edition_its_failed_attempt_left(data_dir):
    from dayfold.db import session_scope
    from dayfold.models import Edition, EditionStatus, GameInstance, GenerationJob
    from dayfold.pipeline.generate import discard_failed_attempt, edition_dir

    job_id = _generation_job()
    edition_id = _edition(job_id, EditionStatus.FAILED)

    discard_failed_attempt(job_id)

    with session_scope() as s:
        assert s.get(Edition, edition_id) is None
        assert s.get(GenerationJob, job_id).edition_id is None
        assert not list(s.scalars(select(GameInstance).where(GameInstance.edition_id == edition_id)))
    assert not edition_dir(date(2026, 11, 17), 1).exists()


def test_a_phantom_sharing_its_directory_keeps_the_printed_papers_files(data_dir):
    """A FAILED edition from before this fix can share its date, number and directory with the
    paper that replaced it: discarding the phantom must leave that paper and its files alone."""
    from dayfold.db import session_scope
    from dayfold.models import Edition, EditionStatus
    from dayfold.pipeline.generate import discard_failed_attempt, edition_dir

    job_id = _generation_job()
    phantom_id = _edition(job_id, EditionStatus.FAILED)
    paper_epub = edition_dir(date(2026, 11, 17), 1) / "paper.epub"
    paper_epub.write_bytes(b"epub")
    with session_scope() as s:
        s.add(Edition(number=1, edition_date=date(2026, 11, 17), title="Dayfold",
                      status=EditionStatus.READY, epub_path=str(paper_epub)))

    discard_failed_attempt(job_id)

    with session_scope() as s:
        assert s.get(Edition, phantom_id) is None
        assert s.scalar(select(Edition.id).where(Edition.status == EditionStatus.READY)) is not None
    assert paper_epub.exists()


def test_a_retry_keeps_an_edition_that_was_already_printed(data_dir):
    from dayfold.db import session_scope
    from dayfold.models import Edition, EditionStatus
    from dayfold.pipeline.generate import discard_failed_attempt, edition_dir

    job_id = _generation_job()
    edition_id = _edition(job_id, EditionStatus.READY)

    discard_failed_attempt(job_id)

    with session_scope() as s:
        assert s.get(Edition, edition_id) is not None
    assert edition_dir(date(2026, 11, 17), 1).exists()


def test_a_failure_after_the_paper_was_printed_is_not_tried_again(data_dir, monkeypatch):
    from dayfold.db import session_scope
    from dayfold.jobs import queue
    from dayfold.models import EditionStatus, GenerationJob, JobStatus

    job_id = _generation_job()
    _edition(job_id, EditionStatus.READY)
    calls: list[str] = []
    monkeypatch.setattr(queue, "_run", _always_raising(calls))
    monkeypatch.setattr(queue, "RETRY_DELAY_S", 0)
    queue._stop.clear()

    queue._attempt("generation", job_id)

    assert calls == ["generation"]  # a second edition for the same day must not be printed
    with session_scope() as s:
        assert s.get(GenerationJob, job_id).status == JobStatus.FAILED


def test_a_generation_interrupted_by_a_restart_leaves_no_edition_behind(data_dir):
    from dayfold.db import session_scope
    from dayfold.jobs import queue
    from dayfold.models import Edition, EditionStatus, GenerationJob, JobStatus
    from dayfold.pipeline.generate import edition_dir

    job_id = _generation_job()
    edition_id = _edition(job_id, EditionStatus.BUILDING)
    with session_scope() as s:
        s.get(GenerationJob, job_id).status = JobStatus.RUNNING

    queue.recover_interrupted()

    with session_scope() as s:
        assert s.get(Edition, edition_id) is None
        assert s.get(GenerationJob, job_id).status == JobStatus.FAILED
    assert not edition_dir(date(2026, 11, 17), 1).exists()


def test_a_rerun_clears_the_edition_the_failed_run_left(data_dir):
    from dayfold.db import session_scope
    from dayfold.jobs import queue
    from dayfold.models import Edition, EditionStatus, GenerationJob, JobStatus
    from dayfold.pipeline.generate import edition_dir

    failed = _generation_job()
    edition_id = _edition(failed, EditionStatus.FAILED)
    with session_scope() as s:
        s.get(GenerationJob, failed).status = JobStatus.FAILED
    queue._stop.set()  # a worker must not pick the new job up mid-test

    queue.enqueue_generation()

    with session_scope() as s:
        assert s.get(Edition, edition_id) is None
    assert not edition_dir(date(2026, 11, 17), 1).exists()


def test_a_failure_after_the_paper_was_typeset_keeps_it_ready(data_dir, monkeypatch):
    """A printed paper is not downgraded, so the retry keeps it instead of reprinting the day."""
    from edition_helpers import generate

    from dayfold.db import session_scope
    from dayfold.jobs import queue
    from dayfold.models import Edition, EditionStatus
    from dayfold.pipeline import generate as pipeline

    def prune_fails() -> None:
        raise RuntimeError("prune failed")

    monkeypatch.setattr(pipeline, "_prune", prune_fails)
    with pytest.raises(RuntimeError):
        generate(monkeypatch, [("nasa", "Rocket launch to the Moon with astronauts")])

    with session_scope() as s:
        edition = s.scalar(select(Edition).order_by(Edition.id.desc()).limit(1))
        assert edition.status == EditionStatus.READY
        assert Path(edition.epub_path).exists()
        assert queue._printed(edition.job_id)  # the second attempt would be a new paper


def test_a_failure_before_the_paper_was_typeset_marks_the_edition_failed(data_dir, monkeypatch):
    from edition_helpers import generate

    from dayfold.db import session_scope
    from dayfold.models import Edition, EditionStatus
    from dayfold.pipeline import generate as pipeline

    def typeset_fails(edition_id: int, log, test_games=None):
        raise RuntimeError("epub failed")

    monkeypatch.setattr(pipeline, "typeset", typeset_fails)
    with pytest.raises(RuntimeError):
        generate(monkeypatch, [("nasa", "Rocket launch to the Moon with astronauts")])

    with session_scope() as s:
        edition = s.scalar(select(Edition).order_by(Edition.id.desc()).limit(1))
        assert edition.status == EditionStatus.FAILED


def test_a_scraper_failure_is_not_retried(data_dir, monkeypatch):
    from dayfold.db import session_scope
    from dayfold.jobs import queue
    from dayfold.models import JobStatus, Provider, ScraperJob

    with session_scope() as s:
        job = ScraperJob(provider_id=s.scalar(select(Provider.id)), kind="generate", use_ai=False, log=[])
        s.add(job)
        s.flush()
        job_id = job.id
    calls: list[str] = []
    monkeypatch.setattr(queue, "_run", _always_raising(calls))

    queue._attempt("scraper", job_id)

    assert calls == ["scraper"]
    with session_scope() as s:
        assert s.get(ScraperJob, job_id).status == JobStatus.FAILED
