"""Scraper creation, regeneration and testing (runs inside the job worker).

Order of attempts: feed discovery, generic extraction, then an AI written selector spec.
A new version only becomes the provider's active version after it passes validation, so
the previous scraper keeps working while a new one is generated or if it fails.
"""

from __future__ import annotations

import json

from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..ai.client import AIError, active_client
from ..db import session_scope
from ..i18n import tr
from ..models import (
    JobStatus,
    Provider,
    ScraperJob,
    ScraperStatus,
    ScraperVersion,
    UsageMode,
    utcnow,
)
from .discovery import discover_feeds, sitemap_urls, trimmed_html
from .runner import run_isolated, validate


class ArticleSelectors(BaseModel):
    title: str | None = None
    subtitle: str | None = None
    author: str | None = None
    date: str | None = None
    body: str | None = None
    image: str | None = None


class SelectorSpec(BaseModel):
    list_url: str
    item_selector: str = Field(min_length=1, max_length=300)
    link_selector: str | None = Field(None, max_length=300)
    article: ArticleSelectors = ArticleSelectors()
    notes: str | None = None


class _Logger:
    def __init__(self, job_id: int, version_id: int | None):
        self.job_id = job_id
        self.version_id = version_id

    def __call__(self, msg: str) -> None:
        with session_scope() as s:
            job = s.get(ScraperJob, self.job_id)
            if job:
                job.log = [*job.log, msg]
            if self.version_id:
                v = s.get(ScraperVersion, self.version_id)
                if v:
                    v.log = [*v.log, msg]


def _set_version(version_id: int, **fields) -> None:
    with session_scope() as s:
        v = s.get(ScraperVersion, version_id)
        for k, val in fields.items():
            setattr(v, k, val)


def next_version_number(session: Session, provider_id: int) -> int:
    n = session.scalar(
        select(func.max(ScraperVersion.version)).where(ScraperVersion.provider_id == provider_id)
    )
    return (n or 0) + 1


def _test(version_id: int, strategy: str, spec: dict, provider: dict, log: _Logger) -> dict:
    _set_version(version_id, status=ScraperStatus.TESTING, strategy=strategy, spec=spec)
    log(tr(f"Testando estratégia '{strategy}' em processo isolado...",
           f"Testing strategy '{strategy}' in an isolated process..."))
    outcome = run_isolated(strategy, spec, max_items=5, language=provider["language"],
                           want_body=provider["usage_mode"] == UsageMode.FULL_CONTENT_ALLOWED)
    for line in outcome.log[-6:]:
        if line:
            log(line.strip()[:400])
    report = validate(outcome, min_items=2, need_body=strategy != "rss")
    _set_version(version_id, test_report=report)
    if report["ok"]:
        log(tr(f"Teste aprovado: {report['count']} matérias, {report['with_body']} com corpo.",
               f"Test passed: {report['count']} stories, {report['with_body']} with body text."))
    else:
        log(tr("Teste reprovado: ", "Test failed: ") + "; ".join(report["reasons"]))
    return report


def _activate(version_id: int, provider_id: int, log: _Logger) -> None:
    with session_scope() as s:
        v = s.get(ScraperVersion, version_id)
        p = s.get(Provider, provider_id)
        v.status = ScraperStatus.READY
        p.active_version_id = v.id
        if v.strategy == "rss":
            p.source_type = "rss"
        else:
            p.source_type = "html"
    log(tr("Versão ativada.", "Version activated."))


AI_PROMPT = """Crie um scraper declarativo (seletores CSS) para o site de notícias abaixo.
O motor do Dayfold abre `list_url`, seleciona `item_selector` (cada item = uma matéria na
listagem), pega o link (`link_selector` relativo ao item, ou o próprio item se for <a>), abre
cada matéria e aplica os seletores de `article`. Seletores de `article` ausentes usam
extração automática (Trafilatura), então só preencha os que tiver certeza.

Responda com JSON neste formato:
{{"list_url": "...", "item_selector": "...", "link_selector": "... ou null",
  "article": {{"title": null, "subtitle": null, "author": null, "date": null, "body": null,
  "image": null}}, "notes": "curta justificativa"}}

Provedor: {name}
URL base: {base_url}
Sitemaps: {sitemaps}
{extra}{previous}
HTML resumido da página de listagem ({list_url}):
{html}
"""


