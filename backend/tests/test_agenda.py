"""A reader's own day: read from their read-only iCal feed and printed on their own front page.

Recurring events are expanded, all-day entries print before the appointments, cancelled ones are
dropped, and the feed's secret address never leaves the server or reaches a log. Each person in
the household gets the same stories with their own agenda, cover and EPUB.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

SECRET = "https://calendar.example/secret-address.ics"
TZ = "America/Sao_Paulo"

# Wednesday, 18 November 2026, on the paper's clock (UTC-3). Wednesday is 2 in Python.
ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//dayfold//test//EN
X-WR-CALNAME:Personal
BEGIN:VEVENT
UID:allday@dayfold
DTSTART;VALUE=DATE:20261118
DTEND;VALUE=DATE:20261119
SUMMARY:Feriado
END:VEVENT
BEGIN:VEVENT
UID:timed@dayfold
DTSTART:20261118T120000Z
DTEND:20261118T130000Z
SUMMARY:Consulta médica
LOCATION:Clínica
END:VEVENT
BEGIN:VEVENT
UID:weekly@dayfold
DTSTART:20261104T140000Z
DTEND:20261104T150000Z
RRULE:FREQ=WEEKLY;BYDAY=WE
SUMMARY:Reunião semanal
END:VEVENT
BEGIN:VEVENT
UID:tomorrow@dayfold
DTSTART:20261119T120000Z
DTEND:20261119T130000Z
SUMMARY:Amanhã
END:VEVENT
BEGIN:VEVENT
UID:cancelled@dayfold
DTSTART:20261118T150000Z
DTEND:20261118T160000Z
STATUS:CANCELLED
SUMMARY:Cancelado
END:VEVENT
END:VCALENDAR
"""


def test_today_lists_the_day_in_order_and_on_the_papers_clock(monkeypatch):
    from dayfold import agenda

    monkeypatch.setattr(
        agenda.net, "fetch", lambda url, **kw: SimpleNamespace(content=ICS.encode()))

    events = agenda.today(SECRET, TZ, date(2026, 11, 18))

    assert [e["title"] for e in events] == ["Feriado", "Consulta médica", "Reunião semanal"]
    assert events[0]["all_day"] is True
    # 12:00 UTC is 09:00 where the paper is printed, and the recurring instance is expanded.
    assert events[1]["start"] == "2026-11-18T09:00:00-03:00"
    assert events[1]["location"] == "Clínica"
    assert "end" not in events[1]  # only the start is kept: nothing prints an end
    assert events[2]["start"] == "2026-11-18T11:00:00-03:00"


def test_a_broken_feed_reports_failure_without_leaking_the_secret(monkeypatch, caplog):
    from dayfold import agenda, net

    def boom(url, **kw):
        raise net.FetchError(f"HTTP 404 at {url}")

    monkeypatch.setattr(agenda.net, "fetch", boom)
    with caplog.at_level(logging.WARNING):
        assert agenda.today(SECRET, TZ, date(2026, 11, 18)) is None

    assert SECRET not in caplog.text
    assert "secret-address" not in caplog.text


def test_a_reader_without_a_calendar_does_not_fetch(monkeypatch):
    from dayfold import agenda

    def never(url, **kw):
        raise AssertionError("a reader without a calendar must not read one")

    monkeypatch.setattr(agenda.net, "fetch", never)

    assert agenda.today("", TZ, date(2026, 11, 18)) == []


def test_webcal_addresses_are_stored_as_https():
    from pydantic import ValidationError

    from dayfold.api.readers import ReaderIn

    assert ReaderIn(ics_url=" webcal://calendar.example/x.ics ").ics_url == (
        "https://calendar.example/x.ics")
    with pytest.raises(ValidationError):
        ReaderIn(ics_url="ftp://calendar.example/x.ics")


