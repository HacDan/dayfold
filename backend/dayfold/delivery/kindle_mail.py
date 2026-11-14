"""Send to Kindle by e-mail through the user's Gmail account (SMTP with an app password).

Amazon only accepts documents from addresses on the account's approved list, converts the
EPUB and delivers it to the Kindle over Wi-Fi."""

from __future__ import annotations

import smtplib
import ssl
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path

from sqlalchemy.orm import Session

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
        labels = {"kindle_email": "e-mail do Kindle", "gmail_address": "Gmail", "gmail_app_password": "senha de app"}
        raise KindleMailError("configure antes: " + ", ".join(labels[k] for k in missing))
    if not epub.exists():
        raise KindleMailError(f"arquivo não encontrado: {epub.name}")
    if epub.stat().st_size > MAX_BYTES:
        raise KindleMailError(f"{epub.name} passa de 25 MB, o limite de anexo do Gmail")
    msg = EmailMessage()
    msg["From"] = cfg.gmail_address
    msg["To"] = cfg.kindle_email
    msg["Subject"] = subject
    msg.set_content("Dayfold: edição enviada para o Kindle.")
    msg.add_attachment(epub.read_bytes(), maintype="application", subtype="epub+zip", filename=epub.name)
    try:
        with smtplib.SMTP(GMAIL_HOST, GMAIL_PORT, timeout=60) as smtp:
            smtp.starttls(context=ssl.create_default_context())
            smtp.login(cfg.gmail_address, cfg.gmail_app_password)
            smtp.send_message(msg)
    except smtplib.SMTPAuthenticationError as exc:
        raise KindleMailError("o Gmail recusou o login: confira o endereço e a senha de app "
                              "(a verificação em duas etapas precisa estar ativa)") from exc
    except (smtplib.SMTPException, OSError) as exc:
        raise KindleMailError(f"falha no envio pelo Gmail: {exc}") from exc


def send_and_record(session: Session, epub: Path, subject: str) -> str:
    """Send, store the outcome in the settings (shown on the dashboard) and return a message.
    Raises KindleMailError after recording a failure."""
    cfg = get_section(session, "kindle")
    if missing_fields(cfg):
        send_epub(cfg, epub, subject)  # raises the "configure first" error, nothing to record
    stamp = datetime.now().strftime("%d/%m/%Y %H:%M")
    try:
        send_epub(cfg, epub, subject)
    except KindleMailError as exc:
        set_section(session, "kindle", {"last_send_at": stamp, "last_send_ok": False,
                                        "last_send_message": str(exc)})
        session.commit()
        raise
    message = f"{epub.name} enviado para {cfg.kindle_email}"
    set_section(session, "kindle", {"last_send_at": stamp, "last_send_ok": True, "last_send_message": message})
    session.commit()
    return message
