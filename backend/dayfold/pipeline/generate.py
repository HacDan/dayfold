"""Edition generation: collect, curate, games, cartoon, cover, EPUB."""

from __future__ import annotations

import json
import shutil
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import func, select

from ..config import config
from ..db import session_scope
from ..edition.cover import CoverData, render_cover
from ..edition.epub import EditionDoc, build_epub
from ..edition.i18n import LABELS, long_date, roman, short_date
from ..edition.images import prepare_photo
from ..games.generators import GENERATORS, seeded
from ..models import (
    Article,
    ChargeAsset,
    Edition,
    EditionArticle,
    EditionStatus,
    Game,
    GameInstance,
    GenerationJob,
    JobStatus,
    Provider,
    Topic,
    utcnow,
)
from ..settings import get_section
from ..sources.base import strip_author
from .collect import collect_all
from .curate import curate

GAME_TITLES = {
    "pt": {"sudoku": "Sudoku", "wordle": "Palavra do Dia", "wordsearch": "Caça-palavras"},
    "en": {"sudoku": "Sudoku", "wordle": "Word of the Day", "wordsearch": "Word Search"},
}


class JobLog:
    def __init__(self, job_id: int):
        self.job_id = job_id

    def __call__(self, msg: str) -> None:
        stamp = datetime.now().strftime("%H:%M:%S")
        with session_scope() as s:
            job = s.get(GenerationJob, self.job_id)
            job.log = [*job.log, f"[{stamp}] {msg}"]

    def step(self, name: str, progress: float) -> None:
        with session_scope() as s:
            job = s.get(GenerationJob, self.job_id)
            job.step = name
            job.progress = progress


def _paragraphs(body: str | None) -> list[str]:
    return [p.strip() for p in (body or "").split("\n\n") if p.strip()]


def _short_url(url: str) -> str:
    u = url.split("://", 1)[-1]
    return u if len(u) <= 70 else u[:67] + "…"


def _article_view(a: Article, section_name: str, lang: str) -> dict:
    when = a.published_at or a.collected_at
    author = strip_author(a.author)
    if author and author.strip().lower() in a.provider.name.lower():
        author = None  # "Por Agência Senado | Fonte: Agência Senado" says the same thing twice
    return {
        "id": a.id, "title": a.title, "subtitle": a.subtitle, "author": author,
        "date_label": short_date(when.date(), lang) + when.strftime(" · %H:%M UTC"),
        "provider": a.provider.name, "url": a.url, "url_short": _short_url(a.url),
        "paragraphs": _paragraphs(a.body), "excerpt": a.excerpt, "section_name": section_name,
        "image_url": a.image_url, "language": a.language,
    }


def today_in_tz() -> date:
    with session_scope() as s:
        tz = get_section(s, "schedule").timezone
    return datetime.now(ZoneInfo(tz)).date()


