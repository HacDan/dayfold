"""The almanac block: the moon computed locally, the day's event from Wikipedia, no key."""

import json
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

from dayfold import almanac
from dayfold.settings import AlmanacSettings

EVENTS = {"selected": [
    {"year": 2012, "text": "Xi Jinping replaced Hu Jintao as General Secretary."},
    {"text": "An event with no year, which cannot be printed."},
]}


def _serve(monkeypatch, payload=EVENTS) -> list[str]:
    seen: list[str] = []

    def fake_fetch(url: str, **kw):
        seen.append(url)
        return SimpleNamespace(content=json.dumps(payload).encode())

    monkeypatch.setattr(almanac.net, "fetch", fake_fetch)
    return seen


def test_the_moon_comes_from_arithmetic():
    """No service, no key: the phase is computed from a known new moon."""
    assert almanac.moon(almanac.EPOCH) == {"phase": 0, "illuminated": 0}
    assert almanac.moon(almanac.EPOCH + timedelta(days=round(almanac.SYNODIC_DAYS / 2))) == {
        "phase": 4, "illuminated": 100}
    quarter = almanac.moon(almanac.EPOCH + timedelta(days=round(almanac.SYNODIC_DAYS / 4)))
    assert quarter["phase"] == 2  # first quarter


def test_moon_labels_follow_the_paper():
    assert almanac.moon_label(4, "en") == "Full moon"
    assert almanac.moon_label(4, "pt") == "Lua cheia"
    assert almanac.moon_label(None, "en") == "New moon"  # never a blank line


def test_on_this_day_picks_the_first_dated_event(monkeypatch):
    seen = _serve(monkeypatch)
    assert almanac.on_this_day(date(2026, 11, 15), "en") == {
        "year": 2012, "text": "Xi Jinping replaced Hu Jintao as General Secretary."}
    assert "/en/onthisday/selected/11/15" in seen[0]


def test_on_this_day_gives_up_quietly(monkeypatch):
    def broken(*a, **kw):
        raise almanac.net.FetchError("offline")

    monkeypatch.setattr(almanac.net, "fetch", broken)
    assert almanac.on_this_day(date(2026, 11, 15), "en") is None
    # the moon still prints: the block degrades, it does not vanish
    snapshot = almanac.today(date(2026, 11, 15), AlmanacSettings(enabled=True))
    assert snapshot is not None and "event" not in snapshot


def test_events_are_snapshotted_in_both_paper_languages(monkeypatch):
    """So a re-typeset in the other language reads in that language, like the weather condition."""
    calls: list[str] = []

    def fake_fetch(url: str, **kw):
        calls.append(url)
        text = ("Xi Jinping substituiu Hu Jintao." if "/pt/" in url
                else "Xi Jinping replaced Hu Jintao.")
        return SimpleNamespace(content=json.dumps({"selected": [{"year": 2012, "text": text}]}).encode())

    monkeypatch.setattr(almanac.net, "fetch", fake_fetch)
    snapshot = almanac.today(date(2026, 11, 15), AlmanacSettings(enabled=True))

    assert snapshot["event"]["en"]["text"].startswith("Xi Jinping replaced")
    assert snapshot["event"]["pt"]["text"].startswith("Xi Jinping substituiu")
    assert len(calls) == 2  # one per language, at generation, not at typeset


def test_long_events_are_shortened_to_a_line():
    long = " ".join(f"word{i}" for i in range(40))
    assert almanac._shorten(long).count("word") == 22
    assert almanac._shorten(long).endswith("…")


def test_the_switch_controls_the_block(monkeypatch):
    _serve(monkeypatch)
    day = date(2026, 11, 15)
    assert almanac.today(day, AlmanacSettings(enabled=False)) is None
    moon_only = almanac.today(day, AlmanacSettings(enabled=True, on_this_day=False))
    assert moon_only is not None and "event" not in moon_only


def test_the_cover_prints_the_almanac(data_dir, monkeypatch):
    """Moon and event are snapshotted with the edition, printed on the cover, Wikipedia credited."""
    from edition_helpers import add_article, capture_cover, epub_text
    from sqlalchemy import select

    from dayfold.db import session_scope
    from dayfold.models import Edition, GenerationJob
    from dayfold.pipeline import generate as gen
    from dayfold.settings import set_section

    monkeypatch.setattr(gen, "collect_all", lambda log: None)
    covers = capture_cover(monkeypatch)
    monkeypatch.setattr(gen.almanac, "today", lambda day, cfg: {
        "moon": {"phase": 4, "illuminated": 99},
        "event": {"en": {"year": 2012, "text": "Xi Jinping replaced Hu Jintao."},
                  "pt": {"year": 2012, "text": "Xi Jinping substituiu Hu Jintao."}},
    })

    def build(language: str) -> tuple[list[str] | None, str]:
        with session_scope() as s:
            set_section(s, "newspaper", {"include_charge": False, "include_images": False,
                                         "include_games": False, "language": language})
            set_section(s, "weather", {"enabled": False})
            set_section(s, "almanac", {"enabled": True})
            add_article(s, "nasa", f"Telescope maps the edge of the solar system ({language})")
            job = GenerationJob()
            s.add(job)
            s.flush()
            job_id = job.id
        gen.run_generation_job(job_id)
        with session_scope() as s:
            edition = s.scalar(select(Edition).order_by(Edition.id.desc()).limit(1))
            return covers[-1].almanac, epub_text(Path(edition.epub_path))

    lines, text = build("en")
    assert lines == ["Moon: Full moon · 99% illuminated",
                     "On this day: 2012 · Xi Jinping replaced Hu Jintao."]
    assert "Almanac: Wikipedia (CC BY-SA 4.0)." in text

    # the same snapshot, printed in Portuguese: the event follows the paper, not the fetch
    portuguese, _ = build("pt")
    assert portuguese[1] == "Neste dia: 2012 · Xi Jinping substituiu Hu Jintao."
