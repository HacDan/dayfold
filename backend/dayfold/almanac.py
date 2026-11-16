"""Almanac: the moon and what happened on this day, printed under the weather.

The moon is arithmetic. The day's event comes from Wikipedia's REST feed, which needs no key or
account; when it cannot be had the moon still prints, so the block degrades instead of vanishing.
"""

from __future__ import annotations

import json
import logging
import math
from datetime import date

from . import net
from .settings import AlmanacSettings

log = logging.getLogger("dayfold.almanac")

ONTHISDAY_URL = "https://api.wikimedia.org/feed/v1/wikipedia/{lang}/onthisday/selected/{month}/{day}"
SYNODIC_DAYS = 29.530588853
EPOCH = date(2000, 1, 6)  # a known new moon, 18:14 UTC
PAPER_LANGS = ("pt", "en")  # every language the paper can be printed in

# Eight phases, each ending at a point of the cycle: (end, pt, en).
PHASES: list[tuple[float, str, str]] = [
    (0.03, "Lua nova", "New moon"),
    (0.22, "Lua crescente", "Waxing crescent"),
    (0.28, "Quarto crescente", "First quarter"),
    (0.47, "Crescente gibosa", "Waxing gibbous"),
    (0.53, "Lua cheia", "Full moon"),
    (0.72, "Minguante gibosa", "Waning gibbous"),
    (0.78, "Quarto minguante", "Last quarter"),
    (1.01, "Minguante", "Waning crescent"),
]


def moon(day: date) -> dict:
    """Phase index and illuminated percentage for a date: no service, no key."""
    age = ((day - EPOCH).days % SYNODIC_DAYS) / SYNODIC_DAYS
    phase = next((i for i, (end, _, _) in enumerate(PHASES) if age < end), len(PHASES) - 1)
    return {"phase": phase, "illuminated": round((1 - math.cos(2 * math.pi * age)) / 2 * 100)}


def moon_label(phase: int | None, lang: str = "pt") -> str:
    _, pt, en = PHASES[phase if phase is not None else 0]
    return pt if lang == "pt" else en


def on_this_day(day: date, lang: str = "pt") -> dict | None:
    """One dated event from Wikipedia's feed for the day, shortened to a line."""
    url = ONTHISDAY_URL.format(lang="pt" if lang == "pt" else "en", month=day.month, day=day.day)
    try:
        events = json.loads(net.fetch(url).content).get("selected") or []
    except Exception as exc:  # noqa: BLE001  the moon alone is reason enough to print the block
        log.warning("almanac for %s unavailable: %s", day, exc)
        return None
    for event in events:
        text = (event.get("text") or "").strip()
        if text and event.get("year"):
            return {"year": int(event["year"]), "text": _shorten(text)}
    return None


def today(day: date, cfg: AlmanacSettings) -> dict | None:
    """The almanac snapshot for an edition, or ``None`` when the block is switched off.

    The day's event is fetched once per paper language and stored that way, so a re-typeset in the
    other language reads in that language without going back to Wikipedia.
    """
    if not cfg.enabled:
        return None
    snapshot: dict = {"moon": moon(day)}
    if cfg.on_this_day:
        events = {lang: event for lang in PAPER_LANGS if (event := on_this_day(day, lang))}
        if events:
            snapshot["event"] = events
    return snapshot


def _shorten(text: str, words: int = 22) -> str:
    parts = text.split()
    return text if len(parts) <= words else " ".join(parts[:words]).rstrip(" ,;:.") + "…"
