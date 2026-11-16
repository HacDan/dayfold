"""Comic feeds: a provider whose usage mode is ``image_only`` prints artwork, not stories.

The feed entry is the whole comic — title, alt text and the image — so nothing else is fetched,
and the edition places the image in the provider's own section like any other article.
"""

import hashlib
from pathlib import Path
from types import SimpleNamespace

FEED = b"""<?xml version="1.0"?><rss version="2.0"><channel><title>Strips</title>
  <item><title>Tiger and boy</title><link>https://example.org/1</link>
    <description><![CDATA[<img src="https://example.org/1.png">A boy argues with a tiger.]]></description></item>
  <item><title>Only words</title><link>https://example.org/2</link>
    <description>An essay, no artwork at all.</description></item>
</channel></rss>"""


def test_image_only_keeps_the_artwork_and_its_alt_text():
    from dayfold.models import UsageMode
    from dayfold.pipeline.collect import apply_usage
    from dayfold.sources.base import ScrapedItem

    item = ScrapedItem(
        url="https://example.org/comic/1", title="Tiger and boy",
        body="A boy argues with a tiger about homework.",
        subtitle="A deck that belongs to a story",
        image_url="https://example.org/comic/1.png", language="en",
    )
    data = apply_usage(item, UsageMode.IMAGE_ONLY, excerpt_words=70)

    assert data["title"] == "Tiger and boy"
    assert data["image_url"] == "https://example.org/comic/1.png"  # the image is the content
    assert data["excerpt"] == "A boy argues with a tiger about homework."  # the alt text
    assert data["body"] is None and data["subtitle"] is None


def test_rss_finds_the_artwork_inside_the_entry_text(monkeypatch):
    """Comic feeds usually put the image in the description; the scraper leaves the rest alone."""
    from dayfold.sources import strategies

    class Client:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(strategies.net, "fetch", lambda url, **kw: SimpleNamespace(content=FEED))
    monkeypatch.setattr(strategies.net, "client", lambda: Client())

    result = strategies.run_strategy("rss", {"feed_url": "https://example.org/feed"},
                                     max_items=5, language="en", want_body=False)

    assert [i.title for i in result.items] == ["Tiger and boy", "Only words"]
    assert result.items[0].image_url == "https://example.org/1.png"
    assert result.items[1].image_url is None


def test_image_only_provider_stores_only_entries_with_artwork(data_dir, monkeypatch):
    """Collection drops the image-less entries, so a text-only feed leaves no empty strips."""
    from sqlalchemy import select

    from dayfold.db import session_scope
    from dayfold.models import Article, Provider, UsageMode
    from dayfold.pipeline import collect as collect_mod
    from dayfold.sources.base import ScrapedItem
    from dayfold.sources.runner import RunOutcome

    items = [
        ScrapedItem(url="https://example.org/1", title="Strip",
                    image_url="https://example.org/1.png", body="A tiger.", language="en"),
        ScrapedItem(url="https://example.org/2", title="Essay", body="No picture.", language="en"),
    ]
    monkeypatch.setattr(collect_mod, "run_isolated",
                        lambda **kw: RunOutcome(ok=True, items=items, log=["ok"]))

    with session_scope() as s:
        p = s.scalar(select(Provider).where(Provider.slug == "nasa"))
        p.usage_mode = UsageMode.IMAGE_ONLY  # seeded providers already carry a ready scraper
        pid = p.id

    lines: list[str] = []
    collect_mod._collect_provider(pid, lines.append, excerpt_words=70)

    with session_scope() as s:
        stored = list(s.scalars(select(Article).where(Article.provider_id == pid)))
    assert [a.title for a in stored] == ["Strip"]
    assert stored[0].image_url == "https://example.org/1.png"
    assert stored[0].excerpt == "A tiger."
    assert any("sem imagem" in line for line in lines)


