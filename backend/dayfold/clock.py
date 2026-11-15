"""Wall-clock time for the operator.

Stored timestamps are naive UTC and the API sends them with a ``Z`` suffix, so the dashboard
renders them in the browser's own zone. Text the server writes itself is different: a job log
line, the paper's print stamp and the Kindle send record are frozen strings, so they have to be
rendered in the one timezone the operator chose — ``schedule.timezone`` — instead of the
container's clock, which is UTC under Docker.
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