def test_an_empty_or_missing_agenda_prints_nothing():
    from dayfold.edition.i18n import LABELS
    from dayfold.pipeline.generate import _agenda_view

    assert _agenda_view(None, LABELS["en"]) == []
    assert _agenda_view([], LABELS["en"]) == []
    # an event the feed left untitled is labelled in the paper's language, not the server's
    untitled = [{"title": "", "all_day": False, "start": "2026-11-18T09:00:00-03:00",
                 "location": None}]
    assert _agenda_view(untitled, LABELS["en"]) == ["09:00 (no title)"]
    assert _agenda_view(untitled, LABELS["pt"]) == ["09:00 (sem título)"]


def test_an_appointment_prints_where_it_happens():
    from dayfold.edition.i18n import LABELS
    from dayfold.pipeline.generate import _agenda_view

    events = [
        {"title": "Consulta médica", "all_day": False,
         "start": "2026-11-18T09:00:00-03:00", "location": "Clínica São Lucas"},
        {"title": "Consulta médica", "all_day": False,
         "start": "2026-11-18T09:00:00-03:00", "location": None},
        {"title": "Feriado", "all_day": True, "start": "2026-11-18", "location": "Prefeitura"},
    ]

    lines = _agenda_view(events[:1], LABELS["en"])
    assert lines == ["09:00 Consulta médica · Clínica São Lucas"]
    # no location prints nothing; an all-day entry is a line of names, not a venue
    assert _agenda_view(events[1:], LABELS["en"]) == [
        "All day: Feriado",
        "09:00 Consulta médica",
    ]


def test_extra_all_day_entries_are_counted_not_truncated():
    from dayfold.edition.i18n import LABELS
    from dayfold.pipeline.generate import _agenda_view

    events = [{"title": f"Aniversário {i}", "all_day": True, "start": "2026-11-18",
               "location": None} for i in range(6)]

    assert _agenda_view(events, LABELS["en"]) == [
        "All day: Aniversário 0 · Aniversário 1 · Aniversário 2 · and 3 more"]
    assert _agenda_view(events, LABELS["pt"]) == [
        "Dia inteiro: Aniversário 0 · Aniversário 1 · Aniversário 2 · e mais 3"]
    # The two caps count separately: a busy day says on each line what it is not showing.
    busy = events + [{"title": f"Consulta {i}", "all_day": False,
                      "start": f"2026-11-18T09:0{i}:00-03:00", "location": None}
                     for i in range(4)]
    # Two appointments fit; the count for the other two rides on the last one that prints.
    assert _agenda_view(busy, LABELS["en"]) == [
        "All day: Aniversário 0 · Aniversário 1 · Aniversário 2 · and 3 more",
        "09:00 Consulta 0",
        "09:01 Consulta 1 · and 2 more",
    ]


def test_long_all_day_names_keep_the_count_the_cover_would_have_ellipsized():
    from dayfold.edition.cover import agenda_line_fits
    from dayfold.edition.i18n import LABELS
    from dayfold.pipeline.generate import _agenda_view

    names = [
        "Reunião extraordinária do conselho municipal de habitação",
        "Aniversário de casamento com jantar na casa da praia",
        "Formatura da turma de engenharia civil da universidade federal",
    ]
    events = [{"title": n, "all_day": True, "start": "2026-11-18", "location": None}
              for n in names]

    line = _agenda_view(events, LABELS["pt"])[0]

    printed = sum(1 for n in names if n in line)
    assert printed < len(names)  # the names did not all fit on the cover's one line
    # The names the cover cannot print are counted, so nothing is silently lost.
    assert line.endswith(f"e mais {len(names) - printed}")
    assert agenda_line_fits(line)  # and the cover prints it whole, count included

    # A single name longer than the whole line keeps its start and does not break the layout.
    huge = [{"title": "Festa " + "muito concorrida " * 20, "all_day": True,
             "start": "2026-11-18", "location": None}]
    line = _agenda_view(huge, LABELS["pt"])[0]
    assert agenda_line_fits(line) and line.endswith("…")


