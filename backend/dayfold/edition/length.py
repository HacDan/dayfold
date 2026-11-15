"""Length cap for full text stories.

A cap can be set for the whole paper, per section and per provider; for words and for paragraphs
separately, the most specific one wins (provider, then section, then paper). A capped story keeps
whole paragraphs while they fit and cuts the last one at a sentence end, then the edition adds a
"continues at the source" note with the link.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Below this many words left, a partial paragraph is not worth starting.
MIN_PARTIAL_WORDS = 25
_SENTENCE_END = re.compile(r"(?<=[.!?…])[\"'”’)]*\s+")


@dataclass(frozen=True)
class Limits:
    words: int | None = None
    paragraphs: int | None = None


def resolve(*levels: object | None) -> Limits:
    """Most specific first: objects with ``max_words``/``max_paragraphs`` (provider, section)
    and finally the paper defaults (``article_max_words``/``article_max_paragraphs``)."""
    words = paragraphs = None
    for lv in levels:
        if lv is None:
            continue
        w = getattr(lv, "max_words", None) or getattr(lv, "article_max_words", None)
        p = getattr(lv, "max_paragraphs", None) or getattr(lv, "article_max_paragraphs", None)
        words = words or w
        paragraphs = paragraphs or p
    return Limits(words, paragraphs)


def _cut(paragraph: str, budget: int) -> str:
    """The sentences of ``paragraph`` that fit in ``budget`` words, or its first words + "…"."""
    out: list[str] = []
    used = 0
    for sentence in _SENTENCE_END.split(paragraph):
        n = len(sentence.split())
        if used + n > budget:
            break
        out.append(sentence)
        used += n
    if out:
        return " ".join(out)
    return " ".join(paragraph.split()[:budget]).rstrip(",;:") + "…"


def cap(paragraphs: list[str], limits: Limits) -> tuple[list[str], bool]:
    """Returns the paragraphs to print and whether the story was shortened."""
    out = paragraphs[: limits.paragraphs] if limits.paragraphs else list(paragraphs)
    if limits.words:
        kept: list[str] = []
        used = 0
        for p in out:
            n = len(p.split())
            if used + n <= limits.words:
                kept.append(p)
                used += n
                continue
            left = limits.words - used
            if not kept or left >= MIN_PARTIAL_WORDS:
                kept.append(_cut(p, left))
            break
        out = kept
    return out, out != paragraphs
