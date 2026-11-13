"""Polite HTTP helpers shared by scrapers and discovery."""

from __future__ import annotations

import time
import urllib.robotparser
from functools import lru_cache
from urllib.parse import urljoin, urlparse

import httpx

USER_AGENT = "Mozilla/5.0 (compatible; Dayfold/0.1; +https://github.com/JonathanLemes/dayfold)"
MAX_BYTES = 6 * 1024 * 1024
DEFAULT_TIMEOUT = httpx.Timeout(20.0, connect=10.0)

_last_hit: dict[str, float] = {}
MIN_INTERVAL_S = 1.0  # per host


class FetchError(RuntimeError):
    pass


class Fetched:
    """Downloaded body with the bits callers need (already decompressed)."""

    def __init__(self, url: str, status_code: int, headers: httpx.Headers, content: bytes,
                 encoding: str | None):
        self.url = url
        self.status_code = status_code
        self.headers = headers
        self.content = content
        self.encoding = encoding or "utf-8"

    @property
    def text(self) -> str:
        return self.content.decode(self.encoding, errors="replace")


def client() -> httpx.Client:
    return httpx.Client(
        headers={"User-Agent": USER_AGENT, "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8"},
        timeout=DEFAULT_TIMEOUT,
        follow_redirects=True,
    )


def _throttle(url: str) -> None:
    host = urlparse(url).netloc
    wait = MIN_INTERVAL_S - (time.monotonic() - _last_hit.get(host, 0))
    if wait > 0:
        time.sleep(wait)
    _last_hit[host] = time.monotonic()


def fetch(url: str, *, http: httpx.Client | None = None, check_robots: bool = False,
          max_bytes: int = MAX_BYTES) -> Fetched:
    if check_robots and not allowed_by_robots(url):
        raise FetchError(f"robots.txt não permite {url}")
    _throttle(url)
    own = http is None
    http = http or client()
    try:
        with http.stream("GET", url) as resp:
            chunks: list[bytes] = []
            size = 0
            for chunk in resp.iter_bytes():
                size += len(chunk)
                if size > max_bytes:
                    raise FetchError(f"resposta maior que {max_bytes // 1024 // 1024} MB: {url}")
                chunks.append(chunk)
            if resp.status_code >= 400:
                raise FetchError(f"HTTP {resp.status_code} em {url}")
            content = b"".join(chunks)
            return Fetched(str(resp.url), resp.status_code, resp.headers, content,
                           resp.charset_encoding)
    except httpx.HTTPError as exc:
        raise FetchError(f"{type(exc).__name__} em {url}: {exc}") from exc
    finally:
        if own:
            http.close()


@lru_cache(maxsize=256)
def _robots_for(origin: str) -> urllib.robotparser.RobotFileParser | None:
    rp = urllib.robotparser.RobotFileParser()
    try:
        with client() as http:
            resp = http.get(urljoin(origin, "/robots.txt"))
        if resp.status_code >= 400:
            return None
        rp.parse(resp.text.splitlines())
        return rp
    except httpx.HTTPError:
        return None


def allowed_by_robots(url: str) -> bool:
    p = urlparse(url)
    rp = _robots_for(f"{p.scheme}://{p.netloc}")
    return True if rp is None else rp.can_fetch("Dayfold", url)


def same_site(a: str, b: str) -> bool:
    ha, hb = urlparse(a).netloc.lower(), urlparse(b).netloc.lower()
    strip = lambda h: h.removeprefix("www.")
    return strip(ha) == strip(hb) or strip(ha).endswith("." + strip(hb)) or strip(hb).endswith(
        "." + strip(ha)
    )
