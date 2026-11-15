"""Editorial selection: deterministic scoring, optional AI selection on top of it."""

from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta

from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..ai.client import AIError, active_client
from ..i18n import tr
from ..models import Article, Edition, EditionArticle, EditionStatus, Provider, Topic, utcnow
from ..settings import CurationSettings, NewspaperSettings


def fold(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.lower())
    return "".join(c for c in s if not unicodedata.combining(c))


TOKEN = re.compile(r"[a-z0-9]{3,}")


def tokens(s: str) -> set[str]:
    return set(TOKEN.findall(fold(s)))


def jaccard(a: set[str], b: set[str]) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


@dataclass
class Candidate:
    article: Article
    section: str
    score: float
    keyword_hits: int


@dataclass
class Pick:
    article_id: int
    section: str
    priority: int
    score: float
    is_headline: bool = False


def _keyword_hits(text: str, keywords: list[str]) -> int:
    t = f" {fold(text)} "
    hits = 0
    for kw in keywords:
        k = fold(kw).strip()
        if k and re.search(rf"(?<![a-z0-9]){re.escape(k)}(?![a-z0-9])", t):
            hits += 1
    return hits


SKIP_LABELS = {
    "language": ("idioma", "language"),
    "blocked": ("palavra bloqueada", "blocked keyword"),
    "no_section": ("sem seção", "no section"),
}


def skip_label(key: str) -> str:
    """Why a story was filtered out, in the server's language: this lands in the job log."""
    return tr(*SKIP_LABELS.get(key, (key, key)))


def candidates(session: Session, cur: CurationSettings, log: Callable[[str], None]) -> list[Candidate]:
    since = utcnow() - timedelta(hours=cur.max_age_hours)
    used = select(EditionArticle.article_id).join(Edition).where(
        Edition.status.in_([EditionStatus.READY, "ARCHIVED"])
    )
    rows = list(session.scalars(
        select(Article).where(
            or_(Article.published_at >= since, Article.published_at.is_(None) & (Article.collected_at >= since)),
            Article.id.not_in(used),
        )
    ))
    topics = list(session.scalars(select(Topic).where(Topic.enabled.is_(True)).order_by(Topic.position)))
    if not topics:
        return []
    by_slug = {t.slug: t for t in topics}
    blocked = [fold(b) for b in cur.blocked_keywords if b.strip()]
    langs = {lang[:2] for lang in cur.languages}
    provider_sections = {p.id: tuple(p.sections) for p in session.scalars(select(Provider))}
    out: list[Candidate] = []
    skipped = defaultdict(int)
    for a in rows:
        if a.language and langs and a.language[:2] not in langs:
            skipped["language"] += 1
            continue
        text = " ".join(filter(None, [a.title, a.subtitle, a.excerpt, (a.body or "")[:1500]]))
        ftext = fold(text)
        if any(b in ftext for b in blocked):
            skipped["blocked"] += 1
            continue
        best, best_hits = None, 0
        for t in topics:
            hits = _keyword_hits(a.title, t.keywords) * 3 + _keyword_hits(text, t.keywords)
            if t.slug in provider_sections.get(a.provider_id, (a.category,)):
                hits += 4
            if hits > best_hits:
                best, best_hits = t, hits
        if best is None:
            skipped["no_section"] += 1
            continue
        age_h = (utcnow() - (a.published_at or a.collected_at)).total_seconds() / 3600
        recency = max(0.0, 1 - age_h / cur.max_age_hours)
        score = best.weight * (1 + min(best_hits, 8) * 0.15) + recency * 1.2
        score += 0.6 if a.body and len(a.body) > 800 else 0
        score += 0.3 if a.image_url else 0
        score += 0.1 if a.author else 0
        out.append(Candidate(a, best.slug, round(score, 3), best_hits))
    if skipped:
        log(tr("Filtradas: ", "Filtered out: ")
            + ", ".join(f"{n} ({skip_label(k)})" for k, n in skipped.items()) + ".")
    # dedupe by title similarity, keep the best scored
    out.sort(key=lambda c: -c.score)
    kept: list[Candidate] = []
    toks: list[set[str]] = []
    for c in out:
        tk = tokens(c.article.title)
        if any(jaccard(tk, other) >= 0.6 for other in toks):
            continue
        kept.append(c)
        toks.append(tk)
    if len(kept) < len(out):
        log(tr(f"Duplicadas removidas por título: {len(out) - len(kept)}.",
               f"Duplicates removed by title: {len(out) - len(kept)}."))
    _ = by_slug
    return kept