def run_generation_job(job_id: int) -> None:
    log = JobLog(job_id)
    with session_scope() as s:
        job = s.get(GenerationJob, job_id)
        job.status = JobStatus.RUNNING
        job.started_at = utcnow()
    edition_id: int | None = None
    try:
        log.step("collect", 0.05)
        collect_all(log)

        log.step("curate", 0.4)
        with session_scope() as s:
            news = get_section(s, "newspaper")
            cur = get_section(s, "curation")
            charge_cfg = get_section(s, "charge")
            device = get_section(s, "device")
            picks, curated_by = curate(s, news, cur, log)
            if not picks:
                raise RuntimeError("nenhuma matéria disponível para a edição (verifique provedores e filtros)")
            ed_date = today_in_tz()
            published = Edition.status.in_([EditionStatus.READY, "ARCHIVED"])
            number = (s.scalar(select(func.count(Edition.id)).where(published)) or 0) + 1
            first = s.scalar(select(func.min(Edition.edition_date)).where(published))
            year_n = (ed_date.year - first.year + 1) if first else 1
            edition = Edition(number=number, edition_date=ed_date, title=news.title,
                              status=EditionStatus.BUILDING, curated_by=curated_by, job_id=job_id)
            s.add(edition)
            s.flush()
            edition_id = edition.id
            for i, p in enumerate(picks):
                s.add(EditionArticle(edition_id=edition.id, article_id=p.article_id, section=p.section,
                                     position=i, priority=p.priority, is_headline=p.is_headline,
                                     score=p.score))
            job = s.get(GenerationJob, job_id)
            job.edition_id = edition.id
        lang = news.language
        L = LABELS[lang]
        out_dir = config.editions_dir / f"{ed_date.isoformat()}-{number:04d}"
        if out_dir.exists():
            shutil.rmtree(out_dir)
        (out_dir / "img").mkdir(parents=True)
        log(f"Edição nº {number} com {len(picks)} matérias ({'IA' if curated_by == 'ai' else 'regras'}).")

        # ------------------------------------------------------ article views
        log.step("images", 0.5)
        with session_scope() as s:
            topics = {t.slug: t for t in s.scalars(select(Topic))}
            items = list(s.scalars(select(EditionArticle).where(EditionArticle.edition_id == edition_id)
                                   .order_by(EditionArticle.position)))
            headline = None
            sections: dict[str, dict] = {}
            headlines_text: list[str] = []
            same_lang_titles: list[str] = []
            providers: dict[int, Provider] = {}
            for it in items:
                a = it.article
                providers[a.provider_id] = a.provider
                sec_name = topics[it.section].name if it.section in topics else it.section.title()
                view = _article_view(a, sec_name, lang)
                headlines_text.append(a.title)
                if (a.language or lang) == lang:
                    same_lang_titles.append(a.title)
                if it.is_headline:
                    headline = view
                    continue
                sec = sections.setdefault(it.section, {
                    "slug": it.section, "name": sec_name, "file": f"sec_{it.section}.xhtml",
                    "articles": [], "position": topics[it.section].position if it.section in topics else 99,
                })
                sec["articles"].append(view)
            sources = [{"name": p.name, "license": p.license_name, "license_url": p.license_url}
                       for p in providers.values()]
        ordered_sections = sorted(sections.values(), key=lambda x: x["position"])
        if news.include_images:
            for v in ([headline] if headline else []) + [a for s_ in ordered_sections for a in s_["articles"]]:
                if v.get("image_url"):
                    path = prepare_photo(v["image_url"], out_dir / "img" / f"a{v['id']}.jpg",
                                         device.image_max_width)
                    if path:
                        v["image_path"] = str(path)

        # ------------------------------------------------------------- games
        games: list[dict] = []
        if news.include_games:
            log.step("games", 0.6)
            with session_scope() as s:
                configs = list(s.scalars(select(Game).where(Game.enabled.is_(True)).order_by(Game.position)))
                for g in configs:
                    cfg = dict(g.config)
                    count = int(cfg.get("count", 1)) if g.kind == "sudoku" else 1
                    for n in range(max(1, min(count, 4))):
                        rng = seeded(ed_date.isoformat(), g.kind, n)
                        if g.kind == "sudoku":
                            puzzle, solution = GENERATORS["sudoku"](rng, cfg.get("difficulty", "medium"))
                        elif g.kind == "wordle":
                            puzzle, solution = GENERATORS["wordle"](
                                rng, cfg.get("language", lang), int(cfg.get("length", 5)),
                                int(cfg.get("attempts", 6)))
                        else:
                            puzzle, solution = GENERATORS["wordsearch"](
                                rng, cfg.get("language", lang), int(cfg.get("size", 12)),
                                cfg.get("theme", "news"), int(cfg.get("words", 10)),
                                same_lang_titles, cfg.get("difficulty", "medium"))
                        title = GAME_TITLES[lang][g.kind] + (f" {n + 1}" if count > 1 else "")
                        s.add(GameInstance(edition_id=edition_id, kind=g.kind, position=len(games),
                                           title=title, puzzle=puzzle, solution=solution))
                        games.append({"kind": g.kind, "title": title, "puzzle": puzzle,
                                      "solution": solution})
            log(f"{len(games)} jogos gerados.")

        # ------------------------------------------------------------ charge
        charge = None
        if news.include_charge:
            log.step("charge", 0.7)
            from ..charge.service import generate_charge

            with session_scope() as s:
                result = generate_charge(s, headlines_text, news.title, lang, charge_cfg, out_dir, log)
                if result:
                    s.add(ChargeAsset(edition_id=edition_id, mode=result["mode"],
                                      status=JobStatus.SUCCEEDED, script=result["script"],
                                      image_path=result["image_path"], caption=result["caption"]))
                    charge = {"image_path": result["image_path"], "caption": result["caption"]}

        # ------------------------------------------------------------- cover
        log.step("cover", 0.8)
        lead = headline or (ordered_sections[0]["articles"][0] if ordered_sections else None)
        secondary = [(a["section_name"], a["title"]) for s_ in ordered_sections for a in s_["articles"][:1]]
        secondary += [(a["section_name"], a["title"]) for s_ in ordered_sections for a in s_["articles"][1:2]]
        extras = []
        if charge:
            extras.append(L["charge"])
        extras += [g["title"] for g in games]
        source_line = None
        if lead:
            source_line = " | ".join(filter(None, [f"{L['by']} {lead['author']}" if lead.get("author") else None,
                                                   lead["provider"]]))
        cover_data = CoverData(
            title=news.title, masthead_font=news.masthead_font, tagline=news.tagline,
            long_date=long_date(ed_date, lang), number_label=f"{L['number']} {number}",
            year_label=f"{L['year']} {roman(year_n)}", daily_label=L["daily"],
            headline=lead["title"] if lead else news.title,
            deck=lead.get("subtitle") if lead else None, headline_source=source_line,
            image_path=Path(lead["image_path"]) if lead and lead.get("image_path") else None,
            also_label=L["also"], secondary=secondary[:6],
            lead_text=" ".join(lead["paragraphs"][:4]) if lead and lead["paragraphs"] else (lead or {}).get("excerpt"),
            footer=" · ".join(extras),
        )
        cover_path = render_cover(cover_data, out_dir / "cover.png", device.cover_width, device.cover_height)

        # -------------------------------------------------------------- epub
        log.step("epub", 0.9)
        identifier = f"dayfold-{ed_date.isoformat()}-{number}"
        doc = EditionDoc(
            identifier=identifier, lang=lang, title=news.title, tagline=news.tagline,
            long_date=long_date(ed_date, lang), short_date=short_date(ed_date, lang),
            iso_date=ed_date.isoformat(), number_label=f"{L['number']} {number}",
            year_label=f"{L['year']} {roman(year_n)}", masthead_font=news.masthead_font,
            typography=news.typography.model_dump(), cover_path=cover_path, headline=headline,
            sections=ordered_sections, games=[dict(g) for g in games], charge=charge,
            closing_order=news.closing_order, sources=sources, curated_by=curated_by,
            generated_at=datetime.now().strftime("%d/%m/%Y %H:%M"),
        )
        epub_path = build_epub(doc, out_dir / f"dayfold-{ed_date.isoformat()}.epub")
        games_path = out_dir / f"dayfold-{ed_date.isoformat()}.games.json"
        games_path.write_text(json.dumps({
            "edition": identifier, "date": ed_date.isoformat(), "title": news.title, "language": lang,
            "games": [{"index": i, "kind": g["kind"], "title": g["title"], "puzzle": g["puzzle"],
                       "solution": g["solution"]} for i, g in enumerate(games)],
        }, ensure_ascii=False))

        with session_scope() as s:
            edition = s.get(Edition, edition_id)
            edition.status = EditionStatus.READY
            edition.headline = lead["title"] if lead else None
            edition.epub_path = str(epub_path)
            edition.cover_path = str(cover_path)
            edition.games_path = str(games_path)
            edition.stats = {
                "articles": len(picks), "sections": len(ordered_sections), "games": len(games),
                "charge": bool(charge), "epub_kb": epub_path.stat().st_size // 1024,
                "images": sum(1 for v in [headline, *[a for s_ in ordered_sections for a in s_["articles"]]]
                              if v and v.get("image_path")),
            }
            job = s.get(GenerationJob, job_id)
            job.status = JobStatus.SUCCEEDED
            job.step = "done"
            job.progress = 1.0
            job.finished_at = utcnow()
        log(f"Edição pronta: {epub_path.name} ({epub_path.stat().st_size // 1024} KB).")
        _prune()
    except Exception as exc:
        with session_scope() as s:
            job = s.get(GenerationJob, job_id)
            job.status = JobStatus.FAILED
            job.error = f"{type(exc).__name__}: {exc}"
            job.finished_at = utcnow()
            if edition_id:
                ed = s.get(Edition, edition_id)
                ed.status = EditionStatus.FAILED
        log(f"Falhou: {exc}")
        raise


def _prune() -> None:
    with session_scope() as s:
        keep = get_section(s, "distribution").keep_editions
        old = list(s.scalars(select(Edition).where(Edition.status == EditionStatus.READY)
                             .order_by(Edition.edition_date.desc(), Edition.id.desc()).offset(keep)))
        for ed in old:
            if ed.epub_path:
                shutil.rmtree(Path(ed.epub_path).parent, ignore_errors=True)
            ed.epub_path = ed.cover_path = ed.games_path = None
            ed.status = "ARCHIVED"
