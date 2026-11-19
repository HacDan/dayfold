"""Editions, generation jobs, and the device feed (latest edition, games, OPDS)."""

from __future__ import annotations

import shutil
from pathlib import Path
from xml.sax.saxutils import escape

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..db import get_session
from ..i18n import tr
from ..jobs.queue import enqueue_generation
from ..models import (
    Article,
    ArticleRating,
    Edition,
    EditionArticle,
    EditionStatus,
    GenerationJob,
    Provider,
    Reader,
    ReaderEdition,
    Topic,
)
from ..settings import get_section
from .auth import require_admin, require_reader
from .serialize import edition_summary, iso, job_out, section_label

router = APIRouter(prefix="/api", tags=["editions"], dependencies=[Depends(require_admin)])
feed = APIRouter(tags=["feed"])


def _edition(session: Session, eid: int) -> Edition:
    e = session.get(Edition, eid)
    if not e:
        raise HTTPException(404, tr("edição não encontrada", "edition not found"))
    return e


def _file(path: str | None, media: str, filename: str | None = None) -> FileResponse:
    if not path or not Path(path).exists():
        raise HTTPException(404, tr("arquivo indisponível", "file unavailable"))
    return FileResponse(path, media_type=media, filename=filename)


@router.post("/generate")
def generate_now() -> dict:
    return {"job_id": enqueue_generation("manual")}


@router.get("/jobs")
def list_jobs(limit: int = 30, session: Session = Depends(get_session)) -> list[dict]:
    return [job_out(j) for j in session.scalars(select(GenerationJob).order_by(GenerationJob.id.desc()).limit(limit))]


@router.get("/jobs/{job_id}")
def get_job(job_id: int, session: Session = Depends(get_session)) -> dict:
    j = session.get(GenerationJob, job_id)
    if not j:
        raise HTTPException(404, tr("job não encontrado", "job not found"))
    return job_out(j)


@router.get("/editions")
def list_editions(session: Session = Depends(get_session)) -> list[dict]:
    return [edition_summary(e) for e in session.scalars(select(Edition).order_by(Edition.id.desc()).limit(200))]


SEARCH_HITS = 40  # a search is for finding a story, not for reading the whole archive


@router.get("/search")
def search_archive(q: str = "", session: Session = Depends(get_session)) -> dict:
    """Stories already printed in an edition, by title or body text, and whether more exist."""
    term = q.strip()
    if len(term) < 2:
        return {"hits": [], "more": False}
    # A literal % or _ is a character to find, not a wildcard.
    like = "%" + term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
    rows = session.execute(
        select(Edition.id, Edition.number, Edition.edition_date, EditionArticle.section,
               Article.title, Article.body)
        .join(EditionArticle, EditionArticle.edition_id == Edition.id)
        .join(Article, Article.id == EditionArticle.article_id)
        .where(Edition.status == EditionStatus.READY,
               or_(Article.title.ilike(like, escape="\\"), Article.body.ilike(like, escape="\\")))
        .order_by(Edition.edition_date.desc(), Edition.id.desc(), EditionArticle.position)
        .limit(SEARCH_HITS + 1)  # one extra row tells us whether the list was cut short
    ).all()
    topics = {t.slug: t.name for t in session.scalars(select(Topic))}
    return {
        "hits": [
            {"edition_id": eid, "number": number, "date": date.isoformat(),
             "section": section_label(topics, section), "title": title,
             "snippet": _snippet(body or title, term)}
            for eid, number, date, section, title, body in rows[:SEARCH_HITS]
        ],
        "more": len(rows) > SEARCH_HITS,
    }


