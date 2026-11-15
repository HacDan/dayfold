"""Find feeds for a site: <link rel=alternate>, common paths and sitemaps."""

from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

import feedparser
from lxml import html as lxml_html

from .. import net
from ..i18n import tr

COMMON_PATHS = [
    "/feed", "/feed/", "/rss", "/rss.xml", "/feed.xml", "/atom.xml", "/index.xml",
    "/feeds/posts/default", "/blog/feed", "/news/rss.xml", "/rss/feed.xml", "/RSS",
]


def _is_feed(url: str) -> int:
    try:
        resp = net.fetch(url)
    except net.FetchError:
        return 0
    parsed = feedparser.parse(resp.content)
    return len(parsed.entries)


def discover_feeds(base_url: str, log: list[str]) -> list[tuple[str, int]]:
    found: list[tuple[str, int]] = []
    seen: set[str] = set()

    def consider(url: str, why: str) -> None:
        if url in seen:
            return
        seen.add(url)
        n = _is_feed(url)
        if n:
            log.append(tr(f"Feed encontrado via {why}: {url} ({n} itens).",
                          f"Feed found via {why}: {url} ({n} items)."))
            found.append((url, n))

    try:
        page = net.fetch(base_url)
        root = lxml_html.fromstring(page.content)
        for link in root.xpath('//link[@rel="alternate"]'):
            t = (link.get("type") or "").lower()
            if "rss" in t or "atom" in t:
                consider(urljoin(page.url, link.get("href", "")), "<link rel=alternate>")
        for a in root.xpath("//a[@href]"):
            href = a.get("href", "")
            if re.search(r"(rss|atom|feed)(\.xml)?/?$", href, re.IGNORECASE):
                consider(urljoin(page.url, href), tr("link na página", "a link on the page"))
                if len(seen) > 12:
                    break
    except (net.FetchError, ValueError) as exc:
        log.append(tr(f"Página inicial não lida: {exc}", f"Home page not read: {exc}"))

    if not found:
        p = urlparse(base_url)
        origin = f"{p.scheme}://{p.netloc}"
        prefix = p.path.rstrip("/")
        for path in COMMON_PATHS:
            if prefix:
                consider(origin + prefix + path, tr("caminho comum", "a common path"))
            consider(origin + path, tr("caminho comum", "a common path"))
            if found:
                break
    found.sort(key=lambda x: -x[1])
    return found


def sitemap_urls(base_url: str, log: list[str]) -> list[str]:
    """Return sitemap URLs declared in robots.txt (used as a hint for the AI)."""
    p = urlparse(base_url)
    try:
        robots = net.fetch(f"{p.scheme}://{p.netloc}/robots.txt").text
    except net.FetchError:
        return []
    maps = re.findall(r"(?im)^sitemap:\s*(\S+)", robots)
    if maps:
        log.append(tr(f"Sitemaps no robots.txt: {', '.join(maps[:3])}",
                      f"Sitemaps in robots.txt: {', '.join(maps[:3])}"))
    return maps[:5]


def _content_links(el) -> int:
    return sum(1 for a in el.iter("a") if len((a.text_content() or "").strip()) >= 25)


def trimmed_html(url: str, limit: int = 16000) -> str:
    """Compact HTML sample for the AI: the region that holds the article links, without
    scripts, styles and attribute noise."""
    page = net.fetch(url, check_robots=True)
    root = lxml_html.fromstring(page.content)
    for bad in root.xpath("//script|//style|//noscript|//svg|//iframe|//head|//comment()"):
        bad.drop_tree()
    candidates = []
    for xp in ("//main", "//*[@id='content']", "//*[@id='main']", "//*[@role='main']"):
        candidates += root.xpath(xp)
    region = next((c for c in candidates if _content_links(c) >= 6), None)
    if region is None:
        trimmed = lxml_html.fromstring(lxml_html.tostring(root))
        for bad in trimmed.xpath("//footer|//form|//*[@role='navigation']"
                                 "|//*[contains(@class,'cookie') or contains(@class,'breadcrumb')]"):
            bad.drop_tree()
        region = trimmed if _content_links(trimmed) >= 6 else root
    keep = {"class", "id", "href", "datetime", "itemprop", "rel"}
    for el in region.iter():
        if not isinstance(el.tag, str):
            continue
        for attr in list(el.attrib):
            if attr not in keep:
                del el.attrib[attr]
        if el.get("class"):
            el.set("class", " ".join(el.get("class", "").split()[:3]))
    text = lxml_html.tostring(region, encoding="unicode")
    text = re.sub(r"\s+", " ", text)
    return text[:limit]