def test_long_appointments_keep_the_count_the_cover_would_have_ellipsized():
    from dayfold.edition.cover import agenda_line_fits
    from dayfold.edition.i18n import LABELS
    from dayfold.pipeline.generate import _agenda_view

    events = [
        {"title": "Consulta de acompanhamento no hospital das clínicas da capital",
         "all_day": False, "start": "2026-11-18T09:00:00-03:00", "location": "Clínica"},
        {"title": "Reunião extraordinária do conselho municipal de habitação e saneamento básico",
         "all_day": False, "start": "2026-11-18T10:00:00-03:00",
         "location": "Sede da prefeitura, sala 12, segundo andar"},
        {"title": "Formatura da turma", "all_day": False,
         "start": "2026-11-18T19:00:00-03:00", "location": None},
    ]

    lines = _agenda_view(events, LABELS["pt"])

    # The first appointment carries no count, so it prints exactly as before.
    assert lines[0] == (
        "09:00 Consulta de acompanhamento no hospital das clínicas da capital · Clínica")
    # The one that carries the count gives up its venue first, never the count.
    assert lines[1].startswith("10:00 Reunião extraordinária do conselho municipal")
    assert lines[1].endswith("e mais 1") and "Sede da prefeitura" not in lines[1]
    assert agenda_line_fits(lines[1])

    # A title that leaves no room for the count even on its own is cut; the count still prints.
    huge = [
        {"title": "Formatura da turma", "all_day": False,
         "start": "2026-11-18T08:00:00-03:00", "location": None},
        {"title": "Reunião extraordinária do conselho municipal de habitação e saneamento "
                  "básico da região metropolitana inteira, com uma pauta muito longa",
         "all_day": False, "start": "2026-11-18T10:00:00-03:00", "location": None},
        {"title": "Jantar", "all_day": False, "start": "2026-11-18T20:00:00-03:00",
         "location": None},
    ]
    line = _agenda_view(huge, LABELS["pt"])[-1]
    assert line.startswith("10:00 Reunião extraordinária")  # the appointment still reads
    assert line.endswith("e mais 1") and "…" in line
    assert agenda_line_fits(line)


def test_a_long_venue_with_a_long_title_drops_the_venue_and_keeps_the_count():
    from dayfold.edition.cover import agenda_line_fits
    from dayfold.edition.i18n import LABELS
    from dayfold.pipeline.generate import _agenda_view

    events = [
        {"title": "Formatura da turma", "all_day": False,
         "start": "2026-11-18T08:00:00-03:00", "location": "Salão nobre"},
        # Long enough that even time + title + count does not fit: the venue goes, then the title.
        {"title": "Reunião extraordinária do conselho municipal de habitação e saneamento "
                  "básico da região metropolitana inteira, com uma pauta muito longa",
         "all_day": False, "start": "2026-11-18T10:00:00-03:00",
         "location": "Sede da prefeitura, sala 12"},
        {"title": "Jantar", "all_day": False, "start": "2026-11-18T20:00:00-03:00",
         "location": None},
    ]

    lines = _agenda_view(events, LABELS["pt"])
    line = lines[-1]

    assert lines[0].endswith("· Salão nobre")  # a venue that fits still prints
    assert "Sede da prefeitura" not in line  # a venue that cannot print whole goes
    assert line.startswith("10:00 Reunião extraordinária")
    assert "…" in line  # the title is the part that gets cut
    assert line.endswith("e mais 1")
    assert agenda_line_fits(line)


def test_a_large_calendar_is_not_cut_off(monkeypatch):
    """Google exports a calendar's whole feed: the cap must not be the old 2 MB."""
    from dayfold import agenda

    seen: dict = {}

    def fake_fetch(url, **kw):
        seen.update(kw)
        return SimpleNamespace(content=ICS.encode())

    monkeypatch.setattr(agenda.net, "fetch", fake_fetch)
    agenda.today(SECRET, TZ, date(2026, 11, 18))

    assert seen["max_bytes"] >= 10 * 1024 * 1024


def _freeze_today(monkeypatch):
    """The dashboard tests the address against the server's today; pin it to the fixture's day."""
    from dayfold.api import admin

    fixed = datetime(2026, 11, 18, 12, tzinfo=ZoneInfo(TZ))
    monkeypatch.setattr(admin.clock, "now", lambda tz=None: fixed)