def rule_select(session: Session, cands: list[Candidate], news: NewspaperSettings,
                cur: CurationSettings) -> list[Pick]:
    limits = {t.slug: t.max_articles for t in session.scalars(select(Topic))}
    per_section: dict[str, int] = defaultdict(int)
    per_provider: dict[int, int] = defaultdict(int)
    picks: list[Pick] = []
    for c in cands:
        if len(picks) >= news.max_articles:
            break
        if per_section[c.section] >= limits.get(c.section, 3):
            continue
        if per_provider[c.article.provider_id] >= cur.per_provider_limit:
            continue
        per_section[c.section] += 1
        per_provider[c.article.provider_id] += 1
        priority = 1 if c.score >= 2.6 else 2 if c.score >= 1.8 else 3
        picks.append(Pick(c.article.id, c.section, priority, c.score))
    if picks:
        def headline_key(p: Pick) -> float:
            a = next(c.article for c in cands if c.article.id == p.article_id)
            return p.score + (0.8 if a.body else 0) + (0.4 if a.image_url else 0)

        max(picks, key=headline_key).is_headline = True
    return picks


class AISelected(BaseModel):
    id: int
    section: str
    priority: int = Field(ge=1, le=3)


class AISelection(BaseModel):
    headline_id: int
    selected: list[AISelected]


AI_PROMPT = """Monte a edição de hoje do jornal "{title}".
Seções disponíveis (slug: tema e palavras-chave): {sections}
Escolha até {max_articles} matérias entre as candidatas abaixo, priorizando relevância
pública, diversidade de temas e de fontes, e evitando assuntos repetidos. Use no máximo
{per_section} por seção. Prioridade: 1 = destaque, 2 = importante, 3 = nota.

Responda com JSON: {{"headline_id": <id>, "selected": [{{"id": <id>, "section": "<slug>",
"priority": 1}}]}}

Candidatas (id | seção sugerida | fonte | título | resumo):
{lines}
"""


def ai_select(session: Session, cands: list[Candidate], news: NewspaperSettings,
              cur: CurationSettings, log: Callable[[str], None]) -> list[Pick] | None:
    ai = active_client(session)
    if ai is None:
        log(tr("Curadoria com IA ligada, mas nenhuma IA está ativa: usando regras.",
               "AI curation is on but no AI provider is active: using rules."))
        return None
    pool = cands[: cur.ai_candidates]
    topics = list(session.scalars(select(Topic).where(Topic.enabled.is_(True)).order_by(Topic.position)))
    sections = "; ".join(f"{t.slug}: {t.name} ({', '.join(t.keywords[:6])})" for t in topics)
    lines = []
    for c in pool:
        a = c.article
        summary = " ".join((a.subtitle or a.excerpt or (a.body or "")[:300]).split()[:30])
        lines.append(f"{a.id} | {c.section} | {a.provider.name} | {a.title} | {summary}")
    prompt = AI_PROMPT.format(
        title=news.title, sections=sections, max_articles=news.max_articles,
        per_section=max(t.max_articles for t in topics), lines="\n".join(lines),
    )
    log(tr(f"Enviando {len(pool)} candidatas para {ai.label} (~{len(prompt) // 4} tokens).",
           f"Sending {len(pool)} candidates to {ai.label} (~{len(prompt) // 4} tokens)."))
    try:
        result = ai.complete_json(prompt, AISelection, max_tokens=1200)
    except AIError as exc:
        log(tr(f"IA falhou ({exc}): usando regras.", f"AI failed ({exc}): using rules."))
        return None
    valid_ids = {c.article.id: c for c in pool}
    slugs = {t.slug for t in topics}
    picks: list[Pick] = []
    seen: set[int] = set()
    for s in result.selected:
        if s.id not in valid_ids or s.id in seen:
            continue
        seen.add(s.id)
        c = valid_ids[s.id]
        section = s.section if s.section in slugs else c.section
        picks.append(Pick(s.id, section, s.priority, c.score, s.id == result.headline_id))
        if len(picks) >= news.max_articles:
            break
    if len(picks) < 3:
        log(tr("IA devolveu poucas matérias válidas: usando regras.",
               "AI returned too few valid stories: using rules."))
        return None
    if not any(p.is_headline for p in picks):
        min(picks, key=lambda p: (p.priority, -p.score)).is_headline = True
    log(tr(f"IA selecionou {len(picks)} matérias.", f"AI selected {len(picks)} stories."))
    return picks


def curate(session: Session, news: NewspaperSettings, cur: CurationSettings,
           log: Callable[[str], None]) -> tuple[list[Pick], str]:
    cands = candidates(session, cur, log)
    log(tr(f"{len(cands)} candidatas após filtros.", f"{len(cands)} candidates after filters."))
    if not cands:
        return [], "rules"
    if cur.use_ai:
        picks = ai_select(session, cands, news, cur, log)
        if picks:
            return order(session, picks), "ai"
    return order(session, rule_select(session, cands, news, cur)), "rules"


def order(session: Session, picks: list[Pick]) -> list[Pick]:
    pos = {t.slug: t.position for t in session.scalars(select(Topic))}
    return sorted(picks, key=lambda p: (not p.is_headline, pos.get(p.section, 99), p.priority, -p.score))
