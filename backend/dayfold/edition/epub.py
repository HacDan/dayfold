"""EPUB assembly with EbookLib and Jinja2 templates."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ebooklib import epub
from jinja2 import Environment, FileSystemLoader, select_autoescape

from ..config import FONTS_DIR, TEMPLATES_DIR
from ..settings import MASTHEAD_FONTS
from .i18n import LABELS

env = Environment(
    loader=FileSystemLoader(TEMPLATES_DIR),
    autoescape=select_autoescape(["j2"], default_for_string=True, default=True),
    trim_blocks=True,
    lstrip_blocks=True,
)

TEXT_FONTS = [
    "PlayfairDisplay-Bold.ttf", "PlayfairDisplay-Black.ttf", "PlayfairDisplay-Italic.ttf",
    "Literata-Regular.ttf", "Literata-Bold.ttf", "Literata-Italic.ttf",
    "OldStandard-Regular.ttf", "OldStandard-Bold.ttf", "OldStandard-Italic.ttf",
]


@dataclass
class EditionDoc:
    identifier: str
    lang: str
    title: str
    tagline: str
    long_date: str
    short_date: str
    iso_date: str
    number_label: str
    year_label: str
    masthead_font: str
    typography: dict
    cover_path: Path
    headline: dict | None
    sections: list[dict]
    games: list[dict] = field(default_factory=list)
    charge: dict | None = None
    closing_order: list[str] = field(default_factory=lambda: ["news", "charge", "games"])
    sources: list[dict] = field(default_factory=list)
    curated_by: str = "rules"
    generated_at: str = ""
    # Native Kindle (Send to Kindle, no jailbreak): no KOReader links, and the answer pages sit
    # behind a warning page at the end in case the conversion ignores linear="no".
    native: bool = False
    # Test edition for native Kindle: adds a page with what to check on the device.
    test_checklist: bool = False


def _page(uid: str, file_name: str, title: str, body: str, lang: str, css: epub.EpubItem) -> epub.EpubHtml:
    item = epub.EpubHtml(uid=uid, file_name=file_name, title=title, lang=lang)
    item.content = f"<html><head><title>{title}</title></head><body>{body}</body></html>"
    item.add_item(css)
    return item


def _font_media(name: str) -> str:
    return "font/otf" if name.endswith(".otf") else "font/ttf"


def build_epub(doc: EditionDoc, dest: Path) -> Path:
    L = LABELS[doc.lang]

    class tpl:  # noqa: N801 - every template also sees ``native``
        def __init__(self, name: str):
            self.t = env.get_template(name)

        def render(self, **kw) -> str:
            return self.t.render(native=doc.native, **kw)
    book = epub.EpubBook()
    book.set_identifier(doc.identifier)
    from datetime import date as _date

    from .i18n import book_title

    book.set_title(book_title(doc.title, _date.fromisoformat(doc.iso_date), doc.lang))
    book.set_language(doc.lang)
    book.add_author(doc.title)
    book.add_metadata("DC", "date", doc.iso_date)
    book.add_metadata("DC", "publisher", "Dayfold")
    book.add_metadata("DC", "description", f"{doc.title} | {doc.long_date} | {doc.number_label}")
    book.add_metadata(None, "meta", "", {"name": "dayfold:edition", "content": doc.identifier})
    book.set_cover("images/cover.png", Path(doc.cover_path).read_bytes(), create_page=True)
    cover_page = book.get_item_with_id("cover")
    if cover_page is not None:
        cover_page.is_linear = True  # the reader starts at the front page cover

    masthead_file = MASTHEAD_FONTS[doc.masthead_font]["file"]
    for name in {*TEXT_FONTS, masthead_file}:
        book.add_item(epub.EpubItem(uid=f"font-{name}", file_name=f"fonts/{name}",
                                    media_type=_font_media(name),
                                    content=(FONTS_DIR / name).read_bytes()))
    css_text = tpl("style.css.j2").render(t=doc.typography, masthead_file=masthead_file)
    css = epub.EpubItem(uid="style", file_name="style/edition.css", media_type="text/css",
                        content=css_text.encode())
    book.add_item(css)

    # images referenced by articles, games and the cartoon
    def add_image_bytes(data: bytes, name: str) -> str:
        book.add_item(epub.EpubItem(uid=f"img-{name}", file_name=f"images/{name}",
                                    media_type="image/png", content=data))
        return f"images/{name}"

    def add_image(local: str | Path, name: str) -> str:
        data = Path(local).read_bytes()
        mt = "image/png" if name.endswith(".png") else "image/jpeg"
        book.add_item(epub.EpubItem(uid=f"img-{name}", file_name=f"images/{name}", media_type=mt,
                                    content=data))
        return f"images/{name}"

    for a in ([doc.headline] if doc.headline else []) + [a for s in doc.sections for a in s["articles"]]:
        if a.get("image_path"):
            a["image"] = add_image(a["image_path"], Path(a["image_path"]).name)

    ed = {
        "title": doc.title, "tagline": doc.tagline, "long_date": doc.long_date,
        "short_date": doc.short_date, "number_label": doc.number_label,
        "year_label": doc.year_label,
    }
    spine: list = ["cover"]
    toc: list = []
    nonlinear: list = []

    for i, g in enumerate(doc.games):
        g["index"] = i
        g["file"] = f"game_{i}.xhtml"
        if g["kind"] == "sudoku":
            # Grids as images: thick 3x3 rules render the same in every reader.
            from .puzzles import sudoku_png

            g["grid_img"] = add_image_bytes(sudoku_png(g["puzzle"]["grid"]), f"sudoku_{i}.png")
            g["solution_img"] = add_image_bytes(
                sudoku_png(g["solution"]["grid"], givens=g["puzzle"]["grid"]), f"sudoku_{i}_sol.png")
        elif g["kind"] == "crossword":
            from .puzzles import crossword_png

            pz = g["puzzle"]
            g["grid_img"] = add_image_bytes(crossword_png(pz["grid"], pz["numbers"]), f"crossword_{i}.png")
            g["solution_img"] = add_image_bytes(
                crossword_png(pz["grid"], pz["numbers"], g["solution"]["grid"]), f"crossword_{i}_sol.png")

    # The news as pages: a section prints its stories, and every strip prints alone on a page of
    # its own, headed by the strip's name — the layout the cartoon already uses. Pages and the
    # index are derived here instead of rewriting the sections the document was built with.
    news: list[dict] = []
    index: list[dict] = []
    for s in doc.sections:
        stories = [a for a in s["articles"] if not a.get("image_only")]
        rows: list[dict] = []
        if stories:
            news.append({"uid": f"sec-{s['slug']}", "file": s["file"], "title": s["name"],
                         "body": tpl("section.html.j2").render(
                             ed=ed, L=L, sec={**s, "articles": stories})})
            rows += [{"title": a["title"], "href": f"{s['file']}#a{a['id']}"} for a in stories]
        for a in s["articles"]:
            if not a.get("image_only"):
                continue
            file = f"comic_{a['id']}.xhtml"
            # Listed by name and day: the headline is only the day, and the section only says
            # "Quadrinhos", so the navigation carries the strip's name.
            label = f"{a['feed_title'] or a['provider']} — {a['title']}"
            news.append({"uid": f"comic-{a['id']}", "file": file, "title": label,
                         "body": tpl("comic.html.j2").render(L=L, c=a)})
            rows.append({"title": label, "href": f"{file}#a{a['id']}"})
        # A section of nothing but strips has no story page, so its heading leads to the first one.
        head = s["file"] if stories or not rows else rows[0]["href"]
        index.append({"name": s["name"], "href": head, "links": rows})

    front = _page("front", "front.xhtml", L["front_page"], tpl("front.html.j2").render(
        ed=ed, L=L, headline=doc.headline, index=index, games=doc.games,
        has_charge=bool(doc.charge)), doc.lang, css)
    book.add_item(front)
    spine.append(front)
    toc.append(front)

    if doc.test_checklist:
        check = _page("kindle-test", "kindle_test.xhtml", L["test_title"],
                      tpl("kindle_test.html.j2").render(L=L, games=doc.games), doc.lang, css)
        book.add_item(check)
        spine.append(check)
        toc.append(check)

    def add_news() -> None:
        for p in news:
            page = _page(p["uid"], p["file"], p["title"], p["body"], doc.lang, css)
            book.add_item(page)
            spine.append(page)
            toc.append(page)

    def add_charge() -> None:
        if not doc.charge:
            return
        charge = dict(doc.charge)
        charge["image"] = add_image(charge["image_path"], "charge.png")
        page = _page("charge", "charge.xhtml", L["charge"],
                     tpl("charge.html.j2").render(L=L, charge=charge), doc.lang, css)
        book.add_item(page)
        spine.append(page)
        toc.append(page)

    def add_games() -> None:
        if not doc.games:
            return
        pages = []
        for g in doc.games:
            first = g["index"] == 0
            if g["kind"] == "sudoku":
                body = tpl("games_sudoku.html.j2").render(ed=ed, L=L, g=g, first=first)
            elif g["kind"] == "wordle":
                help_ = L["wordle_help_native" if doc.native else "wordle_help"].format(n=g["puzzle"]["length"], a=g["puzzle"]["attempts"])
                body = tpl("games_wordle.html.j2").render(ed=ed, L=L, g=g, first=first,
                                                                       help=help_)
                for j, guess in enumerate(g["puzzle"]["pocket"]):
                    gp = _page(f"wordle-{g['index']}-{j}", f"wordle_{g['index']}_{j}.xhtml", guess["word"],
                               tpl("wordle_guess.html.j2").render(L=L, g=g, guess=guess),
                               doc.lang, css)
                    book.add_item(gp)
                    nonlinear.append(gp)
            elif g["kind"] == "crossword":
                body = tpl("games_crossword.html.j2").render(ed=ed, L=L, g=g, first=first)
            else:
                help_ = L["wordsearch_help"].format(theme=g["puzzle"]["theme"])
                body = tpl("games_wordsearch.html.j2").render(ed=ed, L=L, g=g, first=first,
                                                                           help=help_)
            page = _page(f"game-{g['index']}", g["file"], g["title"], body, doc.lang, css)
            book.add_item(page)
            spine.append(page)
            pages.append(page)
        toc.append((epub.Section(L["games"], href=pages[0].file_name), pages))

    for part in doc.closing_order:
        {"news": add_news, "charge": add_charge, "games": add_games}[part]()

    colophon = _page("colophon", "colophon.xhtml", L["colophon"], tpl("colophon.html.j2").render(
        ed=ed, L=L, sources=doc.sources, curated_by=doc.curated_by, generated_at=doc.generated_at),
        doc.lang, css)
    book.add_item(colophon)
    spine.append(colophon)
    toc.append(colophon)

    if doc.games and doc.native:
        guard = _page("answers-ahead", "answers_ahead.xhtml", L["answers_ahead"],
                      tpl("answers_ahead.html.j2").render(L=L), doc.lang, css)
        book.add_item(guard)
        spine.append(guard)

    if doc.games:
        for g in doc.games:
            g["hits"] = set()
            if g["kind"] == "wordsearch":
                for p in g["solution"]["placements"]:
                    (r0, c0), (r1, c1) = p["start"], p["end"]
                    n = len(p["word"])
                    dr = (r1 - r0) // max(1, n - 1)
                    dc = (c1 - c0) // max(1, n - 1)
                    for k in range(n):
                        g["hits"].add((r0 + dr * k, c0 + dc * k))
        sol = _page("solutions", "solutions.xhtml", L["solutions"],
                    tpl("solutions.html.j2").render(L=L, games=doc.games), doc.lang, css)
        book.add_item(sol)
        nonlinear.insert(0, sol)  # only reachable through "see solution" links: no spoilers
        toc.append(sol)

    for p in nonlinear:
        spine.append((p.id, "no"))

    book.toc = toc
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = spine
    dest.parent.mkdir(parents=True, exist_ok=True)
    epub.write_epub(str(dest), book, {"epub3_pages": False})
    return dest