def test_comic_prints_on_its_own_page(data_dir, monkeypatch):
    from edition_helpers import add_article, epub_text
    from sqlalchemy import select

    from dayfold.db import session_scope
    from dayfold.models import Article, Edition, GenerationJob, Provider, UsageMode, utcnow
    from dayfold.pipeline import generate as gen
    from dayfold.settings import set_section

    monkeypatch.setattr(gen, "collect_all", lambda log: None)
    fetched: list[str] = []

    def fake_photo(url: str, dest: Path, max_width: int) -> Path:
        from PIL import Image

        fetched.append(url)
        Path(dest).parent.mkdir(parents=True, exist_ok=True)
        Image.new("L", (600, 400), 255).save(dest, "JPEG")
        return Path(dest)

    monkeypatch.setattr(gen, "prepare_photo", fake_photo)

    url = "https://example.org/comic/1"
    with session_scope() as s:
        set_section(s, "newspaper", {"include_charge": False, "include_images": False,
                                     "include_games": False, "language": "en"})
        # a story to lead the paper, and a comic feed with a section of its own
        add_article(s, "nasa", "Telescope maps the edge of the solar system")
        comic = Provider(slug="tiras", name="Tiras", base_url="https://example.org",
                         source_type="rss", category="quadrinhos", categories=["quadrinhos"],
                         language="en", usage_mode=UsageMode.IMAGE_ONLY)
        s.add(comic)
        s.flush()
        s.add(Article(
            provider_id=comic.id, url=url, url_hash=hashlib.sha1(url.encode()).hexdigest(),
            title="Telescope, the space tiger", body=None,
            excerpt="A boy argues with a tiger about homework.",
            image_url="https://example.org/comic/1.png", usage_mode=UsageMode.IMAGE_ONLY,
            language="en", category="quadrinhos", published_at=utcnow(), collected_at=utcnow(),
        ))
        job = GenerationJob()
        s.add(job)
        s.flush()
        job_id = job.id

    gen.run_generation_job(job_id)

    with session_scope() as s:
        edition = s.scalar(select(Edition).order_by(Edition.id.desc()).limit(1))
        sections = sorted(i.section for i in edition.items)
        epub = Path(edition.epub_path)
    text = epub_text(epub)

    # The strip prints on a page of its own, laid out like the cartoon: strip name, title, artwork.
    assert 'class="comic-page"' in text
    assert '<p class="kicker">Tiras</p>' in text  # the provider names the strip
    assert "<h1>Telescope, the space tiger</h1>" in text
    assert 'class="charge"' in text and 'src="images/a' in text
    assert '<p class="caption">A boy argues with a tiger about homework.</p>' in text  # the alt text
    # Its own section, not matched by keyword; that section has no story page of its own.
    assert sections == ["espaco", "quadrinhos"]
    assert 'class="article headline"' in text  # the story leads the front page
    # The artwork is fetched even though story photos are off in these settings.
    assert fetched == ["https://example.org/comic/1.png"]


def test_comics_section_reaches_installs_seeded_before_it(data_dir):
    """The section is a default, not a migration of the paper: older installs get just this one."""
    from sqlalchemy import delete, select

    from dayfold.db import session_scope
    from dayfold.models import Setting, Topic
    from dayfold.seed import seed

    with session_scope() as s:
        s.execute(delete(Topic).where(Topic.slug == "quadrinhos"))
        row = s.get(Setting, "migrations")
        row.value = {"done": [d for d in row.value["done"] if d != "comics_section"]}

    with session_scope() as s:
        seed(s)

    with session_scope() as s:
        assert s.scalars(select(Topic).where(Topic.slug == "quadrinhos")).one().name == "Quadrinhos"


def _comic_provider(s, slug: str = "tiras", category: str = "cultura", sections: list[str] | None = None):
    from dayfold.models import Provider, UsageMode

    provider = Provider(slug=slug, name=slug.title(), base_url="https://example.org",
                        source_type="rss", category=category, categories=sections or [],
                        language="en", usage_mode=UsageMode.IMAGE_ONLY)
    s.add(provider)
    s.flush()
    return provider


