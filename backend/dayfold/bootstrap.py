from __future__ import annotations

from .db import init_db, session_scope
from .seed import seed
from .settings import SECTIONS, get_section


def bootstrap() -> None:
    init_db()
    with session_scope() as s:
        seed(s)
        for key in SECTIONS:
            get_section(s, key)
