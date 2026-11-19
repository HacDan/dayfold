from __future__ import annotations

import secrets

from sqlalchemy import select

from .db import init_db, session_scope
from .models import Reader, Setting
from .seed import seed
from .settings import SECTIONS, get_section


def bootstrap() -> None:
    init_db()
    with session_scope() as s:
        seed(s)
        for key in SECTIONS:
            get_section(s, key)
        _first_reader(s)


def _first_reader(s) -> None:
    """A household needs at least one reader, and an install that had the single calendar and
    feed token keeps its address and device link."""
    if s.scalar(select(Reader.id).limit(1)) is not None:
        return
    calendar = s.get(Setting, "calendar")
    cal = calendar.value if calendar and isinstance(calendar.value, dict) else {}
    distribution = s.get(Setting, "distribution")
    dist = distribution.value if distribution and isinstance(distribution.value, dict) else {}
    s.add(Reader(name=str(cal.get("label") or "")[:60],
                 ics_url=str(cal.get("ics_url") or "")[:600],
                 include_agenda=bool(cal.get("enabled", False)),
                 token=str(dist.get("feed_token") or "") or secrets.token_urlsafe(18),
                 position=0))
