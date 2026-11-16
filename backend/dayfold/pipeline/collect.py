"""Collection: run every active provider and store normalized articles."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from sqlalchemy import select

from ..db import session_scope
from ..i18n import tr
from ..models import Article, Provider, ScraperStatus, ScraperVersion, UsageMode, utcnow
from ..settings import get_section
from ..sources.base import ScrapedItem, clean_text, first_words
from ..sources.runner import run_isolated

TRACKING = re.compile(r"^(utm_|fbclid|gclid|mc_|ref$|cmpid)")


def normalize_url(url: str) -> str:
    p = urlparse(url.strip())
    query = urlencode([(k, v) for k, v in parse_qsl(p.query) if not TRACKING.match(k)])
    path = p.path.rstrip("/") or "/"
    return urlunparse((p.scheme.lower(), p.netloc.lower().removeprefix("www."), path, "", query, ""))


def url_hash(url: str) -> str:
    return hashlib.sha1(normalize_url(url).encode()).hexdigest()


def _strip_title(body: str | None, title: str) -> str | None:
    if not body:
        return body
    paras = body.split("\n\n")
    while paras and paras[0].strip().rstrip(".").lower() == title.strip().rstrip(".").lower():
        paras = paras[1:]
    return "\n\n".join(paras) or None


def _restates(text: str, title: str) -> bool:
    """True when text says no more than the title does ("... on Sun" vs "... for Sun")."""
    def words(s: str) -> set[str]:
        return set(re.findall(r"[a-z0-9]{2,}", s.casefold()))

    a, b = words(text), words(title)
    return bool(a and b) and len(a & b) / len(a | b) >= 0.8


def apply_usage(item: ScrapedItem, mode: str, excerpt_words: int) -> dict:
    """Keep only what the provider's license allows."""
    body = _strip_title(item.body, item.title)
    source_text = item.excerpt or body or item.subtitle
    data = {
        "title": item.title[:500],
        "subtitle": (item.subtitle or None),
        "author": item.author,
        "image_url": item.image_url,
        "language": (item.language or "")[:2] or None,
        "excerpt": None,
        "body": None,
    }
    if data["subtitle"] and data["subtitle"].strip().lower() == item.title.strip().lower():
        data["subtitle"] = None
    if mode == UsageMode.METADATA_ONLY:
        data["subtitle"] = None
        data["image_url"] = None
    elif mode == UsageMode.IMAGE_ONLY:
        # A comic strip: the artwork is what gets printed, the feed's text is its alt text, and
        # there is no story to cap. The image stays, unlike excerpts, because it is the content.
        alt = clean_text(item.image_alt) or clean_text(source_text)
        if alt and item.title and _restates(alt, item.title):
            alt = None  # the feed's alt text only restates the title we already print
        data["excerpt"] = alt[:500] if alt else None
        data["subtitle"] = None
    elif mode == UsageMode.EXCERPT_AND_LINK:
        data["excerpt"] = first_words(source_text, excerpt_words)
        data["image_url"] = None  # photos often carry separate rights
        if data["subtitle"] and data["excerpt"] and data["excerpt"].startswith(data["subtitle"][:60]):
            data["subtitle"] = None
    else:
        data["body"] = body
        data["excerpt"] = first_words(body or source_text, excerpt_words)
    return data


def _parse_iso(v: str | None) -> datetime | None:
    if not v:
        return None
    try:
        dt = datetime.fromisoformat(v)
    except ValueError:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(UTC).replace(tzinfo=None)
    return dt


def _collect_provider(pid: int, log: Callable[[str], None], excerpt_words: int) -> int:
    with session_scope() as s:
        p = s.get(Provider, pid)
        v = s.get(ScraperVersion, p.active_version_id) if p.active_version_id else None
        if v is None or v.status != ScraperStatus.READY:
            log(tr(f"{p.name}: sem scraper pronto, ignorado.", f"{p.name}: no ready scraper, skipped."))
            return 0
        job = dict(strategy=v.strategy, spec=dict(v.spec), max_items=p.max_items,
                   language=p.language, want_body=p.usage_mode == UsageMode.FULL_CONTENT_ALLOWED)
        name, mode, category = p.name, p.usage_mode, p.category
    outcome = run_isolated(**job)
    new = skipped = refreshed = 0
    with session_scope() as s:
        p = s.get(Provider, pid)
        p.last_run_at = utcnow()
        p.last_run_ok = outcome.ok
        p.last_run_message = outcome.error or (outcome.log[-1] if outcome.log else None)
        p.last_run_count = len(outcome.items)
        if not outcome.ok:
            log(tr(f"{name}: falhou ({outcome.error}).", f"{name}: failed ({outcome.error})."))
            return 0
        for item in outcome.items:
            if mode == UsageMode.IMAGE_ONLY and not item.image_url:
                skipped += 1  # a strip without its artwork is nothing to print
                continue
            h = url_hash(item.url)
            data = apply_usage(item, mode, excerpt_words)
            existing = s.scalar(select(Article).where(Article.url_hash == h))
            if existing:
                if existing.usage_mode != mode or (data["language"] and data["language"] != existing.language):
                    # The provider's usage mode (or language) changed after this story was stored.
                    # What may be printed, and the text printed, follow the mode, so re-derive them
                    # rather than leaving a strip stored as a story with its feed boilerplate.
                    for k, val in data.items():
                        setattr(existing, k, val)
                    existing.usage_mode = mode
                    refreshed += 1
                else:
                    for k, val in data.items():
                        if val and not getattr(existing, k):
                            setattr(existing, k, val)
                existing.category = category
                continue
            s.add(Article(
                provider_id=pid, url=item.url[:1000], url_hash=h,
                published_at=_parse_iso(item.published_at), usage_mode=mode,
                category=category, **data,
            ))
            new += 1
    if skipped:
        log(tr(f"{name}: {skipped} itens sem imagem ignorados.",
               f"{name}: {skipped} items without an image skipped."))
    log(tr(f"{name}: {len(outcome.items)} lidas, {new} novas, {refreshed} atualizadas.",
           f"{name}: {len(outcome.items)} read, {new} new, {refreshed} updated."))
    return new


def collect_all(log: Callable[[str], None]) -> int:
    with session_scope() as s:
        news = get_section(s, "newspaper")
        ids = list(s.scalars(select(Provider.id).where(Provider.enabled.is_(True))))
    log(tr(f"Coletando {len(ids)} provedores ativos...", f"Collecting {len(ids)} active providers..."))
    with ThreadPoolExecutor(max_workers=4) as pool:
        counts = list(pool.map(lambda pid: _collect_provider(pid, log, news.excerpt_words), ids))
    total = sum(counts)
    log(tr(f"Coleta concluída: {total} matérias novas.", f"Collection done: {total} new stories."))
    return total
