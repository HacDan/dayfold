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
    from dayfold.settings import get_section, set_section

    # A zone far from both UTC and the default, so a wrong lookup cannot pass by accident.
    with db.session_scope() as s:
        set_section(s, "schedule", {**get_section(s, "schedule").model_dump(), "timezone": "Asia/Tokyo"})
    with db.session_scope() as s:
        job = GenerationJob(trigger="manual", status=JobStatus.RUNNING, log=[])
        s.add(job)
        s.flush()
        job_id = job.id

    # 03:20 UTC is 12:20 where the schedule runs, and that is what the log line must show.
    fixed = datetime(2026, 11, 15, 3, 20, tzinfo=UTC)
    monkeypatch.setattr(clock, "now", lambda tz=None: fixed.astimezone(tz or fixed.tzinfo))
    JobLog(job_id)("primeira linha")

    with db.session_scope() as s:
        log = s.get(GenerationJob, job_id).log
    assert log[0] == "[12:20:00] primeira linha"


def test_status_reports_the_schedule_timezone(data_dir):
    from fastapi.testclient import TestClient

    from dayfold import db
    from dayfold.app import app
    from dayfold.settings import get_section, set_section

    with db.session_scope() as s:
        set_section(s, "schedule", {**get_section(s, "schedule").model_dump(), "timezone": "Asia/Tokyo"})

    with TestClient(app) as c:
        body = c.get("/api/auth/status").json()
    # The dashboard renders every date in this zone instead of the browser's.
    assert body["timezone"] == "Asia/Tokyo"
