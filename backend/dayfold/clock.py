"""Wall-clock time for the operator.

One timezone belongs to the whole product: ``schedule.timezone``, the zone the operator sets for
the daily run. The dashboard renders its dates in it (the server hands it over in
``/api/auth/status``) and the paper prints its times in it, so both agree.

Stored timestamps are naive UTC and the API sends them with a ``Z`` suffix. Text the server
freezes itself — a job log line, the paper's print stamp, the Kindle send record — cannot be
converted after the fact, so it is rendered here instead of with ``datetime.now()``, which
would read the container's clock (UTC under Docker).
"""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from .db import session_scope
from .settings import get_section


def configured() -> str:
    with session_scope() as s:
        return get_section(s, "schedule").timezone


def zone(timezone: str | None = None) -> ZoneInfo:
    return ZoneInfo(timezone or configured())


def now(timezone: str | ZoneInfo | None = None) -> datetime:
    """The operator's current wall clock, timezone aware."""
    tz = timezone if isinstance(timezone, ZoneInfo) else zone(timezone)
    return datetime.now(tz)


def in_zone(dt: datetime, timezone: str | ZoneInfo | None = None) -> datetime:
    """A stored timestamp as the operator sees it. Naive values are read as UTC."""
    tz = timezone if isinstance(timezone, ZoneInfo) else zone(timezone)
    return (dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt).astimezone(tz)
