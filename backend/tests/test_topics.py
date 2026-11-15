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


def test_delete_is_refused_while_a_provider_feeds_the_section(data_dir):
    """Deletion used to strand the section's slug on its providers, which then matched no topic."""
    from fastapi.testclient import TestClient

    from dayfold.app import app

    with TestClient(app) as c:
        topic = next(t for t in c.get("/api/topics").json() if t["slug"] == "brasil")
        assert any("brasil" in p["categories"] for p in c.get("/api/providers").json())
        r = c.delete(f"/api/topics/{topic['id']}")
        assert r.status_code == 409, r.text
        assert "provedor" in r.json()["detail"]
        assert any(t["id"] == topic["id"] for t in c.get("/api/topics").json())


def test_delete_keeps_old_editions_readable(data_dir):
    """Older editions keep the stored slug; the API must never render it as a raw identifier."""
    from fastapi.testclient import TestClient

    from dayfold.app import app
    from dayfold.db import session_scope
    from dayfold.models import Article, Edition, EditionArticle, Provider

    with session_scope() as s:
        provider = s.scalars(select(Provider).where(Provider.category == "brasil")).first()
        article = Article(provider_id=provider.id, url="https://x.org/d", url_hash="h-del",
                          title="Uma matéria", usage_mode="full_content_allowed")
        s.add(article)
        s.flush()
        edition = Edition(number=2, edition_date=date(2026, 1, 2), title="Dayfold", status="READY")
        s.add(edition)
        s.flush()
        s.add(EditionArticle(edition_id=edition.id, article_id=article.id, section="brasil", position=0))
        edition_id = edition.id
        # a section may only be deleted once nothing feeds it
        for p in s.scalars(select(Provider)):
            if "brasil" in p.sections:
                p.categories = ["mundo" if c == "brasil" else c for c in p.sections]
                if p.category == "brasil":
                    p.category = "mundo"

    with TestClient(app) as c:
        brasil = next(t for t in c.get("/api/topics").json() if t["slug"] == "brasil")
        r = c.delete(f"/api/topics/{brasil['id']}")
        assert r.status_code == 200, r.text
        assert not any(t["slug"] == "brasil" for t in c.get("/api/topics").json())
        items = c.get(f"/api/editions/{edition_id}").json()["articles"]
        assert items[0]["section"] == "brasil"  # history is kept as it was published
        assert items[0]["section_name"] == "Brasil"  # but the slug is never shown raw


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