def test_read_reports_the_feeds_own_calendar_name(monkeypatch):
    from dayfold import agenda

    monkeypatch.setattr(
        agenda.net, "fetch", lambda url, **kw: SimpleNamespace(content=ICS.encode()))
    feed = agenda.read(SECRET, TZ, date(2026, 11, 18))
    assert feed.name == "Personal" and len(feed.events) == 3

    plain = ICS.replace("X-WR-CALNAME:Personal\n", "")
    monkeypatch.setattr(
        agenda.net, "fetch", lambda url, **kw: SimpleNamespace(content=plain.encode()))
    assert agenda.read(SECRET, TZ, date(2026, 11, 18)).name is None


def test_the_reader_address_is_masked_and_a_blank_save_keeps_it(data_dir):
    from dayfold.app import app

    with TestClient(app) as c:
        first = c.get("/api/readers").json()[0]
        assert first["ics_url_set"] is False and "ics_url" not in first
        saved = c.put(f"/api/readers/{first['id']}",
                      json={"name": "Ana", "ics_url": SECRET, "include_agenda": True}).json()
        assert saved["ics_url_set"] is True and SECRET not in str(saved)
        listed = c.get("/api/readers").json()[0]
        assert listed["ics_url_set"] is True and SECRET not in str(listed)
        # a blank save keeps the stored address instead of wiping it
        c.put(f"/api/readers/{first['id']}", json={"name": "Ana", "ics_url": ""})
        assert c.get("/api/readers").json()[0]["ics_url_set"] is True


def test_a_readers_saved_address_can_be_tested_without_saving_anything(data_dir, monkeypatch):
    from dayfold import agenda
    from dayfold.app import app

    monkeypatch.setattr(
        agenda.net, "fetch", lambda url, **kw: SimpleNamespace(content=ICS.encode()))
    _freeze_today(monkeypatch)

    with TestClient(app) as c:
        rid = c.get("/api/readers").json()[0]["id"]
        assert c.post(f"/api/readers/{rid}/test").json() == {
            "ok": False, "events": None, "calendar": None, "reason": "no_address"}
        c.put(f"/api/readers/{rid}",
              json={"name": "Personal", "include_agenda": False, "ics_url": SECRET})

        res = c.post(f"/api/readers/{rid}/test")

        assert res.status_code == 200
        # all-day + two appointments, with the feed's own calendar name and nothing else
        assert res.json() == {"ok": True, "events": 3, "calendar": "Personal"}
        assert SECRET not in res.text
        # read-only, and the agenda stays off: testing an address is not turning it on
        saved = c.get("/api/readers").json()[0]
        assert saved["include_agenda"] is False and saved["name"] == "Personal"


def test_the_address_test_reports_an_unreadable_feed_without_leaking_it(
        data_dir, monkeypatch, caplog):
    from dayfold import agenda, net
    from dayfold.app import app

    def boom(url, **kw):
        raise net.FetchError(f"HTTP 404 at {url}")

    monkeypatch.setattr(agenda.net, "fetch", boom)
    _freeze_today(monkeypatch)

    with TestClient(app) as c:
        rid = c.get("/api/readers").json()[0]["id"]
        c.put(f"/api/readers/{rid}", json={"ics_url": SECRET})
        with caplog.at_level(logging.WARNING):
            res = c.post(f"/api/readers/{rid}/test")

        assert res.json() == {"ok": False, "events": None, "calendar": None,
                              "reason": "unreadable"}
        assert SECRET not in res.text and "secret-address" not in caplog.text


def test_readers_get_their_own_token_and_the_last_one_cannot_be_deleted(data_dir):
    from dayfold.app import app

    with TestClient(app) as c:
        first = c.get("/api/readers").json()[0]
        second = c.post("/api/readers", json={"name": "Bruno"}).json()
        assert second["token"] != first["token"]
        assert c.delete(f"/api/readers/{first['id']}").status_code == 200
        assert [r["name"] for r in c.get("/api/readers").json()] == ["Bruno"]
        assert c.delete(f"/api/readers/{second['id']}").status_code == 409
        rotated = c.post(f"/api/readers/{second['id']}/rotate-token").json()
        assert rotated["token"] != second["token"]