def _comic(s, provider, title: str = "Telescope, the space tiger") -> int:
    from dayfold.models import Article, UsageMode, utcnow

    url = "https://example.org/comic/1"
    article = Article(
        provider_id=provider.id, url=url, url_hash=hashlib.sha1(url.encode()).hexdigest(),
        title=title, body=None, excerpt="A boy argues with a tiger about homework.",
        image_url="https://example.org/comic/1.png", usage_mode=UsageMode.IMAGE_ONLY,
        language="en", category=provider.category, published_at=utcnow(), collected_at=utcnow(),
    )
    s.add(article)
    s.flush()
    return article.id


def _candidates(session):
    from dayfold.pipeline.curate import candidates
    from dayfold.settings import get_section

    return candidates(session, get_section(session, "curation"), lambda m: None)


def test_strip_without_section_chips_prints_in_its_category(data_dir):
    """A comic provider with no chips yet still prints, under the section it is filed in."""
    from dayfold.db import session_scope

    with session_scope() as s:
        _comic(s, _comic_provider(s, category="cultura"))

    with session_scope() as s:
        assert [c.section for c in _candidates(s)] == ["cultura"]


def test_ai_selection_cannot_lead_with_a_comic(data_dir, monkeypatch):
    from edition_helpers import add_article
    from sqlalchemy import select

    from dayfold.db import session_scope
    from dayfold.models import Article
    from dayfold.pipeline import curate as cur_mod
    from dayfold.settings import get_section

    with session_scope() as s:
        add_article(s, "nasa", "Telescope maps the edge of the solar system")
        add_article(s, "nasa", "Rover finds ice under the dust of Mars")
        add_article(s, "nasa", "Orbit raises the space station higher")
        comic_id = _comic(s, _comic_provider(s))

    class FakeAI:
        label = "Fake AI"

        def complete_json(self, prompt, schema, max_tokens=0):
            # the AI puts the strip on the front page; the paper should refuse
            return schema(headline_id=comic_id,
                          selected=[{"id": c.article.id, "section": c.section, "priority": 1}
                                    for c in cands])

    monkeypatch.setattr(cur_mod, "active_client", lambda session: FakeAI())

    with session_scope() as s:
        cands = _candidates(s)
        picks = cur_mod.ai_select(s, cands, get_section(s, "newspaper"),
                                  get_section(s, "curation"), lambda m: None)

    assert picks is not None and len(picks) == 4
    heads = [p for p in picks if p.is_headline]
    assert len(heads) == 1  # the comic keeps its slot, but not the front page
    assert heads[0].article_id != comic_id
    with session_scope() as s:
        assert s.scalar(select(Article.usage_mode).where(Article.id == heads[0].article_id)) != "image_only"


def test_changing_the_mode_updates_stories_already_collected(data_dir, monkeypatch):
    """A strip collected before the provider became image-only must stop printing as a story."""
    from sqlalchemy import select

    from dayfold.db import session_scope
    from dayfold.models import Article, Provider, UsageMode, utcnow
    from dayfold.pipeline import collect as collect_mod
    from dayfold.sources.base import ScrapedItem
    from dayfold.sources.runner import RunOutcome

    url = "https://example.org/comic/1"
    with session_scope() as s:
        p = s.scalar(select(Provider).where(Provider.slug == "nasa"))
        p.usage_mode = UsageMode.IMAGE_ONLY  # stored while the provider was full content
        s.add(Article(provider_id=p.id, url=url, url_hash=hashlib.sha1(url.encode()).hexdigest(),
                      title="Family Circus for Sun, 15 Nov 2026", language="en",
                      image_url="https://example.org/comic/1.png", usage_mode=UsageMode.FULL_CONTENT_ALLOWED,
                      body="Subscribe\n\nBy clicking submit, I authorize marketing.",
                      excerpt="Subscribe", category=p.category,
                      published_at=utcnow(), collected_at=utcnow()))
        pid = p.id

    item = ScrapedItem(url=url, title="Family Circus for Sun, 15 Nov 2026",
                       body="Two panels of family life.", excerpt="A boy argues with a tiger.",
                       image_url="https://example.org/comic/1.png", language="en")
    monkeypatch.setattr(collect_mod, "run_isolated",
                        lambda **kw: RunOutcome(ok=True, items=[item], log=["ok"]))

    lines: list[str] = []
    collect_mod._collect_provider(pid, lines.append, excerpt_words=70)

    with session_scope() as s:
        a = s.scalars(select(Article).where(Article.url_hash == hashlib.sha1(url.encode()).hexdigest())).one()
        assert a.usage_mode == UsageMode.IMAGE_ONLY
        assert a.body is None and a.subtitle is None  # the feed boilerplate is gone
        assert a.excerpt == "A boy argues with a tiger."  # the alt text
        assert a.image_url == "https://example.org/comic/1.png"
    assert any("1 atualizadas" in line or "1 updated" in line for line in lines)


