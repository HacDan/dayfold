from __future__ import annotations

from datetime import datetime

from ..models import Edition, GenerationJob, Provider, ScraperJob, ScraperVersion


def iso(dt: datetime | None) -> str | None:
    return dt.isoformat() + ("Z" if dt and dt.tzinfo is None else "") if dt else None


def edition_summary(e: Edition) -> dict:
    return {
        "id": e.id, "number": e.number, "date": e.edition_date.isoformat(), "title": e.title,
        "status": e.status, "headline": e.headline, "stats": e.stats, "curated_by": e.curated_by,
        "created_at": iso(e.created_at), "has_epub": bool(e.epub_path),
        "cover_url": f"/api/editions/{e.id}/cover.png" if e.cover_path else None,
        "epub_url": f"/api/editions/{e.id}/edition.epub" if e.epub_path else None,
    }


def job_out(j: GenerationJob) -> dict:
    return {
        "id": j.id, "trigger": j.trigger, "status": j.status, "step": j.step, "progress": j.progress,
        "log": j.log, "error": j.error, "edition_id": j.edition_id, "created_at": iso(j.created_at),
        "started_at": iso(j.started_at), "finished_at": iso(j.finished_at),
    }


def version_out(v: ScraperVersion, active_id: int | None = None) -> dict:
    return {
        "id": v.id, "provider_id": v.provider_id, "version": v.version, "strategy": v.strategy,
        "spec": v.spec, "status": v.status, "origin": v.origin, "prompt": v.prompt,
        "test_report": v.test_report, "log": v.log, "is_active": v.id == active_id,
        "created_at": iso(v.created_at), "updated_at": iso(v.updated_at),
    }


def scraper_job_out(j: ScraperJob) -> dict:
    return {
        "id": j.id, "provider_id": j.provider_id, "version_id": j.version_id, "kind": j.kind,
        "use_ai": j.use_ai, "extra_prompt": j.extra_prompt, "status": j.status, "log": j.log,
        "error": j.error, "created_at": iso(j.created_at), "finished_at": iso(j.finished_at),
    }


def provider_out(p: Provider, *, with_versions: bool = False) -> dict:
    active = next((v for v in p.versions if v.id == p.active_version_id), None)
    latest = p.versions[-1] if p.versions else None
    out = {
        "id": p.id, "slug": p.slug, "name": p.name, "base_url": p.base_url,
        "source_type": p.source_type, "category": p.category, "categories": p.sections, "language": p.language,
        "enabled": p.enabled, "usage_mode": p.usage_mode, "license_name": p.license_name,
        "license_url": p.license_url, "license_note": p.license_note, "is_default": p.is_default,
        "max_items": p.max_items, "active_version_id": p.active_version_id,
        "active_version": version_out(active, p.active_version_id) if active else None,
        "latest_status": latest.status if latest else None,
        "latest_version": latest.version if latest else None,
        "last_run_at": iso(p.last_run_at), "last_run_ok": p.last_run_ok,
        "last_run_message": p.last_run_message, "last_run_count": p.last_run_count,
    }
    if with_versions:
        out["versions"] = [version_out(v, p.active_version_id) for v in reversed(p.versions)]
    return out
