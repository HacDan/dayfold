"""Native Kindle (no jailbreak): Send to Kindle by e-mail, downloads and the test edition."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_session
from ..delivery.kindle_mail import KindleMailError, send_and_record
from ..edition.i18n import book_title
from ..models import Edition, EditionStatus
from ..pipeline.generate import kindle_epub_path, kindle_test_epub, retypeset
from ..settings import get_section
from .auth import require_admin, require_feed_token

router = APIRouter(prefix="/api/kindle", tags=["kindle"], dependencies=[Depends(require_admin)])
feed = APIRouter(tags=["feed"])

EPUB = "application/epub+zip"


def _latest(session: Session) -> Edition:
    e = session.scalar(select(Edition).where(Edition.status == EditionStatus.READY)
                       .order_by(Edition.edition_date.desc(), Edition.id.desc()).limit(1))
    if not e or not e.epub_path:
        raise HTTPException(404, "nenhuma edição pronta")
    return e


def native_epub(session: Session, e: Edition) -> Path:
    """The native Kindle EPUB for an edition (with or without puzzles, per the settings).
    Editions typeset before this feature get their variants on first use."""
    games = get_section(session, "kindle").native_games
    path = kindle_epub_path(e.epub_path, games)
    if not path.exists():
        retypeset(e.id)
    return path


def _subject(session: Session, e: Edition) -> str:
    return book_title(e.title or "Dayfold", e.edition_date, get_section(session, "newspaper").language)


class SendIn(BaseModel):
    edition_id: int | None = None


@router.post("/send")
def send(body: SendIn, session: Session = Depends(get_session)) -> dict:
    e = session.get(Edition, body.edition_id) if body.edition_id else _latest(session)
    if not e or not e.epub_path:
        raise HTTPException(404, "edição não encontrada")
    path = native_epub(session, e)
    try:
        return {"message": send_and_record(session, path, _subject(session, e))}
    except KindleMailError as exc:
        raise HTTPException(400, str(exc)) from exc


class TestIn(BaseModel):
    send: bool = False


@router.post("/test")
def test_edition(body: TestIn, session: Session = Depends(get_session)) -> dict:
    e = _latest(session)
    path = kindle_test_epub(e.id)
    out = {"download": "/api/kindle/test.epub", "file": path.name, "message": None}
    if body.send:
        subject = _subject(session, e) + " (teste)"
        try:
            out["message"] = send_and_record(session, path, subject)
        except KindleMailError as exc:
            raise HTTPException(400, str(exc)) from exc
    return out


@router.get("/test.epub")
def download_test(session: Session = Depends(get_session)) -> FileResponse:
    e = _latest(session)
    path = Path(e.epub_path).with_name(Path(e.epub_path).stem + ".kindle-test.epub")
    if not path.exists():
        raise HTTPException(404, "gere a edição de teste antes")
    return FileResponse(path, media_type=EPUB, filename=path.name)


@router.get("/latest.epub")
def download_latest(session: Session = Depends(get_session)) -> FileResponse:
    path = native_epub(session, _latest(session))
    return FileResponse(path, media_type=EPUB, filename=path.name)


@feed.get("/feed/latest.kindle.epub", dependencies=[Depends(require_feed_token)])
def feed_latest_native(session: Session = Depends(get_session)) -> FileResponse:
    path = native_epub(session, _latest(session))
    return FileResponse(path, media_type=EPUB, filename=path.name)
