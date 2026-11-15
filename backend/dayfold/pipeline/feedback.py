"""Reader preferences learned from the "Rate edition" ratings, without AI.

Each rating (-1, 0, 1) feeds three affinities: the provider, the section and the words of the
title. An affinity is a smoothed, time decayed mean in [-1, 1]:

    sum(value * decay) / (sum(decay) + PRIOR)

PRIOR acts as a couple of neutral ratings, so one vote alone moves little, and decay halves
the weight of a rating every HALF_LIFE_DAYS, so tastes can change. Neutral ratings count too:
they pull the affinity towards zero. The curation adds ``bonus()`` to each candidate's score.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import ArticleRating, utcnow

HALF_LIFE_DAYS = 60
PRIOR = 2.0
MIN_TERM_RATINGS = 2  # a word needs this many rated stories before it counts

# Maximum effect of each affinity on the score (scores are roughly 1.5 to 4).
PROVIDER_WEIGHT = 0.5
SECTION_WEIGHT = 0.4
TERM_WEIGHT = 0.7

STOPWORDS = {
    # pt
    "que", "para", "com", "por", "uma", "dos", "das", "nos", "nas", "mais", "como", "sobre", "apos",
    "pelo", "pela", "entre", "sem", "seu", "sua", "seus", "suas", "ser", "sao", "tem", "foi", "diz",
    "ate", "isso", "este", "esta", "esse", "essa", "quem", "qual", "onde", "quando", "ano", "anos",
    "novo", "nova", "pode", "vai", "nao", "sim", "mas", "aos", "num", "numa", "dia", "hoje",
    # en
    "the", "and", "for", "with", "from", "that", "this", "into", "over", "after", "about", "are",
    "was", "were", "has", "have", "had", "its", "his", "her", "their", "new", "says", "will", "how",
    "why", "what", "who", "not", "but", "you", "your", "out", "more", "than", "can", "could", "year",
    "years", "day", "today", "amid",
}


def title_terms(title: str) -> set[str]:
    from .curate import tokens

    return {t for t in tokens(title) if t not in STOPWORDS and not t.isdigit()}


class _Mean:
    __slots__ = ("total", "weight", "count")

    def __init__(self) -> None:
        self.total = self.weight = 0.0
        self.count = 0

    def add(self, value: int, w: float) -> None:
        self.total += value * w
        self.weight += w
        self.count += 1

    @property
    def affinity(self) -> float:
        return self.total / (self.weight + PRIOR)


@dataclass
class Preferences:
    count: int = 0
    providers: dict[int, float] = field(default_factory=dict)
    sections: dict[str, float] = field(default_factory=dict)
    terms: dict[str, float] = field(default_factory=dict)
    counts: dict[str, dict] = field(default_factory=dict)  # how many ratings back each affinity

    def __bool__(self) -> bool:
        return self.count > 0

    def term_affinity(self, title: str) -> float:
        known = [self.terms[t] for t in title_terms(title) if t in self.terms]
        return sum(known) / len(known) if known else 0.0

    def bonus(self, provider_id: int | None, section: str, title: str, weight: float = 1.0) -> float:
        if not self:
            return 0.0
        b = (PROVIDER_WEIGHT * self.providers.get(provider_id or -1, 0.0)
             + SECTION_WEIGHT * self.sections.get(section, 0.0)
             + TERM_WEIGHT * self.term_affinity(title))
        return round(b * weight, 3)


def load_preferences(session: Session) -> Preferences:
    rows = list(session.scalars(select(ArticleRating)))
    if not rows:
        return Preferences()
    now = utcnow()
    providers: dict[int, _Mean] = defaultdict(_Mean)
    sections: dict[str, _Mean] = defaultdict(_Mean)
    terms: dict[str, _Mean] = defaultdict(_Mean)
    for r in rows:
        age_days = max(0.0, (now - r.rated_at).total_seconds() / 86400)
        w = 0.5 ** (age_days / HALF_LIFE_DAYS)
        if r.provider_id is not None:
            providers[r.provider_id].add(r.value, w)
        sections[r.section].add(r.value, w)
        for t in title_terms(r.title):
            terms[t].add(r.value, w)
    return Preferences(
        count=len(rows),
        providers={k: m.affinity for k, m in providers.items()},
        sections={k: m.affinity for k, m in sections.items()},
        terms={k: m.affinity for k, m in terms.items() if m.count >= MIN_TERM_RATINGS},
        counts={
            "providers": {k: m.count for k, m in providers.items()},
            "sections": {k: m.count for k, m in sections.items()},
            "terms": {k: m.count for k, m in terms.items()},
        },
    )


def ranked(aff: dict, counts: dict, positive: bool, limit: int = 5, threshold: float = 0.15) -> list[tuple]:
    items = [(k, v, counts.get(k, 0)) for k, v in aff.items() if (v >= threshold if positive else v <= -threshold)]
    items.sort(key=lambda x: -x[1] if positive else x[1])
    return items[:limit]
