"""User editable settings stored in the ``settings`` table, validated with Pydantic.

Typography sizes are limited to ranges that keep the Kindle layout intact. Values are
``em`` multipliers relative to the reader's base font size, so the user can still change
the font size on the device.
"""

from __future__ import annotations

import re
import secrets
from typing import Literal

from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from .config import FONTS_DIR
from .models import Setting

MASTHEAD_FONTS: dict[str, dict] = {
    "chomsky": {
        "label": "Chomsky (blackletter clássico)",
        "family": "Chomsky",
        "file": "Chomsky.otf",
        "license": "SIL OFL 1.1",
    },
    "unifraktur-maguntia": {
        "label": "UnifrakturMaguntia (gótica)",
        "family": "UnifrakturMaguntia",
        "file": "UnifrakturMaguntia-Book.ttf",
        "license": "SIL OFL 1.1",
    },
    "unifraktur-cook": {
        "label": "UnifrakturCook (gótica negrito)",
        "family": "UnifrakturCook",
        "file": "UnifrakturCook-Bold.ttf",
        "license": "SIL OFL 1.1",
    },
    "old-standard": {
        "label": "Old Standard TT (romana vitoriana)",
        "family": "Old Standard TT",
        "file": "OldStandard-Bold.ttf",
        "license": "SIL OFL 1.1",
    },
    "playfair": {
        "label": "Playfair Display Black (didone)",
        "family": "Playfair Display",
        "file": "PlayfairDisplay-Black.ttf",
        "license": "SIL OFL 1.1",
    },
}

# (min, default, max) in em. Validated server side and exposed to the dashboard.
TYPE_RANGES: dict[str, tuple[float, float, float]] = {
    "masthead": (2.4, 3.4, 4.4),
    "headline": (1.5, 2.1, 2.7),
    "title": (1.15, 1.45, 1.8),
    "subtitle": (0.95, 1.1, 1.3),
    "body": (0.85, 1.0, 1.25),
    "line_height": (1.3, 1.5, 1.75),
}


class Typography(BaseModel):
    masthead: float = TYPE_RANGES["masthead"][1]
    headline: float = TYPE_RANGES["headline"][1]
    title: float = TYPE_RANGES["title"][1]
    subtitle: float = TYPE_RANGES["subtitle"][1]
    body: float = TYPE_RANGES["body"][1]
    line_height: float = TYPE_RANGES["line_height"][1]

    @field_validator("*")
    @classmethod
    def _clamp(cls, v: float, info) -> float:
        lo, _, hi = TYPE_RANGES[info.field_name]
        return round(min(max(float(v), lo), hi), 3)


class NewspaperSettings(BaseModel):
    title: str = Field("Dayfold", min_length=1, max_length=40)
    tagline: str = Field("Notícias do dia, dobradas para ler com calma.", max_length=120)
    masthead_font: str = "chomsky"
    language: Literal["pt", "en"] = "pt"
    max_articles: int = Field(16, ge=3, le=60)
    excerpt_words: int = Field(70, ge=20, le=200)
    include_images: bool = True
    include_charge: bool = False
    include_games: bool = True
    closing_order: list[Literal["news", "charge", "games"]] = ["news", "charge", "games"]
    typography: Typography = Typography()

    @field_validator("masthead_font")
    @classmethod
    def _font(cls, v: str) -> str:
        if v not in MASTHEAD_FONTS:
            raise ValueError(f"unknown masthead font {v!r}")
        return v

    @field_validator("closing_order")
    @classmethod
    def _order(cls, v: list[str]) -> list[str]:
        if sorted(set(v)) != ["charge", "games", "news"] or len(v) != 3:
            raise ValueError("closing_order must contain news, charge and games once")
        return v


class ScheduleSettings(BaseModel):
    enabled: bool = True
    time: str = "09:00"
    timezone: str = "America/Sao_Paulo"

    @field_validator("time")
    @classmethod
    def _time(cls, v: str) -> str:
        if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", v):
            raise ValueError("time must be HH:MM")
        return v

    @field_validator("timezone")
    @classmethod
    def _tz(cls, v: str) -> str:
        from zoneinfo import ZoneInfo

        ZoneInfo(v)
        return v


class CurationSettings(BaseModel):
    use_ai: bool = False
    max_age_hours: int = Field(36, ge=6, le=24 * 7)
    languages: list[str] = ["pt", "en"]
    blocked_keywords: list[str] = []
    ai_candidates: int = Field(40, ge=10, le=120)
    per_provider_limit: int = Field(4, ge=1, le=20)


class ChargeSettings(BaseModel):
    mode: Literal["structured", "illustrated"] = "structured"
    style: str = Field(
        "Charge editorial elegante, bem-humorada e respeitosa, sem ataques pessoais.",
        max_length=400,
    )


class DeviceSettings(BaseModel):
    cover_width: int = Field(1236, ge=600, le=2000)
    cover_height: int = Field(1648, ge=800, le=2600)
    image_max_width: int = Field(1000, ge=300, le=1600)


class DistributionSettings(BaseModel):
    feed_token: str = Field(default_factory=lambda: secrets.token_urlsafe(18))
    keep_editions: int = Field(30, ge=1, le=365)


SECTIONS: dict[str, type[BaseModel]] = {
    "newspaper": NewspaperSettings,
    "schedule": ScheduleSettings,
    "curation": CurationSettings,
    "charge": ChargeSettings,
    "device": DeviceSettings,
    "distribution": DistributionSettings,
}


def get_section(session: Session, key: str) -> BaseModel:
    model = SECTIONS[key]
    row = session.get(Setting, key)
    if row is None:
        value = model()
        session.add(Setting(key=key, value=value.model_dump()))
        session.flush()
        return value
    return model.model_validate(row.value)


def set_section(session: Session, key: str, data: dict) -> BaseModel:
    model = SECTIONS[key]
    current = get_section(session, key).model_dump()
    current.update(data)
    value = model.model_validate(current)
    row = session.get(Setting, key)
    assert row is not None
    row.value = value.model_dump()
    session.flush()
    return value


def all_settings(session: Session) -> dict[str, dict]:
    return {k: get_section(session, k).model_dump() for k in SECTIONS}


def masthead_font_path(key: str) -> str:
    return str(FONTS_DIR / MASTHEAD_FONTS[key]["file"])
