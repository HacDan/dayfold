"""Builds a real edition from articles inserted by hand (no network, no AI)."""

from __future__ import annotations

import hashlib
import zipfile
from pathlib import Path

from sqlalchemy import select

LONG_BODY = "\n\n".join(
    f"Paragraph {i} of the long story says something new about the mission and the crew. " * 3
    for i in range(1, 13)
)


def add_article(s, slug: str, title: str, body: str | None = LONG_BODY, language: str = "en") -> None:
    from dayfold.models import Article, Provider, UsageMode, utcnow

    p = s.scalar(select(Provider).where(Provider.slug == slug))
    url = f"https://example.org/{slug}/{hashlib.sha1(title.encode()).hexdigest()[:8]}"
    s.add(Article(provider_id=p.id, url=url, url_hash=hashlib.sha1(url.encode()).hexdigest(),
                  title=title, body=body, excerpt=(body or "")[:200] or None, language=language,
                  usage_mode=UsageMode.FULL_CONTENT_ALLOWED, category=p.category,
                  published_at=utcnow(), collected_at=utcnow()))


def generate(monkeypatch, articles: list[tuple[str, str]], **newspaper) -> Path:
    """Runs the generation job over the given (provider slug, title) articles; returns the EPUB."""
    from dayfold.db import session_scope
    from dayfold.models import Edition, GenerationJob
    from dayfold.pipeline import generate as gen
    from dayfold.settings import set_section

    monkeypatch.setattr(gen, "collect_all", lambda log: None)
    with session_scope() as s:
        set_section(s, "newspaper", {"include_charge": False, "include_images": False, **newspaper})
        for slug, title in articles:
            add_article(s, slug, title)
        job = GenerationJob()
        s.add(job)
        s.flush()
        job_id = job.id
    gen.run_generation_job(job_id)
    with session_scope() as s:
        return Path(s.scalar(select(Edition.epub_path).order_by(Edition.id.desc()).limit(1)))


def epub_text(path: Path) -> str:
    with zipfile.ZipFile(path) as z:
        return "\n".join(z.read(n).decode("utf-8", "replace") for n in z.namelist()
                         if n.endswith((".xhtml", ".html", ".opf", ".ncx")))
