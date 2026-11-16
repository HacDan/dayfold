from dayfold.models import UsageMode
from dayfold.pipeline.collect import apply_usage, normalize_url
from dayfold.settings import NewspaperSettings, Typography
from dayfold.sources.base import ScrapedItem, html_to_paragraphs, strip_author

BODY = "\n\n".join(f"Parágrafo {i} com bastante texto para a matéria de teste." for i in range(20))


def item():
    return ScrapedItem(url="https://x.org/a", title="Título", subtitle="Sub", body=BODY, image_url="https://x.org/i.jpg")


def test_metadata_only_keeps_no_text():
    d = apply_usage(item(), UsageMode.METADATA_ONLY, 30)
    assert d["body"] is None and d["excerpt"] is None and d["image_url"] is None


def test_excerpt_mode_drops_body_and_limits_words():
    d = apply_usage(item(), UsageMode.EXCERPT_AND_LINK, 30)
    assert d["body"] is None
    assert len(d["excerpt"].split()) <= 31
    assert d["image_url"] is None


def test_full_mode_keeps_body():
    d = apply_usage(item(), UsageMode.FULL_CONTENT_ALLOWED, 30)
    assert d["body"].startswith("Parágrafo 0")


def test_typography_is_clamped():
    t = Typography(body=9, headline=0.1)
    assert t.body == 1.25 and t.headline == 1.5


def test_closing_order_validation():
    import pytest

    with pytest.raises(ValueError):
        NewspaperSettings(closing_order=["news", "news", "games"])


def test_helpers():
    assert normalize_url("https://www.X.org/a/?utm_source=t&id=2") == "https://x.org/a?id=2"
    assert strip_author("noreply@blogger.com (Python Insider)") == "Python Insider"
    assert strip_author("Por da Agência Senado") == "Agência Senado"
    assert strip_author("courtney.groeneveld") == "Courtney Groeneveld"
    assert html_to_paragraphs("<p>Um</p><script>x</script><p>Dois</p>") == "Um\n\nDois"


def test_a_thin_day_fills_the_paper_with_older_unused_stories(data_dir):
    """Late in the day the fresh pool is spent: the paper tops up, and says how many old ones printed."""
    from datetime import timedelta

    from edition_helpers import add_article
    from sqlalchemy import select

    from dayfold.db import session_scope
    from dayfold.models import Article, utcnow
    from dayfold.pipeline.curate import candidates, curate
    from dayfold.settings import get_section, set_section

    with session_scope() as s:
        set_section(s, "curation", {"max_age_hours": 6})
        add_article(s, "nasa", "Rocket launch to the Moon with astronauts")
        add_article(s, "noaa", "Hurricane season forecast for the Atlantic coast")
        s.scalar(select(Article).where(Article.title.like("Hurricane%"))).published_at = (
            utcnow() - timedelta(days=3))

    logs: list[str] = []
    with session_scope() as s:
        cur = get_section(s, "curation")
        assert {c.article.title.split()[0] for c in candidates(s, cur, logs.append)} == {"Rocket"}

    with session_scope() as s:
        cur = get_section(s, "curation")
        cands = candidates(s, cur, logs.append, limit=8)
    assert {c.article.title.split()[0] for c in cands} == {"Rocket", "Hurricane"}
    assert {c.article.title.split()[0] for c in cands if c.fallback} == {"Hurricane"}

    # The count in the log is what the edition prints, not what the top-up pulled.
    with session_scope() as s:
        curate(s, get_section(s, "newspaper"), get_section(s, "curation"), logs.append)
    assert any("Older stories in this edition: 1" in line or "mais antigas nesta edição: 1" in line
               for line in logs), logs
