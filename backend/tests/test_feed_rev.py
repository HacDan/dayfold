"""Devices decide whether their copy is current from the id and revision in /feed/latest.json.
A re-typeset edition keeps its id and file name, so the revision has to change with the file —
otherwise every reader keeps the old paper forever.
"""

from __future__ import annotations

import os
from datetime import date


def _latest(client, token: str) -> dict:
    return client.get(f"/feed/latest.json?token={token}").json()


def test_latest_json_carries_a_revision_that_follows_the_file(data_dir, tmp_path):
    from fastapi.testclient import TestClient

    from dayfold import db
    from dayfold.app import app
    from dayfold.models import Edition
    from dayfold.settings import get_section

    epub = tmp_path / "dayfold-2026-11-15-0001.epub"
    epub.write_bytes(b"paper")
    with db.session_scope() as s:
        s.add(Edition(number=1, edition_date=date(2026, 11, 15), title="Dayfold",
                      status="READY", epub_path=str(epub)))
    with db.session_scope() as s:
        token = get_section(s, "distribution").feed_token

    with TestClient(app) as c:
        first = _latest(c, token)
        assert first["id"] == "dayfold-2026-11-15-1"
        assert isinstance(first["rev"], int)

        # Re-typesetting rewrites the EPUB: same edition, same name, new revision.
        epub.write_bytes(b"paper, typeset again")
        os.utime(epub, (first["rev"] + 60, first["rev"] + 60))
        again = _latest(c, token)

    assert again["id"] == first["id"]
    assert again["rev"] > first["rev"]