def _snippet(text: str, term: str, width: int = 150) -> str:
    """A window around the match, so the hit reads as a sentence; no match starts at the top."""
    text = " ".join(text.split())
    start = max(0, text.lower().find(term.lower()) - width // 3)
    piece = text[start:start + width].strip()
    return ("…" if start else "") + piece + ("…" if start + width < len(text) else "")


@router.get("/editions/{eid}")
def get_edition(eid: int, session: Session = Depends(get_session)) -> dict:
    e = _edition(session, eid)
    topics = {t.slug: t.name for t in session.scalars(select(Topic))}
    job = session.get(GenerationJob, e.job_id) if e.job_id else None
    ratings = _ratings(session, e.id)
    return {
        **edition_summary(e),
        "articles": [{
            "id": it.article.id, "position": it.position, "section": it.section,
            "section_name": section_label(topics, it.section), "priority": it.priority,
            "is_headline": it.is_headline, "score": it.score, "title": it.article.title,
            "subtitle": it.article.subtitle, "author": it.article.author,
            "published_at": iso(it.article.published_at), "provider": it.article.provider.name,
            "url": it.article.url, "usage_mode": it.article.usage_mode,
            "has_body": bool(it.article.body), "image_url": it.article.image_url,
            "excerpt": it.article.excerpt, "rating": ratings.get(it.article.id),
        } for it in e.items],
        "games": [{"kind": g.kind, "title": g.title, "puzzle": g.puzzle, "solution": g.solution} for g in e.games],
        "charge": {"mode": e.charge.mode, "caption": e.charge.caption, "script": e.charge.script,
                   "image_url": f"/api/editions/{e.id}/charge.png"} if e.charge and e.charge.image_path else None,
        "job": job_out(job) if job else None,
    }


@router.get("/editions/{eid}/cover.png")
def edition_cover(eid: int, session: Session = Depends(get_session)) -> FileResponse:
    return _file(_edition(session, eid).cover_path, "image/png")


@router.get("/editions/{eid}/charge.png")
def edition_charge(eid: int, session: Session = Depends(get_session)) -> FileResponse:
    e = _edition(session, eid)
    return _file(e.charge.image_path if e.charge else None, "image/png")


@router.get("/editions/{eid}/edition.epub")
def edition_epub(eid: int, session: Session = Depends(get_session)) -> FileResponse:
    e = _edition(session, eid)
    return _file(e.epub_path, "application/epub+zip", Path(e.epub_path or "x.epub").name)


@router.post("/editions/{eid}/retypeset")
def retypeset_edition(eid: int, session: Session = Depends(get_session)) -> dict:
    """Re-typeset cover and EPUB with the current newspaper settings (no collection, no AI)."""
    from ..pipeline.generate import retypeset

    e = _edition(session, eid)
    if e.status not in (EditionStatus.READY, EditionStatus.FAILED) or not e.items:
        raise HTTPException(400, tr("edição sem matérias para recompor", "edition has no stories to typeset again"))
    session.commit()
    retypeset(eid)
    session.expire_all()
    return edition_summary(_edition(session, eid))


@router.post("/editions/{eid}/charge")
def redo_charge(eid: int, session: Session = Depends(get_session)) -> dict:
    """Draw a new cartoon for an edition with the current charge settings, then re-typeset."""
    from ..charge.service import generate_charge
    from ..models import ChargeAsset, JobStatus
    from ..pipeline.generate import edition_dir, retypeset
    from ..settings import get_section

    e = _edition(session, eid)
    news = get_section(session, "newspaper")
    titles = [it.article.title for it in sorted(e.items, key=lambda i: i.position)]
    logs: list[str] = []
    out = edition_dir(e.edition_date, e.number)
    out.mkdir(parents=True, exist_ok=True)
    result = generate_charge(session, titles, news.title, news.language, get_section(session, "charge"),
                             out, logs.append)
    if not result:
        raise HTTPException(400, "; ".join(logs) or tr("não foi possível gerar a charge",
                                                       "could not generate the cartoon"))
    if e.charge:
        session.delete(e.charge)
        session.flush()
    session.add(ChargeAsset(edition_id=e.id, mode=result["mode"], status=JobStatus.SUCCEEDED,
                            script=result["script"], image_path=result["image_path"], caption=result["caption"]))
    session.commit()
    retypeset(eid)
    session.expire_all()
    return {"logs": logs, **edition_summary(_edition(session, eid))}


# ------------------------------------------------------------------ reader ratings


def _ratings(session: Session, eid: int) -> dict[int, int]:
    rows = session.scalars(select(ArticleRating).where(ArticleRating.edition_id == eid))
    return {r.article_id: r.value for r in rows if r.article_id is not None}


def rating_progress(session: Session, e: Edition) -> dict:
    return {"rated": len(_ratings(session, e.id)), "total": len(e.items)}


class RatingsIn(BaseModel):
    # article id -> -1 (less of this), 0 (indifferent), 1 (more of this) or None (clear)
    ratings: dict[int, int | None]


@router.put("/editions/{eid}/ratings")
def rate_edition(eid: int, body: RatingsIn, session: Session = Depends(get_session)) -> dict:
    e = _edition(session, eid)
    items = {it.article_id: it for it in e.items}
    existing = {r.article_id: r for r in session.scalars(
        select(ArticleRating).where(ArticleRating.edition_id == eid))}
    for aid, value in body.ratings.items():
        if aid not in items:
            raise HTTPException(400, f"a matéria {aid} não está nesta edição")
        if value is not None and value not in (-1, 0, 1):
            raise HTTPException(422, "avaliação deve ser -1, 0 ou 1")
        row = existing.get(aid)
        if value is None:
            if row:
                session.delete(row)
            continue
        if row is None:
            it = items[aid]
            row = ArticleRating(edition_id=eid, article_id=aid, provider_id=it.article.provider_id,
                                section=it.section, title=it.article.title, value=value)
            session.add(row)
        row.value = value
    session.flush()
    return {"ratings": _ratings(session, eid), **rating_progress(session, e)}


@router.get("/feedback")
def feedback_summary(session: Session = Depends(get_session)) -> dict:
    """What the curation learned from the ratings (shown next to the rating page)."""
    from ..pipeline.feedback import load_preferences, ranked

    prefs = load_preferences(session)
    providers = {p.id: p.name for p in session.scalars(select(Provider))}
    topics = {t.slug: t.name for t in session.scalars(select(Topic))}
    names = {"providers": lambda k: providers.get(k, "?"), "sections": lambda k: topics.get(k, k),
             "terms": lambda k: k}

    def side(positive: bool) -> dict:
        out = {}
        for kind, label in names.items():
            aff = getattr(prefs, kind)
            out[kind] = [{"name": label(k), "affinity": round(v, 2), "ratings": n}
                         for k, v, n in ranked(aff, prefs.counts.get(kind, {}), positive)]
        return out

    values = [r.value for r in session.scalars(select(ArticleRating))]
    return {
        "count": prefs.count,
        "positive": sum(1 for v in values if v > 0), "neutral": values.count(0),
        "negative": sum(1 for v in values if v < 0),
        "more": side(True), "less": side(False),
    }


@router.delete("/editions/{eid}")
def delete_edition(eid: int, session: Session = Depends(get_session)) -> dict:
    from ..pipeline.generate import edition_dir

    e = _edition(session, eid)
    if e.epub_path:
        # Every reader's copy lives in its own subfolder: the edition's own directory goes.
        shutil.rmtree(edition_dir(e.edition_date, e.number), ignore_errors=True)
    session.delete(e)
    return {"ok": True}


# ------------------------------------------------------------------ device feed


def _latest(session: Session) -> Edition:
    e = session.scalar(select(Edition).where(Edition.status == EditionStatus.READY)
                       .order_by(Edition.edition_date.desc(), Edition.id.desc()).limit(1))
    if not e:
        raise HTTPException(404, tr("nenhuma edição pronta", "no edition is ready"))
    return e


def reader_paper(session: Session, e: Edition, reader: Reader) -> tuple[str | None, str | None]:
    """That reader's own EPUB and cover.

    An edition printed before readers existed has only its own files, which are not anybody's
    personal paper, so they are served as they are. Once an edition has copies, a reader who
    joined later gets nothing from it: another person's front page is not a fallback."""
    copy = session.scalar(select(ReaderEdition).where(
        ReaderEdition.edition_id == e.id, ReaderEdition.reader_id == reader.id))
    if copy and copy.epub_path:
        return copy.epub_path, copy.cover_path
    if session.scalar(select(ReaderEdition.id).where(ReaderEdition.edition_id == e.id).limit(1)):
        return None, None
    return e.epub_path, e.cover_path


@feed.get("/feed/latest.json")
def feed_latest(reader: Reader = Depends(require_reader),
                session: Session = Depends(get_session)) -> dict:
    e = _latest(session)
    epub_source, _ = reader_paper(session, e, reader)
    base = Path(epub_source).stem if epub_source else f"dayfold-{e.edition_date.isoformat()}"
    epub = Path(epub_source) if epub_source else None
    stat = epub.stat() if epub and epub.exists() else None
    return {
        "id": f"dayfold-{e.edition_date.isoformat()}-{e.number}", "number": e.number,
        "date": e.edition_date.isoformat(), "title": e.title, "headline": e.headline,
        "epub": "/feed/latest.epub", "games": "/feed/latest.games.json", "cover": "/feed/latest.cover.png",
        "epub_name": f"{base}.epub", "games_name": f"{base}.games.json",
        "size": stat.st_size if stat else None,
        # The revision follows the file, not the edition: a re-typeset keeps the same id and file
        # name, so the plugin needs something that tells the new file from the copy it has.
        "rev": int(stat.st_mtime) if stat else None,
        "screensaver": get_section(session, "device").screensaver_cover,
    }


@feed.get("/feed/latest.epub")
def feed_epub(reader: Reader = Depends(require_reader),
              session: Session = Depends(get_session)) -> FileResponse:
    epub, _ = reader_paper(session, _latest(session), reader)
    return _file(epub, "application/epub+zip", Path(epub or "x.epub").name)


@feed.get("/feed/latest.games.json")
def feed_games(reader: Reader = Depends(require_reader),
               session: Session = Depends(get_session)) -> FileResponse:
    return _file(_latest(session).games_path, "application/json")


@feed.get("/feed/latest.cover.png")
def feed_cover(reader: Reader = Depends(require_reader),
               session: Session = Depends(get_session)) -> FileResponse:
    _, cover = reader_paper(session, _latest(session), reader)
    return _file(cover, "image/png")


@feed.get("/feed/editions/{eid}.epub")
def feed_edition(eid: int, reader: Reader = Depends(require_reader),
                 session: Session = Depends(get_session)) -> FileResponse:
    epub, _ = reader_paper(session, _edition(session, eid), reader)
    return _file(epub, "application/epub+zip", Path(epub or "x.epub").name)


@feed.get("/feed/editions/{eid}.cover.png")
def feed_edition_cover(eid: int, reader: Reader = Depends(require_reader),
                       session: Session = Depends(get_session)) -> FileResponse:
    _, cover = reader_paper(session, _edition(session, eid), reader)
    return _file(cover, "image/png")


@feed.get("/opds")
def opds(request: Request, reader: Reader = Depends(require_reader),
         session: Session = Depends(get_session)) -> Response:
    """OPDS 1.2 acquisition feed (KOReader: Search > OPDS catalog), with that reader's papers."""
    token = request.query_params.get("token", "")
    q = f"?token={escape(token)}" if token else ""
    editions = list(session.scalars(select(Edition).where(Edition.status == EditionStatus.READY)
                                    .order_by(Edition.id.desc()).limit(30)))
    updated = iso(editions[0].created_at) if editions else "2026-01-01T00:00:00Z"
    entries = []
    for e in editions:
        epub, cover = reader_paper(session, e, reader)
        entries.append(f"""
  <entry>
    <title>{escape(e.title)} | {e.edition_date.isoformat()} | Nº {e.number}</title>
    <id>urn:dayfold:{e.edition_date.isoformat()}:{e.number}:{reader.id}</id>
    <updated>{iso(e.created_at)}</updated>
    <author><name>{escape(e.title)}</name></author>
    <summary>{escape(e.headline or '')}</summary>
    <link rel="http://opds-spec.org/acquisition" type="application/epub+zip" href="/feed/editions/{e.id}.epub{q}"/>
    <link rel="http://opds-spec.org/image" type="image/png" href="/feed/editions/{e.id}.cover.png{q}"/>
    <link rel="http://opds-spec.org/image/thumbnail" type="image/png" href="/feed/editions/{e.id}.cover.png{q}"/>
  </entry>""")
    title = f"Dayfold · {reader.name.strip()}" if reader.name.strip() else "Dayfold"
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:opds="http://opds-spec.org/2010/catalog">
  <id>urn:dayfold:catalog:{reader.id}</id>
  <title>{escape(title)}</title>
  <updated>{updated}</updated>
  <link rel="self" type="application/atom+xml;profile=opds-catalog;kind=acquisition" href="/opds{q}"/>
  <link rel="start" type="application/atom+xml;profile=opds-catalog;kind=acquisition" href="/opds{q}"/>{''.join(entries)}
</feed>"""
    return Response(xml, media_type="application/atom+xml;profile=opds-catalog;kind=acquisition")
