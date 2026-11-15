"""Optional dashboard password (signed cookie) and feed tokens for devices."""

from __future__ import annotations

import hmac

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from itsdangerous import BadSignature, URLSafeTimedSerializer
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..config import config
from ..db import get_session
from ..i18n import tr
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


def require_feed_token(request: Request, session: Session = Depends(get_session)) -> None:
    expected = get_section(session, "distribution").feed_token
    supplied = request.query_params.get("token") or request.headers.get("x-dayfold-token")
    if not supplied and request.headers.get("authorization", "").lower().startswith("basic "):
        import base64

        try:
            raw = base64.b64decode(request.headers["authorization"][6:]).decode()
            supplied = raw.split(":", 1)[1]
        except Exception:  # noqa: BLE001
            supplied = None
    if supplied and hmac.compare_digest(supplied, expected):
        return
    if is_authenticated(request) and config.password:
        return  # logged in dashboard users can download too
    raise HTTPException(401, tr("token inválido", "invalid token"),
                        headers={"WWW-Authenticate": 'Basic realm="Dayfold"'})


class LoginIn(BaseModel):
    password: str


@router.get("/status")
def status(request: Request) -> dict:
    """Bootstrap call for the dashboard: the language it should start in when the operator has
    never picked one is the server's own (``DAYFOLD_LANGUAGE``)."""
    return {"required": bool(config.password), "authenticated": is_authenticated(request),
            "language": config.language}


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
