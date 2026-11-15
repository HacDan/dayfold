"""Send to Kindle by e-mail through the user's Gmail account (SMTP with an app password).

Amazon only accepts documents from addresses on the account's approved list, converts the
EPUB and delivers it to the Kindle over Wi-Fi."""

from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage
from pathlib import Path

from sqlalchemy.orm import Session

from .. import clock
from ..i18n import language, tr
from ..settings import KindleSettings, get_section, set_section

GMAIL_HOST = "smtp.gmail.com"
GMAIL_PORT = 587
MAX_BYTES = 25 * 1024 * 1024  # Gmail attachment limit (Amazon accepts up to 50 MB)


class KindleMailError(RuntimeError):
    pass


def missing_fields(cfg: KindleSettings) -> list[str]:
    return [k for k in ("kindle_email", "gmail_address", "gmail_app_password") if not getattr(cfg, k)]


def send_epub(cfg: KindleSettings, epub: Path, subject: str) -> None:
    missing = missing_fields(cfg)
    if missing:
        labels = {"kindle_email": ("e-mail do Kindle", "Kindle e-mail"),
                  "gmail_address": ("Gmail", "Gmail"),
                  "gmail_app_password": ("senha de app", "app password")}
        raise KindleMailError(tr("configure antes: " + ", ".join(labels[k][0] for k in missing),
                                 "configure first: " + ", ".join(labels[k][1] for k in missing)))
    if not epub.exists():
        raise KindleMailError(tr(f"arquivo não encontrado: {epub.name}", f"file not found: {epub.name}"))
    if epub.stat().st_size > MAX_BYTES:
        raise KindleMailError(tr(f"{epub.name} passa de 25 MB, o limite de anexo do Gmail",
                                 f"{epub.name} is over 25 MB, the Gmail attachment limit"))
    msg = EmailMessage()
    msg["From"] = cfg.gmail_address
    msg["To"] = cfg.kindle_email
    msg["Subject"] = subject
    msg.set_content(tr("Dayfold: edição enviada para o Kindle.", "Dayfold: edition sent to your Kindle."))
    msg.add_attachment(epub.read_bytes(), maintype="application", subtype="epub+zip", filename=epub.name)
    try:
        with smtplib.SMTP(GMAIL_HOST, GMAIL_PORT, timeout=60) as smtp:
            smtp.starttls(context=ssl.create_default_context())
            smtp.login(cfg.gmail_address, cfg.gmail_app_password)
            smtp.send_message(msg)
    except smtplib.SMTPAuthenticationError as exc:
        raise KindleMailError(tr("o Gmail recusou o login: confira o endereço e a senha de app "
                                 "(a verificação em duas etapas precisa estar ativa)",
                                 "Gmail rejected the login: check the address and the app password "
                                 "(two-step verification must be on)")) from exc
    except (smtplib.SMTPException, OSError) as exc:
        raise KindleMailError(tr(f"falha no envio pelo Gmail: {exc}", f"Gmail send failed: {exc}")) from exc


def send_and_record(session: Session, epub: Path, subject: str) -> str:
    """Send, store the outcome in the settings (shown on the dashboard) and return a message.
    Raises KindleMailError after recording a failure."""
    cfg = get_section(session, "kindle")
    if missing_fields(cfg):
        send_epub(cfg, epub, subject)  # raises the "configure first" error, nothing to record
    stamp = clock.now().strftime("%m/%d/%Y %H:%M" if language() == "en" else "%d/%m/%Y %H:%M")
    try:
        send_epub(cfg, epub, subject)
    except KindleMailError as exc:
        set_section(session, "kindle", {"last_send_at": stamp, "last_send_ok": False,
                                        "last_send_message": str(exc)})
        session.commit()
        raise
    message = tr(f"{epub.name} enviado para {cfg.kindle_email}", f"{epub.name} sent to {cfg.kindle_email}")
    set_section(session, "kindle", {"last_send_at": stamp, "last_send_ok": True, "last_send_message": message})
    session.commit()
    return message
