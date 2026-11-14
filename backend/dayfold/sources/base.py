from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime

from lxml import html as lxml_html

BLOCK_TAGS = {"p", "li", "h2", "h3", "h4", "blockquote", "pre"}


@dataclass
class ScrapedItem:
    url: str
    title: str
    subtitle: str | None = None
    author: str | None = None
    published_at: str | None = None  # ISO 8601, UTC
    image_url: str | None = None
    body: str | None = None  # plain text, paragraphs separated by blank lines
    excerpt: str | None = None
    language: str | None = None
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ScrapeResult:
    items: list[ScrapedItem]
    log: list[str]

    def to_dict(self) -> dict:
        return {"items": [i.to_dict() for i in self.items], "log": self.log}


WS = re.compile(r"[ \t\r\f\v]+")


def clean_text(s: str | None) -> str | None:
    if not s:
        return None
    s = WS.sub(" ", s).strip()
    return s or None


def html_to_paragraphs(fragment: str | None) -> str | None:
    """Turn an HTML fragment into plain paragraphs. Never returns markup."""
    if not fragment or not fragment.strip():
        return None
    try:
        root = lxml_html.fragment_fromstring(fragment, create_parent="div")
    except Exception:  # noqa: BLE001
        return clean_text(re.sub(r"<[^>]+>", " ", fragment))
    for bad in root.xpath(".//script|.//style|.//noscript|.//iframe|.//figure|.//form"):
        bad.drop_tree()
    paras: list[str] = []
    blocks = [el for el in root.iter() if isinstance(el.tag, str) and el.tag in BLOCK_TAGS]
    if blocks:
        for el in blocks:
            if any(isinstance(a.tag, str) and a.tag in BLOCK_TAGS for a in el.iterancestors()):
                continue
            t = clean_text(el.text_content())
            if t:
                paras.append(t)
    else:
        for chunk in re.split(r"\n\s*\n|<br\s*/?>\s*<br\s*/?>", root.text_content()):
            t = clean_text(chunk)
            if t:
                paras.append(t)
    return "\n\n".join(paras) or None


def first_words(text: str | None, n: int) -> str | None:
    if not text:
        return None
    words = text.replace("\n\n", " ¶ ").split()
    out = " ".join(words[:n]).replace(" ¶ ", " ").replace("¶", "").strip()
    if len(words) > n:
        out = out.rstrip(".,;:") + "…"
    return out


def to_iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).isoformat()


def strip_author(author: str | None) -> str | None:
    a = clean_text(author)
    if not a:
        return None
    a = re.sub(r"^(por|by)\s+", "", a, flags=re.IGNORECASE)
    a = re.sub(r"^[Dd](?:a|o|e|as|os)\s+(?=[A-ZÁÉÍÓÚÂÊÔÃÕÇ])", "", a)
    m = re.fullmatch(r"\S+@\S+\s*\(([^)]+)\)", a)  # 'noreply@blogger.com (Name)'
    if m:
        a = m.group(1).strip()
    a = re.sub(r"\s*\([^)]*@[^)]*\)", "", a)  # 'Name (email@x)'
    if a.lower() in {"unknown", "admin", "editor", "hq web team"}:
        return None
    if "@" in a and " " not in a:
        return None
    if " " not in a and re.fullmatch(r"[a-z]+[._][a-z]+(?:[._][a-z]+)*", a):
        a = " ".join(part.capitalize() for part in re.split(r"[._]", a))  # 'jane.doe' login
    return a[:200]
