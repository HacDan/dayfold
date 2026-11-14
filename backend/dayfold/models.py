"""Database entities. See docs/ARCHITECTURE.md for the role of each table."""

from __future__ import annotations

import enum
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class SourceType(enum.StrEnum):
    RSS = "rss"
    HTML = "html"
    API = "api"


class UsageMode(enum.StrEnum):
    METADATA_ONLY = "metadata_only"
    EXCERPT_AND_LINK = "excerpt_and_link"
    FULL_CONTENT_ALLOWED = "full_content_allowed"


class ScraperStatus(enum.StrEnum):
    PENDING = "PENDING"
    GENERATING = "GENERATING"
    TESTING = "TESTING"
    READY = "READY"
    FAILED = "FAILED"
    DISABLED = "DISABLED"


class JobStatus(enum.StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class EditionStatus(enum.StrEnum):
    BUILDING = "BUILDING"
    READY = "READY"
    FAILED = "FAILED"


class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[Any] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class AIProvider(Base):
    __tablename__ = "ai_providers"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    # openai | anthropic | cli
    kind: Mapped[str] = mapped_column(String(20))
    base_url: Mapped[str | None] = mapped_column(String(300), nullable=True)
    model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    api_key: Mapped[str | None] = mapped_column(String(400), nullable=True)
    command: Mapped[str | None] = mapped_column(String(400), nullable=True)
    image_model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    # CLI agent that can draw (e.g. Codex with image generation): runs in a temp dir and must
    # leave an image file there.
    image_command: Mapped[str | None] = mapped_column(String(400), nullable=True)
    max_tokens: Mapped[int] = mapped_column(Integer, default=1500)
    timeout_s: Mapped[int] = mapped_column(Integer, default=120)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    last_test_ok: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    last_test_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Topic(Base):
    __tablename__ = "topics"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(40), unique=True)
    name: Mapped[str] = mapped_column(String(80))
    keywords: Mapped[list[str]] = mapped_column(JSON, default=list)
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    position: Mapped[int] = mapped_column(Integer, default=0)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    max_articles: Mapped[int] = mapped_column(Integer, default=4)


class Provider(Base):
    __tablename__ = "providers"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(60), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    base_url: Mapped[str] = mapped_column(String(300))
    source_type: Mapped[str] = mapped_column(String(10), default=SourceType.RSS)
    category: Mapped[str] = mapped_column(String(40))  # primary section (first of `categories`)
    # All sections this provider feeds; each story goes to the one whose keywords match it best.
    categories: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    language: Mapped[str] = mapped_column(String(8), default="pt")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    usage_mode: Mapped[str] = mapped_column(String(30), default=UsageMode.EXCERPT_AND_LINK)
    license_name: Mapped[str] = mapped_column(String(120), default="Unknown")
    license_url: Mapped[str | None] = mapped_column(String(300), nullable=True)
    license_note: Mapped[str] = mapped_column(Text, default="")
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    max_items: Mapped[int] = mapped_column(Integer, default=15)
    active_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("scraper_versions.id", use_alter=True, ondelete="SET NULL"), nullable=True
    )
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_run_ok: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    last_run_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_run_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    @property
    def sections(self) -> list[str]:
        return [c for c in (self.categories or []) if c] or [self.category]

    versions: Mapped[list[ScraperVersion]] = relationship(
        back_populates="provider",
        foreign_keys="ScraperVersion.provider_id",
        cascade="all, delete-orphan",
        order_by="ScraperVersion.version",
    )


class ScraperVersion(Base):
    __tablename__ = "scraper_versions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider_id: Mapped[int] = mapped_column(ForeignKey("providers.id", ondelete="CASCADE"))
    version: Mapped[int] = mapped_column(Integer)
    # rss | generic | selectors
    strategy: Mapped[str] = mapped_column(String(20))
    spec: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(12), default=ScraperStatus.PENDING)
    origin: Mapped[str] = mapped_column(String(20), default="manual")  # manual | ai | default
    prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    test_report: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    log: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    provider: Mapped[Provider] = relationship(back_populates="versions", foreign_keys=[provider_id])


