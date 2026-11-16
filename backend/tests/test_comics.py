"""Comic feeds: a provider whose usage mode is ``image_only`` prints artwork, not stories.

The feed entry is the whole comic — title, alt text and the image — so nothing else is fetched,
and the edition prints it on a page of its own, in the section its provider declares.
"""

import hashlib
import io
from pathlib import Path
from types import SimpleNamespace

FEED = b"""<?xml version="1.0"?><rss version="2.0"><channel><title>Strips</title>
  <item><title>Tiger and boy</title><link>https://example.org/1</link>
    <description><![CDATA[<img src="https://example.org/1.png">A boy argues with a tiger.]]></description></item>
  <item><title>Only words</title><link>https://example.org/2</link>
    <description>An essay, no artwork at all.</description></item>
</channel></rss>"""


class _Client:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _serve(monkeypatch, feed: bytes) -> None:
    """Point the network at one inline feed."""
    from dayfold.sources import strategies

    monkeypatch.setattr(strategies.net, "fetch", lambda url, **kw: SimpleNamespace(content=feed))
    monkeypatch.setattr(strategies.net, "client", _Client)


def _rss(monkeypatch, feed: bytes):
    """The RSS strategy over an inline feed."""
    from dayfold.sources import strategies

    _serve(monkeypatch, feed)
    return strategies.run_strategy("rss", {"feed_url": "https://example.org/feed"},
                                   max_items=5, language="en", want_body=False)


def _comic_provider(s, slug: str = "tiras", category: str = "cultura",
                    sections: list[str] | None = None, feed_title: str | None = None):
    from dayfold.models import Provider, UsageMode

    provider = Provider(slug=slug, name=slug.title(), base_url="https://example.org",
                        source_type="rss", category=category, categories=sections or [],
                        language="en", usage_mode=UsageMode.IMAGE_ONLY, feed_title=feed_title)
    s.add(provider)
    s.flush()
    return provider


def _comic(s, provider, title: str = "Telescope, the space tiger",
           excerpt: str | None = "A boy argues with a tiger about homework.", n: int = 1) -> int:
    from dayfold.models import Article, UsageMode, utcnow

    url = f"https://example.org/comic/{n}"
    article = Article(
        provider_id=provider.id, url=url, url_hash=hashlib.sha1(url.encode()).hexdigest(),
        title=title, body=None, excerpt=excerpt,
        image_url=f"https://example.org/comic/{n}.png", usage_mode=UsageMode.IMAGE_ONLY,
        language="en", category=provider.category, published_at=utcnow(), collected_at=utcnow(),
    )
    s.add(article)
    s.flush()
    return article.id


def _candidates(session):
    from dayfold.pipeline.curate import candidates
    from dayfold.settings import get_section

    return candidates(session, get_section(session, "curation"), lambda m: None)


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
    items = _rss(monkeypatch, FEED).items

    assert [i.title for i in items] == ["Tiger and boy", "Only words"]
    assert items[0].image_url == "https://example.org/1.png"
    assert items[1].image_url is None


def test_the_channel_title_survives_the_isolated_run(monkeypatch):
    """The worker writes the name and the runner reads it: neither end may drop it."""
    import json
    import sys

    from dayfold.sources import runner, worker

    _serve(monkeypatch, FEED)
    job = {"strategy": "rss", "spec": {"feed_url": "https://example.org/feed"},
           "max_items": 5, "language": "en", "want_body": False}
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(job)))
    out = io.StringIO()
    monkeypatch.setattr(sys, "stdout", out)

    worker.main()

    # The runner turns that stdout into the outcome the collector stores: a name lost on either
    # side of the pipe shows up as None here.
    monkeypatch.setattr(runner.subprocess, "run",
                        lambda *a, **kw: SimpleNamespace(returncode=0, stdout=out.getvalue(), stderr=""))
    assert runner.run_isolated("rss", job["spec"], want_body=False).feed_title == "Strips"


