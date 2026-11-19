"""The day's agenda, read from a read-only iCal feed.

Google Calendar publishes a per-calendar secret iCal address (Settings > your calendar > Secret
address in iCal format), and so do Apple, Outlook and Nextcloud. Reading that address needs no
OAuth app, no API key and no write access, which is the right shape for a home server.

Best effort like the weather: an unreachable feed leaves the page empty, never a broken edition.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta
from typing import NamedTuple
from zoneinfo import ZoneInfo

import icalendar
import recurring_ical_events

from . import net

log = logging.getLogger("dayfold.agenda")

# Google exports a calendar's whole feed, histories and recurrence rules included, so a busy
# calendar runs to several megabytes. The cap only keeps a wrong address from downloading
# something enormous; raising it is cheaper than losing an agenda the user expects to see.
MAX_BYTES = 20 * 1024 * 1024
CANCELLED = {"CANCELLED", "CANCELED"}


class Feed(NamedTuple):
    """One read of a feed: the day's events and the calendar's own name, when it has one."""

    events: list[dict]
    name: str | None


def today(url: str, timezone: str, day: date) -> list[dict] | None:
    """Today's events on the paper's clock, sorted, or ``None`` when the feed cannot be read.

    ``None`` and ``[]`` mean different things to the caller: a feed that failed is worth a log
    line, while an empty day (or a reader with no calendar) simply prints no agenda."""
    if not url:
        return []
    feed = read(url, timezone, day)
    return None if feed is None else feed.events


def read(url: str, timezone: str, day: date) -> Feed | None:
    """Read a feed once for ``day`` on the paper's clock, or ``None`` when it cannot be read.

    The daily generation and the dashboard's "test this address" both come through here, so the
    test exercises exactly the code the paper will run. The name is the feed's own
    ``X-WR-CALNAME`` (Google writes the calendar's name there), never its address."""
    zone = ZoneInfo(timezone)
    start = datetime.combine(day, time.min, tzinfo=zone)
    try:
        calendar = icalendar.Calendar.from_ical(net.fetch(url, max_bytes=MAX_BYTES).content)
        name = " ".join(str(calendar.get("X-WR-CALNAME") or "").split()) or None
        return Feed(events_between(calendar, start, start + timedelta(days=1), zone), name)
    except Exception as exc:  # noqa: BLE001  any failure just means no agenda
        # Never log the exception text: net.fetch puts the URL in it, and the secret address is
        # a bearer credential that must not end up in a log or in the dashboard.
        log.warning("calendar feed unavailable (%s)", type(exc).__name__)
        return None


def events_between(calendar: icalendar.Calendar, start: datetime, end: datetime,
                   zone: ZoneInfo) -> list[dict]:
    """Events overlapping ``[start, end)``, recurring instances expanded, cancellations dropped."""
    found: list[dict] = []
    for event in recurring_ical_events.of(calendar).between(start, end):
        if str(event.get("STATUS") or "").upper() in CANCELLED:
            continue
        begins = event.decoded("DTSTART") if event.get("DTSTART") else None
        if begins is None:
            continue  # no start, nothing to place on a day
        found.append(_out(event, begins, zone))
    found.sort(key=lambda e: (not e["all_day"], e["start"], e["title"].lower()))
    return found


def _out(event, begins: date | datetime, zone: ZoneInfo) -> dict:
    # The title stays as the feed wrote it: an empty one is labelled at typeset, in the paper's
    # language, not here in the server's. Only the start is kept: the end never prints.
    title = " ".join(str(event.get("SUMMARY") or "").split())
    location = " ".join(str(event.get("LOCATION") or "").split()) or None
    if isinstance(begins, datetime):
        return {"title": title, "all_day": False, "start": begins.astimezone(zone).isoformat(),
                "location": location}
    return {"title": title, "all_day": True, "start": begins.isoformat(), "location": location}
