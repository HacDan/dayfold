"""Edition generation: collect, curate, games, cartoon, cover, EPUB."""

from __future__ import annotations

import json
import shutil
from dataclasses import replace
from datetime import date
from pathlib import Path

from sqlalchemy import func, select

from .. import clock
from ..config import config
from ..db import session_scope
from ..edition.cover import CoverData, render_cover
from ..edition.epub import EditionDoc, build_epub
from ..edition.i18n import (
    LABELS,
    generated_stamp,
    localized_tagline,
    long_date,
    roman,
    section_name,
    short_date,
)
from ..edition.images import prepare_photo
from ..edition.length import cap as cap_length
from ..edition.length import resolve as resolve_limits
from ..games.generators import GENERATORS, seeded
from ..i18n import tr
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
    UsageMode,
    utcnow,
)
from ..settings import get_section
from ..sources.base import strip_author
from .collect import collect_all
from .curate import curate

GAME_TITLES = {
    "pt": {"sudoku": "Sudoku", "wordle": "Palavra do Dia", "wordsearch": "Caça-palavras",
           "crossword": "Palavras Cruzadas"},
    "en": {"sudoku": "Sudoku", "wordle": "Word of the Day", "wordsearch": "Word Search", "crossword": "Crossword"},
}


class JobLog:
    def __init__(self, job_id: int):
        self.job_id = job_id
        self.tz = clock.zone()  # read once: one job, one zone

    def __call__(self, msg: str) -> None:
        stamp = clock.now(self.tz).strftime("%H:%M:%S")
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


def _article_view(a: Article, section_name: str, lang: str, tz: str | None = None) -> dict:
    # Publication times are stored in UTC; the paper prints them in the operator's zone, the
    # same one the schedule runs on.
    when = clock.in_zone(a.published_at or a.collected_at, tz)
    author = strip_author(a.author)
    if author and author.strip().lower() in a.provider.name.lower():
        author = None  # "Por Agência Senado | Fonte: Agência Senado" says the same thing twice
    return {
        "id": a.id, "title": a.title, "subtitle": a.subtitle, "author": author,
        "date_label": short_date(when.date(), lang) + when.strftime(" · %H:%M"),
        "provider": a.provider.name, "feed_title": a.provider.feed_title,
        "url": a.url, "url_short": _short_url(a.url),
        "paragraphs": _paragraphs(a.body), "excerpt": a.excerpt, "section_name": section_name,
        "image_url": a.image_url, "language": a.language,
        "image_only": a.usage_mode == UsageMode.IMAGE_ONLY,
    }


def today_in_tz() -> date:
    return clock.now().date()


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
            picks, curated_by = curate(s, news, cur, log)
            if not picks:
                raise RuntimeError(tr("nenhuma matéria disponível para a edição (verifique provedores e filtros)",
                                      "no story is available for the edition (check providers and filters)"))
            ed_date = today_in_tz()
            published = Edition.status.in_([EditionStatus.READY, "ARCHIVED"])
            number = (s.scalar(select(func.count(Edition.id)).where(published)) or 0) + 1
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
        out_dir = edition_dir(ed_date, number)
        if out_dir.exists():
            shutil.rmtree(out_dir)
        (out_dir / "img").mkdir(parents=True)
        log(tr(f"Edição nº {number} com {len(picks)} matérias ({'IA' if curated_by == 'ai' else 'regras'}).",
               f"Edition No. {number} with {len(picks)} stories ({'AI' if curated_by == 'ai' else 'rules'})."))
        lang = news.language
        with session_scope() as s:
            rows = [(a.title, a.language) for a in s.scalars(
                select(Article).join(EditionArticle, EditionArticle.article_id == Article.id)
                .where(EditionArticle.edition_id == edition_id).order_by(EditionArticle.position))]
        headlines_text = [t for t, _ in rows]
        same_lang_titles = [t for t, lg in rows if (lg or lang) == lang]

        # ------------------------------------------------------------- games
        if news.include_games:
            log.step("games", 0.55)
            n_games = 0
            with session_scope() as s:
                enabled = list(s.scalars(select(Game).where(Game.enabled.is_(True)).order_by(Game.position)))
                configs = todays_games(enabled, news.games_per_edition, ed_date)
                if configs:
                    log(tr("Jogos do dia (rodízio): ", "Puzzles of the day (rotation): ")
                        + ", ".join(GAME_TITLES[lang].get(g.kind, g.name) for g in configs) + ".")
                for g in configs:
                    cfg = dict(g.config)
                    count = int(cfg.get("count", 1)) if g.kind == "sudoku" else 1
                    for n in range(max(1, min(count, 4))):
                        rng = seeded(ed_date.isoformat(), g.kind, n)
                        puzzle, solution = make_game(g.kind, cfg, rng, lang, same_lang_titles)
                        title = GAME_TITLES[lang].get(g.kind, g.name) + (f" {n + 1}" if count > 1 else "")
                        s.add(GameInstance(edition_id=edition_id, kind=g.kind, position=n_games,
                                           title=title, puzzle=puzzle, solution=solution))
                        n_games += 1
            log(tr(f"{n_games} jogos gerados.", f"{n_games} puzzles generated."))

        # ------------------------------------------------------------ charge
        if news.include_charge:
            log.step("charge", 0.65)
            from ..charge.service import generate_charge

            with session_scope() as s:
                result = generate_charge(s, headlines_text, news.title, lang, charge_cfg, out_dir, log)
                if result:
                    s.add(ChargeAsset(edition_id=edition_id, mode=result["mode"],
                                      status=JobStatus.SUCCEEDED, script=result["script"],
                                      image_path=result["image_path"], caption=result["caption"]))

        epub_path = typeset(edition_id, log)
        with session_scope() as s:
            job = s.get(GenerationJob, job_id)
            job.status = JobStatus.SUCCEEDED
            job.step = "done"
            job.progress = 1.0
            job.finished_at = utcnow()
        log(tr(f"Edição pronta: {epub_path.name} ({epub_path.stat().st_size // 1024} KB).",
               f"Edition ready: {epub_path.name} ({epub_path.stat().st_size // 1024} KB)."))
        _auto_send_kindle(edition_id, epub_path, log)
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
        log(tr(f"Falhou: {exc}", f"Failed: {exc}"))
        raise


