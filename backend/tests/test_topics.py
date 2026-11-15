"""Renaming a section slug has to carry its references: providers and older editions store it."""

from datetime import date

from sqlalchemy import select


def test_slug_rename_moves_providers_and_editions(data_dir):
    from fastapi.testclient import TestClient

    from dayfold.app import app
    from dayfold.db import session_scope
    from dayfold.models import Article, Edition, EditionArticle, Provider

    with session_scope() as s:
        provider = s.scalars(select(Provider).where(Provider.category == "brasil")).first()
        article = Article(provider_id=provider.id, url="https://x.org/a", url_hash="h-1",
                          title="Uma matéria", usage_mode="full_content_allowed")
        s.add(article)
        s.flush()
        edition = Edition(number=1, edition_date=date(2026, 1, 1), title="Dayfold",
                          status="READY")
        s.add(edition)
        s.flush()
        s.add(EditionArticle(edition_id=edition.id, article_id=article.id,
                             section="brasil", position=0))
        provider_id = provider.id

    with TestClient(app) as c:
        brasil = next(t for t in c.get("/api/topics").json() if t["slug"] == "brasil")
        r = c.put(f"/api/topics/{brasil['id']}", json={**brasil, "slug": "vermont", "name": "Vermont"})
        assert r.status_code == 200, r.text
        assert r.json()["slug"] == "vermont" and r.json()["name"] == "Vermont"
        provider = next(p for p in c.get("/api/providers").json() if p["id"] == provider_id)
        assert provider["category"] == "vermont"
        assert "vermont" in (provider["categories"] or [])

    with session_scope() as s:
        assert s.scalars(select(EditionArticle)).one().section == "vermont"


def test_slug_rename_rejects_duplicates(data_dir):
    from fastapi.testclient import TestClient

    from dayfold.app import app

    with TestClient(app) as c:
        first, second = c.get("/api/topics").json()[:2]
        r = c.put(f"/api/topics/{second['id']}", json={**second, "slug": first["slug"]})
        assert r.status_code == 409
        # the rejected update must not have written anything
        assert c.get("/api/topics").json()[1]["slug"] == second["slug"]


def test_slug_rename_keeps_the_same_topic(data_dir):
    from fastapi.testclient import TestClient

    from dayfold.app import app

    with TestClient(app) as c:
        before = c.get("/api/topics").json()
        topic = before[0]
        r = c.put(f"/api/topics/{topic['id']}", json={**topic, "slug": "manchete"})
        assert r.status_code == 200
        assert r.json()["id"] == topic["id"]
        after = c.get("/api/topics").json()
        assert len(after) == len(before)  # renamed, not recreated
        assert sum(1 for t in after if t["slug"] == "manchete") == 1
