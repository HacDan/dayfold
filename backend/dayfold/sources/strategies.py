"""Scraper strategies. Each takes a JSON ``spec`` and returns a :class:`ScrapeResult`.

* ``rss``: ``{"feed_url", "fetch_full"?}``
* ``generic``: ``{"list_url", "link_pattern"?, "min_title_len"?}``: heuristic article
  links on a listing page, each page extracted with Trafilatura.
* ``selectors``: ``{"list_url", "item_selector", "link_selector"?, "article": {"title"?,
  "subtitle"?, "author"?, "date"?, "body"?, "image"?}}``: CSS selectors, usually written
  by the AI. Missing article selectors fall back to Trafilatura.

Specs are data, never code, so an AI generated scraper cannot execute anything.
"""

from __future__ import annotations

import re
import time
from datetime import UTC, datetime
from urllib.parse import urldefrag, urljoin, urlparse

import feedparser
from lxml import html as lxml_html

from .. import net
from .base import (
    ScrapedItem,
    ScrapeResult,
    clean_text,
    html_to_paragraphs,
    strip_author,
    to_iso,
)
from .extract import extract_article

ALLOWED_STRATEGIES = ("rss", "generic", "selectors")
MIN_BODY_CHARS = 400


def run_strategy(strategy: str, spec: dict, *, max_items: int = 15, language: str | None = None,
                 want_body: bool = True) -> ScrapeResult:
    if strategy == "rss":
        return scrape_rss(spec, max_items=max_items, language=language, want_body=want_body)
    if strategy == "generic":
        return scrape_generic(spec, max_items=max_items, language=language)
    if strategy == "selectors":
        return scrape_selectors(spec, max_items=max_items, language=language)
    raise ValueError(f"estratégia desconhecida: {strategy}")


# ---------------------------------------------------------------- RSS / Atom


def _entry_image(entry) -> str | None:
    for key in ("media_content", "media_thumbnail"):
        for m in entry.get(key) or []:
            if m.get("url") and (m.get("medium") in (None, "image") or "image" in m.get("type", "")):
                return m["url"]
    for link in entry.get("links") or []:
        if link.get("rel") == "enclosure" and str(link.get("type", "")).startswith("image"):
            return link.get("href")
    for e in entry.get("enclosures") or []:
        if str(e.get("type", "")).startswith("image"):
            return e.get("href")
    content = (entry.get("content") or [{}])[0].get("value") or entry.get("summary") or ""
    m = re.search(r"<img[^>]+src=[\"']([^\"']+)", content)
    return m.group(1) if m else None


def _entry_date(entry) -> str | None:
    for key in ("published_parsed", "updated_parsed", "created_parsed"):
        t = entry.get(key)
        if t:
            return to_iso(datetime.fromtimestamp(time.mktime(t), UTC))
    return None


def scrape_rss(spec: dict, *, max_items: int, language: str | None, want_body: bool) -> ScrapeResult:
    log: list[str] = []
    feed_url = spec["feed_url"]
    resp = net.fetch(feed_url)
    parsed = feedparser.parse(resp.content)
    if parsed.bozo and not parsed.entries:
        raise net.FetchError(f"feed inválido: {parsed.bozo_exception}")
    feed_lang = (parsed.feed.get("language") or language or "")[:2].lower() or None
    log.append(f"Feed com {len(parsed.entries)} itens ({feed_url}).")
    fetch_full = want_body and spec.get("fetch_full", True)
    items: list[ScrapedItem] = []
    with net.client() as http:
        for entry in parsed.entries[:max_items]:
            link = entry.get("link")
            title = clean_text(entry.get("title"))
            if not link or not title:
                continue
            content_html = None
            if entry.get("content"):
                content_html = max((c.get("value") or "" for c in entry["content"]), key=len)
            summary = html_to_paragraphs(entry.get("summary"))
            body = html_to_paragraphs(content_html) if content_html else None
            item = ScrapedItem(
                url=link,
                title=title,
                subtitle=None,
                author=strip_author(entry.get("author")),
                published_at=_entry_date(entry),
                image_url=_entry_image(entry),
                body=body,
                excerpt=summary if summary and summary != body else None,
                language=feed_lang,
                tags=[t.get("term") for t in entry.get("tags") or [] if t.get("term")][:8],
            )
            if fetch_full and (not item.body or len(item.body) < MIN_BODY_CHARS):
                try:
                    page = net.fetch(link, http=http, check_robots=True)
                    full = extract_article(link, page.text, language=feed_lang)
                    if full and full.body and len(full.body) > len(item.body or ""):
                        item.body = full.body
                        item.author = item.author or full.author
                        item.image_url = item.image_url or full.image_url
                        item.published_at = item.published_at or full.published_at
                        if full.subtitle and full.subtitle != item.title:
                            item.subtitle = full.subtitle
                except net.FetchError as exc:
                    log.append(f"Página não extraída: {exc}")
            if item.excerpt and item.body and item.body.startswith(item.excerpt[:80]):
                item.excerpt = None
            if not item.subtitle and item.excerpt and len(item.excerpt) < 260:
                item.subtitle = item.excerpt
            items.append(item)
    log.append(f"{len(items)} matérias normalizadas.")
    return ScrapeResult(items=items, log=log)


# ---------------------------------------------------------------- generic


