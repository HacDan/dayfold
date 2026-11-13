"""Settings, sections, AI providers, games and overview."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..ai.client import AIClient, test_provider, usage
from ..db import get_session
from ..games.generators import GENERATORS, seeded
from ..games.words import WORDLE, WORDSEARCH_THEMES
from ..jobs import scheduler
from ..models import (
    AIProvider,
    Edition,
    EditionStatus,
    Game,
    GenerationJob,
    JobStatus,
    Provider,
    ScraperJob,
    ScraperStatus,
    ScraperVersion,
    Topic,
)
from ..settings import MASTHEAD_FONTS, SECTIONS, TYPE_RANGES, all_settings, get_section, set_section
from .auth import require_admin
from .serialize import edition_summary, job_out

router = APIRouter(prefix="/api", tags=["admin"], dependencies=[Depends(require_admin)])


def ai_available(session: Session) -> bool:
    return session.scalar(select(AIProvider.id).where(AIProvider.is_active.is_(True)).limit(1)) is not None


# ---------------------------------------------------------------- overview


@router.get("/overview")
def overview(session: Session = Depends(get_session)) -> dict:
    latest = session.scalar(select(Edition).where(Edition.status == EditionStatus.READY)
                            .order_by(Edition.id.desc()).limit(1))
    last_job = session.scalar(select(GenerationJob).order_by(GenerationJob.id.desc()).limit(1))
    providers_total = session.scalar(select(func.count(Provider.id))) or 0
    providers_active = session.scalar(select(func.count(Provider.id)).where(Provider.enabled.is_(True))) or 0
    failing = session.scalar(select(func.count(Provider.id)).where(Provider.enabled.is_(True),
                                                                   Provider.last_run_ok.is_(False))) or 0
    pending = session.scalar(select(func.count(ScraperVersion.id)).where(
        ScraperVersion.status.in_([ScraperStatus.PENDING, ScraperStatus.GENERATING, ScraperStatus.TESTING]))) or 0
    failed = session.scalar(select(func.count(ScraperJob.id)).where(ScraperJob.status == JobStatus.FAILED)) or 0
    games = list(session.scalars(select(Game).order_by(Game.position)))
    news = get_section(session, "newspaper")
    sched = get_section(session, "schedule")
    active_ai = session.scalar(select(AIProvider).where(AIProvider.is_active.is_(True)))
    recent = list(session.scalars(select(Edition).order_by(Edition.id.desc()).limit(6)))
    nxt = scheduler.next_run()
    return {
        "today": date.today().isoformat(),
        "newspaper": news.model_dump(),
        "latest_edition": edition_summary(latest) if latest else None,
        "last_job": job_out(last_job) if last_job else None,
        "next_run": nxt.isoformat() if nxt else None,
        "schedule": sched.model_dump(),
        "providers": {"total": providers_total, "active": providers_active, "failing": failing},
        "scrapers": {"pending": pending, "failed_jobs": failed},
        "ai": {"active": bool(active_ai), "name": active_ai.name if active_ai else None,
               "kind": active_ai.kind if active_ai else None,
               "session_usage": {"calls": usage.calls, "prompt_chars": usage.prompt_chars,
                                 "completion_chars": usage.completion_chars}},
        "games": [{"kind": g.kind, "name": g.name, "enabled": g.enabled} for g in games],
        "charge": {"enabled": news.include_charge, "available": bool(active_ai)},
        "recent_editions": [edition_summary(e) for e in recent],
    }


# ---------------------------------------------------------------- settings


@router.get("/settings")
def read_settings(session: Session = Depends(get_session)) -> dict:
    return {
        "values": all_settings(session),
        "meta": {
            "masthead_fonts": [{"key": k, **v} for k, v in MASTHEAD_FONTS.items()],
            "type_ranges": {k: {"min": lo, "default": d, "max": hi} for k, (lo, d, hi) in TYPE_RANGES.items()},
            "ai_available": ai_available(session),
        },
    }


@router.put("/settings/{section}")
def write_settings(section: str, body: dict, session: Session = Depends(get_session)) -> dict:
    if section not in SECTIONS:
        raise HTTPException(404, "seção desconhecida")
    if section == "newspaper" and body.get("include_charge") and not ai_available(session):
        raise HTTPException(400, "a charge exige uma IA configurada e ativa")
    if section == "curation" and body.get("use_ai") and not ai_available(session):
        raise HTTPException(400, "a curadoria com IA exige uma IA configurada e ativa")
    try:
        value = set_section(session, section, body)
    except ValidationError as exc:
        raise HTTPException(422, exc.errors(include_url=False, include_context=False)) from exc
    session.commit()
    if section == "schedule":
        scheduler.reschedule()
    return value.model_dump()


@router.post("/settings/distribution/rotate-token")
def rotate_token(session: Session = Depends(get_session)) -> dict:
    import secrets

    value = set_section(session, "distribution", {"feed_token": secrets.token_urlsafe(18)})
    return value.model_dump()


# ---------------------------------------------------------------- topics


class TopicIn(BaseModel):
    slug: str = Field(pattern=r"^[a-z0-9-]{2,40}$")
    name: str = Field(min_length=1, max_length=80)
    keywords: list[str] = []
    weight: float = Field(1.0, ge=0.1, le=3)
    enabled: bool = True
    max_articles: int = Field(4, ge=1, le=20)


def topic_out(t: Topic) -> dict:
    return {"id": t.id, "slug": t.slug, "name": t.name, "keywords": t.keywords, "weight": t.weight,
            "enabled": t.enabled, "max_articles": t.max_articles, "position": t.position}


@router.get("/topics")
def list_topics(session: Session = Depends(get_session)) -> list[dict]:
    return [topic_out(t) for t in session.scalars(select(Topic).order_by(Topic.position))]


@router.post("/topics")
def create_topic(body: TopicIn, session: Session = Depends(get_session)) -> dict:
    if session.scalar(select(Topic).where(Topic.slug == body.slug)):
        raise HTTPException(409, "slug já existe")
    pos = (session.scalar(select(func.max(Topic.position))) or 0) + 1
    t = Topic(position=pos, **body.model_dump())
    session.add(t)
    session.flush()
    return topic_out(t)


@router.put("/topics/{topic_id}")
def update_topic(topic_id: int, body: TopicIn, session: Session = Depends(get_session)) -> dict:
    t = session.get(Topic, topic_id) or _404()
    for k, v in body.model_dump().items():
        setattr(t, k, v)
    return topic_out(t)


@router.put("/topics-order")
def order_topics(ids: list[int], session: Session = Depends(get_session)) -> list[dict]:
    for i, tid in enumerate(ids):
        t = session.get(Topic, tid)
        if t:
            t.position = i
    session.flush()
    return list_topics(session)


@router.delete("/topics/{topic_id}")
def delete_topic(topic_id: int, session: Session = Depends(get_session)) -> dict:
    t = session.get(Topic, topic_id) or _404()
    session.delete(t)
    return {"ok": True}


def _404():
    raise HTTPException(404, "não encontrado")


# ---------------------------------------------------------------- AI providers


class AIIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    kind: str = Field(pattern="^(openai|anthropic|cli)$")
    base_url: str | None = None
    model: str | None = None
    api_key: str | None = None
    command: str | None = None
    image_model: str | None = None
    max_tokens: int = Field(1500, ge=100, le=16000)
    timeout_s: int = Field(120, ge=10, le=900)


def ai_out(p: AIProvider) -> dict:
    key = p.api_key or ""
    return {
        "id": p.id, "name": p.name, "kind": p.kind, "base_url": p.base_url, "model": p.model,
        "api_key_set": bool(key), "api_key_hint": f"…{key[-4:]}" if len(key) > 8 else None,
        "command": p.command, "image_model": p.image_model, "max_tokens": p.max_tokens,
        "timeout_s": p.timeout_s, "is_active": p.is_active, "last_test_ok": p.last_test_ok,
        "last_test_message": p.last_test_message, "can_generate_images": AIClient(p).can_generate_images,
    }


@router.get("/ai/providers")
def list_ai(session: Session = Depends(get_session)) -> list[dict]:
    return [ai_out(p) for p in session.scalars(select(AIProvider).order_by(AIProvider.id))]


@router.post("/ai/providers")
def create_ai(body: AIIn, session: Session = Depends(get_session)) -> dict:
    p = AIProvider(**body.model_dump())
    if not session.scalar(select(AIProvider.id).limit(1)):
        p.is_active = True
    session.add(p)
    session.flush()
    return ai_out(p)


@router.put("/ai/providers/{pid}")
def update_ai(pid: int, body: AIIn, session: Session = Depends(get_session)) -> dict:
    p = session.get(AIProvider, pid) or _404()
    data = body.model_dump()
    if not data.get("api_key"):
        data.pop("api_key")  # keep the stored key when the form leaves it blank
    for k, v in data.items():
        setattr(p, k, v)
    return ai_out(p)


@router.post("/ai/providers/{pid}/activate")
def activate_ai(pid: int, session: Session = Depends(get_session)) -> dict:
    target = session.get(AIProvider, pid) or _404()
    for p in session.scalars(select(AIProvider)):
        p.is_active = p.id == target.id
    return ai_out(target)


@router.post("/ai/deactivate")
def deactivate_ai(session: Session = Depends(get_session)) -> dict:
    for p in session.scalars(select(AIProvider)):
        p.is_active = False
    _disable_ai_features(session)
    return {"ok": True}


def _disable_ai_features(session: Session) -> None:
    set_section(session, "newspaper", {"include_charge": False})
    set_section(session, "curation", {"use_ai": False})


@router.post("/ai/providers/{pid}/test")
def test_ai(pid: int, session: Session = Depends(get_session)) -> dict:
    p = session.get(AIProvider, pid) or _404()
    ok, msg = test_provider(p)
    p.last_test_ok, p.last_test_message = ok, msg
    return ai_out(p)


@router.delete("/ai/providers/{pid}")
def delete_ai(pid: int, session: Session = Depends(get_session)) -> dict:
    p = session.get(AIProvider, pid) or _404()
    was_active = p.is_active
    session.delete(p)
    session.flush()
    if was_active and not ai_available(session):
        _disable_ai_features(session)
    return {"ok": True}


# ---------------------------------------------------------------- games


def game_out(g: Game) -> dict:
    return {"id": g.id, "kind": g.kind, "name": g.name, "enabled": g.enabled,
            "position": g.position, "config": g.config}


GAME_SCHEMAS = {
    "sudoku": {"difficulty": ["easy", "medium", "hard"], "count": [1, 2, 3, 4]},
    "wordle": {"language": ["pt", "en"], "length": [4, 5, 6], "attempts": [4, 5, 6, 7, 8]},
    "wordsearch": {"language": ["pt", "en"], "size": [8, 10, 12, 14, 16],
                   "theme": ["news", *sorted({t for v in WORDSEARCH_THEMES.values() for t in v})],
                   "words": [6, 8, 10, 12, 15], "difficulty": ["easy", "medium", "hard"]},
}


@router.get("/games")
def list_games(session: Session = Depends(get_session)) -> dict:
    return {
        "games": [game_out(g) for g in session.scalars(select(Game).order_by(Game.position))],
        "schemas": GAME_SCHEMAS,
        "wordle_sizes": {lang: {n: len(w) for n, w in v.items()} for lang, v in WORDLE.items()},
    }


class GameIn(BaseModel):
    enabled: bool
    config: dict
    name: str | None = None


@router.put("/games/{gid}")
def update_game(gid: int, body: GameIn, session: Session = Depends(get_session)) -> dict:
    g = session.get(Game, gid) or _404()
    schema = GAME_SCHEMAS[g.kind]
    clean = {}
    for k, v in body.config.items():
        if k in schema and v in schema[k]:
            clean[k] = v
    g.config = {**g.config, **clean}
    g.enabled = body.enabled
    if body.name:
        g.name = body.name[:60]
    return game_out(g)


@router.put("/games-order")
def order_games(ids: list[int], session: Session = Depends(get_session)) -> dict:
    for i, gid in enumerate(ids):
        g = session.get(Game, gid)
        if g:
            g.position = i
    session.flush()
    return list_games(session)


@router.get("/games/{gid}/preview")
def preview_game(gid: int, session: Session = Depends(get_session)) -> dict:
    g = session.get(Game, gid) or _404()
    rng = seeded(date.today().isoformat(), f"preview-{g.kind}")
    cfg = g.config
    if g.kind == "sudoku":
        puzzle, solution = GENERATORS["sudoku"](rng, cfg.get("difficulty", "medium"))
    elif g.kind == "wordle":
        puzzle, solution = GENERATORS["wordle"](rng, cfg.get("language", "pt"), int(cfg.get("length", 5)),
                                                int(cfg.get("attempts", 6)))
    else:
        titles = [t for t in session.scalars(select(Edition.headline).where(Edition.headline.is_not(None))
                                             .order_by(Edition.id.desc()).limit(10))]
        puzzle, solution = GENERATORS["wordsearch"](rng, cfg.get("language", "pt"), int(cfg.get("size", 12)),
                                                    cfg.get("theme", "news"), int(cfg.get("words", 10)),
                                                    titles, cfg.get("difficulty", "medium"))
    return {"kind": g.kind, "puzzle": puzzle, "solution": solution}


# ---------------------------------------------------------------- cover preview


@router.post("/preview/cover")
def preview_cover(body: dict, session: Session = Depends(get_session)) -> Response:
    """Render the cover with unsaved newspaper settings (dashboard live preview)."""
    from ..edition.cover import CoverData, render_cover
    from ..edition.i18n import LABELS, long_date, roman
    from ..settings import NewspaperSettings

    current = get_section(session, "newspaper").model_dump()
    current.update({k: v for k, v in body.items() if k in current})
    try:
        news = NewspaperSettings.model_validate(current)
    except ValidationError as exc:
        raise HTTPException(422, exc.errors(include_url=False, include_context=False)) from exc
    L = LABELS[news.language]
    latest = session.scalar(select(Edition).where(Edition.status == EditionStatus.READY)
                            .order_by(Edition.id.desc()).limit(1))
    secondary: list[tuple[str, str]] = []
    headline = "Manchete principal da edição aparece aqui" if news.language == "pt" else "Main headline goes here"
    deck = None
    lead = None
    if latest:
        items = sorted(latest.items, key=lambda i: i.position)
        head = next((i for i in items if i.is_headline), items[0] if items else None)
        if head:
            headline, deck = head.article.title, head.article.subtitle
            lead = (head.article.body or head.article.excerpt or "")[:900]
        topics = {t.slug: t.name for t in session.scalars(select(Topic))}
        secondary = [(topics.get(i.section, i.section), i.article.title) for i in items if not i.is_headline][:6]
    import tempfile
    from pathlib import Path

    device = get_section(session, "device")
    with tempfile.TemporaryDirectory() as tmp:
        dest = Path(tmp) / "cover.png"
        render_cover(CoverData(
            title=news.title, masthead_font=news.masthead_font, tagline=news.tagline,
            long_date=long_date(date.today(), news.language), number_label=f"{L['number']} {latest.number + 1 if latest else 1}",
            year_label=f"{L['year']} {roman(1)}", daily_label=L["daily"], headline=headline, deck=deck,
            also_label=L["also"], secondary=secondary, lead_text=lead,
            footer=" · ".join(g.name for g in session.scalars(select(Game).where(Game.enabled.is_(True)).order_by(Game.position))),
        ), dest, device.cover_width // 2, device.cover_height // 2)
        data = dest.read_bytes()
    return Response(data, media_type="image/png", headers={"Cache-Control": "no-store"})