def test_the_old_single_calendar_becomes_the_first_reader(data_dir):
    from sqlalchemy import select

    from dayfold.bootstrap import bootstrap
    from dayfold.db import session_scope
    from dayfold.models import Reader, Setting

    with session_scope() as s:
        for r in s.scalars(select(Reader)):
            s.delete(r)
        s.merge(Setting(key="calendar", value={"enabled": True, "label": "Personal",
                                               "ics_url": SECRET}))
        s.merge(Setting(key="distribution", value={"feed_token": "legacy-token",
                                                   "keep_editions": 30}))
    bootstrap()
    with session_scope() as s:
        r = s.scalar(select(Reader))
        assert (r.name, r.ics_url, r.include_agenda, r.token) == (
            "Personal", SECRET, True, "legacy-token")


def _printed_edition(s, number: int, day: date, readers: list) -> Path:
    """An edition row plus what typeset leaves on disk: img/, each reader's copy, games.json."""
    from dayfold.models import Edition, ReaderEdition
    from dayfold.pipeline.generate import edition_dir

    folder = edition_dir(day, number)
    (folder / "img").mkdir(parents=True)
    (folder / "dayfold.games.json").write_text("{}")
    for r in readers:
        copy = folder / f"r-{r.id}"
        copy.mkdir()
        (copy / "dayfold.epub").write_bytes(b"paper")
        (copy / "cover.png").write_bytes(b"png")
    first = folder / f"r-{readers[0].id}"
    edition = Edition(number=number, edition_date=day, title="Dayfold", status="READY",
                      epub_path=str(first / "dayfold.epub"),
                      cover_path=str(first / "cover.png"),
                      games_path=str(folder / "dayfold.games.json"))
    s.add(edition)
    s.flush()
    for r in readers:
        copy = folder / f"r-{r.id}"
        s.add(ReaderEdition(edition_id=edition.id, reader_id=r.id,
                            epub_path=str(copy / "dayfold.epub"),
                            cover_path=str(copy / "cover.png")))
    s.flush()
    return folder


def test_pruning_an_edition_removes_every_readers_folder(data_dir):
    from sqlalchemy import select

    from dayfold.db import session_scope
    from dayfold.models import Edition, Reader
    from dayfold.pipeline.generate import _prune
    from dayfold.settings import set_section

    with session_scope() as s:
        set_section(s, "distribution", {"keep_editions": 1})
        s.add(Reader(name="Bruno", position=1))
        s.flush()
        readers = list(s.scalars(select(Reader).order_by(Reader.id)))
        pruned = _printed_edition(s, 1, date(2026, 11, 17), readers)
        kept = _printed_edition(s, 2, date(2026, 11, 18), readers)

    assert pruned.exists() and kept.exists()
    _prune()

    # Pruning takes the edition's whole directory: one leftover reader folder per pruned day
    # would grow on disk forever, with the images and games file of a paper already archived.
    assert not pruned.exists()
    assert all((kept / f"r-{r.id}" / "dayfold.epub").exists() for r in readers)
    with session_scope() as s:
        row = s.scalar(select(Edition).where(Edition.number == 1))
        assert (row.status, row.epub_path) == ("ARCHIVED", None)


def test_deleting_an_edition_removes_every_readers_folder(data_dir):
    from sqlalchemy import select

    from dayfold.app import app
    from dayfold.db import session_scope
    from dayfold.models import Edition, Reader

    with session_scope() as s:
        s.add(Reader(name="Bruno", position=1))
        s.flush()
        readers = list(s.scalars(select(Reader).order_by(Reader.id)))
        folder = _printed_edition(s, 1, date(2026, 11, 18), readers)
        eid = s.scalar(select(Edition.id))
    assert folder.exists()

    with TestClient(app) as c:
        assert c.delete(f"/api/editions/{eid}").status_code == 200

    # Deleting an edition deletes the paper, not just the first reader's copy of it.
    assert not folder.exists()


