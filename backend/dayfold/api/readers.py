"""Household readers: one paper per person, each with their own calendar and device link.

The calendar address is a bearer secret, so it is stored server side, masked on read and never
logged; the test action reads the saved address and returns only the count and the feed's own
name, exactly like the paper's own generation does.
"""

from __future__ import annotations

import re
import secrets
import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import agenda, clock
from ..db import get_session
from ..i18n import tr
from ..models import Edition, Reader, ReaderEdition
from ..pipeline.generate import edition_dir
from ..settings import get_section
from .auth import require_admin

router = APIRouter(prefix="/api/readers", tags=["readers"], dependencies=[Depends(require_admin)])


class ReaderIn(BaseModel):
    name: str = Field("", max_length=60)
    ics_url: str = Field("", max_length=600)  # a bearer secret: never returned to the browser
    include_agenda: bool = True

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        return " ".join(v.split())

    @field_validator("ics_url")
    @classmethod
    def _url(cls, v: str) -> str:
        v = v.strip()
        if v.lower().startswith("webcal://"):  # the scheme calendar sites link to
            v = "https://" + v[len("webcal://"):]
        if v and not re.match(r"^https?://", v):
            raise ValueError(tr("o endereço iCal começa com https:// ou webcal://",
                                "the iCal address starts with https:// or webcal://"))
        return v


def _out(r: Reader) -> dict:
    return {"id": r.id, "name": r.name, "ics_url_set": bool(r.ics_url),
            "include_agenda": r.include_agenda, "position": r.position, "token": r.token}


def _reader(session: Session, rid: int) -> Reader:
    r = session.get(Reader, rid)
    if r is None:
        raise HTTPException(404, tr("leitor não encontrado", "reader not found"))
    return r


@router.get("")
def list_readers(session: Session = Depends(get_session)) -> list[dict]:
    return [_out(r) for r in session.scalars(select(Reader).order_by(Reader.position, Reader.id))]


@router.post("")
def create_reader(body: ReaderIn, session: Session = Depends(get_session)) -> dict:
    position = (session.scalar(select(func.max(Reader.position))) or 0) + 1
    r = Reader(name=body.name, ics_url=body.ics_url, include_agenda=body.include_agenda,
               position=position)
    session.add(r)
    session.commit()
    return _out(r)


@router.put("/{rid}")
def update_reader(rid: int, body: ReaderIn, session: Session = Depends(get_session)) -> dict:
    r = _reader(session, rid)
    data = body.model_dump()
    if not data["ics_url"]:
        data.pop("ics_url")  # blank in the form keeps the stored secret
    for key, value in data.items():
        setattr(r, key, value)
    session.commit()
    return _out(r)


@router.delete("/{rid}")
def delete_reader(rid: int, session: Session = Depends(get_session)) -> dict:
    r = _reader(session, rid)
    if (session.scalar(select(func.count(Reader.id))) or 0) <= 1:
        raise HTTPException(409, tr("o jornal precisa de pelo menos um leitor",
                                    "the paper needs at least one reader"))
    editions = list(session.scalars(select(Edition).join(
        ReaderEdition, ReaderEdition.edition_id == Edition.id).where(ReaderEdition.reader_id == rid)))
    for e in editions:
        folder = edition_dir(e.edition_date, e.number) / f"r-{rid}"
        shutil.rmtree(folder, ignore_errors=True)
        # The edition's own paths may point into the copy being removed; hand them to another.
        if e.epub_path and Path(e.epub_path).is_relative_to(folder):
            other = next((c for c in e.copies if c.reader_id != rid and c.epub_path), None)
            e.epub_path = other.epub_path if other else None
            e.cover_path = other.cover_path if other else None
    session.delete(r)
    session.commit()
    return {"ok": True}


@router.post("/{rid}/rotate-token")
def rotate_token(rid: int, session: Session = Depends(get_session)) -> dict:
    r = _reader(session, rid)
    r.token = secrets.token_urlsafe(18)
    session.commit()
    return _out(r)


@router.post("/{rid}/test")
def test_feed(rid: int, session: Session = Depends(get_session)) -> dict:
    """Read this reader's saved feed once and count today's events; nothing is written.

    Only the count and the calendar's own name (``X-WR-CALNAME``) leave the server, never the
    address. The agenda being off does not matter: testing an address is the point.
    """
    r = _reader(session, rid)
    if not r.ics_url:
        return {"ok": False, "events": None, "calendar": None, "reason": "no_address"}
    tz = get_section(session, "schedule").timezone
    feed = agenda.read(r.ics_url, tz, clock.now(tz).date())
    if feed is None:
        return {"ok": False, "events": None, "calendar": None, "reason": "unreadable"}
    return {"ok": True, "events": len(feed.events), "calendar": feed.name}
