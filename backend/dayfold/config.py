"""Process level configuration, read from environment variables.

Everything the user can change at runtime lives in the ``settings`` table instead
(see :mod:`dayfold.settings`).
"""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass, field
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
ASSETS_DIR = PACKAGE_DIR / "assets"
FONTS_DIR = ASSETS_DIR / "fonts"
TEMPLATES_DIR = PACKAGE_DIR / "edition" / "templates"


LANGUAGES = ("pt", "en")


def _default_language() -> str:
    raw = (os.environ.get("DAYFOLD_LANGUAGE") or "").strip().lower()
    return raw[:2] if raw[:2] in LANGUAGES else "pt"


def _default_data_dir() -> Path:
    xdg = os.environ.get("XDG_DATA_HOME")
    base = Path(xdg) if xdg else Path.home() / ".local" / "share"
    return base / "dayfold"


def _default_web_dir() -> Path:
    # Built dashboard: <repo>/frontend/dist when running from a checkout.
    return PACKAGE_DIR.parent.parent / "frontend" / "dist"


@dataclass
class Config:
    data_dir: Path = field(
        default_factory=lambda: Path(os.environ.get("DAYFOLD_DATA_DIR") or _default_data_dir())
    )
    host: str = field(default_factory=lambda: os.environ.get("DAYFOLD_HOST", "0.0.0.0"))
    port: int = field(default_factory=lambda: int(os.environ.get("DAYFOLD_PORT", "8422")))
    password: str | None = field(default_factory=lambda: os.environ.get("DAYFOLD_PASSWORD") or None)
    web_dir: Path = field(
        default_factory=lambda: Path(os.environ.get("DAYFOLD_WEB_DIR") or _default_web_dir())
    )
    public_url: str | None = field(default_factory=lambda: os.environ.get("DAYFOLD_PUBLIC_URL"))
    # Language of the server's own text (API errors, labels, logs), not of the newspaper.
    language: str = field(default_factory=_default_language)
    disable_scheduler: bool = field(
        default_factory=lambda: os.environ.get("DAYFOLD_DISABLE_SCHEDULER", "") == "1"
    )

    @property
    def db_path(self) -> Path:
        return self.data_dir / "dayfold.db"

    @property
    def editions_dir(self) -> Path:
        return self.data_dir / "editions"

    @property
    def cache_dir(self) -> Path:
        return self.data_dir / "cache"

    def secret_key(self) -> str:
        """Persistent secret used to sign session cookies."""
        path = self.data_dir / "secret.key"
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(secrets.token_urlsafe(48))
            path.chmod(0o600)
        return path.read_text().strip()

    def ensure_dirs(self) -> None:
        for d in (self.data_dir, self.editions_dir, self.cache_dir):
            d.mkdir(parents=True, exist_ok=True)


config = Config()
