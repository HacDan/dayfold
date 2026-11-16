import re
import zipfile
from pathlib import Path

from dayfold.edition.cover import CoverData, render_cover
from dayfold.edition.epub import EditionDoc, build_epub
from dayfold.games.generators import crossword, seeded, sudoku, wordle, wordsearch


def test_cover_and_epub(tmp_path: Path):
    cover = render_cover(CoverData(title="Dayfold", masthead_font="chomsky", tagline="t", long_date="Hoje",
                                   weather=["Springfield · Overcast · High 43°F · Low 37°F",
                                            "Sunrise 06:49 · Sunset 16:25"],
                                   number_label="Nº 1", year_label="Ano I", daily_label="Diária",
                                   headline="Manchete de teste", secondary=[("Mundo", "Outra")]),
                         tmp_path / "cover.png")
    games = []
    for kind, fn in (("sudoku", lambda r: sudoku(r)), ("wordle", lambda r: wordle(r)), ("wordsearch", lambda r: wordsearch(r)),
                     ("crossword", lambda r: crossword(r))):
        p, s = fn(seeded("t", kind))
        games.append({"kind": kind, "title": kind, "puzzle": p, "solution": s})
    art = {"id": 1, "title": "Manchete", "subtitle": None, "author": "A", "date_label": "hoje", "provider": "P",
           "url": "https://x.org", "url_short": "x.org", "paragraphs": ["Um", "Dois"], "excerpt": None,
           "section_name": "Brasil"}
    doc = EditionDoc(identifier="dayfold-test", lang="pt", title="Dayfold", tagline="t", long_date="Hoje",
                     short_date="hoje", iso_date="2026-01-01", number_label="Nº 1", year_label="Ano I",
                     masthead_font="chomsky", typography={"masthead": 3, "headline": 2, "title": 1.4, "subtitle": 1,
                                                          "body": 1, "line_height": 1.5},
                     cover_path=cover, headline=art,
                     sections=[{"slug": "mundo", "name": "Mundo", "file": "sec_mundo.xhtml",
                                "articles": [dict(art, id=2, excerpt="Excerto", paragraphs=[])]}],
                     games=games)
    import copy

    native_doc = copy.deepcopy(doc)
    path = build_epub(doc, tmp_path / "e.epub")
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        assert "EPUB/front.xhtml" in names and "EPUB/solutions.xhtml" in names
        assert any(n.endswith("Chomsky.otf") for n in names)
        assert "dayfold://game/0" in z.read("EPUB/game_0.xhtml").decode()
        assert "crossword_3.png" in z.read("EPUB/game_3.xhtml").decode()

        # reading starts on the cover, then turns to the front page
        opf = z.read("EPUB/content.opf").decode()
        itemrefs = re.findall(r"<itemref[^>]*/>", opf)
        assert 'idref="cover"' in itemrefs[0] and "linear" not in itemrefs[0]
        assert 'idref="front"' in itemrefs[1] and "linear" not in itemrefs[1]
        assert "EPUB/cover.xhtml" in names and 'properties="cover-image"' in opf

    # native Kindle variant: no KOReader links, answers only after the warning page
    from dataclasses import replace

    native = build_epub(replace(native_doc, native=True, test_checklist=True), tmp_path / "n.epub")
    with zipfile.ZipFile(native) as z:
        pages = {n: z.read(n).decode() for n in z.namelist() if n.endswith(".xhtml")}
        opf = z.read("EPUB/content.opf").decode()
    assert not any("dayfold://" in body for body in pages.values())
    assert "EPUB/kindle_test.xhtml" in pages and "EPUB/answers_ahead.xhtml" in pages
    spine = re.findall(r'<itemref idref="([^"]+)"', opf)
    assert spine.index("answers-ahead") < spine.index("solutions")
    assert spine.index("colophon") < spine.index("answers-ahead")
    assert all(spine.index(i) > spine.index("answers-ahead") for i in spine if i.startswith("wordle-"))
