from fastapi.testclient import TestClient
from sqlalchemy import select

from tests.edition_helpers import add_article, generate


def _rate_latest(c, rule) -> dict:
    ed_id = c.get("/api/overview").json()["latest_edition"]["id"]
    arts = c.get(f"/api/editions/{ed_id}").json()["articles"]
    r = c.put(f"/api/editions/{ed_id}/ratings", json={"ratings": {a["id"]: rule(a) for a in arts}})
    assert r.status_code == 200, r.text
    return r.json()


def test_rating_api_and_learned_summary(data_dir, monkeypatch):
    from dayfold.app import app

    generate(monkeypatch, [("nasa", "Rocket launch to the Moon with astronauts"),
                           ("nasa", "Rocket engine test on the Moon mission"),
                           ("python-insider", "Python release brings faster interpreter"),
                           ("python-insider", "Python packaging survey results")])
    with TestClient(app) as c:
        ov = c.get("/api/overview").json()
        assert ov["latest_ratings"] == {"rated": 0, "total": 4}
        body = _rate_latest(c, lambda a: 1 if "Rocket" in a["title"] else -1)
        assert body["rated"] == 4
        ed_id = ov["latest_edition"]["id"]
        arts = c.get(f"/api/editions/{ed_id}").json()["articles"]
        assert {a["rating"] for a in arts} == {1, -1}
        # clearing one rating, rejecting bad values and foreign stories
        one = arts[0]["id"]
        assert c.put(f"/api/editions/{ed_id}/ratings", json={"ratings": {one: None}}).json()["rated"] == 3
        assert c.put(f"/api/editions/{ed_id}/ratings", json={"ratings": {one: 5}}).status_code == 422
        assert c.put(f"/api/editions/{ed_id}/ratings", json={"ratings": {999999: 1}}).status_code == 400

        fb = c.get("/api/feedback").json()
        assert fb["count"] == 3
        assert "rocket" in [t["name"] for t in fb["more"]["terms"]] or fb["more"]["providers"]
        assert any(p["name"] == "Python Insider" for p in fb["less"]["providers"])

        # ratings survive the deletion of the edition
        assert c.delete(f"/api/editions/{ed_id}").status_code == 200
        assert c.get("/api/feedback").json()["count"] == 3


def test_ratings_steer_the_rule_curation(data_dir, monkeypatch):
    from dayfold.db import session_scope
    from dayfold.models import ArticleRating, Provider, utcnow
    from dayfold.pipeline.curate import candidates, preferences
    from dayfold.settings import get_section, set_section

    with session_scope() as s:
        add_article(s, "nasa", "Rocket launch scheduled for the lunar mission")
        add_article(s, "noaa", "Hurricane season forecast for the Atlantic coast")
    with session_scope() as s:
        pid = {p.slug: p.id for p in s.scalars(select(Provider))}
        for i in range(4):
            s.add(ArticleRating(provider_id=pid["noaa"], section="ciencia", title=f"Hurricane warning {i}",
                                value=1, rated_at=utcnow()))
            s.add(ArticleRating(provider_id=pid["nasa"], section="espaco", title=f"Rocket delay {i}",
                                value=-1, rated_at=utcnow()))

    def scores(use_feedback: bool) -> dict[str, float]:
        with session_scope() as s:
            set_section(s, "curation", {"use_feedback": use_feedback})
            cur = get_section(s, "curation")
            logs: list[str] = []
            cands = candidates(s, cur, logs.append, preferences(s, cur, logs.append))
            return {c.article.title.split()[0]: c.score for c in cands}

    plain, learned = scores(False), scores(True)
    assert learned["Hurricane"] > plain["Hurricane"]
    assert learned["Rocket"] < plain["Rocket"]