class ScraperJob(Base):
    __tablename__ = "scraper_jobs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider_id: Mapped[int] = mapped_column(ForeignKey("providers.id", ondelete="CASCADE"))
    version_id: Mapped[int | None] = mapped_column(
        ForeignKey("scraper_versions.id", ondelete="SET NULL"), nullable=True
    )
    kind: Mapped[str] = mapped_column(String(20), default="generate")  # generate | test
    use_ai: Mapped[bool] = mapped_column(Boolean, default=True)
    extra_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(12), default=JobStatus.QUEUED)
    log: Mapped[list[str]] = mapped_column(JSON, default=list)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Article(Base):
    __tablename__ = "articles"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider_id: Mapped[int] = mapped_column(ForeignKey("providers.id", ondelete="CASCADE"))
    url: Mapped[str] = mapped_column(String(1000))
    url_hash: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(500))
    subtitle: Mapped[str | None] = mapped_column(Text, nullable=True)
    author: Mapped[str | None] = mapped_column(String(300), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    language: Mapped[str | None] = mapped_column(String(8), nullable=True)
    image_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    usage_mode: Mapped[str] = mapped_column(String(30))
    category: Mapped[str | None] = mapped_column(String(40), nullable=True)
    collected_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)

    provider: Mapped[Provider] = relationship()


class Edition(Base):
    __tablename__ = "editions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    number: Mapped[int] = mapped_column(Integer, index=True)
    edition_date: Mapped[date] = mapped_column(Date, index=True)
    title: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(12), default=EditionStatus.BUILDING)
    headline: Mapped[str | None] = mapped_column(String(500), nullable=True)
    epub_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    cover_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    games_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    stats: Mapped[dict] = mapped_column(JSON, default=dict)
    curated_by: Mapped[str] = mapped_column(String(20), default="rules")  # rules | ai
    job_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    items: Mapped[list[EditionArticle]] = relationship(
        back_populates="edition", cascade="all, delete-orphan", order_by="EditionArticle.position"
    )
    games: Mapped[list[GameInstance]] = relationship(
        back_populates="edition", cascade="all, delete-orphan", order_by="GameInstance.position"
    )
    charge: Mapped[ChargeAsset | None] = relationship(
        back_populates="edition", cascade="all, delete-orphan", uselist=False
    )


class EditionArticle(Base):
    __tablename__ = "edition_articles"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    edition_id: Mapped[int] = mapped_column(ForeignKey("editions.id", ondelete="CASCADE"))
    article_id: Mapped[int] = mapped_column(ForeignKey("articles.id", ondelete="CASCADE"))
    section: Mapped[str] = mapped_column(String(40))
    position: Mapped[int] = mapped_column(Integer)
    priority: Mapped[int] = mapped_column(Integer, default=3)  # 1 = highest
    is_headline: Mapped[bool] = mapped_column(Boolean, default=False)
    score: Mapped[float] = mapped_column(Float, default=0)

    edition: Mapped[Edition] = relationship(back_populates="items")
    article: Mapped[Article] = relationship()


class Game(Base):
    __tablename__ = "games"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(20), unique=True)  # sudoku | wordle | wordsearch | crossword
    name: Mapped[str] = mapped_column(String(60))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    config: Mapped[dict] = mapped_column(JSON, default=dict)


class GameInstance(Base):
    __tablename__ = "game_instances"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    edition_id: Mapped[int] = mapped_column(ForeignKey("editions.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(20))
    position: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(120))
    puzzle: Mapped[dict] = mapped_column(JSON)
    solution: Mapped[dict] = mapped_column(JSON)

    edition: Mapped[Edition] = relationship(back_populates="games")


class GenerationJob(Base):
    __tablename__ = "generation_jobs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    trigger: Mapped[str] = mapped_column(String(20), default="manual")  # manual | schedule
    status: Mapped[str] = mapped_column(String(12), default=JobStatus.QUEUED)
    step: Mapped[str | None] = mapped_column(String(40), nullable=True)
    progress: Mapped[float] = mapped_column(Float, default=0)
    log: Mapped[list[str]] = mapped_column(JSON, default=list)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    edition_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ChargeAsset(Base):
    __tablename__ = "charge_assets"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    edition_id: Mapped[int] = mapped_column(ForeignKey("editions.id", ondelete="CASCADE"))
    mode: Mapped[str] = mapped_column(String(20))  # structured | illustrated
    status: Mapped[str] = mapped_column(String(12), default=JobStatus.QUEUED)
    script: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    image_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    caption: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    edition: Mapped[Edition] = relationship(back_populates="charge")
