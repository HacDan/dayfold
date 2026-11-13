"""Article page extraction with Trafilatura."""

from __future__ import annotations

from datetime import datetime

import trafilatura

from .base import ScrapedItem, clean_text, strip_author, to_iso


def extract_article(url: str, html: str, *, language: str | None = None) -> ScrapedItem | None:
    doc = trafilatura.bare_extraction(
        html,
        url=url,
        with_metadata=True,
        include_comments=False,
        include_tables=False,
        favor_precision=True,
    )
    if doc is None:
        return None
    data = doc.as_dict() if hasattr(doc, "as_dict") else dict(doc)
    title = clean_text(data.get("title"))
    text = data.get("text") or ""
    if not title:
        return None
    paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
    published = None
    if data.get("date"):
        try:
            published = to_iso(datetime.fromisoformat(str(data["date"])))
        except ValueError:
            published = None
    return ScrapedItem(
        url=url,
        title=title,
        subtitle=clean_text(data.get("description")),
        author=strip_author(data.get("author")),
        published_at=published,
        image_url=data.get("image") or None,
        body="\n\n".join(paragraphs) or None,
        language=language or data.get("language"),
        tags=[t for t in (data.get("tags") or []) if isinstance(t, str)][:8],
    )