def _ai_attempt(job_id: int, version_id: int, provider: dict, extra_prompt: str | None,
                log: _Logger) -> dict | None:
    with session_scope() as s:
        ai = active_client(s)
    if ai is None:
        log(tr("IA não configurada: criação assistida indisponível.",
               "AI not configured: assisted creation is unavailable."))
        return None
    sitemaps: list[str] = []
    sitemap_urls(provider["base_url"], sitemaps)
    list_url = provider["base_url"]
    try:
        sample = trimmed_html(list_url)
    except Exception as exc:  # noqa: BLE001
        log(tr(f"Não foi possível ler {list_url}: {exc}", f"Could not read {list_url}: {exc}"))
        return None
    previous = ""
    report: dict | None = None
    for attempt in (1, 2):
        _set_version(version_id, status=ScraperStatus.GENERATING)
        log(tr(f"Pedindo seletores à IA ({ai.label}), tentativa {attempt}...",
               f"Asking the AI for selectors ({ai.label}), attempt {attempt}..."))
        prompt = AI_PROMPT.format(
            name=provider["name"], base_url=provider["base_url"], list_url=list_url,
            sitemaps=", ".join(sitemaps) or "nenhum",
            extra=f"Instruções do usuário: {extra_prompt}\n" if extra_prompt else "",
            previous=previous, html=sample,
        )
        try:
            spec = ai.complete_json(prompt, SelectorSpec, max_tokens=800)
        except AIError as exc:
            log(tr(f"Falha da IA: {exc}", f"AI failure: {exc}"))
            return report
        log(tr(f"Spec recebida: item='{spec.item_selector}'. {spec.notes or ''}",
               f"Spec received: item='{spec.item_selector}'. {spec.notes or ''}").strip())
        if spec.list_url != list_url and not spec.list_url.startswith("http"):
            spec.list_url = list_url
        report = _test(version_id, "selectors", spec.model_dump(exclude={"notes"}), provider, log)
        if report["ok"]:
            return report
        previous = (
            "\nTentativa anterior falhou. Spec: "
            + json.dumps(spec.model_dump(), ensure_ascii=False)
            + "\nMotivos: " + "; ".join(report["reasons"]) + "\n"
        )
    return report


def run_scraper_job(job_id: int) -> None:
    with session_scope() as s:
        job = s.get(ScraperJob, job_id)
        provider = s.get(Provider, job.provider_id)
        pdata = {"id": provider.id, "name": provider.name, "base_url": provider.base_url,
                 "language": provider.language, "usage_mode": provider.usage_mode}
        job.status = JobStatus.RUNNING
        job.started_at = utcnow()
        kind, use_ai, extra = job.kind, job.use_ai, job.extra_prompt
        if kind == "test" and job.version_id:
            version_id = job.version_id
            v = s.get(ScraperVersion, version_id)
            strategy, spec = v.strategy, dict(v.spec)
        else:
            v = ScraperVersion(
                provider_id=provider.id, version=next_version_number(s, provider.id),
                strategy="rss", spec={}, status=ScraperStatus.GENERATING,
                origin="ai" if use_ai else "auto", prompt=extra, log=[],
            )
            s.add(v)
            s.flush()
            version_id = v.id
            job.version_id = v.id
            strategy, spec = "", {}
    log = _Logger(job_id, version_id)
    ok = False
    try:
        if kind == "test":
            report = _test(version_id, strategy, spec, pdata, log)
            ok = report["ok"]
            with session_scope() as s:
                is_active = s.get(Provider, pdata["id"]).active_version_id == version_id
            if ok:
                _activate(version_id, pdata["id"], log)
            elif is_active:
                _set_version(version_id, status=ScraperStatus.READY)
                log(tr("A versão ativa falhou no teste agora, mas continua ativa (pode ser instabilidade da fonte).",
                       "The active version just failed its test but stays active (the source may be unstable)."))
            else:
                _set_version(version_id, status=ScraperStatus.FAILED)
            return
        if not (extra and use_ai):
            log(tr(f"Procurando feeds RSS/Atom em {pdata['base_url']}...",
                   f"Looking for RSS/Atom feeds at {pdata['base_url']}..."))
            feeds = discover_feeds(pdata["base_url"], [])
            for url, _n in feeds[:2]:
                report = _test(version_id, "rss", {"feed_url": url}, pdata, log)
                if report["ok"]:
                    ok = True
                    break
            if not ok:
                if not feeds:
                    log(tr("Nenhum feed encontrado.", "No feed found."))
                log(tr("Tentando extração genérica (links + Trafilatura)...",
                       "Trying generic extraction (links + Trafilatura)..."))
                report = _test(version_id, "generic", {"list_url": pdata["base_url"]}, pdata, log)
                ok = report["ok"]
        if not ok and use_ai:
            report = _ai_attempt(job_id, version_id, pdata, extra, log)
            ok = bool(report and report["ok"])
        if ok:
            _activate(version_id, pdata["id"], log)
        else:
            _set_version(version_id, status=ScraperStatus.FAILED)
            log(tr("Nenhuma estratégia passou na validação. A versão anterior (se houver) segue ativa.",
                   "No strategy passed validation. The previous version (if any) stays active."))
    except Exception as exc:
        _set_version(version_id, status=ScraperStatus.FAILED)
        log(tr(f"Erro inesperado: {type(exc).__name__}: {exc}",
               f"Unexpected error: {type(exc).__name__}: {exc}"))
        raise
    finally:
        with session_scope() as s:
            job = s.get(ScraperJob, job_id)
            job.status = JobStatus.SUCCEEDED if ok else JobStatus.FAILED
            job.finished_at = utcnow()
            if not ok and not job.error:
                job.error = "validação falhou"