def _candidate_links(page_url: str, html: str, pattern: str | None, min_len: int) -> list[str]:
    root = lxml_html.fromstring(html)
    root.make_links_absolute(page_url)
    seen: set[str] = set()
    out: list[str] = []
    rx = re.compile(pattern) if pattern else None
    for a in root.iter("a"):
        href = urldefrag(a.get("href") or "")[0]
        if not href.startswith("http") or href in seen or not net.same_site(href, page_url):
            continue
        text = clean_text(a.text_content()) or ""
        path = urlparse(href).path.rstrip("/")
        if rx:
            if not rx.search(href):
                continue
        elif len(text) < min_len or path.count("/") < 2 or re.search(
            r"/(tag|tags|categoria|category|author|autor|page|pagina|search|busca)/", path
        ):
            continue
        seen.add(href)
        out.append(href)
    return out


def scrape_generic(spec: dict, *, max_items: int, language: str | None) -> ScrapeResult:
    log: list[str] = []
    list_url = spec["list_url"]
    resp = net.fetch(list_url, check_robots=True)
    links = _candidate_links(list_url, resp.text, spec.get("link_pattern"),
                             int(spec.get("min_title_len", 25)))
    log.append(f"{len(links)} links candidatos em {list_url}.")
    items: list[ScrapedItem] = []
    with net.client() as http:
        for link in links[: max_items * 2]:
            if len(items) >= max_items:
                break
            try:
                page = net.fetch(link, http=http, check_robots=True)
            except net.FetchError as exc:
                log.append(str(exc))
                continue
            item = extract_article(link, page.text, language=language)
            if item and item.body and len(item.body) >= MIN_BODY_CHARS:
                items.append(item)
    log.append(f"{len(items)} matérias extraídas.")
    return ScrapeResult(items=items, log=log)


# ---------------------------------------------------------------- selectors


def _select_text(root, selector: str | None) -> str | None:
    if not selector:
        return None
    try:
        found = root.cssselect(selector)
    except Exception:  # noqa: BLE001  invalid selector from the spec
        return None
    if not found:
        return None
    el = found[0]
    if el.tag == "meta":
        return clean_text(el.get("content"))
    if el.tag == "time" and el.get("datetime"):
        return el.get("datetime")
    return clean_text(el.text_content())


def _parse_date(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return to_iso(datetime.fromisoformat(value.strip().replace("Z", "+00:00")))
    except ValueError:
        pass
    m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", value)
    if m:
        d, mo, y = map(int, m.groups())
        try:
            return to_iso(datetime(y, mo, d, 12, tzinfo=UTC))
        except ValueError:
            return None
    return None


def scrape_selectors(spec: dict, *, max_items: int, language: str | None) -> ScrapeResult:
    log: list[str] = []
    list_url = spec["list_url"]
    resp = net.fetch(list_url, check_robots=True)
    root = lxml_html.fromstring(resp.text)
    root.make_links_absolute(list_url)
    try:
        nodes = root.cssselect(spec["item_selector"])
    except Exception as exc:
        raise ValueError(f"item_selector inválido: {exc}") from exc
    links: list[str] = []
    for node in nodes:
        a = node
        if spec.get("link_selector"):
            found = node.cssselect(spec["link_selector"])
            a = found[0] if found else None
        elif node.tag != "a":
            found = node.cssselect("a[href]")
            a = found[0] if found else None
        href = a.get("href") if a is not None else None
        if href and href.startswith("http") and href not in links:
            links.append(urldefrag(href)[0])
    log.append(f"{len(nodes)} itens e {len(links)} links com '{spec['item_selector']}'.")
    article_spec = spec.get("article") or {}
    items: list[ScrapedItem] = []
    with net.client() as http:
        for link in links[:max_items]:
            try:
                page = net.fetch(link, http=http, check_robots=True)
            except net.FetchError as exc:
                log.append(str(exc))
                continue
            auto = extract_article(link, page.text, language=language)
            doc = lxml_html.fromstring(page.text)
            doc.make_links_absolute(link)
            title = _select_text(doc, article_spec.get("title")) or (auto.title if auto else None)
            if not title:
                continue
            body = None
            if article_spec.get("body"):
                try:
                    parts = doc.cssselect(article_spec["body"])
                except Exception:  # noqa: BLE001
                    parts = []
                if parts:
                    body = html_to_paragraphs(lxml_html.tostring(parts[0], encoding="unicode"))
            image = None
            if article_spec.get("image"):
                try:
                    imgs = doc.cssselect(article_spec["image"])
                except Exception:  # noqa: BLE001
                    imgs = []
                if imgs:
                    image = imgs[0].get("content") or imgs[0].get("src")
                    image = urljoin(link, image) if image else None
            items.append(
                ScrapedItem(
                    url=link,
                    title=title,
                    subtitle=_select_text(doc, article_spec.get("subtitle"))
                    or (auto.subtitle if auto else None),
                    author=strip_author(_select_text(doc, article_spec.get("author")))
                    or (auto.author if auto else None),
                    published_at=_parse_date(_select_text(doc, article_spec.get("date")))
                    or (auto.published_at if auto else None),
                    image_url=image or (auto.image_url if auto else None),
                    body=body or (auto.body if auto else None),
                    language=language,
                )
            )
    log.append(f"{len(items)} matérias extraídas.")
    return ScrapeResult(items=items, log=log)
