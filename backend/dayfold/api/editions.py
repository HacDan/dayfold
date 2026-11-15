"""Editions, generation jobs, and the device feed (latest edition, games, OPDS)."""

from __future__ import annotations

import shutil
from pathlib import Path
from xml.sax.saxutils import escape

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_session
from ..jobs.queue import enqueue_generation
from ..models import Edition, EditionStatus, GenerationJob, Topic
from ..settings import get_section
from .auth import require_admin, require_feed_token
from .serialize import edition_summary, iso, job_out, section_label

router = APIRouter(prefix="/api", tags=["editions"], dependencies=[Depends(require_admin)])
feed = APIRouter(tags=["feed"])


def _edition(session: Session, eid: int) -> Edition:
    e = session.get(Edition, eid)
    if not e:
        raise HTTPException(404, "edição não encontrada")
    return e


def _file(path: str | None, media: str, filename: str | None = None) -> FileResponse:
    if not path or not Path(path).exists():
        raise HTTPException(404, "arquivo indisponível")
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
        raise HTTPException(404, "job não encontrado")
    return job_out(j)


@router.get("/editions")
def list_editions(session: Session = Depends(get_session)) -> list[dict]:
    return [edition_summary(e) for e in session.scalars(select(Edition).order_by(Edition.id.desc()).limit(200))]


@router.get("/editions/{eid}")
def get_edition(eid: int, session: Session = Depends(get_session)) -> dict:
    e = _edition(session, eid)
    topics = {t.slug: t.name for t in session.scalars(select(Topic))}
    job = session.get(GenerationJob, e.job_id) if e.job_id else None
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
        raise HTTPException(400, "edição sem matérias para recompor")
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
        raise HTTPException(400, "; ".join(logs) or "não foi possível gerar a charge")
    if e.charge:
        session.delete(e.charge)
        session.flush()
    session.add(ChargeAsset(edition_id=e.id, mode=result["mode"], status=JobStatus.SUCCEEDED,
                            script=result["script"], image_path=result["image_path"], caption=result["caption"]))
    session.commit()
    retypeset(eid)
    session.expire_all()
    return {"logs": logs, **edition_summary(_edition(session, eid))}


@router.delete("/editions/{eid}")
def delete_edition(eid: int, session: Session = Depends(get_session)) -> dict:
    e = _edition(session, eid)
    if e.epub_path:
        shutil.rmtree(Path(e.epub_path).parent, ignore_errors=True)
    session.delete(e)
    return {"ok": True}


# ------------------------------------------------------------------ device feed


def _latest(session: Session) -> Edition:
    e = session.scalar(select(Edition).where(Edition.status == EditionStatus.READY)
                       .order_by(Edition.edition_date.desc(), Edition.id.desc()).limit(1))
    if not e:
        raise HTTPException(404, "nenhuma edição pronta")
    return e


@feed.get("/feed/latest.json", dependencies=[Depends(require_feed_token)])
def feed_latest(session: Session = Depends(get_session)) -> dict:
    e = _latest(session)
    base = Path(e.epub_path).stem if e.epub_path else f"dayfold-{e.edition_date.isoformat()}"
    return {
        "id": f"dayfold-{e.edition_date.isoformat()}-{e.number}", "number": e.number,
        "date": e.edition_date.isoformat(), "title": e.title, "headline": e.headline,
        "epub": "/feed/latest.epub", "games": "/feed/latest.games.json", "cover": "/feed/latest.cover.png",
        "epub_name": f"{base}.epub", "games_name": f"{base}.games.json",
        "size": Path(e.epub_path).stat().st_size if e.epub_path and Path(e.epub_path).exists() else None,
        "screensaver": get_section(session, "device").screensaver_cover,
    }


@feed.get("/feed/latest.epub", dependencies=[Depends(require_feed_token)])
def feed_epub(session: Session = Depends(get_session)) -> FileResponse:
    e = _latest(session)
    return _file(e.epub_path, "application/epub+zip", Path(e.epub_path or "x.epub").name)


@feed.get("/feed/latest.games.json", dependencies=[Depends(require_feed_token)])
def feed_games(session: Session = Depends(get_session)) -> FileResponse:
    return _file(_latest(session).games_path, "application/json")


@feed.get("/feed/latest.cover.png", dependencies=[Depends(require_feed_token)])
def feed_cover(session: Session = Depends(get_session)) -> FileResponse:
    return _file(_latest(session).cover_path, "image/png")


@feed.get("/feed/editions/{eid}.epub", dependencies=[Depends(require_feed_token)])
def feed_edition(eid: int, session: Session = Depends(get_session)) -> FileResponse:
    e = _edition(session, eid)
    return _file(e.epub_path, "application/epub+zip", Path(e.epub_path or "x.epub").name)


@feed.get("/feed/editions/{eid}.cover.png", dependencies=[Depends(require_feed_token)])
def feed_edition_cover(eid: int, session: Session = Depends(get_session)) -> FileResponse:
    return _file(_edition(session, eid).cover_path, "image/png")


@feed.get("/opds", dependencies=[Depends(require_feed_token)])
def opds(request: Request, session: Session = Depends(get_session)) -> Response:
    """OPDS 1.2 acquisition feed (KOReader: Search > OPDS catalog)."""
    token = request.query_params.get("token", "")
    q = f"?token={escape(token)}" if token else ""
    editions = list(session.scalars(select(Edition).where(Edition.status == EditionStatus.READY)
                                    .order_by(Edition.id.desc()).limit(30)))
    updated = iso(editions[0].created_at) if editions else "2026-01-01T00:00:00Z"
    entries = []
    for e in editions:
        entries.append(f"""
  <entry>
    <title>{escape(e.title)} | {e.edition_date.isoformat()} | Nº {e.number}</title>
    <id>urn:dayfold:{e.edition_date.isoformat()}:{e.number}</id>
    <updated>{iso(e.created_at)}</updated>
    <author><name>{escape(e.title)}</name></author>
    <summary>{escape(e.headline or '')}</summary>
    <link rel="http://opds-spec.org/acquisition" type="application/epub+zip" href="/feed/editions/{e.id}.epub{q}"/>
    <link rel="http://opds-spec.org/image" type="image/png" href="/feed/editions/{e.id}.cover.png{q}"/>
    <link rel="http://opds-spec.org/image/thumbnail" type="image/png" href="/feed/editions/{e.id}.cover.png{q}"/>
  </entry>""")
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:opds="http://opds-spec.org/2010/catalog">
  <id>urn:dayfold:catalog</id>
  <title>Dayfold</title>
  <updated>{updated}</updated>
  <link rel="self" type="application/atom+xml;profile=opds-catalog;kind=acquisition" href="/opds{q}"/>
  <link rel="start" type="application/atom+xml;profile=opds-catalog;kind=acquisition" href="/opds{q}"/>{''.join(entries)}
</feed>"""
    return Response(xml, media_type="application/atom+xml;profile=opds-catalog;kind=acquisition")