def test_each_reader_gets_their_own_front_page_cover_and_feed(data_dir, monkeypatch):
    """One edition, one set of stories, and a paper per reader: their agenda, cover and EPUB."""
    from edition_helpers import add_article, capture_cover
    from sqlalchemy import select

    from dayfold.app import app
    from dayfold.db import session_scope
    from dayfold.models import Edition, GenerationJob, Reader
    from dayfold.pipeline import generate as gen
    from dayfold.pipeline.generate import kindle_epub_path
    from dayfold.settings import set_section

    monkeypatch.setattr(gen, "collect_all", lambda log: None)
    covers = capture_cover(monkeypatch)
    agendas = {
        "ana": [{"title": "Feriado municipal", "all_day": True, "start": "2026-11-18",
                 "location": None}],
        "bruno": [{"title": "Consulta médica", "all_day": False,
                   "start": "2026-11-18T09:00:00-03:00", "location": "Clínica"}],
    }
    with session_scope() as s:
        set_section(s, "newspaper", {"include_charge": False, "include_images": False,
                                     "include_games": False, "language": "en"})
        set_section(s, "weather", {"enabled": False})
        set_section(s, "almanac", {"enabled": False})
        # The reader bootstrap creates is the first person; Bruno joins the household.
        ana = s.scalar(select(Reader))
        ana.name, ana.ics_url, ana.include_agenda = "Ana", "https://calendar.example/ana.ics", True
        bruno = Reader(name="Bruno", ics_url="https://calendar.example/bruno.ics", position=1)
        s.add(bruno)
        s.flush()
        ids = {"ana": ana.id, "bruno": bruno.id}
        tokens = {"ana": ana.token, "bruno": bruno.token}
        add_article(s, "nasa", "Telescope maps the edge of the solar system")
        job = GenerationJob()
        s.add(job)
        s.flush()
        job_id = job.id

    monkeypatch.setattr(
        gen.agenda, "today", lambda url, tz, day: agendas["ana" if "ana" in url else "bruno"])
    gen.run_generation_job(job_id)

    agendas_on_covers = {c.agenda_label: c.agenda for c in covers if c.agenda}
    assert agendas_on_covers == {
        "Today's agenda · Ana": ["All day: Feriado municipal"],
        "Today's agenda · Bruno": ["09:00 Consulta médica · Clínica"],
    }
    with session_scope() as s:
        edition = s.scalar(select(Edition))
        copies = {c.reader_id: c for c in edition.copies}
        assert set(copies) == set(ids.values())
        for rid in ids.values():
            epub = Path(copies[rid].epub_path)
            assert epub.exists() and epub.parent.name == f"r-{rid}"
            assert kindle_epub_path(epub, True).exists()
        # the edition's own paths stay the first reader's paper
        first = ids["ana"] if ids["ana"] < ids["bruno"] else ids["bruno"]
        assert edition.epub_path == copies[first].epub_path

    # The snapshot prints again after a re-typeset, in the paper's current language.
    with session_scope() as s:
        set_section(s, "newspaper", {"language": "pt"})
        edition_id = s.scalar(select(Edition.id))
    gen.retypeset(edition_id)
    assert {c.agenda_label: c.agenda for c in covers[-2:] if c.agenda} == {
        "Hoje na agenda · Ana": ["Dia inteiro: Feriado municipal"],
        "Hoje na agenda · Bruno": ["09:00 Consulta médica · Clínica"],
    }

    # Someone who joins after the paper was printed gets nothing, not another person's front page.
    with session_scope() as s:
        carla = Reader(name="Carla", position=2)
        s.add(carla)
        s.flush()
        late_token = carla.token

    with TestClient(app) as c:
        assert c.get(f"/feed/latest.epub?token={late_token}").status_code == 404
        papers = {k: c.get(f"/feed/latest.epub?token={t}").content for k, t in tokens.items()}
        covers_by_reader = {k: c.get(f"/feed/latest.cover.png?token={t}").content
                            for k, t in tokens.items()}
        assert all(papers.values()) and papers["ana"] != papers["bruno"]
        assert covers_by_reader["ana"] != covers_by_reader["bruno"]
        assert c.get("/feed/latest.epub?token=nope").status_code == 401
