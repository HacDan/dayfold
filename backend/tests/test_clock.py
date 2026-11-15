from __future__ import annotations

from datetime import UTC, datetime


def test_stored_utc_renders_in_the_operator_zone():
    from dayfold import clock

    when = datetime(2026, 11, 15, 3, 20)  # naive, as the database stores it
    assert clock.in_zone(when, "America/Sao_Paulo").strftime("%Y-%m-%d %H:%M") == "2026-11-15 00:20"
    assert clock.in_zone(when, "Europe/Lisbon").strftime("%H:%M") == "03:20"
    # An aware value is converted, never shifted twice.
    assert clock.in_zone(when.replace(tzinfo=UTC), "America/Sao_Paulo").hour == 0
    # The date can roll over with the zone, and the paper's date label depends on it.
    late = datetime(2026, 11, 15, 23, 30)
    assert clock.in_zone(late, "Asia/Tokyo").date().isoformat() == "2026-11-16"


def test_job_log_stamps_in_the_operator_zone(data_dir, monkeypatch):
    from dayfold import clock, db
    from dayfold.models import GenerationJob, JobStatus
    from dayfold.pipeline.generate import JobLog

    with db.session_scope() as s:
        job = GenerationJob(trigger="manual", status=JobStatus.RUNNING, log=[])
        s.add(job)
        s.flush()
        job_id = job.id

    # 03:20 UTC is 00:20 where the schedule runs, and that is what the log line must show.
    fixed = datetime(2026, 11, 15, 3, 20, tzinfo=UTC)
    monkeypatch.setattr(clock, "now", lambda tz=None: fixed.astimezone(tz or fixed.tzinfo))
    JobLog(job_id)("primeira linha")

    with db.session_scope() as s:
        log = s.get(GenerationJob, job_id).log
    assert log[0] == "[00:20:00] primeira linha"