def _auto_send_kindle(edition_id: int, epub_path: Path, log) -> None:
    """Native Kindle mode with automatic delivery: e-mail the edition to Send to Kindle.
    A failure is logged and shown on the dashboard, but does not fail the edition."""
    from ..delivery.kindle_mail import KindleMailError, send_and_record
    from ..edition.i18n import book_title

    with session_scope() as s:
        cfg = get_section(s, "kindle")
        if cfg.mode != "native" or not cfg.auto_send:
            return
        ed = s.get(Edition, edition_id)
        lang = get_section(s, "newspaper").language
        path = kindle_epub_path(epub_path, cfg.native_games)
        try:
            log("Send to Kindle: " + send_and_record(s, path, book_title(ed.title or "Dayfold", ed.edition_date, lang)))
        except KindleMailError as exc:
            log(tr(f"Send to Kindle falhou: {exc}", f"Send to Kindle failed: {exc}"))


def game_language(cfg: dict, edition_lang: str) -> str:
    """A puzzle's language: its own setting, or the edition's when it is "auto" (the default)."""
    lang = cfg.get("language") or "auto"
    return edition_lang if lang == "auto" else lang


def make_game(kind: str, cfg: dict, rng, lang: str, headlines: list[str]) -> tuple[dict, dict]:
    """Build a puzzle in the language the game asks for, ``auto`` being the paper's: one edition
    must not mix a Portuguese crossword into an English paper."""
    lang = game_language(cfg, lang)
    if kind == "sudoku":
        return GENERATORS["sudoku"](rng, cfg.get("difficulty", "medium"))
    if kind == "wordle":
        return GENERATORS["wordle"](rng, lang, int(cfg.get("length", 5)),
                                    int(cfg.get("attempts", 6)))
    if kind == "crossword":
        return GENERATORS["crossword"](rng, lang, int(cfg.get("words", 10)),
                                       int(cfg.get("size", 13)))
    return GENERATORS["wordsearch"](rng, lang, int(cfg.get("size", 12)),
                                    cfg.get("theme", "news"), int(cfg.get("words", 10)),
                                    headlines, cfg.get("difficulty", "medium"))


def kindle_test_epub(edition_id: int) -> Path:
    """Native Kindle test EPUB for an edition: every game kind (enabled or not, with its saved
    settings) so all of them can be checked on the device."""
    with session_scope() as s:
        lang = get_section(s, "newspaper").language
        ed = s.get(Edition, edition_id)
        key = f"kindle-test-{ed.edition_date.isoformat()}"
        titles = [a.title for a in s.scalars(
            select(Article).join(EditionArticle, EditionArticle.article_id == Article.id)
            .where(EditionArticle.edition_id == edition_id))]
        games = []
        for g in s.scalars(select(Game).order_by(Game.position)):
            puzzle, solution = make_game(g.kind, dict(g.config), seeded(key, g.kind), lang, titles)
            games.append({"kind": g.kind, "title": GAME_TITLES[lang].get(g.kind, g.name),
                          "puzzle": puzzle, "solution": solution})
    return typeset(edition_id, _PrintLog(), test_games=games)