def test_a_used_strip_still_prints_in_the_next_edition(data_dir):
    """A paper regenerated the same day keeps its comic; a used story stays used."""
    from datetime import date

    from sqlalchemy import select

    from dayfold.db import session_scope
    from dayfold.models import Article, Edition, EditionArticle, Provider, UsageMode, utcnow

    with session_scope() as s:
        tiras = _comic_provider(s, category="quadrinhos", sections=["quadrinhos"])
        comic_id = _comic(s, tiras)
        nasa = s.scalar(select(Provider).where(Provider.slug == "nasa"))
        story = Article(provider_id=nasa.id, url="https://example.org/story",
                        url_hash=hashlib.sha1(b"story").hexdigest(), title="A used story",
                        body="Body.", usage_mode=UsageMode.FULL_CONTENT_ALLOWED, language="en",
                        category="espaco", published_at=utcnow(), collected_at=utcnow())
        s.add(story)
        s.flush()
        ed = Edition(number=1, edition_date=date(2026, 11, 15), title="Dayfold", status="READY")
        s.add(ed)
        s.flush()
        for i, aid in enumerate((comic_id, story.id)):
            s.add(EditionArticle(edition_id=ed.id, article_id=aid, section="quadrinhos", position=i))

    with session_scope() as s:
        found = {c.article.id for c in _candidates(s)}
    assert comic_id in found
    assert story.id not in found


def test_the_artwork_alt_text_is_the_caption_not_the_feed_link_label(monkeypatch):
    """comicsrss-style feeds: the description is only a "Source" link; the alt text is the caption."""
    from dayfold.models import UsageMode
    from dayfold.pipeline.collect import apply_usage
    from dayfold.sources import strategies

    feed = b"""<?xml version="1.0"?><rss version="2.0"><channel><title>Strips</title>
      <item><title>Family Circus for Sun, 15 Nov 2026</title><link>https://example.org/1</link>
        <description><![CDATA[<p><img src="https://example.org/1.gif" alt="A boy argues with a tiger"></p>
          <p><a href="https://example.org/1">Source</a></p>]]></description></item>
    </channel></rss>"""

    class Client:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(strategies.net, "fetch", lambda url, **kw: SimpleNamespace(content=feed))
    monkeypatch.setattr(strategies.net, "client", lambda: Client())

    items = strategies.run_strategy("rss", {"feed_url": "https://example.org/feed"},
                                    max_items=5, language="en", want_body=False).items
    assert items[0].image_alt == "A boy argues with a tiger"

    data = apply_usage(items[0], UsageMode.IMAGE_ONLY, excerpt_words=70)
    assert data["excerpt"] == "A boy argues with a tiger"
    assert data["image_url"] == "https://example.org/1.gif"


def test_a_caption_that_only_repeats_the_title_is_dropped():
    from dayfold.models import UsageMode
    from dayfold.pipeline.collect import apply_usage
    from dayfold.sources.base import ScrapedItem

    title = "Family Circus by Bil Keane on Sun, 15 Nov 2026"
    item = ScrapedItem(url="https://example.org/1", title=title, image_url="https://example.org/1.gif",
                       image_alt=title, body="Source")
    data = apply_usage(item, UsageMode.IMAGE_ONLY, excerpt_words=70)

    assert data["excerpt"] is None  # printing the title twice would be worse than no caption
    assert data["image_url"] == "https://example.org/1.gif"
