"""Providers and scrapers."""

from __future__ import annotations

import re
import unicodedata

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, HttpUrl, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_session
from ..jobs.queue import enqueue_scraper
from ..models import Provider, ScraperJob, ScraperStatus, ScraperVersion, UsageMode
from ..sources.builder import next_version_number
from ..sources.strategies import ALLOWED_STRATEGIES
from .auth import require_admin
from .serialize import provider_out, scraper_job_out, version_out

router = APIRouter(prefix="/api", tags=["providers"], dependencies=[Depends(require_admin)])


def slugify(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")[:50] or "fonte"


class ProviderIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    base_url: HttpUrl
    category: str | None = Field(None, max_length=40)  # legacy single section
    categories: list[str] = Field(default_factory=list, max_length=12)

    @model_validator(mode="after")
    def _sections(self):
        cats = [c.strip() for c in self.categories if c and c.strip()]
        if not cats and self.category:
            cats = [self.category.strip()]
        if not cats:
            raise ValueError("escolha ao menos uma seção")
        self.categories = list(dict.fromkeys(cats))[:12]
        self.category = self.categories[0]
        return self
    language: str = Field("pt", max_length=8)
    usage_mode: UsageMode = UsageMode.EXCERPT_AND_LINK
    license_name: str = Field("Verificar termos", max_length=120)
    license_url: str | None = None
    license_note: str = ""
    enabled: bool = True
    max_items: int = Field(15, ge=1, le=50)


class ProviderCreate(ProviderIn):
    mode: str = Field("assisted", pattern="^(manual|assisted)$")
    strategy: str | None = None
    spec: dict | None = None
    use_ai: bool = True
    extra_prompt: str | None = Field(None, max_length=1500)


def _get(session: Session, pid: int) -> Provider:
    p = session.get(Provider, pid)
    if not p:
        raise HTTPException(404, "provedor não encontrado")
    return p


@router.get("/providers")
def list_providers(session: Session = Depends(get_session)) -> list[dict]:
    return [provider_out(p) for p in session.scalars(select(Provider).order_by(Provider.category, Provider.name))]


@router.get("/providers/{pid}")
def get_provider(pid: int, session: Session = Depends(get_session)) -> dict:
    p = _get(session, pid)
    jobs = session.scalars(select(ScraperJob).where(ScraperJob.provider_id == pid)
                           .order_by(ScraperJob.id.desc()).limit(10))
    return {**provider_out(p, with_versions=True), "jobs": [scraper_job_out(j) for j in jobs]}


@router.post("/providers")
def create_provider(body: ProviderCreate, session: Session = Depends(get_session)) -> dict:
    slug = base = slugify(body.name)
    n = 2
    while session.scalar(select(Provider.id).where(Provider.slug == slug)):
        slug = f"{base}-{n}"
        n += 1
    data = body.model_dump(exclude={"mode", "strategy", "spec", "use_ai", "extra_prompt"})
    data["base_url"] = str(body.base_url)
    p = Provider(slug=slug, source_type="rss" if body.strategy == "rss" else "html", **data)
    session.add(p)
    session.flush()
    if body.mode == "manual":
        if body.strategy not in ALLOWED_STRATEGIES or not body.spec:
            raise HTTPException(422, "criação manual exige estratégia e spec")
        v = ScraperVersion(provider_id=p.id, version=1, strategy=body.strategy, spec=body.spec,
                           status=ScraperStatus.PENDING, origin="manual", log=["Criada manualmente."])
        session.add(v)
        session.flush()
        session.commit()
        enqueue_scraper(p.id, kind="test", use_ai=False, version_id=v.id)
    else:
        session.commit()
        enqueue_scraper(p.id, kind="generate", use_ai=body.use_ai, extra_prompt=body.extra_prompt)
    session.refresh(p)
    return provider_out(p)


@router.put("/providers/{pid}")
def update_provider(pid: int, body: ProviderIn, session: Session = Depends(get_session)) -> dict:
    p = _get(session, pid)
    for k, v in body.model_dump().items():
        setattr(p, k, str(v) if k == "base_url" else v)
    return provider_out(p)


@router.delete("/providers/{pid}")
def delete_provider(pid: int, session: Session = Depends(get_session)) -> dict:
    p = _get(session, pid)
    p.active_version_id = None
    session.flush()
    session.delete(p)
    return {"ok": True}


@router.post("/providers/{pid}/test")
def test_provider(pid: int, session: Session = Depends(get_session)) -> dict:
    p = _get(session, pid)
    if not p.active_version_id:
        raise HTTPException(400, "provedor sem scraper ativo")
    session.commit()
    job_id = enqueue_scraper(pid, kind="test", use_ai=False, version_id=p.active_version_id)
    return {"job_id": job_id}


class RegenerateIn(BaseModel):
    use_ai: bool = True
    extra_prompt: str | None = Field(None, max_length=1500)


@router.post("/providers/{pid}/regenerate")
def regenerate(pid: int, body: RegenerateIn, session: Session = Depends(get_session)) -> dict:
    _get(session, pid)
    running = session.scalar(select(ScraperJob.id).where(ScraperJob.provider_id == pid,
                                                         ScraperJob.status.in_(["QUEUED", "RUNNING"])))
    if running:
        raise HTTPException(409, "já existe uma geração em andamento para este provedor")
    session.commit()
    job_id = enqueue_scraper(pid, kind="generate", use_ai=body.use_ai, extra_prompt=body.extra_prompt)
    return {"job_id": job_id}


class ManualVersionIn(BaseModel):
    strategy: str
    spec: dict


@router.post("/providers/{pid}/versions")
def add_manual_version(pid: int, body: ManualVersionIn, session: Session = Depends(get_session)) -> dict:
    _get(session, pid)
    if body.strategy not in ALLOWED_STRATEGIES:
        raise HTTPException(422, "estratégia inválida")
    v = ScraperVersion(provider_id=pid, version=next_version_number(session, pid), strategy=body.strategy,
                       spec=body.spec, status=ScraperStatus.PENDING, origin="manual", log=["Criada manualmente."])
    session.add(v)
    session.flush()
    session.commit()
    job_id = enqueue_scraper(pid, kind="test", use_ai=False, version_id=v.id)
    return {"job_id": job_id, "version_id": v.id}


@router.get("/scrapers")
def list_scrapers(session: Session = Depends(get_session)) -> list[dict]:
    rows = []
    for p in session.scalars(select(Provider).order_by(Provider.name)):
        for v in reversed(p.versions):
            rows.append({**version_out(v, p.active_version_id), "provider_name": p.name})
    return rows


@router.get("/scraper-jobs")
def list_scraper_jobs(provider_id: int | None = None, session: Session = Depends(get_session)) -> list[dict]:
    q = select(ScraperJob).order_by(ScraperJob.id.desc()).limit(30)
    if provider_id:
        q = q.where(ScraperJob.provider_id == provider_id)
    return [scraper_job_out(j) for j in session.scalars(q)]


@router.get("/scraper-jobs/{job_id}")
def get_scraper_job(job_id: int, session: Session = Depends(get_session)) -> dict:
    j = session.get(ScraperJob, job_id)
    if not j:
        raise HTTPException(404, "job não encontrado")
    return scraper_job_out(j)


def _version(session: Session, vid: int) -> ScraperVersion:
    v = session.get(ScraperVersion, vid)
    if not v:
        raise HTTPException(404, "versão não encontrada")
    return v


@router.post("/scrapers/{vid}/activate")
def activate_version(vid: int, session: Session = Depends(get_session)) -> dict:
    """Rollback or roll forward to a version that passed its test."""
    v = _version(session, vid)
    report = v.test_report or {}
    if v.status not in (ScraperStatus.READY, ScraperStatus.DISABLED) or (v.origin != "default" and not report.get("ok")):
        raise HTTPException(400, "só versões validadas podem ser ativadas")
    v.status = ScraperStatus.READY
    v.provider.active_version_id = v.id
    return version_out(v, v.id)


@router.post("/scrapers/{vid}/disable")
def disable_version(vid: int, session: Session = Depends(get_session)) -> dict:
    v = _version(session, vid)
    v.status = ScraperStatus.DISABLED
    if v.provider.active_version_id == v.id:
        v.provider.active_version_id = None
    return version_out(v, v.provider.active_version_id)


@router.post("/scrapers/{vid}/enable")
def enable_version(vid: int, session: Session = Depends(get_session)) -> dict:
    v = _version(session, vid)
    session.commit()
    job_id = enqueue_scraper(v.provider_id, kind="test", use_ai=False, version_id=v.id)
    return {"job_id": job_id}


@router.delete("/scrapers/{vid}")
def delete_version(vid: int, session: Session = Depends(get_session)) -> dict:
    v = _version(session, vid)
    if v.provider.active_version_id == v.id:
        raise HTTPException(400, "desative ou troque a versão ativa antes de excluir")
    session.delete(v)
    return {"ok": True}