def test_rss_resolves_a_relative_artwork_url(monkeypatch):
    """Feeds may point at the artwork relatively; what reaches the pipeline must be fetchable."""
    feed = b"""<?xml version="1.0"?><rss version="2.0" xmlns:media="http://search.yahoo.com/mrss/">
    <channel><title>Strips</title>
      <item><title>In the text</title><link>https://example.org/comics/1</link>
        <description><![CDATA[<img src="/art/1.png" alt="A tiger">]]></description></item>
      <item><title>In media</title><link>https://example.org/comics/2</link>
        <media:content url="../art/2.png" medium="image"/></item>
    </channel></rss>"""

    items = _rss(monkeypatch, feed).items

    assert [i.image_url for i in items] == ["https://example.org/art/1.png",
                                            "https://example.org/art/2.png"]


def test_rss_reads_the_channel_title(monkeypatch):
    """The channel title is what the strip is called; a feed without one has nothing to offer."""
    assert _rss(monkeypatch, FEED).feed_title == "Strips"
    assert _rss(monkeypatch, FEED.replace(b"<title>Strips</title>", b"")).feed_title is None


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
                        lambda **kw: RunOutcome(ok=True, items=items, log=["ok"],
                                                feed_title="Family Circus"))

    with session_scope() as s:
        p = s.scalar(select(Provider).where(Provider.slug == "nasa"))
        p.usage_mode = UsageMode.IMAGE_ONLY  # seeded providers already carry a ready scraper
        pid = p.id

    lines: list[str] = []
    collect_mod._collect_provider(pid, lines.append, excerpt_words=70)

    with session_scope() as s:
        stored = list(s.scalars(select(Article).where(Article.provider_id == pid)))
        feed_title = s.scalar(select(Provider).where(Provider.id == pid)).feed_title
    assert feed_title == "Family Circus"  # printed as the strip's name
    assert [a.title for a in stored] == ["Strip"]
    assert stored[0].image_url == "https://example.org/1.png"
    assert stored[0].excerpt == "A tiger."
    assert any("sem imagem" in line for line in lines)


def test_a_strip_headlines_the_day_not_its_own_name():
    """The kicker names the strip and the artwork signs the artist, so the headline keeps the day."""
    from dayfold.pipeline.generate import _comic_headline

    assert _comic_headline("Family Circus by Bil Keane for Sun, 15 Nov 2026",
                           "Family Circus") == "Sun, 15 Nov 2026"
    assert _comic_headline("Family Circus for Sun, 15 Nov 2026", "Family Circus") == "Sun, 15 Nov 2026"
    assert _comic_headline("Family Circus: Zoo time", "Family Circus") == "Zoo time"
    # Nothing that is not that prefix is touched, and the name alone is not erased.
    assert _comic_headline("Telescope, the space tiger", "Family Circus") == "Telescope, the space tiger"
    assert _comic_headline("Family Circus", "Family Circus") == "Family Circus"


