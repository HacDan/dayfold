"""Optional dashboard password (signed cookie) and feed tokens for devices."""

from __future__ import annotations

import hmac

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from itsdangerous import BadSignature, URLSafeTimedSerializer
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import config
from ..db import get_session
from ..i18n import tr
from ..models import Reader
from ..settings import get_section

COOKIE = "dayfold_session"
MAX_AGE = 60 * 60 * 24 * 30

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(config.secret_key(), salt="dayfold-session")


def is_authenticated(request: Request) -> bool:
    if not config.password:
        return True
    token = request.cookies.get(COOKIE)
    if not token:
        return False
    try:
        _serializer().loads(token, max_age=MAX_AGE)
        return True
    except BadSignature:
        return False


def require_admin(request: Request) -> None:
    if not is_authenticated(request):
        raise HTTPException(401, tr("login necessário", "login required"))


def _supplied_token(request: Request) -> str | None:
    supplied = request.query_params.get("token") or request.headers.get("x-dayfold-token")
    if not supplied and request.headers.get("authorization", "").lower().startswith("basic "):
        import base64

        try:
            raw = base64.b64decode(request.headers["authorization"][6:]).decode()
            supplied = raw.split(":", 1)[1]
        except Exception:  # noqa: BLE001
            supplied = None
    return supplied


def require_reader(request: Request, session: Session = Depends(get_session)) -> Reader:
    """The reader whose secret token is in the address.

    Each reader's device address carries their own token, so a Kindle downloads the paper made for
    its person. A logged in dashboard user without a token gets the first reader's, which is what
    the dashboard's own download links use."""
    supplied = _supplied_token(request)
    if supplied:
        for reader in session.scalars(select(Reader).order_by(Reader.id)):
            if hmac.compare_digest(supplied, reader.token):
                return reader
    if config.password and is_authenticated(request):
        first = session.scalar(select(Reader).order_by(Reader.position, Reader.id).limit(1))
        if first is not None:
            return first
    raise HTTPException(401, tr("token inválido", "invalid token"),
                        headers={"WWW-Authenticate": 'Basic realm="Dayfold"'})


class LoginIn(BaseModel):
    password: str


@router.get("/status")
def status(request: Request, session: Session = Depends(get_session)) -> dict:
    """Bootstrap call for the dashboard: the language it should start in when the operator has
    never picked one is the server's own (``DAYFOLD_LANGUAGE``), and the timezone its dates are
    rendered in (the schedule's, so the dashboard and the printed paper agree)."""
    return {"required": bool(config.password), "authenticated": is_authenticated(request),
            "language": config.language,
            "timezone": get_section(session, "schedule").timezone}


@router.post("/login")
def login(body: LoginIn, response: Response) -> dict:
    if not config.password:
        return {"ok": True}
    if not hmac.compare_digest(body.password, config.password):
        raise HTTPException(401, tr("senha incorreta", "wrong password"))
    response.set_cookie(COOKIE, _serializer().dumps("admin"), max_age=MAX_AGE, httponly=True,
                        samesite="lax")
    return {"ok": True}


@router.post("/logout")
def logout(response: Response) -> dict:
    response.delete_cookie(COOKIE)
    return {"ok": True}
