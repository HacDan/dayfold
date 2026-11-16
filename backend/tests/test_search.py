"""Archive search: stories already printed in an edition, by title or body text."""

from edition_helpers import generate


def test_search_finds_printed_stories(data_dir, monkeypatch):
    from fastapi.testclient import TestClient

    from dayfold.app import app

    generate(monkeypatch, [("nasa", "Rocket launch to the Moon with astronauts"),
                           ("noaa", "Hurricane season forecast for the Atlantic coast")])

    with TestClient(app) as c:
        found = c.get("/api/search", params={"q": "rocket"}).json()
        assert len(found["hits"]) == 1
        assert found["hits"][0]["title"].startswith("Rocket")
        assert found["hits"][0]["number"] == 1 and found["hits"][0]["section"]
        assert found["hits"][0]["snippet"] and found["more"] is False

        # the body counts too, and the snippet shows the words around the match
        body_hits = c.get("/api/search", params={"q": "long story"}).json()["hits"]
        assert len(body_hits) == 2
        assert "long story" in body_hits[0]["snippet"]

        empty = c.get("/api/search", params={"q": "r"}).json()           # too short to be useful
        assert empty == {"hits": [], "more": False}
        assert c.get("/api/search", params={"q": "zzz"}).json()["hits"] == []
        assert c.get("/api/search", params={"q": "%%"}).json()["hits"] == []  # a literal, not a wildcard


def test_search_ignores_stories_that_never_printed(data_dir, monkeypatch):
    from edition_helpers import add_article
    from fastapi.testclient import TestClient

    from dayfold.app import app
    from dayfold.db import session_scope

    generate(monkeypatch, [("nasa", "Rocket launch to the Moon with astronauts")])
    with session_scope() as s:
        add_article(s, "nasa", "Spare story about a rocket that stayed on the pad")

    with TestClient(app) as c:
        assert len(c.get("/api/search", params={"q": "rocket"}).json()["hits"]) == 1  # the spare stays out


def test_search_says_when_it_stopped_short(data_dir, monkeypatch):
    """A common word must not look like a complete set of results."""
    from fastapi.testclient import TestClient

    from dayfold.api import editions as api
    from dayfold.app import app

    generate(monkeypatch, [("nasa", "Rocket launch to the Moon with astronauts"),
                           ("noaa", "Hurricane season forecast for the Atlantic coast")])
    monkeypatch.setattr(api, "SEARCH_HITS", 1)

    with TestClient(app) as c:
        cut = c.get("/api/search", params={"q": "long story"}).json()
        assert len(cut["hits"]) == 1 and cut["more"] is True
        whole = c.get("/api/search", params={"q": "rocket"}).json()
        assert len(whole["hits"]) == 1 and whole["more"] is False