def test_comic_prints_on_its_own_page(data_dir, monkeypatch):
    """The strip prints alone, like the cartoon, and its alt text describes the artwork."""
    from edition_helpers import add_article, epub_text
    from sqlalchemy import select

    from dayfold.db import session_scope
    from dayfold.models import Edition, GenerationJob
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

    with session_scope() as s:
        set_section(s, "newspaper", {"include_charge": False, "include_images": False,
                                     "include_games": False, "language": "en"})
        add_article(s, "nasa", "Telescope maps the edge of the solar system")  # leads the paper
        tiras = _comic_provider(s, category="quadrinhos", sections=["quadrinhos"],
                                feed_title="Family Circus")
        # Titled the way comic feeds do it: strip name, author, then the day.
        _comic(s, tiras, title="Family Circus by Bil Keane for Sun, 15 Nov 2026", n=1)
        other = _comic_provider(s, "outra", "quadrinhos", ["quadrinhos"])  # no channel title
        _comic(s, other, title="Outra by Someone for Sun, 15 Nov 2026", excerpt=None, n=2)
        job = GenerationJob()
        s.add(job)
        s.flush()
        job_id = job.id

    gen.run_generation_job(job_id)

    with session_scope() as s:
        edition = s.scalar(select(Edition).order_by(Edition.id.desc()).limit(1))
        sections = sorted({i.section for i in edition.items})
        epub = Path(edition.epub_path)
    text = epub_text(epub)

    # Each strip gets a page of its own, laid out like the cartoon: strip name, title, artwork.
    assert text.count('class="comic-page"') == 2
    assert '<p class="kicker">Family Circus</p>' in text  # the strip's own name
    assert '<p class="kicker">Outra</p>' in text  # no channel title: the provider name stands in
    # The headline prints the day: the kicker already names the strip, the art already signs it.
    assert text.count("<h1>Sun, 15 Nov 2026</h1>") == 2
    assert "by Bil Keane" not in text  # not in the headline, and this strip's alt is its caption
    assert '<p class="caption">A boy argues with a tiger about homework.</p>' in text
    assert 'alt="A boy argues with a tiger about homework."' in text  # the caption describes it
    # With no caption the feed's full title stays behind the artwork, where it still describes it.
    assert 'alt="Outra by Someone for Sun, 15 Nov 2026"' in text
    assert 'class="caption">Outra by Someone' not in text
    # The navigation names each strip and its day, so a reader can tell them apart.
    assert "Family Circus — Sun, 15 Nov 2026" in text
    assert "Outra — Sun, 15 Nov 2026" in text
    # Its own section, not matched by keyword; that section has no story page of its own.
    assert sections == ["espaco", "quadrinhos"]
    assert 'class="article headline"' in text  # the story leads the front page
    # Artwork is fetched even though story photos are off in these settings.
    assert sorted(fetched) == ["https://example.org/comic/1.png", "https://example.org/comic/2.png"]


def test_a_strip_without_its_artwork_waits_for_another_edition(data_dir, monkeypatch):
    """The artwork is the story: a strip that cannot be fetched is left out, not printed blank."""
    from edition_helpers import add_article, epub_text
    from sqlalchemy import select

    from dayfold.db import session_scope
    from dayfold.models import Edition, GenerationJob
    from dayfold.pipeline import generate as gen
    from dayfold.settings import set_section

    monkeypatch.setattr(gen, "collect_all", lambda log: None)

    def fake_photo(url: str, dest: Path, max_width: int) -> Path | None:
        from PIL import Image

        if url.endswith("/2.png"):
            return None  # this strip's artwork never arrives
        Path(dest).parent.mkdir(parents=True, exist_ok=True)
        Image.new("L", (600, 400), 255).save(dest, "JPEG")
        return Path(dest)

    monkeypatch.setattr(gen, "prepare_photo", fake_photo)

    with session_scope() as s:
        set_section(s, "newspaper", {"include_charge": False, "include_images": False,
                                     "include_games": False, "language": "en"})
        add_article(s, "nasa", "Telescope maps the edge of the solar system")
        tiras = _comic_provider(s, category="quadrinhos", sections=["quadrinhos"])
        _comic(s, tiras, title="Telescope, the space tiger", n=1)
        _comic(s, tiras, title="A quiet day at home", excerpt=None, n=2)
        job = GenerationJob()
        s.add(job)
        s.flush()
        job_id = job.id

    gen.run_generation_job(job_id)

    with session_scope() as s:
        edition = s.scalar(select(Edition).order_by(Edition.id.desc()).limit(1))
        job_log = s.get(GenerationJob, job_id).log
        text = epub_text(Path(edition.epub_path))

    assert text.count('class="comic-page"') == 1  # the strip that has its artwork
    assert "Telescope, the space tiger" in text
    assert "A quiet day at home" not in text  # no title-only page
    assert any("A quiet day at home" in line for line in job_log)  # and it is not silent


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

    feed = b"""<?xml version="1.0"?><rss version="2.0"><channel><title>Strips</title>
      <item><title>Family Circus for Sun, 15 Nov 2026</title><link>https://example.org/1</link>
        <description><![CDATA[<p><img src="https://example.org/1.gif" alt="A boy argues with a tiger"></p>
          <p><a href="https://example.org/1">Source</a></p>]]></description></item>
    </channel></rss>"""

    items = _rss(monkeypatch, feed).items
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