def todays_games(enabled: list, per_edition: int, day: date) -> list:
    """Pick `per_edition` of the enabled games, rotating by day so each edition varies.

    Keeps the configured order: with games [A, B, C] and 1 per edition the days go A, B, C, A...;
    with 2 per edition: AB, BC, CA, AB..."""
    if not enabled:
        return []
    n = len(enabled)
    k = max(1, min(per_edition, n))
    start = (day.toordinal() * k) % n if k < n else 0
    picked = [enabled[(start + i) % n] for i in range(k)]
    return sorted(picked, key=lambda g: g.position)


def edition_basename(ed_date: date, number: int) -> str:
    return f"dayfold-{ed_date.isoformat()}-{number:04d}"


def edition_dir(ed_date: date, number: int) -> Path:
    return config.editions_dir / f"{ed_date.isoformat()}-{number:04d}"


def kindle_epub_path(epub_path: str | Path, games: bool) -> Path:
    """Native Kindle (Send to Kindle) variant written next to the KOReader EPUB."""
    p = Path(epub_path)
    return p.with_name(p.stem + (".kindle-games.epub" if games else ".kindle.epub"))


def typeset(edition_id: int, log, test_games: list[dict] | None = None) -> Path:
    """Images, cover, EPUB and games.json from what is stored for an edition.

    Used by the generation job and to re-typeset an edition after layout changes
    (no new collection, no AI calls). Besides the KOReader EPUB it writes the two native
    Kindle variants (with and without puzzles).

    With ``test_games`` it only builds the native Kindle test EPUB (those games plus a
    checklist page) and leaves the edition untouched."""
    if hasattr(log, "step"):
        log.step("images", 0.75)
    with session_scope() as s:
        news = get_section(s, "newspaper")
        tz = get_section(s, "schedule").timezone
        device = get_section(s, "device")
        ed = s.get(Edition, edition_id)
        ed_date, number, curated_by = ed.edition_date, ed.number, ed.curated_by
        published = Edition.status.in_([EditionStatus.READY, "ARCHIVED"])
        first = s.scalar(select(func.min(Edition.edition_date)).where(published, Edition.id != edition_id))
        year_n = (ed_date.year - first.year + 1) if first and first < ed_date else 1
        lang = news.language
        L = LABELS[lang]
        topics = {t.slug: t for t in s.scalars(select(Topic))}
        headline = None
        sections: dict[str, dict] = {}
        providers: dict[int, Provider] = {}
        for it in sorted(ed.items, key=lambda i: i.position):
            a = it.article
            providers[a.provider_id] = a.provider
            sec_name = (section_name(it.section, topics[it.section].name, lang) if it.section in topics
                        else it.section.title())
            view = _article_view(a, sec_name, lang, tz)
            view["paragraphs"], view["truncated"] = cap_length(
                view["paragraphs"], resolve_limits(a.provider, topics.get(it.section), news))
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
        games = [{"kind": g.kind, "title": g.title, "puzzle": g.puzzle, "solution": g.solution}
                 for g in sorted(ed.games, key=lambda g: g.position)]
        if test_games is not None:
            games = test_games
        charge = ({"image_path": ed.charge.image_path, "caption": ed.charge.caption}
                  if ed.charge and ed.charge.image_path and Path(ed.charge.image_path).exists() else None)
    out_dir = edition_dir(ed_date, number)
    (out_dir / "img").mkdir(parents=True, exist_ok=True)
    ordered_sections = sorted(sections.values(), key=lambda x: x["position"])
    all_views = ([headline] if headline else []) + [a for s_ in ordered_sections for a in s_["articles"]]
    for v in all_views:
        # A comic's artwork is the story, so it is fetched even when story photos are off.
        if v.get("image_url") and (news.include_images or v.get("image_only")):
            dest = out_dir / "img" / f"a{v['id']}.jpg"
            path = dest if dest.exists() else prepare_photo(v["image_url"], dest, device.image_max_width)
            if path:
                v["image_path"] = str(path)

    # cover
    lead = headline or (ordered_sections[0]["articles"][0] if ordered_sections else None)
    secondary = [(a["section_name"], a["title"]) for s_ in ordered_sections for a in s_["articles"][:1]]
    secondary += [(a["section_name"], a["title"]) for s_ in ordered_sections for a in s_["articles"][1:2]]
    extras = ([L["charge"]] if charge else []) + [g["title"] for g in games]
    source_line = None
    if lead:
        source_line = " | ".join(filter(None, [f"{L['by']} {lead['author']}" if lead.get("author") else None,
                                               lead["provider"]]))
    cover_data = CoverData(
        title=news.title, masthead_font=news.masthead_font, tagline=localized_tagline(news.tagline, lang),
        long_date=long_date(ed_date, lang), number_label=f"{L['number']} {number}",
        year_label=f"{L['year']} {roman(year_n)}", daily_label=L["daily"],
        headline=lead["title"] if lead else news.title,
        deck=lead.get("subtitle") if lead else None, headline_source=source_line,
        image_path=Path(lead["image_path"]) if lead and lead.get("image_path") else None,
        also_label=L["also"], secondary=secondary[:6],
        lead_text=" ".join(lead["paragraphs"][:4]) if lead and lead["paragraphs"] else (lead or {}).get("excerpt"),
        footer=" · ".join(extras),
    )
    if hasattr(log, "step"):
        log.step("cover", 0.85)
    cover_name = "cover-test.png" if test_games is not None else "cover.png"
    cover_path = render_cover(cover_data, out_dir / cover_name, device.cover_width, device.cover_height)

    if hasattr(log, "step"):
        log.step("epub", 0.92)
    identifier = f"dayfold-{ed_date.isoformat()}-{number}"
    doc = EditionDoc(
        identifier=identifier, lang=lang, title=news.title, tagline=localized_tagline(news.tagline, lang),
        long_date=long_date(ed_date, lang), short_date=short_date(ed_date, lang),
        iso_date=ed_date.isoformat(), number_label=f"{L['number']} {number}",
        year_label=f"{L['year']} {roman(year_n)}", masthead_font=news.masthead_font,
        typography=news.typography.model_dump(), cover_path=cover_path, headline=headline,
        sections=ordered_sections, games=[dict(g) for g in games], charge=charge,
        closing_order=news.closing_order, sources=sources, curated_by=curated_by,
        generated_at=generated_stamp(clock.now(tz), lang),
    )
    # One file name per edition, so a second edition on the same day is a new book on the device
    # (and lands on top of the library) instead of overwriting the first one.
    base = edition_basename(ed_date, number)
    if test_games is not None:
        test_doc = replace(doc, native=True, test_checklist=True, identifier=identifier + "-kindle-test",
                           games=[dict(g) for g in games])
        return build_epub(test_doc, out_dir / f"{base}.kindle-test.epub")
    for old in [*out_dir.glob("dayfold-*.epub"), *out_dir.glob("dayfold-*.games.json")]:
        old.unlink()
    epub_path = build_epub(doc, out_dir / f"{base}.epub")
    # Native Kindle variants. Without puzzles the cover must not announce them either.
    build_epub(replace(doc, native=True, games=[dict(g) for g in games]), kindle_epub_path(epub_path, True))
    plain_cover = cover_path
    if games:
        plain_cover = render_cover(replace(cover_data, footer=" · ".join([L["charge"]] if charge else [])),
                                   out_dir / "cover-kindle.png", device.cover_width, device.cover_height)
    build_epub(replace(doc, native=True, games=[], cover_path=plain_cover), kindle_epub_path(epub_path, False))
    games_path = out_dir / f"{base}.games.json"
    games_path.write_text(json.dumps({
        "edition": identifier, "date": ed_date.isoformat(), "title": news.title, "language": lang,
        "games": [{"index": i, "kind": g["kind"], "title": g["title"], "puzzle": g["puzzle"],
                   "solution": g["solution"]} for i, g in enumerate(games)],
    }, ensure_ascii=False))
    with session_scope() as s:
        edition = s.get(Edition, edition_id)
        edition.status = EditionStatus.READY
        edition.title = news.title
        edition.headline = lead["title"] if lead else None
        edition.epub_path = str(epub_path)
        edition.cover_path = str(cover_path)
        edition.games_path = str(games_path)
        edition.stats = {
            "articles": len(all_views), "sections": len(ordered_sections), "games": len(games),
            "charge": bool(charge), "epub_kb": epub_path.stat().st_size // 1024,
            "images": sum(1 for v in all_views if v.get("image_path")),
        }
    return epub_path


class _PrintLog:
    def __call__(self, msg: str) -> None:
        print(msg)


def retypeset(edition_id: int) -> Path:
    return typeset(edition_id, _PrintLog())


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
